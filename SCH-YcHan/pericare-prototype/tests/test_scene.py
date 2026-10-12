"""Hospital visualization must agree with the observed clinical/bed state."""
import copy
import json
import math
import tempfile
import unittest

from app.engine import Engine
from app.scene import motion_point


class HospitalSceneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = self.tmp.name + "/scene.db"
        self.e = Engine(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def advance(self, n):
        self.e.mutate("advance", {"minutes": n})

    def action(self, name, **body):
        self.e.mutate(name, {"expected_revision": self.e.state["revision"], **body})

    def scene_patient(self, pid):
        return next(p for p in self.e.view()["scene"]["patients"] if p["id"] == pid)

    def test_every_patient_and_real_bed_has_one_icon_through_full_replay(self):
        for _ in range(73):
            state = self.e.view()
            scene = state["scene"]
            self.assertEqual({p["id"] for p in scene["patients"] if p["phase"] != "DISCHARGED"}, {p["id"] for p in state["patients"] if p["phase"] not in ("DISCHARGED", "DECEASED", "TRANSFERRED")})
            self.assertGreaterEqual(len(scene["patients"]), state["summary"]["patients"])
            self.assertEqual({b["id"] for b in scene["beds"]}, {b["id"] for b in state["beds"]})
            actual = {b["id"]: b["occupant_id"] for b in state["beds"]}
            self.assertEqual(actual, {b["id"]: b["occupant_id"] for b in scene["beds"]})
            for p in scene["patients"]:
                z = next(z for z in scene["zones"] if z["id"] == p["home"]["zone"])
                self.assertTrue(z["x"] < p["home"]["x"] < z["x"] + z["width"])
                self.assertTrue(z["y"] < p["home"]["y"] + 50 < z["y"] + z["height"])
            for r in scene["staff"]:
                self.assertTrue(all(math.isfinite(x) for x in r["position"]))
            if state["minute"] < 360:
                self.advance(5)

    def test_escort_route_matches_actual_reservation_and_nurse(self):
        self.action("play", running=True)
        self.advance(45)
        scene = self.e.view()["scene"]
        p = next(p for p in scene["patients"] if p["id"] == "DEMO-004")
        self.assertEqual(p["phase"], "PACU")
        self.assertEqual(p["motion"]["destination"], "SICU-03")
        self.assertEqual(p["motion"]["origin"], "PACU")
        nurse = next(r for r in scene["staff"] if r["role"] == "transport" and r["patient_id"] == p["id"])
        self.assertEqual(nurse["motion"]["points"], p["motion"]["points"])
        self.assertEqual(nurse["motion"]["start"], p["motion"]["start"])
        self.assertEqual(nurse["motion"]["end"], p["motion"]["end"])
        self.assertIn("pickup", nurse["motion"])
        # No actual admission is invented by an animation target.
        bed = next(b for b in scene["beds"] if b["id"] == "SICU-03")
        self.assertIsNone(bed["occupant_id"])
        self.advance(10)
        p = self.scene_patient("DEMO-004")
        self.assertIsNone(p["motion"])
        self.assertEqual(p["location"], "SICU-03")

    def test_same_preparation_nurse_stays_assigned_between_steps_and_restart(self):
        self.action("play", running=True)
        self.advance(15)
        def assigned():
            return {r["patient_id"]: r["id"] for r in self.e.view()["scene"]["staff"]
                    if r["role"] == "charge" and r["patient_id"]}
        first = assigned()
        self.assertEqual(len(first), 2)
        self.advance(5)
        self.assertEqual(first, assigned())
        self.e = Engine(self.path)
        self.assertEqual(first, assigned())

    def test_patient_slots_do_not_jump_when_neighbour_leaves_or(self):
        before = self.scene_patient("DEMO-003")["home"]
        self.action("play", running=True)
        self.advance(35)
        self.assertEqual(before, self.scene_patient("DEMO-003")["home"])

    def test_quality_hold_removes_movement_without_teleporting_to_destination(self):
        self.action("play", running=True)
        self.advance(45)
        self.assertIsNotNone(self.scene_patient("DEMO-004")["motion"])
        self.action("scenario", patient_id="DEMO-004", kind="artifact")
        p = self.scene_patient("DEMO-004")
        self.assertTrue(p["quality_hold"])
        self.assertIsNone(p["motion"])
        self.assertEqual(p["location"], "PACU")

    def test_ward_handoff_keeps_icu_occupied_until_confirmed_discharge(self):
        self.action("play", running=True)
        self.advance(120)
        self.advance(15)
        scene = self.e.view()["scene"]
        p = next(p for p in scene["patients"] if p["id"] == "DEMO-014")
        self.assertEqual(p["motion"]["destination"], "WARD")
        bed = next(b for b in scene["beds"] if b["id"] == "SICU-02")
        self.assertEqual(bed["occupant_id"], "DEMO-014")
        self.assertEqual(bed["status"], "occupied")
        self.advance(5)
        scene = self.e.view()["scene"]
        bed = next(b for b in scene["beds"] if b["id"] == "SICU-02")
        self.assertIsNone(bed["occupant_id"])
        self.assertEqual(bed["status"], "cleaning")
        self.assertEqual(self.scene_patient("DEMO-014")["zone"], "WARD")
        self.advance(20)
        self.assertEqual(next(b for b in self.e.view()["scene"]["beds"] if b["id"] == "SICU-02")["status"], "available")

    def test_non_modelled_occupant_remains_visible_after_forecast_passes(self):
        self.advance(120)
        b = next(b for b in self.e.view()["scene"]["beds"] if b["id"] == "SICU-05")
        self.assertTrue(b["external_patient"])
        self.assertEqual(b["status"], "occupied")
        self.assertEqual(b["occupant_id"], "비수술 환자 A")
        scene = self.e.view()["scene"]
        self.assertEqual(next(z for z in scene["zones"] if z["id"] == "SICU")["count"],
                         sum(bool(b["occupant_id"]) for b in scene["beds"] if b["unit"] == "SICU"))

    def test_v2_snapshot_adds_scene_without_changing_clinical_state(self):
        self.action("play", running=True)
        self.advance(45)
        old = copy.deepcopy(self.e.state)
        old.pop("scene")
        old.pop("scene_memory")
        self.e.store.save(old)
        self.e = Engine(self.path)
        self.assertEqual(old["patients"], self.e.state["patients"])
        self.assertEqual(old["beds"], self.e.state["beds"])
        self.assertEqual(old["reservations"], self.e.state["reservations"])
        self.assertEqual(old["automation"], self.e.state["automation"])
        self.assertGreaterEqual(len(self.e.view()["scene"]["patients"]), self.e.view()["summary"]["patients"])
        self.assertFalse(self.e.state["running"])

    def test_imported_data_has_locations_without_inventing_autonomous_staff_tasks(self):
        from app.importer import export_canonical
        data = export_canonical(self.e.state)
        self.action("import", dataset=data)
        scene = self.e.view()["scene"]
        self.assertFalse(scene["active"])
        self.assertEqual(scene["mode"], "observed_locations")
        self.assertTrue(all(p["motion"] is None for p in scene["patients"]))
        self.assertTrue(all(r["patient_id"] is None and not r["on_shift"] for r in scene["staff"]))

    def test_public_scene_has_no_future_observations_or_truth_and_cannot_mutate_engine(self):
        scene = self.e.view()["scene"]
        encoded = json.dumps(scene)
        for forbidden in ("truth_icu", "trajectories", "observations", "actual_end_minute", "scene_memory"):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(scene["as_of_minute"], self.e.state["minute"])
        scene["patients"][0]["home"]["x"] = -10000
        self.assertGreater(self.e.view()["scene"]["patients"][0]["home"]["x"], 0)

    def test_failed_commit_keeps_scene_and_staff_assignments_unchanged(self):
        from unittest.mock import patch
        before = copy.deepcopy(self.e.state)
        with patch.object(self.e.store, "save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.advance(45)
        self.assertEqual(before["scene"], self.e.state["scene"])
        self.assertEqual(before["scene_memory"], self.e.state["scene_memory"])

    def test_interpolation_is_bounded_and_handles_zero_length_segments(self):
        route = {"start": 10, "end": 20, "points": [[0, 0], [0, 0], [100, 0], [100, 100]]}
        self.assertEqual(motion_point(route, -20), [0, 0])
        self.assertEqual(motion_point(route, 15), [100, 0])
        self.assertEqual(motion_point(route, 200), [100, 100])


if __name__ == "__main__":
    unittest.main()
