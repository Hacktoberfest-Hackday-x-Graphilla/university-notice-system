"""Tests for the web endpoints (app.py) - especially the admin gate.

Uses Flask's built-in test client, so no real server and no API calls.
"""

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as appmod
import rag

SAMPLE_PDF = Path(__file__).resolve().parents[1] / "examples" / "sample-notice.pdf"


class AdminGateTests(unittest.TestCase):
    def setUp(self):
        os.environ["ADMIN_PASSWORD"] = "test-pass"
        appmod.app.config["TESTING"] = True
        self.client = appmod.app.test_client()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_uploads, self.old_index = rag.UPLOADS_DIR, rag.INDEX_FILE
        rag.UPLOADS_DIR = Path(self.tmp.name) / "uploads"
        rag.INDEX_FILE = Path(self.tmp.name) / "index.json"

    def tearDown(self):
        rag.UPLOADS_DIR, rag.INDEX_FILE = self.old_uploads, self.old_index
        os.environ.pop("ADMIN_PASSWORD", None)

    def _upload_data(self):
        return {
            "file": (io.BytesIO(SAMPLE_PDF.read_bytes()), "sample-notice.pdf"),
        }

    def test_index_page_is_open(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        response.close()  # close the streamed file so no ResourceWarning

    def test_ask_is_open_without_admin(self):
        response = self.client.post("/api/ask", json={"message": "hi"})
        self.assertEqual(response.status_code, 200)

    def test_upload_without_password_is_rejected(self):
        response = self.client.post("/api/upload", data=self._upload_data())
        self.assertEqual(response.status_code, 401)

    def test_upload_with_wrong_password_is_rejected(self):
        response = self.client.post(
            "/api/upload",
            data=self._upload_data(),
            headers={"X-Admin-Password": "wrong"},
        )
        self.assertEqual(response.status_code, 401)

    def test_upload_with_correct_password_works(self):
        response = self.client.post(
            "/api/upload",
            data=self._upload_data(),
            headers={"X-Admin-Password": "test-pass"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.assertIn("sample-notice.pdf", response.get_json()["files"])

    def test_reset_without_password_is_rejected(self):
        response = self.client.post("/api/reset")
        self.assertEqual(response.status_code, 401)

    def test_reset_with_correct_password_works(self):
        response = self.client.post(
            "/api/reset", headers={"X-Admin-Password": "test-pass"}
        )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()