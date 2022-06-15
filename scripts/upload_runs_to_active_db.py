import logging
import glob

from pathlib import Path
from argus.backend.db import ScyllaCluster
from argus.db.testrun import TestRun

logging.basicConfig()
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.DEBUG)

LOAD_DIR = Path("./migration/latest")
DB = ScyllaCluster.get()

if not LOAD_DIR.exists():
    exit(1)

ALL_RUNS = glob.glob(f"{LOAD_DIR.absolute()}/*.json")
TOTAL_RUNS = len(ALL_RUNS)
LOAD_STMT = DB.prepare(f"INSERT INTO {TestRun.table_name()} JSON ?")
EXISTING_ROWS = list(DB.session.execute(f"SELECT id FROM {TestRun.table_name()}").all())

if len(EXISTING_ROWS) > 0:
    LOGGER.error("Found rows in the TestRun table, please truncate it manually")
    exit(1)

for idx, filepath in enumerate(ALL_RUNS):
    LOGGER.info("[%s/%s] Loading %s...", idx+1, TOTAL_RUNS, filepath)
    f = open(filepath, "rt", encoding="utf-8")
    content = f.read()
    try:
        DB.session.execute(LOAD_STMT, parameters=(content,))
    except Exception as e:
        LOGGER.error("[%s] Failed to load! JSON: %s", e.args[0], content)
