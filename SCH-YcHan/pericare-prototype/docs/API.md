# HTTP API v6.1

조회: `/health`, `/api/state`, `/api/example`(스냅샷), `/api/example/replay`(합성 기록 재생 예제), `/api/export/data`(최근 관측 스냅샷), `/api/export/audit`, `/api/export/predictions`, `/api/export/reservations`.

`/api/state`에는 hospital(시작/현재 추적 입원, 신규 입원, 귀가 퇴원·사망·전원, 일별 수, 병동 배정·청소, 종료시각), predictions, 실제 입원 단계, scene, automation, 실제 예약을 포함합니다. 비공개 미래 사건·대기열·합성 정답은 반환하지 않습니다. 장기 경과는 화면용 축약본입니다.

변경은 `POST /api/actions/{action}` JSON, 최대 20MB. 운영 쓰기에는 expected_revision을 사용하며 오래된 검토는 409입니다. 사용자 actor는 감사용 문자열이며 인증 역할을 대신하지 않습니다. 필요한 환경에서는 APP_USERNAME/APP_PASSWORD를 함께 설정하세요.

| action | 주요 입력 |
|---|---|
| play | running, speed=1~240 분/틱 |
| advance | minutes=1~1440, 종료 시각을 넘어가지 않음 |
| reset | seed, 기본 60명·7일 합성 시나리오 |
| import | dataset=공통 계약 1.0/1.1 |
| observe | patient_id, 현재까지의 observations, 선택적 as_of_minute·actual_end_minute·estimated_end_minute |
| end_operation | patient_id, 실제 종료 관측 사유 |
| reserve/apply_recommendation/cancel/admit/discharge | 개발자 운영 API. discharge는 ICU→병동 전실 |
| hospital_discharge | patient_id, 실제 병원 퇴원 사유. 병동 환자만 기록 |
| bed/bed_forecast/policy/scenario/automation/note/ack | 기존 개발자 API 유지 |

시나리오와 가상 의료진 자동 진행은 합성 공통 달력에서만 허용합니다. 실제 자료에는 자동 진료·입퇴원을 생성하지 않습니다. 프런트엔드는 환자 입실·퇴원 결정 입력을 요구하지 않습니다.

API 실패는 전체 변경과 재생 커서를 롤백합니다. 실제 사망·전원은 기록 재생의 명시적 outcome으로 처리하며 귀가 퇴원 수와 구분합니다. 큰 진행 요청도 중간 5분 평가와 정수 분 관측 사건을 순서대로 처리합니다. 실제 event timestamp가 5분 배수일 필요는 없습니다.

수술 종료 정보를 다시 받아도 기존 ICU·병동·종료 상태를 되돌리지 않습니다. 실제 종료 시각과 수신 시각을 구별하며 최초 종료만 수술 완료 수에 집계합니다. 종료 이후 수신한 과거 관측은 측정 시각이 해당 입원 종료 이전인 경우에만 보관합니다. 아직 입원하지 않은 사례의 입원 중 관측과 종료 이후 새 측정은 거부합니다. 병상 재실 정보와 환자 위치가 충돌하는 입력도 거부합니다.
