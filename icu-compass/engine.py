"""가상 병원 시뮬레이션: 층별 ICU, 간호사 위치, 환자 자동 입실, 이벤트 감지, 간호사 배치.

시간 단위는 1분. 정책 두 가지:
- fixed: 기존 방식. 간호사 1명이 환자 2명 고정, 이벤트는 담당 간호사가 먼저 대응,
         심정지는 책임간호사 즉시 + 방송 후(2분) 같은 병동 간호사 합류, 다른 병동 지원 없음.
- auto : 앱 방식. 같은 ICU 안에서 가까운 비어있는 간호사를 배치,
         자리 비운 간호사의 환자는 같은 병동에서 부담이 가장 적은 간호사가 대신 봄.

응급 주입 활력, 필요 인원, 해소 시간, ICU당 MD 1명은 시연 가정이다.
실제 환자 원자료와 별도이며 의사 지시·처방이나 임상 예측을 생성하지 않는다.
"""
import copy
import clinical_evidence
import json
import math
import os
import random
from collections import deque
from pathlib import Path

ROOT = Path(__file__).parent
UNIT_W, UNIT_H, CORRIDOR = 32.0, 14.0, 6.0  # m
WALK = 60.0  # m/분
ELEVATOR_MIN = 2.0
EVENT = {
    "arrest": {"label": "Cardiac arrest", "need": 3, "dur": 30},
    "det": {"label": "Rapid deterioration", "need": 1, "dur": 15},
    "focus": {"label": "Focused care 1:1", "need": 1, "dur": None},  # 위험지표가 내려갈 때까지
}
RISK_ON, RISK_OFF = 70, 55  # 위험지표 진입/해제 기준 (히스테리시스)
CARE_MIN_PER_HR = {1: 10, 2: 20, 3: 35, 4: 50}
REFRACTORY = 60
FIXED_PAGE_DELAY = 2  # 심정지 방송 후 같은 병동 합류까지
FIXED_NOTICE_DELAY = 4  # 담당 간호사가 바쁠 때 다른 간호사가 알아채기까지
ROUND_MIN = 15  # 일상 순회 간격의 중심값 (시연 가정)
ROUND_INTERVAL = (ROUND_MIN - 5, ROUND_MIN + 5)
AUTO_BREAK_CHECK_INTERVAL = (10, 20)
FIXED_BREAK_JITTER = 10  # 고정 휴식 예정 시각의 개인별 ±분 편차
DIAGNOSTIC_DONE = {"specimen_sent", "image_available", "cancelled"}
DIAGNOSTIC_LABEL = {"blood_draw": "Blood draw", "portable_xray": "Portable X-ray"}
VITAL_HISTORY_MIN = 1440
SHIFT_MIN = 480  # 8시간 3교대
DEFAULT_SHIFTS = (
    {"code": "D", "label": "Day", "start_clock": "07:00", "end_clock": "15:00"},
    {"code": "E", "label": "Evening", "start_clock": "15:00", "end_clock": "23:00"},
    {"code": "N", "label": "Night", "start_clock": "23:00", "end_clock": "07:00"},
)
HANDOVER_MIN = 15
EMERGENCY_SCENARIOS = {
    "bleeding": {"kind": "det", "label": "Suspected postoperative bleeding (simulation)",
                 "values": {"hr": 128, "sbp": 86, "map": 58, "rr": 26},
                 "findings": ["Fictional postoperative scenario; surgery type and time are not source records.",
                              "Bright-red drain output: 180 mL in the last hour versus 30 mL in the preceding hour (fictional).",
                              "New blood staining on the wound dressing (fictional).",
                              "Awake and able to speak; reports dizziness and palpitations (fictional patient role-play).",
                              "Hemoglobin, lactate, coagulation results and bleeding source are unknown."]},
    "code_blue": {"kind": "arrest", "label": "Code blue(Simulation)",
                  "values": {"hr": 0, "map": 0, "rr": 0, "spo2": None}},
    "hypoxia": {"kind": "det", "label": "Acute hypoxia (simulation)",
                "values": {"spo2": 82, "rr": 38}},
    "hypotension": {"kind": "det", "label": "Severe hypotension (simulation)",
                    "values": {"map": 45, "hr": 125}},
}
# 피로도 0~100 (분당 증가량). 근무 8시간 동안 경증 2명 ≈ 30, 중증 2명 ≈ 60, 사건이 겹치면 80+
FATIGUE_BASE = 0.03
FATIGUE_CARE = 0.08  # 간호 부담(분/분) 1당
FATIGUE_EVENT = {"arrest": 0.5, "det": 0.3, "focus": 0.25}
FATIGUE_MOVE = 0.05
FATIGUE_REST = 0.6  # 휴식 중 분당 회복 (30분 휴식 ≈ 18)
FATIGUE_WARN, FATIGUE_HIGH = 60, 75
BREAK_MIN = 30
FIXED_BREAK = {1: 300, 2: 330, 3: 360, 4: 390}  # 기존 방식: 근무 시작 후 정해진 시각에 식사·휴식
FIXED_BUDDY = {1: 2, 2: 1, 3: 4, 4: 3}  # 기존 방식: 휴식 때 짝꿍이 대신 봄


def load_config():
    config = json.loads((ROOT / "units.json").read_text())
    if os.environ.get("ICU_COHORT") == "surgical":
        from cohort import surgical_config
        return surgical_config(config)
    return config


def load_pool(source="synth"):
    p = ROOT / "data" / f"pool_{source}.json"
    if not p.exists() and source == "synth":
        import synth
        p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps(synth.build(), ensure_ascii=False))
    pool = json.loads(p.read_text())
    if os.environ.get("ICU_COHORT") == "surgical":
        from cohort import surgical_pool
        return surgical_pool(pool)
    return pool


def dist(a, b):
    return math.hypot(a[1] - b[1], a[2] - b[2])


class Hospital:
    def __init__(self, pool, policy="auto", seed=1, occupancy=0.75, arrivals_per_unit_shift=2.0, cfg=None):
        self.cfg = cfg or load_config()
        self.policy = policy
        self.rng = random.Random(seed)
        self._timing_seed = seed  # routine scheduling must never consume patient randomness
        self.t = 0
        self.shift_schedule = copy.deepcopy(self.cfg.get("shifts", DEFAULT_SHIFTS))
        self.start_minute = self._clock_minutes(self.cfg["start_clock"])
        self._validate_shifts()
        self._initial_cycle = (self.start_minute - self._shift_start) // 1440
        self._active_shift_number = self._shift_number(0)
        self.arrival_p = arrivals_per_unit_shift / 480
        self.by_type = {}
        for p in pool:
            self.by_type.setdefault(p["unit_type"], []).append(p)
        self.units, self.beds, self.nurses, self.floors = {}, {}, {}, []
        self.incidents, self.log = [], []
        self.unattended = {"all": 0, "high": 0}
        self.last_shift = None  # 직전 근무조의 종료 통계 (직원별 관측 업무·피로도)
        self.shift_history = []
        self.last_handover = None
        self.handover_history = []
        self.care_actions = []
        self.activities = []
        self.diagnostics = []
        self._diagnostic_work = {}
        self._did = 0
        self._shift_started_t = 0
        self._iid = 0
        self._build_layout()
        initial_shift = self._shift_at(0)
        self.roster = [{"staff_id": self._staff_id(shift["code"], n["id"]),
                        "slot_id": n["id"], "unit": n["unit"], "role": n["role"],
                        "shift_code": shift["code"], "shift_label": shift["label"]}
                       for shift in self.shift_schedule for n in self.nurses.values()]
        for n in self.nurses.values():
            n.update(staff_id=self._staff_id(initial_shift["code"], n["id"]),
                     shift_code=initial_shift["code"], shift_label=initial_shift["label"])
        # Independent demonstration MD roster; not the nurses' three-shift rota.
        self.doctors = {f"MD-{unit['id']}": {"id": f"MD-{unit['id']}", "unit": unit["id"],
                                           "role": "Unit/on-call physician (simulation)", "pos": unit["station"],
                                           "path": [], "status": "available", "incident": None}
                        for unit in self.units.values()}
        self._init_timing()
        self._initial_census(occupancy)

    @staticmethod
    def _clock_minutes(clock):
        try:
            hour, minute = map(int, clock.split(":"))
        except (AttributeError, ValueError) as exc:
            raise ValueError("Clock must have HH:MM format") from exc
        if not 0 <= hour < 24 or not 0 <= minute < 60:
            raise ValueError("Clock must be between 00:00 and 23:59")
        return hour * 60 + minute

    def _validate_shifts(self):
        if not isinstance(self.shift_schedule, (list, tuple)) or len(self.shift_schedule) != 3:
            raise ValueError("Exactly three eight-hour shifts are required")
        if [shift.get("code") for shift in self.shift_schedule] != ["D", "E", "N"]:
            raise ValueError("Shift order must be D, E, N")
        for index, shift in enumerate(self.shift_schedule):
            start = self._clock_minutes(shift["start_clock"])
            end = self._clock_minutes(shift["end_clock"])
            following = self._clock_minutes(self.shift_schedule[(index + 1) % 3]["start_clock"])
            if (end - start) % 1440 != SHIFT_MIN or end != following:
                raise ValueError("Shifts must cover the day with contiguous eight-hour periods")
        self._shift_start = self._clock_minutes(self.shift_schedule[0]["start_clock"])

    @staticmethod
    def _staff_id(code, slot_id):
        return f"{code}-{slot_id}"

    def _shift_number(self, t):
        return (self.start_minute + int(t) - self._shift_start) // SHIFT_MIN

    def _shift_at(self, t):
        number = self._shift_number(t)
        index = number % 3
        elapsed = (self.start_minute + int(t) - self._shift_start) % SHIFT_MIN
        shift, following = self.shift_schedule[index], self.shift_schedule[(index + 1) % 3]
        return dict(shift, elapsed_min=elapsed, remaining_min=SHIFT_MIN - elapsed,
                    cycle=number // 3 - self._initial_cycle,
                    in_handover=elapsed >= SHIFT_MIN - HANDOVER_MIN,
                    next_code=following["code"], next_label=following["label"],
                    on_duty=len(self.nurses), total_staff=len(self.nurses) * 3)

    def _timing_rng(self, purpose, identity, cycle):
        # Random's string seed is stable across Python processes; hash() is not.
        return random.Random(f"{self._timing_seed!r}|{purpose}|{identity}|{cycle}")

    def _init_timing(self):
        """Stagger routine work for the current people without delaying emergencies.

        These ranges describe a visual simulation, not a clinical rounding or
        break protocol. Separate per-person streams keep the planned routine
        times comparable between policies even when a response skips a round.
        """
        shift = self._shift_at(self.t)
        shift_start_t = self.t - shift["elapsed_min"]
        self._round_rngs = {}
        self._break_check_rngs = {}
        for n in self.nurses.values():
            rounds = self._timing_rng("round", n["staff_id"], shift["cycle"])
            self._round_rngs[n["id"]] = rounds
            n["next_round_t"] = self.t + rounds.randint(1, ROUND_MIN)
            breaks = self._timing_rng("fixed-break", n["staff_id"], shift["cycle"])
            base = FIXED_BREAK.get(n["k"])
            n["fixed_break_t"] = (shift_start_t + base + breaks.randint(-FIXED_BREAK_JITTER, FIXED_BREAK_JITTER)
                                  if base is not None else None)
        for unit in self.units.values():
            checks = self._timing_rng("auto-break", f"{shift['code']}-{unit['id']}", shift["cycle"])
            self._break_check_rngs[unit["id"]] = checks
            unit["next_break_check_t"] = self.t + checks.randint(1, ROUND_MIN)

    def _round_due(self, nurse):
        if self.t < nurse["next_round_t"]:
            return False
        nurse["next_round_t"] = self.t + self._round_rngs[nurse["id"]].randint(*ROUND_INTERVAL)
        return True

    def _break_check_due(self, unit):
        if self.t < unit["next_break_check_t"]:
            return False
        unit["next_break_check_t"] = self.t + self._break_check_rngs[unit["id"]].randint(*AUTO_BREAK_CHECK_INTERVAL)
        return True

    def _rotate_shift(self):
        """Replace the people, retaining duty slots and uninterrupted care paths.

        The minute ending at a boundary belongs to the outgoing staff. Incoming
        staff take over at their predecessor's current position, including an
        active response. This is a simulated bedside handover, not a measured
        roster, location, or clinical handover performance.
        """
        number = self._shift_number(self.t)
        if number == self._active_shift_number:
            return
        outgoing = self.shift_schedule[self._active_shift_number % 3]
        incoming = self.shift_schedule[number % 3]
        staff = [{"staff_id": n["staff_id"], "slot_id": n["id"], "unit": n["unit"],
                  "role": n["role"], "work": n["work"], "incident_min": n["incident_min"],
                  "end_fatigue": n["fatigue"], "peak_fatigue": n["peak"],
                  "over_warn": n["over_warn"], "breaks": n["breaks"]}
                 for n in self.nurses.values()]
        self.last_shift = {"code": outgoing["code"], "label": outgoing["label"],
                           "cycle": self._active_shift_number // 3 - self._initial_cycle,
                           "start_t": self._shift_started_t, "end_t": self.t, "staff": staff}
        self.last_shift["care_actions"] = copy.deepcopy([
            action for action in self.care_actions
            if action["shift_code"] == outgoing["code"] and action["cycle"] == self.last_shift["cycle"]])
        self.last_shift["activities"] = copy.deepcopy([
            action for action in self.activities
            if action["shift_code"] == outgoing["code"] and action["cycle"] == self.last_shift["cycle"]])
        self.shift_history.append(self.last_shift)
        active = [inc for inc in self.incidents if inc["end"] is None]
        patients = []
        for bed in self.beds.values():
            pt = bed["patient"]
            if pt is None:
                continue
            events = [dict(self._incident_json(inc),
                           from_responders=[self.nurses[nid]["staff_id"] for nid in inc["responders"]],
                           to_responders=[self._staff_id(incoming["code"], nid) for nid in inc["responders"]])
                      for inc in active if inc["bed"] == bed["id"]]
            patients.append({"bed": bed["id"], "pid": pt["src"]["pid"], "admit_t": pt["admit_t"], "dx": pt["src"]["dx"],
                             "risk": pt["risk"], "vitals": copy.deepcopy(pt["vitals"]),
                             "observed_vitals": copy.deepcopy(pt.get("observed_vitals", pt["vitals"])),
                             "simulation_override": copy.deepcopy(pt.get("simulation_override")),
                             "abn": list(pt["abn"]), "open_events": events, "actions": self.patient_actions(bed["id"]),
                             "activities": self.patient_activities(bed["id"]),
                             "diagnostics": self.patient_diagnostics(bed["id"]),
                             "receipt": {"status": "pending", "received_by": None, "received_t": None,
                                         "received_clock": None, "questions": []},
                             "from_staff_id": self.nurses[bed["nurse"]]["staff_id"],
                             "to_staff_id": self._staff_id(incoming["code"], bed["nurse"])})
        self.last_handover = {"t": self.t, "clock": self.clock(),
                              "from_code": outgoing["code"], "to_code": incoming["code"],
                              "from_label": outgoing["label"], "to_label": incoming["label"],
                              "patients": patients}
        self.handover_history.append({key: value for key, value in self.last_handover.items()
                                      if key != "patients"})
        self.handover_history[-1].update(patient_count=len(patients), open_event_count=len(active))
        self.handover_history = self.handover_history[-3:]
        for n in self.nurses.values():
            if n["on_break"]:
                self._end_break(n)
            n.update(staff_id=self._staff_id(incoming["code"], n["id"]),
                     shift_code=incoming["code"], shift_label=incoming["label"],
                     fatigue=0.0, peak=0.0, work=0.0, incident_min=0, over_warn=0,
                     breaks=0, on_break=False, break_end=None, round_i=0)
        self._active_shift_number = number
        self._shift_started_t = self.t
        self._init_timing()
        self._log(f"— {outgoing['label']} → {incoming['label']} Shift change: "
                  f"{len(self.nurses)} staff handover records created · awaiting acknowledgement ({len(patients)}Patient, Active events {len(active)} events)")

    def patient_actions(self, bed_id, nurse_id=None):
        """Return only user-entered records for the current admission in this bed.

        Optional nurse_id selects that slot's current person and duty cycle.
        Without that filter, earlier shifts remain available for handover, with
        the actual staff_id on every entry. AI suggestions are never care logs.
        """
        bed = self.beds.get(bed_id)
        pt = bed and bed["patient"]
        if pt is None:
            return []
        nurse = self.nurses.get(nurse_id) if isinstance(nurse_id, str) else None
        if nurse_id is not None and nurse is None:
            return []
        cycle = self._shift_at(self.t)["cycle"]
        return copy.deepcopy([action for action in self.care_actions
                              if action["bed"] == bed_id and action["pid"] == pt["src"]["pid"]
                              and action["admit_t"] == pt["admit_t"]
                              and (nurse_id is None or (action["staff_id"] == nurse["staff_id"]
                                                        and action["cycle"] == cycle))])

    def record_care_action(self, nurse_id, bed_id, text):
        """Record a nurse's own report of completed care, never a verified procedure."""
        if not isinstance(text, str) or not text.strip() or len(text) > 1000:
            raise ValueError("Enter 1–1000 characters describing the care performed.")
        if not isinstance(nurse_id, str) or nurse_id not in self.nurses:
            raise ValueError("Select an on-duty nurse.")
        if not isinstance(bed_id, str) or bed_id not in self.beds or self.beds[bed_id]["patient"] is None:
            raise ValueError("Select an occupied bed.")
        n, bed = self.nurses[nurse_id], self.beds[bed_id]
        responding = any(inc["bed"] == bed_id and inc["end"] is None
                         and nurse_id in inc["responders"] for inc in self.incidents)
        if n["unit"] != bed["unit"] or not (bed["nurse"] == nurse_id or bed_id in n["cover"] or responding
                or (n["role"] == "charge" and n["unit"] == bed["unit"])):
            raise PermissionError("You may record care only for assigned, covered or responding patients, or patients in your ICU as charge nurse.")
        pt = bed["patient"]
        action = {"nurse_id": nurse_id, "staff_id": n["staff_id"], "shift_code": n["shift_code"],
                  "cycle": self._shift_at(self.t)["cycle"], "t": self.t, "clock": self.clock(),
                  "bed": bed_id, "pid": pt["src"]["pid"], "admit_t": pt["admit_t"],
                  "text": text.strip(), "source": "user_entered"}
        self.care_actions.append(action)
        return copy.deepcopy(action)

    def patient_activities(self, bed_id, nurse_id=None):
        """Observed simulator actions, separate from reports of real completed care."""
        bed = self.beds.get(bed_id)
        pt = bed and bed["patient"]
        if pt is None:
            return []
        nurse = self.nurses.get(nurse_id) if isinstance(nurse_id, str) else None
        if nurse_id is not None and nurse is None:
            return []
        cycle = self._shift_at(self.t)["cycle"]
        return copy.deepcopy([entry for entry in self.activities
                              if entry["bed"] == bed_id and entry["pid"] == pt["src"]["pid"]
                              and entry["admit_t"] == pt["admit_t"]
                              and (nurse_id is None or (entry["staff_id"] == nurse["staff_id"]
                                                        and entry["cycle"] == cycle))])

    def _activity(self, nurse_id, bed_id, kind, text, incident_id=None):
        bed, nurse = self.beds[bed_id], self.nurses[nurse_id]
        pt = bed["patient"]
        if pt is None:
            return
        # Work in the minute ending at a boundary still belongs to the old crew.
        self.activities.append({"t": self.t, "clock": self.clock(), "nurse_id": nurse_id,
                                "staff_id": nurse["staff_id"], "shift_code": nurse["shift_code"],
                                "cycle": self._active_shift_number // 3 - self._initial_cycle,
                                "bed": bed_id, "pid": pt["src"]["pid"], "admit_t": pt["admit_t"],
                                "type": kind, "text": text, "source": "simulation_activity",
                                "incident_id": incident_id})

    def _begin_cover(self, nurse_id, bed_id, incident_id=None):
        nurse = self.nurses[nurse_id]
        if self.beds[bed_id]["unit"] != nurse["unit"] or bed_id in nurse["cover"]:
            return
        nurse["cover"].append(bed_id)
        self._activity(nurse_id, bed_id, "cover_start", "Started colleague coverage in simulation", incident_id)

    def request_diagnostic(self, nurse_id, bed_id, kind):
        """Request a workflow demonstration, not an order or a real test result."""
        if not isinstance(kind, str) or kind not in DIAGNOSTIC_LABEL:
            raise ValueError("Select a blood draw or portable X-ray simulation.")
        if not isinstance(nurse_id, str) or nurse_id not in self.nurses:
            raise ValueError("Select an on-duty nurse.")
        if not isinstance(bed_id, str) or bed_id not in self.beds or self.beds[bed_id]["patient"] is None:
            raise ValueError("Select an occupied bed.")
        bed, nurse = self.beds[bed_id], self.nurses[nurse_id]
        responding = any(i["bed"] == bed_id and i["end"] is None and nurse_id in i["responders"]
                         for i in self.incidents)
        if nurse["unit"] != bed["unit"] or not (bed["nurse"] == nurse_id or bed_id in nurse["cover"]
                or responding or nurse["role"] == "charge"):
            raise PermissionError("You may request workflows only for assigned, covered or responding patients, or patients in your ICU as charge nurse.")
        if any(task["kind"] == kind and task["status"] not in DIAGNOSTIC_DONE
               for task in self.patient_diagnostics(bed_id)):
            raise ValueError("A simulation of this diagnostic type is already active for this patient.")
        pt = bed["patient"]
        self._did += 1
        task = {"id": f"DX-{self._did}", "kind": kind, "bed": bed_id, "pid": pt["src"]["pid"],
                "admit_t": pt["admit_t"], "unit": bed["unit"], "nurse_id": nurse_id,
                "requested_by_staff_id": nurse["staff_id"], "requested_t": self.t,
                "requested_clock": self.clock(), "status": "requested", "source": "simulation_workflow",
                "simulated": True, "events": [], "patient_linked": False, "review": None,
                "paused": False, "pause_reason": None}
        if kind == "portable_xray":
            task["image_source"] = "public_nih_example"
        rng = self._timing_rng("diagnostic", f"{task['id']}|{kind}|{bed_id}|{task['pid']}|{task['admit_t']}",
                               self._shift_at(self.t)["cycle"])
        self._diagnostic_work[task["id"]] = {"prep_min": rng.randint(2, 4),
                                            "wait_min": rng.randint(4, 12),
                                            "acquire_min": rng.randint(2, 4), "remaining": None}
        self.diagnostics.append(task)
        self._diagnostic_event(task, "requested", f"{DIAGNOSTIC_LABEL[kind]} workflow simulation requested", nurse_id)
        return copy.deepcopy(task)

    def _same_diagnostic_patient(self, task):
        bed = self.beds.get(task["bed"])
        pt = bed and bed["patient"]
        return bool(pt and pt["src"]["pid"] == task["pid"] and pt["admit_t"] == task["admit_t"])

    def patient_diagnostics(self, bed_id):
        bed = self.beds.get(bed_id) if isinstance(bed_id, str) else None
        if bed is None or bed["patient"] is None:
            return []
        return copy.deepcopy([task for task in self.diagnostics if task["bed"] == bed_id
                              and self._same_diagnostic_patient(task)])

    def diagnostic_task(self, bed_id, task_id):
        if not isinstance(task_id, str):
            raise ValueError("Check the diagnostic simulation ID.")
        task = next((row for row in self.diagnostics if row["id"] == task_id and row["bed"] == bed_id), None)
        if task is None or not self._same_diagnostic_patient(task):
            raise ValueError("Select a diagnostic simulation for the current admission.")
        return copy.deepcopy(task)

    def save_image_review(self, bed_id, task_id, review):
        task_copy = self.diagnostic_task(bed_id, task_id)
        if task_copy["kind"] != "portable_xray" or task_copy["status"] != "image_available":
            raise ValueError("Complete the imaging simulation before reviewing the public example image.")
        if not isinstance(review, dict):
            raise ValueError("Check the image-review result format.")
        saved = copy.deepcopy(review)
        saved.update(image_source="public_nih_example", patient_linked=False)
        task = next(row for row in self.diagnostics if row["id"] == task_id)
        task["review"] = saved
        return copy.deepcopy(task)

    def _diagnostic_event(self, task, status, text, nurse_id=None):
        task["status"] = status
        nurse = self.nurses.get(nurse_id)
        task["events"].append({"t": self.t, "clock": self.clock(), "status": status, "text": text,
                               "staff_id": nurse["staff_id"] if nurse else None,
                               "source": "simulation_activity"})

    def _release_diagnostic_nurse(self, task):
        nurse = self.nurses[task["nurse_id"]]
        if nurse["diagnostic_id"] != task["id"]:
            return
        nurse["diagnostic_id"] = None
        if nurse["incident"] is None and not nurse["on_break"]:
            nurse["status"] = "care"
            nurse["path"] = []
            for mate in self.nurses.values():
                mate["cover"] = [bid for bid in mate["cover"] if bid not in nurse["beds"]]

    def _pause_diagnostic(self, task, reason):
        if task["paused"] and task["pause_reason"] == reason:
            return
        task.update(paused=True, pause_reason=reason)
        self._diagnostic_event(task, task["status"], f"Workflow simulation paused: {reason}", task["nurse_id"])

    def _resume_diagnostic(self, task):
        if not task["paused"]:
            return
        task.update(paused=False, pause_reason=None)
        self._diagnostic_event(task, task["status"], "Workflow simulation resumed", task["nurse_id"])

    def _schedule_diagnostics(self):
        for task in self.diagnostics:
            if task["status"] in DIAGNOSTIC_DONE:
                continue
            if not self._same_diagnostic_patient(task):
                self._release_diagnostic_nurse(task)
                task.update(paused=False, pause_reason=None)
                self._diagnostic_event(task, "cancelled", "Workflow cancelled after discharge or patient change")
                continue
            nurse, bed = self.nurses[task["nurse_id"]], self.beds[task["bed"]]
            bedside_emergency = any(i["bed"] == task["bed"] and i["end"] is None
                                   and i["type"] in ("arrest", "det") for i in self.incidents)
            if task["status"] in ("called", "acquiring"):
                if bedside_emergency:
                    self._pause_diagnostic(task, "Emergency at this bed takes priority")
                else:
                    self._resume_diagnostic(task)
                continue
            if nurse["incident"] is not None or bedside_emergency:
                self._pause_diagnostic(task, "Emergency response takes priority")
                continue
            if nurse["on_break"]:
                self._pause_diagnostic(task, "Nurse on break")
                continue
            if nurse["diagnostic_id"] not in (None, task["id"]):
                self._pause_diagnostic(task, "Nurse is busy with another diagnostic task")
                continue
            reroute = task["paused"] or task["status"] == "requested"
            self._resume_diagnostic(task)
            if task["status"] == "requested":
                nurse["diagnostic_id"] = task["id"]
                self._diagnostic_event(task, "nurse_en_route", "Nurse moving to bed (simulation)", nurse["id"])
                self._activity(nurse["id"], bed["id"], "diagnostic_dispatch",
                               f"In simulation: {DIAGNOSTIC_LABEL[task['kind']]} moving to bed for preparation")
            if self.policy == "auto" and reroute:
                self._cover(nurse["id"], exclude=bed["id"])
            nurse["status"] = "diagnostic"
            if nurse["pos"] != bed["pos"] and (reroute or not nurse["path"]):
                nurse["path"] = [list(p) for p in self.route(nurse["pos"], bed["pos"])[0]]

    def _progress_diagnostics(self):
        for task in self.diagnostics:
            if task["status"] in DIAGNOSTIC_DONE or task["paused"] or task["status"] == "requested":
                continue
            work = self._diagnostic_work[task["id"]]
            nurse, bed = self.nurses[task["nurse_id"]], self.beds[task["bed"]]
            if task["status"] not in ("called", "acquiring"):
                if nurse["incident"] is not None or nurse["on_break"] or nurse["pos"] != bed["pos"] or nurse["path"]:
                    continue
                if task["status"] == "nurse_en_route":
                    status = "collecting" if task["kind"] == "blood_draw" else "preparing"
                    self._diagnostic_event(task, status, "Arrived at bed; blood collection started (simulation)" if status == "collecting"
                                           else "Arrived at bed; imaging preparation started (simulation)", nurse["id"])
                    work["remaining"] = work["prep_min"]
                    continue
            work["remaining"] -= 1
            if work["remaining"] > 0:
                continue
            if task["status"] == "collecting":
                self._diagnostic_event(task, "specimen_sent", "Blood collection and specimen transfer complete (simulation); no laboratory results connected", nurse["id"])
                self._activity(nurse["id"], bed["id"], "diagnostic_complete", "In simulation: Specimen transfer after blood collection complete (no laboratory results)")
                self._release_diagnostic_nurse(task)
            elif task["status"] == "preparing":
                self._diagnostic_event(task, "called", "Portable X-ray technician called after preparation (simulation)", nurse["id"])
                self._activity(nurse["id"], bed["id"], "diagnostic_call", "In simulation: Portable X-ray technician called after preparation")
                work["remaining"] = work["wait_min"]
                self._release_diagnostic_nurse(task)
            elif task["status"] == "called":
                self._diagnostic_event(task, "acquiring", "Technician arrived; image acquisition started (simulation)")
                work["remaining"] = work["acquire_min"]
            elif task["status"] == "acquiring":
                self._diagnostic_event(task, "image_available", "Imaging simulation complete; unrelated public NIH image available for review")
                self._activity(nurse["id"], bed["id"], "diagnostic_image_available",
                               "In simulation: Received imaging completion notice (public example image)")

    def _record_vital_point(self, bed):
        pt = bed["patient"]
        if pt is None:
            return
        history = pt.setdefault("_vital_history", deque(maxlen=VITAL_HISTORY_MIN + 1))
        point = {"t": self.t, "clock": self.clock(), **copy.deepcopy(pt["vitals"]),
                 "observed_vitals": copy.deepcopy(pt.get("observed_vitals", pt["vitals"])),
                 "simulated": pt.get("simulation_override") is not None}
        if history and history[-1]["t"] == self.t:
            history[-1] = point
        else:
            history.append(point)
        while history and history[0]["t"] < self.t - VITAL_HISTORY_MIN:
            history.popleft()

    def patient_vital_history(self, bed_id, minutes=120):
        bed = self.beds.get(bed_id) if isinstance(bed_id, str) else None
        if bed is None or bed["patient"] is None:
            raise ValueError("Select an occupied bed.")
        if not isinstance(minutes, int) or isinstance(minutes, bool) or not 1 <= minutes <= VITAL_HISTORY_MIN:
            raise ValueError("Request between 1 and 1440 minutes of vital history.")
        pt = bed["patient"]
        return {"bed": bed_id, "patient_key": {"pid": pt["src"]["pid"], "admit_t": pt["admit_t"]},
                "as_of": self.clock(), "t": self.t, "source": pt["src"]["source"],
                "source_description": "Only past and current replay observations are stored. Missing values carry forward from up to 12 prior record intervals. "
                                      "Injected simulation values are separate from observed_vitals source records.",
                "points": copy.deepcopy([row for row in pt.get("_vital_history", [])
                                          if max(pt["admit_t"], self.t - minutes) <= row["t"] <= self.t])}

    # ---------- 배치 ----------
    def _build_layout(self):
        per_unit = self.cfg["nurses_per_unit"]
        for fl in self.cfg["floors"]:
            f = fl["floor"]
            self.floors.append(f)
            for ui, u in enumerate(fl["units"]):
                ux = ui * (UNIT_W + CORRIDOR)
                unit = dict(u, floor=f, x=ux, y=0.0, w=UNIT_W, h=UNIT_H, bed_ids=[], nurse_ids=[],
                            station=(f, ux + UNIT_W / 2, UNIT_H / 2))
                per_row = math.ceil(u["beds"] / 2)
                gap = (UNIT_W - 8) / max(per_row - 1, 1)
                for b in range(u["beds"]):
                    row, c = divmod(b, per_row)
                    bid = f"{u['id']}-{b + 1:02d}"
                    self.beds[bid] = {"id": bid, "unit": u["id"], "floor": f,
                                      "pos": (f, ux + 4 + c * gap, 2.5 if row == 0 else UNIT_H - 2.5),
                                      "patient": None, "nurse": None}
                    unit["bed_ids"].append(bid)
                for k in range(per_unit):
                    nid = f"{u['id']}-{'C' if k == 0 else k}"
                    self.nurses[nid] = {"id": nid, "unit": u["id"], "role": "charge" if k == 0 else "bedside",
                                        "pos": unit["station"], "path": [], "status": "care",
                                        "incident": None, "diagnostic_id": None, "beds": [], "cover": [], "work": 0.0,
                                        "incident_min": 0, "round_i": 0, "k": k,
                                        "fatigue": 0.0, "on_break": False, "break_end": None,
                                        "breaks": 0, "over_warn": 0, "peak": 0.0}
                    unit["nurse_ids"].append(nid)
                self.units[u["id"]] = unit
        # 고정 2:1 배정 (fixed와 auto 모두 출발점은 같음, auto는 입실 때 부담 기준으로 배정)
        for u in self.units.values():
            bedside = [n for n in u["nurse_ids"] if self.nurses[n]["role"] == "bedside"]
            for i, bid in enumerate(u["bed_ids"]):
                nid = bedside[min(i // 2, len(bedside) - 1)]
                self.beds[bid]["nurse"] = nid
                self.nurses[nid]["beds"].append(bid)
            for nid in bedside:  # 시작 위치: 자기 첫 환자 옆
                self.nurses[nid]["pos"] = self.beds[self.nurses[nid]["beds"][0]]["pos"]

    def elevator(self, f):
        return (f, UNIT_W + CORRIDOR / 2, UNIT_H / 2)

    def route(self, a, b):
        """경로 waypoint 리스트와 소요 시간(분)."""
        if a[0] == b[0]:
            return [(b, 0.0)], dist(a, b) / WALK
        e1, e2 = self.elevator(a[0]), self.elevator(b[0])
        wait = ELEVATOR_MIN + 0.2 * abs(a[0] - b[0])
        t = dist(a, e1) / WALK + wait + dist(e2, b) / WALK
        return [(e1, 0.0), (e2, wait), (b, 0.0)], t

    # ---------- 환자 ----------
    def _pick_patient(self, utype, start_mid_stay):
        cands = self.by_type.get(utype) or [p for ps in self.by_type.values() for p in ps]
        here = {b["patient"]["src"]["pid"] for b in self.beds.values() if b["patient"]}
        src = self.rng.choice([p for p in cands if p["pid"] not in here] or cands)
        off = self.rng.uniform(0, max(src["los_min"] - 60, 0)) if start_mid_stay else 0.0
        return {"src": src, "offset": off, "admit_t": self.t, "acuity": 1, "vitals": {},
                "abn": [], "last": {"arrest": -999, "det": -999, "focus": -999}, "in_arrest": False,
                "hist": [], "risk": 0, "risk_hours": None, "focus": False}

    def _initial_census(self, occ):
        for u in self.units.values():
            for bid in u["bed_ids"]:
                if self.rng.random() < occ:
                    self.beds[bid]["patient"] = self._pick_patient(u["type"], True)
                    self._update_patient(self.beds[bid])

    def _bedside_load(self, nid):
        n = self.nurses[nid]
        return sum((self.beds[b]["patient"] or {}).get("acuity", 0) for b in n["beds"])

    def _admit(self, unit):
        pt = self._pick_patient(unit["type"], False)
        same_hospital = [u for u in self.units.values() if u.get("hospital_id") == unit.get("hospital_id")]
        order = [unit] + [u for u in same_hospital if u is not unit and u["type"] == unit["type"]]\
            + [u for u in same_hospital if u is not unit and u["floor"] == unit["floor"]]
        for u in order:
            free = [b for b in u["bed_ids"] if self.beds[b]["patient"] is None and not self.beds[b].get("reservation")]
            if not free:
                continue
            bed = self.beds[free[0]]
            bed["patient"] = pt
            self._update_patient(bed)
            if self.policy == "auto":
                # 입실 환자는 중증도 합이 가장 낮은 간호사에게 (최대 3명)
                bedside = [n for n in u["nurse_ids"] if self.nurses[n]["role"] == "bedside"]
                old = bed["nurse"]
                best = min(bedside, key=lambda n: (len(self.nurses[n]["beds"]) - (n == old) >= 3,
                                                   self._bedside_load(n) - (n == old) * pt["acuity"]
                                                   + self.nurses[n]["fatigue"] / 20))
                if best != old:
                    self.nurses[old]["beds"].remove(bed["id"])
                    self.nurses[best]["beds"].append(bed["id"])
                    bed["nurse"] = best
            moved = "" if u is unit else f" ({unit['name']} full → transferred)"
            self._log(f"Admission {bed['id']} {pt['src']['dx']} → Assigned {bed['nurse']}{moved}")
            return
        self._log(f"{unit['name']} Admission Waiting: Empty bed None")

    def _vital(self, src, var, idx):
        arr = src["series"].get(var) or []
        if src.get("bounded_carry_forward"):
            return arr[idx] if 0 <= idx < len(arr) else None
        for j in range(min(idx, len(arr) - 1), max(idx - 12, -1), -1):
            if arr[j] is not None:
                return arr[j]
        return None

    def _thr(self, utype):
        th = self.cfg["thresholds"]
        return th.get(utype, th["adult"])

    def _update_patient(self, bed):
        pt = bed["patient"]
        src = pt["src"]
        idx = int(pt["offset"] // src["step"])
        v = {k: self._vital(src, k, idx) for k in ("hr", "map", "spo2", "rr")}
        for key in ("sbp", "gcs"):
            if key in src["series"]:
                v[key] = self._vital(src, key, idx)
        pt["vitals"] = v
        pt["observed_vitals"] = dict(v)
        th = self._thr(self.units[bed["unit"]]["type"])
        abn = self._abnormal(v, th)
        prev = pt.get("observed_abn", [])
        pt["observed_abn"] = list(abn)
        pt["abn"] = abn
        scenario = next((i for i in self.incidents if i["bed"] == bed["id"] and i["end"] is None
                         and i.get("simulated")), None)
        recorded_arrest = pt["in_arrest"] and not (scenario and scenario["scenario"] == "code_blue")
        pt["acuity"] = 4 if recorded_arrest else min(4, 1 + src["vent"] + src["pressor"] + (len(abn) > 0))
        self._risk(pt, v, abn, arrest=recorded_arrest)
        pt["_recorded_state"] = {key: copy.deepcopy(pt[key]) for key in
                                 ("vitals", "abn", "acuity", "risk", "risk_hours")}
        pt["simulation_override"] = None
        if scenario:
            self._overlay_scenario(bed, scenario)
        if not pt.get("_vital_history"):
            self._record_vital_point(bed)
        arrest = any(pt["offset"] - 1 < c <= pt["offset"] for c in src["cpr"]) or\
            (v["hr"] is not None and v["hr"] < th["arrest_hr"]) or\
            (v["map"] is not None and v["map"] < th["arrest_map"])
        return arrest, bool(abn) and bool(prev)

    @staticmethod
    def _abnormal(v, th):
        abn = []
        if v["hr"] is not None and (v["hr"] > th["hr_high"] or v["hr"] < th["hr_low"]):
            abn.append("HR")
        if v["map"] is not None and v["map"] < th["map_low"]:
            abn.append("MAP")
        if v["spo2"] is not None and v["spo2"] < th["spo2_low"]:
            abn.append("SpO2")
        if v["rr"] is not None and v["rr"] > th["rr_high"]:
            abn.append("RR")
        return abn

    def _overlay_scenario(self, bed, inc):
        """Temporary demonstration values; never mutate retrospective source data."""
        scenario = EMERGENCY_SCENARIOS[inc["scenario"]]
        pt = bed["patient"]
        pt["vitals"] = dict(pt["observed_vitals"], **scenario["values"])
        pt["abn"] = self._abnormal(pt["vitals"], self._thr(self.units[bed["unit"]]["type"]))
        pt["acuity"] = 4 if inc["type"] == "arrest" else max(pt["acuity"], 3)
        pt["risk"] = max(pt["risk"], 90 if inc["type"] == "arrest" else 80)
        pt["simulation_override"] = {"incident_id": inc["id"], "scenario": inc["scenario"],
                                      "label": inc["label"], "source": "simulation_injected",
                                      "values": dict(scenario["values"])}
        pt["simulation_override"]["findings"] = list(scenario.get("findings", []))

    def _risk(self, pt, v, abn, arrest=None):
        """동적 위험지표 0~100과 남은 집중관리 예상 시간.

        자리표시 모델: 입원 전·수술 중 정보로 만든 사전위험(prior_risk) + 현재 이상 활력 + 30분 추세.
        Pod에서 VitalDB/INSPIRE로 학습한 모델로 이 함수만 바꾸면 된다.
        """
        src = pt["src"]
        pt["hist"].append((v["map"], v["hr"]))
        pt["hist"] = pt["hist"][-30:]
        prior = src.get("prior_risk", 20 + 15 * src["vent"] + 15 * src["pressor"])
        trend = 0
        old = pt["hist"][0]
        if v["map"] is not None and old[0] is not None and old[0] - v["map"] > 10:
            trend += 12
        if v["hr"] is not None and old[1] is not None and v["hr"] - old[1] > 20:
            trend += 12
        r = 0.6 * prior + 14 * len(abn) + trend + (40 if (pt["in_arrest"] if arrest is None else arrest) else 0)
        pt["risk"] = round(max(0, min(100, r)))
        base_h = src.get("prior_icu_hours", src["los_min"] / 60)
        pt["risk_hours"] = round(max(0.0, base_h * (0.5 + pt["risk"] / 100) - pt["offset"] / 60), 1)

    # ---------- 이벤트와 배치 ----------
    def _log(self, msg):
        self.log.append(f"{self.clock()} {msg}")
        self.log = self.log[-300:]

    def calendar_day(self):
        hour, minute = map(int, self.cfg["start_clock"].split(":"))
        return int((hour * 60 + minute + self.t) // 1440)

    def clock(self, t=None):
        h, m = map(int, self.cfg["start_clock"].split(":"))
        tot = h * 60 + m + int(self.t if t is None else t)
        return f"{(tot // 60) % 24:02d}:{tot % 60:02d}"

    def trigger_emergency(self, bed_id, scenario):
        """Inject a demonstration event. Counts, vitals, MD capacity and durations
        are scenario assumptions, not forecasts or treatment recommendations.
        """
        if not isinstance(scenario, str) or scenario not in EMERGENCY_SCENARIOS:
            raise ValueError("Select a supported emergency simulation.")
        if not isinstance(bed_id, str) or bed_id not in self.beds or self.beds[bed_id]["patient"] is None:
            raise ValueError("Start emergency simulation in an occupied bed.")
        if any(inc["bed"] == bed_id and inc["end"] is None for inc in self.incidents):
            raise ValueError("An event is already active in this bed.")
        inc = self._new_incident(self.beds[bed_id], EMERGENCY_SCENARIOS[scenario]["kind"], scenario=scenario)
        self._update_patient(self.beds[bed_id])
        self._dispatch(inc)
        return self._incident_json(inc)

    def _new_incident(self, bed, kind, scenario=None):
        self._iid += 1
        label = EMERGENCY_SCENARIOS[scenario]["label"] if scenario else EVENT[kind]["label"]
        evidence = clinical_evidence.assessment(bed["patient"]["vitals"], self._thr(self.units[bed["unit"]]["type"]), bed["patient"]["src"]["source"], simulated=bool(scenario))
        if not scenario and kind == "det":
            label = evidence["title"] + " (replay alert)"
        if not scenario and kind == "arrest":
            label = "Critical hemodynamic / CPR-record alert (replay)"
        inc = {"id": self._iid, "type": kind, "label": label, "bed": bed["id"],
               "unit": bed["unit"], "floor": bed["floor"], "start": self.t, "need": EVENT[kind]["need"],
               "responders": [], "arrived": [], "first": None, "full": None, "end": None, "helpers": 0,
               "scenario": scenario, "simulated": scenario is not None, "evidence": evidence,
               "doctor_id": f"MD-{bed['unit']}" if kind != "focus" else None,
               "doctor_called_t": self.t if kind != "focus" else None,
               "doctor_arrived_t": None}
        self.incidents.append(inc)
        pt = bed["patient"]
        pt["last"][kind] = self.t
        if kind == "arrest":
            pt["in_arrest"] = True
        if kind == "focus":
            pt["focus"] = True
            self._log(f"◆ Risk index {pt['risk']} ≥ {RISK_ON}: {bed['id']} Focused care started")
            return inc
        if scenario:
            self._overlay_scenario(bed, inc)
            inc["evidence"] = clinical_evidence.assessment(pt["vitals"], self._thr(self.units[bed["unit"]]["type"]), pt["src"]["source"], simulated=True)
        self._log(f"⚠ {inc['label']} {bed['id']} (HR {pt['vitals']['hr']}, MAP {pt['vitals']['map']}, "
                  f"SpO2 {pt['vitals']['spo2']})")
        self._dispatch_doctor(inc)
        return inc

    def _dispatch_doctor(self, inc):
        if not inc["doctor_id"]:
            return
        doctor = self.doctors[inc["doctor_id"]]
        if doctor["incident"] == inc["id"] or doctor["incident"] is not None:
            return  # only the same ICU's MD is eligible; busy means waiting
        doctor["incident"] = inc["id"]
        doctor["path"] = [list(p) for p in self.route(doctor["pos"], self.beds[inc["bed"]]["pos"])[0]]
        doctor["status"] = "called"
        self._log(f"☎ {doctor['id']} Called {inc['bed']} ({inc['label']})")

    def _move_doctors(self):
        for doctor in self.doctors.values():
            if doctor["status"] == "called":
                doctor["status"] = "moving"
            if doctor["path"]:
                self._move(doctor)
            if not doctor["path"] and doctor["incident"] is not None:
                doctor["status"] = "responding"
                inc = next(i for i in self.incidents if i["id"] == doctor["incident"])
                if inc["doctor_arrived_t"] is None:
                    inc["doctor_arrived_t"] = self.t
                    self._log(f"↳ {doctor['id']} Arrived {inc['bed']} (Simulation MD Response)")
            elif not doctor["path"]:
                doctor["status"] = "available"

    def _incident_json(self, inc):
        doctor = self.doctors.get(inc["doctor_id"])
        return {**{key: copy.deepcopy(inc[key]) for key in
                   ("id", "type", "label", "bed", "unit", "floor", "start", "need", "responders", "arrived",
                    "scenario", "simulated", "evidence", "doctor_id", "doctor_called_t", "doctor_arrived_t")},
                "shortage": max(0, inc["need"] - len(inc["responders"])),
                "elapsed_min": self.t - inc["start"], "duration_min": EVENT[inc["type"]]["dur"],
                "doctor_waiting": bool(doctor and doctor["incident"] != inc["id"] and inc["doctor_arrived_t"] is None),
                "doctor_status": doctor["status"] if doctor else None}

    def _free(self, nid):
        n = self.nurses[nid]
        return n["incident"] is None and not n["on_break"] and n["diagnostic_id"] is None

    def _emergency_free(self, nid):
        n = self.nurses[nid]
        return n["incident"] is None and not n["on_break"]

    def _away(self, n):
        return n["incident"] is not None or n["on_break"] or n["diagnostic_id"] is not None

    def _eligible(self, inc):
        dt = self.t - inc["start"]
        bed = self.beds[inc["bed"]]
        free = [n for n in self.nurses if self._emergency_free(n) and self.nurses[n]["unit"] == inc["unit"]]
        if inc["type"] == "focus" and self.policy == "auto":
            owner = [n for n in free if bed["id"] in self.nurses[n]["beds"]]
            return owner or [n for n in free if self.nurses[n]["unit"] == inc["unit"]]
        if self.policy == "auto":
            return free
        owner = [n for n in free if bed["id"] in self.nurses[n]["beds"]]
        if inc["type"] == "focus":
            same_free = [n for n in free if self.nurses[n]["unit"] == inc["unit"]]
            return owner if owner else (same_free if dt >= FIXED_NOTICE_DELAY else [])
        same = [n for n in free if self.nurses[n]["unit"] == inc["unit"]]
        if inc["type"] == "arrest":
            charge = [n for n in same if self.nurses[n]["role"] == "charge"]
            return owner + charge + (same if dt >= FIXED_PAGE_DELAY else [])
        return owner if owner else (same if dt >= FIXED_NOTICE_DELAY else [])

    def _dispatch(self, inc, preferred=None):
        bed = self.beds[inc["bed"]]
        while len(inc["responders"]) < inc["need"]:
            cands = [n for n in dict.fromkeys(self._eligible(inc)) if n not in inc["responders"]]
            if not cands:
                return
            def cost(n):  # auto: 가까운 사람 우선, 피로도가 높으면 덜 부름 (피로도 40 = 1분 거리)
                t = self.route(self.nurses[n]["pos"], bed["pos"])[1]
                return t + ((self.nurses[n]["fatigue"] / 40 + self._bedside_load(n) / 20
                             + len(self.nurses[n]["cover"]) / 10) if self.policy == "auto" else 0)
            ranked = sorted(cands, key=lambda nid: (nid != preferred, cost(nid)))
            nid = ranked[0]
            n = self.nurses[nid]
            if n["diagnostic_id"] is not None:
                task = next(row for row in self.diagnostics if row["id"] == n["diagnostic_id"])
                self._pause_diagnostic(task, "Emergency response takes priority")
            path, eta = self.route(n["pos"], bed["pos"])
            n["path"] = [list(p) for p in path]
            n["status"] = "moving"
            n["incident"] = inc["id"]
            inc["responders"].append(nid)
            self._log(f"→ {nid} Dispatched {inc['bed']} ({eta:.1f}min)")
            self._activity(nid, inc["bed"], "dispatch", f"In simulation: {inc['label']} Response dispatch started", inc["id"])
            if self.policy == "auto":
                self._cover(nid, exclude=inc["bed"])

    def _cover(self, nid, exclude):
        n = self.nurses[nid]
        # A newly absent person also hands over beds they were covering. On
        # diagnostic resumption an emergency may have cleared the old cover.
        for b in dict.fromkeys(n["beds"] + n["cover"]):
            if b == exclude or self.beds[b]["patient"] is None:
                continue
            holders = [m for m in self.units[n["unit"]]["nurse_ids"] if b in self.nurses[m]["cover"]]
            available = [m for m in holders if m != nid and self._free(m)]
            keeper = available[0] if available else None
            for holder in holders:
                if holder != keeper:
                    self.nurses[holder]["cover"] = [bid for bid in self.nurses[holder]["cover"] if bid != b]
            if keeper is not None:
                continue
            owner = self.nurses[self.beds[b]["nurse"]]
            if owner["id"] != nid and not self._away(owner):
                continue  # the original owner is available again
            mates = [m for m in self.units[n["unit"]]["nurse_ids"] if m != nid and self._free(m)]
            if not mates:
                continue
            m = min(mates, key=lambda m: self._bedside_load(m) + len(self.nurses[m]["cover"]) * 2
                    + self.nurses[m]["fatigue"] / 20)
            self._begin_cover(m, b, n["incident"])

    def _release(self, inc):
        for nid in inc["responders"]:
            n = self.nurses[nid]
            self._activity(nid, inc["bed"], "response_end", f"In simulation: {inc['label']} Response ended", inc["id"])
            n["incident"] = None
            n["status"] = "care"
            home = self.beds[n["beds"][0]]["pos"] if n["beds"] else self.units[n["unit"]]["station"]
            path, _ = self.route(n["pos"], home)
            n["path"] = [list(p) for p in path]
            for m in self.nurses.values():  # 대신 봐주던 환자 돌려받기
                m["cover"] = [b for b in m["cover"] if b not in n["beds"]]
        pt = self.beds[inc["bed"]]["patient"]
        if pt:
            pt["in_arrest"] = False
            pt["focus"] = False
            if inc.get("simulated"):
                pt.update(copy.deepcopy(pt["_recorded_state"]))
                pt["simulation_override"] = None
        doctor = self.doctors.get(inc["doctor_id"])
        if doctor and doctor["incident"] == inc["id"]:
            doctor["incident"] = None
            doctor["path"] = [list(p) for p in self.route(doctor["pos"], self.units[doctor["unit"]]["station"])[0]]
            doctor["status"] = "moving"
        self._log(f"✓ {inc['label']} {inc['bed']} Ended (first arrival {inc['first'] - inc['start']:.0f}min)")

    # ---------- 이동 ----------
    def _move(self, n):
        budget = 1.0  # 분
        while n["path"] and budget > 0:
            (f, x, y), wait = n["path"][0]
            if wait > 0:
                use = min(wait, budget)
                n["path"][0][1] -= use
                budget -= use
                if n["path"][0][1] <= 1e-9:
                    n["pos"] = (f, x, y)
                    n["path"].pop(0)
                continue
            d = dist(n["pos"], (f, x, y)) if n["pos"][0] == f else 0.0
            step = WALK * budget
            if d <= step:
                n["pos"] = (f, x, y)
                n["path"].pop(0)
                budget -= d / WALK
            else:
                px, py = n["pos"][1], n["pos"][2]
                n["pos"] = (f, px + (x - px) * step / d, py + (y - py) * step / d)
                budget = 0

    # ---------- 피로도와 휴식 ----------
    def _start_break(self, nid):
        n = self.nurses[nid]
        n["on_break"], n["break_end"], n["breaks"] = True, self.t + BREAK_MIN, n["breaks"] + 1
        n["status"] = "break"
        f, x, y = self.units[n["unit"]]["station"]
        path, _ = self.route(n["pos"], (f, x + 4, y))  # 휴게실: 스테이션 옆
        n["path"] = [list(p) for p in path]
        if self.policy == "fixed":
            buddy = f"{n['unit']}-{FIXED_BUDDY[n['k']]}"
            if self._free(buddy):
                for bed_id in n["beds"]:
                    if self.beds[bed_id]["patient"]:
                        self._begin_cover(buddy, bed_id)
        else:
            self._cover(nid, exclude=None)
        self._log(f"☕ {nid} Break started (Fatigue {n['fatigue']:.0f})")

    def _end_break(self, n):
        n["on_break"], n["break_end"], n["status"] = False, None, "care"
        for m in self.nurses.values():
            m["cover"] = [b for b in m["cover"] if b not in n["beds"]]
        if n["beds"]:
            path, _ = self.route(n["pos"], self.beds[n["beds"][0]]["pos"])
            n["path"] = [list(p) for p in path]
        self._log(f"↩ {n['id']} Break ended (Fatigue {n['fatigue']:.0f})")

    def _breaks(self):
        # At the boundary, finish the outgoing minute before changing people.
        if self._shift_number(self.t) != self._active_shift_number:
            return
        st = self._shift_at(self.t)["elapsed_min"]
        for n in self.nurses.values():
            if n["on_break"] and self.t >= n["break_end"]:
                self._end_break(n)
        busy_units = {i["unit"] for i in self.incidents if i["end"] is None}
        for u in self.units.values():
            bedside = [self.nurses[x] for x in u["nurse_ids"] if self.nurses[x]["role"] == "bedside"]
            check_due = self._break_check_due(u)
            if self.policy == "fixed":
                if (u["id"] in busy_units or any(n["on_break"] for n in bedside)
                        or SHIFT_MIN - st < BREAK_MIN):
                    continue
                due = sorted((n for n in bedside if n["breaks"] == 0
                              and self.t >= n["fixed_break_t"] and self._free(n["id"]) and not n["cover"]),
                             key=lambda n: (n["fixed_break_t"], n["id"]))
                for n in due:
                    buddy = self.nurses[f"{n['unit']}-{FIXED_BUDDY[n['k']]}"]
                    if buddy["unit"] == n["unit"] and self._free(buddy["id"]):
                        self._start_break(n["id"])
                        break  # retries preserve a missed break without overlapping unit breaks
                continue
            # ICU마다 다른 확인 시각. 조용하고 남는 인원이 있으면 가장 지친 사람부터 휴식.
            if (not check_due or u["id"] in busy_units or any(n["on_break"] for n in bedside)
                    or SHIFT_MIN - st < BREAK_MIN):
                continue
            free = [n for n in bedside if self._free(n["id"])]
            due = [n for n in free if n["breaks"] == 0 and (n["fatigue"] >= FATIGUE_WARN or st >= 360)]
            if due and len(free) >= 3:
                self._start_break(max(due, key=lambda n: n["fatigue"])["id"])

    def _fatigue(self, n):
        if n["on_break"] and not n["path"]:
            n["fatigue"] -= FATIGUE_REST
        else:
            inc = next((i for i in self.incidents if i["id"] == n["incident"]), None)
            if inc is not None:
                load = FATIGUE_EVENT[inc["type"]]
            else:
                load = FATIGUE_CARE * sum(CARE_MIN_PER_HR[self.beds[b]["patient"]["acuity"]] / 60
                                          for b in n["beds"] + n["cover"] if self.beds[b]["patient"])
            n["fatigue"] += FATIGUE_BASE + load + (FATIGUE_MOVE if n["path"] else 0)
        n["fatigue"] = max(0.0, min(100.0, n["fatigue"]))
        n["peak"] = max(n["peak"], n["fatigue"])
        if n["fatigue"] >= FATIGUE_HIGH:
            n["over_warn"] += 1

    # ---------- 1분 진행 ----------
    def step(self):
        self.t += 1
        # 입실·퇴실
        for u in self.units.values():
            if self.rng.random() < self.arrival_p:
                self._admit(u)
        active = {i["bed"] for i in self.incidents if i["end"] is None}
        for bed in self.beds.values():
            reservation = bed.get("reservation")
            if reservation and not bed["patient"] and self.t >= reservation["expected_t"]:
                bed["patient"] = self._pick_patient(self.units[bed["unit"]]["type"], False)
                bed.pop("reservation")
                self._log(f"{bed['id']} Scheduled postoperative admission (fictional simulation)")
            pt = bed["patient"]
            if pt is None:
                continue
            pt["offset"] += 1
            if pt["offset"] >= pt["src"]["los_min"] and bed["id"] not in active:
                self._log(f"Discharge {bed['id']}")
                bed["patient"] = None
                continue
            arrest, det = self._update_patient(bed)
            if bed["id"] in active:
                continue
            if arrest and self.t - pt["last"]["arrest"] > REFRACTORY:
                self._new_incident(bed, "arrest")
            elif det and self.t - pt["last"]["det"] > REFRACTORY:
                self._new_incident(bed, "det")
            elif pt["risk"] >= RISK_ON and not pt["focus"] and self.t - pt["last"]["focus"] > 30:
                self._new_incident(bed, "focus")

        # 배치와 도착
        for inc in self.incidents:
            if inc["end"] is not None:
                continue
            self._dispatch_doctor(inc)
            self._dispatch(inc)
            for nid in inc["responders"]:
                n = self.nurses[nid]
                if not n["path"] and nid not in inc["arrived"]:
                    inc["arrived"].append(nid)
                    self._activity(nid, inc["bed"], "arrival", f"In simulation: {inc['label']} Arrived at event bed", inc["id"])
                    n["status"] = "incident"
                    if inc["first"] is None:
                        inc["first"] = self.t
                    if len(inc["arrived"]) >= inc["need"] and inc["full"] is None:
                        inc["full"] = self.t
            dur = EVENT[inc["type"]]["dur"]
            pt = self.beds[inc["bed"]]["patient"]
            if dur is None:
                over = pt is None or pt["risk"] < RISK_OFF
            else:
                if inc.get("simulated"):
                    # Demonstration resolution begins after the requested local
                    # team AND MD have arrived. Waiting/shortage cannot silently
                    # resolve an injected emergency; this is not clinical logic.
                    response_start = (max(inc["full"], inc["doctor_arrived_t"])
                                      if inc["full"] is not None and inc["doctor_arrived_t"] is not None else None)
                    over = response_start is not None and self.t - response_start >= dur
                else:
                    over = inc["first"] is not None and self.t - inc["first"] >= dur
            if over and inc["first"] is not None:
                inc["end"] = self.t
                self._release(inc)

        self._breaks()
        self._schedule_diagnostics()

        # 이동, 일상 간호, 자리 비운 환자
        for n in self.nurses.values():
            round_due = self._round_due(n)  # advance even if busy, keeping exogenous timing shared
            self._fatigue(n)
            if n["incident"] is not None:
                n["incident_min"] += 1
                n["work"] += 1
            elif n["diagnostic_id"] is not None and not n["on_break"]:
                n["work"] += 1  # elapsed simulated workflow time, not proof of treatment
            elif not n["on_break"] and not n["path"] and round_due:
                targets = [bid for bid in dict.fromkeys(n["beds"] + n["cover"])
                           if self.beds[bid]["patient"] is not None]
                if targets:
                    n["round_i"] = (n["round_i"] + 1) % len(targets)
                    path, _ = self.route(n["pos"], self.beds[targets[n["round_i"]]]["pos"])
                    n["path"] = [list(p) for p in path]
            self._move(n)
        self._move_doctors()
        self._progress_diagnostics()
        active = {i["bed"] for i in self.incidents if i["end"] is None}
        for bed in self.beds.values():
            pt = bed["patient"]
            if pt is None or bed["id"] in active:
                continue
            if any(task["bed"] == bed["id"] and task["status"] in ("collecting", "preparing")
                   and not task["paused"] for task in self.diagnostics):
                continue
            owner = self.nurses[bed["nurse"]]
            need = CARE_MIN_PER_HR[pt["acuity"]] / 60
            if not self._away(owner):
                owner["work"] += need
                continue
            cover = [m for m in self.nurses.values() if bed["id"] in m["cover"] and not self._away(m)]
            if cover:
                cover[0]["work"] += need
            else:
                self.unattended["all"] += 1
                if pt["acuity"] >= 3:
                    self.unattended["high"] += 1
        for bed in self.beds.values():
            self._record_vital_point(bed)
        self._rotate_shift()

    # ---------- 지표와 상태 ----------
    def metrics(self):
        done = [i for i in self.incidents if i["first"] is not None]

        def avg(xs):
            return round(sum(xs) / len(xs), 1) if xs else None
        out = {"policy": self.policy, "minutes": self.t}
        for k in EVENT:
            inc = [i for i in done if i["type"] == k]
            out[k] = {"n": len([i for i in self.incidents if i["type"] == k]),
                      "first_resp": avg([i["first"] - i["start"] for i in inc]),
                      "full_team": avg([i["full"] - i["start"] for i in inc if i["full"] is not None]),
                      "helpers": sum(i["helpers"] for i in inc)}
        # Slots remain stable while people change. Preserve cumulative comparison
        # measures without pretending that incoming staff did outgoing work.
        completed = [staff for shift in self.shift_history for staff in shift["staff"]]
        work = {nid: n["work"] for nid, n in self.nurses.items()}
        for staff in completed:
            work[staff["slot_id"]] += staff["work"]
        sds, current_sds = [], []
        for u in self.units.values():
            w = [work[n] for n in u["nurse_ids"] if self.nurses[n]["role"] == "bedside"]
            m = sum(w) / len(w)
            sds.append(math.sqrt(sum((x - m) ** 2 for x in w) / len(w)))
            current = [self.nurses[n]["work"] for n in u["nurse_ids"] if self.nurses[n]["role"] == "bedside"]
            mean = sum(current) / len(current)
            current_sds.append(math.sqrt(sum((x - mean) ** 2 for x in current) / len(current)))
        out["workload_sd"] = round(sum(sds) / len(sds), 1)
        out["workload_sd_basis"] = "cumulative_slots"
        out["workload_current_sd"] = round(sum(current_sds) / len(current_sds), 1)
        fat = [n["fatigue"] for n in self.nurses.values() if n["role"] == "bedside"]
        previous = ([n["end_fatigue"] for n in self.last_shift["staff"] if n["role"] == "bedside"]
                    if self.last_shift else [])
        boundary = bool(self.last_shift and self.t == self.last_shift["end_t"])
        out["fatigue_current_mean"] = round(sum(fat) / len(fat))
        out["fatigue_last_shift_mean"] = round(sum(previous) / len(previous)) if previous else None
        out["fatigue_last_shift_label"] = self.last_shift["label"] if self.last_shift else None
        out["fatigue_mean"] = out["fatigue_last_shift_mean"] if boundary else out["fatigue_current_mean"]
        out["fatigue_mean_basis"] = "last_completed_shift" if boundary else "current_on_duty"
        label = self.last_shift["label"] if boundary else self._shift_at(self.t)["label"]
        out["fatigue_mean_label"] = (f"Previous {label} shift: mean fatigue at end" if boundary
                                     else f"Current {label} mean shift fatigue")
        out["fatigue_max"] = round(max([n["peak"] for n in self.nurses.values()]
                                       + [n["peak_fatigue"] for n in completed]))
        out["fatigue_high_min"] = sum(n["over_warn"] for n in self.nurses.values()) + sum(n["over_warn"] for n in completed)
        out["unattended_min"] = self.unattended["all"]
        out["unattended_high_min"] = self.unattended["high"]
        return out

    def state(self):
        floors = []
        for f in self.floors:
            us = [u for u in self.units.values() if u["floor"] == f]
            floors.append({"floor": f, "units": [{
                "id": u["id"], "name": u["name"], "x": u["x"], "w": u["w"], "h": u["h"],
                "hospital_id": u.get("hospital_id", "A"), "hospital_name": u.get("hospital_name", "Demo Hospital A"),
                "display_floor": u.get("display_floor", f),
                "beds": [self._bed_json(self.beds[b]) for b in u["bed_ids"]]} for u in us]})
        active = [i for i in self.incidents if i["end"] is None]
        shift = self._shift_at(self.t)
        return {
            "t": self.t, "clock": self.clock(), "policy": self.policy,
            "shift": shift,
            "shift_schedule": [dict(row, active=row["code"] == shift["code"],
                                    next=row["code"] == shift["next_code"],
                                    staff_count=len(self.nurses)) for row in self.shift_schedule],
            "roster": [dict(row, on_duty=row["shift_code"] == shift["code"])
                       for row in self.roster],
            "doctors": [{"id": d["id"], "unit": d["unit"], "role": d["role"],
                         "floor": d["pos"][0], "x": round(d["pos"][1], 2), "y": round(d["pos"][2], 2),
                         "status": d["status"], "incident": d["incident"]}
                        for d in self.doctors.values()],
            "last_handover": copy.deepcopy(self.last_handover),
            "handover_history": copy.deepcopy(self.handover_history),
            "completed_shifts": copy.deepcopy(self.shift_history),
            "care_actions": copy.deepcopy(self.care_actions),
            "activities": copy.deepcopy(self.activities),
            "diagnostics": copy.deepcopy(self.diagnostics),
            "elevator_x": UNIT_W + CORRIDOR / 2, "floor_w": 2 * UNIT_W + CORRIDOR, "floor_h": UNIT_H,
            "floors": floors,
            "nurses": [{"id": n["id"], "unit": n["unit"], "role": n["role"], "floor": n["pos"][0],
                        "staff_id": n["staff_id"], "shift_code": n["shift_code"], "shift_label": n["shift_label"],
                        "care_actions": copy.deepcopy([a for a in self.care_actions
                                                       if a["staff_id"] == n["staff_id"] and a["cycle"] == shift["cycle"]]),
                        "activities": copy.deepcopy([a for a in self.activities
                                                      if a["staff_id"] == n["staff_id"] and a["cycle"] == shift["cycle"]]),
                        "x": round(n["pos"][1], 2), "y": round(n["pos"][2], 2), "status": n["status"],
                        "incident": n["incident"], "diagnostic_id": n["diagnostic_id"],
                        "beds": n["beds"], "cover": n["cover"],
                        "work": round(n["work"]), "fatigue": round(n["fatigue"]),
                        "on_break": n["on_break"], "breaks": n["breaks"]} for n in self.nurses.values()],
            "incidents": [self._incident_json(i) for i in active],
            "risk_on": RISK_ON, "risk_off": RISK_OFF,
            "fatigue_warn": FATIGUE_WARN, "fatigue_high": FATIGUE_HIGH,
            "log": self.log[-60:],
            "metrics": self.metrics(),
        }

    def _bed_json(self, bed):
        pt = bed["patient"]
        out = {"id": bed["id"], "x": bed["pos"][1], "y": bed["pos"][2], "nurse": bed["nurse"]}
        out["reservation"] = copy.deepcopy(bed.get("reservation"))
        if pt:
            s = pt["src"]
            out["patient"] = {"pid": s["pid"], "admit_t": pt["admit_t"], "dx": s["dx"], "age": s["age"], "sex": s["sex"],
                              "vent": s["vent"], "pressor": s["pressor"], "acuity": pt["acuity"],
                              "devices": copy.deepcopy(s.get("devices", {})),
                              "care_indicators": copy.deepcopy(s.get("care_indicators", {})),
                              "calendar_day": self.calendar_day(),
                              "extra_observations": copy.deepcopy(s.get("extra_observations", {})),
                              "vitals": pt["vitals"], "abn": pt["abn"], "arrest": pt["in_arrest"],
                              "observed_vitals": copy.deepcopy(pt.get("observed_vitals", pt["vitals"])),
                              "simulation_override": copy.deepcopy(pt.get("simulation_override")),
                              "diagnostics": self.patient_diagnostics(bed["id"]),
                              "hours": round(pt["offset"] / 60, 1), "source": s["source"],
                              "risk": pt["risk"], "risk_hours": pt["risk_hours"], "focus": pt["focus"],
                              "clinical": clinical_evidence.assessment(pt["vitals"], self._thr(self.units[bed["unit"]]["type"]), s["source"], bool(pt.get("simulation_override")), s.get("age")),
                              "provenance": copy.deepcopy(s.get("provenance", {}))}
        return out


def run(pool, policy, seed, minutes=480):
    h = Hospital(pool, policy=policy, seed=seed)
    for _ in range(minutes):
        h.step()
    return h.metrics()
