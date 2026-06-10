import xml.etree.ElementTree as ET

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
