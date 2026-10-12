# KCD 데이터셋 연결과 모델 입력 구성

이 앱은 공식 데이터셋 자체를 배포하거나 익명 환자 대응표를 추정하지 않습니다. 실제 배포 버전·키·시각·결측을 확인하고 아래 방식으로 upstream에서 연결합니다.

## 권장 기본안: INSPIRE

1. subject_id–hadm_id–op_id로 환자·입원·수술 기준표를 만듭니다.
2. labs/diagnosis/medications는 환자키와 현재 판단시각 이전 구간으로 연결합니다.
3. vitals는 수술키와 chart_time으로 정렬합니다.
4. 현재 수술 중 예측에는 이후 ward/ICU 기록을 넣지 않습니다. 수술 후 지원·ICU·퇴원 정보는 정답으로 분리합니다.
5. 환자별 시간 단위와 기준시점을 확인합니다. 수술실 입실, 마취 시작, 수술 시작을 동의어로 치환하지 않습니다.
6. INSPIRE의 공개 ICU 시각은 수술 후 24시간 이내 입실 범위이므로 결측을 전체 입원 중 ICU 미이용으로 라벨링하지 않습니다.

수술 도중 학습 landmark=τ의 모델 입력을 만드는 경우:

`as_of_source = 수술 시작 시각 + τ`

`canonical_minute = source_time - as_of_source`

각 사례를 현재 판단시각 0에 맞추면 `clock_kind=case_relative`로 표시합니다. 병상 예약은 차단됩니다. 실제 동시 수요를 계산하려면 환자 간 달력이 보존된 승인 자료나 명시적인 합성 공통 일정을 별도로 구성해야 합니다.

estimated_end_minute에는 수술 예정시간 또는 현재까지의 경과로 추정한 종료를 사용합니다. 원본 최종 수술시간으로 미래 종료를 미리 알려주지 않습니다. 최종 약물 총량·최종 출혈량·퇴원·수술 후 지원도 입력에서 제외합니다.

첫 입원의 진단·약물에 충분한 입원 전 이력이 있다고 가정하지 않습니다. 실제 과거 관측 범위를 확인하고 입원 전 정보와 입원 후·수술 전 검사를 구분합니다.

## VitalDB

caseid로 임상·검사·수술 중 신호를 연결하고 subjectid로 반복 수술을 분리합니다. 신호는 기록 시작 기준 초 단위입니다. canonical 분 단위로 변환할 때 기록 기준점과 수술 사건 기준점의 offset이 필요합니다.

고해상도 파형은 upstream에서 인코딩·집계합니다. 약물 속도 채널은 실제 기록된 사례에서만 사용합니다. `Orchestra/NEPI_RATE` 등 mL/h 채널을 µg/kg/min로 변환하려면 약물 농도와 체중이 확인돼야 합니다. 농도·체중 미상인 값을 이 앱의 norepi에 직접 넣지 않습니다.

공개 INSPIRE와 공개 VitalDB를 합치는 공식 op_id–caseid 대응표는 별도 필요합니다. 같은 병원 자료라는 사실만으로 같은 익명 ID를 뜻하지 않습니다. 대응표가 없으면 별도 코호트로 사용합니다.

## SNUH-CDM / 기관 신호

승인된 공통 환자·입원·수술키 + 수술별 파형 파일 + recording start/end + 임상 사건 offset이 필요합니다. OMOP PERSON/VISIT_OCCURRENCE와 CONDITION/MEASUREMENT/DRUG/PROCEDURE/DEVICE를 이용하며 ICU 세부 체류는 VISIT_DETAIL 또는 원천 전동 이력을 확인합니다.

DRUG_EXPOSURE가 실제 투여인지 처방인지 확인합니다. 날짜만 있는 수술 코드로 초·분 단위 신호를 정렬할 수 없습니다. 대회 제공 환자군이 사망 환자 중심으로 선별되었는지도 확인하세요.

## K-MIMIC / MIMIC-IV

환자–입원–ICU 체류키로 별도 ICU 경과 하위 과제를 구성합니다. 수술실 기록을 대신하거나 다른 데이터셋의 환자에 붙이지 않습니다. MIMIC-IV ICU inputevents의 실제 시작·종료·속도 이력은 지원 지속기간 하위 과제에 사용할 수 있습니다. ICU 미입실 일반 수술 환자에 대한 필요 확률의 대표 학습 코호트로 간주하지 않습니다.

## AMC 대회 하위집합

공식 제공 수술–OMOP–파형 연결 메타데이터를 사용합니다. 사망이 확인된 선별 코호트를 일반 수술 위험 확률의 대표 분포로 취급하지 않습니다. 해당 특성은 UI의 모의 예측으로 해결되는 문제가 아니며 학습·평가 설계에서 다뤄야 합니다.

## 병상 운영에 필요한 자료

공통 병원 달력, 비수술 ICU 유입, 시간별 가동병상/인력, 예약 요청·확정·취소, 준비·청소시간, 실제 입퇴실·이송 지연. 자료가 없다면 합성 운영 달력을 명시하고 시뮬레이션 결과로 발표합니다.

공식 문서:

- https://datathon.kr/information/dataset/
- https://physionet.org/content/inspire/1.4.2/
- https://vitaldb.net/dataset/
- https://arxiv.org/html/2412.04474v1
- https://ohdsi.github.io/CommonDataModel/cdm54.html
- https://mimic.mit.edu/docs/iv/modules/icu/inputevents.html
- https://physionet.org/content/mimiciv/3.1/


## v6 연결 후 확인

먼저 실제 제공 하위집합의 환자 수, ICU 미이용 비율, 병원 총 LOS/수술 후 LOS/ICU LOS의 중앙값·사분위수·단기 체류 비율을 집계하세요. 60명·24명/일·7일은 앱 시연 조건이며 실제 분포를 뜻하지 않습니다. 사망·전원과 진행 중 체류를 단순한 정상 퇴원으로 라벨링하지 않습니다.

환자별 상대시각의 관측 재생은 지원하지만 실제 병상 수요를 재구성하지 않습니다. 공통 달력·병상 재고가 없으면 예약을 차단합니다. 실제 미래 관측과 종료는 replay_events로만 반영하고 학습 특징에 포함하지 않습니다. 잔여 입원기간의 목표는 관측된 종료시각에서 예측 시각을 뺀 값이며, 전체 LOS를 그대로 잔여기간으로 표시하지 않습니다.
