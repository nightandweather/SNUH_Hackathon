import unittest
from copy import deepcopy
from clinical_detail import snapshot, model_facts
from grounded_chat import context_for

class ClinicalDetails(unittest.TestCase):
    def test_imaging_filters_include_old_records_and_never_publish_paths(self):
        c = self.case()
        c['_clinical']['imaging_tests'] = [dict(itemid=str(i), name='Other test', chart_minute=30,
            available_minute=31) for i in range(65)] + [dict(itemid='XR', name='Chest AP portable',
            chart_minute=1, available_minute=2, FILE_PATH='PRIVATE', file_path='PRIVATE',
            file_reference_present=True, report_text='UNVERIFIED', image_url='UNVERIFIED'),
            dict(itemid='CT', name='Abdomen CT', chart_minute=3, available_minute=4),
            dict(itemid='F', name='Chest AP', chart_minute=50, available_minute=61)]
        s = snapshot(c, 0, test_kind='cxr')
        self.assertEqual([r['itemid'] for r in s['tests']], ['XR'])
        self.assertEqual(s['tests'][0]['imaging_kind'], 'portable_cxr')
        self.assertEqual(s['tests'][0]['image_status'], 'not_linked')
        self.assertNotIn('PRIVATE', str(s)); self.assertNotIn('UNVERIFIED', str(s))
        self.assertEqual(snapshot(c, 0, test_kind='ct', test_query='abdomen')['test_filtered_count'], 1)
        self.assertEqual(len(snapshot(c, 0, test_offset=60)['tests']), 7)
        self.assertEqual(snapshot(c, 0)['test_counts']['cxr'], 0)
        self.assertEqual(snapshot(c, 0, test_kind='ct', test_query='chest')['tests'], [])

    def test_imaging_classifier_does_not_infer_portable_from_ap(self):
        from clinical_detail import imaging_kind
        for name, expected in [('Chest AP','cxr'), ('Portable Chest','portable_cxr'),
                               ('흉부 이동식 촬영','portable_cxr'), ('CT 조영제','ct'),
                               ('ACTH','other'), ('Chest ultrasound','other')]:
            self.assertEqual(imaging_kind({'name':name}), expected)
        for kwargs in ({'test_kind':'bad'}, {'test_query':None}, {'test_offset':-1}, {'test_offset':True}):
            with self.assertRaises(ValueError): snapshot(self.case(), 0, **kwargs)

    def case(self):
        return {'id':'CASE-001','rows':[{'minute':60}], '_clinical':{'status':'linked','admission':{'admit_minute':-100},'current_diagnoses':[{'code':'FUTURE-DIAGNOSIS'}], 'past_diagnoses':[{'code':'OLD','name_status':'verified','name_en':'Prior condition','prior_discharge_minute':-101},{'code':'SAME-ADMISSION','prior_discharge_minute':-99}], 'labs':[{'itemid':'A','name':'Test','value':'12.5','unit':'g/dL','chart_minute':20,'available_minute':30},{'itemid':'A','value':'NOT-YET-AVAILABLE','chart_minute':50,'available_minute':70},{'itemid':'B','value':'FUTURE','chart_minute':80,'available_minute':90},{'itemid':'C','value':'NO-STORE','chart_minute':10,'available_minute':None},{'itemid':'D','value':'INVALID-TIME','chart_minute':50,'available_minute':40}], 'imaging_tests':[], 'coverage':{}}}
    def test_store_time_and_future_exclusion(self):
        c=self.case();s=snapshot(c,0)
        self.assertEqual([r['value'] for r in s['labs']],['12.5'])
        self.assertEqual(s['lab_availability_unknown_count'],1)
        self.assertEqual([r['code'] for r in s['past_diagnoses']],['OLD'])
    def test_retrospective_diagnoses_only_in_ui(self):
        c=self.case();self.assertIn('FUTURE-DIAGNOSIS',str(snapshot(c,0)))
        f=str(model_facts(c,0));self.assertNotIn('FUTURE-DIAGNOSIS',f);self.assertNotIn('NOT-YET',f);self.assertIn('12.5',f)
    def test_case_isolation_and_unknown(self):
        c=self.case();other={'id':'CASE-002','rows':[{'minute':60}]}
        self.assertEqual(model_facts(other,0),[])
        self.assertEqual(snapshot(other,0)['status'],'unlinked')
        self.assertNotIn('12.5',str(snapshot(other,0)))
        self.assertIn('assessment',snapshot(other,0))
        self.assertIsNone(snapshot(other,0)['assessment']['calculator']['score'])
        self.assertEqual(snapshot(other,0)['assessment']['calculator']['range'],[0,3])
    def test_qualitative_and_conflicting_results_excluded_from_model(self):
        c=self.case();c['_clinical']['labs'].append({'itemid':'A','value':'9.2','unit':'g/dL','chart_minute':20,'available_minute':31})
        self.assertTrue(all(r['same_time_conflict'] for r in snapshot(c,0)['labs']))
        self.assertFalse(any(f['kind']=='laboratory' for f in model_facts(c,0)))
        c=self.case();c['_clinical']['labs'][0]['unit']=''
        self.assertFalse(any(f['kind']=='laboratory' for f in model_facts(c,0)))
    def test_invalid_index(self):
        for index in (-1,1,True,'0'):
            with self.assertRaises(ValueError):snapshot(self.case(),index)
    def test_earlier_time_removes_results(self):
        c=self.case();c['rows'][0]['minute']=25
        self.assertEqual(snapshot(c,0)['labs'],[])

    def large_case(self):
        c = self.case()
        c['rows'][0]['minute'] = 1000
        c['_clinical']['labs'] = [
            {'itemid':'HB', 'name':'Hemoglobin', 'value':str(10 + i / 100),
             'unit':'g/dL', 'chart_minute':i + 100, 'available_minute':i + 101}
            for i in range(245)
        ] + [{'itemid':'OLD-NA', 'name':'Sodium', 'value':'138', 'unit':'mmol/L',
              'chart_minute':1, 'available_minute':2, 'SUBJECT_ID':'PRIVATE', 'file_path':'PRIVATE'}]
        return c

    def test_catalog_and_filter_include_results_older_than_default_page(self):
        c = self.large_case()
        default = snapshot(c, 0)
        self.assertEqual(len(default['labs']), 120)
        self.assertEqual(default['laboratory_available_count'], 246)
        self.assertEqual(default['laboratory_filtered_count'], 246)
        self.assertFalse(any(r['itemid'] == 'OLD-NA' for r in default['labs']))
        self.assertEqual(default['lab_items'], [
            {'itemid':'HB', 'name':'Hemoglobin', 'count':245},
            {'itemid':'OLD-NA', 'name':'Sodium', 'count':1}])
        selected = snapshot(c, 0, lab_item='OLD-NA')
        self.assertEqual([r['value'] for r in selected['labs']], ['138'])
        self.assertEqual(selected['laboratory_available_count'], 246)
        self.assertEqual(selected['laboratory_filtered_count'], 1)
        self.assertNotIn('PRIVATE', str(selected))

    def test_lab_pagination_is_applied_after_filtering(self):
        c = self.large_case()
        pages = [snapshot(c, 0, lab_item='HB', lab_offset=offset) for offset in (0,120,240,360)]
        self.assertEqual([len(p['labs']) for p in pages], [120,120,5,0])
        self.assertEqual([p['lab_offset'] for p in pages], [0,120,240,360])
        self.assertTrue(all(p['lab_page_size'] == 120 and p['laboratory_filtered_count'] == 245 for p in pages))
        minutes = [r['chart_minute'] for p in pages for r in p['labs']]
        self.assertEqual(minutes, list(range(344,99,-1)))

    def test_lab_search_matches_casefolded_name_and_item_code(self):
        c = self.large_case()
        self.assertEqual(snapshot(c, 0, lab_query='  sODIum ')['laboratory_filtered_count'], 1)
        self.assertEqual(snapshot(c, 0, lab_query='old-na')['laboratory_filtered_count'], 1)
        self.assertEqual(snapshot(c, 0, lab_item='HB', lab_query='sodium')['labs'], [])
        self.assertEqual(snapshot(c, 0, lab_query='unmatched')['laboratory_filtered_count'], 0)
        c['_clinical']['labs'][-1]['itemid'] = 123
        self.assertEqual(snapshot(c, 0, lab_item='123')['laboratory_filtered_count'], 1)

    def test_catalog_excludes_future_unavailable_and_invalid_time_records(self):
        c = self.case()
        s = snapshot(c, 0)
        self.assertEqual(s['lab_items'], [{'itemid':'A', 'name':'Test', 'count':1}])
        self.assertEqual(s['laboratory_available_count'], 1)
        self.assertEqual(snapshot(c, 0, lab_item='B')['labs'], [])
        c['rows'][0]['minute'] = 25
        self.assertEqual(snapshot(c, 0)['lab_items'], [])

    def test_conflict_is_computed_before_query_filter_and_page_slice(self):
        c = self.large_case()
        c['_clinical']['labs'] += [
            {'itemid':'CONFLICT', 'name':'Preferred test', 'value':'1', 'unit':'g/L',
             'chart_minute':500, 'available_minute':501},
            {'itemid':'CONFLICT', 'name':'Alternate label', 'value':'2', 'unit':'g/L',
             'chart_minute':500, 'available_minute':502},
        ]
        s = snapshot(c, 0, lab_query='Preferred')
        self.assertEqual(len(s['labs']), 1)
        self.assertTrue(s['labs'][0]['same_time_conflict'])
        self.assertFalse(any(f.get('itemid') == 'CONFLICT' for f in model_facts(c, 0)))

    def test_ui_filters_do_not_mutate_source_or_default_ai_facts(self):
        c = self.large_case()
        original = deepcopy(c)
        facts_before = model_facts(c, 0)
        self.assertEqual([f['itemid'] for f in facts_before if f['kind'] == 'laboratory'], ['HB'])
        snapshot(c, 0, lab_item='OLD-NA')
        snapshot(c, 0, lab_query='sodium', lab_offset=120)
        self.assertEqual(model_facts(c, 0), facts_before)
        self.assertEqual(c, original)
        self.assertEqual(len(snapshot(c, 0)['labs']), 120)

    def test_invalid_lab_filters(self):
        for kwargs in ({'lab_item':None}, {'lab_query':1}, {'lab_offset':-1},
                       {'lab_offset':True}, {'lab_offset':1.5}, {'lab_offset':'120'},
                       {'lab_interpolate':'1'}, {'lab_interpolate':1}, {'lab_interpolate':None}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                snapshot(self.case(), 0, **kwargs)

    def test_http_case_detail_filter_and_invalid_offset(self):
        import json
        import tempfile
        import threading
        from pathlib import Path
        from http.server import ThreadingHTTPServer
        from urllib.error import HTTPError
        from urllib.request import urlopen
        from unittest.mock import patch
        import kmimic_board
        with tempfile.TemporaryDirectory() as directory:
            pool = Path(directory) / 'pool.json'
            pool.write_text('[]')
            with patch.object(kmimic_board, 'case_payload', return_value={'count':1, 'cases':[self.large_case()]}), \
                 patch.object(kmimic_board, 'Discussions'), \
                 patch.object(kmimic_board, 'ThreadingHTTPServer') as stub:
                kmimic_board.serve(pool, 0)
                handler = stub.call_args.args[1]
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}/api/case-detail?case_id=CASE-001&row_index=0'
            try:
                with urlopen(base + '&lab_item=HB&lab_query=hemoglobin&lab_offset=240') as response:
                    s = json.load(response)
                self.assertEqual(len(s['labs']), 5)
                self.assertEqual(s['lab_offset'], 240)
                self.assertNotIn('lab_interpolation', s)
                with urlopen(base + '&lab_item=HB&lab_interpolate=1') as response:
                    s = json.load(response)
                self.assertTrue(s['lab_interpolation']['exclude_from_ai'])
                with urlopen(base + '&lab_interpolate=0') as response:
                    self.assertNotIn('lab_interpolation', json.load(response))
                for flag in ('2', '', 'true', '-1'):
                    with self.subTest(flag=flag), self.assertRaises(HTTPError) as error:
                        urlopen(base + '&lab_interpolate=' + flag)
                    self.assertEqual(error.exception.code, 400)
                for offset in ('-1', '1.5', '', 'nan'):
                    with self.subTest(offset=offset), self.assertRaises(HTTPError) as error:
                        urlopen(base + '&lab_offset=' + offset)
                    self.assertEqual(error.exception.code, 400)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def interpolation_case(self):
        c = self.case()
        c['rows'] = [{'minute':60}]
        c['_clinical']['labs'] = [
            {'itemid':'HB', 'name':'Hemoglobin', 'value':'10.0', 'unit':'g/dL',
             'chart_minute':0, 'available_minute':1},
            {'itemid':'HB', 'name':'Hemoglobin', 'value':'12.5', 'unit':'g/dL',
             'chart_minute':120, 'available_minute':121, 'SUBJECT_ID':'PRIVATE'},
            {'itemid':'FUTURE-ONLY', 'name':'Future test', 'value':'77', 'unit':'mEq/L',
             'chart_minute':100, 'available_minute':101},
        ]
        return c

    def test_interpolation_future_is_confined_to_explicit_display_channel(self):
        c = self.interpolation_case()
        original = deepcopy(c)
        actual = snapshot(c, 0, lab_item='HB')
        facts = model_facts(c, 0)
        self.assertNotIn('lab_interpolation', actual)
        self.assertEqual([r['value'] for r in actual['labs']], ['10.0'])
        self.assertEqual(actual['lab_items'], [{'itemid':'HB', 'name':'Hemoglobin', 'count':1}])
        self.assertNotIn('12.5', str(facts))
        s = snapshot(c, 0, lab_item='HB', lab_interpolate=True)
        self.assertEqual({k:v for k,v in s.items() if k != 'lab_interpolation'}, actual)
        estimate = s['lab_interpolation']
        self.assertEqual(estimate['status'], 'estimated')
        self.assertEqual(estimate['value'], 11.25)
        self.assertEqual(estimate['method'], 'linear')
        self.assertTrue(estimate['historical_only'])
        self.assertTrue(estimate['exclude_from_ai'])
        self.assertTrue(estimate['uses_future_observation'])
        self.assertEqual(estimate['after'], {'chart_minute':120, 'available_minute':121, 'value':'12.5', 'unit':'g/dL'})
        self.assertNotIn('PRIVATE', str(s))
        self.assertEqual(c, original)
        self.assertEqual(model_facts(c, 0), facts)

    def test_interpolation_requires_exact_selected_item_and_brackets(self):
        c = self.interpolation_case()
        self.assertEqual(snapshot(c, 0, lab_interpolate=True)['lab_interpolation']['reason'], 'select_item')
        for item in ('HB,OTHER', 'FUTURE-ONLY', 'UNKNOWN'):
            estimate = snapshot(c, 0, lab_item=item, lab_interpolate=True)['lab_interpolation']
            self.assertEqual(estimate['status'], 'unavailable')
            self.assertNotIn('value', estimate)
        c['rows'][0]['minute'] = 130
        self.assertEqual(snapshot(c, 0, lab_item='HB', lab_interpolate=True)['lab_interpolation']['reason'], 'no_bracketing_observations')

    def test_interpolation_gap_limit_and_no_extrapolation(self):
        c = self.interpolation_case()
        future = c['_clinical']['labs'][1]
        future.update(chart_minute=360, available_minute=361)
        estimate = snapshot(c, 0, lab_item='HB', lab_interpolate=True)['lab_interpolation']
        self.assertEqual(estimate['status'], 'estimated')
        self.assertEqual(estimate['max_gap_minutes'], 360)
        future.update(chart_minute=361, available_minute=362)
        estimate = snapshot(c, 0, lab_item='HB', lab_interpolate=True)['lab_interpolation']
        self.assertEqual(estimate['reason'], 'gap_exceeds_limit')
        self.assertNotIn('value', estimate)
        c['rows'][0]['minute'] = -1
        self.assertEqual(snapshot(c, 0, lab_item='HB', lab_interpolate=True)['lab_interpolation']['reason'], 'no_bracketing_observations')

    def test_interpolation_observed_value_keeps_source_time(self):
        c = self.interpolation_case()
        c['rows'][0]['minute'] = 120
        s = snapshot(c, 0, lab_item='HB', lab_interpolate=True)
        self.assertEqual([r['value'] for r in s['labs']], ['10.0'])
        observed = s['lab_interpolation']
        self.assertEqual(observed['status'], 'unavailable')
        self.assertEqual(observed['reason'], 'result_not_available')
        self.assertNotIn('value', observed)
        self.assertNotIn('after', observed)
        c['_clinical']['labs'][1]['available_minute'] = 120
        observed = snapshot(c, 0, lab_item='HB', lab_interpolate=True)['lab_interpolation']
        self.assertEqual(observed['status'], 'observed')
        self.assertEqual(observed['value'], 12.5)
        self.assertEqual(observed['before'], observed['after'])
        self.assertFalse(observed['uses_future_observation'])

    def test_interpolation_rejects_units_conflicts_and_invalid_times(self):
        for changes, reason in (({'unit':'mg/dL'}, 'unit_mismatch'),
                                ({'unit':''}, 'missing_unit'),
                                ({'unit':None}, 'missing_unit'),
                                ({'available_minute':119}, 'no_bracketing_observations'),
                                ({'available_minute':None}, 'no_bracketing_observations'),
                                ({'same_time_conflict':True}, 'conflicting_observations')):
            with self.subTest(changes=changes):
                c = self.interpolation_case()
                c['_clinical']['labs'][1].update(changes)
                estimate = snapshot(c, 0, lab_item='HB', lab_interpolate=True)['lab_interpolation']
                self.assertEqual(estimate['reason'], reason)
                self.assertNotIn('value', estimate)
        for changes in ({'value':'13'}, {'unit':'mg/dL'}):
            c = self.interpolation_case()
            c['_clinical']['labs'].append({**c['_clinical']['labs'][1], **changes})
            self.assertEqual(snapshot(c, 0, lab_item='HB', lab_interpolate=True)['lab_interpolation']['reason'], 'conflicting_observations')

    def test_interpolation_rejects_categorical_nonfinite_and_non_numeric_values(self):
        for changes, reason in (({'reference_low':'Negative'}, 'qualitative_result'),
                                ({'reference_high':'Nonreactive'}, 'qualitative_result'),
                                ({'reference_low':'POSITIVE'}, 'qualitative_result'),
                                ({'value':'positive'}, 'qualitative_result'),
                                ({'value':'<2'}, 'non_numeric_result'),
                                ({'value':'NaN'}, 'non_numeric_result'),
                                ({'value':'Infinity'}, 'non_numeric_result'),
                                ({'value':True}, 'non_numeric_result')):
            with self.subTest(changes=changes):
                c = self.interpolation_case()
                c['_clinical']['labs'][1].update(changes)
                estimate = snapshot(c, 0, lab_item='HB', lab_interpolate=True)['lab_interpolation']
                self.assertEqual(estimate['reason'], reason)
                self.assertNotIn('value', estimate)

    def test_interpolation_does_not_skip_a_nearer_invalid_sample(self):
        c = self.interpolation_case()
        c['_clinical']['labs'].append({'itemid':'HB', 'name':'Hemoglobin', 'value':'<2', 'unit':'g/dL', 'chart_minute':90, 'available_minute':91})
        self.assertEqual(snapshot(c, 0, lab_item='HB', lab_interpolate=True)['lab_interpolation']['reason'], 'non_numeric_result')

    def test_interpolation_rejects_unit_bearing_ordinal_and_unreviewed_names(self):
        for name in ('Glasgow Coma Scale', 'SOFA score', 'Urine blood grade', 'Unknown test', '', None):
            with self.subTest(name=name):
                c = self.interpolation_case()
                for r in c['_clinical']['labs'][:2]:
                    r.update(name=name, unit='score')
                estimate = snapshot(c, 0, lab_item='HB', lab_interpolate=True)['lab_interpolation']
                self.assertEqual(estimate['reason'], 'unreviewed_quantitative_item')
                self.assertNotIn('value', estimate)

    def test_interpolation_reviewed_name_variants_require_name_not_code(self):
        for name in ('  HAEMOGLOBIN  ', 'White   blood cell count', 'WBC', 'BUN', 'Creatinine'):
            with self.subTest(name=name):
                c = self.interpolation_case()
                for r in c['_clinical']['labs'][:2]:
                    r['name'] = name
                self.assertEqual(snapshot(c, 0, lab_item='HB', lab_interpolate=True)['lab_interpolation']['status'], 'estimated')
        c = self.interpolation_case()
        for r in c['_clinical']['labs'][:2]:
            r.update(itemid='Hemoglobin', name='Unknown test')
        self.assertEqual(snapshot(c, 0, lab_item='Hemoglobin', lab_interpolate=True)['lab_interpolation']['reason'], 'unreviewed_quantitative_item')

    def test_interpolation_accepts_only_audited_korean_annotated_names(self):
        accepted = ('Glucose(정량)(현장검사)',
                    'Hb(Hemoglobin)[Spectrophotometry]:응급검사실',
                    'Hb(Hemoblobin)[Spectrophotometry] : 응급검사실',
                    'Hct(Hematocrit):응급검사실', 'RBC Count:응급검사실',
                    'WBC Count : 응급검사실', 'Platelet Count:응급검사실',
                    '[처방불가]Glucose (em)', '[처방불가]Creatinine (serum, em)',
                    '[처방불가]Potassium (serum, em)', '[처방불가]Hb (em)',
                    'Hb(검사24시간가능)', 'Glucose(검사24시간가능)')
        rejected = ('Glucose(정성)(현장검사)', 'Hb(Hemoglobin)[Other]:응급검사실',
                    'WBC Count:기타검사실', 'Platelet Count:응급검사실:등급',
                    'Glasgow Coma Scale:응급검사실', 'SOFA score:응급검사실',
                    'Hb(Hemoglobin)[Spectrophotometry]:응급검사실 positive',
                    '[처방불가]Glucose (urine, em)', '[처방불가]Creatinine (urine, em)',
                    '[처방불가]Potassium (serum, em):grade', '[처방불가]Unknown (em)',
                    'Glucose(검사24시간가능)(정성)')
        for name in accepted + rejected:
            with self.subTest(name=name):
                c = self.interpolation_case()
                for r in c['_clinical']['labs'][:2]:
                    r['name'] = name
                estimate = snapshot(c, 0, lab_item='HB', lab_interpolate=True)['lab_interpolation']
                self.assertEqual(estimate['status'], 'estimated' if name in accepted else 'unavailable')
                if name in rejected:
                    self.assertEqual(estimate['reason'], 'unreviewed_quantitative_item')
                    self.assertNotIn('value', estimate)

if __name__=='__main__':unittest.main()
