# ICU Compass — 외과 ICU 상황판 개발 기록

8병상·31일 시나리오와 K-MIMIC GS ICU 기록을 기존 병동 지도에 연결하는 연구용 프로토타입입니다. 병원 → ICU → 병상 → 환자 상세 순서로 탐색하고, 선택 시점의 활력징후·검사·장비 기록과 간호 지원 LLM을 함께 봅니다.

**이 저장소에는 코드와 합성 시연 자료만 포함합니다. 실제 환자 풀, 원본 EMR·DICOM·영상, 인증정보, 환자 화면 캡처는 포함하지 않습니다.**

## 먼저 볼 문서

- [개발 과정과 시행착오](docs/DEVELOPMENT_LOG.md)
- [현재 구현 범위와 남은 작업](docs/STATUS.md)
- [공개 시연 스냅샷](public-presentation/README.md)
- [KHDP 배포 구조](deployment/README.md)
- [이전 단계의 상세 기록](docs/LEGACY_README.md) — 당시 상태를 보존한 문서로, 현재 상태는 STATUS가 우선합니다.

## 빠른 실행

Python 3.10 이상에서 합성 시나리오 UI를 실행합니다.

```bash
python3 run_surgical_demo.py
# http://127.0.0.1:8000/
```

이 실행 경로는 가상 시나리오를 만듭니다. 시작 시 공개 예시 CXR 다운로드를 시도할 수 있습니다. LLM을 사용하려면 별도 비공개 설정이 필요하며, 인증정보가 없으면 실제 모델 응답은 제공되지 않습니다. 공개 시연만 보려면 네트워크/모델 호출이 없는 정적 스냅샷을 실행합니다.

```bash
python3 -m http.server 8080 --bind 127.0.0.1 --directory public-presentation
```

인증된 KHDP 환경에서 실제 기록 상황판을 실행할 때는 별도로 준비한 풀 경로를 사용합니다.

```bash
ICU_LLM_CONFIG=/private/path/llm.json python3 kmimic_board.py \
  --pool /private/path/pool_gs.json --port 8007
```

설정 파일은 `base`, `key`, `model`, `vision_model`을 사용합니다. 키는 저장소 밖에 보관합니다. CXR 검토는 허용된 KHDP 게이트웨이와 검증된 환자·검사·시점 연결만 사용합니다. 이미지 원본 등록 없이는 영상이 표시되지 않습니다.

## 검증

```bash
python3 -m unittest test_vision_review test_patient_imaging test_grounded_chat test_kmimic_board test_clinical_detail
python3 -m unittest discover -s analysis -p 'test_*.py'
node --check static/patient-detail.js
```

DICOM 관련 검사는 `numpy`, `Pillow`, `pydicom`이 필요합니다. 추출 도구 중에는 `duckdb` 또는 `openpyxl`을 사용하는 도구도 있습니다. 현재 실행 환경의 검증 결과는 [repository-checks.json](verification/repository-checks.json)에 기록합니다.

## 해석 범위

병상 배치·의료진 이동은 시뮬레이션입니다. 실제 동시 병상 점유, 의료진의 실제 이동이나 환자의 치료 반응을 재현했다고 주장하지 않습니다. AI 영상 검토는 공식 영상판독문과 구분하며 임상 정확도가 검증된 기능이 아닙니다. 데이터 누락을 정상이나 장비 미사용으로 간주하지 않습니다.
