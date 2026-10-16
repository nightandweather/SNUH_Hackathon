import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from patient_imaging import ImageRegistry
from grounded_chat import ChatError
from vision_review import VisionReviews,validate,configuration

class ReviewBoundaries(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
  png=b'\x89PNG\r\n\x1a\nfixture';self.key=hashlib.sha256(png).hexdigest();(root/(self.key+'.png')).write_bytes(png)
  self.case={'id':'CASE-1','_image_binding':'a','rows':[{'minute':5},{'minute':30}], '_clinical':{'imaging_tests':[{'name':'Chest AP','record_ref':'t','chart_minute':10,'available_minute':20}]}}
  self.entry={'binding':'a','verified':True,'record_ref':'t','chart_minute':10,'available_minute':20,'image_id':self.key,'modality':'CR'}
  (root/'verified.json').write_text(json.dumps({'images':[self.entry]}));self.registry=ImageRegistry(root)
  self.calls=[]
  def complete(messages):
   self.calls.append(messages)
   return json.dumps({'summary':'AI review','image_quality':'Review limited','visible_findings':['Uncertain appearance'], 'uncertainties':['No comparison'], 'clinician_review':['Radiologist review'],'nursing_focus':['Confirm current observations']}),'vision-model'
  self.service=VisionReviews({'cases':[self.case,{**self.case,'id':'CASE-2','_image_binding':'b'}]},self.registry,complete)
  self.patch=patch('vision_review.context_for',side_effect=lambda c,i:{'case_id':c['id'],'row_index':i,'facts':[{'id':'F1','kind':'scope'}],'context_hash':'frozen'})
  self.patch.start();self.addCleanup(self.patch.stop)
  self.body={'case_id':'CASE-1','row_index':1,'image_id':self.key,'language':'ko','question':'Review this CXR'}
 def test_image_actually_sent_with_same_case(self):
  out=self.service.review(self.body);self.assertTrue(out['image_input']);self.assertFalse(out['official_report'])
  content=self.calls[0][1]['content'];self.assertTrue(content[1]['image_url']['url'].startswith('data:image/png;base64,'))
  self.assertEqual(json.loads(content[0]['text'])['SOURCE_FACTS']['case_id'],'CASE-1')
 def test_other_patient_future_and_arbitrary_path_do_not_call_model(self):
  for change in ({'case_id':'CASE-2'},{'row_index':0},{'image_id':'../../secret'}):
   with self.assertRaises(ChatError):self.service.review({**self.body,**change})
  self.assertEqual(self.calls,[])
 def test_tampered_png_not_sent(self):
  (self.registry.root/(self.key+'.png')).write_bytes(b'corrupt')
  with self.assertRaises(ChatError):self.service.review(self.body)
  self.assertEqual(self.calls,[])
 def test_unknown_availability_is_explicit_retrospective(self):
  self.case['_clinical']['imaging_tests'][0]['available_minute']=None;self.entry['available_minute']=None
  (self.registry.root/'verified.json').write_text(json.dumps({'images':[self.entry]}))
  out=self.service.review(self.body);self.assertFalse(out['availability_known'])
  supplied=json.loads(self.calls[0][1]['content'][0]['text']);self.assertIn('retrospective',supplied['review_scope'])
 def test_only_approved_gateway(self):
  with patch.dict('os.environ',{'LLM_BASE_URL':'https://unapproved.example/v1'},clear=True):
   with self.assertRaises(ChatError):configuration()
 def test_invalid_output_rejected(self):
  for raw in ('not json','{}','{"summary":"invented"}'):
   with self.assertRaises(ChatError):validate(raw)
if __name__=='__main__':unittest.main()
