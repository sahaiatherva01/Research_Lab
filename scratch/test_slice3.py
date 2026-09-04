import unittest
import os
import fitz
from app import app
import database as db
import research.pdf_reader as pdf_reader
import research.papers as papers_mgmt

class Slice3PDFReaderTests(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        self.app.config['TESTING'] = True

    def test_01_pymupdf_extraction(self):
        # Create a sample synthetic PDF for test verification
        sample_pdf_path = os.path.join(papers_mgmt.UPLOADS_DIR, "test_paper.pdf")
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 72), "Abstract: We demonstrate that reaction-diffusion dynamics can form spatial structures.")
        page.insert_text((50, 120), "Section 1: The mathematical formulation proceeds from two interacting morphogens with diffusion coefficients D1 and D2.")
        doc.save(sample_pdf_path)
        doc.close()

        # Test extraction
        res = pdf_reader.extract_pdf_pages(sample_pdf_path)
        self.assertTrue(res.get("success"), f"Extraction failed: {res.get('error')}")
        self.assertEqual(len(res["pages"]), 1)
        self.assertIn("reaction-diffusion dynamics", res["pages"][0]["text"])

        # Test chunking
        chunk_res = pdf_reader.extract_pdf_chunks(sample_pdf_path, chunk_size=20, overlap=5)
        self.assertTrue(chunk_res.get("success"))
        self.assertTrue(chunk_res.get("total_chunks") >= 1)

    def test_02_paper_annotations_flow(self):
        # Register researcher
        db.auth_sign_up("rosalind.franklin@kcl.ac.uk", "dna12345", "Rosalind Franklin")
        user = db.auth_sign_in("rosalind.franklin@kcl.ac.uk", "dna12345")["user"]

        proj_res = db.create_project(
            "X-Ray Crystallography of Nucleic Acids",
            "What is the helical symmetry of B-form DNA fibers?",
            "Biophysics",
            "Diffraction analysis of sodium thymonucleate.",
            user["id"]
        )
        project_id = proj_res["project_id"]

        paper_res = papers_mgmt.save_paper_to_project(project_id, {
            "title": "Molecular Configuration in Sodium Thymonucleate",
            "authors": ["R. E. Franklin", "R. G. Gosling"],
            "abstract": "The helical structure gives characteristic cross-diffraction pattern.",
            "year": 1953
        }, user["id"])
        paper_id = paper_res["paper_id"]

        # Add annotation
        ann_res = db.add_paper_annotation(
            project_id=project_id,
            paper_id=paper_id,
            user_id=user["id"],
            page_number=1,
            selected_text="characteristic cross-diffraction pattern indicates cylindrical helical symmetry",
            comment="Crucial empirical evidence for double helix model.",
            color="#10B981"
        )
        self.assertTrue(ann_res["success"], f"Annotation creation failed: {ann_res.get('error')}")
        annotation_id = ann_res["annotation_id"]

        # Retrieve annotations
        annotations = db.get_paper_annotations(project_id, paper_id, user["id"])
        self.assertEqual(len(annotations), 1)
        self.assertEqual(annotations[0]["selected_text"], "characteristic cross-diffraction pattern indicates cylindrical helical symmetry")
        self.assertEqual(annotations[0]["color"], "#10B981")

        # Delete annotation
        del_res = db.delete_paper_annotation(project_id, annotation_id, user["id"])
        self.assertTrue(del_res["success"])
        self.assertEqual(len(db.get_paper_annotations(project_id, paper_id, user["id"])), 0)

if __name__ == '__main__':
    unittest.main()
