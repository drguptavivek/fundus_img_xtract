import subprocess
import time

import pytest

from scripts import backup_db


def test_report_progress_shows_elapsed_time_and_output_size(tmp_path, capsys):
    output_path = tmp_path / "dump.sql"
    output_path.write_bytes(b"x" * 2048)

    with backup_db.report_progress("SQL dump", output_path, interval=0.01):
        time.sleep(0.03)

    output = capsys.readouterr().out
    assert "SQL dump: still running" in output
    assert "output 2.0 KiB" in output


def test_database_backup_removes_partial_files_when_interrupted(
    tmp_path, monkeypatch, capsys
):
    timestamp = "20261028_120000"
    sql_path = tmp_path / f"backup_{timestamp}_db.sql"
    tar_path = tmp_path / f"backup_{timestamp}_db.tar.gz"

    def interrupt_dump(*_args, **_kwargs):
        sql_path.write_text("partial dump")
        tar_path.write_text("partial archive")
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess, "run", interrupt_dump)

    with pytest.raises(KeyboardInterrupt):
        backup_db.create_postgresql_backup(tmp_path, timestamp)

    assert not sql_path.exists()
    assert not tar_path.exists()
    assert "removing partial database files" in capsys.readouterr().out


def test_app_backup_removes_partial_archive_when_interrupted(
    tmp_path, monkeypatch, capsys
):
    timestamp = "20261028_120000"
    tar_path = tmp_path / f"backup_{timestamp}_app.tar.gz"

    def interrupt_add(self, *_args, **_kwargs):
        tar_path.write_text("partial archive")
        raise KeyboardInterrupt

    monkeypatch.setattr(backup_db.tarfile.TarFile, "add", interrupt_add)

    with pytest.raises(KeyboardInterrupt):
        backup_db.create_app_backup(tmp_path, timestamp)

    assert not tar_path.exists()
    assert "removing partial app archive" in capsys.readouterr().out
