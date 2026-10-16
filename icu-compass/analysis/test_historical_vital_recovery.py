import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import build_gs_board_pool as builder
import diagnose_gs_001_availability as recovery


class HistoricalRecoveryTests(unittest.TestCase):
    def test_recovery_preserves_frozen_facts_and_excludes_wrong_stay_or_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Path(directory);root=workspace/'datasets';out=workspace/'runtime'/'gs-board-pool'
            out.mkdir(parents=True);part=root/'kmimic-emr-001'/'1';part.mkdir(parents=True)
            selection_dir=out.parent/'gs-scenario-selection';selection_dir.mkdir()
            selected={'hospital':'001','SUBJECT_ID':'1','HADM_ID':'10','STAY_ID':'100',
                      'icu_in':'2020-01-01T00:00:00','icu_out':'2020-01-01T01:01:00',
                      'source_partition_list':['1'],'case_alias':'GS-CASE-001',
                      'gs_entry_evidence':{'table':'SERVICES','at':'2020-01-01T00:00:00','code':'GS'},
                      'scenario_labels':[],'evidence':{},'preferred_checkpoint':{'minute':0}}
            p=builder.build_case(selected,{}, {'D_ITEMS':{},'D_LABITEMS':{},'D_TESTITEMS':{}},{},{},14321)
            original=json.loads(json.dumps(p));(out/'pool_gs.json').write_text(json.dumps([p]))
            (selection_dir/'selected_cases.json').write_text(json.dumps({'cases':[selected]}))
            (part/'D_ITEMS.csv').write_text('ITEMID,LABEL,UNITNAME,CATEGORY\n001C_1021_25105,Heart rate,bpm,vital\n')
            fields=['SUBJECT_ID','HADM_ID','STAY_ID','ITEMID','CHARTTIME','STORETIME','VALUE','VALUEUOM','CHARTEVENT_ID']
            base={'SUBJECT_ID':'1','HADM_ID':'10','STAY_ID':'100','ITEMID':'001C_1021_25105',
                  'CHARTTIME':'2020-01-01T00:05:00','STORETIME':'','VALUE':'90','VALUEUOM':'bpm','CHARTEVENT_ID':'1'}
            rows=[base,{**base,'VALUE':'110','CHARTEVENT_ID':'2'},
                  {**base,'CHARTTIME':'2020-01-01T00:06:00','STORETIME':'2020-01-01T00:05:00','CHARTEVENT_ID':'3'},
                  {**base,'CHARTTIME':selected['icu_out'],'CHARTEVENT_ID':'4'},
                  {**base,'STAY_ID':'101','CHARTEVENT_ID':'5'}]
            with (part/'CHARTEVENTS.csv').open('w',newline='') as handle:
                writer=csv.DictWriter(handle,fields);writer.writeheader();writer.writerows(rows)
            with patch.object(recovery,'W',out.parent),patch.object(recovery,'ROOT',root),patch.object(recovery,'OUT',out),contextlib.redirect_stdout(io.StringIO()):
                recovery.main(True,True)
            result=json.loads((out/'pool_gs.json').read_text())[0]
            records=result.pop('historical_vital_observations');result.pop('historical_vital_scope')
            self.assertEqual(result,original)
            self.assertEqual(len(records),3)
            self.assertTrue(all(r['historical_only'] and r['availability_status']=='unknown' for r in records))
            self.assertEqual(sum(r['same_time_conflict'] for r in records),2)
            self.assertTrue(all(r['chart_minute']<61 and r['unit']=='bpm' for r in records))
            self.assertEqual({r['availability_reason'] for r in records},{'missing_storetime','store_before_chart'})


if __name__=='__main__':unittest.main()
