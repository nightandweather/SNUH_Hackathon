# CalMRL v19 — ICU 입실 24시간 기준 위험도·전과시간

2026-10-17 실제 MIMIC 자료로 test 평가를 마친 **학습된 v19 모델**입니다. 고정된 Original EMR과 CalMRL 표현 복원·결합 가중치를 포함합니다. 공식 CalMRL의 임상 과제용 변형이며 원 논문의 그대로인 구현은 아닙니다. 각 새 구성 요소는 30 epoch 학습했습니다.

| Test 지표 | Original EMR | CalMRL v19 |
|---|---:|---:|
| 사망 위험 AUPRC (average precision) | 0.489899 | **0.614379** |
| 사망 위험 AUROC | 0.744444 | **0.833333** |
| 조건부 전과 잔여시간 MAE, 일 | **2.465306** | 2.478863 |
| 조건부 전과 잔여시간 RMSE, 일 | **3.547579** | 3.594894 |

위험도는 **원내 사망**, 시간은 **생존 상태의 ICU→일반병동 전과가 확인된 사례에서 전과까지 남은 일수**입니다. 안전한 퇴실 확률이나 모든 환자의 퇴실일을 직접 예측하는 모델은 아닙니다. 전과시간 성능은 개선되지 않았습니다.

기존 환자 분할·라벨·시각 검증과 고유 CXR 1,000개 제한을 유지했습니다. 학습 129명/219입원, validation 25명/34입원, test 21명/33입원이며 test 사망 3건, 시간 라벨 23건입니다. CXR 선정 부분 코호트에서 CXR이 없는 시점도 포함하며 **전체 MIMIC ICU 코호트 결과가 아닙니다**. 반복 노출된 test의 탐색적 결과이므로 통계적·외부 검증 우월성이 확립된 것은 아닙니다. 세부 지표와 환자 단위 bootstrap은 `metrics.json`에 있습니다.

## 사용

Python 3.12와 PyTorch 2.8.0에서 검증했습니다. 아래 코드는 이 폴더에서 실행합니다.

```bash
python -m pip install -r requirements.txt
```

```python
import numpy as np
from calmrl_v19_inference import InferenceBundle

model = InferenceBundle('.', device='cpu')
with np.load('authorized_inputs.npz', allow_pickle=False) as x:
    logits, emr = model.encode_emr(
        x['values'], x['observed_mask'], x['delta_hours'], x['emr_age_hours'])
    prediction = model.predict_from_features(
        emr, logits, x['cxr_imagenet'], x['cxr_medical'],
        x['cxr_semantic11'], x['cxr_observed'], x['cxr_age_hours'])
```

입력은 별도로 환자·시각 연결을 검증한 자료여야 합니다. `values`, `observed_mask`, `delta_hours`는 `[N,24,19]`이며 특성 순서는 `model.json`의 scaler에 있습니다. 경과시간 단위는 시간입니다. 세 CXR 표현은 각각 `[N,1024]`, `[N,1024]`, `[N,11]`입니다. 관측 CXR은 landmark 이전 72시간 안의 동일 환자 영상이며, 누락 사례의 CXR 배열은 NaN으로 둘 수 있습니다. 인코더와 변환은 `external_image_encoders.json`을 확인하세요. 임의의 다른 embedding으로 대체할 수 없습니다.

`parameters.npz`는 수치 가중치, `model.json`은 추론 설정입니다. pickle을 사용하지 않으며, 환자별 데이터·예측·연결키·Pod 경로·원본 영상은 포함하지 않습니다. 외부 사전학습 영상 가중치는 공식 배포처에서 별도로 받습니다. `verification_aggregate.json`은 Pod 안에서 원래 모델과 내보낸 모델의 예측 일치를 확인한 집계 기록입니다.

기존 시각은 retrospective study-time proxy이며 임상 현장의 결과 공개 시각이 검증된 것은 아닙니다. 의료진의 연구·판단 지원용이며 자동 퇴실 결정에 사용하지 않습니다. 상황판 앱에 자동 연결하거나 배포한 버전은 아닙니다.

참고: [CalMRL 논문](https://arxiv.org/abs/2511.12034), [공식 코드](https://github.com/Xiaohao-Liu/CalMRL), [TorchXRayVision](https://github.com/mlmed/torchxrayvision), [torchvision DenseNet](https://github.com/pytorch/vision/blob/v0.23.0/torchvision/models/densenet.py).
