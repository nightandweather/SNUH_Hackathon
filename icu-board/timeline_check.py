"""Aggregate-only CSV time checks to run inside the approved data environment.

Does not establish de-identification rules or recover an original hospital calendar.
No raw patient identifiers, values, dates or paths are written to the report.
"""
import argparse
import csv
from datetime import datetime
import gzip
import json
from pathlib import Path
import sys


def rows(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as stream:
        yield from csv.DictReader(stream)


def stamp(value):
    return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))


def audit(args):
    counts = {key: 0 for key in ("admissions", "invalid_admission_time", "duplicate_stay_keys",
                                "events_checked", "unmatched_stay", "patient_mismatch",
                                "invalid_event_time", "incomparable_timezone", "before_icu_admission",
                                "after_icu_discharge", "within_icu_interval")}
    admissions = {}
    required = {args.patient_column, args.stay_column, args.anchor_column, args.end_column}
    for row in rows(args.admissions):
        if not required.issubset(row):
            raise ValueError("admission_columns_missing")
        counts["admissions"] += 1
        key = row[args.stay_column]
        if key in admissions:
            counts["duplicate_stay_keys"] += 1
            admissions[key] = None  # never pick an arbitrary admission for an ambiguous key
            continue
        try:
            begin, end = stamp(row[args.anchor_column]), stamp(row[args.end_column])
            if begin > end:
                raise ValueError("reversed interval")
        except (ValueError, TypeError):
            counts["invalid_admission_time"] += 1
            admissions[key] = None
            continue
        admissions[key] = (row[args.patient_column], begin, end)
    required_events = {args.patient_column, args.stay_column, args.time_column}
    limit_reached = False
    for row in rows(args.events):
        if not required_events.issubset(row):
            raise ValueError("event_columns_missing")
        if args.max_rows and counts["events_checked"] >= args.max_rows:
            limit_reached = True
            break
        counts["events_checked"] += 1
        interval = admissions.get(row[args.stay_column])
        if interval is None:
            counts["unmatched_stay"] += 1
            continue
        patient, begin, end = interval
        if row[args.patient_column] != patient:
            counts["patient_mismatch"] += 1
            continue
        try:
            event = stamp(row[args.time_column])
        except (ValueError, TypeError):
            counts["invalid_event_time"] += 1
            continue
        try:
            category = ("before_icu_admission" if event < begin else
                        "after_icu_discharge" if event > end else "within_icu_interval")
        except TypeError:
            counts["incomparable_timezone"] += 1
            continue
        counts[category] += 1
    return {"scope": "aggregate_csv_time_checks", "counts": counts, "partial": limit_reached,
            "time_transform_verified": False, "cross_patient_calendar_verified": False,
            "limitation": "시간 변환 규칙·사건시각/가용시각 의미는 제공 문서로 별도 확인해야 합니다.",
            "outside_interval_note": "입퇴실 구간 밖 기록이 모두 오류인 것은 아닙니다. 제공자 정의로 확인하세요."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admissions", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--patient-column", default="subject_id")
    parser.add_argument("--stay-column", default="stay_id")
    parser.add_argument("--time-column", default="charttime")
    parser.add_argument("--anchor-column", default="intime")
    parser.add_argument("--end-column", default="outtime")
    parser.add_argument("--max-rows", type=int, default=10000)
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.max_rows < 0:
        parser.error("max-rows must be nonnegative; 0 scans all rows")
    try:
        report = audit(args)
        code = 0
    except (OSError, ValueError, csv.Error, UnicodeError):
        report = {"scope": "aggregate_csv_time_checks", "status": "failed",
                  "error": "파일 읽기·컬럼명·시간 형식을 확인하세요. 원문 자료는 출력하지 않습니다."}
        code = 2
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
