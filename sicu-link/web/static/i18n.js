/* UI-only localization. Source records and conversation bodies are immutable. */
const I18n = (() => {
  const dictionary = Object.fromEntries(`
Transit|이송·인계
Turnover|병상 정리
Deceased|사망
RED · transfer on hold|RED · 전실 보류
BLUE · transfer review|BLUE · 전실 검토
GREEN · transfer candidate|GREEN · 전실 후보
Transfer-review draft, not a validated severity score.|전실 검토 초안이며 검증된 중증도 점수가 아닙니다.
Recorded care this shift|이번 근무 처치 기록 수
Nurse ring = presence of user-entered care records, not fatigue|간호사 테두리 = 사용자 입력 처치 기록 유무
Data sources and language|데이터 출처·언어 안내
Scenario details|시나리오 설명
No configured threshold crossed|설정한 기준값을 넘지 않음
synthetic retrospective replay|가상 데이터 시점 재생
Replay alerts are not confirmed clinical events. Missing measurements are not treated as normal.|재생 알림은 확정된 임상 이벤트가 아닙니다. 누락된 측정값을 정상으로 간주하지 않습니다.
Reference calculation only in this ICU. No emergency classification from qSOFA.|이 ICU에서는 참고 계산만 제공합니다. qSOFA로 응급상황을 분류하지 않습니다.
AgentMD-inspired calculator workflow; deterministic qSOFA reference implementation. AgentMD itself is not running.|AgentMD에서 착안한 계산기 흐름과 규칙 기반 qSOFA 참고 구현입니다. AgentMD 자체를 실행하는 것은 아닙니다.
Mental status (GCS proxy)|의식 상태 (GCS 기준)
Possible score|가능 점수
no total assigned|총점 미산정
point(s)|점
As of|기준 시각
No future prediction|미래 예측 아님
Last replay observation|최근 재생 관측값
Two-hour replay trend. Blue: recorded values; orange: simulated emergency.|2시간 재생 추이. 파랑: 기록값, 주황: 모의 응급상황.
Only past and current replay observations are stored. Missing values carry forward from up to 12 prior record intervals. Injected simulation values are separate from observed_vitals source records.|과거·현재의 재생 관측값만 저장합니다. 결측값은 최대 12개 이전 기록 구간의 값으로 유지됩니다. 주입한 시뮬레이션 값은 observed_vitals 원본 기록과 구분됩니다.
Assigned nurse role simulation|담당 간호사 역할 시뮬레이션
No diagnostic simulations for this admission|이번 입실의 검사 시뮬레이션 없음
h since admission|시간 경과 (입실 후)
h remaining|시간 남음
years|세
side|옆
Demo icon rules · ● active / ○ inactive / ? unknown|모의 아이콘 기준 · ● 활성 / ○ 비활성 / ? 미확인
Illustrative thresholds only: SBP <90 or MAP <65 mmHg; HR >100 bpm; SpO₂ <92%; RR ≥22/min; GCS <15; pain ≥4/10; temperature ≥38°C. Bleeding requires an explicit simulated finding. These icons are not a validated triage score.|예시 기준: SBP <90 또는 MAP <65 mmHg, HR >100회/분, SpO₂ <92%, RR ≥22회/분, GCS <15, 통증 ≥4/10, 체온 ≥38°C. 출혈은 명시된 모의 소견이 있을 때만 활성화합니다. 검증된 중증도 분류 점수가 아닙니다.
Patient conversation|환자별 팀 대화
Patient summary|환자 요약
Close conversation|대화창 닫기
More actions|추가 기능
No active demo finding|활성화된 모의 소견 없음
Applying settings…|설정 적용 중…
Settings applied.|설정을 적용했습니다.
Settings failed. Please retry.|설정 적용에 실패했습니다. 다시 시도해 주세요.
Connection interrupted. Retrying…|연결이 끊겼습니다. 다시 연결하는 중…
Could not refresh the dashboard.|상황판을 갱신하지 못했습니다.
A care record is being saved. Try again when saving finishes.|간호 기록을 저장하고 있습니다. 저장이 끝나면 다시 시도해 주세요.
The selected hospital receives the scenario. Starting or resetting a scenario resets the shared simulation clock.|선택한 병원에 시나리오를 적용합니다. 시나리오 시작·초기화 시 공통 시뮬레이션 시간이 초기화됩니다.
Back to conversation|대화로 돌아가기
Fictional postoperative scenario; surgery type and time are not source records.|가상의 수술 후 상황입니다. 수술 종류와 시각은 원본 기록이 아닙니다.
Bright-red drain output: 180 mL in the last hour versus 30 mL in the preceding hour (fictional).|선홍색 배액: 직전 1시간 30 mL에서 최근 1시간 180 mL로 증가 (가상).
New blood staining on the wound dressing (fictional).|상처 드레싱에 새로운 혈액 얼룩 (가상).
Awake and able to speak; reports dizziness and palpitations (fictional patient role-play).|의식이 있고 대화 가능하며 어지러움과 두근거림을 호소 (가상 환자 역할극).
Hemoglobin, lactate, coagulation results and bleeding source are unknown.|혈색소·젖산·응고검사 결과와 출혈 부위는 미확인입니다.
Injected vitals|모의 활력징후
In simulation|시뮬레이션에서
Response dispatch started|대응 인력 호출 시작
simulation|시뮬레이션
CPR today|당일 CPR
ECMO / CRRT|ECMO / CRRT
Pressor escalation / unstable|승압제 증량·불안정
Surgery today|당일 수술
Five care indicators inside each occupied bed. Select a bed for patient details.|각 환자 병상 안에 5개 간호 상태 아이콘을 표시합니다. 병상을 누르면 상세 정보를 볼 수 있습니다.
Five care indicators|5가지 간호 상태 아이콘
Filled color: active · Outline: not active · Dashed ?: unknown. Today uses the simulation calendar day. Icons indicate care needs, not a severity score.|색 채움: 해당 상태 있음 · 윤곽선: 없음 · 점선 ?: 미확인. ‘당일’은 시뮬레이션 날짜 기준입니다. 간호 상태 표시이며 중증도 점수가 아닙니다.
Simulation controls|시뮬레이션 설정
Ward map · staff positions|병동 지도 · 인력 위치
30-day bed planning sandbox|30일 병상 계획 샌드박스
8 beds per ICU|ICU당 8병상
Cardiovascular Surgical ICU|심혈관외과 중환자실
Neurosurgical ICU|신경외과 중환자실
Trauma Surgical ICU|외상외과 중환자실
Surgical ICU|외과 중환자실
Current|현재
Total nurses|전체 간호사
until shift change|교대까지
on duty / all three shifts|근무 중 / 3교대 전체
staff|명
1min/sec|1분/초
2min/sec|2분/초
5min/sec|5분/초
15min/sec|15분/초
30min/sec|30분/초
ICU Nursing Dashboard|ICU 간호 상황판
Surgical ICU Nursing Dashboard|외과계 ICU 간호 상황판
Surgical ICU · Team Simulation|외과계 ICU · 팀 시뮬레이션
Pause|일시정지
Play|실행
Fixed 2:1 staffing|고정 2:1 배치
Dynamic staffing (within ICU)|유동 배치 (동일 ICU)
Calm shift|평온한 근무
Suspected bleeding|출혈 의심
Overloaded shift|과부하 근무
Start selected scenario|선택한 시나리오 시작
Reset scenario|시나리오 초기화
30-day bed flow ↓|30일 병상 흐름 ↓
All-ward view|전체 병동 보기
My nurse view|내 담당 간호사 보기
Shift scenario|근무 시나리오
Speed: simulated minutes per second|속도: 실제 1초당 시뮬레이션 시간(분)
Research prototype|연구용 프로토타입
Open actual K-MIMIC replay on KHDP|KHDP에서 실제 K-MIMIC 재생 열기
AgentMD-inspired calculator workflow|AgentMD 참고 계산기 흐름
. qSOFA is calculated from available observations; it does not establish an ICU emergency. The 0–100 workload index is a simulation heuristic, not a validated clinical score.|. qSOFA는 이용 가능한 관측값으로 계산하며 ICU 응급상황을 확정하지 않습니다. 0–100 업무량 지수는 시뮬레이션용이며 검증된 임상 점수가 아닙니다.
Current shift|현재 근무
Loading shift information|근무 정보 불러오는 중
Advance to next shift|다음 근무로 이동
Current shift and three-shift schedule|현재 근무 및 3교대 일정
Patient timelines and active events continue across shifts. Assignment, coverage and response stay within the same ICU. My view follows the current nurse in the selected slot. One physician per ICU is a simulation assumption.|근무가 바뀌어도 환자 경과와 진행 중인 이벤트는 이어집니다. 배치·지원·대응은 같은 ICU 안에서 수행합니다. 내 보기는 선택한 근무 자리의 현재 간호사를 따릅니다. ICU당 의사 1명은 시뮬레이션 가정입니다.
New AI replies follow the selected language. Existing conversations, saved notes and source records remain in their original language.|새 AI 응답은 선택한 언어로 생성됩니다. 기존 대화·저장된 기록·원본 데이터는 원문을 유지합니다.
Fully fictional training cases · 8 beds per ICU · Staff markers are spaced for readability; movement and dispatch are simulated.|모든 사례는 교육용 가상 데이터 · ICU당 8병상 · 직원 표시는 겹치지 않게 배치했으며 이동·호출은 시뮬레이션입니다.
Surgical ICU simulation|외과계 ICU 시뮬레이션
Legend|범례
Critical · active emergency|위급 · 응급 이벤트 진행
Watch · elevated demo workload|주의 · 높은 모의 업무량
Stable · routine monitoring|안정 · 일반 모니터링
Reserved · surgery scheduled|예약 · 수술 예정
Empty · available|빈 병상 · 사용 가능
Colors represent simulation states, not validated clinical severity.|색상은 시뮬레이션 상태이며 검증된 임상 중증도가 아닙니다.
Assigned patient care|담당 환자 간호
Event response|이벤트 대응
Coverage within the same ICU|동일 ICU 내 지원
Unit/on-call physician (simulation)|병동·당직 의사 (시뮬레이션)
Nurse ring = fatigue (green <60 · yellow 60–74 · red ≥75)|간호사 테두리 = 피로도 (초록 <60 · 노랑 60–74 · 빨강 ≥75)
Standby / response availability|대기 인력 · 대응 가능 여부
Active alerts · evidence|진행 중인 알림 · 근거
Nurses with highest fatigue this shift|이번 근무 피로도 상위 간호사
Patients / nurses|환자 · 간호사
Select a bed to view patient details.|병상을 선택하면 환자 상세 정보가 표시됩니다.
Current vitals · two-hour replay|현재 활력징후 · 2시간 재생
Record replay|기록 재생
Simulated emergency · dots mark replay observations|모의 응급상황 · 점은 기록 관측값
Diagnostic workflow simulation|검사 흐름 시뮬레이션
Simulated specimen and imaging workflows. These are not actual orders or results.|검체·영상 검사 흐름을 모의합니다. 실제 처방이나 검사 결과가 아닙니다.
Simulate blood draw|채혈 시뮬레이션
Simulate portable X-ray call|이동식 X선 호출 시뮬레이션
Current / next shift|현재 · 다음 근무
Select ICU for roster and handovers|근무표·인계 정보를 볼 ICU 선택
Latest shift handover|최근 근무 인계
Metrics|지표
8 hours · one shift|8시간 · 1개 근무
24 hours · three shifts|24시간 · 3개 근무
Compare the same scenario|같은 시나리오 비교
Records|기록
30-day surgical ICU bed flow · 8 beds|외과계 ICU 30일 병상 흐름 · 8병상
RED · Critical|빨강 · 위급
BLUE · ICU monitoring|파랑 · ICU 관찰
GREEN · Ward transfer day|초록 · 일반병동 전동일
YELLOW · Surgery reserved|노랑 · 수술 예약
GRAY · Available|회색 · 사용 가능
Select a cell to inspect its fictional patient journey.|칸을 선택하면 가상 환자의 입실·전동 경과를 볼 수 있습니다.
Care team discussion|진료팀 대화
Public NIH example chest X-ray; not this patient's image|공개 NIH 흉부 X선 예시 · 이 환자의 영상이 아닙니다
Patient context · original source and simulation|환자 맥락 · 원본 및 시뮬레이션 원문
Completed care · user entry|수행한 간호 · 사용자 입력
Care actually performed by the user|사용자가 실제 수행한 간호
Example: 14:40 Rechecked blood pressure and informed the physician|예: 14:40 혈압을 재측정하고 담당 의사에게 알림
Save record|기록 저장
Shift handover|근무 인계
Chat and AI suggestions are not automatically saved as completed care.|대화와 AI 제안은 수행한 간호로 자동 저장되지 않습니다.
Simulation activity|시뮬레이션 활동
Simulated dispatch, arrival and response events; not actual patient treatment records.|모의 호출·도착·대응 이벤트이며 실제 치료 기록이 아닙니다.
Live Qwen role-play|실시간 Qwen 역할 대화
Conversation participants|대화 참여자
2 people · Nurse + Patient|2인 · 간호사 + 환자
3 people · Nurse + Patient + Physician|3인 · 간호사 + 환자 + 의사
Nurse + Physician + AI|간호사 + 의사 + AI
Start new conversation|새 대화 시작
Chat with this CXR|이 흉부 X선으로 대화
Continue team discussion ▶|팀 대화 이어가기 ▶
Summarize as SBAR|SBAR로 요약
Close|닫기
Your discussion role|내 대화 역할
Patient (role-play)|환자 (역할극)
AI facilitator|AI 진행자
Ask the team about this patient…|이 환자에 대해 팀에 질문하세요…
Send|보내기
My view|내 담당 보기
High fatigue|높은 피로도
Break recommended|휴식 권장
Normal|정상
Critical|위급
Watch|주의
Stable|안정
Reserved|예약
Empty|빈 병상
CRITICAL|위급
BLEED?|출혈?
WATCH|주의
STABLE|안정
RESERVED|예약
EMPTY|빈 병상
SIMULATION|시뮬레이션
Suspected postoperative bleeding|수술 후 출혈 의심
Fictional bloody drainage + tachycardia + hypotension|가상의 혈성 배액 + 빈맥 + 저혈압
Click the patient for live Qwen role-play: nurse + patient, with an optional physician. These findings are not source-record observations.|환자를 클릭하면 간호사·환자·의사의 실시간 Qwen 역할 대화를 엽니다. 소견은 원본 기록의 관측값이 아닙니다.
Review patient & discuss|환자 확인 및 대화
Fictional postoperative monitoring case|가상의 수술 후 관찰 환자
Within-ICU calls only|같은 ICU 내 호출만 가능
Called → en route|호출됨 → 이동 중
At bedside · responding|병상 도착 · 대응 중
On break|휴식 중
Diagnostic task|검사 업무
Assigned care · callable|담당 간호 중 · 호출 가능
Standby · available for call|대기 중 · 호출 가능
Awaiting call|호출 대기
Arrived / responding|도착 · 대응 중
Called / en route|호출됨 · 이동 중
No physician call information|의사 호출 정보 없음
At alert onset|알림 발생 당시
Nurses needed|필요 간호사
Shortage|부족
Elapsed|경과
No assigned patients|담당 환자 없음
Empty bed|빈 병상
Assigned (on break)|담당 (휴식 중)
Assigned|담당
Coverage|지원
Dispatched|호출됨
Responding to event|이벤트 대응 중
En route to event|이벤트로 이동 중
Providing care|간호 수행 중
Elevator/corridor|엘리베이터·복도
Station|스테이션
Break room|휴게실
Moving|이동 중
Break|휴식
Staffing slot|근무 자리
Current location|현재 위치
Work this shift|이번 근무 업무량
My fatigue|내 피로도
Nurses in this ICU|이 ICU의 간호사
Charge nurse|책임 간호사
Bedside nurse|담당 간호사
Charge|책임
Next shift|다음 근무
Next|다음
Day|주간
Evening|오후
Night|야간
Shift|근무
No shift handover has been created yet.|아직 근무 인계가 생성되지 않았습니다.
A patient and assignment snapshot is created at each shift change, awaiting acknowledgement.|교대 시 환자·배치 현황을 저장하고 인수 확인을 기다립니다.
No unresolved events|미해결 이벤트 없음
No handover patients in this ICU|이 ICU의 인계 환자 없음
No user-entered care records|사용자가 입력한 간호 기록 없음
No simulation activity|시뮬레이션 활동 없음
No user-entered care records saved for this patient.|이 환자에게 저장된 사용자 간호 기록이 없습니다.
Awaiting acknowledgement|인수 확인 대기
Handover acknowledged|인수 확인 완료
Question saved · awaiting reply|질문 저장됨 · 답변 대기
Acknowledge handover|인수 확인
AI consultation on current records|현재 기록으로 AI 상담
Question for the handover record|인계 기록에 남길 질문
Save question|질문 저장
Questions are saved in the handover record. No message is sent to the previous nurse.|질문은 인계 기록에만 저장됩니다. 이전 간호사에게 메시지를 보내지 않습니다.
Only the currently assigned receiving nurse can acknowledge or save questions.|현재 배정된 인수 간호사만 확인하거나 질문을 저장할 수 있습니다.
Outgoing nurse|인계 간호사
Incoming nurse|인수 간호사
User-entered question|사용자 입력 질문
Cardiac arrest events|심정지 이벤트 수
First arrest response (min)|심정지 첫 대응 시간 (분)
Arrest team of three (min)|심정지 3인 대응팀 도착 (분)
Deterioration events|악화 이벤트 수
First deterioration response (min)|악화 첫 대응 시간 (분)
One-to-one care events|1:1 간호 이벤트 수
Unattended time (patient-min)|간호 공백 (환자·분)
High-risk unattended time (min)|고위험 환자 간호 공백 (분)
Workload standard deviation by slot (min)|근무 자리별 업무량 표준편차 (분)
Peak fatigue|최대 피로도
Mean fatigue at evaluation|평가 시점 평균 피로도
Fatigue ≥75 (nurse-min)|피로도 ≥75 (간호사·분)
Blood draw|채혈
Portable X-ray|이동식 X선
Requested|요청됨
Nurse en route|간호사 이동 중
Simulated specimen collection|모의 검체 채취
Simulated specimen delivery complete|모의 검체 전달 완료
Simulated imaging preparation|모의 촬영 준비
Simulated image acquisition|모의 영상 촬영
Public example image available|공개 예시 영상 사용 가능
Cancelled|취소됨
Simulation report|시뮬레이션 보고
Demo workload index|모의 업무량 지수
Simulated care duration|모의 간호 시간
One-to-one care active|1:1 간호 진행 중
Source replay observations|원본 기록 재생 관측값
Mechanical ventilation|인공호흡기
Vasopressor|승압제
Linked nurses|연결된 간호사
Open live role-play|실시간 역할 대화 열기
Call standby nurse (simulation)|대기 간호사 호출 (모의)
Emergency simulation|응급상황 시뮬레이션
Injects simulated events and observations. Does not alter source patient records.|모의 이벤트와 관측값을 추가합니다. 원본 환자 기록은 변경하지 않습니다.
Code blue|심정지
Hypoxia|저산소증
Hypotension|저혈압
qSOFA reference|qSOFA 참고 계산
Incomplete|미완성
Missing|누락
not scored|점수 미산정
Original qSOFA criteria|원본 qSOFA 기준
AgentMD method reference|AgentMD 방법 참고
Thinking…|생각 중…
Patient|환자
Nurse|간호사
Physician|의사
AI assistant|AI 보조자
Participant|참여자
Your message|내 메시지
Simulated role|가상 역할
Model output|모델 응답
Model unavailable|모델 연결 불가
Scripted simulation · no live model|미리 작성된 시뮬레이션 · 실시간 모델 아님
Rule-based output|규칙 기반 응답
CXR vision|흉부 X선 영상 분석
Arrived|도착
Response ended|대응 종료
Coverage started|지원 시작
Author|작성자
Unassigned|미배정
User entry|사용자 입력
Saving record…|기록 저장 중…
User-entered care record saved.|사용자 간호 기록이 저장되었습니다.
Enter the care you performed.|수행한 간호 내용을 입력하세요.
Not saved. Your input has been retained.|저장되지 않았습니다. 입력 내용은 유지됩니다.
Request could not be completed.|요청을 완료하지 못했습니다.
Wait for the current consultation or save to finish before opening another.|현재 대화 또는 저장이 끝난 후 다른 환자를 열어 주세요.
The shift scenario changed. Start a new conversation.|근무 시나리오가 바뀌었습니다. 새 대화를 시작하세요.
The clinical scenario changed. Start a new conversation.|환자 상황이 바뀌었습니다. 새 대화를 시작하세요.
The patient in this bed changed. Close and reopen the consultation.|병상의 환자가 바뀌었습니다. 대화창을 닫고 다시 열어 주세요.
The shift and author changed. Reopen the consultation as the current nurse.|근무와 작성자가 바뀌었습니다. 현재 간호사로 대화를 다시 열어 주세요.
Patient data|환자 데이터
Synthetic|가상 데이터
Scenario|시나리오
Simulation|시뮬레이션
Simulated|모의
None|없음
Waiting|대기
Planned admissions|입실 예정
Admitted|입실
Waiting on day 30|30일차 대기
Cumulative waiting|누적 대기
patient-days (simulation)|환자·일 (시뮬레이션)
Day / date|일차 · 날짜
Bed|병상
Available|사용 가능
Ward transfer|일반병동 전동
Surgery scheduled · postoperative ICU admission|수술 예정 · 수술 후 ICU 입실
Fictional schedule; patient not yet admitted.|가상 일정이며 아직 입실하지 않았습니다.
Six stable patients, one planned postoperative admission and one available bed per ICU. Initial nurse fatigue: 10/100 (assumed).|ICU마다 안정 환자 6명, 수술 후 입실 예정 1명, 빈 병상 1개입니다. 시작 피로도는 10/100으로 가정합니다.
One fictional postoperative bleeding case in SICU, a watch-level patient, and reserved / available beds. Initial nurse fatigue: 20/100 (assumed).|SICU의 가상 수술 후 출혈 의심 환자 1명과 주의 환자, 예약·빈 병상을 배치했습니다. 시작 피로도는 20/100으로 가정합니다.
Seven occupied beds per ICU, simultaneous emergencies and a reserved admission. Initial nurse fatigue: 70/100 (assumed); workload and response delays then evolve in the simulator.|ICU마다 환자 7명, 동시 응급상황과 입실 예약이 있습니다. 시작 피로도는 70/100으로 가정하며 업무량과 대응 지연은 시뮬레이션에 따라 변합니다.
Hospital network|병원 네트워크
Hospital|병원
Ward|병동
All wards in this hospital|이 병원의 전체 병동
Demo Hospital A|가상 병원 A
Demo Hospital B|가상 병원 B
Demo Hospital C|가상 병원 C
Shared ICU availability · ambulance planning|공유 ICU 수용 현황 · 구급 이송 계획
Fictional hospitals only. Empty beds are not confirmed acceptance. Staff and equipment readiness require hospital confirmation.|가상 병원 시뮬레이션입니다. 빈 병상은 수용 확정이 아니며, 인력·장비 준비는 해당 병원의 확인이 필요합니다.
View hospital|병원 보기
View ward|병동 보기
Beds|병상
Occupied|사용 중
Active events|진행 이벤트
On-duty nurses|근무 간호사
Available beds|빈 병상
Reserved beds|예약 병상
Acceptance unconfirmed|수용 미확정
No empty beds|빈 병상 없음
Hospital response pending (simulation)|병원 응답 대기 (모의)
Request acceptance (simulation)|수용 확인 요청 (모의)
Simulated requests only; no hospital has been contacted and no patient has been assigned.|모의 요청입니다. 실제 병원에 연락하거나 환자를 배정하지 않았습니다.
Patients · findings and devices|환자 · 소견 및 장비
Active / not active / unknown. Device states below are fictional fixtures, not verified K-MIMIC patient device records.|활성 / 비활성 / 미확인. 아래 장비 상태는 가상 설정이며 실제 K-MIMIC 환자의 장비 기록이 아닙니다.
Bleeding suspected|출혈 의심
Low blood pressure|저혈압
Fast heart rate|빈맥
Low oxygen|저산소
Fast breathing|빈호흡
Altered consciousness|의식 저하
Pain|통증
Fever|발열
Ventilator|인공호흡기
Oxygen|산소 공급
IV cannula|말초정맥관
Central line|중심정맥관
Arterial line|동맥관
Urinary catheter|유치도뇨관
Drain|배액관
Unknown|미확인
Active|활성
Not active|비활성
Snapshot|현재 현황
Scope|조회 범위
Whole-network metrics|전체 네트워크 지표
Scoped simulation records|현재 조회 범위의 시뮬레이션 기록
`.trim().split('\n').map(line => {const i=line.indexOf('|');return [line.slice(0,i),line.slice(i+1)];}));
  // Longest phrases first, bounded so identifiers (e.g. SIM-SICU-01) stay intact.
  const escaped = Object.keys(dictionary).sort((a,b)=>b.length-a.length).map(s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'));
  const pattern = new RegExp('(?<![A-Za-z0-9_-])(?:'+escaped.join('|')+')(?![A-Za-z0-9_-])','g');
  let language='ko';
  try {language=new URLSearchParams(location.search).get('lang')||localStorage.getItem('icu.language')||'ko';} catch {}
  if(!['ko','en'].includes(language))language='ko';
  const originals=new WeakMap(), attributes=new WeakMap();
  const ignored='script,style,textarea,[data-no-translate],#languageSwitch';
  function t(text){return language==='en'?text:String(text).replace(pattern,match=>dictionary[match]);}
  function text(node){
    if(node.parentElement?.closest(ignored))return;
    const previous=originals.get(node);
    const source=previous&&node.nodeValue===previous.rendered?previous.source:node.nodeValue;
    const rendered=t(source); originals.set(node,{source,rendered});
    if(node.nodeValue!==rendered)node.nodeValue=rendered;
  }
  function element(node){
    if(node.closest('script,style,[data-no-translate],#languageSwitch'))return;
    let saved=attributes.get(node)||{};
    for(const key of ['title','aria-label','placeholder','alt']){
      const current=node.getAttribute(key);if(current===null)continue;
      const previous=saved[key],source=previous&&current===previous.rendered?previous.source:current,rendered=t(source);
      saved[key]={source,rendered};if(current!==rendered)node.setAttribute(key,rendered);
    }
    attributes.set(node,saved);
  }
  function apply(root=document.body){
    if(root.nodeType===3){text(root);return;}
    if(root.nodeType!==1)return;
    element(root);
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT);
    while(walker.nextNode()){const n=walker.currentNode;n.nodeType===3?text(n):element(n);}
  }
  const observer=new MutationObserver(records=>{
    observer.disconnect();
    for(const r of records){if(r.type==='childList')r.addedNodes.forEach(apply);else apply(r.target);}
    observe();
  });
  function observe(){observer.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['title','aria-label','placeholder','alt']});}
  function set(next){
    if(!['ko','en'].includes(next))return;
    language=next;try{localStorage.setItem('icu.language',language);}catch{}
    const url=new URL(location);url.searchParams.set('lang',language);history.replaceState(null,'',url);
    document.documentElement.lang=language;
    document.title=language==='ko'?'외과계 ICU · 병원 네트워크':'Surgical ICU · Hospital Network';
    document.querySelectorAll('[data-language]').forEach(button=>{button.classList.toggle('on',button.dataset.language===language);button.setAttribute('aria-pressed',String(button.dataset.language===language));});
    observer.disconnect();apply();observe();document.dispatchEvent(new Event("icu-language"));
  }
  function init(){document.querySelectorAll('[data-language]').forEach(b=>b.onclick=()=>set(b.dataset.language));set(language);}
  return {init,set,t,apply,get language(){return language;}};
})();
