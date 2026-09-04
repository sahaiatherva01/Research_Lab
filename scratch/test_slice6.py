import unittest
import os
from app import app
import database as db
import research.git_tracker as git_tracker

class Slice6GitIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        self.app.config['TESTING'] = True

    def test_01_git_repo_lifecycle_and_commits(self):
        # Register user
        db.auth_sign_up("linus.torvalds@kernel.org", "gitmaster123", "Linus Torvalds")
        user = db.auth_sign_in("linus.torvalds@kernel.org", "gitmaster123")["user"]

        # Create project (should auto-init git repo)
        proj_res = db.create_project(
            "Distributed Content-Addressable Object Storage",
            "Can a directed acyclic graph of SHA-1 hashes provide lock-free version control?",
            "Computer Systems",
            "Initial exploration of decentralized revision control architectures.",
            user["id"]
        )
        project_id = proj_res["project_id"]

        # 1. Verify repo path and files
        repo_path = git_tracker.get_repo_path(project_id)
        self.assertTrue(os.path.exists(os.path.join(repo_path, ".git")))
        self.assertTrue(os.path.exists(os.path.join(repo_path, "README.md")))
        self.assertTrue(os.path.exists(os.path.join(repo_path, ".gitignore")))

        # 2. Check initial commit
        commits = git_tracker.get_commit_history(project_id)
        self.assertTrue(len(commits) >= 1)
        self.assertIn("Initial", commits[0]["message"])
        self.assertEqual(len(commits[0]["short_hash"]), 7)

        # 3. Check File Tree
        tree = git_tracker.get_project_file_tree(project_id)
        file_names = [item["name"] for item in tree]
        self.assertIn("README.md", file_names)
        self.assertIn(".gitignore", file_names)

        # 4. Save and commit new file
        save_res = git_tracker.save_and_commit_file(
            project_id=project_id,
            relative_path="src/sha1_tree.py",
            content="def compute_tree_hash(blobs):\n    import hashlib\n    return hashlib.sha1(''.join(blobs).encode()).hexdigest()\n",
            message="Implement tree hash computation logic",
            author_name="Linus Torvalds",
            author_email="linus.torvalds@kernel.org"
        )
        self.assertTrue(save_res["success"], f"Commit failed: {save_res.get('output')}")

        # 5. Check updated commit history
        updated_commits = git_tracker.get_commit_history(project_id)
        self.assertEqual(len(updated_commits), 2)
        self.assertEqual(updated_commits[0]["message"], "Implement tree hash computation logic")
        self.assertEqual(updated_commits[0]["author_name"], "Linus Torvalds")

        # 6. Read file content safely
        read_res = git_tracker.get_file_content(project_id, "src/sha1_tree.py")
        self.assertTrue(read_res["success"])
        self.assertIn("compute_tree_hash", read_res["content"])

if __name__ == '__main__':
    unittest.main()
