#!/usr/bin/env python3
"""Keep a local desktop copy of one project's data in sync with the server.

Standard library only (Python 3.9+), so it runs on a PI's desktop without
installing anything. It needs a sync credential ("pds_...") issued from the web
app's *Project data sync* page after email confirmation and administrator
approval.

Usage:
    python3 project_sync_client.py init   --server https://host --dest ./MYPROJ_mirror
    python3 project_sync_client.py sync   --dest ./MYPROJ_mirror [--interval 3600]
    python3 project_sync_client.py status --dest ./MYPROJ_mirror

Each ``sync`` walks the full encounter and direct-image lists, downloads only
images missing locally, refreshes a sidecar only when the server fingerprint
changed, and writes timestamped CSV snapshots. It never deletes local files.

Layout under --dest:
    data/encounters/<YYYY-MM>/<capture-date>_<encounter-uuid>/
        encounter.jsonl                 encounter record + every task and grade
        <image-uuid>.<ext>              original image
        <image-uuid>.edited.<ext>       edited image (when one exists)
        <image-uuid>.jsonl              image, tasks, every grader's grade +
                                        annotations, and a COCO record
    data/direct_images/<YYYY-MM>/<image-uuid>.<ext> (+ .jsonl)
    exports/<YYYYmmdd_HHMMSS>/encounters.csv, images.csv, gradings.csv, report.json
    .sync/config.json (0600), state.json, sync.lock, sync.log
"""
from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import json
import logging
import os
import shutil
import socket
import ssl
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

CLIENT_VERSION = "1.0"
USER_AGENT = f"fundus-project-sync-client/{CLIENT_VERSION}"
API_PREFIX = "/api/sync/v1"
MAX_RETRIES = 6
BUSY_WAIT_LIMIT = 6 * 3600
EXPORT_FILENAME_SAFE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
CHUNK = 1024 * 256
SIDECAR_BATCH = 50

log = logging.getLogger("project_sync_client")


# ---------------------------------------------------------------------------
# Local files
# ---------------------------------------------------------------------------


class Paths:
    def __init__(self, dest: Path):
        self.dest = dest
        self.meta = dest / ".sync"
        self.config = self.meta / "config.json"
        self.state = self.meta / "state.json"
        self.lock = self.meta / "sync.lock"
        self.log = self.meta / "sync.log"
        self.data = dest / "data"
        self.exports = dest / "exports"


def _atomic_write_text(path: Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _write_jsonl(path: Path, records: list[dict]) -> None:
    _atomic_write_text(path, "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records))


def _read_jsonl(path: Path) -> list[dict]:
    try:
        with path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    except (OSError, ValueError):
        return []


def load_config(paths: Paths) -> dict:
    if not paths.config.exists():
        sys.exit(f"No config at {paths.config}. Run 'init' first.")
    if os.name == "posix" and paths.config.stat().st_mode & 0o077:
        log.warning("%s is readable by other users; run: chmod 600 %s", paths.config, paths.config)
    config = json.loads(paths.config.read_text(encoding="utf-8"))
    env_credential = os.environ.get("PROJECT_SYNC_CREDENTIAL")
    if env_credential:
        config["credential"] = env_credential.strip()
    if not config.get("credential"):
        sys.exit("No credential configured (config.json or PROJECT_SYNC_CREDENTIAL).")
    return config


def load_state(paths: Paths) -> dict:
    try:
        state = json.loads(paths.state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    state.setdefault("encounters", {})
    state.setdefault("images", {})
    return state


def save_state(paths: Paths, state: dict) -> None:
    _atomic_write_text(paths.state, json.dumps(state, indent=1, sort_keys=True))


class RunLock:
    """Refuse to run two syncs into the same folder at once."""

    def __init__(self, path: Path):
        self.path = path
        self.fd = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            age = time.time() - self.path.stat().st_mtime
            if age < 12 * 3600:
                sys.exit(f"Another sync appears to be running ({self.path}). Delete it if that is not true.")
            log.warning("Removing stale lock %s", self.path)
            self.path.unlink()
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(self.fd, str(os.getpid()).encode())
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
        try:
            self.path.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirects are followed manually so the credential never leaves our server."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, server: str, credential: str, *, ca_file: str | None = None, timeout: int = 120):
        self.server = server.rstrip("/")
        self.credential = credential
        self.timeout = timeout
        self.min_interval = 0.25
        self._pace_lock = threading.Lock()
        self._next_slot = 0.0
        context = ssl.create_default_context(cafile=ca_file) if ca_file else ssl.create_default_context()
        self._opener = urllib.request.build_opener(_NoRedirect(), urllib.request.HTTPSHandler(context=context))
        self._plain_opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))

    def _request(self, method: str, path: str, *, params=None, body=None):
        url = self.server + API_PREFIX + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Authorization": f"Bearer {self.credential}", "User-Agent": USER_AGENT, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        return urllib.request.Request(url, data=data, headers=headers, method=method)

    def _pace(self) -> None:
        """Leave the server-advertised gap between our requests (all threads)."""
        with self._pace_lock:
            now = time.monotonic()
            wait = self._next_slot - now
            self._next_slot = max(now, self._next_slot) + self.min_interval
        if wait > 0:
            time.sleep(wait)

    def _open(self, request, *, opener=None):
        """Open with retry on 429/5xx/network errors. Returns the response.

        ``429`` means the server's sync queue is full (graders come first), so
        the client waits its turn for up to BUSY_WAIT_LIMIT seconds.
        """
        opener = opener or self._opener
        delay = 2.0
        attempt = 0
        busy_waited = 0.0
        while True:
            attempt += 1
            if opener is self._opener:
                self._pace()
            try:
                return opener.open(request, timeout=self.timeout)
            except urllib.error.HTTPError as exc:
                if exc.code in (301, 302, 303, 307, 308):
                    return exc  # handled by caller
                if exc.code == 429:
                    wait = min(max(_retry_after(exc) or 5.0, 1.0), 300.0)
                    if busy_waited + wait > BUSY_WAIT_LIMIT:
                        raise _api_error(exc) from None
                    log.debug("Server busy, waiting %.0fs", wait)
                    time.sleep(wait)
                    busy_waited += wait
                    continue
                if exc.code >= 500:
                    wait = _retry_after(exc) or delay
                    if attempt >= MAX_RETRIES:
                        raise _api_error(exc) from None
                    log.info("HTTP %s, retrying in %.0fs", exc.code, wait)
                    time.sleep(wait)
                    delay = min(delay * 2, 120)
                    continue
                raise _api_error(exc) from None
            except (urllib.error.URLError, socket.timeout, ConnectionError) as exc:
                if attempt >= MAX_RETRIES:
                    raise
                log.info("Network error (%s), retrying in %.0fs", exc, delay)
                time.sleep(delay)
                delay = min(delay * 2, 120)

    def get_json(self, path: str, **params) -> dict:
        with self._open(self._request("GET", path, params=params)) as response:
            return json.loads(response.read().decode("utf-8"))

    def post_json(self, path: str, body: dict) -> dict:
        with self._open(self._request("POST", path, body=body)) as response:
            return json.loads(response.read().decode("utf-8"))

    def download(self, media_uuid: str, variant: str, target: Path) -> tuple[int, str]:
        """Stream one object to ``target`` atomically. Returns (bytes, md5)."""
        response = self._open(self._request("GET", f"/media/{urllib.parse.quote(media_uuid)}", params={"variant": variant}))
        if getattr(response, "code", 200) in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ApiError(502, "bad_redirect", "Redirect without Location")
            # Storage redirect (presigned URL): no Authorization header.
            response = self._open(
                urllib.request.Request(location, headers={"User-Agent": USER_AGENT}), opener=self._plain_opener
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        expected = response.headers.get("Content-Length")
        digest = hashlib.md5()  # noqa: S324 - integrity comparison with server md5, not security
        size = 0
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".part-")
        try:
            with os.fdopen(fd, "wb") as handle, response:
                while True:
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    handle.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            if expected is not None and int(expected) != size:
                raise ApiError(0, "truncated", f"expected {expected} bytes, got {size}")
            if size == 0:
                raise ApiError(0, "empty", "empty file")
            os.replace(tmp, target)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        return size, digest.hexdigest()


    def download_export(self, token: str, filename: str, target: Path) -> None:
        path = f"/exports/{urllib.parse.quote(token)}/{urllib.parse.quote(filename)}"
        response = self._open(self._request("GET", path))
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".part-")
        try:
            with os.fdopen(fd, "wb") as handle, response:
                shutil.copyfileobj(response, handle, CHUNK)
            os.replace(tmp, target)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise


def _retry_after(exc) -> float | None:
    value = exc.headers.get("Retry-After") if exc.headers else None
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _api_error(exc: urllib.error.HTTPError) -> ApiError:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
        return ApiError(exc.code, payload.get("error", "error"), payload.get("message", ""))
    except Exception:  # noqa: BLE001
        return ApiError(exc.code, "http_error", exc.reason or "")


def check_server_url(server: str, allow_http: bool) -> str:
    parsed = urllib.parse.urlparse(server)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        sys.exit("--server must look like https://host")
    if parsed.scheme == "http" and not allow_http and parsed.hostname not in ("localhost", "127.0.0.1"):
        sys.exit("Refusing plain http (credential and patient data would travel unencrypted). Use https.")
    return f"{parsed.scheme}://{parsed.netloc}"


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def _safe(value: str) -> str:
    return "".join(c for c in str(value) if c.isalnum() or c in "-_") or "x"


def encounter_folder(paths: Paths, encounter: dict) -> Path:
    capture = (encounter.get("capture_date") or "")[:10]
    month = capture[:7] if len(capture) >= 7 else "undated"
    prefix = capture if capture else "undated"
    return paths.data / "encounters" / _safe(month) / f"{_safe(prefix)}_{_safe(encounter['uuid'])}"


def direct_folder(paths: Paths, image: dict) -> Path:
    created = (image.get("created_at") or "")[:7]
    return paths.data / "direct_images" / (_safe(created) if created else "undated")


def image_files(folder: Path, image: dict) -> tuple[Path, Path | None, Path]:
    ext = _safe(image.get("ext") or "bin")
    uid = _safe(image["uuid"])
    edited = folder / f"{uid}.edited.{ext}" if image.get("has_edited") else None
    return folder / f"{uid}.{ext}", edited, folder / f"{uid}.jsonl"


def _relocate(old: str | None, new: Path, dest: Path) -> None:
    """Move previously downloaded files when an encounter's folder changes."""
    if not old:
        return
    old_path = dest / old
    if old_path.exists() and old_path != new and not new.exists():
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_path), str(new))


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


class SyncRun:
    def __init__(self, paths: Paths, client: Client, *, workers: int, include_edited: bool, export_wait: int):
        self.paths = paths
        self.client = client
        self.workers = max(1, min(workers, 8))
        self.include_edited = include_edited
        self.export_wait = export_wait
        self.state = load_state(paths)
        self.lock = threading.Lock()
        self.stats = {"encounters": 0, "images": 0, "downloaded": 0, "bytes": 0, "sidecars": 0,
                      "failed": 0, "md5_mismatch": 0, "missing_on_server": 0}
        self.errors: list[str] = []

    # -- walking ------------------------------------------------------------

    def walk(self, path: str, limit: int):
        after = 0
        while True:
            page = self.client.get_json(path, after_id=after, limit=limit)
            for item in page.get("items", []):
                yield item
            after = page.get("next_after_id")
            if not after:
                return

    def run(self) -> dict:
        started = datetime.now(timezone.utc)
        info = self.client.get_json("/whoami")
        limits = info.get("page_limits", {})
        policy = info.get("client_policy", {})
        self.workers = max(1, min(self.workers, int(policy.get("max_concurrency", 1))))
        self.client.min_interval = max(0.0, float(policy.get("min_interval_ms", 250)) / 1000.0)
        export_requested = self._request_export()
        labs = {lab["id"]: lab["name"] for lab in info.get("lab_units", [])}
        log.info("Project %s as %s; %d lab unit(s); grant expires %s",
                 info["project"]["code"], info["user"]["username"], len(labs), info.get("expires_at"))

        downloads: list[tuple] = []
        encounter_sidecars: list[tuple[str, Path]] = []
        image_sidecars: list[tuple[str, Path, str]] = []
        encounter_rows: list[dict] = []
        image_rows: list[dict] = []

        for encounter in self.walk("/encounters", limits.get("encounters", 200)):
            self.stats["encounters"] += 1
            folder = encounter_folder(self.paths, encounter)
            rel_folder = folder.relative_to(self.paths.dest).as_posix()
            known = self.state["encounters"].get(encounter["uuid"], {})
            if known.get("folder") and known["folder"] != rel_folder:
                _relocate(known["folder"], folder, self.paths.dest)
            folder.mkdir(parents=True, exist_ok=True)
            sidecar = folder / "encounter.jsonl"
            if known.get("fingerprint") != encounter.get("sidecar_fingerprint") or not sidecar.exists():
                encounter_sidecars.append((encounter["uuid"], sidecar))
            self.state["encounters"][encounter["uuid"]] = {
                "folder": rel_folder, "fingerprint": known.get("fingerprint"),
                "pending_fingerprint": encounter.get("sidecar_fingerprint"),
            }
            encounter_rows.append({
                "encounter_uuid": encounter["uuid"],
                "lab_unit_id": encounter.get("lab_unit_id"),
                "lab_unit": labs.get(encounter.get("lab_unit_id"), ""),
                "capture_date": encounter.get("capture_date"),
                "disease": encounter.get("disease"),
                "is_set_based": encounter.get("is_set_based"),
                "referral_suggestion": encounter.get("referral_suggestion"),
                "encounter_verified_status": encounter.get("encounter_verified_status"),
                "dr_verified_status": encounter.get("dr_verified_status"),
                "glaucoma_verified_status": encounter.get("glaucoma_verified_status"),
                "patient_id": encounter.get("patient_id") or "",
                "patient_name": encounter.get("patient_name") or "",
                "image_count": len(encounter.get("images", [])),
                "local_folder": rel_folder,
            })
            for image in encounter.get("images", []):
                self._plan_image(image, folder, encounter["uuid"], downloads, image_sidecars, image_rows)

        for image in self.walk("/direct-images", limits.get("direct_images", 500)):
            self._plan_image(image, direct_folder(self.paths, image), None, downloads, image_sidecars, image_rows)

        log.info("%d encounters, %d images; %d files to download, %d encounter + %d image sidecars to refresh",
                 self.stats["encounters"], self.stats["images"], len(downloads),
                 len(encounter_sidecars), len(image_sidecars))
        save_state(self.paths, self.state)

        self._download_all(downloads)
        self._refresh_sidecars(encounter_sidecars, image_sidecars)
        save_state(self.paths, self.state)

        for row in image_rows:
            entry = self.state["images"].get(row["image_uuid"], {})
            row["downloaded"] = bool(entry.get("path")) and (self.paths.dest / entry["path"]).exists()
            row["bytes"] = entry.get("bytes", "")
            row["md5_match"] = entry.get("md5_match", "")
        export_dir = self._write_exports(started, info, encounter_rows, image_rows)
        self._fetch_workbook(export_dir, wait=self.export_wait if export_requested else 0)
        return {"export_dir": str(export_dir), **self.stats}

    # -- project workbook (queued server-side) -------------------------------

    def _request_export(self) -> bool:
        try:
            self.client.post_json("/exports", {})
            log.info("Project Excel workbook queued on the server")
            return True
        except ApiError as exc:
            if exc.status == 409:
                return True
            if exc.status == 429:
                log.info("Workbook export not re-queued (hourly limit); using the latest available")
                return False
            raise

    def _fetch_workbook(self, export_dir: Path, *, wait: int) -> None:
        deadline = time.monotonic() + wait
        while True:
            job = self.client.get_json("/exports/latest").get("export")
            if not job or job["status"] in ("done", "error") or time.monotonic() >= deadline:
                break
            time.sleep(15)
        if not job:
            return
        if job["status"] == "error":
            self.errors.append(f"workbook export failed: {job.get('error')}")
            return
        if job["status"] != "done":
            log.info("Workbook still %s on the server; it will be fetched on the next run", job["status"])
            return
        previous = self.state.get("last_workbook") or {}
        for name in job.get("files", []):
            if not name or set(name) - EXPORT_FILENAME_SAFE or name.startswith("."):
                continue
            target = export_dir / name
            old = self.paths.dest / previous.get("folder", "") / name if previous.get("folder") else None
            if previous.get("job_token") == job["job_token"] and old is not None and old.is_file():
                shutil.copy2(old, target)  # unchanged on the server; no re-download
            else:
                self.client.download_export(job["job_token"], name, target)
            log.info("Saved %s", target.relative_to(self.paths.dest))
        self.state["last_workbook"] = {
            "job_token": job["job_token"],
            "updated_at": job.get("updated_at"),
            "folder": export_dir.relative_to(self.paths.dest).as_posix(),
        }
        save_state(self.paths, self.state)

    # -- walking ------------------------------------------------------------

    def walk(self, path: str, limit: int):
        after = 0
        while True:
            page = self.client.get_json(path, after_id=after, limit=limit)
            for item in page.get("items", []):
                yield item
            after = page.get("next_after_id")
            if not after:
                return

    def run(self) -> dict:
        started = datetime.now(timezone.utc)
        info = self.client.get_json("/whoami")
        limits = info.get("page_limits", {})
        policy = info.get("client_policy", {})
        self.workers = max(1, min(self.workers, int(policy.get("max_concurrency", 1))))
        self.client.min_interval = max(0.0, float(policy.get("min_interval_ms", 250)) / 1000.0)
        export_requested = self._request_export()
        labs = {lab["id"]: lab["name"] for lab in info.get("lab_units", [])}
        log.info("Project %s as %s; %d lab unit(s); grant expires %s",
                 info["project"]["code"], info["user"]["username"], len(labs), info.get("expires_at"))

        downloads: list[tuple] = []
        encounter_sidecars: list[tuple[str, Path]] = []
        image_sidecars: list[tuple[str, Path, str]] = []
        encounter_rows: list[dict] = []
        image_rows: list[dict] = []

        for encounter in self.walk("/encounters", limits.get("encounters", 200)):
            self.stats["encounters"] += 1
            folder = encounter_folder(self.paths, encounter)
            rel_folder = folder.relative_to(self.paths.dest).as_posix()
            known = self.state["encounters"].get(encounter["uuid"], {})
            if known.get("folder") and known["folder"] != rel_folder:
                _relocate(known["folder"], folder, self.paths.dest)
            folder.mkdir(parents=True, exist_ok=True)
            sidecar = folder / "encounter.jsonl"
            if known.get("fingerprint") != encounter.get("sidecar_fingerprint") or not sidecar.exists():
                encounter_sidecars.append((encounter["uuid"], sidecar))
            self.state["encounters"][encounter["uuid"]] = {
                "folder": rel_folder, "fingerprint": known.get("fingerprint"),
                "pending_fingerprint": encounter.get("sidecar_fingerprint"),
            }
            encounter_rows.append({
                "encounter_uuid": encounter["uuid"],
                "lab_unit_id": encounter.get("lab_unit_id"),
                "lab_unit": labs.get(encounter.get("lab_unit_id"), ""),
                "capture_date": encounter.get("capture_date"),
                "disease": encounter.get("disease"),
                "is_set_based": encounter.get("is_set_based"),
                "referral_suggestion": encounter.get("referral_suggestion"),
                "encounter_verified_status": encounter.get("encounter_verified_status"),
                "dr_verified_status": encounter.get("dr_verified_status"),
                "glaucoma_verified_status": encounter.get("glaucoma_verified_status"),
                "patient_id": encounter.get("patient_id") or "",
                "patient_name": encounter.get("patient_name") or "",
                "image_count": len(encounter.get("images", [])),
                "local_folder": rel_folder,
            })
            for image in encounter.get("images", []):
                self._plan_image(image, folder, encounter["uuid"], downloads, image_sidecars, image_rows)

        for image in self.walk("/direct-images", limits.get("direct_images", 500)):
            self._plan_image(image, direct_folder(self.paths, image), None, downloads, image_sidecars, image_rows)

        log.info("%d encounters, %d images; %d files to download, %d encounter + %d image sidecars to refresh",
                 self.stats["encounters"], self.stats["images"], len(downloads),
                 len(encounter_sidecars), len(image_sidecars))
        save_state(self.paths, self.state)

        self._download_all(downloads)
        self._refresh_sidecars(encounter_sidecars, image_sidecars)
        save_state(self.paths, self.state)

        for row in image_rows:
            entry = self.state["images"].get(row["image_uuid"], {})
            row["downloaded"] = bool(entry.get("path")) and (self.paths.dest / entry["path"]).exists()
            row["bytes"] = entry.get("bytes", "")
            row["md5_match"] = entry.get("md5_match", "")
        export_dir = self._write_exports(started, info, encounter_rows, image_rows)
        self._fetch_workbook(export_dir, wait=self.export_wait if export_requested else 0)
        return {"export_dir": str(export_dir), **self.stats}

    # -- project workbook (queued server-side) -------------------------------

    def _request_export(self) -> bool:
        try:
            self.client.post_json("/exports", {})
            log.info("Project Excel workbook queued on the server")
            return True
        except ApiError as exc:
            if exc.status == 409:
                return True
            if exc.status == 429:
                log.info("Workbook export not re-queued (hourly limit); using the latest available")
                return False
            raise

    def _fetch_workbook(self, export_dir: Path, *, wait: int) -> None:
        deadline = time.monotonic() + wait
        while True:
            job = self.client.get_json("/exports/latest").get("export")
            if not job:
                return
            if job["status"] == "done" or time.monotonic() >= deadline or job["status"] == "error":
                break
            time.sleep(15)
        if job["status"] == "error":
            self.errors.append(f"workbook export failed: {job.get('error')}")
        if job["status"] != "done":
            if job["status"] != "error":
                log.info("Workbook still %s; it will be fetched on the next run", job["status"])
            job = self.state.get("last_workbook") and None or job
        if job and job["status"] == "done":
            for name in job.get("files", []):
                if not name or set(name) - EXPORT_FILENAME_SAFE or name.startswith("."):
                    continue
                self.client.download_export(job["job_token"], name, export_dir / name)
                log.info("Saved %s", (export_dir / name).relative_to(self.paths.dest))
            self.state["last_workbook"] = {"job_token": job["job_token"], "updated_at": job.get("updated_at")}
            save_state(self.paths, self.state)

    def _plan_image(self, image, folder: Path, encounter_uuid, downloads, sidecars, rows) -> None:
        self.stats["images"] += 1
        original, edited, sidecar = image_files(folder, image)
        entry = self.state["images"].get(image["uuid"], {})
        rel = lambda p: p.relative_to(self.paths.dest).as_posix()  # noqa: E731
        for old_key, new_path in (("path", original), ("edited_path", edited), ("sidecar", sidecar)):
            if new_path is not None and entry.get(old_key) and entry[old_key] != rel(new_path):
                _relocate(entry[old_key], new_path, self.paths.dest)
        if not original.exists():
            downloads.append((image, "original", original))
        if edited is not None and self.include_edited and not edited.exists():
            downloads.append((image, "edited", edited))
        if image.get("sidecar_fingerprint") and (
            entry.get("fingerprint") != image["sidecar_fingerprint"] or not sidecar.exists()
        ):
            sidecars.append((image["uuid"], sidecar, image["sidecar_fingerprint"]))
        entry.update({
            "path": rel(original),
            "edited_path": rel(edited) if edited is not None else None,
            "sidecar": rel(sidecar) if image.get("sidecar_fingerprint") else None,
            "source_md5": image.get("source_md5"),
        })
        self.state["images"][image["uuid"]] = entry
        rows.append({
            "image_uuid": image["uuid"],
            "encounter_uuid": encounter_uuid or "",
            "kind": image.get("kind"),
            "eye_side": image.get("eye_side") or "",
            "position": image.get("position") or "",
            "is_pii": image.get("is_pii"),
            "has_edited": image.get("has_edited"),
            "is_not_gradable": image.get("is_not_gradable", ""),
            "created_at": image.get("created_at") or "",
            "local_path": rel(original),
            "edited_local_path": rel(edited) if edited is not None else "",
            "sidecar_path": rel(sidecar) if image.get("sidecar_fingerprint") else "",
        })

    # -- downloads ----------------------------------------------------------

    def _download_one(self, image: dict, variant: str, target: Path) -> None:
        size, md5 = self.client.download(image["uuid"], variant, target)
        with self.lock:
            self.stats["downloaded"] += 1
            self.stats["bytes"] += size
            if variant == "original":
                entry = self.state["images"].setdefault(image["uuid"], {})
                entry["bytes"] = size
                if image.get("source_md5"):
                    entry["md5_match"] = md5 == image["source_md5"]
                    if not entry["md5_match"]:
                        self.stats["md5_mismatch"] += 1

    def _download_all(self, downloads: list[tuple]) -> None:
        if not downloads:
            return
        done = 0
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(self._download_one, *job): job for job in downloads}
            for future in as_completed(futures):
                image, variant, _ = futures[future]
                try:
                    future.result()
                except ApiError as exc:
                    self._fail(f"{image['uuid']} ({variant}): {exc}", missing=exc.status == 404)
                    if exc.status in (401, 403, 503):
                        pool.shutdown(wait=False, cancel_futures=True)
                        raise
                except Exception as exc:  # noqa: BLE001
                    self._fail(f"{image['uuid']} ({variant}): {exc}")
                done += 1
                if done % 100 == 0:
                    log.info("downloaded %d/%d", done, len(downloads))
                    save_state(self.paths, self.state)

    def _fail(self, message: str, *, missing: bool = False) -> None:
        with self.lock:
            self.stats["failed"] += 1
            if missing:
                self.stats["missing_on_server"] += 1
            self.errors.append(message)
        log.warning("failed: %s", message)

    # -- sidecars -----------------------------------------------------------

    def _refresh_sidecars(self, encounter_sidecars, image_sidecars) -> None:
        for start in range(0, len(encounter_sidecars), SIDECAR_BATCH):
            batch = encounter_sidecars[start:start + SIDECAR_BATCH]
            result = self.client.post_json("/sidecars", {"encounters": [u for u, _ in batch]})
            for uuid, path in batch:
                records = result.get("encounters", {}).get(uuid)
                if records is None:
                    self._fail(f"encounter sidecar {uuid} unavailable", missing=True)
                    continue
                _write_jsonl(path, records)
                entry = self.state["encounters"][uuid]
                entry["fingerprint"] = entry.pop("pending_fingerprint", None)
                self.stats["sidecars"] += 1
        for start in range(0, len(image_sidecars), SIDECAR_BATCH):
            batch = image_sidecars[start:start + SIDECAR_BATCH]
            result = self.client.post_json("/sidecars", {"images": [u for u, _, _ in batch]})
            for uuid, path, fingerprint in batch:
                records = result.get("images", {}).get(uuid)
                if records is None:
                    self._fail(f"image sidecar {uuid} unavailable", missing=True)
                    continue
                _write_jsonl(path, records)
                self.state["images"][uuid]["fingerprint"] = fingerprint
                self.stats["sidecars"] += 1
            if start and start % (SIDECAR_BATCH * 20) == 0:
                save_state(self.paths, self.state)

    # -- CSV exports ----------------------------------------------------------

    def _grading_rows(self) -> list[dict]:
        """Flatten every grade from local sidecars (all graders, AI included)."""
        annotation_counts: dict[int, int] = {}
        coco_counts: dict[int, int] = {}
        consensus: dict[str, dict] = {}
        grade_records: list[tuple[dict, str]] = []
        for entry in self.state["images"].values():
            if not entry.get("sidecar"):
                continue
            for record in _read_jsonl(self.paths.dest / entry["sidecar"]):
                if record.get("record_type") == "grade":
                    annotations = (record.get("annotation_set") or {}).get("instances") or []
                    annotation_counts[record["grade_id"]] = len(annotations)
                elif record.get("record_type") == "coco":
                    for ann in record.get("annotations", []):
                        coco_counts[ann.get("source_grade_id")] = coco_counts.get(ann.get("source_grade_id"), 0) + 1
        seen: set[int] = set()
        sources = [(self.paths.dest / e["folder"] / "encounter.jsonl") for e in self.state["encounters"].values()]
        sources += [self.paths.dest / e["sidecar"] for e in self.state["images"].values()
                    if e.get("sidecar") and "/direct_images/" in "/" + e["sidecar"]]
        for path in sources:
            records = _read_jsonl(path)
            encounter_uuid = next((r.get("uuid") for r in records if r.get("record_type") == "encounter"), "")
            for record in records:
                if record.get("record_type") == "task" and record.get("consensus"):
                    consensus[record["task_uuid"]] = record["consensus"]
            for record in records:
                if record.get("record_type") == "grade" and record["grade_id"] not in seen:
                    seen.add(record["grade_id"])
                    grade_records.append((record, encounter_uuid))
        rows = []
        for record, encounter_uuid in grade_records:
            final = consensus.get(record["task_uuid"]) or {}
            rows.append({
                "encounter_uuid": encounter_uuid,
                "image_uuid": record.get("image_uuid") or "",
                "task_uuid": record["task_uuid"],
                "disease": record.get("disease"),
                "grade_id": record["grade_id"],
                "role_slot": record.get("role_slot"),
                "grade": record.get("grade_name"),
                "grader_user_id": record.get("grader_user_id"),
                "grader_username": record.get("grader_username"),
                "started_at": record.get("started_at") or "",
                "graded_at": record.get("created_at"),
                "updated_at": record.get("updated_at"),
                "time_taken_seconds": record.get("time_taken_seconds") or "",
                "ai_model": record.get("ai_model_name") or "",
                "comment": record.get("comment") or "",
                "annotation_instances": annotation_counts.get(record["grade_id"], ""),
                "coco_annotations": coco_counts.get(record["grade_id"], ""),
                "consensus_grade": final.get("final_grade") or "",
                "consensus_method": final.get("method") or "",
                "consensus_decided_at": final.get("decided_at") or "",
            })
        return rows

    def _write_exports(self, started: datetime, info: dict, encounters, images) -> Path:
        stamp = started.strftime("%Y%m%d_%H%M%S")
        export_dir = self.paths.exports / stamp
        export_dir.mkdir(parents=True, exist_ok=True)
        for name, rows in (("encounters", encounters), ("images", images), ("gradings", self._grading_rows())):
            path = export_dir / f"{name}.csv"
            fields = list(rows[0].keys()) if rows else ["empty"]
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
        report = {
            "client_version": CLIENT_VERSION,
            "started_at": started.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "server": self.client.server,
            "project": info.get("project"),
            "user": info.get("user"),
            "grant_expires_at": info.get("expires_at"),
            "stats": self.stats,
            "errors": self.errors[:1000],
        }
        _atomic_write_text(export_dir / "report.json", json.dumps(report, indent=2))
        return export_dir


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_init(args) -> int:
    paths = Paths(Path(args.dest).expanduser().resolve())
    server = check_server_url(args.server, args.allow_http)
    credential = os.environ.get("PROJECT_SYNC_CREDENTIAL") or getpass.getpass("Sync credential (pds_...): ")
    credential = credential.strip()
    if not credential.startswith("pds_"):
        print("That does not look like a sync credential (expected pds_...).", file=sys.stderr)
        return 2
    client = Client(server, credential, ca_file=args.ca_file)
    info = client.get_json("/whoami")
    paths.meta.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(paths.meta, 0o700)
    config = {"server": server, "credential": credential, "project": info["project"], "ca_file": args.ca_file,
              "allow_http": bool(args.allow_http)}
    _atomic_write_text(paths.config, json.dumps(config, indent=2), mode=0o600)
    print(f"Configured {paths.dest} for project {info['project']['code']} as {info['user']['username']}.")
    print(f"Grant expires {info.get('expires_at')}. Run: python3 {Path(sys.argv[0]).name} sync --dest {args.dest}")
    return 0


def _run_once(paths: Paths, config: dict, args) -> int:
    client = Client(config["server"], config["credential"], ca_file=config.get("ca_file"))
    with RunLock(paths.lock):
        try:
            result = SyncRun(paths, client, workers=args.workers, include_edited=not args.no_edited,
                             export_wait=args.export_wait).run()
        except ApiError as exc:
            if exc.status in (401, 403):
                log.error("Credential rejected (%s). The grant may be revoked, expired, or your project role removed.", exc.code)
                return 3
            if exc.status == 503:
                log.error("Sync is disabled on the server.")
                return 4
            raise
    log.info("Done: %s", json.dumps(result))
    return 0 if not result["failed"] else 1


def cmd_sync(args) -> int:
    paths = Paths(Path(args.dest).expanduser().resolve())
    config = load_config(paths)
    check_server_url(config["server"], config.get("allow_http", False))
    if not args.interval:
        return _run_once(paths, config, args)
    while True:
        code = _run_once(paths, config, args)
        if code in (3, 4):
            return code
        log.info("Next sync in %d seconds", args.interval)
        time.sleep(args.interval)


def cmd_status(args) -> int:
    paths = Paths(Path(args.dest).expanduser().resolve())
    config = load_config(paths)
    state = load_state(paths)
    images = state["images"].values()
    have = sum(1 for e in images if e.get("path") and (paths.dest / e["path"]).exists())
    print(f"Project: {config.get('project', {}).get('code')}  server: {config['server']}")
    print(f"Encounters known: {len(state['encounters'])}  images known: {len(state['images'])}  present locally: {have}")
    exports = sorted(p.name for p in paths.exports.glob("*") if p.is_dir()) if paths.exports.exists() else []
    print(f"Last export: {exports[-1] if exports else '-'}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_init = sub.add_parser("init", help="store server + credential for a destination folder")
    p_init.add_argument("--server", required=True)
    p_init.add_argument("--dest", required=True)
    p_init.add_argument("--ca-file", help="custom CA bundle for a private TLS certificate")
    p_init.add_argument("--allow-http", action="store_true", help="permit plain http (not recommended)")
    p_sync = sub.add_parser("sync", help="download missing data and write CSV snapshots")
    p_sync.add_argument("--dest", required=True)
    p_sync.add_argument("--interval", type=int, default=0, help="repeat every N seconds (0 = run once)")
    p_sync.add_argument("--workers", type=int, default=1,
                        help="parallel downloads (capped by the server's advertised limit)")
    p_sync.add_argument("--export-wait", type=int, default=900,
                        help="seconds to wait for the queued Excel workbook (0 = fetch next run)")
    p_sync.add_argument("--no-edited", action="store_true", help="skip edited image variants")
    p_status = sub.add_parser("status", help="summarise the local copy")
    p_status.add_argument("--dest", required=True)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    handlers = [logging.StreamHandler()]
    dest = getattr(args, "dest", None)
    if dest and args.command == "sync":
        meta = Path(dest).expanduser().resolve() / ".sync"
        meta.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(meta / "sync.log", encoding="utf-8"))
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)
    return {"init": cmd_init, "sync": cmd_sync, "status": cmd_status}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
