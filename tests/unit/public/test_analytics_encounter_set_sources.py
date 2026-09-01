from pathlib import Path


def test_public_pages_load_the_shared_kpi_api_with_htmx():
    root = Path(__file__).resolve().parents[3]
    for template_name in ("home.html", "public/analytics.html"):
        template = (root / "templates" / template_name).read_text()
        assert "fundus_api.public_kpis" in template
        assert 'hx-trigger="load"' in template
        assert "js/htmx.min.js" in template


def test_deleted_analytics_kpi_endpoint_is_not_referenced_by_public_templates():
    root = Path(__file__).resolve().parents[3]
    for template_name in ("home.html", "public/analytics.html"):
        template = (root / "templates" / template_name).read_text()
        assert "/api/analytics/kpi" not in template
