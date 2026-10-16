"""Private preview registry. Never expose DICOM headers or arbitrary file paths."""
import hashlib
import json
import math
import re
from pathlib import Path


def binding(provenance):
    identity = provenance.get('source_identity')
    if not isinstance(identity, dict) or not all(identity.get(k) for k in ('SUBJECT_ID', 'HADM_ID', 'STAY_ID')):
        return None
    return hashlib.sha256(json.dumps([provenance.get('dataset'), identity], sort_keys=True).encode()).hexdigest()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


class ImageRegistry:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def entries(self, case, row_index):
        if type(row_index) is not int or not 0 <= row_index < len(case['rows']):
            raise ValueError('Invalid observation index')
        minute = case['rows'][row_index]['minute']
        if not case.get('_image_binding'):
            return []
        try:
            manifest = json.loads((self.root / 'verified.json').read_text())
        except FileNotFoundError:
            manifest = {}
        tests = {r.get('record_ref'): r for r in case.get('_clinical', {}).get('imaging_tests', []) if r.get('record_ref')}
        result = []
        for r in manifest.get('images', []):
            if r.get('binding') != case['_image_binding'] or r.get('verified') is not True:
                continue
            test = tests.get(r.get('record_ref'))
            if not test or not finite(test.get('chart_minute')) or test['chart_minute'] > minute:
                continue
            # Registry timestamps must match the source, never user-provided query parameters.
            if r.get('chart_minute') != test['chart_minute'] or r.get('available_minute') != test.get('available_minute'):
                continue
            available = test.get('available_minute')
            if finite(available) and (available < test['chart_minute'] or available > minute):
                continue
            if not re.fullmatch(r'[a-f0-9]{64}', str(r.get('image_id', ''))) or r.get('modality') not in ('CR', 'DX', 'CT'):
                continue
            file = (self.root / (r['image_id'] + '.png')).resolve()
            if file.parent != self.root or not file.is_file():
                continue
            result.append({**r, '_file':file, 'availability_known':finite(available)})
        return result + self.simulation_entries(case)

    def simulation_entries(self, case):
        """Explicit random pairing, never evidence of this patient's actual imaging."""
        try:
            manifest = json.loads((self.root / 'simulation.json').read_text())
        except FileNotFoundError:
            return []
        if manifest.get('enabled') is not True or not case.get('_image_binding'):
            return []
        result = []
        for r in manifest.get('assignments', []):
            if r.get('case_id') != case['id'] or r.get('binding') != case['_image_binding']:
                continue
            if r.get('linkage') != 'random_simulation' or r.get('modality') not in ('CR','DX'):
                continue
            key = str(r.get('image_id',''))
            if not re.fullmatch(r'[a-f0-9]{64}',key): continue
            file = (self.root / 'simulation' / (key + '.png')).resolve()
            if file.parent != (self.root / 'simulation').resolve() or not file.is_file(): continue
            result.append({**r, '_file':file, 'chart_minute':None, 'available_minute':None,
                           'availability_known':False, 'patient_linked':False})
        return result

    def listing(self, case, row_index):
        rows = self.entries(case, row_index)
        return {'case_id':case['id'], 'row_index':row_index, 'images':[
            {**{k:r.get(k) for k in ('image_id','modality','chart_minute','available_minute','availability_known','width','height','linkage','patient_linked')},
             'name':'CXR · 무작위 모의 배정' if r.get('linkage') == 'random_simulation' else next(t.get('name','CXR') for t in case['_clinical']['imaging_tests'] if t.get('record_ref') == r['record_ref']),
             'view_position':r.get('view_position') if r.get('view_position') in ('AP','PA','LL','RL') else None,
             'portable':r.get('portable') if type(r.get('portable')) is bool else None,
             'model_input':False} for r in rows]}

    def png(self, case, row_index, image_id):
        match = next((r for r in self.entries(case, row_index) if r['image_id'] == image_id), None)
        if not match:
            raise FileNotFoundError('Image not available for this case and time')
        if match['_file'].stat().st_size > 30 * 1024 * 1024:
            raise ValueError('Preview too large')
        data = match['_file'].read_bytes()
        if not data.startswith(b'\x89PNG\r\n\x1a\n') or hashlib.sha256(data).hexdigest() != match['image_id']:
            raise ValueError('Preview verification failed')
        return data
