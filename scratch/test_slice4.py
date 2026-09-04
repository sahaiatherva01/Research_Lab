import unittest
import os
import pymupdf as fitz
from app import app
import database as db
import research.papers as papers_mgmt
import research.rag as rag
import ai.research_agent as research_agent

class Slice4ResearchAITests(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        self.app.config['TESTING'] = True

    def test_01_rag_indexing_and_grounded_qa(self):
        # Register user
        db.auth_sign_up("richard.feynman@caltech.edu", "quantum123", "Richard Feynman")
        user = db.auth_sign_in("richard.feynman@caltech.edu", "quantum123")["user"]

        # Create project
        proj_res = db.create_project(
            "Quantum Electrodynamics & Path Integrals",
            "How do probability amplitudes sum over paths in spacetime?",
            "Theoretical Physics",
            "Space-time approach to non-relativistic quantum mechanics.",
            user["id"]
        )
        project_id = proj_res["project_id"]

        # Save paper 1
        p1_res = papers_mgmt.save_paper_to_project(project_id, {
            "title": "Space-Time Approach to Non-Relativistic Quantum Mechanics",
            "authors": ["R. P. Feynman"],
            "abstract": "The probability amplitude for a particle to go from one point to another is a sum over all possible paths with weight exp(iS/hbar).",
            "year": 1948
        }, user["id"])
        self.assertTrue(p1_res["success"])
        p1_id = p1_res["paper_id"]

        # Create sample cached PDF with specific verifiable facts
        pdf_path = os.path.join(papers_mgmt.UPLOADS_DIR, project_id, f"{p1_id}.pdf")
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
        doc = fitz.open()
        page1 = doc.new_page()
        page1.insert_text((50, 72), "Abstract: We present the path integral formulation of quantum mechanics.")
        page1.insert_text((50, 110), "The classical action S is computed as the time integral of the Lagrangian L = T - V.")
        page1.insert_text((50, 150), "Interference among paths accounts for the emergence of the principle of least action in the classical limit as hbar approaches zero.")
        doc.save(pdf_path)
        doc.close()


        # Build FAISS index
        idx_res = rag.build_project_faiss_index(project_id, user["id"])
        self.assertTrue(idx_res.get("success"), f"Indexing failed: {idx_res.get('error')}")
        self.assertTrue(idx_res.get("total_chunks") >= 1)

        # Query vector search
        search_res = rag.search_project_index(project_id, "How is classical action S computed from Lagrangian?", top_k=2)
        self.assertTrue(search_res.get("success"))
        self.assertTrue(len(search_res["results"]) > 0)
        self.assertIn("Lagrangian", search_res["results"][0]["text"])

        # Query Research AI Agent
        qa_res = research_agent.ask_research_agent(project_id, user["id"], "What is the formula for classical action S?")
        self.assertTrue(qa_res.get("success"), f"QA failed: {qa_res.get('error')}")
        self.assertIn("answer", qa_res)
        self.assertTrue(len(qa_res.get("sources", [])) > 0)
        self.assertEqual(qa_res["sources"][0]["paper_title"], "Space-Time Approach to Non-Relativistic Quantum Mechanics")
        self.assertEqual(qa_res["sources"][0]["page_number"], 1)

    def test_02_empty_literature_handling(self):
        db.auth_sign_up("empty.user@lab.edu", "password123", "Empty User")
        user = db.auth_sign_in("empty.user@lab.edu", "password123")["user"]
        proj_res = db.create_project("Empty Project", "No question", "General", "Desc", user["id"])
        
        qa_res = research_agent.ask_research_agent(proj_res["project_id"], user["id"], "What are the baselines?")
        self.assertFalse(qa_res.get("success"))
        self.assertIn("No saved papers found", qa_res.get("error"))

if __name__ == '__main__':
    unittest.main()
