# 공통 관측·기록 재생 계약 v1.1

UTF-8 JSON, 최대 20MB, 사례 1~1,000개, 병상 0~100개, 미래 재생 사건 최대 100,000개입니다. 스냅샷 1.0도 읽습니다. `examples/canonical-data.json`은 스냅샷, `examples/recorded-replay.json`은 기록 재생 형식의 합성 예제입니다.

## 최상위

`schema_version`, 시간대가 있는 `base_time`, 정수 `minute`(현재), `horizon_minutes`(종료, 현재~현재+30일), `clock_kind`, `units`, `patients`, `beds`, 선택적 `replay_events`.

`clock_kind`: synthetic_shared/hospital_shared/patient_relative/case_relative. 환자별 상대시각은 실제 동시성을 뜻하지 않으며 병상 예약을 차단합니다. 실제 병상·인력 정보를 받지 못했으면 빈 beds를 사용하세요. 모델이 자원 경쟁을 추정하지 않습니다.

```json
{"map":"mmHg","hr":"bpm","spo2":"%","lactate":"mmol/L","hemoglobin":"g/dL","norepi":"ug/kg/min","urine_ml_kg_h":"mL/kg/h"}
```

## 환자 기준표

id(고유 사례), subject_id, admission_id, operation_id(고유), name(익명), age(18~100), sex(M/F/U), asa(정수 1~5), surgery, department, location, admission_minute, operation_start_minute, estimated_end_minute, actual_end_minute, planned_icu, emergency, preferred_unit(SICU/CCU), capabilities_required(ventilator/crrt), conditions, preop_labs, preop_labs_minute, pre_admission, observations, treatments.

추가로 procedure_group(minor/standard/major/complex/unknown), status(active/discharged/deceased/transferred), 이미 관측된 discharge_minute를 지원합니다. 분류를 제공하지 않으면 unknown입니다. 최종 실제 기간을 분류나 예상 종료로 변환하지 않습니다. 하나의 사례는 하나의 수술입니다. 반복 수술과 동일 입원의 현재 대표 사례·병상 키를 upstream에서 정리하세요.

미래 입원은 1.1에서만 허용합니다. location=NOT_ARRIVED, 빈 observations/treatments, actual_end_minute=null, 일치하는 hospital_admission 사건이 필요합니다. 해당 입원 이전에는 현재 화면·현재 모델 요청에 노출하지 않습니다. 미래에 알려질 진단·검사를 현재 스냅샷에 넣지 않습니다.

현재의 actual_end_minute와 discharge_minute는 미래를 허용하지 않습니다. 이후의 실제 값은 별도 사건으로 분리합니다. predicted LOS와 실제 종료 사건은 서로 바꾸어 넣지 않습니다.

## 관측

minute(측정시각), map, hr, spo2, lactate, hemoglobin, norepi, urine_ml_kg_h는 유한 숫자 또는 null. 지원 ventilation/crrt/artifact는 boolean 또는 null. 선택적 회복 관측 oral_intake/ambulating/wound_ok/discharge_plan_confirmed는 boolean/null, pain_score는 0~10/null. 입력에 없는 항목은 null이며 정상 또는 미사용으로 간주하지 않습니다.

기본 범위: MAP 20~200, HR 20~220, SpO₂ 50~100, 젖산 0~30, Hb 2~22, NE 0~5, 소변량 0~20. 실제 극단값은 upstream에서 확인하고 계약을 조정하세요. 범위 밖 값을 자동 정상화하지 않습니다.

환자별 현재 관측 최대 1,000개, 처치 최대 500개. 처치 항목은 minute/kind/label/dose/unit. 미래 관측·처치·검사와 중복 관측 시각은 현재 스냅샷에서 거부합니다. 고해상도 원파형은 모델 서비스에서 집계·인코딩합니다.

## 재생 사건

사건은 `{minute, patient_id, kind, ...}` 형식이며 현재 이후 정수 분, 종료 시각 이내입니다. 그 시점에만 관측으로 반영합니다.

| kind | 추가 필드 |
|---|---|
| hospital_admission | location, 기준표 admission_minute와 동일 시각 |
| observation | observation 객체. 측정 minute은 사건 minute 이하 |
| operation_start | 관측 location. 실제 수술 시작 시각 반영 |
| operation_end | 선택적 actual_end_minute(실제 종료 시각 ≤ 사건 minute). 없으면 사건 시각을 종료 시각으로 사용 |
| location | 관측 location, 목적 ICU 병상이 있으면 실제 점유 확인 |
| hospital_discharge | outcome=home/death/transfer 필수 |

동일 시각은 입원→수술 시작→관측→수술 종료→위치→병원 종료 순으로 기록하며, 해당 시각의 병상 이동은 한 묶음으로 확인합니다. 중복 사건, 종료 후 이동·진료 사건, 중복 수술 종료를 거부합니다. 종료 이후에 도착한 과거 관측은 측정 시각이 입원 종료 이전일 때만 이력으로 보관하며, 환자를 다시 입원 상태로 바꾸지 않습니다. 관측은 제공받은 측정시각과 가용시각을 구별할 수 있습니다. 입퇴원 사건의 minute에는 기록된 사건 시각을 사용합니다. operation_end는 minute을 정보가 관측 가능해진 시각, actual_end_minute를 실제 종료 시각으로 구분할 수 있습니다. 종료 정보는 minute에 도달하기 전에는 공개·예측 입력에 반영하지 않습니다.

실제 병상 중복 기록이 발생하면 해당 진행 요청을 원자적으로 거부하고 기존 상태를 보존합니다. 날짜 이동이 환자 간 달력을 보존하지 않으면 hospital_shared로 표시하지 않습니다.

## 병상·내보내기

병상은 id/unit/capabilities/enabled/occupant_id/available_minute/available_basis/closed_reason. available_minute는 예측이며 실제 퇴실이 아닙니다. 종료·예정 환자가 실제 병상을 점유하도록 입력할 수 없습니다. 환자의 특정 병상 location과 그 병상의 occupant_id는 반드시 일치해야 합니다. ICU/SICU/CCU처럼 구역만 제공한 경우에는 함께 제공된 occupant_id 연결로 위치를 구체화합니다. 등록된 병상 ID는 기관별 문자열이어도 됩니다.

v6.1에서 availability_forecast_known은 선택적 boolean입니다. 가용 예상 시각을 제공하지 않으면 false이고, true라면 available_minute를 제공해야 합니다. false인 재실 병상은 숫자 자리표시자가 있어도 미래 예약 후보로 사용하지 않으며 화면에 퇴실 시각 미확인으로 표시합니다. 새 재실이 기록될 때 이전 환자의 예상 가용 시각을 상속하지 않습니다. 실제 입실 기록은 추정 청소 시간보다 우선하는 관측이며, 실제 자료의 청소 완료 이력은 별도 운영 자료로 연결해야 합니다.

현재 스냅샷 내보내기는 활성 사례 최근 72개 관측, 종료 사례 최근 12개 관측, 최근 50개 처치와 현재 상태를 포함합니다. 비공개 미래 사건·예정 환자·감사·예약 전체를 포함하지 않는 부분 내보내기입니다. SQLite와 원자료를 별도로 보관합니다.
