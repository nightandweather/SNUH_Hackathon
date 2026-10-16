"""One private KHDP model call, with only structural diagnostics on stdout.

Run with the live server's existing environment. No credentials are copied into
the artifact or logs. The raw reply and patient context remain mode-600 on Pod.
"""
import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

KEYS = {'evidence_ids','discussion','questions','actions','order_review','escalation','sbar','uncertainties'}
SBAR = {'situation','background','assessment','recommendation'}
ORDER = {'item','rationale','check_first'}
QUESTION = ('저는 이 환자를 보는 간호사입니다. 이 평가 시점까지 확인된 기록을 기준으로 어떤 중재를 검토해야 하나요? '
            '의사 관점에서 먼저 확인할 사항, 간호사가 준비할 대응, 담당 의사와 검토할 검사·처치를 구분해 주세요. '
            '각 항목의 근거와 부족한 정보를 설명하고, 실제 처방이 아닌 검토 초안으로 답해 주세요.')


def write_private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    descriptor=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    os.fchmod(descriptor,0o600)
    with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,allow_nan=False)
    temp.replace(path)


def diagnostics(raw, context):
    report={'raw_type':type(raw).__name__,'raw_characters':len(raw) if isinstance(raw,str) else None,
            'json_parse_ok':False,'failed_checks':[],'fields':{}}
    if not isinstance(raw,str):
        report['failed_checks'].append('raw_not_string');return report
    text=raw.strip()
    report['code_fence_present']=text.startswith('```')
    if text.startswith('```'):
        text=re.sub(r'^```(?:json)?\s*|\s*```$','',text)
    try:out=json.loads(text)
    except (ValueError,TypeError):
        report['failed_checks'].append('json_parse');return report
    report.update(json_parse_ok=True,root_type=type(out).__name__)
    if not isinstance(out,dict):
        report['failed_checks'].append('root_not_object');return report
    report['json_keys']=sorted(k if k in KEYS else '<unexpected-key>' for k in out)
    report['missing_keys']=sorted(KEYS-set(out))
    report['unexpected_key_count']=len(set(out)-KEYS)
    if set(out)!=KEYS:report['failed_checks'].append('exact_keys')
    valid={f['id'] for f in context['facts']}
    refs=out.get('evidence_ids');report['evidence_id_count']=len(refs) if isinstance(refs,list) else None
    if isinstance(refs,list):
        report['valid_evidence_id_count']=sum(isinstance(x,str) and x in valid for x in refs)
        report['invalid_evidence_id_count']=sum(not isinstance(x,str) or x not in valid for x in refs)
    if not isinstance(refs,list) or not 1<=len(refs)<=len(context['facts']) or any(not isinstance(x,str) or x not in valid for x in refs):
        report['failed_checks'].append('evidence_ids')
    prose=[]
    def string_check(path, value, minimum, maximum):
        valid_string=isinstance(value,str)
        field={'type':type(value).__name__,'length':len(value) if valid_string else None,
               'nonblank':bool(value.strip()) if valid_string else False}
        if valid_string:
            field['contains_digit']=bool(re.search(r'\d',value))
            field['contains_case_alias']=bool(re.search(r'CASE-',value,re.I))
            field['contains_credential_prefix']=bool(re.search(r'khdp_pat_',value,re.I))
            field['unsupported_stability_phrase']=bool(re.search(r'안정적(?:이|입|으)|(?:are|is|were|was) (?:clinically )?(?:stable|normal)',value,re.I))
            prose.append(value)
        report['fields'][path]=field
        if not valid_string or not minimum<=len(value)<=maximum or not value.strip():
            report['failed_checks'].append(path+'.string_bounds')
    string_check('discussion',out.get('discussion'),5,2400)
    string_check('escalation',out.get('escalation'),5,1400)
    for name,limit in (('questions',4),('actions',4),('uncertainties',3)):
        values=out.get(name);report['fields'][name]={'type':type(values).__name__,'count':len(values) if isinstance(values,list) else None}
        if not isinstance(values,list) or not 1<=len(values)<=limit:
            report['failed_checks'].append(name+'.list_bounds')
        if isinstance(values,list):
            for index,value in enumerate(values):string_check(f'{name}[{index}]',value,1,700)
    sbar=out.get('sbar');report['fields']['sbar']={'type':type(sbar).__name__}
    if not isinstance(sbar,dict) or set(sbar)!=SBAR:report['failed_checks'].append('sbar.keys')
    if isinstance(sbar,dict):
        for name,value in sbar.items():string_check('sbar.'+(name if name in SBAR else '<unexpected-key>'),value,1,900)
    orders=out.get('order_review');report['fields']['order_review']={'type':type(orders).__name__,'count':len(orders) if isinstance(orders,list) else None}
    if not isinstance(orders,list) or not 1<=len(orders)<=3:report['failed_checks'].append('order_review.list_bounds')
    if isinstance(orders,list):
        for index,item in enumerate(orders):
            if not isinstance(item,dict) or set(item)!=ORDER:report['failed_checks'].append(f'order_review[{index}].keys')
            if isinstance(item,dict):
                for name,value in item.items():string_check(f'order_review[{index}].'+(name if name in ORDER else '<unexpected-key>'),value,1,700)
    joined=' '.join(prose)
    report['digits_or_identifier_in_prose']=bool(re.search(r'\d|CASE-|khdp_pat_',joined,re.I))
    report['stability_flag']=bool(re.search(r'안정적(?:이|입|으)|(?:are|is|were|was) (?:clinically )?(?:stable|normal)',joined,re.I))
    if report['digits_or_identifier_in_prose']:report['failed_checks'].append('prose_digits_or_identifier')
    if report['stability_flag']:report['failed_checks'].append('unsupported_stability')
    return report


def main(args):
    sys.path.insert(0,str(args.live))
    import kmimic_board
    import grounded_chat
    pool=json.loads(args.pool.read_text())
    payload=kmimic_board.case_payload(pool)
    case=next(c for c in payload['cases'] if c['id']==args.case)
    context=grounded_chat.context_for(case,args.row)
    report={'at':datetime.now(timezone.utc).isoformat(),'case_alias':args.case,'row_index':args.row,
            'as_of_minute':context['as_of_minute'],'prompt_version':grounded_chat.VERSION,
            'context_fact_count':len(context['facts'])}
    try:
        with urlopen('http://127.0.0.1:8007/api/cases',timeout=10) as response:live=json.load(response)
        livecase=next(c for c in live['cases'] if c['id']==args.case)
        report['live_case_shape_matches']=len(livecase['rows'])==len(case['rows']) and livecase['dataset']==case['dataset'] and livecase['rows'][args.row]['minute']==context['as_of_minute']
        if not report['live_case_shape_matches']:raise ValueError('Live case mismatch')
    except Exception as error:
        report['live_shape_check_error']=type(error).__name__
        print('GS_LLM_DIAGNOSTIC',json.dumps(report),flush=True)
        return
    messages=grounded_chat.messages_for(context,[],'agent','ko',QUESTION)
    try:
        raw,model=grounded_chat.complete(messages)
    except Exception as error:
        report['completion_error_type']=type(error).__name__
        report['completion_status']=getattr(error,'status',None)
        print('GS_LLM_DIAGNOSTIC',json.dumps(report),flush=True)
        return
    report['model']=re.sub(r'[^A-Za-z0-9_.:/-]','?',str(model))[:120]
    report.update(diagnostics(raw,context))
    try:
        grounded_chat.validate_output(raw,context)
        report['live_validator_accepts']=True
    except Exception as error:
        report['live_validator_accepts']=False
        report['validation_error_type']=type(error).__name__
        report['validation_status']=getattr(error,'status',None)
    write_private(args.output,{'at':report['at'],'raw':raw,'model':model,'context':context,
                              'question':QUESTION,'diagnostics':report})
    print('GS_LLM_DIAGNOSTIC',json.dumps(report),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',type=Path,default=Path('/home/khdp-user/workspace/icu-runtime/kmimic-board-v1'))
    parser.add_argument('--pool',type=Path,default=Path('/home/khdp-user/workspace/icu-runtime/gs-board-pool/pool_gs.json'))
    parser.add_argument('--case',default='CASE-001');parser.add_argument('--row',type=int,default=548)
    parser.add_argument('--output',type=Path,default=Path('/home/khdp-user/workspace/icu-runtime/gs-llm-smoke.private.json'))
    main(parser.parse_args())
