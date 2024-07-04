import json
from pathlib import Path

from argus.backend.models.web import ArgusRelease
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.db import ScyllaCluster
from argus.backend.util.encoders import ArgusJSONEncoder
db = ScyllaCluster.get()

release = ArgusRelease.get(name="enterprise-2023.1") # change name here
total = db.session.execute(f"SELECT count(build_id) FROM sct_test_run WHERE release_id = {release.id}").one()["system.count(build_id)"]
idx = 0
for run in SCTTestRun.filter(release_id=release.id).all():
    idx += 1
    with Path(f"./dev-db/sample_data/{run.id}.json").open(mode="wt", encoding="utf-8") as dst:
        print(f"Saving {run.id} [{idx}/{total}]")
        json.dump(run, dst, cls=ArgusJSONEncoder)
