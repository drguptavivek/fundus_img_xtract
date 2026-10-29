"""Rate limits for high-volume EncounterSet review operations."""

REVIEW_RATE_LIMIT = "20000 per hour; 1000 per minute"


def configure_review_rate_limit(app):
    """Give image review its own quota while retaining per-user limiting."""
    limiters = app.extensions.get("limiter")
    if not limiters:
        return
    limiter = next(iter(limiters)) if isinstance(limiters, set) else limiters
    endpoint = "verify_encounter_set.mark_reviewed"
    app.view_functions[endpoint] = limiter.limit(
        REVIEW_RATE_LIMIT, methods=["POST"], override_defaults=True
    )(app.view_functions[endpoint])
