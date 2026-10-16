"""Human-entered receipt of a simulator handover, without sending messages."""
import copy


def record_receipt(hospital, nurse_id, bed_id, handover_t, action, text=None):
    if action not in ("ack", "question"):
        raise ValueError("인계 확인 또는 질문을 선택하세요.")
    snapshot = hospital.last_handover
    if not snapshot or handover_t != snapshot["t"]:
        raise RuntimeError("인계 자료가 바뀌었습니다. 최신 교대 자료를 확인하세요.")
    bed = hospital.beds.get(bed_id)
    pt = bed and bed["patient"]
    row = next((item for item in snapshot["patients"] if item["bed"] == bed_id), None)
    if pt is None or row is None or row["pid"] != pt["src"]["pid"] or row["admit_t"] != pt["admit_t"]:
        raise RuntimeError("인계 대상 환자가 바뀌었습니다. 새 환자 자료를 확인하세요.")
    nurse = hospital.nurses.get(nurse_id)
    if (nurse is None or nurse["unit"] != bed["unit"] or bed["nurse"] != nurse_id
            or nurse["staff_id"] != row["to_staff_id"]):
        raise PermissionError("이 환자의 인계를 받는 현재 담당자만 확인·질문할 수 있습니다.")
    if action == "question" and (not isinstance(text, str) or not text.strip() or len(text) > 1000):
        raise ValueError("인계 질문을 1~1000자 이내로 입력하세요.")
    receipt = row.setdefault("receipt", {"status": "pending", "received_by": None,
                                         "received_t": None, "received_clock": None, "questions": []})
    new_entry = action == "question" or receipt["received_t"] is None
    if action == "ack":
        if receipt["received_t"] is None:
            receipt.update(received_by=nurse["staff_id"], received_t=hospital.t,
                           received_clock=hospital.clock())
        receipt["status"] = "question_open" if receipt["questions"] else "received"
    else:
        receipt["questions"].append({"t": hospital.t, "clock": hospital.clock(),
                                     "staff_id": nurse["staff_id"], "text": text.strip(),
                                     "source": "user_entered"})
        receipt["status"] = "question_open"
    if new_entry:
        if not hasattr(hospital, "handover_receipts"):
            hospital.handover_receipts = []
        hospital.handover_receipts.append({"handover_t": snapshot["t"], "t": hospital.t,
                                           "clock": hospital.clock(), "bed": bed_id,
                                           "pid": row["pid"], "admit_t": row["admit_t"],
                                           "from_staff_id": row["from_staff_id"],
                                           "staff_id": nurse["staff_id"], "action": action,
                                           "text": text.strip() if action == "question" else None,
                                           "source": "user_entered"})
    return copy.deepcopy(receipt)
