"""Routine timing varies independently of patient replay and urgent dispatch."""
import copy
import unittest
from collections import Counter

import engine
from test_shifts import admit, advance, hospital, recorded_pool


def occupied_hospital(policy="fixed", seed=1, arrivals=0):
    pool = [dict(copy.deepcopy(recorded_pool()[0]), pid=f"case-{index}") for index in range(80)]
    return engine.Hospital(pool, policy=policy, seed=seed, occupancy=1,
                           arrivals_per_unit_shift=arrivals)


class TimingTests(unittest.TestCase):
    def test_first_routine_departures_are_spread_across_minutes(self):
        h = occupied_hospital()
        departed = {}
        for _ in range(engine.ROUND_MIN):
            before = {nid: n["pos"] for nid, n in h.nurses.items()}
            h.step()
            for nid, n in h.nurses.items():
                if n["role"] == "bedside" and n["pos"] != before[nid]:
                    departed.setdefault(nid, h.t)
        self.assertEqual(len(departed), 32)
        self.assertGreaterEqual(len(set(departed.values())), 6)
        self.assertLess(max(Counter(departed.values()).values()), 16)
        first_schedule = {nid: n["next_round_t"] for nid, n in h.nurses.items()}
        advance(h, 60)
        self.assertTrue(all(n["next_round_t"] > first_schedule[nid] for nid, n in h.nurses.items()))

    def test_empty_beds_are_not_round_destinations_and_one_patient_stays_put(self):
        h = hospital(policy="auto")
        stations = {nid: n["pos"] for nid, n in h.nurses.items()}
        advance(h, 30)
        self.assertEqual({nid: n["pos"] for nid, n in h.nurses.items()}, stations)
        bed = admit(h)
        advance(h, 20)
        nurse = h.nurses[bed["nurse"]]
        self.assertEqual(nurse["pos"], bed["pos"])
        for _ in range(40):
            h.step()
            self.assertEqual(nurse["pos"], bed["pos"])
        self.assertEqual(h.beds["MICU-02"]["patient"], None)

    def test_occupied_cover_beds_are_included_in_routine_rounds(self):
        h = hospital(policy="auto")
        own = admit(h)
        covered = admit(h, "MICU-03")
        nurse = h.nurses[own["nurse"]]
        nurse["cover"].append(covered["id"])
        visited = set()
        for _ in range(60):
            h.step()
            visited.add(nurse["pos"])
        self.assertTrue({own["pos"], covered["pos"]}.issubset(visited))
        self.assertNotIn(h.beds["MICU-02"]["pos"], visited)

    def test_same_seed_reproduces_complete_movement_and_breaks(self):
        first, second = occupied_hospital(), occupied_hospital()
        advance(first, 530)
        advance(second, 530)
        self.assertEqual(first.state(), second.state())
        self.assertEqual(first.rng.getstate(), second.rng.getstate())
        other = occupied_hospital(seed=2)
        initial = occupied_hospital()
        self.assertNotEqual([n["next_round_t"] for n in other.nurses.values()],
                            [n["next_round_t"] for n in initial.nurses.values()])

    def test_timing_streams_preserve_patient_randomness_and_policy_comparability(self):
        fixed, auto = occupied_hospital(arrivals=4), occupied_hospital("auto", arrivals=4)
        rng_before = fixed.rng.getstate()
        fixed._init_timing()
        self.assertEqual(fixed.rng.getstate(), rng_before)
        for minute in range(530):
            fixed.step()
            auto.step()
            self.assertEqual(fixed.rng.getstate(), auto.rng.getstate(), minute)
            self.assertEqual([n["next_round_t"] for n in fixed.nurses.values()],
                            [n["next_round_t"] for n in auto.nurses.values()], minute)
        for bid in fixed.beds:
            fp, ap = fixed.beds[bid]["patient"], auto.beds[bid]["patient"]
            self.assertEqual((fp["src"]["pid"], fp["offset"], fp["observed_vitals"]) if fp else None,
                             (ap["src"]["pid"], ap["offset"], ap["observed_vitals"]) if ap else None)

    def test_shift_rotation_resets_timing_for_incoming_identity_and_cycle(self):
        h = hospital()
        day = [n["next_round_t"] for n in h.nurses.values()]
        advance(h, 479)
        for n in h.nurses.values():
            n["next_round_t"] = 100000
        h.step()
        self.assertTrue(all(n["staff_id"].startswith("E-") and 480 < n["next_round_t"] <= 495
                            for n in h.nurses.values()))
        self.assertTrue(all(480 < u["next_break_check_t"] <= 495 for u in h.units.values()))
        advance(h, 960)
        next_day = [n["next_round_t"] - h.t for n in h.nurses.values()]
        self.assertEqual(h.state()["shift"]["cycle"], 1)
        self.assertNotEqual(next_day, day)

    def test_partial_shift_uses_wall_clock_break_targets_without_truncated_breaks(self):
        h = hospital("14:50")
        for n in h.nurses.values():
            if n["role"] == "bedside":
                self.assertLessEqual(abs(n["fixed_break_t"] - (-470 + engine.FIXED_BREAK[n["k"]])),
                                     engine.FIXED_BREAK_JITTER)
        advance(h, 9)
        self.assertTrue(all(n["breaks"] == 0 for n in h.nurses.values()))
        h.step()
        self.assertTrue(all(10 < n["next_round_t"] <= 25 for n in h.nurses.values()))
        self.assertEqual(h.state()["shift"]["code"], "E")

    def test_fixed_break_retries_require_local_buddy_and_do_not_overlap(self):
        h = hospital()
        admit(h)
        nurse, buddy = h.nurses["MICU-1"], h.nurses["MICU-2"]
        target = nurse["fixed_break_t"]
        buddy["incident"] = 999  # unavailable; other ICUs still have free staff
        advance(h, target + 2)
        self.assertEqual(nurse["breaks"], 0)
        buddy["incident"] = None
        h.step()
        self.assertEqual(nurse["breaks"], 1)
        self.assertTrue(nurse["on_break"])
        self.assertIn("MICU-01", buddy["cover"])
        self.assertEqual(buddy["unit"], nurse["unit"])
        for _ in range(140):
            h.step()
            for unit in h.units.values():
                self.assertLessEqual(sum(h.nurses[nid]["on_break"] for nid in unit["nurse_ids"]), 1)
        self.assertTrue(all(n["breaks"] == 1 for n in h.nurses.values() if n["role"] == "bedside"))
        self.assertGreater(len({n["fixed_break_t"] for n in h.nurses.values() if n["k"] == 1}), 1)

    def test_auto_breaks_start_at_different_minutes_across_icus(self):
        h = hospital(policy="auto")
        for n in h.nurses.values():
            n["fatigue"] = engine.FATIGUE_WARN + 1
        starts = {}
        for _ in range(15):
            h.step()
            for unit in h.units.values():
                if any(h.nurses[nid]["on_break"] for nid in unit["nurse_ids"]):
                    starts.setdefault(unit["id"], h.t)
        self.assertEqual(len(starts), 8)
        self.assertGreater(len(set(starts.values())), 1)

    def test_emergency_dispatch_does_not_wait_for_routine_timing(self):
        for policy in ("fixed", "auto"):
            with self.subTest(policy=policy):
                h = hospital(policy=policy)
                admit(h)
                for n in h.nurses.values():
                    n["next_round_t"] = 100000
                event = h.trigger_emergency("MICU-01", "hypoxia")
                self.assertEqual(h.t, 0)
                self.assertEqual(len(event["responders"]), 1)
                self.assertEqual(h.doctors["MD-MICU"]["status"], "called")
                self.assertEqual(h.doctors["MD-MICU"]["incident"], event["id"])
                advance(h, 2)
                self.assertIsNotNone(h.incidents[0]["first"])
                self.assertIsNotNone(h.incidents[0]["doctor_arrived_t"])


if __name__ == "__main__":
    unittest.main()
