import unittest
import json
from copy import deepcopy
from kmimic_board import case_payload
class BoardSafetyTests(unittest.TestCase):
 def fixture(self):
  return {'pid':'test','source':'K-MIMIC','careunit':'SICU','bounded_carry_forward':True,'step':5,'series':{'hr':[80,90,100]},'measurement_age_min':{'hr':[0,31,-1]},'vent':False,'pressor':False,'procedure_table_available':True,'procedures':[{'start_min':0,'end_min':10,'itemid':'test'},{'start_min':20,'end_min':10},{'start_min':0,'end_min':float('nan')}]}
 def test_missing_and_stale_are_unknown(self):
  c=case_payload([self.fixture()])['cases'][0]
  self.assertEqual([r['vitals']['hr'] for r in c['rows']],[80,None,None]);self.assertEqual(c['devices'],{});self.assertEqual(c['anatomy_findings'],[])
 def test_source_and_alias_validation(self):
  p=self.fixture()
  with self.assertRaises(ValueError):case_payload([p,p])
  p['source']='synthetic'
  with self.assertRaises(ValueError):case_payload([p])
 def test_only_valid_procedures_no_early_completion(self):
  c=case_payload([self.fixture()])['cases'][0];self.assertEqual(len(c['procedures']),1)
  self.assertEqual(sum(e['end_min']<=5 for e in c['procedures']),0)
  self.assertEqual(sum(e['end_min']<=10 for e in c['procedures']),1)
 def test_explicit_on_off_only(self):
  p=self.fixture();p['device_events']={'ventilator':[{'minute':1,'active':True,'raw':'ON','itemid':'test'},{'minute':2,'active':True,'raw':'OFF','itemid':'test'}]}
  c=case_payload([p])['cases'][0];self.assertEqual(len(c['device_events']['ventilator']),1)
 def gs_fixture(self):
  p=self.fixture();p['gs_selection']={'service_code':'GS','criterion':'gs_at_icu_entry','strict_cohort_stays':14321,'service_evidence':{'table':'SERVICES','code':'GS','minute':-30,'SUBJECT_ID':'PRIVATE'},'matched_scenarios':['icu_death'],'scenario_events':[{'kind':'death_during_icu','minute':10,'table':'ADMISSIONS','evidence_status':'confirmed','HADM_ID':'PRIVATE'}],'source_identity':{'SUBJECT_ID':'PRIVATE'}};return p
 def test_gs_only_pool_and_exact_service(self):
  p=self.gs_fixture();result=case_payload([p]);self.assertEqual(result['gs_cohort']['strict_cohort_stays'],14321)
  self.assertNotIn('PRIVATE',json.dumps(result));self.assertEqual(result['cases'][0]['gs_selection']['scenario_events'][0]['kind'],'death_during_icu')
  other=self.fixture();other['pid']='other'
  with self.assertRaises(ValueError):case_payload([p,other])
  p['gs_selection']['service_code']='GSL'
  with self.assertRaises(ValueError):case_payload([p])
 def test_scenario_future_is_not_model_evidence(self):
  from grounded_chat import context_for
  c=case_payload([self.gs_fixture()])['cases'][0]
  self.assertNotIn('death_during_icu',json.dumps(context_for(c,0)))
 def test_device_availability_validation(self):
  p=self.fixture();valid={'minute':10,'chart_minute':5,'available_minute':10,'active':True,'subtype':'ecmo','value':2.5,'unit':'L/min','itemid':'test','table':'CHARTEVENTS','evidence_kind':'positive_ecmo_flow'}
  p['device_events']={'ecmo_crrt':[valid,{**valid,'available_minute':None},{**valid,'chart_minute':20},{**valid,'value':0},{**valid,'SUBJECT_ID':'PRIVATE'}],'cpr':[{'minute':10,'chart_minute':5,'available_minute':10,'event_minute':20,'active':True,'itemid':'test','table':'DATETIMEEVENTS','evidence_kind':'cpr_start_record'}]}
  c=case_payload([p])['cases'][0];self.assertEqual(len(c['device_events']['ecmo_crrt']),2);self.assertEqual(c['device_events']['cpr'],[]);self.assertNotIn('PRIVATE',json.dumps(c))
 def test_historical_vitals_remain_out_of_current_state_and_ai(self):
  from grounded_chat import context_for
  p=self.gs_fixture();p['los_min']=60
  e={'chart_minute':5,'variable':'hr','value':177,'unit':'bpm','table':'CHARTEVENTS','historical_only':True,'availability_status':'unknown','availability_reason':'missing_storetime','SUBJECT_ID':'PRIVATE'}
  p['historical_vital_observations']=[e,{**e,'chart_minute':-1},{**e,'chart_minute':61},{**e,'value':float('nan')},{**e,'unit':'wrong'},{**e,'historical_only':False}]
  c=case_payload([p])['cases'][0]
  self.assertEqual(len(c['historical_vital_observations']),1)
  self.assertEqual(c['rows'][1]['vitals']['hr'],None)
  self.assertNotIn('177',json.dumps(context_for(c,1)))
  self.assertNotIn('PRIVATE',json.dumps(c))
 def test_historical_devices_are_separate_time_bounded_and_sanitized(self):
  from grounded_chat import context_for
  p=self.gs_fixture();p['los_min']=60
  e={'chart_minute':5,'device_type':'urinary_catheter','active':True,'table':'CHARTEVENTS','historical_only':True,'availability_status':'unknown','availability_reason':'store_before_chart','evidence_kind':'explicit_device_state','itemid':'reviewed-code','name':'PRIVATE','SUBJECT_ID':'PRIVATE'}
  p['historical_device_observations']=[e,{**e,'chart_minute':-1},{**e,'chart_minute':60},{**e,'same_time_conflict':True},{**e,'device_type':'guessed_device'},{**e,'historical_only':False},{**e,'availability_status':'known'},{**e,'active':'true'}]
  c=case_payload([p])['cases'][0]
  self.assertEqual(len(c['historical_device_observations']),1)
  self.assertEqual(c['historical_device_observations'][0]['name_ko'],'도뇨관')
  self.assertEqual(c['devices'],{})
  self.assertNotIn('urinary_catheter',json.dumps(context_for(c,1)))
  self.assertNotIn('PRIVATE',json.dumps(c))
 def test_historical_flow_requires_positive_ecmo_measurement(self):
  p=self.fixture();p['los_min']=60
  e={'chart_minute':5,'device_type':'ecmo','active':True,'value':2.5,'table':'CHARTEVENTS','historical_only':True,'availability_status':'unknown','availability_reason':'missing_storetime','evidence_kind':'positive_ecmo_flow'}
  p['historical_device_observations']=[e,{**e,'value':0},{**e,'device_type':'crrt'},{**e,'active':False}]
  self.assertEqual(len(case_payload([p])['cases'][0]['historical_device_observations']),1)
 def test_documented_device_use_is_historical_even_with_valid_availability(self):
  from grounded_chat import context_for
  p=self.fixture();p['los_min']=60
  e={'chart_minute':5,'event_minute':4,'available_minute':6,'device_type':'central_line','active':True,'table':'DATETIMEEVENTS','historical_only':True,'availability_status':'known','evidence_kind':'documented_device_use'}
  p['historical_device_observations']=[e,{**e,'event_minute':7},{**e,'available_minute':3},{**e,'available_minute':60},{**e,'event_minute':-1},{**e,'table':'CHARTEVENTS'}]
  c=case_payload([p])['cases'][0]
  self.assertEqual(len(c['historical_device_observations']),1)
  self.assertEqual(c['historical_device_observations'][0]['available_minute'],6)
  self.assertEqual(c['device_events']['accessories'],[])
  self.assertNotIn('central_line',json.dumps(context_for(c,1)))
 def test_documented_device_removal_is_not_a_ventilator_stop_or_ai_fact(self):
  from grounded_chat import context_for
  p=self.fixture();p['los_min']=60
  e={'chart_minute':5,'event_minute':5,'device_type':'endotracheal_tube','active':False,'table':'DATETIMEEVENTS','historical_only':True,'availability_status':'unknown','availability_reason':'store_before_chart','evidence_kind':'documented_device_removal'}
  p['historical_device_observations']=[e,{**e,'active':True},{**e,'event_minute':6},{**e,'chart_minute':60},{**e,'table':'CHARTEVENTS'}]
  c=case_payload([p])['cases'][0]
  self.assertEqual(len(c['historical_device_observations']),1)
  self.assertFalse(c['historical_device_observations'][0]['active'])
  self.assertEqual(c['historical_device_observations'][0]['device_type'],'endotracheal_tube')
  self.assertEqual(c['device_events']['ventilator'],[])
  self.assertNotIn('endotracheal_tube',json.dumps(context_for(c,1)))
if __name__=='__main__':unittest.main()
