**VoiceSignBridge Local Setup & Audio Requirements**

- **Project:** VoiceSignBridge (speech → ISL gloss → video)
- **Location:** `VoiceSignBridge/`

**Quick Start (Windows, local dev)**
- Create a `.env` from the provided template:

```
copy .env.example .env
```

- Fill in `DATABASE_URL` or leave blank to use the local SQLite fallback. Set `SESSION_SECRET`.

- Install Python dependencies in the workspace virtual environment (already configured):

```powershell
D:/ISL_app/.venv/Scripts/python.exe -m pip install -r requirements.txt
# or if you prefer direct install
D:/ISL_app/.venv/Scripts/python.exe -m pip install flask flask-sqlalchemy sqlalchemy speechrecognition psycopg2-binary python-dotenv
```

- Start the dev server (example uses the workspace virtualenv created in this repo):

```powershell
D:/ISL_app/.venv/Scripts/python.exe d:\ISL_app\VoiceSignBridge\app.py
```

**ffmpeg and audio formats (important)**
- The browser often sends audio in WebM/OGG (Opus/Vorbis) format. `speech_recognition` requires PCM WAV, AIFF, or FLAC to read audio directly.
- To handle browser audio, the server converts uploaded audio to a 16 kHz mono WAV using `ffmpeg`.
- If `ffmpeg` is not installed or conversion fails, the server will return a clear error asking you to install `ffmpeg` or upload a supported format.

Supported formats the server can process (after conversion):
- WAV (PCM) (preferred)
- FLAC
- AIFF

If browser uploads WebM/OGG, `ffmpeg` is required to transcode to WAV.

Install `ffmpeg` on Windows
- With Chocolatey:

```powershell
choco install ffmpeg -y
```

- With Scoop:

```powershell
scoop install ffmpeg
```

- Or download a static build from https://ffmpeg.org/download.html, extract, and add the `bin` directory to your PATH.

Verify installation in PowerShell:

```powershell
ffmpeg -version
```

**Database**
- By default, if `DATABASE_URL` is not set, the app uses a local SQLite file: `VoiceSignBridge/voice_sign_bridge.db`.
- To connect to PostgreSQL, set `DATABASE_URL` in your `.env`, for example:

```
DATABASE_URL=postgresql+psycopg2://username:password@db-host:5432/dbname
```

**Other notes**
- A `.env.example` is provided. Do not commit your real `.env` to version control.
- The app serves static assets from `static/`. If you see `favicon.ico` 404s this is non-critical.

**If you run into audio errors**
- Error: "Audio file could not be read as PCM WAV, AIFF/AIFF-C, or Native FLAC" means the server couldn't read the upload. Install `ffmpeg` and retry, or configure the client to upload WAV/FLAC/AIFF.
- If conversion fails, check server logs the code now returns ffmpeg stderr to help debugging.



