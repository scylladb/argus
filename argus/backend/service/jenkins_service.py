import re
import requests
from typing import Any, TypedDict
from uuid import UUID
import xml.etree.ElementTree as ET
import jenkins
import logging

from flask import current_app, g

from argus.backend.models.web import ArgusGroup, ArgusRelease, ArgusTest, UserOauthToken

LOGGER = logging.getLogger(__name__)
GITHUB_REPO_RE = r"(?P<http>^https?:\/\/(www\.)?github\.com\/(?P<user>[\w\d\-]+)\/(?P<repo>[\w\d\-]+)(\.git)?$)|(?P<ssh>git@github\.com:(?P<ssh_user>[\w\d\-]+)\/(?P<ssh_repo>[\w\d\-]+)(\.git)?)"

class Parameter(TypedDict):
    _class: str
    name: str
    description: str
    value: Any


class JenkinsServiceError(Exception):
    pass


class JenkinsService:
    RESERVED_PARAMETER_NAME = "requested_by_user"

    SETTINGS_CONFIG_MAP = {
        "scylla-cluster-tests": {
            "gitRepo": "*//scm/userRemoteConfigs/hudson.plugins.git.UserRemoteConfig/url",
            "gitBranch": "*//scm/branches/hudson.plugins.git.BranchSpec/name",
            "pipelineFile": "*//scriptPath",
        },
        "driver-matrix-tests": {
            "gitRepo": "*//scm/userRemoteConfigs/hudson.plugins.git.UserRemoteConfig/url",
            "gitBranch": "*//scm/branches/hudson.plugins.git.BranchSpec/name",
            "pipelineFile": "*//scriptPath",
        },
        "sirenada": {
            "gitRepo": "*//scm/userRemoteConfigs/hudson.plugins.git.UserRemoteConfig/url",
            "gitBranch": "*//scm/branches/hudson.plugins.git.BranchSpec/name",
            "pipelineFile": "*//scriptPath",
        }
    }

    def __init__(self) -> None:
        self._jenkins = jenkins.Jenkins(url=current_app.config["JENKINS_URL"],
                                        username=current_app.config["JENKINS_USER"],
                                        password=current_app.config["JENKINS_API_TOKEN"])

    def retrieve_job_parameters(self, build_id: str, build_number: int) -> list[Parameter]:
        job_info = self._jenkins.get_build_info(name=build_id, number=build_number)
        raw_config = self._jenkins.get_job_config(name=build_id)
        config = ET.fromstring(raw_config)
        parameter_defs = config.find("*//parameterDefinitions")
        if parameter_defs:
            descriptions = {
                define.findtext("name"): f"{define.findtext('description', '')}" + f" (default: <span class=\"fw-bold\">{define.findtext('defaultValue')}</span>)" if define.findtext('defaultValue') else ""
                for define in parameter_defs.iterfind("hudson.model.StringParameterDefinition")
            }
        else:
            descriptions = {}
        params = next(a for a in job_info["actions"] if a.get("_class", "#NONE") == "hudson.model.ParametersAction")["parameters"]
        params = [param for param in params if param["name"] != self.RESERVED_PARAMETER_NAME]
        for idx, param in enumerate(params):
            params[idx]["description"] = descriptions.get(param["name"], "")

        return params

    def get_releases_for_clone(self, test_id: str):
        test_id = UUID(test_id)
        # TODO: Filtering based on origin location / user preferences
        _: ArgusTest = ArgusTest.get(id=test_id)

        releases = list(ArgusRelease.all())

        return sorted(releases, key=lambda r: r.pretty_name if r.pretty_name else r.name)

    def get_groups_for_release(self, release_id: str):
        groups = list(ArgusGroup.filter(release_id=release_id).all())

        return sorted(groups, key=lambda g: g.pretty_name if g.pretty_name else g.name)

    def _verify_sct_settings(self, new_settings: dict[str, str]) -> tuple[bool, str]:
        if not (match := re.match(GITHUB_REPO_RE, new_settings["gitRepo"])):
            return (False, "Repository doesn't conform to GitHub schema")

        git_info = match.groupdict()
        if git_info.get("ssh"):
            repo = git_info["ssh_repo"]
            user = git_info["ssh_user"]
        else:
            repo = git_info["repo"]
            user = git_info["user"]

        user_tokens = UserOauthToken.filter(user_id=g.user.id).all()
        token = None
        for tok in user_tokens:
            if tok.kind == "github":
                token = tok.token
                break
        if not token:
            raise JenkinsServiceError("Github token not found")

        response = requests.get(
            url=f"https://api.github.com/repos/{user}/{repo}/contents/{new_settings['pipelineFile']}?ref={new_settings['gitBranch']}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
            }
            )
        
        if response.status_code == 404:
            return (False, f"Pipeline file not found in the <a href=\"https://github.com/{user}/{repo}/tree/{new_settings['gitBranch']}\"> target repository</a>, please check the repository before continuing")

        if response.status_code == 403:
            return (True, "No access to this repository using your token. The pipeline file cannot be verified.")

        if response.status_code == 200:
            return (True, "")

        return (False, "Generic Error")

    def verify_job_settings(self, build_id: str, new_settings: dict[str, str]) -> tuple[bool, str]:
        PLUGIN_MAP = {
            "scylla-cluster-tests": self._verify_sct_settings,
            # for now they match
            "sirenada": self._verify_sct_settings,
            "driver-matrix-tests": self._verify_sct_settings,
        }
        test: ArgusTest = ArgusTest.get(build_system_id=build_id)
        plugin_name = test.plugin_name

        validated, message = PLUGIN_MAP.get(plugin_name, lambda _: (True, ""))(new_settings)

        return {
            "validated": validated,
            "message": message,
        }

    def get_advanced_settings(self, build_id: str):
        test: ArgusTest = ArgusTest.get(build_system_id=build_id)
        plugin_name = test.plugin_name

        if not (plugin_settings := self.SETTINGS_CONFIG_MAP.get(plugin_name)):
            return {}

        settings = {}
        raw_config = self._jenkins.get_job_config(name=build_id)
        config = ET.fromstring(raw_config)

        for setting, xpath in plugin_settings.items():
            value = config.find(xpath)
            settings[setting] = value.text

        return settings

    def adjust_job_settings(self, build_id: str, plugin_name: str, settings: dict[str, str]):
        xpath_map = self.SETTINGS_CONFIG_MAP.get(plugin_name)
        if not xpath_map:
            return
        
        config = self._jenkins.get_job_config(name=build_id)
        xml = ET.fromstring(config)
        for setting, value in settings.items():
            element = xml.find(xpath_map[setting])
            element.text = value

        adjusted_config = ET.tostring(xml, encoding="unicode")
        self._jenkins.reconfig_job(name=build_id, config_xml=adjusted_config)

    def clone_job(self, current_test_id: str, new_name: str, target: str, group: str, advanced_settings: bool | dict[str, str]):
        cloned_test: ArgusTest = ArgusTest.get(id=current_test_id)
        target_release: ArgusRelease = ArgusRelease.get(id=target)
        target_group: ArgusGroup = ArgusGroup.get(id=group)

        if target_group.id == cloned_test.id and new_name == cloned_test.name:
            raise JenkinsServiceError("Unable to clone: source and destination are the same")

        if not target_group.build_system_id:
            raise JenkinsServiceError("Unable to clone: target group is missing jenkins folder path")

        jenkins_new_build_id = f"{target_group.build_system_id}/{new_name}"

        new_test = ArgusTest()
        new_test.name = new_name
        new_test.build_system_id = jenkins_new_build_id
        new_test.group_id = target_group.id
        new_test.release_id = target_release.id
        new_test.plugin_name = cloned_test.plugin_name

        old_config = self._jenkins.get_job_config(name=cloned_test.build_system_id)
        LOGGER.info(old_config)
        xml = ET.fromstring(old_config)
        display_name = xml.find("displayName")
        display_name.text = new_name
        new_config = ET.tostring(xml, encoding="unicode")
        self._jenkins.create_job(name=jenkins_new_build_id, config_xml=new_config)
        new_job_info = self._jenkins.get_job_info(name=jenkins_new_build_id)
        new_test.build_system_url = new_job_info["url"]
        new_test.save()

        if advanced_settings:
            self.adjust_job_settings(build_id=jenkins_new_build_id, plugin_name=new_test.plugin_name, settings=advanced_settings)

        return {
            "new_job": new_job_info,
            "new_entity": new_test,
        }

    def clone_build_job(self, build_id: str, params: dict[str, str]):
        queue_item = self.build_job(build_id=build_id, params=params)
        return {
            "queueItem": queue_item,
        }

    def build_job(self, build_id: str, params: dict, user_override: str = None):
        queue_number = self._jenkins.build_job(build_id, {
            **params,
            self.RESERVED_PARAMETER_NAME: g.user.username if not user_override else user_override
        })
        return queue_number

    def get_queue_info(self, queue_item: int):
        build_info = self._jenkins.get_queue_item(queue_item)
        LOGGER.info("%s", build_info)
        executable = build_info.get("executable")
        if executable:
            return executable
        else:
            return {
                "why": build_info["why"],
                "inQueueSince": build_info["inQueueSince"],
                "taskUrl": build_info["task"]["url"],
            }