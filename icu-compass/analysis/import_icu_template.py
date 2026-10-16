"""Read user's planning workbook; never treat it as K-MIMIC clinical records."""
from pathlib import Path
import json,openpyxl
root=Path(__file__).resolve().parents[1]
w=openpyxl.load_workbook('/Users/iganghun/Downloads/ICU.xlsx',data_only=True);s=w['Sheet1']
colors={'FFFF0000':'red','FF0070C0':'blue','FF00B050':'green','FFFFFF00':'yellow'}
rows=[]
for row in range(2,37):
 cells=[]
 for col in range(2,10):
  c=s.cell(row,col);status=colors.get(c.fill.fgColor.rgb,'empty') if c.fill.fgColor.type=='rgb' and c.fill.patternType else 'empty'
  cells.append({'status':status,'event':str(c.value or '').strip()})
 rows.append({'day':s.cell(row,1).value,'sourceRow':row,'beds':cells})
js='''/* User-supplied fictional plan. Blanks interpreted by user confirmation. */
(()=>{const rows=DATA;
function render(){const ko=document.documentElement.lang!=='en',e=document.getElementById('workbookPlan');if(!e)return;const empty=ko?'빈 병상':'Empty bed',occupied=ko?'계속 입실 중':'Still admitted',reserved=ko?'입실 예약':'Reserved';
e.innerHTML='<summary>'+(ko?'ICU.xlsx · 제공한 8병상 시나리오':'ICU.xlsx · supplied eight-bed plan')+'</summary><h2>'+(ko?'31일 병상 시나리오':'31-day bed scenario')+'</h2><p class="tag">'+(ko?'색칠된 빈칸은 계속 입실 중, 색 없는 칸은 빈 병상입니다. 노란색은 입실 예약입니다. 원본 마지막 4행은 날짜 미기재로 유지했습니다. AE·OR은 원문 약어이며 의미 미확인입니다. 실제 K-MIMIC 환자 경과가 아닌 제공된 계획표입니다.':'Colored blanks mean still admitted; unfilled cells mean empty beds; yellow means reserved. The final four source rows have no day assigned. AE and OR are undefined source labels. This is a supplied fictional plan, not actual K-MIMIC patient history.')+'</p><div class="flow-scroll"><table class="workbook-table"><thead><tr><th>'+(ko?'일차':'Day')+'</th>'+Array.from({length:8},(_,i)=>'<th>'+(ko?'병상 ':'Bed ')+(i+1)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr><th scope="row">'+(r.day??(ko?'미기재':'Unspecified'))+'<small>'+(r.day?'':(ko?'원본 행 ':'Row ')+r.sourceRow)+'</small></th>'+r.beds.map(c=>'<td class="'+c.status+'"><b>'+(c.event||(c.status==='empty'?empty:c.status==='yellow'?reserved:occupied))+'</b><small>'+c.status.toUpperCase()+'</small></td>').join('')+'</tr>').join('')+'</tbody></table></div>';
}document.addEventListener('icu-language',render);document.addEventListener('DOMContentLoaded',render);})();
'''.replace('DATA',json.dumps(rows,ensure_ascii=False))
(root/'static/workbook-plan.js').write_text(js)
p=root/'static/index.html';h=p.read_text().replace('<section class="flow-panel"><details id="flowDetails"','<section class="flow-panel"><details id="workbookPlan" open data-no-translate></details></section><section class="flow-panel"><details id="flowDetails"',1);h=h.replace('</body>','<script>'+js+'</script></body>');p.write_text(h)
p=root/'static/app-shell.css';h=p.read_text()+'''\n#workbookPlan>summary{font-size:17px;font-weight:700;margin-bottom:12px}.workbook-table th:last-child{width:auto}.workbook-table th:first-child{width:110px}.workbook-table td{padding:8px;height:72px;color:white}.workbook-table small{display:block;font-size:10px;font-weight:400}.workbook-table th[scope=row]{position:static;font-size:12px}.workbook-table .empty{color:#475569}.workbook-table .yellow{color:#67521c}\n''';p.write_text(h)
print('Imported',len(rows),'rows, eight cells each; original workbook unchanged')
