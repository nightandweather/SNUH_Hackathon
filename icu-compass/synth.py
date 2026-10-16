"""K-MIMIC 형태의 가상 환자 풀 생성 (로컬 개발용).

Pod에서는 kmimic.py로 실제 환자 풀을 만들고, 이 파일은 쓰지 않는다.
출력 형식은 kmimic.py와 같다: data/pool_synth.json
"""
import json
import random
from pathlib import Path

STEP = 5  # 분 단위 해상도

# 병동 종류별 기본 활력징후와 기계환기/승압제 확률
PROFILES = {
    "EICU":  dict(hr=95, map=78, spo2=96, rr=20, vent=0.35, pressor=0.25, age=(30, 90)),
    "SICU":  dict(hr=88, map=82, spo2=97, rr=18, vent=0.45, pressor=0.20, age=(40, 85)),
    "CSICU": dict(hr=92, map=75, spo2=97, rr=16, vent=0.60, pressor=0.45, age=(45, 85)),
    "CCU":   dict(hr=82, map=80, spo2=96, rr=18, vent=0.15, pressor=0.20, age=(45, 90)),
    "MICU":  dict(hr=100, map=74, spo2=94, rr=22, vent=0.50, pressor=0.35, age=(35, 90)),
    "PICU":  dict(hr=120, map=65, spo2=96, rr=28, vent=0.40, pressor=0.15, age=(1, 15)),
    "NICU":  dict(hr=145, map=40, spo2=94, rr=50, vent=0.35, pressor=0.10, age=(0, 0)),
}
DX = {
    "EICU": ["다발성 외상", "패혈성 쇼크", "약물 중독", "뇌출혈"],
    "SICU": ["위절제술 후", "간이식 후", "장천공 수술 후", "췌십이지장절제술 후"],
    "CSICU": ["CABG 후", "판막치환술 후", "대동맥 박리 수술 후", "ECMO"],
    "CCU": ["NSTEMI", "STEMI PCI 후", "심부전 악화", "완전방실차단"],
    "MICU": ["폐렴", "패혈증", "ARDS", "상부위장관 출혈"],
    "PICU": ["RSV 세기관지염", "선천성 심질환 수술 후", "경련 중첩증", "DKA"],
    "NICU": ["미숙아 28주", "신생아 호흡곤란", "신생아 패혈증", "선천성 횡격막 탈장"],
}


def make_patient(pid, utype, rng):
    p = PROFILES[utype]
    los_min = rng.randint(12, 48) * 60
    n = los_min // STEP
    vent = rng.random() < p["vent"]
    pressor = rng.random() < p["pressor"]
    sev = 1 + vent + pressor  # 중증도가 높을수록 변동과 사건이 잦음
    base = {k: p[k] + rng.uniform(-6, 6) for k in ("hr", "map", "spo2", "rr")}
    base["spo2"] = min(base["spo2"], 99)
    cur = dict(base)
    series = {k: [] for k in ("hr", "map", "spo2", "rr")}

    # 악화 에피소드와 심정지 시점 미리 정하기
    episodes = []
    for i in range(n):
        if rng.random() < 0.0025 * sev:
            episodes.append((i, "det"))
    cpr = []
    if rng.random() < 0.06 * sev:
        i = rng.randint(n // 6, n - 6)
        episodes.append((i, "arrest"))
        cpr.append(i * STEP)

    shock = [0.0] * n  # 0~1, 악화 강도
    arrest = [False] * n
    for i, kind in episodes:
        if kind == "det":
            for j in range(-4, 8):  # 20분 진행, 40분 회복
                if 0 <= i + j < n:
                    shock[i + j] = max(shock[i + j], 1 - abs(j) / (4 if j < 0 else 8))
        else:
            for j in range(-3, 3):
                if 0 <= i + j < n:
                    shock[i + j] = max(shock[i + j], 0.8)
            for j in range(0, 3):
                if i + j < n:
                    arrest[i + j] = True

    for i in range(n):
        for k in cur:
            cur[k] += 0.25 * (base[k] - cur[k]) + rng.gauss(0, {"hr": 3, "map": 3, "spo2": 0.7, "rr": 1.2}[k])
        s = shock[i]
        hr = cur["hr"] * (1 + 0.45 * s)
        mp = cur["map"] * (1 - 0.35 * s)
        sp = cur["spo2"] - 10 * s
        rr = cur["rr"] * (1 + 0.6 * s)
        if arrest[i]:
            hr, mp, sp, rr = rng.uniform(0, 20), rng.uniform(10, 25), rng.uniform(50, 70), 0
        series["hr"].append(round(hr))
        series["map"].append(round(mp))
        series["spo2"].append(round(min(sp, 100)))
        series["rr"].append(round(rr))

    a0, a1 = p["age"]
    # 입원 전 EMR·수술 중 정보로 만든 사전위험 자리표시 (Pod에서 VitalDB/INSPIRE 모델로 대체)
    prior = min(100, max(0, 20 + 15 * vent + 15 * pressor + rng.gauss(0, 10)))
    return {
        "pid": pid,
        "unit_type": utype,
        "age": rng.randint(a0, a1),
        "sex": rng.choice("MF"),
        "dx": rng.choice(DX[utype]),
        "vent": vent,
        "pressor": pressor,
        "step": STEP,
        "los_min": n * STEP,
        "series": series,
        "cpr": cpr,
        "prior_risk": round(prior),
        "prior_icu_hours": round(n * STEP / 60 * rng.uniform(0.6, 1.0), 1),
        "source": "synthetic",
    }


def build(n_per_unit=60, seed=7):
    rng = random.Random(seed)
    pool = []
    for utype in PROFILES:
        for i in range(n_per_unit):
            pool.append(make_patient(f"S-{utype}-{i:03d}", utype, rng))
    return pool


if __name__ == "__main__":
    out = Path(__file__).parent / "data" / "pool_synth.json"
    pool = build()
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(pool, ensure_ascii=False))
    print(f"{len(pool)}명 → {out}")
