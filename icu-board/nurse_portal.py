"""Scoped accounts for the public ICU demonstration, not hospital identity proof.

The original board remains public. These tab-specific bearer sessions exercise
the nurse workflow; they must not be presented as production authentication.
"""
import copy
import secrets


class PortalError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class NursePortal:
    def __init__(self):
        self.sessions = {}

    @staticmethod
    def registry(hospital):
        accounts = {}
        for row in hospital.roster:
            nurse = hospital.nurses.get(row["slot_id"])
            account_id = row["staff_id"]
            accounts[account_id] = {"account_id": account_id, "staff_id": row["staff_id"],
                                    "slot_id": row["slot_id"], "unit": row["unit"], "role": row["role"],
                                    "shift_code": row["shift_code"], "shift_label": row["shift_label"],
                                    "on_duty": bool(nurse and nurse["staff_id"] == row["staff_id"]
                                                    and nurse["unit"] == row["unit"]
                                                    and nurse["role"] == row["role"])}
        accounts["HN01"] = {"account_id": "HN01", "staff_id": "HN01", "slot_id": None, "unit": None,
                             "role": "head_nurse", "shift_code": None,
                             "shift_label": "전체 수간호사", "on_duty": True}
        return accounts

    def accounts(self, hospital):
        return copy.deepcopy(list(self.registry(hospital).values()))

    def login(self, hospital, account_id, pin):
        account = self.registry(hospital).get(account_id) if isinstance(account_id, str) else None
        if account is None or not isinstance(pin, str) or not secrets.compare_digest(pin.encode(), b"2026"):
            raise PortalError(401, "시연 계정과 PIN을 확인하세요.")
        token = secrets.token_urlsafe(32)
        self.sessions[token] = account["account_id"]
        return {"token": token, "account": copy.deepcopy(account)}

    @staticmethod
    def bearer(headers):
        value = headers.get("Authorization", "")
        if not isinstance(value, str) or not value.startswith("Bearer ") or not value[7:]:
            raise PortalError(401, "간호사 계정으로 로그인하세요.")
        return value[7:]

    def account(self, hospital, token):
        account_id = self.sessions.get(token) if isinstance(token, str) else None
        account = self.registry(hospital).get(account_id)
        if account is None:
            raise PortalError(401, "로그인이 만료되었습니다. 다시 로그인하세요.")
        return copy.deepcopy(account)

    def logout(self, token):
        if not isinstance(token, str) or token not in self.sessions:
            raise PortalError(401, "로그인이 만료되었습니다. 다시 로그인하세요.")
        del self.sessions[token]

    @staticmethod
    def visible_beds(hospital, account):
        if account["role"] == "head_nurse":
            return set(hospital.beds)
        if not account["on_duty"]:
            return set()
        slot_id = account["slot_id"]
        nurse = hospital.nurses[slot_id]
        own_unit = account["unit"]
        responding = {incident["bed"] for incident in hospital.incidents
                      if incident["end"] is None and incident["unit"] == own_unit
                      and slot_id in incident["responders"]}
        return {bid for bid, bed in hospital.beds.items() if bed["unit"] == own_unit
                and (account["role"] == "charge" or bed["nurse"] == slot_id
                     or bid in nurse["cover"] or bid in responding)}

    @staticmethod
    def actual_nurse(hospital, nurse_id):
        nurse = hospital.nurses[nurse_id]
        return {"id": nurse["id"], "staff_id": nurse["staff_id"], "unit": nurse["unit"],
                "role": nurse["role"], "shift_code": nurse["shift_code"], "shift_label": nurse["shift_label"]}

    def authorize(self, hospital, token, body, operation):
        account = self.account(hospital, token)
        if not account["on_duty"]:
            raise PortalError(403, "현재 근무 시간이 아닙니다. 해당 근무조에서 환자를 확인하세요.")
        if account["role"] == "head_nurse" and operation not in ("patient", "consult"):
            raise PortalError(403, "전체 수간호사 계정은 조회·초안 확인만 가능합니다.")
        bed_id = body.get("bed")
        if not isinstance(bed_id, str) or bed_id not in self.visible_beds(hospital, account):
            raise PortalError(403, "현재 로그인 계정의 환자 범위에서만 사용할 수 있습니다.")
        nurse_id = hospital.beds[bed_id]["nurse"] if account["role"] == "head_nurse" else account["slot_id"]
        return account, nurse_id

    def scoped_handover(self, hospital, account, scope=None):
        snapshot = hospital.last_handover
        if not account["on_duty"] or not snapshot:
            return None
        scope = self.visible_beds(hospital, account) if scope is None else scope
        patients = []
        for row in snapshot["patients"]:
            if row["bed"] not in scope:
                continue
            pt = hospital.beds[row["bed"]]["patient"]
            if pt is None or pt["src"]["pid"] != row["pid"] or pt["admit_t"] != row["admit_t"]:
                continue
            if account["role"] == "bedside" and row["to_staff_id"] != account["staff_id"]:
                continue
            patients.append(copy.deepcopy(row))
        return {"t": snapshot["t"], "clock": snapshot["clock"], "from_label": snapshot["from_label"],
                "to_label": snapshot["to_label"], "patients": patients}

    def state(self, hospital, token, *, seed, source, running):
        account = self.account(hospital, token)
        scope = self.visible_beds(hospital, account)
        full = hospital.state()
        nurse = next((row for row in full["nurses"] if row["id"] == account["slot_id"]), None)
        if not account["on_duty"]:
            nurse = None
        elif nurse is not None:
            nurse = copy.deepcopy(nurse)
            nurse["beds"] = [bid for bid in nurse["beds"] if bid in scope]
            nurse["cover"] = [bid for bid in nurse["cover"] if bid in scope]
        patients = []
        tasks = []
        for bid, bed in hospital.beds.items():
            if bid not in scope or bed["patient"] is None:
                continue
            assignment = "overview" if account["role"] == "head_nurse" else (
                "unit" if account["role"] == "charge" else "assigned" if bed["nurse"] == account["slot_id"]
                else "cover" if bid in hospital.nurses[account["slot_id"]]["cover"] else "responder")
            patients.append({"id": bid, "unit": bed["unit"], "nurse": bed["nurse"], "assignment": assignment,
                             "patient": copy.deepcopy(hospital._bed_json(bed)["patient"])})
            tasks.extend(hospital.patient_diagnostics(bid))
        scope_label = "전체 ICU 조회" if account["role"] == "head_nurse" else (
            "비근무 · 환자 조회 중지" if not account["on_duty"] else
            f"{account['unit']} 전체" if account["role"] == "charge" else "담당·대신 보기·출동 환자")
        return {"account": account, "clock": full["clock"], "t": full["t"], "seed": seed,
                "shift": copy.deepcopy(full["shift"]), "source": copy.deepcopy(source), "running": running,
                "scope_label": scope_label, "nurse": nurse, "patients": patients,
                "alerts": copy.deepcopy([incident for incident in full["incidents"] if incident["bed"] in scope]),
                "tasks": tasks, "my_actions": copy.deepcopy(nurse["care_actions"] if nurse else []),
                "activities": copy.deepcopy(nurse["activities"] if nurse else []),
                "handover": self.scoped_handover(hospital, account, scope)}
