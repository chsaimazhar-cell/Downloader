"""Unit tests for downloader validation and helper functions."""

import importlib.util
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TEST_ROOT = Path(tempfile.mkdtemp(prefix="downloader-tests-"))
os.environ["DRIFT_DOWNLOAD_ROOT"] = str(TEST_ROOT)
os.environ["DRIFT_DB_PATH"] = str(TEST_ROOT / "test.sqlite3")

SOURCE = Path(__file__).resolve().parents[1] / "drift (1).py"
SPEC = importlib.util.spec_from_file_location("downloader_app_under_test", SOURCE)
downloader = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(downloader)


def public_dns_result():
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


class DownloaderHelperTests(unittest.TestCase):
    def test_rejects_empty_non_http_and_unsupported_urls(self):
        self.assertFalse(downloader.validate_public_url("")[0])
        self.assertFalse(downloader.validate_public_url("ftp://youtube.com/video")[0])
        self.assertFalse(downloader.validate_public_url("https://example.org/video")[0])

    def test_rejects_private_ip_and_localhost(self):
        self.assertFalse(downloader.validate_public_url("http://127.0.0.1/")[0])
        self.assertFalse(downloader.validate_public_url("http://localhost/")[0])

    def test_rejects_url_credentials(self):
        self.assertFalse(downloader.validate_public_url("https://user:pass@youtube.com/watch?v=x")[0])

    def test_rejects_private_dns_results(self):
        private_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443))]
        with patch.object(downloader.socket, "getaddrinfo", return_value=private_dns):
            valid, _ = downloader.validate_public_url("https://www.youtube.com/watch?v=x")
        self.assertFalse(valid)

    def test_accepts_supported_host_with_public_dns(self):
        with patch.object(downloader.socket, "getaddrinfo", return_value=public_dns_result()):
            valid, parsed = downloader.validate_public_url("https://www.youtube.com/watch?v=x")
        self.assertTrue(valid)
        self.assertEqual(parsed.hostname, "www.youtube.com")

    def test_quality_normalization(self):
        self.assertEqual(downloader.normalize_quality("720P"), "720p")
        self.assertEqual(downloader.normalize_quality("9999p"), "best")

    def test_format_selector_respects_height_limit(self):
        self.assertIn("height<=720", downloader.format_selector("720p"))
        self.assertIn("bestvideo", downloader.format_selector("best"))

    def test_safe_filename_removes_unsafe_path_characters(self):
        result = downloader.safe_filename("../unsafe:name?.mp4")
        self.assertNotIn("/", result)
        self.assertNotIn(":", result)
        self.assertTrue(result.endswith(".mp4"))


if __name__ == "__main__":
    unittest.main()
