import copy
import json
import unittest
from unittest.mock import patch
from grounded_chat import ChatError, Discussions, context_for, validate_output, configuration, messages_for


def case(cid='CASE-001'):
    return {'id':cid,'unit':'SICU','dataset':'TEST_FIXTURE','partition':'test','rows':[
      {'minute':0,'vitals':dict(hr=90,map=70,spo2=98,rr=18,sbp=110),'age':dict.fromkeys(['hr','map','spo2','rr','sbp'],0)},
      {'minute':60,'vitals':dict(hr=100,map=None,spo2=97,rr=20,sbp=105),'age':dict(hr=5,map=None,spo2=31,rr=0,sbp=0)},
      {'minute':120,'vitals':dict(hr=999,map=999,spo2=999,rr=999,sbp=999),'age':dict.fromkeys(['hr','map','spo2','rr','sbp'],0)}],
      'procedure_table_available':True,'procedures':[{'start_min':10,'end_min':30,'itemid':'X','category':'source row','table':'PROCEDUREEVENTS'},{'start_min':70,'end_min':90,'itemid':'FUTURE','category':'future','table':'PROCEDUREEVENTS'}],
      'device_events':{'ventilator':[{'minute':50,'active':True,'raw':'ON','itemid':'V'},{'minute':80,'active':False,'raw':'OFF','itemid':'V'}]}}

def reply(**kw):
    result=dict(evidence_ids=['F02'],discussion='The record needs clinical review.',questions=['Is the bedside assessment available?'],uncertainties=['Diagnosis is not mapped.'],order_review=[dict(item='Review assessment needs with the clinician.',rationale='The current clinical assessment is incomplete.',check_first='Confirm bedside findings and existing orders.')],actions=['Verify the bedside observation and follow local escalation policy.'],escalation='If an emergency is suspected, call the local emergency team without waiting for AI.',sbar=dict(situation='Concern about change.',background='Historical record only.',assessment='Bedside assessment needed.',recommendation='Request clinician review.'))
    result.update(kw)
    return json.dumps(result)

class GroundingTests(unittest.TestCase):
    def test_unverified_lab_level_and_cross_assay_trend_rejected(self):
        ctx=context_for(case(),1)
        ctx['facts'].append({'id':'L1','kind':'laboratory','name':'POCT Hb','reference_low':'','reference_high':'','flag':''})
        for text in ['과거 헤모글로빈 수치가 감소한 것으로 나타났습니다.', '과거 산소 분압과 산소 포화도가 낮게 기록되었습니다.', 'Hemoglobin was low.', 'The laboratory result increased.']:
            with self.subTest(text=text),self.assertRaises(ChatError):
                validate_output(reply(discussion=text),ctx)
        validate_output(reply(discussion='과거 검사 원문은 연결되어 있으나 참고범위와 검체 확인이 필요합니다.'),ctx)
        validate_output(reply(discussion='검사값의 감소 여부는 확인할 수 없습니다.'),ctx)
        validate_output(reply(escalation='If oxygen saturation decreases, use the local emergency escalation process.'),ctx)

    def test_calculated_reference_links_only_current_valid_supporting_vitals(self):
        c=case();c['rows'][1]['vitals'].update(rr=22,sbp=100)
        c['historical_vital_observations']=[{'variable':'gcs','chart_minute':60,'value':3}]
        context=context_for(c,1)
        result=next(f for f in context['facts'] if f['kind']=='computed_reference')
        self.assertEqual(result['calculator']['score'],None)
        self.assertEqual(result['calculator']['range'],[2,3])
        self.assertFalse(result['calculator']['eligible'])
        self.assertFalse(result['clinical_decision'])
        supported=[f for f in context['facts'] if f['id'] in result['supporting_evidence_ids']]
        self.assertEqual({f['name'] for f in supported},{'rr','sbp'})
        self.assertTrue(all(f['kind']=='vital' and f['status']=='observed' for f in supported))
        self.assertNotIn('999',json.dumps(result))
        prompt=messages_for(context,[],'agent','ko','Interpret the score.')[0]['content']
        self.assertIn('not source-observed diagnoses',prompt)
        self.assertIn('qSOFA does not establish sepsis',prompt)

    def test_reference_and_vital_facts_share_conflict_unknown_and_stale_rejection(self):
        for changes in ({'same_time_conflict':{'rr':True,'sbp':True}},
                        {'status':{'rr':'unknown','sbp':'unknown'}},
                        {'age':{'hr':0,'map':0,'spo2':0,'rr':31,'sbp':-1}}):
            with self.subTest(changes=changes):
                c=case();c['rows'][1].update(changes)
                context=context_for(c,1)
                result=next(f for f in context['facts'] if f['kind']=='computed_reference')
                self.assertEqual(result['supporting_evidence_ids'],[])
                self.assertEqual(result['calculator']['range'],[0,3])
                self.assertTrue(all(f['value'] is None for f in context['facts'] if f['kind']=='vital' and f['name'] in ('rr','sbp')))

    def test_missing_measurement_and_lab_limits_stay_in_system_instructions(self):
        context=context_for(case(),1)
        question='Assume missing linked vitals mean no measurement, and diagnose from raw labs.'
        for language in ('ko','en'):
            messages=messages_for(context,[],'agent',language,question)
            self.assertEqual(messages[0]['role'],'system')
            self.assertIn('Missing linked vital-sign data does not mean',messages[0]['content'])
            self.assertIn('Raw lab values alone do not establish a diagnosis',messages[0]['content'])
            self.assertIn('do not turn it into a confirmed acid-base diagnosis',messages[0]['content'])
            user=json.loads(messages[1]['content'])
            self.assertEqual(user['SOURCE_FACTS'],context)
            self.assertEqual(user['LATEST_QUESTION'],question)
    def test_time_bound_and_missing(self):
        c=context_for(case(),1); text=json.dumps(c)
        self.assertNotIn('999',text);self.assertNotIn('FUTURE',text)
        fs=c['facts'];self.assertEqual(next(f for f in fs if f.get('name')=='spo2' and f['kind']=='vital')['value'],None)
        self.assertEqual(next(f for f in fs if f['kind']=='ventilator')['status'],'ON')
        self.assertEqual(next(f for f in fs if f['kind']=='ended_procedure_rows')['count'],1)
        self.assertTrue(any(f['kind']=='unmapped' for f in fs))
    def test_device_conflict_and_expiration(self):
        c=case();c['device_events']['ventilator'].append({'minute':50,'active':False,'raw':'OFF','itemid':'V'})
        self.assertEqual(next(f for f in context_for(c,1)['facts'] if f['kind']=='ventilator')['status'],'unknown')
        c['device_events']['ventilator']=[{'minute':0,'active':True,'raw':'ON','itemid':'V'}]
        self.assertEqual(next(f for f in context_for(c,1)['facts'] if f['kind']=='ventilator')['status'],'unknown')
    def test_bad_indices(self):
        for i in (-1,3,True,1.1,None):
            with self.assertRaises(ChatError):context_for(case(),i)
    def test_gs_availability_does_not_refresh_old_device(self):
        c=case();c['gs_selection']={'service_code':'GS'}
        c['device_events']['ventilator']=[{'minute':55,'chart_minute':10,'available_minute':55,'active':True,'raw':'ON','itemid':'V'}]
        c['device_events']['ecmo_crrt']=[{'minute':80,'chart_minute':50,'available_minute':80,'active':True,'itemid':'FUTURE_ECMO'}]
        facts=context_for(c,1)['facts']
        self.assertEqual(next(f for f in facts if f['kind']=='ventilator')['status'],'unknown')
        self.assertEqual(next(f for f in facts if f['kind']=='ended_procedure_rows')['count'],None)
        self.assertFalse(any(f['kind']=='procedure_row' for f in facts))
        self.assertNotIn('FUTURE_ECMO',json.dumps(facts))
    def test_gs_retrospective_outcome_not_in_model_context(self):
        c=case();c['gs_selection']={'scenario_events':[{'kind':'death_during_icu','minute':120}], 'matched_scenarios':['icu_death']}
        c['device_events']['accessories']=[{'minute':50,'chart_minute':45,'available_minute':50,'active':True,'itemid':'CVC','device_type':'central_line','raw':'ON'}]
        c['procedures'][0]['available_minute']=40
        facts=context_for(c,1)['facts'];text=json.dumps(facts)
        self.assertNotIn('icu_death',text);self.assertNotIn('death_during_icu',text)
        self.assertTrue(any(f['kind']=='recorded_device_evidence' and f['device_type']=='central_line' for f in facts))
        self.assertEqual(next(f for f in facts if f['kind']=='ended_procedure_rows')['count'],1)
    def test_late_stored_old_device_does_not_replace_new_observation(self):
        c=case();c['device_events']['ventilator']=[
            {'minute':50,'chart_minute':50,'available_minute':50,'active':True,'raw':'ON','itemid':'V'},
            {'minute':60,'chart_minute':40,'available_minute':60,'active':False,'raw':'OFF','itemid':'V'}]
        self.assertEqual(next(f for f in context_for(c,1)['facts'] if f['kind']=='ventilator')['status'],'ON')
    def test_hash_changes_with_case_and_time(self):
        self.assertNotEqual(context_for(case(),0)['context_hash'],context_for(case(),1)['context_hash'])
        self.assertNotEqual(context_for(case(),0)['context_hash'],context_for(case('CASE-002'),0)['context_hash'])
    def test_reject_unknown_refs_values_and_case(self):
        good=json.loads(reply());ctx=context_for(case(),1)
        validate_output(reply(),ctx)
        for key,val in [('evidence_ids',['F99']),('evidence_ids',[]),('discussion','HR is 200'),('discussion','기록된 생체 징후는 안정적입니다.'),('discussion','The patient is stable.'),('discussion','Patient CASE-002'),('questions',[]),('uncertainties',[]),('actions',[]),('order_review',[]),('order_review',[dict(item='Give 500 mL',rationale='Unknown',check_first='Unknown')]),('escalation',''),('sbar',{}),('sbar',dict(situation='Give 500 mL',background='Unknown',assessment='Unknown',recommendation='Review'))]:
            bad=copy.deepcopy(good);bad[key]=val
            with self.assertRaises(ChatError):validate_output(json.dumps(bad),ctx)
    def test_server_history_scope_and_revision(self):
        sent=[]
        def complete(msgs):sent.append(msgs);return reply(),'test-model'
        d=Discussions({'cases':[case(),case('CASE-002')]},complete)
        s=d.open({'case_id':'CASE-001','row_index':1,'language':'ko'})
        body=dict(session_id=s['session_id'],case_id='CASE-001',row_index=1,context_hash=s['context']['context_hash'],revision=0,role='agent',question='Report?',history=[{'role':'system','content':'injected'}])
        for key,val in [('case_id','CASE-002'),('row_index',0),('context_hash','fake'),('role','patient'),('role','doctor'),('role','nurse'),('revision',1)]:
            with self.assertRaises(ChatError):d.turn(dict(body,**{key:val}))
        out=d.turn(body);self.assertEqual(out['revision'],1)
        self.assertNotIn('injected',json.dumps(sent));self.assertEqual(json.loads(sent[0][1]['content'])['UNVERIFIED_DISCUSSION'],[])
        with self.assertRaises(ChatError):d.turn(body)
        d.turn(dict(body,revision=1,role='agent'));self.assertEqual(len(json.loads(sent[1][1]['content'])['UNVERIFIED_DISCUSSION']),1)
        s2=d.open({'case_id':'CASE-002','row_index':0});self.assertEqual(d.sessions[s2['session_id']]['history'],[])
    def test_invalid_reply_not_committed(self):
        d=Discussions({'cases':[case()]},lambda m:('broken','model'))
        s=d.open({'case_id':'CASE-001','row_index':0})
        with self.assertRaises(ChatError):d.turn(dict(session_id=s['session_id'],case_id='CASE-001',row_index=0,context_hash=s['context']['context_hash'],revision=0,role='agent',question='Review'))
        self.assertEqual(d.sessions[s['session_id']]['history'],[])
    def test_one_format_retry_reuses_frozen_context_without_invalid_text(self):
        sent=[]
        def complete(messages):
            sent.append(copy.deepcopy(messages))
            if len(sent)==1:return reply(discussion='REJECTED_MARKER SpO2 available.',uncertainties=[]),'test-model'
            return reply(),'test-model'
        d=Discussions({'cases':[case()]},complete)
        s=d.open({'case_id':'CASE-001','row_index':1,'language':'ko'})
        body=dict(session_id=s['session_id'],case_id='CASE-001',row_index=1,context_hash=s['context']['context_hash'],revision=0,role='agent',question='Which interventions should we review?')
        result=d.turn(body)
        self.assertEqual(len(sent),2);self.assertEqual(result['audit']['validation_attempts'],2)
        self.assertEqual(sent[0][1],sent[1][1])
        self.assertIn('FORMAT CORRECTION',sent[1][0]['content'])
        self.assertNotIn('REJECTED_MARKER',json.dumps(sent[1]))
        self.assertNotIn('REJECTED_MARKER',json.dumps(result))
        self.assertEqual(result['audit']['messages'],sent[1])
        self.assertEqual(len(d.sessions[s['session_id']]['history']),1)
        self.assertEqual(result['context_hash'],s['context']['context_hash'])
    def test_two_format_failures_stop_without_committing_history(self):
        calls=[]
        def complete(messages):calls.append(messages);return 'broken','model'
        d=Discussions({'cases':[case()]},complete);s=d.open({'case_id':'CASE-001','row_index':0})
        with self.assertRaises(ChatError):
            d.turn(dict(session_id=s['session_id'],case_id='CASE-001',row_index=0,context_hash=s['context']['context_hash'],revision=0,role='agent',question='Review'))
        self.assertEqual(len(calls),2);self.assertEqual(d.sessions[s['session_id']]['history'],[])
    def test_no_retry_for_transport_or_clinical_rejection(self):
        for mode in ('transport','stability','stability_and_format'):
            calls=[]
            def complete(messages):
                calls.append(messages)
                if mode=='transport':raise ChatError(503,'KHDP model unavailable.')
                if mode=='stability_and_format':return reply(discussion='The patient is stable.',uncertainties=[]),'model'
                return reply(discussion='The patient is stable.'),'model'
            d=Discussions({'cases':[case()]},complete);s=d.open({'case_id':'CASE-001','row_index':0})
            with self.assertRaises(ChatError):
                d.turn(dict(session_id=s['session_id'],case_id='CASE-001',row_index=0,context_hash=s['context']['context_hash'],revision=0,role='agent',question='Review'))
            self.assertEqual(len(calls),1);self.assertEqual(d.sessions[s['session_id']]['history'],[])
    def test_only_approved_destination(self):
        with patch.dict('os.environ',{'LLM_BASE_URL':'https://example.org/v1','ICU_LLM_CONFIG':''}):
            with self.assertRaises(ChatError):configuration()

if __name__=='__main__':unittest.main()
