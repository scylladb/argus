from pathlib import Path
import json

from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.db import ScyllaCluster
from argus.backend.util.config import Config

db = ScyllaCluster.get()
if "127.0.0.10" in Config.CONFIG.get("SCYLLA_CONTACT_POINTS"):
    raise Exception("This script should not be run on local DB!")

release_name = "scylla-enterprise"  # change name here
dest = Path(__file__).parent / "sample_data" / release_name

print("importing releases")
statement = db.prepare("INSERT INTO argus_release_v2 JSON ?")
with (dest / "release.json").open(mode="rt", encoding="utf-8") as src:
    release_raw = src.read()
    release = json.loads(release_raw)
    db.session.execute(statement, parameters=(release_raw,))
    print(f"Saved {release['id']}")

print("importing groups")
statement = db.prepare("INSERT INTO argus_group_v2 JSON ?")
for file in dest.glob("group_*.json"):
    with file.open(mode="rt", encoding="utf-8") as src:
        group_raw = src.read()
        group = json.loads(group_raw)
        db.session.execute(statement, parameters=(group_raw,))
        print(f"Saved {group['id']}")

print("importing tests")
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

print("importing generic result metadata")
statement = db.prepare("INSERT INTO generic_result_metadata_v1 JSON ?")
for file in dest.glob("generic_result_metadata_*.json"):
    with file.open(mode="rt", encoding="utf-8") as src:
        metadata_raw = src.read()
        metadata = json.loads(metadata_raw)
        db.session.execute(statement, parameters=(metadata_raw,))
        print(f"Saved metadata for test {metadata['test_id']} and name {metadata['name']}")

print("importing graph views")
statement = db.prepare("INSERT INTO graph_view_v1 JSON ?")
for file in dest.glob("graph_view_*.json"):
    with file.open(mode="rt", encoding="utf-8") as src:
        graph_views = json.loads(src.read())
        for graph_view in graph_views:
            graph_view_raw = json.dumps(graph_view)
            db.session.execute(statement, parameters=(graph_view_raw,))
            print(f"Saved graph view {graph_view['id']} for test {graph_view['test_id']}")

print("importing best results")
statement = db.prepare("INSERT INTO generic_result_best_v2 JSON ?")
for file in dest.glob("best_result_*.json"):
    with file.open(mode="rt", encoding="utf-8") as src:
        best_results = json.loads(src.read())
        for best_result in best_results:
            best_result_raw = json.dumps(best_result)
            db.session.execute(statement, parameters=(best_result_raw,))
            print(f"Saved best result for test {best_result['test_id']} and name {best_result['name']}")

print("importing generic result data")
statement = db.prepare("INSERT INTO generic_result_data_v1 JSON ?")
for file in dest.glob("generic_result_data_*.json"):
    with file.open(mode="rt", encoding="utf-8") as src:
        results = json.loads(src.read())
        for result_data in results:
            result_data_raw = json.dumps(result_data)
            db.session.execute(statement, parameters=(result_data_raw,))
            print(
                f"Saved generic result data for run {result_data['run_id']}, test {result_data['test_id']}, name {result_data['name']}"
            )
