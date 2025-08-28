
# `app.py` — Developer Documentation

## Purpose
Application factory and entry-point for the Flask app. Initializes configuration, environment, logging, DB schema, thread pool, and registers all blueprints. Provides the homepage route (`/`).

---

## Initialization Flow (`create_app()`)
1. **Environment**: `load_dotenv()` loads variables from `.env` into `os.environ`.
2. **Flask app**: 
   ```python
   app = Flask(__name__, static_folder="static", static_url_path="/static")
   ```
   - Static assets are served under **`/static/<path:filename>`**, mapped to the project’s `./static` directory.
3. **Config knobs (with defaults)**:
   - `SEND_FILE_MAX_AGE_DEFAULT` ← `STATIC_MAX_AGE` (default **604800** seconds = 7 days)
   - `ASSETS_VERSION` ← `ASSETS_VERSION` (default empty) — useful for cache busting in templates
   - `SECRET_KEY` / `app.secret_key` ← `FLASK_SECRET_KEY` (default **"dev-secret"**)
   - `MAX_CONTENT_LENGTH` ← (default **500 MiB**). Hard cap for incoming request bodies (uploads).
   - `PER_FILE_MAX_BYTES` ← (default **10 MiB**). Per-file validation used by uploads blueprint.
   - `MAX_FILES_PER_UPLOAD` ← (default **50**). Upload count guard.
   - `WORKERS` ← (default **4**). Used for background job queue (ThreadPoolExecutor).
   - `UPLOADED_RESULTS_PAGE_SIZE` ← (default **50**). Pagination size.
   - `SCREENINGS_PAGE_SIZE` ← (default **50**). Pagination size.
4. **Thread pool**: `app.config["EXECUTOR"] = ThreadPoolExecutor(max_workers=WORKERS)`
5. **Environment & DB setup**:
   - `setup_environment()` (from `main.py`) — creates required folders/paths.
   - `Base.metadata.create_all(engine)` (from `models`) — ensures schema exists.
6. **HTTP access logging**:
   - Log directory: `./logs/` (created if missing).
   - Files (overridable via env):
     - Success log: `HTTP_SUCCESS_LOG` (default `logs/http_success.log`)
     - Error log: `HTTP_ERROR_LOG` (default `logs/http_error.log`)
   - Rotation: `maxBytes=2 MiB`, `backupCount=5` for both files.
   - Format: `%(asctime)s [%(levelname)s] %(message)s`
   - Per-request logging:
     - `@app.before_request` captures `start_time`.
     - `@app.after_request` logs: client IP (prefers `X-Forwarded-For`), method+URL, status, user agent, and duration in ms.
     - `<400` → success logger; `>=400` → error logger.
7. **Blueprint registration** (import-and-register pattern; URL prefixes come from each blueprint’s `__init__.py`):
   - `uploads` (no explicit prefix in package — routes define `/upload`, `/upload_files`)
   - `jobs` (no explicit prefix in package — routes define `/jobs/...`, `/healthz`)
   - `uploaded_results` (no explicit prefix — defines `/uploaded_results`)
   - `screenings` (prefix `/screenings`)
   - `reports` (prefix `/reports` — serves PDFs)
   - `media` (prefix `/media` — serves images)
8. **Homepage**: 
   ```python
   @app.route("/")
   def homepage():
       return render_template("home.html")
   ```

For local dev execution, the bottom guard runs `app.run(debug=True, host="127.0.0.1", port=5000)`. For production, use a WSGI server (e.g., gunicorn/uwsgi) behind a reverse proxy that sets `X-Forwarded-For`.

---

## Static & Templates
- **Static**: `static_folder="static"` with `static_url_path="/static"` → URL: `/static/<path:filename>`.
- **Templates**: standard Flask default (`templates/`), referenced e.g., `render_template("home.html")`.

---

## Runtime Environment Variables (consumed in `app.py`)
| Variable | Purpose | Default |
|---|---|---|
| `STATIC_MAX_AGE` | Cache max age (seconds) for static files (`SEND_FILE_MAX_AGE_DEFAULT`) | `604800` |
| `ASSETS_VERSION` | Cache-busting suffix you can append in templates | `""` |
| `FLASK_SECRET_KEY` | Flask secret key | `"dev-secret"` |
| `MAX_CONTENT_LENGTH` | Max request size (bytes) | `524288000` (500 MiB) |
| `PER_FILE_MAX_BYTES` | Max per-file size (bytes) for uploads | `10485760` (10 MiB) |
| `MAX_FILES_PER_UPLOAD` | Max number of files per POST | `50` |
| `WORKERS` | Thread pool workers (background jobs) | `4` |
| `UPLOADED_RESULTS_PAGE_SIZE` | Pagination: uploaded results | `50` |
| `SCREENINGS_PAGE_SIZE` | Pagination: screenings | `50` |
| `HTTP_SUCCESS_LOG` | Path to success log file | `logs/http_success.log` |
| `HTTP_ERROR_LOG` | Path to error log file | `logs/http_error.log` |

> Note: Additional env-configurable paths/dirs are likely defined in other modules (`models.py`, `process_pdfs.py`). See “Images & PDFs” below.

---

## Images & PDFs (served by blueprints)
- **Images** — `media` blueprint  
  - URL pattern: `/media/img/<path:filename>`  
  - Implementation uses `send_from_directory` and a safe join against **`IMAGE_DIR`** imported from `models`.  
  - Allowed extensions: `.png .jpg .jpeg .gif .bmp .webp`.  
- **PDFs** — `reports` blueprint  
  - Diabetic Retinopathy PDFs: `/reports/dr/<path:filename>` → sent inline as `application/pdf`  
  - Glaucoma PDFs: `/reports/glaucoma/<path:filename>` → sent inline  
  - Base directories imported from **`process_pdfs`: `DR_PDF_DIR`, `GLAUCOMA_PDF_DIR`** (these are `Path` objects; typically wired via `.env`).

> Exact filesystem roots for `IMAGE_DIR`, `DR_PDF_DIR`, and `GLAUCOMA_PDF_DIR` come from their respective modules.


---

## Route Inventory (as per current code)
| Endpoint (blueprint.view) | Method | Path |
|---|---|---|
| `homepage` | GET | `/` |
| `jobs.healthz` | GET | `/healthz` |
| `jobs.job_status_json` | GET | `/jobs/<job_token>` |
| `jobs.job_status_page` | GET | `/jobs/<job_token>/view` |
| `jobs.list_recent_jobs` | GET | `/jobs` |
| `media.serve_image` | GET | `/media/img/<path:filename>` |
| `reports.serve_dr_pdf` | GET | `/reports/dr/<path:filename>` |
| `reports.serve_glaucoma_pdf` | GET | `/reports/glaucoma/<path:filename>` |
| `screenings.list_screenings` | GET | `/screenings/` |
| `screenings.screening_detail` | GET | `/screenings/<int:encounter_id>` |
| `static` | GET | `/static/<path:filename>` |
| `uploaded_results.list_uploaded_results` | GET | `/uploaded_results` |
| `uploads.upload_files` | POST | `/upload` |
| `uploads.upload_form` | GET | `/upload_files` |

> The `jobs.job_status_page`, `screenings.screening_detail`, and other view/page endpoints render templates (`render_template(...)`) located under `templates/`.

---

## Logging Details
- **Success log** vs **Error log** split (<400 vs ≥400) using dedicated loggers.
- Client IP prioritizes `X-Forwarded-For` (first value) then `request.remote_addr`.
- Log line example:  
  `203.0.113.10 "GET https://example.com/screenings?page=2" 200 UA="Mozilla/5.0 ..." duration=123ms`

---

## Operational Notes
- For production, deploy with a WSGI server and reverse proxy; keep `ASSETS_VERSION` updated during releases for cache-busting.
- Ensure `logs/` is writable by the app process.
- Thread pool lives in `app.config["EXECUTOR"]`; if you add long-running tasks, consider lifecycle/shutdown handling on app teardown.
- `.env` should define the secret key and any directory paths used by `models` and `process_pdfs` (e.g., image & PDF roots).

---

## Minimal `.env.example`
```ini
# Flask basics
FLASK_SECRET_KEY=change-me
ASSETS_VERSION=

# Upload & pagination limits
MAX_CONTENT_LENGTH=524288000
PER_FILE_MAX_BYTES=10485760
MAX_FILES_PER_UPLOAD=50
UPLOADED_RESULTS_PAGE_SIZE=50
SCREENINGS_PAGE_SIZE=50

# Worker pool
WORKERS=4

# Caching
STATIC_MAX_AGE=604800

# Logs (optional overrides)
HTTP_SUCCESS_LOG=logs/http_success.log
HTTP_ERROR_LOG=logs/http_error.log

# (Elsewhere) Media roots for blueprints (define in modules or here, if wired there)
# IMAGE_DIR=./files/images
# DR_PDF_DIR=./files/pdfs/dr
# GLAUCOMA_PDF_DIR=./files/pdfs/glaucoma
```

---

## Related Modules & Responsibilities (quick map)
- `uploads/` — upload form + POST handler, file validation, job queueing.
- `jobs/` — job status JSON + HTML page, `/healthz`, recent jobs feed.
- `uploaded_results/` — paginated listing of processed items.
- `screenings/` — paginated screening list + detail page.
- `media/` — image serving (safe filenames, allowed ext).
- `reports/` — inline PDF serving for DR & Glaucoma reports.
- `models` — SQLAlchemy engine/session/models; constants like `IMAGE_DIR`.
- `main` — `setup_environment()` to ensure required directories exist.

---

*Generated for quick handoff to another developer. Keep this alongside the repo root so paths are accurate.*
