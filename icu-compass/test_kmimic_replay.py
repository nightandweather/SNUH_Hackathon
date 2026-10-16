"""Synthetic fixtures only: no K-MIMIC patient records leave KHDP."""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ReplayExtractionTests(unittest.TestCase):
    def test_all_partitions_namespaces_units_and_no_future_or_stale_fill(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'datasets'; out = Path(temp)/'out'
            def write(part, name, fields, rows):
                part.mkdir(parents=True, exist_ok=True)
                with (part/name).open('w') as f:
                    w=csv.DictWriter(f, fieldnames=fields);w.writeheader();w.writerows(rows)
            cols=['SUBJECT_ID','HADM_ID','STAY_ID','FIRST_CAREUNIT','INTIME','OUTTIME']
            stay=dict(zip(cols,['1','1','1','SICU','2020-01-01 00:00:00','2020-01-01 02:00:00']))
            first=root/'kmimic-emr-001'/'001'
            write(first,'ICUSTAYS.csv',cols,[stay])
            write(root/'kmimic-emr-001'/'002','ICUSTAYS.csv',cols,[stay,dict(stay,SUBJECT_ID='2',FIRST_CAREUNIT='TSICU'),dict(stay,SUBJECT_ID='3',FIRST_CAREUNIT='1ICU')])
            write(root/'kmimic-emr-009'/'001','ICUSTAYS.csv',cols,[stay])
            mapping={'001C_1021_25105':('hr','회/min',80),'001C_1014_27095':('map','mmHg',70),'001C_1003_24480':('spo2','%',98),'001C_1023_27310':('rr','회/min',24),'001C_1012_24795':('sbp','mmHg',100)}
            write(first,'D_ITEMS.csv',['ITEMID','UNITNAME'],[{'ITEMID':k,'UNITNAME':v[1]} for k,v in mapping.items()])
            events=[]
            for iid,(_,unit,value) in mapping.items():
                for minute in range(5,60,5):
                    events.append(dict(SUBJECT_ID='1',HADM_ID='1',STAY_ID='1',ITEMID=iid,VALUEUOM='',VALUENUM=value,CHARTTIME=f'2020-01-01 00:{minute:02d}:00'))
            events.append(dict(events[0],VALUENUM=0))
            events.append(dict(events[0],VALUEUOM='wrong-unit',VALUENUM=90))
            write(first,'CHARTEVENTS.csv',list(events[0]),events)
            env=dict(os.environ,KMIMIC_ROOT=str(root),KMIMIC_OUTPUT=str(out))
            subprocess.run([sys.executable,str(Path(__file__).with_name('build_surgical_replay.py'))],env=env,check=True,capture_output=True)
            summary=json.loads((out/'cohort_summary.json').read_text())['datasets']
            self.assertEqual(summary['kmimic-emr-001']['candidate_stays'],2)
            self.assertEqual(summary['kmimic-emr-009']['candidate_stays'],1)
            pool=json.loads((out/'pool_kmimic.json').read_text());self.assertEqual(len(pool),1)
            self.assertIsNone(pool[0]['series']['hr'][0]) # first measurement is in the future
            self.assertEqual(pool[0]['series']['hr'][1],80)
            self.assertIsNone(pool[0]['series']['hr'][18]) # 35 minutes since last observation
            self.assertEqual(pool[0]['measurement_age_min']['hr'][17],30)
            audit=json.loads((out/'replay_audit.json').read_text())
            self.assertEqual(audit['rejections']['invalid:hr'],1)
            self.assertEqual(audit['rejections']['unit:hr:wrong-unit'],1)


if __name__=='__main__':
    unittest.main()
