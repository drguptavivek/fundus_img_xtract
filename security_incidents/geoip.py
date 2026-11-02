"""Optional offline GeoIP; never send source IPs to an external provider."""
from dataclasses import asdict, dataclass
from functools import lru_cache
import ipaddress
from pathlib import Path


@dataclass(frozen=True)
class GeoLocation:
    status: str
    country: str | None = None
    city: str | None = None
    database_date: str | None = None

    def to_dict(self):
        return asdict(self)


@lru_cache(maxsize=2)
def _reader(path: str, modified: float):
    import maxminddb
    return maxminddb.open_database(path)


def locate_ip(ip_address: str, *, database_path: str | None) -> GeoLocation:
    try:
        address = ipaddress.ip_address(ip_address)
    except ValueError:
        return GeoLocation("invalid")
    if not address.is_global:
        return GeoLocation("private_or_reserved")
    if not database_path:
        return GeoLocation("not_configured")
    try:
        path = Path(database_path)
        reader = _reader(str(path), path.stat().st_mtime)
        record = reader.get(str(address))
        if not record:
            return GeoLocation("not_found")
        from datetime import datetime, timezone
        built = datetime.fromtimestamp(reader.metadata().build_epoch, timezone.utc).date().isoformat()
        return GeoLocation("located", record.get("country", {}).get("names", {}).get("en")
                           or record.get("country", {}).get("iso_code"),
                           record.get("city", {}).get("names", {}).get("en"), built)
    except (ImportError, OSError, ValueError, RuntimeError):
        return GeoLocation("lookup_unavailable")
