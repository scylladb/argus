import glob
from pathlib import Path
import json

from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.db import ScyllaCluster

db = ScyllaCluster.get()
for file in (Path(p) for p in glob.glob("./dev-db/sample_data/*.json")):
    with file.open(mode="rt", encoding="utf-8") as src:
        run_raw = src.read()
        future_row = json.loads(run_raw)
        db.session.execute(db.prepare("INSERT INTO sct_test_run JSON ?"), parameters=(run_raw,))
        run: SCTTestRun = SCTTestRun.get(id=future_row["id"])
        run.assign_categories()
        run.save()
        print(f"Saved {run.id}")
