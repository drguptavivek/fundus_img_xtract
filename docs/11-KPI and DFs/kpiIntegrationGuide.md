# KPI Integration Guide for Coding Agents

This guide outlines the key patterns for integrating analytics routes with the centralized KPI API system.

## 🔑 Key Integration Patterns

### 1. Backend Route (Flask)

- **Imports**:
  - `from api.kpis.<kpi_module> import get_filtered_<..._>_dataframe`
  - `from api.kpis.kpiutils import parse_filter_params, get_user_permissions`
  - `from utils.utils import with_session`
- **Structure**:
  - Use `@with_session()` for database operations. It is a Context manager and not a decorator
  - Fetch filter parameters: `params = parse_filter_params()`
  - Get user permissions: `user_lab_unit_ids = get_user_permissions(current_user.id)`
  - Retrieve data: `df, _ = get_filtered_..._dataframe(db, params, user_lab_unit_ids)`
  - Handle pagination and render the template.

### 2. Frontend Template (Jinja2)

- **JavaScript Includes**:
  - `common-filters.js`: For shared filter UI and logic.
  - A KPI-specific JS file (e.g., `encounter-kpis.js`): For chart/data handling.
  - `chart.min.js`: For visualizations.
- **Key Elements**:
  - A `<meta name="user-id" content="{{ current_user.id }}">` tag.
  - A filter section populated by `common-filters.js`.
  - An Excel download link pointing to an API endpoint: `url_for('api.get_filtered_dataframe_excel', **filters)`.
  - A container for a data table or charts (`<canvas>`).

### 3. Frontend JavaScript (Modular)

- **Architecture**: Use a dedicated class (e.g., `EncounterKPIs`) in a separate JS file.
- **Initialization**:
  - The class should accept an instance of `commonFilters`.
  - Initialize on `DOMContentLoaded`, ensuring `commonFilters` is available.
- **Event Handling**:
  - Listen for `filtersApplied` and `filtersCleared` events on the `document`.
  - On these events, refresh chart data by fetching from KPI API endpoints.
- **Chart/Table Management**:
  - **Chart.js**: Destroy chart instances (`chart.destroy()`) before re-rendering to prevent canvas reuse errors.
  - **DataTables**: Use `destroy(false)` to destroy a DataTable instance without removing the table's HTML structure, preventing re-initialization errors.

---

## 🏗️ Implementation Checklist

### Backend Route
- [ ] Import from `api.kpis.*` and `utils.utils`.
- [ ] Use `parse_filter_params()` and `get_user_permissions()`.
- [ ] Call the appropriate `get_filtered_..._dataframe()` function.
- [ ] Implement pagination.

### Frontend Template
- [ ] Include `common-filters.js` and a KPI-specific JS file.
- [ ] Point Excel download to the correct `api` endpoint.
- [ ] Add `<meta name="user-id" ...>`.

### JavaScript Module
- [ ] Create a class to manage KPIs and charts.
- [ ] Listen for `filtersApplied` and `filtersCleared` events.
- [ ] Fetch data from `/api/kpis/...` endpoints.
- [ ] Correctly destroy and re-create Chart.js and DataTables instances.

---

## 🔄 Migration Steps for Existing Routes

1.  **Update Imports**: Replace old dataframe/utility imports with `api.kpis` imports.
2.  **Replace DataFrame Generation**: Switch to using `with_session`, `parse_filter_params`, `get_user_permissions`, and `get_filtered_..._dataframe`.
3.  **Update Template**: Change the Excel download link to the `api` endpoint.
4.  **Test**: Verify filters, pagination, downloads, and permissions.

---

## 📚 Resources

- **KPI API Docs**: `docs/11-KPI and DFs/01-EncounterFile-KPI-API.md`
- **Common Filters Guide**: `docs/11-KPI and DFs/02-Common-Filters-Mechanism.md`
- **DB Context Manager**: `docs/10-DEVELOP/DB CONTEXT MANAGER.md`