from pathlib import Path
import json

from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.db import ScyllaCluster
from argus.backend.util.config import Config

db = ScyllaCluster.get()
if "127.0.0.10" in Config.CONFIG.get("SCYLLA_CONTACT_POINTS"):
    raise Exception("This script should not be run on local DB!")

release_name = "scylla-2025.4"  # change name here
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

print("importing SCT events")
statement = db.prepare("INSERT INTO sct_event JSON ?")
for file in dest.glob("sct_event_*.json"):
    with file.open(mode="rt", encoding="utf-8") as src:
        events = json.loads(src.read())
        for event in events:
            event_raw = json.dumps(event)
            db.session.execute(statement, parameters=(event_raw,))
        run_id = file.stem.replace("sct_event_", "")
        print(f"Saved {len(events)} SCT events for run {run_id}")

print("importing issue links")
statement = db.prepare("INSERT INTO issue_link JSON ?")
for file in dest.glob("issue_link_*.json"):
    with file.open(mode="rt", encoding="utf-8") as src:
        issue_links = json.loads(src.read())
        for issue_link in issue_links:
            issue_link_raw = json.dumps(issue_link)
            db.session.execute(statement, parameters=(issue_link_raw,))
        run_id = file.stem.replace("issue_link_", "")
        print(f"Saved {len(issue_links)} issue links for run {run_id}")

print("importing GitHub issues (full table)")
github_issues_file = dest / "github_issues.json"
if github_issues_file.exists():
    statement = db.prepare("INSERT INTO github_issue JSON ?")
    with github_issues_file.open(mode="rt", encoding="utf-8") as src:
        github_issues = json.loads(src.read())
        for github_issue in github_issues:
            github_issue_raw = json.dumps(github_issue)
            db.session.execute(statement, parameters=(github_issue_raw,))
        print(f"Saved {len(github_issues)} GitHub issues")
