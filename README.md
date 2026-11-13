# Downloader

A small web application for downloading publicly accessible videos through a browser. The Python backend uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) and FFmpeg. It verifies media output and converts incompatible streams to broadly compatible H.264/AAC MP4 when needed. The frontend is embedded in the Python source file.

> **Use responsibly:** Only download media that you own, have permission to download, or are otherwise legally allowed to save. Respect each platform's terms, copyright, privacy, and local law. Drift does not support bypassing DRM, private accounts, or access controls.

## Requirements

- Python 3.10 or newer
- FFmpeg available on your system PATH (required to merge or convert some formats)
- Packages listed in `requirements.txt`

## Run on Windows

Open PowerShell in this repository folder:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
$env:DRIFT_HOST = "127.0.0.1"
$env:DRIFT_PORT = "5000"
python drift.py
```

Open http://127.0.0.1:5000 in your browser. Press Ctrl+C in the terminal to stop the server.

If PowerShell blocks activation, use Command Prompt and run `.venv\Scripts\activate.bat`, or invoke the virtual-environment interpreter directly: `.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.venv\Scripts\python.exe "drift (1).py"`.

## Run with Docker

Build the image from the repository root:

```bash
docker build -t saim-downloader .
```

Run it with persistent storage:

```bash
docker run --rm -p 5000:5000 -v downloader-data:/data saim-downloader
```

Then open http://localhost:5000. The container installs FFmpeg, runs as a non-root user, and stores its database and temporary downloads under `/data`.

## Configuration

| Variable | Default | Purpose |
|---|---:|---|
| `DRIFT_HOST` | `127.0.0.1` unless `PORT` is set | Bind address |
| `DRIFT_PORT` / `PORT` | `5000` | HTTP port |
| `DRIFT_MAX_DOWNLOAD_MB` | `500` | Maximum download size in MB |
| `DRIFT_MAX_ACTIVE_JOBS` | `2` | Worker count |
| `DRIFT_JOB_TTL_SECONDS` | `1800` | Retention time for finished jobs |
| `DRIFT_DOWNLOAD_ROOT` | System temporary directory | Download and database directory |
| `DRIFT_DB_PATH` | `<download root>/drift.sqlite3` | SQLite database path |
| `DRIFT_ALLOWED_ORIGIN` | `*` | CORS origin for a separately hosted frontend |

For local use, keep the server bound to `127.0.0.1`. The current application has no user login or API-key authentication. Do not expose it directly to the public internet without placing it behind an authenticated access layer, adding appropriate abuse controls, and reviewing your hosting provider's security settings. The built-in rate limiter is process-local and is not a substitute for authentication.

## Health check

The backend exposes:

```text
GET /api/health
```

It reports whether the downloader dependency and FFmpeg are available, plus the active job count.

## Tests

```bash
python -m unittest discover -s tests -v
```

These tests cover input validation and utility functions. They do not download real media from third-party websites; platform availability can change and requires a separate manual integration test.

## Project files

- `drift.py` — HTTP server, embedded HTML/CSS/JavaScript, job queue, SQLite storage, validation, and download handling.
- `requirements.txt` — Python dependencies.
- `Dockerfile` — container build and runtime configuration.
- `tests/` — automated unit tests.

## License

No license file is currently included. Unless a license is added by the project owner, others should not assume they have permission to reuse or redistribute this code.
