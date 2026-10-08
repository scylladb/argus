from uuid import uuid4

from argus.backend.service import test_lookup as lookup


def test_quoted_facet_value_keeps_its_spaces_without_the_quotes():
    parsed = lookup.parse_query('release:"scylla 5.4"')

    assert parsed.facets == {"release": ("scylla 5.4",)}
    assert parsed.terms == ()


def test_facet_value_keeps_a_slash():
    parsed = lookup.parse_query("release:scylla-2025.1/releng-testing")

    assert parsed.facets == {"release": ("scylla-2025.1/releng-testing",)}


def test_words_become_separate_terms():
    parsed = lookup.parse_query("longevity 50gb")

    assert parsed.terms == ("longevity", "50gb")


def test_leading_dash_excludes_a_term():
    parsed = lookup.parse_query("longevity -azure")

    assert parsed.terms == ("longevity",)
    assert parsed.excluded_terms == ("azure",)


def test_leading_dash_excludes_a_facet():
    parsed = lookup.parse_query("-type:group")

    assert parsed.excluded_facets == {"type": ("group",)}
    assert parsed.facets == {}


def test_tokens_made_of_dashes_are_plain_terms():
    parsed = lookup.parse_query("-- root directory --")

    assert parsed.terms == ("--", "root", "directory")
    assert parsed.excluded_terms == ()


def test_quoted_phrase_starting_with_a_dash_is_a_plain_term():
    parsed = lookup.parse_query('"-- root directory --"')

    assert parsed.terms == ("-- root directory --",)
    assert parsed.excluded_terms == ()


def test_repeated_facet_collects_every_value():
    parsed = lookup.parse_query("release:scylla-master release:scylla-staging group:longevity")

    assert parsed.facets == {"release": ("scylla-master", "scylla-staging"), "group": ("longevity",)}


def test_unknown_key_value_stays_a_term():
    parsed = lookup.parse_query("backend:aws")

    assert parsed.terms == ("backend:aws",)
    assert parsed.facets == {}


def test_terms_and_facet_values_are_lowercased():
    parsed = lookup.parse_query("Longevity release:Scylla-Master")

    assert parsed.terms == ("longevity",)
    assert parsed.facets == {"release": ("scylla-master",)}


def test_jenkins_url_becomes_its_job_path():
    parsed = lookup.parse_query(
        "https://jenkins.scylladb.com/job/scylla-master/job/longevity/job/longevity-50gb-3days-test/42/")

    assert parsed.terms == ("scylla-master/longevity/longevity-50gb-3days-test",)


def test_single_uuid_query_sets_uuid():
    entity_id = uuid4()

    parsed = lookup.parse_query(f" {entity_id} ")

    assert parsed.uuid == entity_id


def test_uuid_among_other_words_is_a_term():
    entity_id = uuid4()

    parsed = lookup.parse_query(f"{entity_id} longevity")

    assert parsed.uuid is None
    assert parsed.terms == (str(entity_id), "longevity")


def test_unbalanced_quote_runs_to_the_end_of_the_query():
    parsed = lookup.parse_query('longevity release:"scylla 5.4')

    assert parsed.terms == ("longevity",)
    assert parsed.facets == {"release": ("scylla 5.4",)}


def test_regex_characters_are_plain_text():
    parsed = lookup.parse_query("longevity.*[")

    assert parsed.terms == ("longevity.*[",)


def test_status_is_a_facet():
    parsed = lookup.parse_query("longevity status:failed -status:passed")

    assert parsed.terms == ("longevity",)
    assert parsed.facets == {"status": ("failed",)}
    assert parsed.excluded_facets == {"status": ("passed",)}


def test_investigation_status_and_assignee_are_facets():
    parsed = lookup.parse_query("istatus:not assignee:alice")

    assert parsed.facets == {"istatus": ("not",), "assignee": ("alice",)}


def test_issue_key_is_taken_from_the_issue_facet():
    parsed = lookup.parse_query("longevity issue:SCT-717 status:failed")

    assert parsed.issue_keys == ("sct-717",)
    assert "issue" not in parsed.facets


def test_excluded_issue_key_is_ignored():
    parsed = lookup.parse_query("longevity -issue:SCT-717")

    assert parsed.issue_keys == ()
    assert parsed.excluded_facets == {}


def test_config_facet_keeps_the_case_of_its_name_and_value():
    parsed = lookup.parse_query("longevity config:sct_config.Region=US-East")

    assert parsed.configs == (("sct_config.Region", "US-East"),)
    assert "config" not in parsed.facets


def test_config_facet_without_a_value_asks_for_the_parameter_to_be_set():
    assert lookup.parse_query("config:backend").configs == (("backend", None),)
    assert lookup.parse_query("config:backend=").configs == (("backend", None),)


def test_config_facet_value_keeps_spaces_in_quotes_and_later_equal_signs():
    assert lookup.parse_query('config:name="a b"').configs == (("name", "a b"),)
    assert lookup.parse_query("config:args=--x=1").configs == (("args", "--x=1"),)


def test_excluded_config_facet_is_ignored():
    assert lookup.parse_query("-config:backend=aws").configs == ()


def test_config_name_resolves_exactly_or_by_a_unique_dotted_suffix():
    names = ["sct_config.backend", "sct_config.backup_bucket_backend", "a.region", "b.region"]

    assert lookup._resolve_param_name("sct_config.backend", names) == "sct_config.backend"
    assert lookup._resolve_param_name("backend", names) == "sct_config.backend"
    assert lookup._resolve_param_name("region", names) is None
    assert lookup._resolve_param_name("missing", names) is None


def test_a_negated_uuid_is_an_exclusion_not_a_lookup():
    entity_id = uuid4()

    parsed = lookup.parse_query(f"-{str(entity_id).upper()}")

    assert parsed.uuid is None
    assert parsed.excluded_terms == (str(entity_id),)


def test_repeated_issue_keys_are_all_kept():
    assert lookup.parse_query("issue:SCT-1 issue:SCT-2").issue_keys == ("sct-1", "sct-2")
