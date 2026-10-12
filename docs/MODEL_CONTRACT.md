# 외부 예측 모델 인터페이스 v1.0

앱은 이미 학습된 예측 모델이 존재한다는 가정하에 **동기 JSON HTTP 인터페이스**를 제공합니다. 실제 가중치·학습 코드·교정된 의료 모델은 이 패키지에 포함하지 않았습니다.

## 설정

`MODEL_BACKEND=remote`, `MODEL_URL=http(s)://.../predict`, 선택적 `MODEL_API_KEY`.

앱은 동일 판단 시점에 환자별 최대 4개 병렬 요청을 보냅니다. 요청당 timeout은 3초, 응답 읽기는 최대 1MB입니다. 새 관측·정책·경과 변화 시 예측을 갱신하고 조회는 저장된 예측을 반환합니다. 운영 변경도 예측을 다시 계산하므로 추론 서버는 동일 입력의 반복 호출을 처리해야 합니다.

## 요청

```json
{"schema_version":"1.0","as_of_minute":0,"features":{"patient_id":"DEMO-001","minute":0,"phase":"OR","age":67,"asa":3,"emergency":false,"planned_icu":false,"conditions":[],"preop_labs":{},"preop_labs_minute":-120,"pre_admission":[],"latest":{},"signal_window":[],"treatment_history":[],"units":{},"map_min_30":54,"low_map_fraction_30":0.7,"map_slope_30":0.1,"hr_max_30":115,"spo2_min_30":96,"persistent_postop_ventilation":false,"observation_age_minutes":0,"quality":1,"stale":false,"quality_issues":[],"observed_count":18,"elapsed_operation_minutes":55}}
```

`signal_window`는 최근 30분 관측, `treatment_history`는 현재까지 최근 50개 처치입니다. `pre_admission`은 입원 전·현재 이전 기록, `preop_labs`는 해당 관측 시각이 현재 이전인 검사만 포함합니다. 최종 수술시간, 최종 수술 총량, 미래 ICU·퇴원·지원 결과는 포함하지 않습니다.

이 기본 계약은 수치 시계열 수준입니다. 고주파 ECG/ART 파형 인코더는 모델 서비스 또는 upstream에서 수행하고 계약을 확장하세요. 앱이 500Hz 원파형을 직접 수집·학습한다고 주장하지 않습니다.

## 필수 응답

```json
{
  "need_score": 78,
  "need_probability": 0.82,
  "icu_probability": 0.90,
  "intensive_hours": 18,
  "intensive_hours_upper": 30,
  "icu_los_hours": 36,
  "icu_los_upper": 54,
  "hospital_los_days": 8,
  "hospital_los_upper": 12,
  "confidence": 0.86,
  "model_version": "your-model-v1",
  "interval_kind": "q50_q90",
  "contributions": [{"label":"지속 저혈압","points":12,"detail":"최근 관측 구간의 저혈압 부담"}]
}
```

`need_score` 0~100, 확률·신뢰 0~1, 모든 기간은 비음수입니다. 상한은 중앙값 이상이어야 합니다. 임상적 필요성과 실제 ICU 이용은 서로 다른 결과로 학습·정의해야 합니다.

집중관리/ICU 기간은 입실 전에는 수술 후 예상 기간, 회복실·ICU에서는 잔여 기간으로 정의합니다. `hospital_los_days`는 현재 시점부터 **잔여 입원기간**입니다. 원 모델이 총 LOS만 출력하면 upstream에서 이미 지난 기간을 반영해 변환하고 범위를 재검증하세요.

`confidence`의 정의와 범위 교정은 모델 공급자가 문서화해야 합니다. 예측 불확실성의 분위수/신뢰구간/시나리오 상한을 섞어 사용하지 않습니다. 화면의 기본 문구는 중앙 예측과 상한이며 95% CI라고 표시하지 않습니다.

`contributions`는 최대 30개입니다. 각 항목은 문자열 label/detail, 유한 숫자 points입니다. 실제 모델의 SHAP나 attribution을 사용하려면 해당 계산의 정의를 명시하세요. 기본 모드는 규칙 점수의 기여도입니다.

## 실패 동작

연결 실패·타임아웃·JSON 오류·NaN·누락 필드·역전 범위는 `mode=unavailable`, 수치 null, 신뢰 0으로 표시합니다. 예약 추천은 보류됩니다. 임의의 모의 값을 대신 표시하지 않습니다. 이미 확정된 예약은 자동 취소하지 않으며 담당자가 확인합니다.

## 검증 전제

환자 단위 분할, 수술별 landmark, 시간 정렬, 결측·채널 부재의 구분, 수술 후 정답 정의, 사망·관측 종료, 기관 선택 편향, 확률 보정은 모델 개발 단계에서 별도로 검증해야 합니다. 앱의 테스트 통과는 의료 모델 성능 검증을 의미하지 않습니다.


## v5의 추가 경과 입력

features에 elapsed_admission_hours, elapsed_postop_hours, procedure_group를 추가했습니다. elapsed_operation_minutes는 관측된 수술 종료 이후 증가하지 않습니다. 실제 종료가 시각 0이어도 정상 처리합니다. 새 필드는 현재 알려진 사실이며 최종 실제 LOS가 아닙니다.

입원 예정과 종료 사례는 현재 모델 요청에서 제외합니다. 종료 사례는 mode=completed, 현재 위험·확률=null이며, 실제 입원·퇴원 이력과 과거 관측을 보관합니다. 병동 신호의 신선도는 수술실·ICU와 다른 기준을 사용합니다. 기본 잔여기간 규칙은 경과시간을 반영하도록 변경했지만 학습·보정된 의료 모델은 아닙니다.

실제 데이터의 퇴원·사망·전원 사건은 예측 결과와 무관하게 해당 관측 시점에 반영합니다. 예측된 병상 가용성이나 LOS 만료는 사건을 대신할 수 없습니다. UI 축약 시계열은 모델 입력이 아니며, 모델 요청에는 현재 관측 원본 구간을 사용합니다.
