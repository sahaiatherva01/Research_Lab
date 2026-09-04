import unittest
from app import app
import database as db

class Slice5ResearchNotesTests(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        self.app.config['TESTING'] = True

    def test_01_notes_lifecycle_and_counts(self):
        # Register user
        db.auth_sign_up("enrico.fermi@uchicago.edu", "reactor123", "Enrico Fermi")
        user = db.auth_sign_in("enrico.fermi@uchicago.edu", "reactor123")["user"]

        # Create project
        proj_res = db.create_project(
            "Self-Sustaining Nuclear Chain Reactions",
            "What is the critical mass and neutron multiplication factor k for uranium-graphite lattice?",
            "Nuclear Engineering",
            "Experimental graphite pile construction under Stagg Field stadium.",
            user["id"]
        )
        project_id = proj_res["project_id"]

        # Verify initial notes count is 0
        initial_projects = db.get_user_projects(user["id"])
        target_proj = next(p for p in initial_projects if p["id"] == project_id)
        self.assertEqual(target_proj["notes_count"], 0)

        # Create Note 1
        n1_res = db.create_research_note(
            project_id=project_id,
            title="Cadmium Control Rod Measurements",
            content="Observed neutron flux drop when cadmium rods are inserted by 25 cm.",
            user_id=user["id"]
        )
        self.assertTrue(n1_res["success"])
        n1_id = n1_res["note_id"]

        # Retrieve notes
        notes = db.get_project_notes(project_id, user["id"])
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["title"], "Cadmium Control Rod Measurements")
        self.assertEqual(notes[0]["author_name"], "Enrico Fermi")

        # Update Note 1
        upd_res = db.update_research_note(
            project_id=project_id,
            note_id=n1_id,
            title="Cadmium Control Rod Measurements (Calibrated)",
            content="Observed neutron flux drop when cadmium rods are inserted by 25 cm. Multiplication factor k = 1.0006.",
            user_id=user["id"]
        )
        self.assertTrue(upd_res["success"])

        # Check updated note
        notes_updated = db.get_project_notes(project_id, user["id"])
        self.assertEqual(notes_updated[0]["title"], "Cadmium Control Rod Measurements (Calibrated)")
        self.assertIn("k = 1.0006", notes_updated[0]["content"])

        # Verify dashboard shows 1 note
        dash_projects = db.get_user_projects(user["id"])
        target_dash_proj = next(p for p in dash_projects if p["id"] == project_id)
        self.assertEqual(target_dash_proj["notes_count"], 1)

        # Delete Note
        del_res = db.delete_research_note(project_id, n1_id, user["id"])
        self.assertTrue(del_res["success"])
        self.assertEqual(len(db.get_project_notes(project_id, user["id"])), 0)

if __name__ == '__main__':
    unittest.main()
