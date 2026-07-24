import xml.etree.ElementTree as ET

import jenkins
import pytest

from argus.backend.error_handlers import DataValidationError
from argus.backend.service.jenkins_service import JenkinsService


CONFIG_WITH_CHOICES = """<?xml version='1.1' encoding='UTF-8'?>
<flow-definition plugin="workflow-job">
  <properties>
    <hudson.model.ParametersDefinitionProperty>
      <parameterDefinitions>
        <hudson.model.ChoiceParameterDefinition>
          <name>billing_project</name>
          <description>GCP billing project</description>
          <choices class="java.util.Arrays$ArrayList">
            <a class="string-array">
              <string>sct</string>
              <string>qa</string>
              <string>perf</string>
            </a>
          </choices>
        </hudson.model.ChoiceParameterDefinition>
        <hudson.model.StringParameterDefinition>
          <name>scylla_version</name>
          <description>Scylla version</description>
          <defaultValue>master:latest</defaultValue>
        </hudson.model.StringParameterDefinition>
      </parameterDefinitions>
    </hudson.model.ParametersDefinitionProperty>
  </properties>
</flow-definition>
"""

CONFIG_FLAT_CHOICES = """<?xml version='1.1' encoding='UTF-8'?>
<flow-definition>
  <properties>
    <hudson.model.ParametersDefinitionProperty>
      <parameterDefinitions>
        <hudson.model.ChoiceParameterDefinition>
          <name>billing_project</name>
          <choices>
            <string>sct</string>
            <string>qa</string>
          </choices>
        </hudson.model.ChoiceParameterDefinition>
      </parameterDefinitions>
    </hudson.model.ParametersDefinitionProperty>
  </properties>
</flow-definition>
"""

CONFIG_NO_CHOICES = """<?xml version='1.1' encoding='UTF-8'?>
<flow-definition>
  <properties>
    <hudson.model.ParametersDefinitionProperty>
      <parameterDefinitions>
        <hudson.model.StringParameterDefinition>
          <name>scylla_version</name>
        </hudson.model.StringParameterDefinition>
      </parameterDefinitions>
    </hudson.model.ParametersDefinitionProperty>
  </properties>
</flow-definition>
"""


def test_extract_choice_parameters_nested_arraylist():
    config = ET.fromstring(CONFIG_WITH_CHOICES)
    choices = JenkinsService._extract_choice_parameters(config)
    assert choices == {"billing_project": ["sct", "qa", "perf"]}


def test_extract_choice_parameters_flat():
    config = ET.fromstring(CONFIG_FLAT_CHOICES)
    choices = JenkinsService._extract_choice_parameters(config)
    assert choices == {"billing_project": ["sct", "qa"]}


def test_extract_choice_parameters_none():
    config = ET.fromstring(CONFIG_NO_CHOICES)
    choices = JenkinsService._extract_choice_parameters(config)
    assert choices == {}


def _apply(params, choices, descriptions=None):
    JenkinsService._apply_choice_defaults(params, choices, descriptions or {})
    return params


def test_optional_choice_param_defaults_to_empty():
    # billing_project with no value must default to empty, not the first project.
    params = [{"name": "billing_project", "value": ""}]
    _apply(params, {"billing_project": ["sct", "qa", "perf"]})
    assert params[0]["value"] == ""
    assert params[0]["choices"] == ["", "sct", "qa", "perf"]


def test_optional_choice_param_unknown_value_resets_to_empty():
    params = [{"name": "billing_project", "value": "stale"}]
    _apply(params, {"billing_project": ["sct", "qa"]})
    assert params[0]["value"] == ""


def test_optional_choice_param_preserves_explicit_selection():
    # A real prior selection (e.g. cloned run) is kept.
    params = [{"name": "billing_project", "value": "qa"}]
    _apply(params, {"billing_project": ["sct", "qa", "perf"]})
    assert params[0]["value"] == "qa"
    assert params[0]["choices"] == ["", "sct", "qa", "perf"]


def test_regular_choice_param_defaults_to_first():
    # Non-optional choice params keep the old first-choice fallback.
    params = [{"name": "region", "value": "unknown"}]
    _apply(params, {"region": ["us-east-1", "eu-west-1"]})
    assert params[0]["value"] == "us-east-1"
    assert params[0]["choices"] == ["us-east-1", "eu-west-1"]


class _FakeJenkins:
    """Minimal stand-in for the python-jenkins client so next_build_number can
    be tested without a real Jenkins connection."""

    def __init__(self, job_info=None, error=None, job_config=None, build_info=None):
        self._job_info = job_info or {}
        self._error = error
        self._job_config = job_config
        self._build_info = build_info or {}

    def get_job_info(self, name):  # noqa: ARG002 - signature parity
        if self._error is not None:
            raise self._error
        return self._job_info

    def get_job_config(self, name):  # noqa: ARG002 - signature parity
        return self._job_config

    def get_build_info(self, name, number):  # noqa: ARG002 - signature parity
        return self._build_info


def _service_with(fake):
    # Bypass __init__ (which opens a real Jenkins connection) and inject the fake.
    service = object.__new__(JenkinsService)
    service._jenkins = fake
    return service


def test_next_build_number_returns_next():
    service = _service_with(_FakeJenkins(job_info={"nextBuildNumber": 43}))
    assert service.next_build_number("scylla-2026.2/longevity/longevity-100gb") == 43


def test_next_build_number_missing_is_minus_one():
    # A job Jenkins reports without nextBuildNumber yields the sentinel -1.
    service = _service_with(_FakeJenkins(job_info={}))
    assert service.next_build_number("scylla-2026.2/longevity/longevity-100gb") == -1


def test_next_build_number_jenkins_error_is_non_fatal():
    # A Jenkins error must not propagate: the trigger already succeeded.
    service = _service_with(_FakeJenkins(error=jenkins.JenkinsException("boom")))
    assert service.next_build_number("scylla-2026.2/longevity/longevity-100gb") == -1


def test_validate_sct_version_source_accepts_single_source():
    # Exactly one family set (with other keys empty) is valid.
    JenkinsService.validate_sct_version_source({"scylla_version": "master:latest", "scylla_repo": ""})


def test_validate_sct_version_source_accepts_image_variant():
    # Any single key of the image family counts as one source.
    JenkinsService.validate_sct_version_source({"gce_image_db": "https://www.googleapis.com/compute/v1/x"})


def test_validate_sct_version_source_rejects_none_set():
    with pytest.raises(DataValidationError):
        JenkinsService.validate_sct_version_source({"scylla_version": "", "scylla_repo": "  "})


def test_validate_sct_version_source_rejects_missing_keys_entirely():
    # No source keys present at all is also invalid.
    with pytest.raises(DataValidationError):
        JenkinsService.validate_sct_version_source({"backend": "aws"})


def test_validate_sct_version_source_rejects_multiple_families():
    with pytest.raises(DataValidationError) as exc:
        JenkinsService.validate_sct_version_source(
            {"scylla_version": "master:latest", "scylla_ami_id": "ami-1234"}
        )
    # The message should name the conflicting families.
    assert "scylla_version" in str(exc.value)
    assert "scylla_image" in str(exc.value)


# job_info whose configured defaults (scylla_version=master:latest) differ from
# the last build's actual parameters, so the two fetch modes are distinguishable.
_JOB_INFO_WITH_DEFAULTS = {
    "nextBuildNumber": 6,
    "property": [
        {
            "_class": "hudson.model.ParametersDefinitionProperty",
            "parameterDefinitions": [
                {"name": "scylla_version", "defaultParameterValue": {"value": "master:latest"}},
                {"name": "billing_project", "defaultParameterValue": {"value": "sct"}},
                {"name": "requested_by_user", "defaultParameterValue": {"value": "seed"}},
            ],
        }
    ],
}

_BUILD_INFO_WITH_PARAMS = {
    "actions": [
        {
            "_class": "hudson.model.ParametersAction",
            "parameters": [
                {"name": "scylla_version", "value": "5.4:latest"},
                {"name": "billing_project", "value": "qa"},
                {"name": "requested_by_user", "value": "someone"},
            ],
        }
    ],
}


def _params_by_name(params):
    return {p["name"]: p for p in params}


def _params_service():
    fake = _FakeJenkins(
        job_info=_JOB_INFO_WITH_DEFAULTS,
        job_config=CONFIG_WITH_CHOICES,
        build_info=_BUILD_INFO_WITH_PARAMS,
    )
    return _service_with(fake)


def test_retrieve_job_parameters_from_defaults_uses_job_config():
    # from_defaults ignores the last build and returns the configured defaults.
    params = _params_service().retrieve_job_parameters("job", None, from_defaults=True)
    by_name = _params_by_name(params)
    assert by_name["scylla_version"]["value"] == "master:latest"
    # requested_by_user is always stripped from the returned set.
    assert "requested_by_user" not in by_name
    # billing_project is an optional choice: it defaults to empty with a blank
    # option prepended, regardless of its configured default.
    assert by_name["billing_project"]["value"] == ""
    assert by_name["billing_project"]["choices"] == ["", "sct", "qa", "perf"]


def test_retrieve_job_parameters_from_defaults_ignores_missing_builds():
    # A fresh job with no builds still yields its defaults (no build lookup).
    fake = _FakeJenkins(
        job_info={"property": _JOB_INFO_WITH_DEFAULTS["property"]},
        job_config=CONFIG_WITH_CHOICES,
    )
    params = _service_with(fake).retrieve_job_parameters("job", None, from_defaults=True)
    assert _params_by_name(params)["scylla_version"]["value"] == "master:latest"


def test_retrieve_job_parameters_rebuild_uses_last_build():
    # Default mode (from_defaults=False) seeds from the last build's parameters.
    params = _params_service().retrieve_job_parameters("job", None, from_defaults=False)
    by_name = _params_by_name(params)
    assert by_name["scylla_version"]["value"] == "5.4:latest"
    assert by_name["billing_project"]["value"] == "qa"
    assert "requested_by_user" not in by_name


def test_retrieve_job_parameters_rebuild_specific_build():
    # A specific build number also uses the build's parameters.
    params = _params_service().retrieve_job_parameters("job", 3, from_defaults=False)
    assert _params_by_name(params)["scylla_version"]["value"] == "5.4:latest"
