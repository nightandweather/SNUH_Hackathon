import unittest
import audit_cached_device_transitions as audit


class CachedTransitionAuditTests(unittest.TestCase):
    def test_values_never_echo_unreviewed_free_text(self):
        self.assertEqual(audit.value_class('unreviewed patient narrative', 'ventilator 적용 중임'), 'undisclosed_text')
        self.assertEqual(audit.value_class('ventilator 적용 중 임', 'ventilator 적용 중임 > ventilator'), 'exact_dictionary_phrase')
        self.assertEqual(audit.value_class('OFF', 'Ventilator'), 'explicit_state:off')
        self.assertEqual(audit.value_class('0', 'Ventilator'), 'numeric')

    def test_candidate_classification_does_not_map_orders_to_use(self):
        self.assertEqual(audit.phrase_class('기관내관 제거함'), 'removal_or_stop_candidate')
        self.assertEqual(audit.phrase_class('기관내관 제거 예정'), 'order_or_plan_candidate')
        self.assertEqual(audit.phrase_class('Foley catheter 유지 중임'), 'insertion_or_use_candidate')

    def test_half_open_icu_time_and_patient_boundaries(self):
        selected = {'hospital': '001', 'SUBJECT_ID': '1', 'HADM_ID': '10', 'STAY_ID': '100',
                    'icu_in': '2020-01-01T00:00:00', 'icu_out': '2020-01-01T01:01:00'}
        patient = {'los_min': 60}
        entry = {'hospital': '001', 'row': {'SUBJECT_ID': '1', 'HADM_ID': '10', 'STAY_ID': '100',
                  'CHARTTIME': '2020-01-01T01:00:00', 'STORETIME': ''}}
        self.assertEqual(audit.accepted_time(entry, selected, patient), (60, None, 61))
        entry['row']['CHARTTIME'] = '2020-01-01T01:01:00'
        self.assertIsNone(audit.accepted_time(entry, selected, {'los_min': 65}))
        entry['row']['CHARTTIME'] = '2020-01-01T00:05:00'
        entry['row']['STAY_ID'] = '101'
        self.assertIsNone(audit.accepted_time(entry, selected, patient))


if __name__ == '__main__':
    unittest.main()
