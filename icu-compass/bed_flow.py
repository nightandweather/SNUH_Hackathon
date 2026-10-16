"""Thirty-day, eight-bed fictional planning sandbox; no clinical predictions."""
from datetime import date, timedelta


def build(profile="bleeding"):
    beds = [None] * 8
    queue, rows, patients = [], [], []
    arrival_count = 3 if profile == "surge" else 1
    delayed_days = 0
    booked_slots = []
    for day in range(1, 31):
        for slot, patient in enumerate(beds):
            if patient and patient["discharge_day"] < day:
                beds[slot] = None
        for _ in range(arrival_count):
            number = len(patients) + 1
            los = 2 + number % 4 if profile != "surge" else 5 + number % 3
            if profile == "bleeding" and number % 7 == 0:
                los += 2
            patient = {"id": f"P{number:03}", "planned_day": day, "los": los,
                       "critical_days": 0 if profile == "calm" else 2 if number % 7 == 0 or profile == "surge" else 1}
            patients.append(patient)
            queue.append(patient)
        for slot in booked_slots + [i for i in range(8) if i not in booked_slots]:
            if beds[slot] is None and queue:
                patient = queue.pop(0)
                patient.update(admit_day=day, discharge_day=day+patient["los"]-1, bed=slot+1)
                beds[slot] = patient
        cells = []
        reserve = arrival_count
        booked_slots = []
        for slot, patient in enumerate(beds):
            if patient:
                elapsed = day-patient["admit_day"]
                status = "green" if day == patient["discharge_day"] else "red" if elapsed < patient["critical_days"] else "blue"
                event = "Transfer to ward" if status == "green" else "Admission" if elapsed == 0 else "ICU stay"
                cells.append({"status": status, "patient": patient["id"], "event": event,
                              "admit_day": patient["admit_day"], "discharge_day": patient["discharge_day"]})
            elif reserve > 0 and day < 30:
                booked_slots.append(slot)
                planned_id = f"P{len(patients)+len(booked_slots):03}"
                cells.append({"status": "yellow", "patient": None, "reserved_patient": planned_id,
                              "event": f"Reserved {planned_id} · next-day surgery"})
                reserve -= 1
            else:
                cells.append({"status": "empty", "patient": None, "event": "Available"})
        delayed_days += len(queue)
        rows.append({"day": day, "date": str(date(2026,10,1)+timedelta(days=day-1)),
                     "beds": cells, "waiting": len(queue)})
    return {"profile": profile, "rows": rows,
            "summary": {"planned": len(patients), "admitted": sum("admit_day" in p for p in patients),
                        "waiting_day_30": len(queue), "waiting_patient_days": delayed_days},
            "note": "Independent planning sandbox: fictional patients, operation bookings, severity states and ward transfers. Not K-MIMIC observations or discharge recommendations. Daily arrival and length-of-stay assumptions differ by scenario; discharge day counts as an occupied bed-day."}
