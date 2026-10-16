"""Hospital identity isolation and per-request dialogue language."""
import copy
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest
from unittest.mock import patch
import consult
import demo_profiles
import team_chat

class NetworkLanguageTest(unittest.TestCase):
    def test_three_hospitals_have_distinct_patient_and_bed_ids(self):
        h = demo_profiles.create('bleeding', multi_hospital=True)
        state = h.state()
        self.assertEqual(len(h.beds), 96)
        self.assertEqual({u['hospital_id'] for f in state['floors'] for u in f['units']}, {'A','B','C'})
        patients = [b['patient']['src']['pid'] for b in h.beds.values() if b['patient']]
        self.assertEqual(len(patients), len(set(patients)))
        for incident in state['incidents']:
            self.assertTrue(all(h.nurses[n]['unit'] == incident['unit'] for n in incident['responders']))
        b_units = [u for u in h.units.values() if u.get('hospital_id') == 'B']
        self.assertTrue(all(not h.beds[bid]['patient'] or h.beds[bid]['patient']['src']['extra_observations']['gcs']==15 for u in b_units for bid in u['bed_ids']))

    def test_korean_system_language_preserves_history_and_evidence(self):
        messages=[{'role':'system','content':'Respond in English. Begin with Simulated patient:.'}, {'role':'user','content':'Original English record: HR 128 mmHg is recorded literally.'}]
        original=copy.deepcopy(messages)
        with consult.response_language('ko'):
            result=consult.localized_messages(messages)
        self.assertIn('Respond in Korean',result[0]['content'])
        self.assertIn('가상 환자:',result[0]['content'])
        self.assertEqual(result[1],messages[1])
        self.assertEqual(messages,original)
        self.assertEqual(consult.RESPONSE_LANGUAGE.get(),'en')

    def test_concurrent_clients_do_not_leak_language(self):
        barrier=threading.Barrier(2)
        def request(language):
            with consult.response_language(language):
                barrier.wait()
                return consult.localized_messages([{'role':'system','content':'Respond in English.'}])[0]['content']
        with ThreadPoolExecutor(2) as executor:
            ko=executor.submit(request,'ko');en=executor.submit(request,'en')
            self.assertIn('Respond in Korean',ko.result())
            self.assertIn('Respond in English',en.result())
        self.assertEqual(consult.RESPONSE_LANGUAGE.get(),'en')

    def test_korean_model_reply_is_not_rejected_as_unavailable(self):
        ctx=consult.context(demo_profiles.create('bleeding'),'SICU-01')
        with consult.response_language('ko'),patch.object(consult,'chat',return_value='가상 환자: 배액에 대해 설명해 주세요.'),patch.object(consult,'model_name',return_value='test-qwen'):
            answer=team_chat.turn(ctx,[],'patient')
        self.assertEqual(answer['mode'],'model')
        self.assertTrue(answer['text'].startswith('가상 환자:'))

    def test_language_reset_even_after_failure(self):
        with self.assertRaises(RuntimeError):
            with consult.response_language('ko'):
                raise RuntimeError('test')
        self.assertEqual(consult.RESPONSE_LANGUAGE.get(),'en')

class HospitalControlTest(unittest.TestCase):
    def test_profile_control_targets_selected_hospital_and_preserves_other_profiles(self):
        from test_shift_api import DirectRequests
        import server
        profiles={"A":"bleeding","B":"calm","C":"surge"}
        h=demo_profiles.create("bleeding",multi_hospital=True)
        with patch.dict("os.environ",{"ICU_DEMO_SCENARIO":"bleeding"}), patch.dict(server.sim,{"h":h,"seed":10,"profile":"bleeding","hospital_profiles":profiles.copy(),"running":False,"speed":2,"baseline":None},clear=True):
            client=DirectRequests()
            result=client.request("POST","/api/control",{"action":"profile","hospital_id":"B","value":"surge"})
            self.assertEqual(result['code'],200)
            self.assertEqual(server.sim['hospital_profiles'],{"A":"bleeding","B":"surge","C":"surge"})
            self.assertEqual(server.sim['seed'],11)
            self.assertEqual(sum(i['unit'].startswith('B-') for i in server.sim['h'].incidents),16)
            result=client.request("POST","/api/control",{"action":"profile","hospital_id":"B","value":"bleeding"})
            self.assertEqual(result['code'],200)
            b_events=[i for i in server.sim['h'].incidents if i['unit'].startswith('B-')]
            self.assertEqual(len(b_events),1)
            self.assertEqual(b_events[0]['bed'],'B-SICU-01')
            before=server.sim['seed']
            self.assertEqual(client.request("POST","/api/control",{"action":"profile","hospital_id":"missing","value":"calm"})['code'],400)
            self.assertEqual(server.sim['seed'],before)

if __name__=='__main__':unittest.main()
