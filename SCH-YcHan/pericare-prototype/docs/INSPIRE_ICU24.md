# INSPIRE 수술 후 24시간 이내 ICU 입실 모델

이 모듈은 INSPIRE 수술 자료에서 **수술 종료 후 0~1,440분 이내에 해당 기관의 ICU 신규 입실이 기록될 확률**을 학습합니다. 집중관리의 임상적 필요, 비예정 ICU 입실, ICU 체류기간을 정답으로 사용하지 않습니다. 첫 모델의 예측 시점은 수술실 입실(`orin_time`)이며, 수술 시작 후 30·60·90분 등의 시점도 선택하여 재학습할 수 있습니다.

학습·평가·HTTP 연결을 재현하는 연구용 구현입니다. 후향적 기록에서의 성능은 실제 병원에 적용했을 때의 효과나 전향적 임상 성능을 보장하지 않습니다. 원본 정의는 [INSPIRE 1.4.2](https://physionet.org/content/inspire/1.4.2/)와 배포본 `schema.csv`, `parameters.csv`를 확인하세요.

실제 INSPIRE 전체 자료로 실행한 첫 PREOP 모델의 집계 결과는 [학습·연결 검증 결과](INSPIRE_ICU24_RESULTS.md)에 정리했습니다. 수술 중 예측 코드는 구현했으며, 이번에 학습한 모델의 적용 단계는 PREOP입니다.

## 구성과 입출력

| 모듈 | 입력 | 출력 |
|---|---|---|
| `ml.icu24.prepare` | INSPIRE 원본 CSV 또는 CSV.gz | 시점별 `prepared.csv`, `cohort_audit.json` |
| `ml.icu24.train` | 전처리 표와 출처 메타데이터 | `model.joblib`, `report.json`, 로컬 분할·예측 표 |
| `ml.icu24.serve` | 모델 파일, PeriCare HTTP 요청 | 현재 시점의 ICU 입실 확률과 적용 범위 |
| `ml.icu24.export_pericare` | 전처리 PREOP 행, 사용자가 제공한 수술 계획 | 미래 결과가 없는 단일 사례 앱 가져오기 JSON |
| `ml.icu24.synthetic` | 환자 수와 난수 seed | 실제 환자가 없는 시험용 원본 형태 CSV |

원본은 수정하지 않습니다. `operations.csv`, `vitals.csv`, 선택적인 `labs.csv`를 사용합니다. 원본 폴더에 `operations.csv/operations.csv`처럼 한 단계 더 풀려 있는 경우와 `.csv.gz`도 읽습니다. 수술·환자·입원 ID는 연결과 분할에만 사용합니다.

### 입력 특징

학습과 실행은 `ml/icu24/features.py`의 같은 변환을 사용합니다.

- 정적 특징: 나이, 성별, ASA, 체중·키, 응급 여부, 진료과, 마취 종류, 현재 단계.
- 수술 경과시간과 최근 30분 MAP·심박수·SpO₂의 현재값·요약값, 유효 관측 수와 관측 신선도.
- 선택적 검사: Hb, 크레아티닌, 혈소판, 알부민, 젖산 및 검사 경과시간. `hb`, `platelet`, INSPIRE의 `lacate` 철자를 공통 이름으로 변환합니다.
- 범위를 벗어나거나 없는 값은 결측으로 남기고, 결측 대체는 학습 분할에서만 맞춥니다. 관측 부재를 정상이나 0으로 만들지 않습니다.

최근 저혈압 비율은 **관측 개수 중 MAP 65 미만인 비율**입니다. 관측 간격을 보정한 저혈압 시간 비율이 아닙니다. 최종 수술시간, 최종 수술 코드·출혈량, 미래 ICU/퇴원시각, 미래 관측, ID는 입력 특징에 포함하지 않습니다. `case_id`는 INSPIRE가 제공하는 VitalDB 연결키이며 이 모델의 입력은 아닙니다.

### 예측 시점과 정보 가용성

`--landmarks preop`은 수술실 입실시점입니다. `preop,30,60,90`은 여기에 실제 수술 시작 후 해당 분의 시점을 추가합니다. 각 행에는 그 시점까지의 관측만 포함하며, 수술이 이미 끝난 뒤의 수술 중 시점은 만들지 않습니다. 실제 수술 종료시각은 코호트·정답 구성에만 사용합니다.

수술표의 ASA·응급 여부·마취 종류 등에는 개별 기록 가용시각이 없습니다. 연구용 입력에서는 수술실 입실 전에 알 수 있었다고 가정하므로, 실제 운영 연결 전 해당 기관의 입력 가용성을 확인해야 합니다. INSPIRE 나이는 배포된 범주값 그대로 사용합니다.

검사 `chart_time`은 실제 결과 확인시각을 보장하지 않습니다. `--labs`를 켜면 기본적으로 **60분 가용 지연**을 적용하여 `chart_time + 60 <= 예측시각`인 검사만 사용합니다. 이 값은 보수적으로 정한 연구 가정이며 실제 지연을 복원한 값이 아닙니다. `--lab-delay-minutes`를 바꾼 민감도 분석과 기관별 결과 확인시각 검증이 필요합니다. 검사 없이 학습한 모델에는 운영에서도 검사를 추가하지 않습니다.

### 정답과 제외 기준

```text
y_icu24 = 1 : opend_time <= icuin_time <= opend_time + 1440
y_icu24 = 0 : 정의한 관찰 구간에서 ICU 입실이 없고 음성 판정 조건이 충족됨
판정 불가    : 추적·시간·입실 기록 조건이 부족하면 학습에서 제외하고 감사 집계
```

나이 18~90세, ASA 1~5, 유효한 연결키·수술/입원 시간 순서를 확인합니다. 기존 ICU 재실·수술 종료 전 ICU 입실, 조기 사망, 추적 부족, 겹치거나 결과 귀속이 모호한 반복 수술은 별도 점검·제외합니다. 같은 입원의 여러 수술은 첫 수술을 기준으로 하며, 그 수술이 부적격이라고 이후 수술로 대체하지 않습니다. 단순히 ICU 시각이 빈 모든 행을 음성으로 만들지 않습니다. 정확한 제외 수와 사유는 생성된 `cohort_audit.json`으로 확인하세요.

원본의 ICU 시각이 해당 입원의 퇴원 이후를 가리키면 이번 입원의 양성으로 인정하지 않습니다. 그 먼 미래 ICU 사건 때문에 사례 자체를 제외하지 않으며, 다른 부적격 사유가 없으면 정의한 관찰 구간의 음성입니다. ICU 퇴실시각의 역전 등은 입실 라벨과 구분해 점검할 무결성 항목입니다. 입실확률 과제에서 정상적인 ICU 체류기간을 일괄적인 사례 선택 조건으로 삼지 않습니다. 입실시각 없이 퇴실시각만 있는 사례는 판정 불가로 제외합니다. 감사 JSON의 `exclusions`에는 제외 사유와 비적격 사건 집계가 함께 있으므로 모든 값을 더해 제외 환자 수로 해석하지 마세요.

24시간 전에 생존하여 병원을 떠나고 그때까지 ICU 입실 기록이 없는 사례는 해당 기관 관찰 종료까지의 음성으로 처리합니다. 퇴원시각이 있다고 전원 여부가 확실해지는 것은 아닙니다. 제공 자료로 구분할 수 없는 전원·외부병원 ICU 입실 및 누락은 남는 한계입니다. 이 모델의 목표는 **해당 기관에서 기록된 입실**이며 모든 기관을 합친 ICU 이용 여부가 아닙니다.

## 설치와 실행

명령은 `SCH-YcHan/pericare-prototype` 폴더에서 PowerShell로 실행합니다. Python 3.11~3.14가 필요합니다. `python` 명령이 없으면 설치된 Python 실행파일의 절대경로로 대체하세요. 앱 본체와 분리된 환경을 사용합니다.

```powershell
python -m venv .venv-ml
.\.venv-ml\Scripts\python.exe -m pip install -r ml/requirements.txt
```

실제 원본을 읽어 수술실 입실시점 기본 모델을 만듭니다. 준비된 행과 학습 결과는 로컬 전용입니다.

```powershell
.\.venv-ml\Scripts\python.exe -m ml.icu24.prepare `
  --data-dir "C:\Users\cczzt\OneDrive\Desktop\KCD2026\Dataset\INSPIRE\1.4.2" `
  --output-dir ".\ml_data\inspire-icu24" --landmarks preop

.\.venv-ml\Scripts\python.exe -m ml.icu24.train `
  --data ".\ml_data\inspire-icu24\prepared.csv" `
  --metadata ".\ml_data\inspire-icu24\cohort_audit.json" `
  --output-dir ".\ml_artifacts\inspire-icu24" --dataset-kind inspire --seed 26
```

수술 중 수치 시계열을 추가하려면 다음 설정으로 별도 폴더에 전처리한 뒤 같은 학습 명령을 해당 경로에 실행합니다.

```powershell
.\.venv-ml\Scripts\python.exe -m ml.icu24.prepare `
  --data-dir "C:\Users\cczzt\OneDrive\Desktop\KCD2026\Dataset\INSPIRE\1.4.2" `
  --output-dir ".\ml_data\inspire-icu24-multi" `
  --landmarks preop,30,60,90 --labs --lab-delay-minutes 60
```

`vitals.csv`와 `labs.csv`는 큰 파일이므로 해당 옵션은 원본 전체를 순회할 수 있습니다. 실제 데이터의 학습 성능은 `report.json`을 확인한 뒤 설명해야 하며, 합성 시험 점수와 섞어서 보고하지 않습니다.

### 환자 단위 분할·학습·평가

- 기본 비율은 학습 60%, 모델 선택용 검증 15%, 확률 보정 10%, 최종 시험 15%입니다. 환자별 양성 여부로 층화하고, 동일 환자의 모든 입원·수술·시점을 한 분할에 묶습니다.
- 수치 결측 대체·범주 인코딩을 포함한 전처리는 학습 환자에서만 맞춥니다. 로지스틱 회귀와 HistGradientBoosting을 비교하고, 수술별 가중 검증 log loss로 후보를 선택합니다.
- 선택한 모델에 별도 보정 환자로 sigmoid 보정을 적용합니다. 민감도 목표 0.90의 기준은 검증자료에서 선택합니다. 최종 시험자료는 선택·보정·기준 조정에 사용하지 않습니다.
- 여러 시점이 있는 긴 수술의 과도한 기여를 줄이기 위해 수술별 가중치를 사용합니다. AUROC, AUPRC, Brier score, log loss, 보정구간과 선택 기준의 혼동행렬·민감도·양성예측도를 기록합니다. 환자 단위 bootstrap으로 불확실성을 계산합니다.

`report.json`에는 분할 수, 유병률, 후보 비교, 최종 시험 결과, 사용 특징과 출처 설정 등이 들어갑니다. `split_manifest.csv`, `validation_predictions.csv`, `test_predictions.csv`에는 연결키가 포함되므로 공유 저장소에 올리지 않습니다. 반복 수술·랜드마크가 있는 경우 행 단위 무작위 분할로 대체하지 마세요.

## PeriCare 연결

로컬 모델 서버를 실행합니다. `--host`의 기본값은 루프백이며, 모델의 출처·특징 버전·학습 단계 범위를 확인합니다.

```powershell
.\.venv-ml\Scripts\python.exe -m ml.icu24.serve `
  --model ".\ml_artifacts\inspire-icu24\model.joblib" `
  --host 127.0.0.1 --port 9000
```

앱을 호스트에서 실행하면 **별도 PowerShell 창**에서 환경변수를 설정하고 실행합니다. 호스트 Python 서버는 `.env`를 자동으로 읽지 않습니다.

```powershell
$env:MODEL_BACKEND = "remote"
$env:MODEL_URL = "http://127.0.0.1:9000/predict"
$env:MODEL_TASK = "icu24_after_operation_end"
$env:HOST = "127.0.0.1"
.\.venv-ml\Scripts\python.exe server.py
```

이 서비스는 **ICU 입실확률만** 제공합니다. `need_probability`, `need_score`, 집중관리·ICU·입원 기간과 신뢰도는 지원하지 않아 `null`로 반환합니다. 화면에서도 미지원으로 표시하고, 기간이 없으므로 병상 예약은 보류합니다. 예측 단계는 PREOP/OR에 한정되며, 수술실 입실시점만 학습한 모델은 OR 요청도 거절합니다. 회복실·ICU·병동 환자에게 같은 모델을 적용하지 않습니다. 예측 실패나 적용 범위 밖 요청은 데모 확률로 대체하지 않습니다.

`prepared.csv`는 학습용이며 앱의 환자 JSON 형식은 아닙니다. 앱에는 기존 [자료 가져오기 형식](DATA_SCHEMA.md)에 맞춘 관측 자료를 불러옵니다. 서비스는 `source_mode: import` 또는 이에 해당하는 출처 정보가 있는 입력만 허용하므로, 기본 합성 운영 화면을 실제 모델의 결과로 바꾸지 않습니다. 검사별 가용시각·단위와 수술실 입실/시작 기준을 학습 때와 동일하게 제공해야 합니다.

### 실제 INSPIRE 사례 한 건을 화면에서 확인

PREOP 전처리 행 한 건을 앱 형식으로 변환할 수 있습니다. `--op-id`를 생략하면 첫 유효 PREOP 사례를 선택합니다. 아래 `30`, `120`은 **사용자가 주는 시험용 계획**입니다. 미래의 실제 수술 시작·종료를 원본에서 가져오는 값이 아닙니다. 실제 알려진 계획이 있으면 그 값을 사용하세요.

```powershell
.\.venv-ml\Scripts\python.exe -m ml.icu24.export_pericare `
  --data-dir "C:\Users\cczzt\OneDrive\Desktop\KCD2026\Dataset\INSPIRE\1.4.2" `
  --prepared ".\ml_data\inspire-icu24\prepared.csv" `
  --output ".\ml_data\inspire-icu24\pericare-preop.json" `
  --planned-start-in-minutes 30 --estimated-duration-minutes 120
```

앱의 **실제 관측 자료 연결 → 자료 선택 → 자료 불러오기**에서 해당 JSON을 불러옵니다. 현재 시점은 0분, 달력 표시는 임의의 2000년 기준, 시간축은 `case_relative`입니다. 원래 입원 경과와 가용 검사만 보존하며, 실제 미래 ICU 입퇴실·수술 종료·퇴원·사망·정답 라벨·가상 병상은 넣지 않습니다. 예정 ICU 여부·병력·장비 필요는 제공하지 않은 상태이며 앱 호환용 기본값을 임상적 음성으로 해석하면 안 됩니다. 예측 화면에서 ICU 입실확률만 확인하고 병상 예약은 보류되는 것이 정상입니다.

학습 행과 앱 요청의 특징이 같고 HTTP 연결이 동작하는지 재검증할 수도 있습니다. 검증기는 임시 앱·모델 서버를 열어 가져오기와 예측을 수행하고 종료합니다. `--output`에는 환자 행을 포함하지 않는 집계 확인 결과가 저장됩니다.

```powershell
.\.venv-ml\Scripts\python.exe -m ml.icu24.verify `
  --model ".\ml_artifacts\inspire_icu24_preop\model.joblib" `
  --snapshot ".\ml_data\inspire_preop_final\pericare_snapshot.json" `
  --prepared ".\ml_data\inspire_preop_final\prepared.csv" `
  --output ".\ml_artifacts\inspire_icu24_preop\connection_verification.json"
```

위 경로는 이번 실제 실행 결과입니다. 새 실험을 만들었다면 해당 실험의 모델·자료 경로로 바꾸세요.

### Docker로 앱과 모델 함께 실행

루트 `.env`의 `ML_MODEL_DIR`에 `model.joblib`이 있는 **절대경로**를 지정합니다. `ML_SKLEARN_VERSION`에는 학습 결과 `report.json`의 `versions.sklearn` 값을 그대로 입력합니다. 서버는 학습·실행의 scikit-learn 버전이 다르면 기동을 보류합니다. Windows에서도 `/`를 사용할 수 있습니다. 예시는 `ml/.env.example`에 있습니다.

```dotenv
ML_MODEL_DIR=C:/Users/cczzt/OneDrive/Documents/ChatGPT/KCD2026/SNUH_Hackathon/SCH-YcHan/pericare-prototype/ml_artifacts/inspire-icu24
ML_SKLEARN_VERSION=<report.json의 versions.sklearn 값>
MODEL_API_KEY=
```

```powershell
docker compose -f compose.yaml -f compose.icu24.yaml up --build
```

앱은 `http://127.0.0.1:8000`에서 열립니다. 모델 폴더는 읽기 전용으로 연결되며 모델 포트는 외부에 공개하지 않습니다. Compose가 `MODEL_BACKEND=remote`, `MODEL_URL=http://model-service:9000/predict`를 설정합니다. 모델과 앱을 각각 호스트/컨테이너에서 실행할 때는 주소가 달라지므로 위 두 실행 방식을 섞지 마세요.

## 합성 자료로 전체 흐름만 시험

실제 자료 없이 코드 실행을 확인하려면 새 빈 디렉터리에 시험자료를 만듭니다. 모든 사람·입원·수술·관측은 난수로 생성되며 반복 환자와 두 클래스를 포함합니다.

```powershell
.\.venv-ml\Scripts\python.exe -m ml.icu24.synthetic `
  --output-dir ".\ml_data\synthetic-source" --patients 300 --seed 26
.\.venv-ml\Scripts\python.exe -m ml.icu24.prepare `
  --data-dir ".\ml_data\synthetic-source" `
  --output-dir ".\ml_data\synthetic-prepared" --landmarks preop
.\.venv-ml\Scripts\python.exe -m ml.icu24.train `
  --data ".\ml_data\synthetic-prepared\prepared.csv" `
  --metadata ".\ml_data\synthetic-prepared\cohort_audit.json" `
  --output-dir ".\ml_artifacts\synthetic" --dataset-kind synthetic --seed 26
.\.venv-ml\Scripts\python.exe -m ml.icu24.serve `
  --model ".\ml_artifacts\synthetic\model.joblib" --allow-synthetic-artifact
```

합성 모델은 기본 서버 기동에서 차단됩니다. 위 허용 옵션은 시험 때만 사용하며, 합성 모델의 높은 점수를 실제 예측 성능으로 해석하지 않습니다. 생성기는 기존 표 파일을 덮어쓰지 않습니다.

## 데이터와 결과 보관

`ml_data/`, `ml_artifacts/`, `.venv-ml/`, `.ml-deps/`는 Git·Docker 전송 대상에서 제외합니다. `.gitignore`는 이미 추적 중인 파일을 지우거나 별도의 클라우드 동기화를 차단하지는 않습니다. 원본과 파생 행·분할 ID·개인별 예측·학습 가중치는 승인된 로컬 위치에 두고, 공동 GitHub 저장소에는 코드와 집계 결과만 필요한 범위에서 공유하세요.

모델 파일은 전처리와 모델·버전·학습 설정을 함께 저장하는 joblib 형식입니다. joblib은 파일 로드 시 코드를 실행할 수 있으므로 자신이 학습했거나 출처를 신뢰하는 파일만 읽으세요. 모델을 옮길 때는 같은 의존성 환경을 사용하고 기록된 버전을 확인하세요. 소스와 직접 학습·서빙에는 같은 `.venv-ml` 환경을 사용하는 것이 좋습니다.

이번 실제 모델의 로컬 폴더에는 전체 패키지 버전을 기록한 `requirements.freeze.txt`도 보관했습니다. 새 환경에서 동일 버전을 재현할 때 사용할 수 있습니다.

INSPIRE는 환자별 상대시간 자료이므로 여기서 만든 ICU 확률만으로 실제 동시 병상 수요나 대기시간 감소를 검증할 수 없습니다. 병상 운영 효과는 별도의 공통 병원 시간축·재고·예약 자료로 평가해야 합니다.

## 코드 검증

Windows에서는 Python의 UTF-8 모드를 켜고 전체 검증을 실행합니다.

```powershell
.\.venv-ml\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
docker compose -f compose.yaml -f compose.icu24.yaml config --quiet
```

Compose 검증에는 앞서 설명한 `ML_MODEL_DIR`, `ML_SKLEARN_VERSION` 설정이 필요합니다. 이번 실행에서 전체 테스트 158개와 Compose 설정 검증이 통과했습니다. 실제 모델·앱 연결은 위 `ml.icu24.verify`로 별도 확인했습니다. Docker 데몬이 가동되지 않아 컨테이너 빌드·기동은 확인하지 못했습니다.
