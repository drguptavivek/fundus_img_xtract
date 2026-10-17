"""Build the staged project export package as one DuckDB file."""
from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import (
    guide, stage_ai, stage_annotations, stage_api, stage_dims, stage_grading, stage_intra, stage_ocr, stage_review,
    stage_timing, stage_verification, tables,
)
from .schema import (
    DATA_DICTIONARY, GUIDE, MANIFEST, PACKAGE_TABLES, RELATIONSHIPS, SCHEMA_VERSION, TABLES, Table,
)

# Stages in priority order; each build(ctx) returns {table name: rows}.
STAGES = (
    stage_api, stage_verification, stage_ocr, stage_ai, stage_grading, stage_annotations,
    stage_timing, stage_review, stage_intra, stage_dims,
)


def _coerce(column, value):
    """Last line of defence: one odd value must never fail a whole export."""
    if value is None:
        return None
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    if column.type == "VARCHAR" and not isinstance(value, str):
        return str(value)
    if column.type == "JSON" and not isinstance(value, str):
        return json.dumps(value, default=str)
    return value


def _insert(con, table: Table, rows: list[dict], workdir: Path) -> None:
    """Create the table and bulk-load ``rows`` through a typed newline-delimited JSON file.

    Row-by-row executemany takes ~1 ms per row (100 s for a 70k-row project); read_json loads the same data in
    well under a second. JSON-typed columns travel as text and are cast on insert.
    """
    names = table.column_names
    for row in rows:
        if set(row) != set(names):
            raise ValueError(f"{table.name}: row keys differ from schema: {sorted(set(row) ^ set(names))}")
    con.execute(table.ddl())
    if not rows:
        return
    source = workdir / f"{table.name}.ndjson"
    with source.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps({c.name: _coerce(c, row[c.name]) for c in table.columns}, default=str))
            handle.write("\n")
    columns = ", ".join(f"'{c.name}': '{'VARCHAR' if c.type == 'JSON' else c.type}'" for c in table.columns)
    con.execute(
        f'INSERT INTO "{table.name}" SELECT * FROM read_json(?, format = \'newline_delimited\', columns = {{{columns}}})',
        [str(source)],
    )
    source.unlink()


# (source table, key column, derived table). The derived table has one typed column per metadata key.
_TYPED_METADATA = (
    ("encounters", "encounter_uuid", "encounter_metadata"),
    ("images", "image_uuid", "image_metadata_values"),
)


def _typed_metadata(con, source: str, key: str, dest: str) -> tuple[list[dict], str | None]:
    """Flatten ``source.metadata`` JSON into typed columns (json_group_structure + json_transform).

    Returns ``(data_dictionary_rows, error)``. Never raises: the JSON column stays authoritative, so an
    unusual key set only costs the convenience table. Timestamps stay VARCHAR (JSON has no timestamp type).
    """
    where = "metadata IS NOT NULL"
    try:
        structure = con.execute(f'SELECT json_group_structure(metadata::JSON) FROM "{source}" WHERE {where}').fetchone()[0]
        if structure in (None, "null", "{}"):
            return [], None
        con.execute(f'SET VARIABLE structure = (SELECT json_group_structure(metadata::JSON) FROM "{source}" WHERE {where})')
        con.execute(
            f'CREATE TABLE "{dest}" AS SELECT "{key}", '
            f"unnest(json_transform(metadata::JSON, getvariable('structure')), recursive := true, keep_parent_names := true) "
            f'FROM "{source}" WHERE {where}'
        )
    except Exception as exc:  # duckdb.Error subclasses; also covers a metadata key colliding with the join key
        con.execute(f'DROP TABLE IF EXISTS "{dest}"')
        return [], f"{type(exc).__name__}: {exc}"[:300]
    rows = [{"table_name": dest, "stage": "derived", "column_name": "",
             "type": "", "description": f"Typed, flattened copy of {source}.metadata (one column per key; "
                                         f"nested keys joined with '.'; timestamps remain text). Join on {key}."}]
    rows += [
        {"table_name": dest, "stage": "derived", "column_name": name, "type": col_type,
         "description": "Metadata key." if name != key else f"Join key to {source}."}
        for name, col_type, *_ in con.execute(f'DESCRIBE "{dest}"').fetchall()
    ]
    return rows, None


def build_package(db, scope, path: str | Path, *, project_code: str, project_title: str) -> dict[str, int]:
    """Write ``path`` and return ``{table: row_count}``. Refuses to overwrite an existing file."""
    import duckdb  # lazy: the module must stay importable (options, DTOs) without the wheel

    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    encounters = tables.load_encounters(db, scope)
    ctx = tables.BuildContext(db, scope, encounters, tables.collect_media(db, scope, encounters))
    built = {"encounters": tables.encounter_rows(ctx), "images": tables.image_rows(ctx)}
    for stage in STAGES:
        built.update(stage.build(ctx))
    missing = {table.name for table in TABLES} ^ set(built)
    if missing:
        raise RuntimeError(f"stage output does not match the schema: {sorted(missing)}")
    counts = {name: len(rows) for name, rows in built.items()}
    manifest = [
        ("schema_version", SCHEMA_VERSION),
        ("duckdb_version", duckdb.__version__),
        ("exported_at", datetime.now(timezone.utc).isoformat()),
        ("scope", "project" if scope.project_id is not None else "no_project"),
        ("project_id", "" if scope.project_id is None else str(scope.project_id)),
        ("project_code", project_code),
        ("project_title", project_title),
        ("lab_unit_ids", ",".join(str(i) for i in sorted(scope.lab_unit_ids))),
        ("identifier_lab_unit_ids", ",".join(str(i) for i in sorted(scope.pii_lab_unit_ids))),
        *((f"rows_{name}", str(count)) for name, count in counts.items()),
    ]
    dictionary = []
    for table in TABLES + PACKAGE_TABLES:
        dictionary.append({"table_name": table.name, "stage": table.stage, "column_name": "",
                           "type": "", "description": table.description})
        dictionary.extend(
            {"table_name": table.name, "stage": table.stage, "column_name": c.name,
             "type": c.type, "description": c.description}
            for c in table.columns
        )
    workdir = Path(tempfile.mkdtemp(prefix="export_load_", dir=path.parent))
    con = duckdb.connect(str(path))
    try:
        for table in TABLES:
            _insert(con, table, built[table.name], workdir)
        for source, key, dest in _TYPED_METADATA:
            extra, error = _typed_metadata(con, source, key, dest)
            dictionary.extend(extra)
            manifest.append((f"typed_{dest}", "built" if extra else (f"skipped: {error}" if error else "no metadata")))
        _insert(con, MANIFEST, [{"key": k, "value": v} for k, v in manifest], workdir)
        _insert(con, GUIDE, [{"section": s, "title": ti, "text": tx} for s, ti, tx in guide.GUIDE], workdir)
        _insert(con, RELATIONSHIPS, [
            dict(zip(RELATIONSHIPS.column_names, row)) for row in guide.RELATIONSHIPS
        ], workdir)
        _insert(con, DATA_DICTIONARY, dictionary, workdir)
    except Exception:
        con.close()
        path.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    con.close()
    return counts
