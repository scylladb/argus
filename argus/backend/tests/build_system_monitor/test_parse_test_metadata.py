import pytest

from argus.backend.models.web import ArgusTest
from argus.backend.service.test_metadata import apply_test_metadata, parse_test_metadata

REAL_DESCRIPTION = """jenkins-pipelines/oss/longevity/longevity-10gb-3h.jenkinsfile

Basic longevity test running cassandra-stress write workload at QUORUM consistency for ~4 hours on a 6-node single-DC cluster with SisyphusMonkey nemesis. Validates cluster stability under moderate write load with continuous chaos operations.

### TestMetadata
tier: tier1
test_type: longevity
duration_class: short
supported_backends: ['aws', 'gce', 'azure']
"""

PARAMETER_FIRST_LINE_DESCRIPTION = """test: longevity_test.LongevityTest.test_custom_time | backend: aws | region: eu-west-1

Runs a custom time longevity against a single datacenter.

### TestMetadata
tier: tier2
"""


def test_parses_every_key_and_the_prose_from_a_real_description():
    assert parse_test_metadata(REAL_DESCRIPTION) == {
        "description": (
            "Basic longevity test running cassandra-stress write workload at QUORUM consistency "
            "for ~4 hours on a 6-node single-DC cluster with SisyphusMonkey nemesis. Validates "
            "cluster stability under moderate write load with continuous chaos operations."
        ),
        "tier": "tier1",
        "test_type": "longevity",
        "duration_class": "short",
        "supported_backends": '["aws", "gce", "azure"]',
    }


def test_takes_the_prose_when_the_first_line_is_a_parameter_line():
    parsed = parse_test_metadata(PARAMETER_FIRST_LINE_DESCRIPTION)

    assert parsed["description"] == "Runs a custom time longevity against a single datacenter."
    assert parsed["tier"] == "tier2"


def test_returns_none_when_the_heading_is_absent():
    assert parse_test_metadata("Just a job description with no block.") is None


@pytest.mark.parametrize("description", [None, "", "   \n\n  "])
def test_returns_none_for_an_empty_description(description):
    assert parse_test_metadata(description) is None


def test_returns_none_when_the_block_holds_neither_a_pair_nor_prose():
    assert parse_test_metadata("### TestMetadata\n") is None


def test_skips_the_blank_line_between_the_heading_and_the_first_pair():
    assert parse_test_metadata("### TestMetadata\n\ntier: tier1\n") == {"tier": "tier1"}


def test_keeps_a_key_it_has_never_seen():
    parsed = parse_test_metadata("### TestMetadata\ntier: tier1\nowner_team: sct\n")

    assert parsed == {"tier": "tier1", "owner_team": "sct"}


def test_keeps_the_keys_whatever_their_order():
    parsed = parse_test_metadata("### TestMetadata\ntest_type: longevity\ntier: tier1\n")

    assert parsed == {"tier": "tier1", "test_type": "longevity"}


def test_ends_the_block_at_the_first_line_that_is_not_a_pair():
    parsed = parse_test_metadata("### TestMetadata\ntier: tier1\n-- not a pair --\nduration_class: short\n")

    assert parsed == {"tier": "tier1"}


def test_leaves_the_prose_that_follows_the_block_out_of_the_map():
    parsed = parse_test_metadata("### TestMetadata\ntier: tier1\n\nNote: run this with care.\n")

    assert parsed == {"tier": "tier1"}


def test_reads_a_description_with_crlf_line_endings():
    parsed = parse_test_metadata(REAL_DESCRIPTION.replace("\n", "\r\n"))

    assert parsed["tier"] == "tier1"
    assert parsed["supported_backends"] == '["aws", "gce", "azure"]'
    assert parsed["description"].endswith("continuous chaos operations.")


def test_stores_a_list_literal_as_a_json_array_string():
    parsed = parse_test_metadata("### TestMetadata\nsupported_backends: ['aws', 'gce']\n")

    assert parsed["supported_backends"] == '["aws", "gce"]'


def test_stores_a_double_quoted_list_literal_as_a_json_array_string():
    parsed = parse_test_metadata('### TestMetadata\nsupported_backends: ["aws", "gce"]\n')

    assert parsed["supported_backends"] == '["aws", "gce"]'


def test_stores_an_empty_list_literal_as_an_empty_json_array_string():
    assert parse_test_metadata("### TestMetadata\nsupported_backends: []\n")["supported_backends"] == "[]"


def test_falls_back_to_the_raw_string_for_a_malformed_list():
    parsed = parse_test_metadata("### TestMetadata\nsupported_backends: ['aws', 'gce'\n")

    assert parsed["supported_backends"] == "['aws', 'gce'"


def test_keeps_the_tail_of_a_value_that_holds_a_colon():
    parsed = parse_test_metadata("### TestMetadata\ndocs_url: https://example.invalid/a:b\n")

    assert parsed["docs_url"] == "https://example.invalid/a:b"


def test_keeps_a_value_that_holds_a_comma():
    parsed = parse_test_metadata("### TestMetadata\nnotes: runs on aws, then on gce\n")

    assert parsed["notes"] == "runs on aws, then on gce"


def test_takes_the_last_value_of_a_duplicate_key():
    assert parse_test_metadata("### TestMetadata\ntier: tier1\ntier: tier2\n")["tier"] == "tier2"


def test_keeps_a_key_whose_value_is_empty():
    assert parse_test_metadata("### TestMetadata\ntier:\n") == {"tier": ""}


def test_matches_the_heading_whatever_its_level_and_case():
    assert parse_test_metadata("# testmetadata\ntier: tier1\n") == {"tier": "tier1"}


def test_takes_the_first_heading_when_it_occurs_twice():
    parsed = parse_test_metadata("### TestMetadata\ntier: tier1\n\n### TestMetadata\ntier: tier2\n")

    assert parsed["tier"] == "tier1"


def test_omits_the_description_when_the_only_prose_is_a_jenkinsfile_path():
    parsed = parse_test_metadata("pipelines/longevity/longevity-10gb-3h.jenkinsfile\n\n### TestMetadata\ntier: tier1\n")

    assert parsed == {"tier": "tier1"}


def test_every_value_is_a_string():
    parsed = parse_test_metadata(REAL_DESCRIPTION)

    assert all(isinstance(value, str) for value in parsed.values())


def test_apply_returns_true_and_assigns_when_the_map_changes():
    test = ArgusTest.model_construct()

    assert apply_test_metadata(test, REAL_DESCRIPTION) is True
    assert test.test_metadata["tier"] == "tier1"


def test_apply_returns_false_when_the_map_is_unchanged():
    test = ArgusTest.model_construct()
    apply_test_metadata(test, REAL_DESCRIPTION)

    assert apply_test_metadata(test, REAL_DESCRIPTION) is False


def test_apply_keeps_the_stored_map_when_the_description_has_no_block():
    test = ArgusTest.model_construct()
    apply_test_metadata(test, REAL_DESCRIPTION)

    assert apply_test_metadata(test, "A description with no block at all.") is False
    assert test.test_metadata["tier"] == "tier1"


REAL_JENKINS_DESCRIPTION = (
    "jenkins-pipelines/oss/tier1/gemini-1tb-10h.jenkinsfile\n"
    "\n"
    "Large-scale Gemini fuzz test comparing a 6-node mixed Scylla/oracle cluster against a 1TB "
    "dataset, running ~8h of active Gemini stress with a large IO-worker pool and SisyphusMonkey "
    "nemesis (excluding ENOSPC and node-isolation disruptions), to validate data consistency under "
    "sustained mixed load and chaos at scale.\n"
    "\n"
    "### TestMetadata\n"
    "tier: tier1\n"
    "test_type: gemini\n"
    "duration_class: medium\n"
    "supported_backends: ['aws']"
)

JOB_DEFINITIONS_DESCRIPTION = """Runs the nightly longevity suite.

### JobDefinitions
folder-description: Cluster - Tier1 Longevities
job-name: longevity

Basic longevity test running cassandra-stress.

### TestMetadata
tier: tier1
duration_class: n/a
supported_backends: []
"""


def test_reads_a_description_a_jenkins_job_carries_today():
    assert parse_test_metadata(REAL_JENKINS_DESCRIPTION) == {
        "tier": "tier1",
        "test_type": "gemini",
        "duration_class": "medium",
        "supported_backends": '["aws"]',
        "description": (
            "Large-scale Gemini fuzz test comparing a 6-node mixed Scylla/oracle cluster against a "
            "1TB dataset, running ~8h of active Gemini stress with a large IO-worker pool and "
            "SisyphusMonkey nemesis (excluding ENOSPC and node-isolation disruptions), to validate "
            "data consistency under sustained mixed load and chaos at scale."
        ),
    }


def test_takes_the_prose_below_a_job_definitions_block():
    parsed = parse_test_metadata(JOB_DEFINITIONS_DESCRIPTION)

    assert parsed["description"] == "Basic longevity test running cassandra-stress."
    assert parsed["duration_class"] == "n/a"
    assert parsed["supported_backends"] == "[]"


def test_reads_a_block_whose_pairs_are_indented():
    parsed = parse_test_metadata("### TestMetadata\n  tier: tier1\n  test_type: longevity\n")

    assert parsed == {"tier": "tier1", "test_type": "longevity"}
