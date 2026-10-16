import sys,io,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import numpy as np
from PIL import Image
from pydicom.dataset import Dataset,FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian
from render_patient_dicom import preview_bytes
class PreviewTest(unittest.TestCase):
 def sample(self):
  d=Dataset();d.file_meta=FileMetaDataset();d.file_meta.TransferSyntaxUID=ExplicitVRLittleEndian
  d.Modality='CR';d.Rows=2;d.Columns=2;d.SamplesPerPixel=1;d.PhotometricInterpretation='MONOCHROME2';d.BitsAllocated=16;d.BitsStored=12;d.HighBit=11;d.PixelRepresentation=0;d.PixelData=np.array([[0,100],[200,300]],dtype='<u2').tobytes();d.PatientName='DO_NOT_EXPORT';return d
 def test_orientation_polarity_and_no_metadata(self):
  d=self.sample();b,m=preview_bytes(d);a=np.asarray(Image.open(io.BytesIO(b)));self.assertEqual(a.tolist(),[[0,85],[170,255]])
  self.assertNotIn(b'DO_NOT_EXPORT',b);self.assertNotIn('DO_NOT_EXPORT',str(m))
  d.PhotometricInterpretation='MONOCHROME1';b,_=preview_bytes(d);self.assertEqual(np.asarray(Image.open(io.BytesIO(b))).tolist(),[[255,170],[85,0]])
 def test_multi_frame_and_unhandled_types_blocked(self):
  d=self.sample();d.NumberOfFrames=2
  with self.assertRaises(ValueError):preview_bytes(d)
  d=self.sample();d.PhotometricInterpretation='RGB'
  with self.assertRaises(ValueError):preview_bytes(d)
 def test_windowed_preview_is_finite(self):
  d=self.sample();d.WindowCenter=150;d.WindowWidth=150;d.RescaleSlope=2;d.RescaleIntercept=-10
  b,m=preview_bytes(d);a=np.asarray(Image.open(io.BytesIO(b)));self.assertEqual(a.shape,(2,2));self.assertEqual(a[0,0],0);self.assertEqual(a[1,1],255)
 def test_anonymized_empty_transform_tags(self):
  d=self.sample();d.RescaleSlope=None;d.RescaleIntercept=None;d.WindowCenter=None;d.WindowWidth=None
  b,m=preview_bytes(d)
  self.assertEqual(np.asarray(Image.open(io.BytesIO(b))).tolist(),[[0,85],[170,255]])
  self.assertEqual(len(m['omitted_empty_transforms']),2)
  self.assertIn('RescaleSlope',d)
if __name__=='__main__':unittest.main()
