# ICU 간호 배치 상황판 — 3교대·수행 기록·응급 시연

층별 ICU 8개 병동(가정 배치)에 공개 MIMIC 기록과 소아·신생아 합성 경과를 넣어 가상 병원을 돌리고, 간호사 위치와 호출을 실시간으로 보여준다.
외부 라이브러리 없이 Python 표준 라이브러리만 사용 (KHDP Pod 오프라인 대비).

처음 사용하는 경우 [사용방법.md](사용방법.md)를 먼저 읽는다. Google Drive의 `icu-board-demo.zip`을 내려받아 풀면 실행 파일과 `icu-board` 폴더가 함께 나온다. macOS에서는 실행 파일을 열거나 압축을 푼 폴더에서 `/bin/zsh ./start-original-icu.command`를 실행한다. 전체 상황판은 8000번, 별도 로그인 데모는 8001번 포트를 사용한다.

## 이번 확장본

원본 전체 평면도를 유지한 수정본이다. `/Users/iganghun/kcd-2026/app`의 원본과 별도 `ward-app` 로그인 데모에는 자동 반영되지 않는다. 이미 실행한 원본 터미널을 Ctrl+C로 종료하고, 상위 폴더의 `start-original-icu.command`를 다시 실행하면 이 폴더의 수정본이 열린다. 기본 주소는 `http://127.0.0.1:8000/`이며 서버 기본 바인딩은 이 컴퓨터 내부이다.

- D 07–15시, E 15–23시, N 23–07시: 조별 40명, 전체 120명을 구분한다. 지도에는 현재 근무 40명이 보인다. 시간표는 `units.json`에 있다.
- 교대 15분 전 인계 준비 표시, 이전 조의 업무·피로도 보존, 현재 환자 상태와 진행 사건의 다음 조 인계. `다음 교대까지`는 분마다 시뮬레이션을 진행한 뒤 일시정지한다. 최대 24시간이다.
- 자동 배정·대신 보기·사건 출동은 같은 ICU에 한정한다. 다른 ICU 일반 간호사를 자동 호출하지 않는다. 현재 자동 배정은 병동 안에서 거리·업무 부담·피로도를 고려하는 비교이다.
- 상담창 `수행 기록`에 직접 입력해 저장한 내용만 수행 이력으로 남긴다. 환자와 입원 회차, 기록 시각, D/E/N 실제 직원 ID를 함께 저장한다. 이는 사용자의 수행 보고이며 행위를 독립적으로 검증한 기록은 아니다.
- `근무 인계` 버튼이나 “내가 여태 뭘 했는지 인계해줘”로 내 이번 근무 기록·이전 조/동료 기록·현재 상태·미해결 사건을 확인한다. 채팅 대화나 AI 권고는 수행 기록에 자동 저장되지 않는다.
- 가상 간호사가 시뮬레이션에서 출동·도착·대응 종료·대신 보기를 실행한 활동은 별도 활동 기록으로 남는다. 사용자 입력 수행 보고와 구분하고 실제 환자 처치 완료의 증거로 사용하지 않는다.
- 환자 또는 근무조가 상담 중 바뀌면 기존 입력을 새 환자·새 직원에게 붙이지 않고 다시 선택하도록 안내한다.
- 병상을 선택해 코드블루·저산소증·저혈압 시연을 주입할 수 있다. 원본 재생 활력과 시연 활력을 분리하고, 시연 종료 후 원본 재생 상태로 돌아간다. 사건 생성 자체는 간호사 수행 이력이 아니다.
- MD는 ICU마다 1명인 별도 시연 인원이다. 호출·이동·도착 상태를 보여주며, 간호사 3교대와 동일한 의사 근무표를 가정하지 않는다. MD 인원, 출동 인원, 시연 활력과 사건 지속시간은 실제 병원 운영 기준이나 검증된 치료 효과가 아니다. 부족한 간호 인원이나 바쁜 MD는 대기로 표시된다.
- 기록과 인계는 현재 시나리오의 서버 메모리에 보존된다. 새 시나리오나 서버 재시작 시 초기화된다.
- 순회 시작과 휴식 확인은 개인·ICU별로 시간차를 둔다. 순회 첫 출발은 1–15분, 이후 10–20분, 고정 휴식은 예정 시각에서 ±10분이다. 환자가 있는 담당·대신 보기 병상만 순회한다. 응급 호출에는 이 시간차를 적용하지 않는다.
- 환자 상세에서 현재 HR·MAP·SpO₂·RR와 최근 2시간 추세를 확인한다. 추세는 현재 입원 회차에서 시뮬레이터가 이미 관찰한 재생값이다. 결측값·원자료 값 유지와 응급 시연 주입을 구분하며 미래 경과를 미리 공개하지 않는다.
- `채혈 시연`은 간호사 이동·채취·검체 이송을, `포터블 X-ray 시연`은 준비·호출·촬영·예시 영상 표시를 진행한다. 응급 출동을 우선하고 미완료 업무는 교대 인계에 남는다. 검사 수치나 실제 환자 촬영 결과를 생성하지 않는다.
- 촬영 시연 완료 후 `VL 영상 검토`로 공개 NIH 예시 영상을 실제 연결된 비전 모델에 전송할 수 있다. 해당 환자의 영상이 아니며 출력은 의사 확인 전 초안이다. 모델 호출 실패는 `영상 검토 미실행`으로 표시하고 판독 소견을 대신 만들어내지 않는다.
- 교대 자동 진행은 인계 자료 생성 단계다. 다음 담당자 역할로 `인계 확인`하거나 질문을 저장하면 수신 상태가 별도로 남는다. 질문 저장은 이전 근무자에게 실제 메시지를 전송하는 기능이 아니다.

### 응급실 전입과 사망의 범위

EICU는 이 지도에서 응급 ICU로 설정한 병동이다. 응급실 접수·분류·초기 진료에서 ICU로 전입하는 별도 경과는 구현되어 있지 않다. 심정지 사건의 시연 타이머 종료를 사망이나 소생의 확인으로 사용하지 않는다. 테이블 데스 등 시술 중 사망, 사망 확인·시각·가족 연락·사후 업무도 현재 모델의 사건이나 결과 항목에 포함되어 있지 않다.

### 인계 확인

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -q
python3 verify_handover.py --output verification/handover-offline.json
node verification/ui-check.cjs
PYTHONDONTWRITEBYTECODE=1 python3 verification/verify_workflows.py
```

기본 검증은 모델 없이 저장 기록과 현재 상태를 사용하는 경로이다. 모델 연결 후 실제 응답을 확인할 때는 `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`를 Pod 내부 모델에 맞게 설정하고 `python3 verify_handover.py --model`을 실행한다. 모델이 실패해서 기록 기반 응답으로 돌아오면 `--model` 검증은 통과로 표시하지 않는다.

UI 검증은 브라우저를 띄우지 않는 JavaScript VM·간이 DOM 검사이다. 실제 화면 렌더링과 HTTP 통합 검증은 포함하지 않는다.

인계의 확정 기록은 코드가 시각·수행자·기록 내용과 함께 표시한다. LLM 출력은 별도의 `AI 검토 항목 초안`으로 표시한다. 실제 GLM 호출은 아직 이 확장본에서 검증되지 않았다.

### 환자별 디지털 트윈의 다음 단계

현재는 기록 재생과 운영 시뮬레이션이다. 환자마다 독립된 상태·처치 이력·기억을 두고 공통 GLM/Qwen 모델에 각 환자의 문맥을 전달하는 방식으로 확장할 수 있다. 모델 클라이언트와 에이전트별 문맥을 분리하는 [Microsoft AutoGen의 공식 예시](https://microsoft.github.io/autogen/dev/user-guide/core-user-guide/components/model-context.html)를 참고한 설계이며 환자마다 모델 가중치 전체를 따로 올릴 필요는 없다. 다른 치료를 선택했을 때의 경과·성공률을 보여주려면 별도의 치료 조건부 상태 예측과 평가가 필요하다. 관찰 의료 데이터에서 치료 정책의 평가에는 [교란과 평가 편향 문제가 있다](https://arxiv.org/abs/1805.12298). 현재 기능은 치료 반응이나 강화학습 정책의 효과를 입증하지 않는다.

## 설치

### 방법 1. Python으로 바로 (가장 간단)
1. Python 3.10 이상 설치 확인: 터미널(윈도우는 PowerShell)에서 `python3 --version`
   - 없으면 https://www.python.org/downloads/ 에서 설치 (윈도우는 설치 때 "Add python.exe to PATH" 체크, 명령은 `python`)
2. 이 폴더를 통째로 내려받기 (드라이브에서 폴더 우클릭 → 다운로드 → zip 압축 풀기)
3. 터미널에서 폴더로 이동 후 실행
   ```bash
   cd icu-board
   python3 server.py
   ```
4. 브라우저에서 http://localhost:8000
   - 제공 ZIP에는 공개 MIMIC-IV demo에서 만든 환자 재생 자료와 공개 예시 영상이 포함되어 있다. 환자 재생 자료가 없으면 첫 실행 때 공개 데모를 내려받아 만든다.
   - 인터넷이 안 되면 가상 환자로 실행됨
   - 종료는 터미널에서 Ctrl+C

pip install 할 것 없음 (표준 라이브러리만 사용).

### 방법 2. Docker
1. Docker Desktop 설치 후 실행: https://www.docker.com/products/docker-desktop/
2. 폴더에서
   ```bash
   docker build -t icu-board .
   docker run -e HOST=0.0.0.0 -p 127.0.0.1:8000:8000 icu-board
   ```
3. 브라우저에서 http://localhost:8000

### 다른 노트북에서 같이 보기
- 현재 기본 실행은 이 컴퓨터에서 보는 공개 데이터 시연이다. 다중 사용자 배포와 로그인은 별도 구성이다.
- 포트 변경이 필요한 배포에서는 `PORT` 환경변수를 명시한다.

## 사용 방법

### 화면 구성
- 왼쪽: 층별 평면도 (7층 위 → 4층 아래), 층마다 병동 2개와 가운데 엘리베이터(E/V)
- 네모 = 병상. 안의 숫자 = 위험지표(0~100)
  - 초록 <40, 노랑 40~69, 빨강 ≥70(집중관리 대상). 점선 네모 = 빈 병상
  - 깜빡이면 심정지·급격한 악화 발생, 빨간 테두리면 1:1 집중관리 중
- 동그라미 = 간호사. 안의 글자: C = 책임간호사(점선 테두리), 1~4 = 담당간호사
  - 파랑 = 자기 환자 간호, 주황 = 이동 중, 빨강 = 이벤트 대응, 보라 = 동료 환자 대신 봄, 회색 = 휴식
  - 둘레 고리 = 피로도
- 오른쪽: 진행 중인 이벤트, 클릭한 환자/간호사 정보, 지표, 기록(시각 · 몇 번 환자 알림 · 몇 번 간호사 출동)

### 상단 버튼
- 일시정지/재생, 속도(1초에 1·2·5·15·30분 진행)
- 기존 2:1 고정 / 자동 배치: 누르면 그 방식으로 처음부터 다시 시작
- 새 시나리오: 다른 환자 조합으로 다시 시작
- "병동 전체 화면" 선택 칸: 간호사를 고르면 그 간호사의 개인 화면

### 두 가지 화면
- 병동 전체 화면 (책임간호사·관리자용)
  - 모든 층·병동의 환자와 간호사 위치를 한 번에 봄
  - 병상을 누르면 그 환자와 연결된 간호사(담당 / 대신 봄 / 출동)까지 점선이 이어지고, 각 간호사가 지금 어디서 뭘 하는지 표시 (예: "6층 CCU-03 옆 · 간호 중")
  - 간호사 동그라미를 누르면 위치, 담당 환자, 대신 보는 환자, 누적 업무, 피로도
- 개인 화면 (간호사 본인용)
  - 오른쪽 위 "내 화면": 내 위치, 내 피로도, 내 환자 목록(위험지표, 진단, 활력징후), 대신 보는 환자
  - 평면도에서 내 환자만 진하게, 나와 내 환자 사이에 점선
  - 호출되면 맨 위 배너: "○○ 병상으로 이동하세요" / "동료 대신 ○○ 환자를 봐주세요"
  - 책임간호사(C)를 고르면 자기 병동 환자 전체가 목록에 뜸
  - 주소 뒤에 `?nurse=MICU-1`처럼 붙여도 됨 → 노트북·휴대폰마다 다른 간호사로 열어둘 수 있음

### 피로도
- 간호사마다 피로도 0~100. 담당 환자 중증도(간호 부담), 이벤트 대응(심정지 > 급격한 악화 > 1:1 집중관리), 이동으로 오르고, 휴식 때 내려감
  - 근무 8시간 동안 경증 2명이면 30 안팎, 중증 2명이면 60 안팎, 이벤트가 겹치면 75 이상
- 간호사 동그라미 둘레 고리가 피로도 (초록 <60 양호 · 노랑 60~74 휴식 권고 · 빨강 ≥75 과로), 회색 동그라미 = 휴식 중(스테이션 옆 휴게실)
- 오른쪽 "피로도 높은 간호사"에 상위 6명. 책임간호사 개인 화면에는 자기 병동 간호사 피로도 목록
- 휴식 방식
  - 기존 2:1 고정: 근무 시작 5시간·5시간 반·6시간·6시간 반 뒤를 기준으로 개인별 ±10분 차이를 두고 30분 휴식한다. 같은 ICU 짝꿍(1↔2, 3↔4)이 가능할 때 시작하며, 바쁘면 재시도한다.
  - 자동 배치: ICU별 첫 확인 1–15분, 이후 10–20분마다 병동이 조용하고 남는 인원이 3명 이상이면 가장 지친 사람부터 30분 휴식한다. 피로도 60 이상이거나 근무 6시간 동안 못 쉰 사람이 대상이며 부담 적은 동료가 대신 본다.
  - 자동 배치는 이벤트 출동·대신 보기·신규 입실 배정 때 피로도가 높은 간호사를 덜 부름 (피로도 40 ≈ 1분 거리만큼 불리)
- D/E/N 교대 때 다른 직원이 역할을 이어받고, 이전 조의 통계와 환자 인계를 보존한다.
- 지표: 누적 최고 피로도·과로 시간, 현재 조 평균 피로도와 직전 완료 조 평균을 구분한다.

### AI 상담과 촬영 후 영상 검토
- 병상을 누르고 `AI 상담` → 상담 창
  - 왼쪽: 공개 예시 흉부 X-ray와 예시 영상 소견, AI에게 들어가는 환자 데이터(진단, 기계환기·승압제, 위험지표, 최근 2시간 활력징후, 담당 간호사). 예시 영상과 소견은 해당 환자의 검사 결과가 아니다.
  - 오른쪽: 대화. 파란 말풍선 = 간호사, 회색 = AI 에이전트
- 간호사 역할
  - 처음에는 간호사 역할 AI가 자동으로 질문 → AI 에이전트가 답
  - "자동 대화 ▶": 간호사↔에이전트 3번 더 주고받음 (뭘 먼저 볼지 → X-ray·처치와 연결 → 노티 기준 → 다음 1시간 관찰 계획 순서)
  - 아래 입력창에 직접 치면 그때부터 사람이 간호사 (말풍선에 "간호사 (사람)" 표시)
  - "SBAR로 정리": 담당의 보고용 S/B/A/R 네 줄
- 간호사 개인 화면에서 호출되면 배너에 "AI 브리핑" 버튼 → 그 환자 상담이 "가는 중인데 뭐부터 봐요?"로 시작
- 주소로 바로 열기: `http://<IP>:8000/?consult=MICU-01`
- 일반 상담과 SBAR는 텍스트 맥락만 사용한다. 영상 전송은 환자 상세의 포터블 촬영 시연이 완료된 뒤 별도 `VL 영상 검토`에서 수행한다. 공개 예시 영상의 기존 소견 라벨을 모델이 새로 발견한 소견으로 표시하지 않는다.
- AI 에이전트 규칙(프롬프트, `consult.py`): 판단에 쓴 수치·시각을 짚음, 확정 진단·처방 금지, 모르는 건 모른다고, 담당의 보고 기준 제시
- X-ray는 공개 NIH ChestX-ray14 예시 영상(15장, 첫 실행 때 자동 다운로드). 이 환자 영상이 아니고, 진단명에 맞는 소견을 골라 붙인 것. 화면에 그렇게 표시됨

#### 모델 연결
- OpenAI 호환 API면 무엇이든: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` 환경변수
  - 기본값 `http://127.0.0.1:8091/v1` (로컬 Qwen)
  - 대회 Pod: `LLM_BASE_URL=<KHDP.ai 주소> LLM_MODEL=<Qwen 또는 GLM 비전 모델> LLM_API_KEY=... python3 server.py`
- 맥(Apple Silicon)에서 로컬 Qwen3-VL: 새 터미널에서 `./run_qwen_local.sh` (8B) 또는 `./run_qwen_local.sh 30b` (30B-A3B). 처음에는 모델 다운로드가 필요하며 메모리 사용량과 속도는 모델·양자화·환경에 따라 다르다.
  - 그다음 다른 터미널에서 `python3 server.py`
- 모델이 없으면 규칙 기반 문장으로 답함 (상담 창 위에 "모델 연결 없음" 표시). 다른 노트북은 모델 없이도 화면은 다 돌아감
- 전용 VL 영상 검토는 실제 이미지 입력을 지원하는 모델이 필요하다. 모델이 없거나 응답에 실패하면 `unavailable`로 남기며 규칙으로 영상 소견을 대체하지 않는다.
- Docker에서 맥의 로컬 Qwen을 쓰려면 기본값(`host.docker.internal:8091`) 그대로

#### 실제 검사·영상 연결

현재 어댑터는 MIMIC-IV 활력 기록을 재생하며 `labevents`와 MIMIC-CXR는 연결되어 있지 않다. [MIMIC-IV labevents](https://mimic.mit.edu/docs/iv/modules/hosp/labevents.html)의 `charttime`과 `storetime`을 구분해 검체 채취와 결과 공개를 시간 순서대로 처리해야 한다. [MIMIC-CXR-JPG](https://physionet.org/content/mimic-cxr-jpg/2.1.0/)는 별도 접근 승인이 필요한 자료이며 `subject_id`, `study_id`, `dicom_id`와 촬영 시각을 가진다. 영상의 환자 ID와 입원 시간창을 대조해야 하며 현재 풀의 `M-stay_id`만으로 영상이 자동 연결되지는 않는다.

### 기본 사용 순서
1. 접속하면 07:00 근무가 자동으로 시작됨 (자동 배치 방식)
2. 병상을 눌러 환자 정보 확인: 진단, 위험지표, 집중관리 예상 시간, HR·MAP·SpO₂·RR, 기계환기·승압제, 연결된 간호사
3. 기록 칸에서 "⚠ 급격한 악화 CCU-05 → CCU-C 출동 → ✓ 종료" 흐름 확인
4. 오른쪽 "같은 시나리오 8시간 비교"를 누르면 기존 2:1과 자동 배치를 같은 환자 조합으로 끝까지 돌린 결과가 표로 나옴
   - 돌봄 공백(환자·분): 담당 간호사가 자리를 비워 아무도 안 본 시간. 핵심 지표
   - 담당 자리별 누적 업무량 편차: 교대를 포함해 담당 자리마다 누적된 부담을 비교한다. 개인별 공정성 지표는 아니다.
   - 최고 피로도 / 피로도 75 이상 간호사·분: 과로가 생기는지

### 발표·시연 순서 (3분)
1. 속도 15분/초, "기존 2:1 고정"으로 시작 → 이벤트가 나면 담당 간호사만 뛰어가고 남은 환자는 비는 장면
2. "자동 배치"로 바꿈 → 위험지표가 70을 넘으면 담당 간호사는 1:1, 옆 동료가 보라색으로 바뀌며 남은 환자를 맡는 장면
3. 노트북 2~3대에서 각자 간호사 화면(`?nurse=SICU1-2` 등)을 띄워 호출 배너가 뜨는 것 보여주기
4. 피로도 고리와 "피로도 높은 간호사" 패널: 기존 방식은 한 사람에게 몰려 빨개지고, 자동 배치는 지친 사람을 쉬게 하는 장면
5. 환자 병상 → 바이탈 추세·채혈·포터블 X-ray 시연 확인 → 촬영 완료 후 공개 예시의 `VL 영상 검토` → 텍스트 `AI 상담`에서 질문·SBAR 정리 → 다음 교대에서 미완료 업무와 수신 확인.
6. "같은 시나리오 8시간 비교" 표로 마무리

## 실행 옵션
- `POOL=synth python3 server.py`: 가상 환자로만
- `POOL=mimic`: MIMIC-IV demo, `POOL=kmimic`: K-MIMIC (Pod)

## 환자 데이터
- MIMIC-IV demo (공개, 실제 환자 100명, https://physionet.org/content/mimic-iv-demo/2.2/): 첫 실행 때 자동. 수동은 `python3 mimic.py --fetch`.
  성인 ICU만 있어서 소아·신생아 ICU는 가상 환자로 채움.
- K-MIMIC (Pod 안에서만): `python3 kmimic.py --dir <K-MIMIC 폴더>` 후 `POOL=kmimic python3 server.py`.
  itemid는 병원별로 달라 `concepts.json`에 채워야 함 (지금은 001 병원만). 아직 실제 K-MIMIC으로 돌려보지 않음.
- 날짜는 환자별 shift라 입실 기준 상대 시간만 사용. 실제 동시 재원은 알 수 없어 가상 병동으로 구성.

## 동작
- 병동 8개 × 8병상, 병동당 간호사 5명(책임 1 + 담당 4, 담당 1명이 환자 2명).
- 환자는 무작위로 입실해 빈 병상에 자동 배치(만실이면 같은 종류/같은 층 병동으로 전동), 기록이 끝나면 퇴실.
- 이벤트: 심정지(HR<30 또는 MAP<30, 또는 CPR 기록), 급격한 악화(이상 활력 2회 연속), 위험지표 ≥70 → 집중관리 1:1.
- 정책
  - 기존 2:1 고정: 담당 간호사가 대응, 그동안 남은 환자는 공백. 심정지는 책임간호사 즉시 + 2분 뒤 같은 병동 합류.
  - 자동 배치: 같은 ICU에서 가장 가까운 비어있는 간호사를 배치, 자리 비운 간호사의 환자는 같은 ICU 동료가 대신 봄.
- "같은 시나리오 8시간 비교" 버튼: 같은 seed로 두 정책을 끝까지 돌려 지표 비교.

## 아직 자리표시인 것
- 위험지표: 나이·진단 수·기계환기·승압제·활력 추세 임시 공식 (`engine.Hospital._risk`). VitalDB/INSPIRE로 학습한 모델로 교체 예정.
- 피로도 계수: 임상 근거 없는 가정값 (`engine.py` 상단 FATIGUE_*). 간호사 의견으로 조정 필요. NASA-TLX 같은 자가보고나 근무표 데이터로 보정 가능.
- 층 배치·병상 수: `units.json` 가정값.
- AI 상담: 로컬 8B는 한국어 의학 용어가 가끔 어색함. KHDP.ai의 큰 Qwen/GLM이나 로컬 30B로 바꾸면 나아짐. 배치 결정은 LLM이 아니라 규칙 코드가 함.
- X-ray: 환자와 무관한 공개 예시 영상. Pod에서 SNUH CXR이나 MIMIC-CXR이 K-MIMIC/MIMIC-IV 환자와 연결되면 실제 영상으로 교체.

## 파일
engine.py 시뮬레이션 · server.py 웹 서버 · consult.py AI 상담·촬영 후 VL 검토 · handover.py 인계 수신·질문 기록 · run_qwen_local.sh 로컬 Qwen · static/index.html 상황판 · static/cxr/index.json 예시 X-ray 목록 · synth.py 가상 환자 · mimic.py / kmimic.py 데이터 어댑터 · units.json 병동 배치 · concepts.json K-MIMIC itemid


## K-MIMIC evidence replay (2026-10-16)

The KHDP server now has a separate English evidence view at `/proxy/8005/`. The local `:8002` staffing view still uses public MIMIC-IV replay, with a link to the actual K-MIMIC server view. Neither view runs AgentMD or Qwen inference.

- `build_surgical_replay.py` scans all ICUSTAYS partitions for exact SICU/TSICU admission-unit candidates; deduplicates within dataset + subject + admission + stay, excluding conflicting keys. Generic ICU codes and OP_FLAG are not used. Hospital unit definitions still need confirmation. Override KMIMIC_ROOT and KMIMIC_OUTPUT for synthetic testing; keep real row-level outputs in KHDP.
- Server output: `~/workspace/icu-runtime/kmimic-cohort/`. Candidate CSV is private (0600): 56,336 ICU stays across seven datasets; this is not a distinct-person count.
- The initial replay uses the first 48 eligible SICU stays in dataset 001, partition 268; 38 have sufficient mapped observations. This is a convenience sample, not a validated or representative cohort. There are 10,008 accepted first-day observations.
- ITEMIDs are explicitly mapped from D_ITEMS. VALUEUOM is checked; blank units use D_ITEMS.UNITNAME. No future fill; five-minute bins with at most 30-minute carry-forward. Gaps, unmapped GCS, diagnosis, ventilation and pressor status are not fabricated. Simultaneous values use the upper median; arterial/non-invasive BP distinctions are not modeled.
- `serve_surgical_replay.py` runs a copy of the existing simulation with only SICU beds on localhost:8005 behind the existing authenticated KHDP proxy. It uses `~/workspace/icu-runtime/kmimic-evidence.html` (local source: `kmimic_evidence.html`). Initial windows deliberately show complete observations and one observed alert if available; displayed alert counts are not prevalence estimates.
- `clinical_evidence.py` implements qSOFA reference components and explicit replay-threshold evidence in the local application. qSOFA is not an ICU emergency detector. Missing components produce a range and no total. GCS is unavailable in this K-MIMIC adapter, so qSOFA remains incomplete.
- AgentMD (https://doi.org/10.1038/s41467-025-64430-x) is cited for its calculator-selection/execution/interpretation approach. Original qSOFA criteria: https://doi.org/10.1001/jama.2016.0287. The 0–100 simulation workload heuristic and alert thresholds are not AgentMD formulas or validated mortality scores.
- Qwen is deferred; the K-MIMIC server rejects consult/image-review inference calls with 503. The legacy `kmimic.py` importer remains unvalidated and should not replace this audited extraction path.

Validation: existing app tests plus synthetic multi-partition, duplicate-key namespace, unit fallback/rejection, missing-value, future-data and stale-carry tests. Browser checks cover actual K-MIMIC loading, selection, replay and calculator evidence.


### K-MIMIC role discussion on KHDP (2026-10-16)

The server evidence board at `/proxy/8005/` opens a case discussion when an occupied patient row is clicked. Select **Speak as**, then **Start discussion** or submit a question. **Continue round** adds a round; **New snapshot** captures newer observations on the next submission.

`case_chat.py` calls the verified KHDP internal OpenAI-compatible gateway with `qwen3-8-flash-next-ax`. The PAT is read from the existing private `~/workspace/icu-runtime/khdp-api.json`; it is never sent to the browser. Thinking is disabled and JSON Schema constrains the response shape. Asynchronous jobs avoid the KHDP proxy request timeout. Failures display a message, never fabricated replacement replies.

One model simulates nurse, physician and evidence-agent turns. The patient role is an explicit record-limitation statement: the current extract has no documented patient speech or subjective symptoms. User-selected speaking roles are simulation perspectives, not verified clinician identities. Typed claims do not become recorded facts. This is not four independent agents and is not real patient/clinician communication.

The backend captures the selected stay under the simulation lock, reads the source series (not injected scenario values), applies measurement-age limits, and freezes the five available vital signs, qSOFA components, threshold evidence and source offset. Measurement timestamps are rendered deterministically in evidence tags; numeric times are omitted from model input to avoid confusing measurement age with admission offset. No raw source patient identifiers, unrelated CXR, invented diagnosis or treatment are included. Requests use only the KHDP internal model; raw source files remain on the Pod. Patient-linked CXR is still unavailable in this extract.

Conversations stay in server memory for 30 minutes, with six rounds per snapshot and at most two concurrent model requests. Resetting a replay or replacing a bed occupant invalidates its earlier session. Reloading the page or restarting the process does not restore conversations. Evidence tags are drawn from the frozen source; generated prose remains an unvalidated simulation and requires human review.

Deployment files: `case_chat.py` beside `serve_surgical_replay.py`, `case_chat.js` saved as `case-chat.js` on the Pod, and `kmimic_evidence.html` saved as `kmimic-evidence.html`. The page embeds the chat script inline because the KHDP proxy did not initialize the separately loaded script during testing.

### English surgical ICU role-play demo

Run `python3 run_surgical_demo.py` on port 8000. The launcher uses four surgical
ICUs with eight beds each and fully fictional training patients. These scenarios
are not K-MIMIC records. Choose Calm shift, Suspected bleeding, or Overloaded shift;
new scenarios start paused so the patient discussion can be reviewed before Play.
The initial fatigue values and workload thresholds are simulation assumptions.

Bed states: red = active emergency, amber = watch, green = routine monitoring,
purple = surgery scheduled / postoperative bed reserved, gray = available.
Reserved patients are admitted at simulated 09:00. Staff markers are spaced apart
for legibility; nurse and physician details retain their simulated locations.
Call standby nurse requests assistance within the patient's ICU, prioritizing a
free nurse without occupied assigned/covered beds. Play advances dispatch and arrival.

Click a patient to start actual Qwen role-play. Select Nurse + Patient (2 people),
Nurse + Patient + Physician (3 people), or Nurse + Physician + AI, then Start new
conversation. Patient statements are fictional role-play. The launcher reads the
existing private credential file outside the repository and calls the KHDP gateway
with qwen3-8-flash-next-ax. Failed live calls display an error instead of a scripted
substitute. No chat is automatically saved as completed treatment.

The 30-day bed-flow panel is a separate eight-bed planning sandbox inspired by the
provided reference sheet. Red denotes a fictional critical day, blue ICU monitoring,
green the planned ward-transfer day, yellow a next-day surgical reservation, and
gray an available bed. It does not reconstruct actual hospital occupancy: patient
IDs, dates, arrivals, lengths of stay and transfers are generated assumptions.
Daily scenario assumptions and waiting-patient-day totals are visible in the panel.

### Bilingual hospital network demo (2026-10-16)

The local surgical demo now has three explicitly fictional hospitals (A/B/C),
each with four surgical ICUs and eight beds per ICU. Initially A has suspected bleeding, B is calm, and C is overloaded. The
scenario selector applies to the currently selected hospital and preserves the
other hospital profiles. Starting/resetting scenarios resets the shared clock. No real hospital capacity feed or
ambulance dispatch is connected. An acceptance-request button demonstrates a
pending state only; it never confirms an admission or contacts a hospital.

One shared patient schema is used. Hospital identity is attached to units;
unit and bed IDs are unique across hospitals (e.g. `B-SICU-01`), as are synthetic
patient IDs. Hospital selection scopes to 32 beds and ward selection to eight;
staff, alerts, care records, diagnostics and handovers are scoped with them.
All-network comparison metrics are explicitly labelled and collapsed. No
separate patient database is created per hospital. These are in-memory demo
fixtures, not a production multi-hospital access-control system.

The header switches Korean/English without resetting patient selection, chat
history, or user drafts. The default is Korean; `?lang=en` and `?lang=ko` override
the saved preference. UI strings live in `static/i18n.js`. Original context,
saved notes and conversation bodies are preserved. New model responses use a
request-local language context, isolated across concurrent requests. Language
switching is disabled while a role-play sequence is being generated.

Patient cards expose eight illustrative finding flags and device fixtures.
Unknown is distinct from absent. These are simulation states, not verified
K-MIMIC device attachments or a validated triage score. Previously inspected
K-MIMIC D_ITEMS metadata includes ventilator On/Off, IV cannula, central-line
management, ECMO flow and drain output; dictionary availability alone does not
establish a particular patient's attached devices.

Validation: `python3 -m unittest discover -p 'test_*.py'`; pure UI scope tests:
`node test_network_ui.cjs /path/to/synthetic-api-state.json`.


The consultation now has a persistent full-width top bar with a 44px Close
button, Escape dismissal and keyboard focus handling. Closing an active LLM
conversation aborts the client request and prevents its late result from
modifying a newer conversation; an already-started backend inference may still
finish. Saved-care requests are not silently cancelled. Secondary discussion
actions are grouped in More actions. On narrow screens, Patient summary toggles
the context pane without hiding the Close button.

Simulation controls display the target hospital and applying/success/error
states, refresh immediately after changes, and reject stale polling results.
Control requests have timeouts, and polling failures are visible. Verification:
117 Python tests passed; browser-tested B-hospital overload/calm/bleeding,
play/speed/pause, and Escape cancellation with controls unlocked.


Five care indicators now use original SVG pictograms based on the supplied
reference: CPR today, ECMO/CRRT, pressor escalation/instability, ventilator, and
surgery today. Filled color means active, outline means explicitly inactive,
and a dashed question mark means unknown. Occupied cards show a patient/bed
outline; reserved and empty cards show an empty bed. The markers indicate care
needs, not a validated severity score. Existing findings remain text summaries.

All current indicator flags are fictional fixtures. CPR and surgery require
an explicit record for the current simulation calendar day; changing days
makes old daily flags unknown in both the UI and LLM context. Arrest, routine
pressor use, a postoperative diagnosis, or a planned admission alone do not
activate those flags. ECMO/CRRT is active when either is true and inactive only
when both are explicitly false. Surge scenario bed 05 demonstrates all five
active markers. Verification: 118 Python tests and pure JavaScript state tests
passed; Korean/English rendering and active/inactive/unknown icons checked in
the local browser.
