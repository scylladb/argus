from argus.backend.util.common import BATCH_MAX_STATEMENTS, SizedBatchQuery, save_in_batches


class RecordingBatch(SizedBatchQuery):
    """A SizedBatchQuery that records each flush instead of talking to the cluster."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.flushed = []

    def execute(self):
        self.flushed.append(self.pending)
        self._statements.clear()


class FakeDocument:
    def __init__(self, payload: str):
        self.payload = payload

    def save(self, batch=None):
        batch.add("INSERT INTO t (a) VALUES (?)", [self.payload])


def test_a_batch_flushes_once_it_reaches_the_statement_cap():
    batch = RecordingBatch(max_statements=10, max_bytes=10_000_000)

    for i in range(25):
        batch.add("INSERT INTO t (a) VALUES (?)", [str(i)])
    batch.flush()

    assert batch.flushed == [10, 10, 5]


def test_a_batch_flushes_before_it_outgrows_the_byte_cap():
    batch = RecordingBatch(max_statements=1000, max_bytes=200)

    for _ in range(10):
        batch.add("INSERT INTO t (a) VALUES (?)", ["x" * 50])
    batch.flush()

    assert len(batch.flushed) > 1
    assert sum(batch.flushed) == 10


def test_an_empty_batch_never_executes():
    batch = RecordingBatch()

    batch.flush()

    assert batch.flushed == []


def test_save_in_batches_writes_every_document(monkeypatch):
    seen = []

    class Counting(SizedBatchQuery):
        def execute(self):
            seen.append(self.pending)
            self._statements.clear()

    monkeypatch.setattr("argus.backend.util.common.SizedBatchQuery", Counting)

    written = save_in_batches(range(450), lambda i: [FakeDocument(str(i)), FakeDocument(f"{i}-b")])

    assert written == 900
    assert sum(seen) == 900
    assert max(seen) <= BATCH_MAX_STATEMENTS


def test_save_in_batches_tolerates_an_item_yielding_nothing(monkeypatch):
    class Counting(SizedBatchQuery):
        def execute(self):
            self._statements.clear()

    monkeypatch.setattr("argus.backend.util.common.SizedBatchQuery", Counting)

    assert save_in_batches(range(5), lambda i: [] if i % 2 else [FakeDocument(str(i))]) == 3
