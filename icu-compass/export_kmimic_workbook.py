"""Generate XLSX inside KHDP. Uses bundled XlsxWriter fallback (no Node/artifact runtime on Pod)."""
from pathlib import Path
import json,sys,collections,html,zipfile,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).with_name('xlsxwriter-runtime.zip')))
import xlsxwriter
base=Path.home()/'workspace/icu-runtime/kmimic-board-cohort'
pool=json.loads((base/'pool_kmimic.json').read_text())
out=Path(__file__).parent/'K-MIMIC_SICU_sample.xlsx'
wb=xlsxwriter.Workbook(str(out),{'strings_to_formulas':False,'strings_to_urls':False})
body=wb.add_format({'font_name':'Arial','font_size':11,'valign':'vcenter'})
head=wb.add_format({'font_name':'Arial','font_size':11,'bold':True,'font_color':'white','bg_color':'#213E5B','text_wrap':True,'valign':'vcenter','align':'center'})
num=wb.add_format({'font_name':'Arial','font_size':11,'num_format':'0.0','valign':'vcenter'})
title=wb.add_format({'font_name':'Arial','font_size':16,'bold':True,'font_color':'#213E5B'})
note=wb.add_format({'font_name':'Arial','font_size':11,'font_color':'#596D80','text_wrap':True,'valign':'top'})
previews=[]
def sheet(name,headers,rows,widths,source):
 ws=wb.add_worksheet(name);ws.hide_gridlines(2);ws.set_default_row(23);ws.merge_range(1,0,1,len(headers)-1,name,title);ws.merge_range(2,0,2,len(headers)-1,source,note);ws.set_row(2,42)
 ws.write_row(4,0,headers,head);ws.set_row(4,34)
 for col,width in enumerate(widths):ws.set_column(col,col,width,body)
 for r,row in enumerate(rows,5):
  for c,v in enumerate(row):
   if v is None:ws.write_blank(r,c,None,body)
   elif isinstance(v,bool):ws.write_boolean(r,c,v,body)
   elif isinstance(v,(float,int)):ws.write_number(r,c,v,num if isinstance(v,float) else body)
   else:ws.write_string(r,c,str(v),body)
 if rows:ws.autofilter(4,0,len(rows)+4,len(headers)-1)
 ws.freeze_panes(5,1);ws.set_landscape();ws.fit_to_pages(1,0);ws.repeat_rows(4)
 previews.append((name,headers,rows[:8],source));return ws
admissions=[];vitals=[];devices=[];procedures=[]
for i,p in enumerate(pool,1):
 alias=f'CASE-{i:03d}'; prov=p['provenance']; ps=p.get('procedures',[]);done=[e for e in ps if e['end_min']<=p['los_min']]
 admissions.append([alias,p['careunit'],prov['dataset'],prov['partition'],p['los_min'],len(p.get('raw_observations',[])),len(done),len(p.get('device_events',{}).get('ventilator',[])),'Not mapped'])
 for e in p.get('raw_observations',[]):vitals.append([alias,e['minute'],e['variable'],e['itemid'],e['value'],e['unit'],e['table']])
 for e in p.get('device_events',{}).get('ventilator',[]):devices.append([alias,e['minute'],'Ventilator',e['raw'],e['itemid'],e['table']])
 for e in ps:procedures.append([alias,e['start_min'],e['end_min'],e['itemid'],e.get('category',''),e.get('value',''),e.get('unit',''),e['end_min']<=p['los_min'],'PROCEDUREEVENTS'])
source='K-MIMIC kmimic-emr-001 / partition 268; source files remain in KHDP. IDs replaced with workbook case aliases.'
summary=[['Source','K-MIMIC kmimic-emr-001 / 268'],['Grain','One ICU admission per case, not distinct patients'],['Selection','FIRST_CAREUNIT = SICU; first 48 eligible stays; 38 usable vital replay admissions'],['Time','Minutes since source ICU admission; first 24 hours or shorter stay'],['Scope','Convenience sample, not a representative cohort or live occupancy'],['Procedure count','Unique PROCEDUREEVENT_ID within admission; valid start/end; end within displayed period'],['Meaning','Documented ended procedure rows, not confirmed nursing effort or verified treatment completion'],['Not counted','Vital signs, model text, simulated calls, medication input rows'],['Nurse attribution','PROCEDUREEVENTS does not expose CGID here; nurse-level attribution unavailable'],['Device mapping','001C_1207_22360 VALUE ON/OFF only; absence of a record means unknown'],['Vitals','Accepted numeric original observations with verified units; no filled-forward values in this workbook'],['Missing','Blank means unavailable; zero procedure records does not prove no care'],['Privacy','No original subject/admission/stay identifiers or shifted absolute timestamps exported']]
sheet('Guide',['항목 / Item','내용 / Definition'],summary,[29,110],source)
sheet('Admissions',['사례 / Case','ICU','Dataset','Partition','관측 범위 min','활력징후 기록 수','종료시각 처치 행 수','인공호흡기 기록 수','간호사 연결'],admissions,[18,14,23,14,21,22,24,24,22],source+' Counts are static source summaries for the extracted interval.')
sheet('Vitals',['사례 / Case','입실 후 min','변수','ITEMID','값 / Value','단위 / Unit','원본 테이블'],vitals,[18,18,16,26,16,18,24],source+' CHARTEVENTS; accepted observations, not diagnoses.')
sheet('Devices',['사례 / Case','입실 후 min','장비','원본 상태','ITEMID','원본 테이블'],devices,[18,18,22,20,26,25],source+(' No matching ventilator ON/OFF rows in selected first-day admissions; status remains unknown.' if not devices else ' Explicit source ON/OFF values.'))
sheet('Procedures',['사례 / Case','시작 min','종료 min','ITEMID','원본 분류','원본 값','단위','표본기간 내 종료','원본 테이블'],procedures,[18,17,17,26,30,24,18,24,26],source+(' No matched rows in selected interval; this does not establish absence of treatment.' if not procedures else ' Original documented procedure rows; caregiver attribution unavailable.'))
audit=json.loads((base/'replay_audit.json').read_text());mapping=audit['item_mapping'];bookrows=[[iid,var,'CHARTEVENTS','Numeric value; unit validated'] for iid,var in mapping.items()]+[['001C_1207_22360','ventilator','CHARTEVENTS','VALUE ON / OFF; no matching record = unknown'],['FIRST_CAREUNIT','SICU','ICUSTAYS','Exact unit-code filter; institutional definition pending']]
sheet('Codebook',['ITEMID / Field','Variable','Table','Interpretation'],bookrows,[28,22,25,70],source)
wb.close()
# Validate serialized workbook and row totals without moving real records off Pod.
with zipfile.ZipFile(out) as z:
 assert z.testzip() is None
 root=ET.fromstring(z.read('xl/workbook.xml'));ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
 assert len(root.findall('s:sheets/s:sheet',ns))==6
 for n,expected in [(2,len(admissions)),(3,len(vitals)),(4,len(devices)),(5,len(procedures))]:
  r=ET.fromstring(z.read(f'xl/worksheets/sheet{n}.xml'));assert len(r.findall('s:sheetData/s:row',ns))==expected+3,(n,expected)
# Browser-readable workbook preview, using the same rows and header layout.
parts=['<!doctype html><meta charset="utf-8"><title>K-MIMIC Excel preview</title><style>body{font:14px Arial,sans-serif;background:#f3f6fa;color:#243c53;margin:25px}section{background:white;padding:22px;margin:20px 0;border:1px solid #d5e0eb;border-radius:10px;overflow:auto}table{border-collapse:collapse;min-width:900px}th{background:#213e5b;color:white;text-align:center}th,td{padding:12px;border-bottom:1px solid #d9e2eb;max-width:700px;white-space:normal}h1{font-size:24px}h2{font-size:20px}a{font-weight:bold;color:#245f98}p{color:#5b7082}</style><h1>K-MIMIC 외과 ICU 엑셀 미리보기</h1><p>각 시트의 처음 8행입니다. 전체 기록은 엑셀에 포함됩니다.</p><a href="workbook.xlsx">엑셀 내려받기 / Download XLSX</a>']
for name,headers,rows,src in previews:
 parts.append('<section><h2>'+html.escape(name)+'</h2><p>'+html.escape(src)+'</p><table><tr>'+''.join('<th>'+html.escape(str(v))+'</th>' for v in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape('' if v is None else str(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</table></section>')
(Path(__file__).parent/'workbook-preview.html').write_text(''.join(parts))
print(json.dumps({'xlsx':out.name,'admissions':len(admissions),'vital_rows':len(vitals),'device_rows':len(devices),'procedure_rows':len(procedures),'bytes':out.stat().st_size}))
