import sqlite3
from types import SimpleNamespace

from easydesign.agent.phase34_read_scope import authority_read, verified_read


def test_authority_read_does_not_cache_across_operations_or_ledger_changes():
    class Reader:
        def __init__(self):
            self.store = SimpleNamespace(db=sqlite3.connect(":memory:"))
            self.store.db.execute("CREATE TABLE events(seq INTEGER)")
            self.calls = 0
            self.fact = "first"

        @verified_read
        def facts(self):
            self.calls += 1
            return {"value": self.fact}

        @authority_read
        def snapshot(self, advance=False):
            first = self.facts()
            first["value"] = "caller mutation"
            if advance:
                self.fact = "new revision"
                self.store.db.execute("INSERT INTO events VALUES(1)")
            return self.facts()

    reader = Reader()
    assert reader.snapshot() == {"value": "first"}
    assert reader.calls == 1
    reader.fact = "externally changed"
    assert reader.snapshot() == {"value": "externally changed"}
    assert reader.calls == 2
    assert reader.snapshot(advance=True) == {"value": "new revision"}
    assert reader.calls == 4
    assert reader._authority_reads is None
    reader.store.db.close()
