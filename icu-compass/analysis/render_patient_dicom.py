"""Decode a single grayscale DICOM into a private, non-diagnostic PNG preview.
Registration requires a separately audited patient/test linkage; this module does
not discover patients or register arbitrary files in the web server.
"""
import io
import copy
import hashlib
import numpy as np
from PIL import Image
import pydicom
from pydicom.pixels import apply_modality_lut, apply_voi_lut


def preview_bytes(ds):
    if str(ds.get('Modality', '')) not in ('CR', 'DX', 'CT'):
        raise ValueError('Unsupported modality')
    if int(ds.get('NumberOfFrames', 1)) != 1 or int(ds.get('SamplesPerPixel', 1)) != 1:
        raise ValueError('Only single-frame grayscale previews supported')
    photo = str(ds.get('PhotometricInterpretation', ''))
    if photo not in ('MONOCHROME1', 'MONOCHROME2'):
        raise ValueError('Unsupported photometric interpretation')
    if not (0 < int(ds.Rows) <= 12000 and 0 < int(ds.Columns) <= 12000) or int(ds.Rows)*int(ds.Columns)>40000000:
        raise ValueError('Unsupported image dimensions')
    pixels = ds.pixel_array
    if pixels.ndim != 2:
        raise ValueError('Unsupported image shape')
    # De-identified exports can retain empty DS tags. Pydicom treats their
    # presence as a transform and otherwise multiplies pixels by None.
    display = copy.deepcopy(ds)
    omitted = []
    for group in (('RescaleSlope', 'RescaleIntercept'), ('WindowCenter', 'WindowWidth')):
        if any(k in display for k in group) and any(display.get(k) in (None, '') for k in group):
            for k in group:
                if k in display: del display[k]
            omitted.append('/'.join(group))
    rendered = np.asarray(apply_voi_lut(apply_modality_lut(pixels, display), display), dtype=np.float64)
    if not np.isfinite(rendered).all():
        raise ValueError('Invalid pixel values')
    low, high = float(rendered.min()), float(rendered.max())
    if high <= low:
        raise ValueError('Constant image')
    gray = np.clip((rendered-low)/(high-low), 0, 1)
    if photo == 'MONOCHROME1':
        gray = 1-gray
    out=io.BytesIO();Image.fromarray(np.rint(gray*255).astype(np.uint8)).save(out,format='PNG')
    return out.getvalue(), {'width':int(ds.Columns), 'height':int(ds.Rows),
                           'modality':str(ds.Modality), 'view_position':str(ds.get('ViewPosition','')),
                           'rendering':'Available DICOM modality/VOI transform, min-max 8-bit preview; not diagnostic',
                           'omitted_empty_transforms':omitted}


def render(path, directory):
    from pathlib import Path
    path=Path(path)
    if path.stat().st_size > 50*1024*1024:
        raise ValueError('DICOM exceeds per-file limit')
    ds=pydicom.dcmread(path)
    data,meta=preview_bytes(ds)
    key=hashlib.sha256(data).hexdigest()
    dest=Path(directory)/(key+'.png');dest.write_bytes(data);dest.chmod(0o600)
    return {'image_id':key, **meta, 'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
