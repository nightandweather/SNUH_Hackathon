import copy
import unittest
import repair_gs_device_evidence as r


class DeviceRecoveryTests(unittest.TestCase):
    def setup_source(self,**fields):
        selected={'hospital':'001','SUBJECT_ID':'1','HADM_ID':'10','STAY_ID':'100',
                  'icu_in':'2020-01-01T00:00:00','icu_out':'2020-01-01T01:01:00'}
        patient={'pid':'GS-CASE-001','los_min':61}
        row={'SUBJECT_ID':'1','HADM_ID':'10','STAY_ID':'100','ITEMID':'001C_1207_22360',
             'CHARTTIME':'2020-01-01T00:05:00','STORETIME':'','VALUE':'ON','CHARTEVENT_ID':'1',**fields}
        entry={'case_alias':'GS-CASE-001','hospital':'001','table':'CHARTEVENTS','row':row,'dictionary':{}}
        return entry,selected,patient

    def test_unknown_availability_is_only_historical(self):
        scope,evidence=r.extract(*self.setup_source())
        self.assertEqual(scope,'historical_only');self.assertTrue(evidence['historical_only'])
        self.assertEqual(evidence['availability_status'],'unknown')
        self.assertNotIn('available_minute',evidence)
        self.assertEqual(evidence['device_type'],'ventilator')

    def test_valid_store_eligible_but_late_store_never_resurrects_after_exit(self):
        scope,evidence=r.extract(*self.setup_source(STORETIME='2020-01-01T00:10:00'))
        self.assertEqual(scope,'current_eligible');self.assertEqual(evidence['chart_minute'],5)
        self.assertEqual(evidence['available_minute'],10)
        self.assertIsNone(r.extract(*self.setup_source(STORETIME='2020-01-01T01:01:00')))

    def test_invalid_store_retained_as_unknown_not_current(self):
        scope,evidence=r.extract(*self.setup_source(STORETIME='2020-01-01T00:01:00'))
        self.assertEqual(scope,'historical_only');self.assertEqual(evidence['availability_reason'],'store_before_chart')

    def test_cross_patient_exit_and_unmapped_or_coded_values_excluded(self):
        for values in ({'STAY_ID':'101'},{'HADM_ID':'11'},{'SUBJECT_ID':'2'},
                       {'CHARTTIME':'2020-01-01T01:01:00'},{'VALUE':'1'},{'VALUE':'ordered'},
                       {'ITEMID':'UNMAPPED'}):
            self.assertIsNone(r.extract(*self.setup_source(**values)))

    def test_ecmo_flow_zero_is_not_absence_and_other_hospital_not_mapped(self):
        self.assertIsNone(r.extract(*self.setup_source(ITEMID='001C_1093_22025',VALUE='0')))
        scope,evidence=r.extract(*self.setup_source(ITEMID='001C_1093_22025',VALUE='4',VALUEUOM='L/min'))
        self.assertEqual(evidence['device_type'],'ecmo');self.assertTrue(evidence['active'])
        entry,selected,patient=self.setup_source();entry['hospital']=selected['hospital']='003'
        self.assertIsNone(r.extract(entry,selected,patient))

    def test_history_conflicts_marked_and_recovery_idempotent(self):
        _,on=r.extract(*self.setup_source());_,off=r.extract(*self.setup_source(VALUE='OFF'))
        merged=r.merge_records([],[on,off]);self.assertTrue(all(e['same_time_conflict'] for e in merged))
        self.assertEqual(r.merge_records(merged,[on,off]),merged)

    def test_documented_use_with_known_store_is_historical_not_active_flag(self):
        entry,selected,patient=self.setup_source(ITEMID='001D_1404_10900',VALUE='Foley catheter 통해 소변 배출되고 있음',STORETIME='2020-01-01T00:10:00')
        entry['table']='DATETIMEEVENTS';entry['dictionary']={'LABEL':'Foley catheter 통해 소변 배출되고 있음 > bflow'}
        scope,evidence=r.extract(entry,selected,patient)
        self.assertEqual(scope,'historical_only');self.assertTrue(evidence['historical_only'])
        self.assertEqual(evidence['availability_status'],'known')
        self.assertEqual(evidence['event_minute'],5);self.assertEqual(evidence['available_minute'],10)
        self.assertEqual(evidence['time_basis'],'documented_chart_time')
        self.assertEqual(evidence['device_type'],'urinary_catheter')
        self.assertEqual(evidence['evidence_kind'],'documented_device_use')
        self.assertNotIn('raw',evidence)

    def test_documented_use_requires_matching_positive_label_and_recorded_phrase(self):
        entry,selected,patient=self.setup_source(ITEMID='001D_1404_10900',VALUE='Foley catheter 통해 소변 배출되고 있음')
        entry['table']='DATETIMEEVENTS';entry['dictionary']={'LABEL':'Foley catheter 통해 소변 배출되고 있음 > bflow'}
        self.assertIsNotNone(r.extract(entry,selected,patient))
        wrong=copy.deepcopy(entry);wrong['dictionary']['LABEL']='Foley catheter 준비 중임'
        self.assertIsNone(r.extract(wrong,selected,patient))
        for value in ('ON','1','2020-01-01T00:06:00','Foley catheter 준비 중임','Foley catheter 유지하지 않음'):
            wrong=copy.deepcopy(entry);wrong['row']['VALUE']=value
            self.assertIsNone(r.extract(wrong,selected,patient))

    def test_documented_ventilator_phrase_whitespace_is_not_a_new_mapping(self):
        entry,selected,patient=self.setup_source(ITEMID='003D_7323_10523_01',VALUE='ventilator 적용 중 임')
        selected['hospital']=entry['hospital']='003';entry['table']='DATETIMEEVENTS'
        entry['dictionary']={'LABEL':'ventilator 적용 중임 > ventilator'}
        _,evidence=r.extract(entry,selected,patient)
        self.assertEqual(evidence['device_type'],'ventilator')

    def test_reviewed_device_removal_is_false_at_observation_only(self):
        entry,selected,patient=self.setup_source(ITEMID='006D_7046',VALUE='arterial line 제거함',STORETIME='2020-01-01T00:10:00')
        selected['hospital']=entry['hospital']='006';entry['table']='DATETIMEEVENTS'
        entry['dictionary']={'LABEL':'arterial line 제거함'}
        scope,evidence=r.extract(entry,selected,patient)
        self.assertEqual(scope,'historical_only');self.assertFalse(evidence['active'])
        self.assertEqual(evidence['evidence_kind'],'documented_device_removal')
        self.assertEqual(evidence['device_type'],'arterial_line')
        self.assertEqual(evidence['chart_minute'],5);self.assertEqual(evidence['available_minute'],10)
        wrong=copy.deepcopy(entry);wrong['row']['VALUE']='arterial line 제거 예정'
        self.assertIsNone(r.extract(wrong,selected,patient))

    def test_extubation_is_only_tube_removal_and_circuit_care_is_not_removal(self):
        entry,selected,patient=self.setup_source(ITEMID='001D_7412_12340',VALUE='기관내관 발관함')
        entry['table']='DATETIMEEVENTS';entry['dictionary']={'LABEL':'기관내관 발관함 > 제거함'}
        scope,evidence=r.extract(entry,selected,patient)
        self.assertEqual(scope,'historical_only');self.assertEqual(evidence['device_type'],'endotracheal_tube')
        self.assertFalse(evidence['active']);self.assertEqual(evidence['availability_status'],'unknown')
        self.assertNotIn('ventilator',evidence.values())
        for hospital,itemid in [('001','001D_8201_10225'),('003','003D_1000004911_10794_01')]:
            care=copy.deepcopy(entry);case=copy.deepcopy(selected)
            care['hospital']=case['hospital']=hospital;care['row']['ITEMID']=itemid
            care['row']['VALUE']='ventilator circuit 의 물 제거함'
            care['dictionary']['LABEL']='ventilator circuit 의 물 제거함 > 제거함'
            self.assertIsNone(r.extract(care,case,patient))


if __name__=='__main__':unittest.main()
