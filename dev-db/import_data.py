from pathlib import Path
import json

from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.db import ScyllaCluster

db = ScyllaCluster.get()

release_name = "perf-regression" # change name here
dest = Path(__file__).parent / "sample_data" / release_name

print('importing releases')
statement = db.prepare(f"INSERT INTO argus_release_v2 JSON ?")
with (dest / "release.json").open(mode="rt", encoding="utf-8") as src:
    release_raw = src.read()
    release = json.loads(release_raw)
    db.session.execute(statement, parameters=(release_raw,))
    print(f"Saved {release['id']}")

print('importing groups')
statement = db.prepare("INSERT INTO argus_group_v2 JSON ?")
for file in dest.glob("group_*.json"):
    with file.open(mode="rt", encoding="utf-8") as src:
        group_raw = src.read()
        group = json.loads(group_raw)
        db.session.execute(statement, parameters=(group_raw,))
        print(f"Saved {group['id']}")

print('importing tests')
statement = db.prepare("INSERT INTO argus_test_v2 JSON ?")
for file in dest.glob("test_*.json"):
    with file.open(mode="rt", encoding="utf-8") as src:
        job_raw = src.read()
        future_job = json.loads(job_raw)
        db.session.execute(statement, parameters=(job_raw,))
        print(f"Saved {future_job['id']}")

print("importing runs")
statement = db.prepare("INSERT INTO sct_test_run JSON ?")
for file in dest.glob("run_*.json"):
    with file.open(mode="rt", encoding="utf-8") as src:
        run_raw = src.read()
        future_row = json.loads(run_raw)
        db.session.execute(statement, parameters=(run_raw,))
        run: SCTTestRun = SCTTestRun.get(id=future_row["id"])
        run.assign_categories()
        run.save()
        print(f"Saved {run.id}")
