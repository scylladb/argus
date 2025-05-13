import json
from pathlib import Path
from collections import defaultdict

from argus.backend.models.web import ArgusRelease, ArgusTest, ArgusGroup
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.db import ScyllaCluster
from argus.backend.util.encoders import ArgusJSONEncoder
from argus.backend.models.result import (
    ArgusGenericResultMetadata,
    ArgusGenericResultData,
    ArgusBestResultData,
    ArgusGraphView,
)

db = ScyllaCluster.get()

release_name = "scylla-enterprise"  # change name here
dest = Path(__file__).parent / "sample_data" / release_name
dest.mkdir(parents=True, exist_ok=True)
release = ArgusRelease.get(name=release_name)
print(f"Saving release {release.id}")
(dest / "release.json").write_text(json.dumps(release, cls=ArgusJSONEncoder))

print("getting groups data")
for group in ArgusGroup.filter(release_id=release.id).all():
    print(f"Saving group {group.id}")
    (dest / f"group_{group.id}.json").write_text(json.dumps(group, cls=ArgusJSONEncoder))

print("getting test data")
for test in ArgusTest.filter(release_id=release.id).all():
    print(f"Saving test {test.id}")
    (dest / f"test_{test.id}.json").write_text(json.dumps(test, cls=ArgusJSONEncoder))

    # Export ArgusGenericResultMetadata for each test
    for metadata in ArgusGenericResultMetadata.filter(test_id=test.id).allow_filtering().all():
        print(f"Saving generic result metadata for test {test.id} and name {metadata.name}")
        (dest / f"generic_result_metadata_{test.id}_{metadata.name}.json").write_text(
            json.dumps(metadata, cls=ArgusJSONEncoder)
        )

    # Export ArgusGraphView for each test - group by test_id (partition key)
    graph_views_by_test = defaultdict(list)
    for graph_view in ArgusGraphView.filter(test_id=test.id).allow_filtering().all():
        graph_views_by_test[str(test.id)].append(graph_view)

    for test_id, views in graph_views_by_test.items():
        print(f"Saving graph views for test {test_id}")
        (dest / f"graph_view_{test_id}.json").write_text(json.dumps(views, cls=ArgusJSONEncoder))

    # Export ArgusBestResultData for each test - group by test_id and name (partition keys)
    best_results_by_partition = defaultdict(list)
    for best_result in ArgusBestResultData.filter(test_id=test.id).allow_filtering().all():
        partition_key = f"{test.id}_{best_result.name}"
        best_results_by_partition[partition_key].append(best_result)

    for partition_key, results in best_results_by_partition.items():
        print(f"Saving best results for partition {partition_key}")
        (dest / f"best_result_{partition_key}.json").write_text(json.dumps(results, cls=ArgusJSONEncoder))

print("getting runs data")
total = db.session.execute(f"SELECT count(build_id) FROM sct_test_run WHERE release_id = {release.id}").one()[
    "system.count(build_id)"
]
idx = 0
for run in SCTTestRun.filter(release_id=release.id).all():
    idx += 1
    print(f"Saving {run.id} [{idx}/{total}]")
    (dest / f"run_{run.id}.json").write_text(json.dumps(run, cls=ArgusJSONEncoder))

    # Export ArgusGenericResultData for each run - group by test_id and name (partition keys)
    result_data_by_partition = defaultdict(list)
    for result_data in ArgusGenericResultData.filter(run_id=run.id).allow_filtering().all():
        partition_key = f"{run.id}_{result_data.name}"
        result_data_by_partition[partition_key].append(result_data)

    for partition_key, results in result_data_by_partition.items():
        print(f"Saving generic result data for partition {partition_key}")
        (dest / f"generic_result_data_{partition_key}.json").write_text(json.dumps(results, cls=ArgusJSONEncoder))
