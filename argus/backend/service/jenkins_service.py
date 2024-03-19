from typing import Any, TypedDict
import xml.etree.ElementTree as ET
import jenkins
import logging

from flask import current_app, g

LOGGER = logging.getLogger(__name__)


class Parameter(TypedDict):
    _class: str
    name: str
    description: str
    value: Any


class JenkinsService:
    RESERVED_PARAMETER_NAME = "requested_by_user"

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