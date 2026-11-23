import os
from pathlib import Path
import tempfile
import unittest

class QueueTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("AGENT_DB")
        os.environ["AGENT_DB"] = str(Path(self.tmp.name) / "tasks.sqlite3")
        import agent_company
        self.app = agent_company
        self.app.DB = Path(os.environ["AGENT_DB"])
        self.app.init()

    def tearDown(self):
        if self.old is None:
            os.environ.pop("AGENT_DB", None)
        else:
            os.environ["AGENT_DB"] = self.old
        self.tmp.cleanup()

    def test_mock_review_approval(self):
        tid = self.app.add("research", "mock", "Test task")
        self.assertEqual(self.app.run_once(), tid)
        self.assertEqual(self.app.list_tasks()[0]["status"], "review")
        self.app.approve(tid)
        self.assertEqual(self.app.list_tasks()[0]["status"], "done")

    def test_reject_unapproved(self):
        tid = self.app.add("research", "mock", "Test task")
        with self.assertRaises(ValueError):
            self.app.approve(tid)

    def test_muse_requires_workspace(self):
        with self.assertRaises(ValueError):
            self.app.add("builder", "muse", "Modify source")

if __name__ == "__main__":
    unittest.main()
