import unittest
import json
from app import app
import database as db
import research.search as academic_search
import research.papers as papers_mgmt

class Slice2LiteratureTests(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        self.app.config['TESTING'] = True

    def test_01_real_academic_search(self):
        # Hit real academic search
        res = academic_search.search_academic_papers("Attention is All You Need", limit=3)
        self.assertTrue(res.get("success"), f"Search failed: {res.get('error')}")
        papers = res.get("papers", [])
        self.assertTrue(len(papers) > 0, "Expected at least 1 paper in search results")
        
        # Verify schema
        first_paper = papers[0]
        self.assertIn("title", first_paper)
        self.assertIn("authors", first_paper)
        self.assertIn("abstract", first_paper)
        print(f"\n[Test] Found real paper: '{first_paper['title']}' by {first_paper['authors'][:2]}")

    def test_02_save_and_manage_paper_library(self):
        # Register researcher
        db.auth_sign_up("marie.curie@sorbonne.fr", "radium123", "Marie Curie")
        login_res = db.auth_sign_in("marie.curie@sorbonne.fr", "radium123")
        user_id = login_res["user"]["id"]

        # Create project
        proj_res = db.create_project(
            "Radiation Properties of Uranium Compounds",
            "What determines the ionization rate of pitchblende minerals?",
            "Nuclear Physics",
            "Investigating spontaneous ray emissions.",
            user_id
        )
        self.assertTrue(proj_res["success"])
        project_id = proj_res["project_id"]

        # Save paper
        paper_data = {
            "title": "On a New Substance Strongly Radio-Active, Contained in Pitchblende",
            "authors": ["P. Curie", "M. Curie", "G. Bemont"],
            "abstract": "The authors describe the discovery of a new radioactive element, radium.",
            "year": 1898,
            "venue": "Comptes Rendus",
            "doi": "10.1038/curie1898",
            "arxiv_id": None,
            "open_access_pdf_url": None
        }

        save_res = papers_mgmt.save_paper_to_project(project_id, paper_data, user_id)
        self.assertTrue(save_res["success"], f"Save paper failed: {save_res.get('error')}")
        paper_id = save_res["paper_id"]

        # Retrieve saved papers
        saved = papers_mgmt.get_project_papers(project_id, user_id)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["title"], "On a New Substance Strongly Radio-Active, Contained in Pitchblende")
        self.assertEqual(saved[0]["authors"], ["P. Curie", "M. Curie", "G. Bemont"])

        # Delete paper
        del_res = papers_mgmt.delete_project_paper(project_id, paper_id, user_id)
        self.assertTrue(del_res["success"])

        # Check library is now 0
        saved_after = papers_mgmt.get_project_papers(project_id, user_id)
        self.assertEqual(len(saved_after), 0)

if __name__ == '__main__':
    unittest.main()
