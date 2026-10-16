"""K-MIMIC CSV → 환자 풀 (data/pool_kmimic.json). Pod 안에서 실행.

    python kmimic.py --dir /path/to/kmimic --max-per-unit 200 --hours 24

- 표준 라이브러리만 사용 (인터넷 없는 Pod 대비). .csv / .csv.gz 둘 다 읽음.
- 날짜는 환자별로 shift 되어 있으므로 입실 시각(intime) 기준 상대 시간(분)만 쓴다.
  원래 날짜 복원은 하지 않는다 (재식별 시도 금지).
- itemid는 concepts.json에서 읽는다. 병원별 ID가 다르니 Pod에서 확인 후 채울 것.
- 아직 실제 K-MIMIC으로 돌려보지 않았다. 컬럼명이 다르면 COLS만 고치면 된다.
"""
import argparse
import csv
import gzip
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
STEP = 5
COLS = {
    "stay": ["stay_id", "icustay_id"],
    "unit": ["first_careunit", "careunit"],
    "intime": ["intime"],
    "outtime": ["outtime"],
    "subject": ["subject_id"],
    "itemid": ["itemid"],
    "time": ["charttime", "value"],  # datetimeevents는 value에 시각이 들어있을 수 있음
    "num": ["valuenum", "value"],
}


def open_table(d, name):
    for fn in (f"{name}.csv", f"{name}.csv.gz", f"{name.upper()}.csv", f"{name.upper()}.csv.gz"):
        for p in Path(d).rglob(fn):
            f = gzip.open(p, "rt", encoding="utf-8-sig") if p.suffix == ".gz" else open(p, encoding="utf-8-sig")
            r = csv.DictReader(f)
            r.fieldnames = [c.strip().lower() for c in r.fieldnames]
            return r
    raise FileNotFoundError(f"{name} 테이블을 {d}에서 못 찾음")


def col(row, key):
    for c in COLS[key]:
        if c in row and row[c] not in (None, ""):
            return row[c]
    return None


def ts(s):
    s = s.strip()[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def unit_type(careunit, keywords):
    cu = (careunit or "").upper()
    for utype, kws in keywords.items():
        if any(k.upper() in cu for k in kws):
            return utype
    return None


def build(d, max_per_unit, hours):
    cfg = json.loads((ROOT / "concepts.json").read_text())
    vitals = {k: set(cfg[k]) for k in ("hr", "map", "spo2", "rr")}
    item2var = {i: k for k, ids in vitals.items() for i in ids}
    cpr_ids, vent_ids, pressor_ids = set(cfg["cpr"]), set(cfg["vent"]), set(cfg["pressor"])

    stays, counts, unknown = {}, {}, {}
    for row in open_table(d, "icustays"):
        cu = col(row, "unit")
        ut = unit_type(cu, cfg["careunit_keywords"])
        if ut is None:
            unknown[cu] = unknown.get(cu, 0) + 1
            continue
        if counts.get(ut, 0) >= max_per_unit:
            continue
        t0 = ts(col(row, "intime") or "")
        if t0 is None:
            continue
        counts[ut] = counts.get(ut, 0) + 1
        stays[col(row, "stay")] = {"ut": ut, "t0": t0, "cu": cu, "obs": {}, "cpr": [], "vent": False, "pressor": False}
    print("병동별 선택:", counts)
    if unknown:
        print("병동 분류 못한 careunit (concepts.json 키워드 추가 필요):", unknown)

    horizon = hours * 60
    n = horizon // STEP

    def rel(row, s):
        t = ts(col(row, "time") or "")
        if t is None:
            return None
        m = (t - s["t0"]).total_seconds() / 60
        return m if 0 <= m < horizon else None

    for row in open_table(d, "chartevents"):
        s = stays.get(col(row, "stay"))
        var = item2var.get(row.get("itemid"))
        if s is None or var is None:
            continue
        m = rel(row, s)
        try:
            v = float(col(row, "num"))
        except (TypeError, ValueError):
            continue
        if m is not None:
            s["obs"].setdefault(var, []).append((m, v))

    for row in open_table(d, "datetimeevents"):
        s = stays.get(col(row, "stay"))
        iid = row.get("itemid")
        if s is None or iid not in cpr_ids | vent_ids:
            continue
        m = rel(row, s)
        if m is None:
            continue
        if iid in cpr_ids:
            s["cpr"].append(int(m))
        else:
            s["vent"] = True

    if pressor_ids:
        try:
            for row in open_table(d, "inputevents"):
                s = stays.get(col(row, "stay"))
                if s is not None and row.get("itemid") in pressor_ids:
                    s["pressor"] = True
        except FileNotFoundError:
            pass

    pool = []
    for sid, s in stays.items():
        if "hr" not in s["obs"]:
            continue
        series, last_t = {}, 0
        for var in ("hr", "map", "spo2", "rr"):
            pts = sorted(s["obs"].get(var, []))
            out, j, last = [], 0, None
            for i in range(n):
                while j < len(pts) and pts[j][0] <= i * STEP:
                    last = pts[j]
                    j += 1
                # 60분 넘게 새 측정이 없으면 값 없음(None)
                out.append(round(last[1]) if last and i * STEP - last[0] <= 60 else None)
            series[var] = out
            if pts:
                last_t = max(last_t, pts[-1][0])
        k = min(n, int(last_t // STEP) + 1)
        series = {v: a[:k] for v, a in series.items()}
        pool.append({
            "pid": f"K-{sid}", "unit_type": s["ut"], "careunit": s["cu"],
            "age": None, "sex": None, "dx": s["cu"],
            "vent": s["vent"], "pressor": s["pressor"],
            "step": STEP, "los_min": k * STEP, "series": series,
            "cpr": sorted(set(s["cpr"])), "source": "K-MIMIC",
        })
    return pool


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--max-per-unit", type=int, default=200)
    ap.add_argument("--hours", type=int, default=24)
    a = ap.parse_args()
    pool = build(a.dir, a.max_per_unit, a.hours)
    out = ROOT / "data" / "pool_kmimic.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(pool, ensure_ascii=False))
    print(f"{len(pool)}명 → {out}")
