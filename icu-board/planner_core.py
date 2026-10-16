"""Synthetic ICU reservation workflow; stdlib only, no clinical model.

Clinical courses are fixed synthetic replay. Arrival schedules, ICU probabilities,
and reservation horizons are explicit scenario assumptions. Booking a bed does
not change a patient's course or establish treatment benefit. Future clinical
events stay private; known schedules and approved resource bookings are public.
The HTTP layer must serialize calls when sharing an instance between threads.
"""
import copy
import hashlib
import math
import random
from datetime import datetime, timedelta, timezone


START = datetime(2026, 10, 16, 7, 0, tzinfo=timezone(timedelta(hours=9)))
UNIT = "DEMO-ICU"
POLICIES = ("first_available", "optimized")
SHIFT_CAPACITY = {"D": 3, "E": 3, "N": 2}


class PlannerError(Exception):
    def __init__(self, message, code, status=400):
        super().__init__(message)
        self.message, self.code, self.status = message, code, status

    def as_dict(self):
        return {"error": self.message, "code": self.code}


def _overlap(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end


class PlannerHospital:
    """One three-bed virtual ICU with revision-checked human approvals."""
    def __init__(self, seed=1):
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise PlannerError("seed는 정수여야 합니다.", "invalid_seed")
        self.seed, self.t, self.revision = seed, 0, 1
        self._patients, self._plans, self._reservations, self._audit = {}, {}, [], []
        self._plan_seq, self._reservation_seq, self._emergency_seq = 0, 0, 0
        self.staff_capacity = dict(SHIFT_CAPACITY)
        self._beds = [{"id": f"ICU-{i}", "unit": UNIT, "staffed": True} for i in range(1, 4)]
        self._fixtures()
        self._log("scenario_started", {"seed": seed, "source": "synthetic_operational_scenario"})

    def _rng(self, purpose, identity):
        return random.Random(f"planner|{self.seed}|{purpose}|{identity}")

    def _fixtures(self):
        # Reservation assumptions are declared independently of replay outcomes.
        rows = [
            ("P001", "기존 ICU 환자 A", None, None, (2, 6), 1.0, 1, 0),
            ("P002", "기존 ICU 환자 B", None, None, (48, 72), 1.0, 1, 0),
            ("P003", "금요일 수술 A", 120, 240, (12, 20), .75, 1, 240),
            ("P004", "금요일 수술 B", 240, 330, (2, 4), .80, 5, 240),
            ("P005", "금요일 수술 C", 360, 420, (4, 6), .65, 2, 360),
            ("P006", "금요일 수술 D", 480, 540, (8, 10), .85, 3, 360),
            ("P007", "월요일 수술 E", 4380, 4470, (8, 12), .60, 2, 240),
            ("P008", "월요일 수술 F", 4500, 4560, (4, 8), .30, 1, 240),
        ]
        for pid, label, start, end, bounds, probability, priority, delay in rows:
            assumption_rng = self._rng("scenario_assumptions", pid)
            upper = bounds[1] - (assumption_rng.randrange(2) if pid == "P003" else 0)
            assumption = {"source": "scenario_assumption", "icu_probability": probability,
                          "icu_los_range_hours": [bounds[0], upper],
                          "los_p50_min": (bounds[0] + upper) * 30, "los_p90_min": upper * 60,
                          "nurse_units": 1, "priority_weight": priority, "max_delay_minutes": delay,
                          "validated": False, "live_model": False,
                          "note": "합성 운영 가정. 확률·p50/p90 표기는 검증된 임상 예측이나 보정된 분위수가 아닙니다."}
            patient = {"id": pid, "patient_id": pid, "label": label, "unit": UNIT,
                       "elective": start is not None, "scheduled_start_t": start, "scheduled_end_t": end,
                       "desired_start": end if end is not None else 0,
                       "scenario_assumption": assumption, "_events": self._clinical_events(pid, start, end)}
            self._patients[pid] = patient
        self._add_reservation("P001", "ICU-1", 0, 360, "initial_scenario_assumption")
        self._add_reservation("P002", "ICU-2", 0, 4320, "initial_scenario_assumption")

    def _clinical_events(self, pid, start, end):
        # This independent replay stream is never consulted by the predictor.
        rng = self._rng("private_synthetic_clinical_course", pid)
        baseline = {"hr": rng.randint(68, 90), "map": rng.randint(72, 88), "spo2": 97, "rr": 16}
        if start is None:
            exit_t = 330 if pid == "P001" else 3900
            return [{"t": 0, "type": "icu_observation", "text": "합성 ICU 경과 관찰", "phase": "icu", "vitals": baseline},
                    {"t": exit_t, "type": "icu_exit", "text": "합성 경과에서 ICU 퇴실이 관찰됨", "phase": "ward", "vitals": baseline}]
        actual_end = end + rng.choice((0, 15, 30))
        actual_hours = {"P003": 12, "P004": 2, "P005": 4, "P006": 8, "P007": 10, "P008": 0}[pid]
        events = [{"t": 0, "type": "preop_observation", "text": "합성 수술 전 관찰", "phase": "preop", "vitals": baseline},
                  {"t": start, "type": "anesthesia_started", "text": "합성 경과에서 마취 시작이 관찰됨", "phase": "intraop", "vitals": baseline},
                  {"t": start + 30, "type": "intraop_observation", "text": "합성 수술 중 활력 관찰", "phase": "intraop",
                   "vitals": {"hr": baseline["hr"] + 10, "map": baseline["map"] - 8, "spo2": 96, "rr": 14}},
                  {"t": actual_end, "type": "recovery_started", "text": "합성 경과에서 회복 단계가 관찰됨", "phase": "recovery", "vitals": baseline}]
        if actual_hours:
            events += [{"t": actual_end + 30, "type": "icu_observation", "text": "고정 합성 경과의 ICU 단계 관찰", "phase": "icu", "vitals": baseline},
                       {"t": actual_end + 30 + actual_hours * 60, "type": "icu_exit", "text": "합성 경과에서 ICU 퇴실이 관찰됨", "phase": "ward", "vitals": baseline}]
        else:
            events.append({"t": actual_end + 90, "type": "ward_observation", "text": "합성 경과에서 일반병동 단계가 관찰됨", "phase": "ward", "vitals": baseline})
        return sorted(events, key=lambda row: row["t"])

    def _calendar_at(self, minute):
        date = START + timedelta(minutes=minute)
        number = int(minute // 480) % 3
        code, label = (("D", "Day"), ("E", "Evening"), ("N", "Night"))[number]
        return {"datetime": date.isoformat(timespec="minutes"), "weekday": date.strftime("%A"),
                "weekday_index": date.weekday(), "weekend": date.weekday() >= 5,
                "elective_surgery_open": date.weekday() < 5,
                "shift": {"code": code, "label": label, "cycle": int(minute // 1440),
                          "elapsed_min": int(minute % 480), "remaining_min": 480 - int(minute % 480),
                          "staff_capacity": self.staff_capacity[code], "source": "scenario_assumption"}}

    def _public_patient(self, patient):
        result = {key: copy.deepcopy(value) for key, value in patient.items() if not key.startswith("_")}
        events = [copy.deepcopy(row) for row in patient["_events"] if row["t"] <= self.t]
        result["observed_events"] = events
        result["phase"] = events[-1]["phase"] if events else "no_observation"
        measured = [row for row in events if "vitals" in row]
        result["vitals"] = copy.deepcopy(measured[-1]["vitals"]) if measured else None
        result["vitals_observed_t"] = measured[-1]["t"] if measured else None
        result["prediction"] = {key: result["scenario_assumption"].get(key) for key in
                                ("source", "icu_probability", "los_p50_min", "los_p90_min", "validated", "live_model")}
        result["prediction"]["as_of_t"] = self.t
        result["reservable"] = result["phase"] not in ("ward", "discharged") and not self._patient_reserved(patient["id"])
        result["source"] = "synthetic_scenario"
        result["clinical_replay"] = "fixed_synthetic_course_not_modified_by_booking"
        return result

    def get_patient(self, patient_id):
        patient = self._patients.get(patient_id) if isinstance(patient_id, str) else None
        if patient is None:
            raise PlannerError("합성 환자를 찾을 수 없습니다.", "patient_not_found", 404)
        return self._public_patient(patient)

    def _reservation_view(self, row):
        result = copy.deepcopy(row)
        if result["status"] != "cancelled":
            result["status"] = "completed" if row["end_t"] <= self.t else "active" if row["start_t"] <= self.t else "confirmed"
        return result

    def state(self):
        beds = copy.deepcopy(self._beds)
        for bed in beds:
            active = [row for row in self._reservations if row["bed_id"] == bed["id"]
                      and row["status"] != "cancelled" and row["start_t"] <= self.t < row["end_t"]]
            bed["patient_id"] = active[0]["patient_id"] if active else None
            bed["status"] = "reserved_active" if active else "available"
            bed["occupancy_basis"] = "approved_virtual_resource_reservations"
            bed["shared_staff_capacity"] = self._calendar_at(self.t)["shift"]["staff_capacity"]
        return {"revision": self.revision, "t": self.t, "calendar": self._calendar_at(self.t),
                "patients": [self._public_patient(row) for row in self._patients.values()], "beds": beds,
                "reservations": [self._reservation_view(row) for row in self._reservations],
                "plans": copy.deepcopy(list(self._plans.values())), "audit": copy.deepcopy(self._audit),
                "scenario": {"source": "synthetic_operational_scenario", "seed": self.seed,
                             "live_model_evaluated": False, "clinical_prediction_validated": False,
                             "icu_capacity": 3, "staff_capacity_by_shift": dict(self.staff_capacity),
                             "weekend_elective_cases": 0,
                             "note": "예약·대기 비교용 합성 운영 시뮬레이션. 실제 환자 동시 점유나 치료 효과를 재현하지 않습니다."}}

    def _log(self, action, details, status="ok"):
        self._audit.append({"id": f"A-{len(self._audit) + 1}", "t": self.t,
                            "datetime": self._calendar_at(self.t)["datetime"], "revision": self.revision,
                            "action": action, "status": status, "details": copy.deepcopy(details)})

    def _patient_reserved(self, patient_id):
        return any(row["patient_id"] == patient_id and row["status"] != "cancelled"
                   and row["end_t"] > self.t for row in self._reservations)

    def _check_calendar(self, patient):
        if patient["elective"]:
            start = patient.get("scheduled_start_t")
            if not isinstance(start, (int, float)) or not self._calendar_at(start)["elective_surgery_open"]:
                raise PlannerError("주말 정규 수술 일정은 허용하지 않습니다. ICU 경과·교대는 계속 진행합니다.", "weekend_elective", 409)

    def _fit_reason(self, bed_id, start, end, nurse_units=1, extra=None):
        bed = next((row for row in self._beds if row["id"] == bed_id), None)
        if bed is None or not bed["staffed"]:
            return "bed_unavailable"
        rows = [row for row in self._reservations if row["status"] != "cancelled"] + list(extra or [])
        if any(row["bed_id"] == bed_id and _overlap(start, end, row["start_t"], row["end_t"]) for row in rows):
            return "bed_overlap"
        points = {start}
        points.update(x for row in rows for x in (row["start_t"], row["end_t"]) if start < x < end)
        points.update(range((int(start) // 480 + 1) * 480, int(math.ceil(end)), 480))
        for point in sorted(points):
            used = sum(row.get("nurse_units", 1) for row in rows if row["start_t"] <= point < row["end_t"])
            if used + nurse_units > self._calendar_at(point)["shift"]["staff_capacity"]:
                return "staff_capacity"
        return None

    def _candidates(self, patient, extra=None):
        assumed = patient["scenario_assumption"]
        duration = assumed.get("los_p90_min")
        desired = patient["desired_start"]
        earliest, latest = max(self.t, desired), desired + assumed["max_delay_minutes"]
        if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
            raise PlannerError("유효한 ICU 예약시간 운영 가정이 필요합니다.", "missing_duration")
        candidates = []
        for start in range(int(math.ceil(earliest)), int(latest) + 1, 15):
            for bed in self._beds:
                if not self._fit_reason(bed["id"], start, start + duration, assumed["nurse_units"], extra):
                    candidates.append((start, start + duration, bed["id"]))
        return candidates

    def _candidate_score(self, patient, candidate):
        start, end, bed_id = candidate
        score = max(0, start - patient["desired_start"]) * patient["scenario_assumption"]["priority_weight"]
        extra = [{"start_t": start, "end_t": end, "bed_id": bed_id,
                  "nurse_units": patient["scenario_assumption"]["nurse_units"]}]
        # Small lookahead rule, not a solver. It uses known schedules and declared
        # assumptions only, never future clinical events or realized lengths.
        for other in self._patients.values():
            if (other["id"] == patient["id"] or not other["elective"] or self._patient_reserved(other["id"])
                    or not patient["desired_start"] <= other["desired_start"] <= patient["desired_start"] + 480):
                continue
            possible = self._candidates(other, extra)
            wait = min(row[0] for row in possible) - other["desired_start"] if possible else 1440
            score += max(0, wait) * other["scenario_assumption"]["priority_weight"]
        return score

    def propose(self, patient_id, policy="optimized"):
        if policy not in POLICIES:
            raise PlannerError("first_available 또는 optimized 규칙을 선택하세요.", "unknown_policy")
        self.get_patient(patient_id)
        patient = self._patients[patient_id]
        self._check_calendar(patient)
        if self._patient_reserved(patient_id):
            raise PlannerError("이 환자의 ICU 예약이 이미 있습니다.", "duplicate_reservation", 409)
        if self.get_patient(patient_id)["phase"] in ("ward", "discharged"):
            raise PlannerError("현재 관찰에서 ICU 경과가 끝난 합성 환자입니다.", "course_completed", 409)
        candidates = self._candidates(patient)
        if not candidates:
            self._log("proposal_rejected", {"patient_id": patient_id, "policy": policy, "code": "no_feasible"}, "rejected")
            raise PlannerError("운영 가정의 최대 대기시간 안에 병상·3교대 인력을 동시에 확보할 수 없습니다.", "no_feasible", 409)
        if policy == "first_available":
            selected = min(candidates, key=lambda row: (row[0], row[2]))
            score, rule = None, "가장 이른 가용 병상 규칙"
        else:
            selected = min(candidates, key=lambda row: (self._candidate_score(patient, row), row[0], row[2]))
            score, rule = self._candidate_score(patient, selected), "알려진 일정의 우선순위·대기시간 비교 규칙 (솔버·LLM 아님)"
        start, end, bed_id = selected
        self._plan_seq += 1
        plan = {"id": f"PLAN-{self._plan_seq}", "patient_id": patient_id, "revision": self.revision,
                "status": "proposed", "bed_id": bed_id, "start_t": start, "end_t": end,
                "desired_start": patient["desired_start"], "delay_minutes": max(0, start - patient["desired_start"]),
                "policy": policy, "score": score, "nurse_units": patient["scenario_assumption"]["nurse_units"],
                "source": "scenario_assumption", "reason": f"{rule}. ICU 체류시간은 명시한 운영 가정으로 확보하며 승인 전에는 배정하지 않습니다."}
        self._plans[plan["id"]] = plan
        self._log("plan_proposed", {"plan_id": plan["id"], "patient_id": patient_id, "policy": policy})
        return copy.deepcopy(plan)

    def _plan(self, plan_id):
        plan = self._plans.get(plan_id) if isinstance(plan_id, str) else None
        if plan is None:
            raise PlannerError("예약 제안을 찾을 수 없습니다.", "plan_not_found", 404)
        return plan

    def _add_reservation(self, patient_id, bed_id, start, end, source, plan_id=None, nurse_units=1):
        self._reservation_seq += 1
        reservation = {"id": f"RES-{self._reservation_seq}", "patient_id": patient_id, "bed_id": bed_id,
                       "start_t": start, "end_t": end, "status": "confirmed", "source": source,
                       "plan_id": plan_id, "nurse_units": nurse_units, "unit": UNIT}
        self._reservations.append(reservation)
        return reservation

    def approve(self, plan_id, expected_revision, approver="demo_coordinator"):
        plan = self._plan(plan_id)
        if plan["status"] == "approved":
            raise PlannerError("이미 승인된 제안입니다. 중복 예약하지 않았습니다.", "already_approved", 409)
        if (not isinstance(expected_revision, int) or isinstance(expected_revision, bool)
                or expected_revision != self.revision or plan["revision"] != self.revision or plan["status"] != "proposed"):
            self._log("approval_rejected", {"plan_id": plan_id, "code": "stale_revision"}, "rejected")
            raise PlannerError("제안 이후 상태가 바뀌었습니다. 재조회·재계획·재승인이 필요합니다.", "stale_revision", 409)
        if not isinstance(approver, str) or not approver.strip():
            raise PlannerError("시연 승인자를 지정하세요.", "missing_approver")
        patient = self._patients[plan["patient_id"]]
        self._check_calendar(patient)
        if self._patient_reserved(patient["id"]):
            raise PlannerError("같은 환자에게 이미 예약이 있습니다.", "duplicate_reservation", 409)
        if plan["start_t"] < self.t:
            raise PlannerError("예약 시작 시각이 지났습니다. 새 제안이 필요합니다.", "expired_plan", 409)
        if plan["start_t"] < patient["desired_start"] or plan["start_t"] > patient["desired_start"] + patient["scenario_assumption"]["max_delay_minutes"]:
            raise PlannerError("환자 일정의 예약 시간창과 일치하지 않습니다.", "invalid_window", 409)
        reason = self._fit_reason(plan["bed_id"], plan["start_t"], plan["end_t"], plan["nurse_units"])
        if reason:
            raise PlannerError("병상 또는 해당 시간대 인력을 다시 확보해야 합니다.", reason, 409)
        reservation = self._add_reservation(patient["id"], plan["bed_id"], plan["start_t"], plan["end_t"],
                                            "approved_scenario_assumption", plan_id, plan["nurse_units"])
        self.revision += 1
        plan.update(status="approved", proposed_revision=plan["revision"], revision=self.revision, approver=approver, approved_t=self.t)
        self._log("plan_approved", {"plan_id": plan_id, "reservation_id": reservation["id"], "approver": approver})
        return {"ok": True, "revision": self.revision, "plan": copy.deepcopy(plan), "reservation": self._reservation_view(reservation)}

    def inject_conflict(self, plan_id):
        plan = self._plan(plan_id)
        if plan["status"] != "proposed" or plan["revision"] != self.revision:
            raise PlannerError("현재 제안에만 승인 전 충돌을 주입할 수 있습니다.", "stale_revision", 409)
        reason = self._fit_reason(plan["bed_id"], plan["start_t"], plan["end_t"], plan["nurse_units"])
        if reason:
            raise PlannerError("이미 자원 충돌이 있는 제안입니다.", reason, 409)
        self._emergency_seq += 1
        pid = f"EMG-{self._emergency_seq}"
        # A declared 90-minute competing booking overlaps the proposal without
        # making recovery impossible by occupying all remaining night staffing.
        duration = min(90, plan["end_t"] - plan["start_t"])
        self._patients[pid] = {"id": pid, "patient_id": pid, "label": "승인 전 선점 합성 환자", "unit": UNIT,
                               "elective": False, "scheduled_start_t": None, "scheduled_end_t": None,
                               "desired_start": plan["start_t"],
                               "scenario_assumption": {"source": "scenario_assumption", "icu_probability": 1.0,
                                                       "los_p50_min": duration, "los_p90_min": duration,
                                                       "icu_los_range_hours": [duration / 60, duration / 60], "nurse_units": 1,
                                                       "priority_weight": 1, "max_delay_minutes": 0, "validated": False,
                                                       "live_model": False, "note": "충돌 검증용 합성 응급 자원 요청"},
                               "_events": [{"t": self.t, "type": "conflict_demand_announced",
                                            "text": "합성 응급 자원 예약 요청이 알려짐", "phase": "resource_request"}]}
        reservation = self._add_reservation(pid, plan["bed_id"], plan["start_t"], plan["start_t"] + duration, "injected_synthetic_conflict")
        self.revision += 1
        plan["status"] = "stale"
        self._log("conflict_injected", {"plan_id": plan_id, "reservation_id": reservation["id"], "patient_id": pid})
        return {"ok": True, "plan_id": plan_id, "revision": self.revision, "reservation": self._reservation_view(reservation)}

    def replan(self, plan_id):
        old = self._plan(plan_id)
        if old["status"] == "approved":
            raise PlannerError("승인된 예약을 재계획하려면 별도 취소 절차가 필요합니다.", "already_approved", 409)
        result = self.propose(old["patient_id"], old["policy"])
        old["status"] = "superseded"
        self._plans[result["id"]]["replaces_plan_id"] = plan_id
        self._log("plan_replanned", {"old_plan_id": plan_id, "new_plan_id": result["id"]})
        return copy.deepcopy(self._plans[result["id"]])

    def advance(self, minutes):
        if not isinstance(minutes, int) or isinstance(minutes, bool) or not 0 <= minutes <= 10080:
            raise PlannerError("진행 시간은 0~10080분 정수여야 합니다.", "invalid_minutes")
        if not minutes:
            return self.state()
        self.t += minutes
        # Observed course completion may release a reserved horizon early.
        # No future discharge time is used to plan that horizon.
        for patient in self._patients.values():
            exits = [row["t"] for row in patient["_events"] if row["t"] <= self.t
                     and row["type"] in ("icu_exit", "ward_observation")]
            if not exits:
                continue
            exit_t = min(exits)
            for row in self._reservations:
                if row["patient_id"] == patient["id"] and row["status"] != "cancelled" and row["end_t"] > exit_t:
                    if row["start_t"] >= exit_t:
                        row["status"] = "cancelled"
                    else:
                        row["end_t"] = exit_t
                    row["release_source"] = "observed_synthetic_course"
        self.revision += 1
        self._log("time_advanced", {"minutes": minutes, "current_shift": self._calendar_at(self.t)["shift"]["code"]})
        return self.state()

    def constraint_report(self):
        """Audit confirmed resource intervals, including past history."""
        rows = [row for row in self._reservations if row["status"] != "cancelled"]
        violations = []
        for i, row in enumerate(rows):
            if row["start_t"] >= row["end_t"] or row["bed_id"] not in {bed["id"] for bed in self._beds}:
                violations.append({"code": "invalid_interval", "reservation_id": row["id"]})
            for other in rows[i + 1:]:
                if _overlap(row["start_t"], row["end_t"], other["start_t"], other["end_t"]):
                    if row["bed_id"] == other["bed_id"]:
                        violations.append({"code": "bed_overlap", "ids": [row["id"], other["id"]]})
                    if row["patient_id"] == other["patient_id"]:
                        violations.append({"code": "patient_overlap", "ids": [row["id"], other["id"]]})
        points = {x for row in rows for x in (row["start_t"], row["end_t"])}
        if rows:
            points.update(range(0, int(max(row["end_t"] for row in rows)) + 1, 480))
        for point in sorted(points):
            active = [row for row in rows if row["start_t"] <= point < row["end_t"]]
            units = sum(row.get("nurse_units", 1) for row in active)
            if len(active) > len(self._beds) or units > self._calendar_at(point)["shift"]["staff_capacity"]:
                violations.append({"code": "resource_capacity", "t": point, "bed_count": len(active), "nurse_units": units})
        for patient in self._patients.values():
            try:
                self._check_calendar(patient)
            except PlannerError:
                violations.append({"code": "weekend_elective", "patient_id": patient["id"]})
        return {"ok": not violations, "violations": violations, "source": "synthetic_resource_constraints",
                "live_model_evaluated": False}

    def fixture_signature(self):
        import json
        fixtures = [{key: row[key] for key in ("id", "scheduled_start_t", "scheduled_end_t", "scenario_assumption")}
                    for row in self._patients.values() if not row["id"].startswith("EMG-")]
        return hashlib.sha256(json.dumps(fixtures, sort_keys=True).encode()).hexdigest()
