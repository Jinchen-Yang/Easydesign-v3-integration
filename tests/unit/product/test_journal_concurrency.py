"""Concurrent RequestJournal schema bootstrap and legacy upgrades keep records.

Fresh scoped databases are opened simultaneously by many account requests
(threads inside the product server) and by worker processes, so the CREATE +
check-then-ALTER migration must serialize instead of racing
``duplicate column name`` on ``product_projects``. Legacy databases upgrade
in place without losing project/request records or projection semantics.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from easydesign.product.journal import RequestJournal

LEGACY_REQUEST = "legacy-create-000001"
LEGACY_PROJECT = "legacy-project"
LEGACY_PAYLOAD = {"request_id": LEGACY_REQUEST, "operation": "conversation"}

UPGRADE_CHILD = """
import json
import sys
import time
from pathlib import Path

from easydesign.product.journal import RequestJournal

start, path = float(sys.argv[1]), Path(sys.argv[2])
while time.time() < start:
    time.sleep(0.005)
payload = {"request_id": "proc-create-000001", "operation": "create"}
journal = RequestJournal(path)
try:
    legacy = journal.project("legacy-project")
    _, reserved = journal.reserve("proc-shared-project", payload)
    _, registered = journal.register_project(
        "proc-shared-project",
        request_id="proc-create-000001",
        title="Process acceptance",
        goal="Synthetic concurrent process goal.",
        thread="thread-proc",
        input_id=None,
        surface="easy",
    )
    print(
        json.dumps(
            {
                "legacy_title": legacy["title"] if legacy else None,
                "legacy_detail": legacy["detail"] if legacy else None,
                "legacy_surface": legacy["surface"] if legacy else None,
                "legacy_projection": legacy["projection"] if legacy else None,
                "reserved": reserved,
                "registered": registered,
            }
        )
    )
finally:
    journal.close()
"""


def legacy_database(path: Path) -> None:
    """A pre-surface, pre-projection journal holding real records to preserve."""
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    try:
        db.execute(
            "CREATE TABLE requests (id TEXT PRIMARY KEY, project TEXT NOT NULL, "
            "hash TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL, "
            "result TEXT, created REAL NOT NULL, updated REAL NOT NULL)"
        )
        db.execute("CREATE TABLE project_labels (project TEXT PRIMARY KEY, title TEXT NOT NULL)")
        db.execute(
            "CREATE TABLE product_projects ("
            "id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, title TEXT NOT NULL, "
            "goal TEXT NOT NULL, thread TEXT NOT NULL, input_id TEXT, state TEXT NOT NULL, "
            "detail TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL)"
        )
        db.execute(
            "INSERT INTO product_projects VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                LEGACY_PROJECT,
                LEGACY_REQUEST,
                "Legacy program",
                "Legacy synthetic goal.",
                "thread-legacy",
                None,
                "project_created",
                json.dumps({"kept": True}),
                1234.5,
                1234.6,
            ),
        )
        db.execute(
            "INSERT INTO requests VALUES(?,?,?,?,?,?,?,?)",
            (
                LEGACY_REQUEST,
                LEGACY_PROJECT,
                "hash-legacy",
                json.dumps(LEGACY_PAYLOAD),
                "succeeded",
                json.dumps({"kept": True}),
                1234.5,
                1234.6,
            ),
        )
        db.commit()
    finally:
        db.close()


def product_columns(path: Path) -> list[str]:
    db = sqlite3.connect(path)
    try:
        return [str(row[1]) for row in db.execute("PRAGMA table_info(product_projects)")]
    finally:
        db.close()


def preserved_legacy_project(value: dict | None) -> dict:
    """Every observable field of the legacy row must survive the upgrade."""
    assert value is not None
    assert value["id"] == LEGACY_PROJECT
    assert value["request_id"] == LEGACY_REQUEST
    assert value["title"] == "Legacy program"
    assert value["goal"] == "Legacy synthetic goal."
    assert value["thread"] == "thread-legacy"
    assert value["input_id"] is None
    assert value["state"] == "project_created"
    assert value["detail"] == {"kept": True}
    assert value["created"] == 1234.5
    assert value["updated"] == 1234.6
    assert value["surface"] is None
    assert value["projection"] is None
    return value


def test_current_journal_opens_for_reading_while_another_connection_is_writing(tmp_path):
    path = tmp_path / "requests.sqlite"
    journal = RequestJournal(path)
    try:
        journal.register_project(
            "readable-project",
            request_id="readable-create-000001",
            title="Committed title",
            goal="Synthetic reader isolation goal.",
            thread="thread-readable",
            input_id=None,
            surface="easy",
        )
        journal.update_projection("readable-project", {"title": "Committed title"})
    finally:
        journal.close()

    writer = sqlite3.connect(path)
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("UPDATE product_projects SET title='Uncommitted title'")
    finished = threading.Event()
    failures: list[BaseException] = []
    observed: list[dict | None] = []

    def read_committed_project() -> None:
        try:
            reader = RequestJournal(path)
            try:
                observed.append(reader.project("readable-project"))
            finally:
                reader.close()
        except BaseException as error:  # pragma: no cover - only on regression
            failures.append(error)
        finally:
            finished.set()

    thread = threading.Thread(target=read_committed_project)
    try:
        thread.start()
        # The reader must finish before the writer releases its lock. This is
        # WAL reader/writer isolation, not a query-speed benchmark.
        read_without_waiting_for_writer = finished.wait(timeout=2)
    finally:
        writer.rollback()
        writer.close()
        thread.join(timeout=20)
    assert read_without_waiting_for_writer, "Opening a current journal waited for a write lock"
    assert failures == []
    assert observed[0] is not None
    assert observed[0]["title"] == "Committed title"
    assert observed[0]["projection"] == {"title": "Committed title"}


def test_concurrent_thread_opens_upgrade_legacy_database_preserving_records(tmp_path):
    path = tmp_path / "state" / "product" / "requests.sqlite"
    legacy_database(path)
    barrier = threading.Barrier(8)
    failures: list[BaseException] = []
    observed: list[dict] = []

    def open_and_read() -> None:
        try:
            barrier.wait(timeout=60)
            journal = RequestJournal(path)
            try:
                observed.append(preserved_legacy_project(journal.project(LEGACY_PROJECT)))
            finally:
                journal.close()
        except BaseException as error:  # pragma: no cover - only on regression
            failures.append(error)

    threads = [threading.Thread(target=open_and_read) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert failures == []
    assert len(observed) == 8
    assert product_columns(path).count("surface") == 1
    assert product_columns(path).count("projection") == 1

    journal = RequestJournal(path)
    try:
        preserved_legacy_project(journal.project(LEGACY_PROJECT))
        request = journal.get(LEGACY_REQUEST)
        assert request is not None
        assert request["state"] == "succeeded"
        assert request["payload"] == LEGACY_PAYLOAD
        assert request["result"] == {"kept": True}
        # Projection semantics survive the upgrade path.
        journal.update_projection(LEGACY_PROJECT, {"title": "Legacy program", "phase": "prepare"})
        projected = journal.project(LEGACY_PROJECT)
        assert projected is not None
        assert projected["projection"] == {"title": "Legacy program", "phase": "prepare"}
        journal.rename_project(LEGACY_PROJECT, "Renamed legacy program")
        renamed = journal.project(LEGACY_PROJECT)
        assert renamed is not None
        projection = renamed["projection"]
        assert projection is not None and projection["title"] == "Renamed legacy program"
        journal.update_project(LEGACY_PROJECT, "prepare_started", {"note": "synthetic"})
        upgraded = journal.project(LEGACY_PROJECT)
        assert upgraded is not None
        assert upgraded["title"] == "Renamed legacy program"
        assert upgraded["state"] == "prepare_started"
        assert upgraded["detail"] == {"note": "synthetic"}
        assert upgraded["projection"] is None
    finally:
        journal.close()


@pytest.mark.parametrize("legacy", [False, True], ids=["fresh", "legacy"])
def test_concurrent_process_opens_preserve_records_and_request_identity(tmp_path, legacy):
    path = tmp_path / "state" / "product" / "requests.sqlite"
    if legacy:
        legacy_database(path)
    start = time.time() + 1.5
    children = [
        subprocess.Popen(
            [sys.executable, "-B", "-c", UPGRADE_CHILD, str(start), str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(4)
    ]
    reports = []
    for child in children:
        stdout, stderr = child.communicate(timeout=120)
        assert child.returncode == 0, stderr
        reports.append(json.loads(stdout))
    expected_title = "Legacy program" if legacy else None
    expected_detail = {"kept": True} if legacy else None
    assert all(report["legacy_title"] == expected_title for report in reports)
    assert all(report["legacy_detail"] == expected_detail for report in reports)
    assert all(report["legacy_surface"] is None for report in reports)
    assert all(report["legacy_projection"] is None for report in reports)
    # Exactly one process created the shared identity; the rest replayed it.
    assert sum(report["reserved"] for report in reports) == 1
    assert sum(report["registered"] for report in reports) == 1
    assert product_columns(path).count("surface") == 1
    assert product_columns(path).count("projection") == 1

    journal = RequestJournal(path)
    try:
        if legacy:
            preserved_legacy_project(journal.project(LEGACY_PROJECT))
            assert journal.get(LEGACY_REQUEST) is not None
        shared = journal.project("proc-shared-project")
        assert shared is not None
        assert shared["title"] == "Process acceptance"
        assert shared["surface"] == "easy"
    finally:
        journal.close()


def test_concurrent_fresh_database_opens_stay_idempotent(tmp_path):
    """The reported race: many first opens of one fresh scoped database."""
    path = tmp_path / "fresh" / "requests.sqlite"
    barrier = threading.Barrier(12)
    failures: list[BaseException] = []
    outcomes: list[tuple[bool, bool]] = []
    payload = {"request_id": "fresh-create-000001", "operation": "create"}

    def open_and_seed() -> None:
        try:
            barrier.wait(timeout=60)
            journal = RequestJournal(path)
            try:
                _, reserved = journal.reserve("fresh-project", payload)
                _, registered = journal.register_project(
                    "fresh-project",
                    request_id="fresh-create-000001",
                    title="Fresh acceptance",
                    goal="Synthetic fresh goal.",
                    thread="thread-fresh",
                    input_id=None,
                    surface="easy",
                )
                outcomes.append((reserved, registered))
            finally:
                journal.close()
        except BaseException as error:  # pragma: no cover - only on regression
            failures.append(error)

    threads = [threading.Thread(target=open_and_seed) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert failures == []
    assert len(outcomes) == 12
    assert sum(reserved for reserved, _ in outcomes) == 1
    assert sum(registered for _, registered in outcomes) == 1

    journal = RequestJournal(path)
    try:
        fresh = journal.project("fresh-project")
        assert fresh is not None
        assert fresh["projection"] is None
        assert journal.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert journal.db.execute("PRAGMA synchronous").fetchone()[0] == 2
    finally:
        journal.close()
    assert product_columns(path).count("surface") == 1
    assert product_columns(path).count("projection") == 1


def test_reopening_a_replaced_database_checks_its_own_schema(tmp_path):
    path = tmp_path / "requests.sqlite"
    journal = RequestJournal(path)
    journal.close()
    # Both files are synthetic fixtures with no live connections. Reusing a
    # pathname must not skip migrations for the different database now there.
    path.rename(tmp_path / "previous.sqlite")
    legacy_database(path)

    replacement = RequestJournal(path)
    try:
        preserved_legacy_project(replacement.project(LEGACY_PROJECT))
        replacement.update_projection(LEGACY_PROJECT, {"title": "Replacement projection"})
        project = replacement.project(LEGACY_PROJECT)
        assert project is not None
        assert project["projection"] == {"title": "Replacement projection"}
    finally:
        replacement.close()


def test_legacy_typed_project_backfills_identity_from_its_original_request(tmp_path):
    path = tmp_path / "legacy.sqlite"
    journal = RequestJournal(path)
    target = {"kind": "uniprot", "accession": "P21452"}
    payload = {"operation": "create", "request_id": "legacy-create-0001", "target_input": target}
    journal.reserve("legacy-project", payload)
    journal.register_project(
        "legacy-project",
        request_id="legacy-create-0001",
        title="Legacy",
        goal="Synthetic goal",
        thread="thread",
        input_id=None,
        surface="easy",
    )
    with journal.db:
        journal.db.execute("ALTER TABLE product_projects DROP COLUMN target_input")
        journal.db.execute("ALTER TABLE product_projects DROP COLUMN deleted_at")
    journal.close()
    migrated = RequestJournal(path)
    try:
        assert migrated.project("legacy-project")["target_input"] == target
        saved, created = migrated.register_project(
            "legacy-project",
            request_id="legacy-create-0001",
            title="Legacy",
            goal="Synthetic goal",
            thread="thread",
            input_id=None,
            surface="easy",
            target_input=target,
        )
        assert not created
        assert saved["target_input"] == target
        assert migrated.get("legacy-create-0001")["payload"] == payload
    finally:
        migrated.close()
