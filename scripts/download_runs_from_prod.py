import os
import json
import logging

from pathlib import Path
from time import time
from argus.db.argus_json import ArgusJSONEncoder
from argus.db.testrun import TestRun
from argus.db.interface import ArgusDatabase
from argus.db.config import FileConfig

logging.basicConfig()
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.DEBUG)

SAVE_DIR = Path(f"./migration/{TestRun.table_name()}-{int(time())}")
PROD_INTERFACE = ArgusDatabase(FileConfig("./argus.local.prod.yaml"))

ALL_ROWS = list(PROD_INTERFACE.session.execute("SELECT id FROM test_runs_v7").all())
TestRun.set_argus(PROD_INTERFACE)

if not (p := Path("./migration")).exists():
    os.mkdir(p.absolute())

if Path("./migration/latest").exists():
    os.unlink("./migration/latest")

os.mkdir(SAVE_DIR.absolute())
os.symlink(SAVE_DIR.absolute(), "./migration/latest", target_is_directory=True)

total_rows = len(ALL_ROWS)
print(f"Total rows fetched: {total_rows}")
for idx, row in enumerate(ALL_ROWS):
    LOGGER.info(f"[%s/%s] Processing id:%s", idx+1, total_rows, row["id"])
    tr = TestRun.from_id(row["id"])
    with open(SAVE_DIR / f"{row['id']}.json", "wt") as f:
        json.dump(tr.serialize(), f, cls=ArgusJSONEncoder)
