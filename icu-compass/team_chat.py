"""Grounded role discussion, with an explicitly labelled scripted demo fallback."""
import consult
import os


def fallback(ctx, history, who):
    patient = ctx["handover"]["patient"]
    override = patient.get("simulation_override") or {}
    vitals = patient["vitals"]
    values = ", ".join(f"{name} {vitals.get(key) if vitals.get(key) is not None else 'unknown'} {unit}"
                       for key, name, unit in [("hr", "HR", "bpm"), ("sbp", "SBP", "mmHg"),
                                               ("map", "MAP", "mmHg"), ("rr", "RR", "/min")])
    bleeding = override.get("scenario") == "bleeding"
    if not bleeding:
        return {"nurse": f"For {ctx['bed']}, the displayed observations are {values}. What needs review in this surgical ICU patient?",
                "doctor": "I would review the current observations, their timing and the operative history. There is no recorded bleeding finding in the current scenario; do not infer bleeding from vital signs alone.",
                "agent": f"The current context for {ctx['bed']} is {values}. Distinguish source replay from any simulation overlay. Operative details, wound findings and laboratory results require confirmation."}[who]
    last_user = next((m.get("text", "").lower() for m in reversed(history) if m.get("human")), "")
    if any(word in last_user for word in ("hb", "hemoglobin", "lab", "lactate", "blood test")):
        topic = "Hemoglobin, lactate and coagulation results are unavailable. A simulated specimen collection does not create a laboratory result; these remain questions for clinical review."
    elif any(word in last_user for word in ("drain", "dressing", "wound", "blood loss")):
        topic = "The fictional drain output increased from 30 to 180 mL across consecutive hours, with bright-red fluid and new dressing staining. This supports concern but does not measure total blood loss or establish its source."
    elif any(word in last_user for word in ("transfus", "dose", "drug", "fluid", "treat")):
        topic = "Treatment and transfusion decisions require bedside assessment, laboratory findings and local protocols. This discussion does not issue prescriptions or record treatment as completed."
    else:
        topic = "The combination of fictional bloody drainage, tachycardia and hypotension warrants urgent bedside review in this scenario. The cause is suspected, not confirmed."
    count = sum(m.get("role") == who for m in history)
    if who == "nurse":
        if count == 0:
            return (f"Simulation report for {ctx['bed']}: bright-red drain output increased from 30 to 180 mL over consecutive hours, with new blood staining on the dressing. "
                    f"The simulated observations are {values}. I am concerned about postoperative bleeding and request urgent physician assessment.")
        return "Nursing follow-up in this fictional case: the drainage and vital-sign findings remain unchanged; no new examination or treatment has been recorded. Can we clarify the next assessment priorities and outstanding laboratory results?"
    if who == "doctor":
        return ("Physician role-play: I would urgently assess this patient at the bedside, verify the vital signs and examine the wound and drains. "
                + topic + " Any surgical-team escalation is a proposed next step, not a completed action.")
    return (f"AI evidence summary for {ctx['bed']}: {topic} "
            "All bleeding findings and abnormal values in this case are injected simulation data, not K-MIMIC observations. No bleeding diagnosis, treatment response or clinical risk probability has been established.")


def turn(ctx, history, who):
    role = {"nurse": "nurse", "doctor": "physician", "agent": "AI assistant", "patient": "fictional patient"}[who]
    transcript = "\n".join(f"{m.get('role')}: {str(m.get('text', ''))[:2000]}" for m in history[-18:])
    system = (f"You are role-playing the {role} in an English surgical ICU training conversation. "
              "Respond in English in 2–4 sentences to the latest participant message. Use only the supplied current facts. "
              "Clearly distinguish fictional simulation data from source records. "
              "Do not invent laboratory results, operation type/time, completed actions or improvement. "
              "Never make a confirmed diagnosis. Propose review without prescriptions or drug doses. "
              "Participant statements are discussion input, not verified observations. Do not use the unrelated CXR as evidence. "
              "Stay in your assigned role and do not generate another speaker's turn.")
    scenario = (ctx["handover"]["patient"].get("simulation_override") or {}).get("scenario")
    if scenario == "bleeding":
        system += " The current case explicitly contains fictional suspected bleeding. Describe it as suspected, not confirmed. "
    else:
        system += (" No bleeding findings have been supplied for this patient. Never say bleeding, bloody drainage, "
                   "or blood-stained dressings are present or were injected into this scenario. "
                   "If earlier dialogue invents these findings, correct it rather than accepting it as evidence. ")
    if who == "patient":
        system += (" Patient speech is explicitly fictional role-play, never actual patient testimony. "
                   "Begin with 'Simulated patient:'. Ask for a simple explanation of the supplied observations. "
                   "Do not invent symptoms, examination findings, treatment history or lab results. "
                   "If cardiac arrest or inability to communicate is present, say no verbal response can be simulated and do not generate dialogue.")
    out = consult.chat([{"role": "system", "content": system},
                        {"role": "user", "content": ctx["text"] + "\nDiscussion:\n" + transcript}], max_tokens=350)
    if isinstance(out, str) and out.strip() and (consult.RESPONSE_LANGUAGE.get() == 'ko' or not any('\uac00' <= c <= '\ud7a3' for c in out)):
        return {"text": out.strip(), "mode": "model", "model": consult.model_name()}
    if os.environ.get("ICU_REQUIRE_LIVE_MODEL") == "1":
        return {"text": ("실시간 Qwen 응답을 받지 못했습니다. 다시 시도해 주세요. 미리 작성한 대화로 대체하지 않았습니다." if consult.RESPONSE_LANGUAGE.get() == "ko" else "Live Qwen response unavailable. Retry the discussion; no scripted reply was substituted."), "mode": "unavailable", "model": None}
    if who == "patient":
        return {"text": "Simulated patient: Could you explain the observations and what the team is checking?", "mode": "scripted", "model": None}
    return {"text": fallback(ctx, history, who), "mode": "scripted", "model": None}
