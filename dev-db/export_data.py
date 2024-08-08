import json
from pathlib import Path

from argus.backend.models.web import ArgusRelease, ArgusTest, ArgusGroup
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.db import ScyllaCluster
from argus.backend.util.encoders import ArgusJSONEncoder
db = ScyllaCluster.get()

release_name = "perf-regression" # change name here
dest = Path(__file__).parent / "sample_data" / release_name
dest.mkdir(parents=True, exist_ok=True)
release = ArgusRelease.get(name=release_name)
print(f"Saving release {release.id}")
(dest / "release.json").write_text(json.dumps(release, cls=ArgusJSONEncoder))

print('getting groups data')
for group in ArgusGroup.filter(release_id=release.id).all():
    print(f"Saving group {group.id}")
    (dest / f"group_{group.id}.json").write_text(json.dumps(group, cls=ArgusJSONEncoder))

print('getting test data')
for test in ArgusTest.filter(release_id=release.id).all():
    print(f"Saving test {test.id}")
    (dest / f"test_{test.id}.json").write_text(json.dumps(test, cls=ArgusJSONEncoder))

print('getting runs data')
total = db.session.execute(f"SELECT count(build_id) FROM sct_test_run WHERE release_id = {release.id}").one()["system.count(build_id)"]
idx = 0
for run in SCTTestRun.filter(release_id=release.id).all():
    idx += 1
    print(f"Saving {run.id} [{idx}/{total}]")
    (dest / f"run_{run.id}.json").write_text(json.dumps(run, cls=ArgusJSONEncoder))
