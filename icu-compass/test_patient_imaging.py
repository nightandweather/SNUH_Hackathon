import hashlib,json,tempfile,unittest
from pathlib import Path
from patient_imaging import ImageRegistry

class ImageAccess(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.data=b'\x89PNG\r\n\x1a\nfixture';self.key=hashlib.sha256(self.data).hexdigest()
  (self.root/(self.key+'.png')).write_bytes(self.data)
  self.case={'id':'CASE-1','_image_binding':'binding-A','rows':[{'minute':10},{'minute':30}], '_clinical':{'imaging_tests':[{'record_ref':'test-a','name':'Chest AP','chart_minute':15,'available_minute':20}]}}
  self.entry={'binding':'binding-A','verified':True,'record_ref':'test-a','chart_minute':15,'available_minute':20,'image_id':self.key,'modality':'CR','object_key':'PRIVATE','PatientID':'PRIVATE'}
  self.save();self.reg=ImageRegistry(self.root)
 def save(self): (self.root/'verified.json').write_text(json.dumps({'images':[self.entry]}))
 def test_case_time_and_metadata_boundary(self):
  self.assertEqual(self.reg.listing(self.case,0)['images'],[])
  info=self.reg.listing(self.case,1);self.assertEqual(len(info['images']),1);self.assertNotIn('PRIVATE',str(info));self.assertNotIn('binding-A',str(info))
  self.assertEqual(self.reg.png(self.case,1,self.key),self.data)
  other={**self.case,'_image_binding':'other'}
  with self.assertRaises(FileNotFoundError):self.reg.png(other,1,self.key)
  with self.assertRaises(FileNotFoundError):self.reg.png(self.case,0,self.key)
 def test_missing_test_mismatch_traversal_and_tampering(self):
  for field,value in [('record_ref','other'),('chart_minute',16),('available_minute',0),('verified',False),('image_id','../private')]:
   old=self.entry[field];self.entry[field]=value;self.save();self.assertEqual(self.reg.listing(self.case,1)['images'],[]);self.entry[field]=old
  self.save();(self.root/(self.key+'.png')).write_bytes(b'other')
  with self.assertRaises(ValueError):self.reg.png(self.case,1,self.key)
 def test_unknown_availability_is_retrospective_and_not_model_input(self):
  self.case['_clinical']['imaging_tests'][0]['available_minute']=None;self.entry['available_minute']=None;self.save()
  image=self.reg.listing(self.case,1)['images'][0];self.assertFalse(image['availability_known']);self.assertFalse(image['model_input'])
 def test_symlink_cannot_escape_private_registry(self):
  with tempfile.TemporaryDirectory() as other:
   f=Path(other)/'outside.png';f.write_bytes(self.data);p=self.root/(self.key+'.png');p.unlink();p.symlink_to(f)
   self.assertEqual(self.reg.listing(self.case,1)['images'],[])
if __name__=='__main__':unittest.main()
