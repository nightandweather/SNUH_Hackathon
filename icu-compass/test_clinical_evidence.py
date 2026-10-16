import unittest

import clinical_evidence as ce
from test_shifts import hospital, admit


class EvidenceTests(unittest.TestCase):
    def source_case(self):
        return {'rows':[{'minute':60, 'vitals':{'rr':22, 'sbp':100}, 'age':{'rr':0,'sbp':5}},
                        {'minute':120, 'vitals':{'rr':80, 'sbp':40, 'gcs':3}, 'age':{'rr':0,'sbp':0,'gcs':0}}],
                'historical_vital_observations':[{'variable':'gcs','chart_minute':60,'value':3}],
                'interpolated_vitals':{'gcs':3}}

    def test_source_reference_uses_only_selected_row_and_never_fills_gcs(self):
        result=ce.source_assessment(self.source_case(),0)
        self.assertEqual(result['calculator']['score'],None)
        self.assertEqual(result['calculator']['range'],[2,3])
        self.assertEqual(result['supporting_vital_keys'],['rr','sbp'])
        self.assertIsNone(result['inputs']['gcs']['value'])
        self.assertEqual(result['inputs']['sbp']['observed_minute'],55)
        self.assertFalse(result['clinical_decision'])
        self.assertFalse(result['calculator']['eligible'])
        self.assertIn('RR >= 22',result['calculator']['formula'])
        self.assertEqual(result['calculator']['source_url'],ce.QSOFA_URL)
        self.assertEqual(result['calculator']['method_url'],ce.AGENTMD_URL)

    def test_source_reference_rejects_stale_future_conflict_and_explicit_unknown(self):
        changes=({'age':{'rr':31,'sbp':31}}, {'age':{'rr':-1,'sbp':-1}},
                 {'same_time_conflict':{'rr':True,'sbp':True}},
                 {'status':{'rr':'unknown','sbp':'unknown'}},
                 {'vitals':{'rr':True,'sbp':'100'}}, {'vitals':{'rr':101,'sbp':0}})
        for change in changes:
            with self.subTest(change=change):
                c=self.source_case();c['rows'][0].update(change)
                result=ce.source_assessment(c,0)
                self.assertIsNone(result['calculator']['score'])
                self.assertEqual(result['calculator']['range'],[0,3])
                self.assertEqual(result['supporting_vital_keys'],[])

    def test_source_reference_accepts_thirty_minute_boundary_without_icu_eligibility(self):
        c=self.source_case();c['rows'][0].update(vitals={'rr':22,'sbp':100,'gcs':14},age={'rr':30,'sbp':30,'gcs':30})
        result=ce.source_assessment(c,0)
        self.assertEqual(result['calculator']['score'],3)
        self.assertFalse(result['calculator']['eligible'])
        self.assertFalse(result['clinical_decision'])

    def test_source_reference_index_and_time_validation(self):
        for index in (-1,2,True,'0'):
            with self.assertRaises(ValueError):ce.source_assessment(self.source_case(),index)
        c=self.source_case();c['rows'][0]['minute']=float('nan')
        with self.assertRaises(ValueError):ce.source_assessment(c,0)

    def test_qsofa_boundaries_and_no_icu_classification(self):
        for rr, sbp, gcs, expected in [(21, 101, 15, 0), (22, 100, 14, 3), (22, 101, 15, 1)]:
            result = ce.qsofa(dict(rr=rr, sbp=sbp, gcs=gcs), age=60, suspected_infection=True)
            self.assertEqual(result['score'], expected)
            self.assertFalse(result['eligible'])
            self.assertIn('No emergency classification', result['interpretation'])

    def test_missing_and_invalid_values_never_become_normal(self):
        for invalid in (None, 'unknown', float('nan'), float('inf'), True, -1):
            result = ce.qsofa(dict(rr=22, sbp=invalid))
            self.assertIsNone(result['score'])
            self.assertEqual(result['range'], [1, 3])
        self.assertIsNone(ce.qsofa(dict(rr=22, sbp=90, gcs=14.5))['score'])

    def test_map_is_not_used_as_systolic_bp(self):
        result = ce.qsofa(dict(rr=20, map=70, gcs=15))
        self.assertEqual(result['missing'], ['Systolic BP'])
        self.assertIsNone(result['score'])

    def test_alert_snapshot_and_simulation_provenance(self):
        h = hospital(); bed = admit(h)
        event = h.trigger_emergency(bed['id'], 'hypotension')
        evidence = event['evidence']
        self.assertEqual(evidence['source'], 'Injected simulation')
        self.assertTrue(any(e['key']=='map' and e['value']==45 for e in evidence['evidence']))
        self.assertIsNone(evidence['calculator']['score'])
        bed['patient']['vitals']['map'] = 90
        self.assertTrue(any(e['value']==45 for e in h._incident_json(h.incidents[-1])['evidence']['evidence']))

    def test_bounded_kmimic_missing_value_does_not_fill_again(self):
        h = hospital()
        source = {'series': {'hr': [80, None, None]}, 'bounded_carry_forward': True}
        self.assertIsNone(h._vital(source, 'hr', 1))
        self.assertIsNone(h._vital(source, 'hr', 4))


if __name__ == '__main__':
    unittest.main()
