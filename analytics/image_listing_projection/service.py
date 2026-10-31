from dataclasses import dataclass

from sqlalchemy import text

from db_transaction_manager import transaction_scope


@dataclass(frozen=True)
class RefreshResult:
    status: str
    refreshed: int = 0


def refresh_glaucoma_listing() -> RefreshResult:
    """Refresh the complete application glaucoma listing, skipping overlapping workers."""
    with transaction_scope() as db:
        db.execute(text("SET LOCAL statement_timeout='20s'"))
        db.execute(text("SET LOCAL lock_timeout='1s'"))
        locked = db.execute(text(
            "SELECT pg_try_advisory_xact_lock(hashtextextended("
            "current_schema() || '.glaucoma_listing_refresh', 0))"
        )).scalar()
        if not locked:
            return RefreshResult(status='busy')
        available = db.execute(text(
            "SELECT EXISTS (SELECT 1 FROM pg_matviews WHERE schemaname=current_schema() "
            "AND matviewname='mvw_image_listing_glaucoma_1_v2')"
        )).scalar()
        if not available:
            return RefreshResult(status='not_installed')
        db.execute(text('REFRESH MATERIALIZED VIEW CONCURRENTLY mvw_image_listing_glaucoma_1_v2'))
        return RefreshResult(status='updated', refreshed=1)
