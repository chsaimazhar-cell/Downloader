"""Unit tests for downloader validation and helper functions."""

import importlib.util
import os
import socket
import subprocess
import json
import threading
import uuid
from urllib.request import urlopen
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TEST_ROOT = Path(tempfile.mkdtemp(prefix="downloader-tests-"))
os.environ["DRIFT_DOWNLOAD_ROOT"] = str(TEST_ROOT)
os.environ["DRIFT_DB_PATH"] = str(TEST_ROOT / "test.sqlite3")

SOURCE = Path(__file__).resolve().parents[1] / "drift.py"
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


    def test_http_server_health_and_frontend_smoke(self):
        downloader.init_db()
        server = downloader.ThreadingHTTPServer(("127.0.0.1", 0), downloader.Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base_url + "/api/health", timeout=5) as response:
                self.assertEqual(response.status, 200)
                health = json.loads(response.read().decode("utf-8"))
            self.assertEqual(health["status"], "ok")
            with urlopen(base_url + "/", timeout=5) as response:
                self.assertEqual(response.status, 200)
                page = response.read().decode("utf-8")
            self.assertIn("<title>", page)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    def test_non_mp4_media_is_converted_to_compatible_mp4(self):
        ffmpeg = downloader.find_ffmpeg()
        if not ffmpeg:
            self.skipTest("FFmpeg is not available in this test environment.")
        encoders = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        if "libx264" not in encoders:
            self.skipTest("This FFmpeg build does not include the libx264 encoder.")

        downloader.init_db()
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.avi"
            subprocess.run(
                [
                    ffmpeg, "-y", "-f", "lavfi", "-i",
                    "color=c=black:s=64x64:d=1", "-c:v", "mpeg4",
                    "-an", str(source),
                ],
                capture_output=True,
                check=True,
            )
            converted = downloader.ensure_compatible_mp4(source, "unit-conversion")
            self.assertTrue(converted.is_file())
            self.assertEqual(converted.suffix.lower(), ".mp4")
            media_info = downloader.probe_media(converted)
            self.assertEqual(media_info["video"][0]["codec"], "h264")
            self.assertEqual(media_info["video"][0]["pix_fmt"], "yuv420p")
            self.assertIn("mp4", media_info["container"].split(","))

    def test_download_file_streaming_and_http_range(self):
        downloader.init_db()
        with tempfile.TemporaryDirectory() as temp:
            media_path = Path(temp) / "sample.mp4"
            media_bytes = b"0123456789abcdef"
            media_path.write_bytes(media_bytes)
            job_id = uuid.uuid4().hex
            timestamp = downloader.now()
            downloader.insert_job({
                "id": job_id,
                "status": "ready",
                "phase": "Ready",
                "progress": 100,
                "downloaded_bytes": len(media_bytes),
                "total_bytes": len(media_bytes),
                "speed": None,
                "eta": None,
                "url": "https://www.youtube.com/watch?v=test",
                "quality": "best",
                "format": "MP4",
                "platform": "YouTube",
                "title": "Sample file",
                "thumbnail": None,
                "filename": "Sample_file.mp4",
                "file_size": len(media_bytes),
                "message": "Ready",
                "error": None,
                "created_at": timestamp,
                "updated_at": timestamp,
                "completed_at": timestamp,
                "job_dir": temp,
                "file_path": str(media_path),
                "duration": "0:01",
            })
            server = downloader.ThreadingHTTPServer(("127.0.0.1", 0), downloader.Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                with urlopen(base_url + f"/api/downloads/{job_id}/file", timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.read(), media_bytes)
                    self.assertEqual(response.headers.get("Accept-Ranges"), "bytes")

                request = __import__("urllib.request", fromlist=["Request"]).Request(
                    base_url + f"/api/downloads/{job_id}/file",
                    headers={"Range": "bytes=2-5"},
                )
                with urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 206)
                    self.assertEqual(response.read(), b"2345")
                    self.assertEqual(response.headers.get("Content-Range"), "bytes 2-5/16")
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
