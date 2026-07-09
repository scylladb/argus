import xml.etree.ElementTree as ET

import jenkins

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

    def __init__(self, job_info=None, error=None):
        self._job_info = job_info or {}
        self._error = error

    def get_job_info(self, name):  # noqa: ARG002 - signature parity
        if self._error is not None:
            raise self._error
        return self._job_info


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
