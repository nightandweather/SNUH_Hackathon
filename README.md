# SNUH Hackathon — ICU 상황판과 병상 계획

환자 상태 변화를 지속적으로 반영해 ICU 필요도와 병상 예약 시점을 최적화하는 Agentic AI 시스템을 위한 시연·연구 코드입니다.

## 지금 보던 ICU 상황판 실행

2026-10-16에 기존 로컬 상황판의 최신 소스를 `icu-board/`에 추가했습니다. Python 3.10 이상만 있으면 실행하며 pip·npm 설치가 필요 없습니다.

GitHub에서 저장소를 내려받거나 clone한 뒤 저장소 폴더에서 실행하세요.

```bash
cd icu-board
POOL=synth OFFLINE_DEMO=1 PLANNER_MODE=offline HOST=127.0.0.1 PORT=8002 python3 server.py
```

Windows PowerShell에서는 다음처럼 환경변수를 설정합니다.

```powershell
cd icu-board
$env:POOL='synth'
$env:OFFLINE_DEMO='1'
$env:PLANNER_MODE='offline'
$env:HOST='127.0.0.1'
$env:PORT='8002'
python server.py
```

macOS에서는 저장소 최상위의 `start-pod-demo.command`를 열거나 `/bin/zsh ./start-pod-demo.command`로 실행할 수 있습니다. 서버를 켠 터미널은 열어 두세요. 종료는 `Ctrl+C`입니다.

| 주소 | 화면 |
|---|---|
| http://127.0.0.1:8002/ | 전체 ICU 상황판: 8개 ICU·64병상, D/E/N 3교대·직원 이동·응급 및 검사 시연 |
| http://127.0.0.1:8002/nurse | 간호사 로그인: 담당자·책임 간호사·수간호사별 조회 범위와 수행 기록·인계 |
| http://127.0.0.1:8002/planning | 합성 환자 8명·ICU 3병상의 별도 예약 시연: 제안·충돌·승인 차단·재계획·사람 승인 |

간호사 시연 계정은 `D-MICU-1`, 수간호사는 `HN01`, 공통 시연 PIN은 `2026`입니다. 일반 계정은 현재 근무조와 담당 범위에 따라 환자가 표시됩니다. 이 PIN은 실제 병원 인증용이 아닙니다.

예약 시연의 환자는 전체 상황판의 환자와 연결되지 않습니다. 기본 실행은 합성 자료와 규칙 계산을 사용합니다. 실제 Qwen/GLM 호출, K-MIMIC 연결, 치료 결과 예측과 디지털 트윈의 임상 타당성을 검증한 제품은 아닙니다. 실제 모델 설정·점검과 코드 반입 허용 여부는 [Pod 사용방법](icu-board/POD_사용방법.md)을 확인하세요.

## 업데이트와 검증

clone한 저장소에서 `git pull --ff-only`로 갱신한 뒤, 기존 서버 터미널에서 `Ctrl+C`로 종료하고 위 명령으로 다시 실행하세요. 브라우저도 새로고침하세요. GitHub 소스 갱신만으로 이미 실행 중인 로컬 Python 프로세스가 바뀌지는 않습니다. 이 저장소 자체가 실행 중인 웹 서비스를 제공하는 것은 아닙니다.

```bash
cd icu-board
OFFLINE_DEMO=1 PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -q
python3 pod_check.py --offline
python3 build_pod_package.py
python3 verification/verify_pod_package.py
```

마지막 두 명령은 저장소 최상위에 `icu-pod-ready.zip`을 만들고, 별도 임시 폴더에서 압축 해제·해시·단위 테스트·HTTP 검증을 수행합니다. 환자 캐시·실제 API 키·다운로드한 영상은 GitHub 소스와 이 ZIP에 포함하지 않습니다. 서버를 재시작하거나 시나리오를 초기화하면 ICU 상황판의 메모리 기록이 초기화됩니다.

자세한 기능과 제한은 [ICU README](icu-board/README.md), [전체 사용방법](icu-board/사용방법.md)에 있습니다. `verification/`의 기존 JSON은 각 시점의 점검 기록이며 실제 모델·Pod 검증을 대신하지 않습니다. 일부 JavaScript 브라우저 점검 스크립트에는 작성 당시 Mac 환경의 경로가 들어 있어 실행 환경에 맞게 설정해야 합니다.

## 기존 PeriCare 작업

`SCH-YcHan/pericare-prototype/`는 기존 PeriCare 작업이며 ICU 상황판과 별도 앱입니다. 실행·데이터 연결·INSPIRE ICU24 모델 안내는 [PeriCare README](SCH-YcHan/pericare-prototype/README.md)를 확인하세요. 기존 소스와 모델 연동 코드는 유지했습니다.
