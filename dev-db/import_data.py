import asyncio
from pathlib import Path
import json

from coodie.aio import execute_raw

from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.db import ScyllaCluster
from argus.backend.util.config import Config

release_name = "scylla-2025.4"  # change name here
dest = Path(__file__).parent / "sample_data" / release_name


async def insert_json(keyspace: str, table: str, payload: str):
    await execute_raw(f"INSERT INTO {keyspace}.{table} JSON ?", [payload])


async def import_releases(keyspace: str):
    print("importing releases")
    with (dest / "release.json").open(mode="rt", encoding="utf-8") as src:
        release_raw = src.read()
        release = json.loads(release_raw)
        await insert_json(keyspace, "argus_release_v2", release_raw)
        print(f"Saved {release['id']}")


async def import_groups(keyspace: str):
    print("importing groups")
    for file in dest.glob("group_*.json"):
        with file.open(mode="rt", encoding="utf-8") as src:
            group_raw = src.read()
            group = json.loads(group_raw)
            await insert_json(keyspace, "argus_group_v2", group_raw)
            print(f"Saved {group['id']}")


async def import_tests(keyspace: str):
    print("importing tests")
    for file in dest.glob("test_*.json"):
        with file.open(mode="rt", encoding="utf-8") as src:
            job_raw = src.read()
            future_job = json.loads(job_raw)
            await insert_json(keyspace, "argus_test_v2", job_raw)
            print(f"Saved {future_job['id']}")


async def import_runs(keyspace: str):
    print("importing runs")
    for file in dest.glob("run_*.json"):
        with file.open(mode="rt", encoding="utf-8") as src:
            run_raw = src.read()
            future_row = json.loads(run_raw)
            await insert_json(keyspace, "sct_test_run", run_raw)
            run: SCTTestRun = await SCTTestRun.get(id=future_row["id"])
            await run.assign_categories()
            await run.save()
            print(f"Saved {run.id}")


async def import_generic_result_metadata(keyspace: str):
    print("importing generic result metadata")
    for file in dest.glob("generic_result_metadata_*.json"):
        with file.open(mode="rt", encoding="utf-8") as src:
            metadata_raw = src.read()
            metadata = json.loads(metadata_raw)
            await insert_json(keyspace, "generic_result_metadata_v1", metadata_raw)
            print(f"Saved metadata for test {metadata['test_id']} and name {metadata['name']}")


async def import_graph_views(keyspace: str):
    print("importing graph views")
    for file in dest.glob("graph_view_*.json"):
        with file.open(mode="rt", encoding="utf-8") as src:
            graph_views = json.loads(src.read())
            for graph_view in graph_views:
                await insert_json(keyspace, "graph_view_v1", json.dumps(graph_view))
                print(f"Saved graph view {graph_view['id']} for test {graph_view['test_id']}")


async def import_best_results(keyspace: str):
    print("importing best results")
    for file in dest.glob("best_result_*.json"):
        with file.open(mode="rt", encoding="utf-8") as src:
            best_results = json.loads(src.read())
            for best_result in best_results:
                await insert_json(keyspace, "generic_result_best_v2", json.dumps(best_result))
                print(f"Saved best result for test {best_result['test_id']} and name {best_result['name']}")


async def import_generic_result_data(keyspace: str):
    print("importing generic result data")
    for file in dest.glob("generic_result_data_*.json"):
        with file.open(mode="rt", encoding="utf-8") as src:
            results = json.loads(src.read())
            for result_data in results:
                await insert_json(keyspace, "generic_result_data_v1", json.dumps(result_data))
                print(
                    f"Saved generic result data for run {result_data['run_id']}, test {result_data['test_id']}, name {result_data['name']}"
                )


async def import_sct_events(keyspace: str):
    print("importing SCT events")
    for file in dest.glob("sct_event_*.json"):
        with file.open(mode="rt", encoding="utf-8") as src:
            events = json.loads(src.read())
            for event in events:
                await insert_json(keyspace, "sct_event", json.dumps(event))
            run_id = file.stem.replace("sct_event_", "")
            print(f"Saved {len(events)} SCT events for run {run_id}")


async def import_issue_links(keyspace: str):
    print("importing issue links")
    for file in dest.glob("issue_link_*.json"):
        with file.open(mode="rt", encoding="utf-8") as src:
            issue_links = json.loads(src.read())
            for issue_link in issue_links:
                await insert_json(keyspace, "issue_link", json.dumps(issue_link))
            run_id = file.stem.replace("issue_link_", "")
            print(f"Saved {len(issue_links)} issue links for run {run_id}")


async def import_github_issues(keyspace: str):
    print("importing GitHub issues (full table)")
    github_issues_file = dest / "github_issues.json"
    if github_issues_file.exists():
        with github_issues_file.open(mode="rt", encoding="utf-8") as src:
            github_issues = json.loads(src.read())
            for github_issue in github_issues:
                await insert_json(keyspace, "github_issue", json.dumps(github_issue))
            print(f"Saved {len(github_issues)} GitHub issues")


async def main():
    keyspace = ScyllaCluster.get().config["SCYLLA_KEYSPACE_NAME"]
    if "127.0.0.10" in Config.CONFIG.get("SCYLLA_CONTACT_POINTS"):
        raise Exception("This script should not be run on local DB!")

    await import_releases(keyspace)
    await import_groups(keyspace)
    await import_tests(keyspace)
    await import_runs(keyspace)
    await import_generic_result_metadata(keyspace)
    await import_graph_views(keyspace)
    await import_best_results(keyspace)
    await import_generic_result_data(keyspace)
    await import_sct_events(keyspace)
    await import_issue_links(keyspace)
    await import_github_issues(keyspace)


if __name__ == "__main__":
    asyncio.run(main())
