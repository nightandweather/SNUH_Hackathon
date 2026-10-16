"""MIMIC-IV (demo 또는 전체) → 환자 풀 data/pool_mimic.json.

    python mimic.py --fetch              # 공개 demo 내려받고 풀 만들기
    python mimic.py --dir <MIMIC-IV 폴더> # 이미 받은 데이터로

- 성인 ICU만 있으므로 PICU/NICU는 synth.py 가상 환자로 채운다 (source 표시로 구분).
- 날짜는 환자별 shift. 입실 시각 기준 상대 시간만 쓴다.
- 사전위험(prior_risk)은 자리표시: 입실 시점 정보(나이, 진단 수, 기계환기, 승압제).
  Pod에서 VitalDB/INSPIRE로 학습한 모델로 바꾼다.
"""
import argparse
import csv
import gzip
import json
import random
from datetime import datetime
from pathlib import Path

import synth

ROOT = Path(__file__).parent
STEP = 5
VITALS = {"hr": {"220045"}, "map": {"220052", "220181"}, "spo2": {"220277"}, "rr": {"220210", "224690"}}
ITEM2VAR = {i: k for k, ids in VITALS.items() for i in ids}
ARREST = {"225466"}  # procedureevents: Cardiac Arrest
VENT = {"225792"}  # procedureevents: Invasive Ventilation
PRESSORS = {"221906", "221289", "221662", "222315", "221749"}  # norepi, epi, dopamine, vasopressin, phenylephrine
CAREUNIT = [  # 순서 중요: 앞에서 먼저 매칭
    ("Cardiac Vascular", "CSICU"), ("Coronary", "CCU"), ("Trauma", "EICU"),
    ("Medical/Surgical", None), ("Neuro Surgical", "SICU"), ("Surgical", "SICU"), ("Medical", "MICU"),
]
TABLES = ["icu/icustays", "icu/chartevents", "icu/procedureevents", "icu/inputevents",
          "hosp/patients", "hosp/diagnoses_icd", "hosp/d_icd_diagnoses"]
DEMO_URL = "https://physionet.org/files/mimic-iv-demo/2.2"


def fetch(d):
    """공개 MIMIC-IV demo를 d에 내려받는다 (약 8MB, 이미 있으면 건너뜀)."""
    import urllib.request
    for t in TABLES:
        p = Path(d) / f"{t}.csv.gz"
        if p.exists():
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        print(f"  내려받는 중 {t}")
        urllib.request.urlretrieve(f"{DEMO_URL}/{t}.csv.gz", p)


def save(d, hours=48):
    pool, kids = build(d, hours)
    out = ROOT / "data" / "pool_mimic.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(pool + kids, ensure_ascii=False))
    return pool, kids, out


def rows(d, name):
    with gzip.open(Path(d) / f"{name}.csv.gz", "rt") as f:
        yield from csv.DictReader(f)


def ts(s):
    return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")


def build(d, hours, seed=7):
    rng = random.Random(seed)
    horizon, n = hours * 60, hours * 60 // STEP
    pts = {r["subject_id"]: r for r in rows(d, "hosp/patients")}
    titles = {(r["icd_code"], r["icd_version"]): r["long_title"] for r in rows(d, "hosp/d_icd_diagnoses")}
    dx, ndx = {}, {}
    for r in rows(d, "hosp/diagnoses_icd"):
        ndx[r["hadm_id"]] = ndx.get(r["hadm_id"], 0) + 1
        if r["seq_num"] == "1":
            dx[r["hadm_id"]] = titles.get((r["icd_code"], r["icd_version"]), r["icd_code"])

    stays = {}
    for r in rows(d, "icu/icustays"):
        ut = None
        for key, t in CAREUNIT:
            if key in r["first_careunit"]:
                ut = t or rng.choice(["MICU", "SICU"])
                break
        if ut is None:
            continue
        stays[r["stay_id"]] = {"ut": ut, "t0": ts(r["intime"]), "r": r, "obs": {}, "arrest": [],
                               "vent": False, "pressor": False}

    def rel(s, t):
        m = (ts(t) - s["t0"]).total_seconds() / 60
        return m if 0 <= m < horizon else None

    for r in rows(d, "icu/chartevents"):
        s, var = stays.get(r["stay_id"]), ITEM2VAR.get(r["itemid"])
        if s is None or var is None or not r["valuenum"]:
            continue
        m = rel(s, r["charttime"])
        if m is not None:
            s["obs"].setdefault(var, []).append((m, float(r["valuenum"])))
    for r in rows(d, "icu/procedureevents"):
        s = stays.get(r["stay_id"])
        if s is None:
            continue
        m = rel(s, r["starttime"])
        if r["itemid"] in ARREST and m is not None:
            s["arrest"].append(int(m))
        if r["itemid"] in VENT and (m is None or m < 360):  # 입실 6시간 안에 기계환기
            s["vent"] = True
    for r in rows(d, "icu/inputevents"):
        s = stays.get(r["stay_id"])
        if s is not None and r["itemid"] in PRESSORS:
            m = rel(s, r["starttime"])
            if m is not None and m < 360:
                s["pressor"] = True

    pool = []
    for sid, s in stays.items():
        if "hr" not in s["obs"]:
            continue
        series, last_t = {}, 0.0
        for var in VITALS:
            obs = sorted(s["obs"].get(var, []))
            out, j, last = [], 0, None
            for i in range(n):
                while j < len(obs) and obs[j][0] <= i * STEP:
                    last = obs[j]
                    j += 1
                out.append(round(last[1]) if last and i * STEP - last[0] <= 60 else None)
            series[var] = out
            if obs:
                last_t = max(last_t, obs[-1][0])
        k = min(n, int(last_t // STEP) + 1)
        if k < 24:  # 2시간 미만 기록은 제외
            continue
        r = s["r"]
        p = pts.get(r["subject_id"], {})
        age = int(p.get("anchor_age") or 0)
        prior = 15 + 15 * s["vent"] + 15 * s["pressor"] + min(ndx.get(r["hadm_id"], 0), 30) * 0.7 \
            + (10 if age >= 75 else 0)
        pool.append({
            "pid": f"M-{sid}", "unit_type": s["ut"], "careunit": r["first_careunit"],
            "age": age, "sex": p.get("gender"), "dx": dx.get(r["hadm_id"], r["first_careunit"]),
            "vent": s["vent"], "pressor": s["pressor"], "step": STEP, "los_min": k * STEP,
            "series": {v: a[:k] for v, a in series.items()}, "cpr": sorted(set(s["arrest"])),
            "prior_risk": round(min(prior, 100)), "prior_icu_hours": round(float(r["los"]) * 24, 1),
            "source": "MIMIC-IV",
        })
    kids = [p for p in synth.build(n_per_unit=40, seed=seed) if p["unit_type"] in ("PICU", "NICU")]
    return pool, kids


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "data" / "mimic-iv-demo"))
    ap.add_argument("--fetch", action="store_true", help="공개 MIMIC-IV demo 내려받기")
    ap.add_argument("--hours", type=int, default=48)
    a = ap.parse_args()
    if a.fetch:
        fetch(a.dir)
    pool, kids, out = save(a.dir, a.hours)
    by = {}
    for p in pool:
        by[p["unit_type"]] = by.get(p["unit_type"], 0) + 1
    print("MIMIC-IV 병동별:", by, "· 심정지 기록:", sum(bool(p["cpr"]) for p in pool))
    print(f"{len(pool)}명 + 소아/신생아 가상 {len(kids)}명 → {out}")
