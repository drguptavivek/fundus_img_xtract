import os
import re as _re
from collections import Counter
from flask import render_template
from sqlalchemy import select
from auth.roles import roles_required
from models import BASE_DIR, Session


def malicious_uploads():
    """Show recent malicious upload incidents parsed from the log file with KPIs."""
    log_path = BASE_DIR / os.getenv("MALICIOUS_UPLOAD_LOG", "logs/malicious_uploads.log")
    incidents: list[dict] = []
    try:
        if log_path.exists():
            lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            # Keep and parse the last 1000 entries (reverse for newest-first later)
            for line in lines[-1000:]:
                # Format: [ts] zip=... user=... ip=... reason=... [expected=...] [detected=...] entry=...
                m = _re.match(r"^\[(?P<ts>[^\]]+)\]\s+(?P<rest>.*)$", line)
                if not m:
                    continue
                rest = m.group("rest")
                def kv(key: str, default: str = "-") -> str:
                    mm = _re.search(rf"\b{key}=([^\s]+)", rest)
                    return mm.group(1) if mm else default
                # entry may contain spaces; capture to end
                me = _re.search(r"\bentry=(.*)$", rest)
                incidents.append({
                    "ts": m.group("ts"),
                    "zip": kv("zip"),
                    "user": kv("user"),
                    "ip": kv("ip"),
                    "reason": kv("reason"),
                    "expected": kv("expected", ""),
                    "detected": kv("detected", ""),
                    "entry": (me.group(1).strip() if me else ""),
                })
        else:
            flash(f"Log not found: {log_path}", "warning")
    except Exception as e:
        flash(f"Failed to read log: {e}", "danger")

    # Newest first
    incidents.reverse()

    # KPIs
    total = len(incidents)
    by_user = Counter((it["user"] or "-") for it in incidents)
    by_reason = Counter((it["reason"] or "-") for it in incidents)
    by_ip = Counter((it["ip"] or "-") for it in incidents)

    # Top lists (limit 10)
    top_users = by_user.most_common(10)
    top_reasons = by_reason.most_common(10)
    top_ips = by_ip.most_common(10)

    return render_template(
        "admin/malicious_uploads.html",
        incidents=incidents,
        log_path=str(log_path),
        total=total,
        top_users=top_users,
        top_reasons=top_reasons,
        top_ips=top_ips,
    )