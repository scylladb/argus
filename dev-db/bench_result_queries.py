#!/usr/bin/env python3
"""Benchmark candidate query strategies for cross-test result analysis (ARGUS-213).

ARGUS-96 wants adaptive-timeout and duration metrics analysed across all jobs
and releases.  Generic results are partitioned by ``test_id``
(``generic_result_data_v1``: PK ``(test_id, name)``, CK ``(run_id, column, row)``),
so there is no single query that spans tests.  Three strategies are possible:

  A  index    -- ``WHERE column = ?``, using the existing (unused) global
                 secondary index ``generic_result_data_v1_column_idx``.
  B  fanout   -- one full-partition read per test, filtered client-side.  This
                 is what every "global" widget does today (see
                 ``views_widgets/graphed_stats.py``, which loops over
                 ``view.tests``).  Measured both sequentially (what the code
                 does now) and concurrently (what it could do).
  C  denorm   -- a table partitioned by ``(column, time_bucket)``, so the same
                 question becomes a bounded single-partition read.  Costs a
                 write-path change and a backfill.

Usage:
    # against the dev DB from argus_web.yaml
    python dev-db/bench_result_queries.py seed --tests 50 --runs 50 --columns 20 --rows 10
    python dev-db/bench_result_queries.py bench --repeats 5
    python dev-db/bench_result_queries.py sweep          # several scales in one go
    python dev-db/bench_result_queries.py drop           # remove benchmark data

    # against any other cluster -- REQUIRED for a meaningful A-vs-C answer
    python dev-db/bench_result_queries.py seed  --contact-points n1 n2 n3 --rf 3 ...
    python dev-db/bench_result_queries.py bench --contact-points n1 n2 n3 --rf 3
    python dev-db/bench_result_queries.py trace --contact-points n1 n2 n3 --rf 3

Run from the repository root so argus_web.yaml is found automatically.

NOTE ON VALIDITY: strategy A's cost is dominated by how many replicas the
coordinator must contact, which a single-node cluster cannot show at all -- on
one node A looks competitive with C, and on three it is 3x worse.  Always use
--contact-points against a real cluster before drawing an A-vs-C conclusion,
and use `trace` to see the per-page node fan-out and server-side event count
that explain the difference.
"""

import argparse
import logging
import statistics
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cassandra import ConsistencyLevel, OperationTimedOut
from cassandra.auth import PlainTextAuthProvider
from cassandra.cluster import EXEC_PROFILE_DEFAULT, Cluster, ExecutionProfile
from cassandra.concurrent import execute_concurrent_with_args
from cassandra.policies import RoundRobinPolicy
from cassandra.query import SimpleStatement, TraceUnavailable, dict_factory

from argus.backend.db import ScyllaCluster
from argus.backend.util.config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
LOGGER = logging.getLogger("bench")
logging.getLogger("cassandra").setLevel(logging.WARNING)

# Benchmark rows are tagged with this table name so they can be found and
# dropped without touching real seeded data.
BENCH_TABLE_NAME = "ARGUS213 Bench Table"

# The metric the dashboard would ask about.  Deliberately one of many columns
# so the index partition for it is a small slice of the whole table -- the
# realistic case, and the one where a secondary index looks most attractive.
TARGET_COLUMN = "adaptive_timeout_duration"

DENORM_TABLE = "bench_result_by_column"

# Faithful copy of the production schema, for the --contact-points path where
# the target cluster has no Argus schema of its own.  Kept byte-comparable with
# `DESCRIBE TABLE argus.generic_result_data_v1` (clustering order included --
# it decides whether the index read is a sequential or scattered walk).
MAIN_DDL = """
CREATE TABLE IF NOT EXISTS {keyspace}.generic_result_data_v1 (
    test_id uuid,
    name text,
    run_id uuid,
    column ascii,
    row ascii,
    status ascii,
    sut_timestamp timestamp,
    value double,
    value_text text,
    PRIMARY KEY ((test_id, name), run_id, column, row)
) WITH CLUSTERING ORDER BY (run_id ASC, column ASC, row ASC)
"""
MAIN_INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS generic_result_data_v1_column_idx ON {keyspace}.generic_result_data_v1(column)",
    "CREATE INDEX IF NOT EXISTS generic_result_data_v1_row_idx ON {keyspace}.generic_result_data_v1(row)",
]

DENORM_DDL = f"""
CREATE TABLE IF NOT EXISTS {{keyspace}}.{DENORM_TABLE} (
    column ascii,
    time_bucket int,
    sut_timestamp timestamp,
    test_id uuid,
    run_id uuid,
    row ascii,
    value double,
    status ascii,
    PRIMARY KEY ((column, time_bucket), sut_timestamp, test_id, run_id, row)
) WITH CLUSTERING ORDER BY (sut_timestamp DESC)
"""


def bucket_of(ts: datetime) -> int:
    """Month bucket, e.g. 202609.  Coarse enough to keep partitions few."""
    return ts.year * 100 + ts.month


def connect_external(contact_points: list[str], port: int, keyspace: str, username: str, password: str, rf: int):
    """Session against an arbitrary cluster, creating the schema if absent.

    Used to run the same benchmark against a multi-node cluster, which is the
    only way to see strategy A's replica fan-out.  Consistency level matches
    the QUORUM that ``ScyllaCluster.session`` uses, so the two paths are
    comparable.
    """
    profile = ExecutionProfile(
        load_balancing_policy=RoundRobinPolicy(),
        consistency_level=ConsistencyLevel.QUORUM,
        row_factory=dict_factory,
        request_timeout=600,
    )
    cluster = Cluster(
        contact_points=contact_points,
        port=port,
        protocol_version=4,
        auth_provider=PlainTextAuthProvider(username, password),
        execution_profiles={EXEC_PROFILE_DEFAULT: profile},
    )
    session = cluster.connect()
    # SimpleStrategy so the throwaway bench keyspace does not depend on the
    # target cluster's snitch/DC naming -- replica count is what matters here,
    # not topology awareness.
    session.execute(
        f"CREATE KEYSPACE IF NOT EXISTS {keyspace} WITH replication = "
        f"{{'class': 'SimpleStrategy', 'replication_factor': {rf}}}"
    )
    session.set_keyspace(keyspace)
    session.execute(MAIN_DDL.format(keyspace=keyspace))
    for ddl in MAIN_INDEX_DDL:
        session.execute(ddl.format(keyspace=keyspace))
    LOGGER.info(
        "connected to %s:%d keyspace=%s rf=%d (%d hosts up)",
        contact_points,
        port,
        keyspace,
        rf,
        len(cluster.metadata.all_hosts()),
    )
    return session, keyspace


class Bench:
    def __init__(self, session=None, keyspace: str | None = None) -> None:
        if session is not None:
            self.session, self.keyspace = session, keyspace
        else:
            self.session = ScyllaCluster.get().session
            self.keyspace = Config.CONFIG["SCYLLA_KEYSPACE_NAME"]

    # ---------------------------------------------------------------- seeding

    def seed(self, tests: int, runs: int, columns: int, rows: int, months: int) -> dict:
        """Write `tests * runs * columns * rows` cells into the real results
        table, plus the same data into the denormalized table."""
        self.session.execute(DENORM_DDL.format(keyspace=self.keyspace))

        col_names = [TARGET_COLUMN] + [f"metric_{i:02d}" for i in range(columns - 1)]
        row_names = [f"op_{i:02d}" for i in range(rows)]
        test_ids = [uuid4() for _ in range(tests)]

        insert_main = self.session.prepare(
            "INSERT INTO generic_result_data_v1 "
            "(test_id, name, run_id, column, row, sut_timestamp, value, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
        insert_denorm = self.session.prepare(
            f"INSERT INTO {DENORM_TABLE} "
            "(column, time_bucket, sut_timestamp, test_id, run_id, row, value, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )

        now = datetime.now(UTC)
        total = 0
        started = time.monotonic()

        for t_idx, test_id in enumerate(test_ids):
            main_args, denorm_args = [], []
            for r_idx in range(runs):
                run_id = uuid4()
                # Spread runs over `months` so the denormalized table gets a
                # realistic number of time buckets.
                ts = now - timedelta(days=(r_idx * months * 30) // max(runs, 1))
                bucket = bucket_of(ts)
                for col in col_names:
                    for row in row_names:
                        value = float((t_idx * 7 + r_idx * 13 + len(col)) % 600)
                        main_args.append((test_id, BENCH_TABLE_NAME, run_id, col, row, ts, value, "PASS"))
                        denorm_args.append((col, bucket, ts, test_id, run_id, row, value, "PASS"))

            execute_concurrent_with_args(self.session, insert_main, main_args, concurrency=64)
            execute_concurrent_with_args(self.session, insert_denorm, denorm_args, concurrency=64)
            total += len(main_args)
            LOGGER.info("seeded test %d/%d (%d cells so far)", t_idx + 1, tests, total)

        elapsed = time.monotonic() - started
        LOGGER.info("seeded %d cells in %.1fs", total, elapsed)
        return {
            "cells": total,
            "tests": tests,
            "runs": runs,
            "columns": columns,
            "rows": rows,
            "test_ids": test_ids,
            "seed_seconds": elapsed,
        }

    def bench_test_ids(self) -> list:
        """Recover the benchmark's test_ids from the data itself, so `bench`
        can run in a separate process from `seed`."""
        stmt = SimpleStatement("SELECT DISTINCT test_id, name FROM generic_result_data_v1", fetch_size=5000)
        return [r["test_id"] for r in self.session.execute(stmt) if r["name"] == BENCH_TABLE_NAME]

    # ------------------------------------------------------------- strategies

    def strategy_index(self) -> tuple[int, float]:
        """A: one cross-partition read through the secondary index."""
        stmt = self.session.prepare(
            "SELECT test_id, run_id, row, value, sut_timestamp FROM generic_result_data_v1 WHERE column = ?"
        )
        stmt.fetch_size = 5000
        started = time.monotonic()
        count = sum(1 for _ in self.session.execute(stmt, (TARGET_COLUMN,)))
        return count, time.monotonic() - started

    def strategy_fanout_serial(self, test_ids: list) -> tuple[int, float]:
        """B: full-partition read per test, sequential -- today's pattern."""
        stmt = self.session.prepare(
            "SELECT run_id, column, row, value, sut_timestamp "
            "FROM generic_result_data_v1 WHERE test_id = ? AND name = ?"
        )
        stmt.fetch_size = 5000
        started = time.monotonic()
        count = 0
        for test_id in test_ids:
            for cell in self.session.execute(stmt, (test_id, BENCH_TABLE_NAME)):
                if cell["column"] == TARGET_COLUMN:
                    count += 1
        return count, time.monotonic() - started

    def strategy_fanout_concurrent(self, test_ids: list) -> tuple[int, float]:
        """B': same reads issued concurrently -- the optimised ceiling."""
        stmt = self.session.prepare(
            "SELECT run_id, column, row, value, sut_timestamp "
            "FROM generic_result_data_v1 WHERE test_id = ? AND name = ?"
        )
        started = time.monotonic()
        results = execute_concurrent_with_args(
            self.session, stmt, [(tid, BENCH_TABLE_NAME) for tid in test_ids], concurrency=32, results_generator=True
        )
        count = 0
        for ok, rows in results:
            if ok:
                count += sum(1 for c in rows if c["column"] == TARGET_COLUMN)
        return count, time.monotonic() - started

    def strategy_denorm(self, months: int) -> tuple[int, float]:
        """C: bounded single-partition reads on the denormalized table."""
        now = datetime.now(UTC)
        buckets = sorted({bucket_of(now - timedelta(days=30 * m)) for m in range(months + 1)})
        stmt = self.session.prepare(
            f"SELECT test_id, run_id, row, value, sut_timestamp FROM {DENORM_TABLE} "
            "WHERE column = ? AND time_bucket IN ?"
        )
        stmt.fetch_size = 5000
        started = time.monotonic()
        count = sum(1 for _ in self.session.execute(stmt, (TARGET_COLUMN, buckets)))
        return count, time.monotonic() - started

    # ----------------------------------------------------------------- report

    def scanned_rows(self) -> dict:
        """Rows each strategy must read to answer the same question.  Unlike
        wall time this is independent of node count and cluster size, so it is
        the part of a single-node measurement that stays meaningful."""
        total = self.session.execute(
            SimpleStatement("SELECT COUNT(*) AS c FROM generic_result_data_v1", fetch_size=5000)
        ).one()["c"]
        count_stmt = self.session.prepare("SELECT COUNT(*) AS c FROM generic_result_data_v1 WHERE column = ?")
        target = self.session.execute(count_stmt, (TARGET_COLUMN,)).one()["c"]
        return {"rows_in_table": total, "rows_matching_target": target}

    def run(self, repeats: int, months: int) -> None:
        test_ids = self.bench_test_ids()
        if not test_ids:
            LOGGER.error("no benchmark data found -- run `seed` first")
            return

        counts = self.scanned_rows()
        LOGGER.info(
            "table holds %d rows; column %r matches %d of them across %d tests",
            counts["rows_in_table"],
            TARGET_COLUMN,
            counts["rows_matching_target"],
            len(test_ids),
        )

        strategies = {
            "A index": self.strategy_index,
            "B fanout serial": lambda: self.strategy_fanout_serial(test_ids),
            "B' fanout concurrent": lambda: self.strategy_fanout_concurrent(test_ids),
            "C denorm": lambda: self.strategy_denorm(months),
        }

        print(flush=True)
        print(f"{'strategy':<24} {'rows':>10} {'median':>10} {'min':>10} {'max':>10}", flush=True)
        print("-" * 68, flush=True)
        for name, fn in strategies.items():
            timings, rows = [], 0
            for _ in range(repeats):
                rows, elapsed = fn()
                timings.append(elapsed)
            print(
                f"{name:<24} {rows:>10} {statistics.median(timings):>9.3f}s "
                f"{min(timings):>9.3f}s {max(timings):>9.3f}s",
                flush=True,
            )
        print(flush=True)
        print(
            f"rows in table: {counts['rows_in_table']}   "
            f"rows matching {TARGET_COLUMN}: {counts['rows_matching_target']}",
            flush=True,
        )

    def trace(self, months: int) -> None:
        """Report how many distinct nodes each strategy's first page touches.

        This is the number that decides A vs C and the one a single-node
        cluster cannot produce.  A single-partition read (C) should contact one
        replica set; a secondary-index read (A) contacts every node holding a
        slice of the index, so on an N-node cluster its cost grows with N even
        though the row count is identical.  Only the first page is traced --
        that is enough to tell a local read from a scatter.
        """
        test_ids = self.bench_test_ids()
        now = datetime.now(UTC)
        buckets = sorted({bucket_of(now - timedelta(days=30 * m)) for m in range(months + 1)})

        probes = {
            "A index": (
                "SELECT test_id, run_id, row, value FROM generic_result_data_v1 WHERE column = ?",
                (TARGET_COLUMN,),
            ),
            "B fanout (one test)": (
                "SELECT run_id, column, row, value FROM generic_result_data_v1 WHERE test_id = ? AND name = ?",
                (test_ids[0], BENCH_TABLE_NAME),
            ),
            "C denorm": (
                f"SELECT test_id, run_id, row, value FROM {DENORM_TABLE} WHERE column = ? AND time_bucket IN ?",
                (TARGET_COLUMN, buckets),
            ),
        }

        print(flush=True)
        print(f"{'strategy':<24} {'nodes/page':>11} {'trace events':>13}  sources", flush=True)
        print("-" * 78, flush=True)
        for name, (cql, params) in probes.items():
            stmt = self.session.prepare(cql)
            stmt.fetch_size = 5000
            result = self.session.execute(stmt, params, trace=True)
            _ = result.current_rows  # force the first page
            try:
                events = result.get_query_trace(max_wait_sec=20).events
            except (TraceUnavailable, OperationTimedOut) as exc:
                print(f"{name:<24} {'n/a':>11} {'-':>13}  ({exc})", flush=True)
                continue
            sources = sorted({str(e.source) for e in events})
            print(f"{name:<24} {len(sources):>11} {len(events):>13}  {', '.join(sources)}", flush=True)

    def drop(self) -> None:
        """Remove benchmark rows and the denormalized table."""
        test_ids = self.bench_test_ids()
        delete = self.session.prepare("DELETE FROM generic_result_data_v1 WHERE test_id = ? AND name = ?")
        for test_id in test_ids:
            self.session.execute(delete, (test_id, BENCH_TABLE_NAME))
        self.session.execute(f"DROP TABLE IF EXISTS {self.keyspace}.{DENORM_TABLE}")
        LOGGER.info("dropped benchmark data for %d tests", len(test_ids))


SWEEP = [
    # tests, runs, columns, rows  -> cells
    (10, 10, 10, 5),  # 5k
    (25, 25, 10, 5),  # 31k
    (50, 50, 10, 5),  # 125k
    (100, 50, 20, 10),  # 1M
]


def main() -> None:
    conn = argparse.ArgumentParser(add_help=False)
    conn.add_argument(
        "--contact-points",
        nargs="+",
        help="target an arbitrary cluster instead of the dev DB from "
        "argus_web.yaml; required to measure replica fan-out",
    )
    conn.add_argument("--port", type=int, default=9042)
    conn.add_argument("--keyspace", default="argus_bench")
    conn.add_argument("--username", default="cassandra")
    conn.add_argument("--password", default="cassandra")
    conn.add_argument("--rf", type=int, default=3, help="replication factor when creating the keyspace")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_seed = sub.add_parser("seed", parents=[conn], help="generate benchmark data")
    p_seed.add_argument("--tests", type=int, default=50)
    p_seed.add_argument("--runs", type=int, default=50)
    p_seed.add_argument("--columns", type=int, default=20)
    p_seed.add_argument("--rows", type=int, default=10)
    p_seed.add_argument("--months", type=int, default=6)

    p_bench = sub.add_parser("bench", parents=[conn], help="benchmark the strategies")
    p_bench.add_argument("--repeats", type=int, default=5)
    p_bench.add_argument("--months", type=int, default=6)

    p_sweep = sub.add_parser("sweep", parents=[conn], help="seed+bench at several scales")
    p_sweep.add_argument("--repeats", type=int, default=3)
    p_sweep.add_argument("--months", type=int, default=6)

    p_trace = sub.add_parser("trace", parents=[conn], help="report per-page node fan-out for each strategy")
    p_trace.add_argument("--months", type=int, default=6)

    sub.add_parser("drop", parents=[conn], help="remove benchmark data")

    args = parser.parse_args()
    if args.contact_points:
        session, keyspace = connect_external(
            args.contact_points, args.port, args.keyspace, args.username, args.password, args.rf
        )
        bench = Bench(session=session, keyspace=keyspace)
    else:
        bench = Bench()

    if args.cmd == "seed":
        bench.seed(args.tests, args.runs, args.columns, args.rows, args.months)
    elif args.cmd == "bench":
        bench.run(args.repeats, args.months)
    elif args.cmd == "trace":
        bench.trace(args.months)
    elif args.cmd == "drop":
        bench.drop()
    elif args.cmd == "sweep":
        for tests, runs, columns, rows in SWEEP:
            cells = tests * runs * columns * rows
            print(
                f"\n{'=' * 68}\nSCALE: {tests} tests x {runs} runs x {columns} cols "
                f"x {rows} rows = {cells} cells\n{'=' * 68}",
                flush=True,
            )
            bench.drop()
            bench.seed(tests, runs, columns, rows, args.months)
            bench.run(args.repeats, args.months)


if __name__ == "__main__":
    main()
