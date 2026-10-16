import copy
import unittest
from unittest.mock import patch
import consult
import demo_profiles
import team_chat


class DemoProfilesTest(unittest.TestCase):
    def test_explicit_care_indicators_and_calendar_rollover(self):
        h = demo_profiles.create("surge")
        bed = h.beds["SICU-05"]
        pt = h._bed_json(bed)["patient"]
        self.assertTrue(pt["care_indicators"]["cpr_today"])
        self.assertTrue(pt["care_indicators"]["surgery_today"])
        self.assertTrue(pt["care_indicators"]["pressor_unstable"])
        self.assertTrue(pt["devices"]["crrt"])
        self.assertTrue(pt["devices"]["ventilator"])
        self.assertEqual(pt["pressor"], 1)
        ctx = consult.context(h, "SICU-05")
        self.assertTrue(ctx["handover"]["patient"]["care_indicators"]["cpr_today"])
        h.cfg["start_clock"] = "23:30"
        h.t = 30
        self.assertEqual(h._bed_json(bed)["patient"]["calendar_day"], 1)
        flags = consult.context(h, "SICU-05")["handover"]["patient"]["care_indicators"]
        self.assertIsNone(flags["cpr_today"])
        self.assertIsNone(flags["surgery_today"])
        self.assertTrue(bed["patient"]["src"]["care_indicators"]["cpr_today"])

    def test_calm_has_eight_beds_with_distinct_reserved_and_available_states(self):
        h = demo_profiles.create("calm")
        self.assertEqual(set(h.units), {"CSICU", "NSICU", "SICU", "TSICU"})
        self.assertEqual(len(h.incidents), 0)
        for unit in h.units.values():
            beds = [h.beds[bid] for bid in unit["bed_ids"]]
            self.assertEqual(len(beds), 8)
            self.assertEqual(sum(b["patient"] is not None for b in beds), 6)
            self.assertEqual(sum(bool(b.get("reservation")) for b in beds), 1)
        for _ in range(120):
            h.step()
        self.assertTrue(h.beds["SICU-07"]["patient"])
        self.assertFalse(h.beds["SICU-07"].get("reservation"))
        self.assertIsNone(h.beds["SICU-08"]["patient"])

    def test_bleeding_preserves_baseline_and_marks_fictional_findings(self):
        h = demo_profiles.create("bleeding")
        bed = h.beds["SICU-01"]
        source = copy.deepcopy(bed["patient"]["src"])
        ctx = consult.context(h, "SICU-01")
        self.assertEqual(bed["patient"]["vitals"]["map"], 58)
        self.assertEqual(bed["patient"]["observed_vitals"]["map"], 82)
        self.assertIn("180 mL", ctx["text"])
        self.assertIn("fictional", ctx["text"].lower())
        for _ in range(30):
            h.step()
        self.assertEqual(bed["patient"]["src"], source)
        self.assertEqual(h.care_actions, [])

    def test_overload_creates_shortages_and_higher_fatigue_than_calm(self):
        calm, surge = demo_profiles.create("calm"), demo_profiles.create("surge")
        self.assertEqual(len(surge.incidents), 16)
        self.assertTrue(any(i["shortage"] > 0 for i in surge.state()["incidents"]))
        self.assertGreater(surge.metrics()["fatigue_current_mean"], calm.metrics()["fatigue_current_mean"])
        self.assertTrue(all(surge.nurses[n]["unit"] == i["unit"] for i in surge.incidents for n in i["responders"]))

    def test_live_model_failure_does_not_fake_patient_speech(self):
        ctx = consult.context(demo_profiles.create("bleeding"), "SICU-01")
        with patch.object(consult, "chat", return_value=None), patch.dict("os.environ", {"ICU_REQUIRE_LIVE_MODEL": "1"}):
            answer = team_chat.turn(ctx, [], "patient")
        self.assertEqual(answer["mode"], "unavailable")
        self.assertIsNone(answer["model"])


if __name__ == "__main__":
    unittest.main()
