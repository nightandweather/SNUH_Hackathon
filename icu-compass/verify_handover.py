"""공개 데모 환자로 기록 기반 인계를 확인한다. --model은 실제 모델 응답을 요구한다."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

import consult
import engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="store_true", help="설정된 모델을 호출하고 성공 여부를 확인")
    parser.add_argument("--output", type=Path, help="검증 결과 JSON 저장 위치")
    parser.add_argument("--emergency", choices=("code_blue", "hypoxia", "hypotension"),
                        help="인계 전에 응급 시연과 간호사 출동을 실행")
    args = parser.parse_args()
    h = engine.Hospital(engine.load_pool("mimic"), seed=7, occupancy=1, arrivals_per_unit_shift=0)
    bed = next(b for b in h.beds.values() if b["patient"] and b["unit"] == "MICU")
    note = "시연 입력: 활력징후를 재확인했고 담당 MD에게 현재 상태를 보고함."
    record = h.record_care_action(bed["nurse"], bed["id"], note)
    if args.emergency:
        h.trigger_emergency(bed["id"], args.emergency)
        for _ in range(3):
            h.step()
    ctx = consult.context(h, bed["id"], nurse_id=bed["nurse"])
    if args.model:
        result = consult.handover_turn(ctx)
    else:
        with patch.object(consult, "chat", return_value=None):
            result = consult.handover_turn(ctx)
    checks = {
        "explicit_record_present": note in result["text"],
        "recorded_staff_present": record["staff_id"] in result["text"],
        "patient_present": bed["patient"]["src"]["pid"] in result["text"],
        "current_map_present": f"MAP {bed['patient']['vitals']['map']}" in result["text"],
        "chat_does_not_add_actions": h.care_actions == [record],
        "actual_model_response": result["mode"] == "model" if args.model else None,
        "scenario_origin_is_separate": (ctx["handover"]["patient"]["vitals_origin"] == "simulation_injected"
                                        if args.emergency else None),
        "simulation_activities_present": bool(ctx.get("activities")) if args.emergency else None,
    }
    success = all(value for value in checks.values() if value is not None)
    report = {"success": success, "data": "public MIMIC-IV demo plus synthetic ward scenario",
              "record_is_demo_input": True, "mode": result["mode"], "model": result["model"],
              "checks": checks, "text": result["text"]}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(result["text"])
    print("\n검증:", json.dumps(checks, ensure_ascii=False))
    print("결과:", "통과" if success else "미완료")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
