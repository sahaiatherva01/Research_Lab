import unittest
from app import app
import database as db

class Slice1AuthAndWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        self.app.config['TESTING'] = True

    def test_01_signup_and_login_flow(self):
        import uuid
        test_email = f"ada.{uuid.uuid4().hex[:6]}@cambridge.ac.uk"
        # 1. Sign up user
        res = self.client.post('/signup', data={
            'email': test_email,
            'password': 'password123',
            'full_name': 'Ada Lovelace'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Ada Lovelace', res.data)
        self.assertIn(b'Research Projects', res.data)

        # 2. Create Project
        res = self.client.post('/projects/new', data={
            'title': 'Analytical Engine Algorithmic Complexity',
            'domain': 'Computational Theory',
            'research_question': 'How does symbolic execution scale on non-Von-Neumann machinery?',
            'description': 'Foundational analysis of step functions on mechanical analytical hardware.'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Analytical Engine Algorithmic Complexity', res.data)
        self.assertIn(b'Computational Theory', res.data)
        self.assertIn(b'0', res.data) # 0 papers, 0 notes

    def test_02_collaborator_invite_flow(self):
        import uuid
        owner_email = f"ada.owner.{uuid.uuid4().hex[:6]}@cambridge.ac.uk"
        collab_email = f"charles.{uuid.uuid4().hex[:6]}@cambridge.ac.uk"

        # Register owner and collaborator
        db.auth_sign_up(owner_email, 'password123', 'Ada Lovelace')
        db.auth_sign_up(collab_email, 'password123', 'Charles Babbage')
        
        # Sign in as Ada
        self.client.post('/login', data={
            'email': owner_email,
            'password': 'password123'
        }, follow_redirects=True)

        user_id = db.auth_sign_in(owner_email, 'password123')['user']['id']
        proj_res = db.create_project("Engine Theory", "Hypothesis", "Math", "Desc", user_id)
        proj_id = proj_res['project_id']

        # Invite Charles as Researcher
        res = self.client.post(f'/projects/{proj_id}/invite', data={
            'email': collab_email,
            'role': 'researcher'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Charles Babbage', res.data)
        self.assertIn(b'researcher', res.data)

        # Sign out Ada, sign in Charles, verify project shows in Charles's dashboard with role 'researcher'
        self.client.get('/logout', follow_redirects=True)
        self.client.post('/login', data={
            'email': collab_email,
            'password': 'password123'
        }, follow_redirects=True)

        dash_res = self.client.get('/dashboard')
        self.assertIn(b'Engine Theory', dash_res.data)
        self.assertIn(b'researcher', dash_res.data)


if __name__ == '__main__':
    unittest.main()
