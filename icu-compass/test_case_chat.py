import copy
import json
import unittest
import threading
import time
import types
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from case_chat import install
from case_chat import CaseChat, CaseError, snapshot_from_patient, parse_turns


def patient():
    return {'offset': 5, 'admit_t': 0, 'vitals': {'map': 1}, 'src': {
        'pid': 'DEMO-01', 'step': 5,
        'series': {'hr': [80, 70], 'map': [75, 56], 'spo2': [98, 97], 'rr': [15, 24], 'sbp': [110, 94]},
        'measurement_age_min': {'hr': [0, 31], 'map': [0, 4], 'spo2': [0, 2], 'rr': [0, 1], 'sbp': [0, 4]},
        'provenance': {'dataset': 'synthetic-test', 'partition': 'test', 'raw_subject_id': 'NEVER_EXPORT'}}}


class CaseChatTests(unittest.TestCase):
    def test_async_http_returns_job_then_completed_result(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def _send(self,status,body):
                data=json.dumps(body).encode()
                self.send_response(status); self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
            def do_GET(self): self._send(404,{'error':'not found'})
            def do_POST(self): self._send(404,{'error':'not found'})
        h=types.SimpleNamespace(beds={'A':{'patient':patient()}},state=lambda:{'clock':'07:00'})
        server=types.SimpleNamespace(lock=threading.Lock(),sim={'h':h},H=Handler)
        def fake_model(*args):
            time.sleep(.03)
            return [{'role':'patient','text':'Missing','evidence_keys':['missing'],'origin':'record_limit'}]
        with patch('case_chat.model_round',fake_model): install(server,'.')
        http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=http.serve_forever,daemon=True);worker.start()
        base='http://127.0.0.1:'+str(http.server_port)
        try:
            req=urllib.request.Request(base+'/api/case-conversation',json.dumps({'bed':'A','patient_id':'DEMO-01'}).encode(),{'Content-Type':'application/json','X-ICU-Case':'1'})
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status,202);job=json.load(resp)
            self.assertTrue(job['pending'])
            for _ in range(30):
                time.sleep(.02)
                req=urllib.request.Request(base+'/api/case-result?id='+job['job_id'],headers={'X-ICU-Case':'1'})
                with urllib.request.urlopen(req) as resp: result=json.load(resp)
                if not result.get('pending'): break
            self.assertEqual(len(result['rounds']),1)
            self.assertEqual(result['snapshot']['replay_id'],'DEMO-01')
        finally: http.shutdown();http.server_close();worker.join()

    def test_source_snapshot_never_uses_injected_values_or_raw_identifiers(self):
        snap = snapshot_from_patient(patient(), 'SICU-01', '07:00')
        self.assertEqual(snap['measurements']['map']['value'], 56)
        self.assertIsNone(snap['measurements']['hr']['value'])
        self.assertEqual(snap['qsofa']['possible_range'], [2, 3])
        self.assertIsNone(snap['qsofa']['score'])
        self.assertNotIn('NEVER_EXPORT', json.dumps(snap))

    def test_validated_roles_and_no_model_patient_speech(self):
        data={'turns':[{'role':r,'text':'Review the record.', 'evidence_keys':['map','missing']} for r in ('nurse','physician','llm_agent')]}
        turns=parse_turns(json.dumps(data))
        self.assertEqual([x['role'] for x in turns],['patient','nurse','physician','llm_agent'])
        self.assertEqual(turns[0]['origin'],'record_limit')
        data['turns'][0]['evidence_keys']=['imaginary_ct']
        with self.assertRaises(CaseError): parse_turns(json.dumps(data))
        with self.assertRaises(CaseError): parse_turns('not json')

    def test_frozen_snapshot_and_cross_patient_rejection(self):
        pt=patient(); generation=[1]; calls=[]
        def capture(bed,pid):
            return (generation[0],bed,pid), snapshot_from_patient(pt,bed,'07:00')
        def model(base,snap,history,q):
            calls.append(copy.deepcopy(snap))
            return [{'role':'patient','text':'Missing','evidence_keys':['missing'],'origin':'record_limit'}]
        chat=CaseChat('.',capture,model)
        first=chat.handle({'bed':'A','patient_id':'P'})
        pt['src']['series']['map'][1]=90
        second=chat.handle({'bed':'A','patient_id':'P','session_id':first['session_id'],'message':'Continue'})
        self.assertEqual(calls[1]['measurements']['map']['value'],56)
        self.assertEqual(len(second['rounds']),2)
        with self.assertRaises(CaseError): chat.handle({'bed':'B','patient_id':'Q','session_id':first['session_id']})
        generation[0]=2
        with self.assertRaises(CaseError): chat.handle({'bed':'A','patient_id':'P','session_id':first['session_id']})

    def test_patient_changed_during_model_response_is_rejected(self):
        version=[1]
        def capture(bed,pid): return version[0],snapshot_from_patient(patient(),bed,'07:00')
        def model(*args): version[0]+=1; return []
        chat=CaseChat('.',capture,model)
        with self.assertRaises(CaseError) as err: chat.handle({'bed':'A','patient_id':'P'})
        self.assertEqual(err.exception.status,409)

    def test_failure_does_not_add_fake_dialogue(self):
        def capture(bed,pid): return 1,snapshot_from_patient(patient(),bed,'07:00')
        def model(*args): raise CaseError(503,'offline')
        chat=CaseChat('.',capture,model)
        with self.assertRaises(CaseError): chat.handle({'bed':'A','patient_id':'P'})
        self.assertTrue(all(not s['rounds'] and not s['busy'] for s in chat.sessions.values()))

    def test_speaking_role_is_discussion_context_not_record(self):
        seen=[]
        def capture(bed,pid): return 1,snapshot_from_patient(patient(),bed,'07:00')
        def model(base,snapshot,history,question):
            seen.append((copy.deepcopy(snapshot),question));return []
        chat=CaseChat('.',capture,model)
        reply=chat.handle({'bed':'A','patient_id':'P','speaker':'patient','message':'Hypothetically, I feel dizzy.'})
        self.assertEqual(reply['rounds'][0]['speaker'],'patient')
        self.assertEqual(seen[0][1]['role'],'patient')
        self.assertNotIn('dizzy',json.dumps(seen[0][0]))
        with self.assertRaises(CaseError): chat.handle({'bed':'A','patient_id':'P','speaker':'system'})

if __name__=='__main__': unittest.main()
