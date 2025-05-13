
import logging
import datetime
import json
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from functools import reduce
from typing import Any, Optional, TypedDict
from uuid import UUID
from flask import g
from slugify import slugify

from argus.backend.models.plan import ArgusReleasePlan
from argus.backend.models.web import ArgusGroup, ArgusRelease, ArgusTest, ArgusUserView, User
from argus.backend.service.jenkins_service import JenkinsService
from argus.backend.service.test_lookup import TestLookup
from argus.backend.service.views import UserViewService
from argus.backend.util.common import chunk


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, init=True, repr=True, kw_only=True)
class CreatePlanPayload:
    name: str
    description: str
    owner: str
    participants: list[str]
    target_version: str | None
    release_id: str
    tests: list[str]
    groups: list[str]
    assignments: dict[str, str]
    created_from: Optional[str] = None


@dataclass(frozen=True, init=True, repr=True, kw_only=True)
class TempPlanPayload:
    id: str
    name: str
    completed: bool
    description: str
    owner: str
    participants: list[str]
    target_version: str
    assignee_mapping: dict[str, str]
    assignments: dict[str, str] = None
    release_id: str
    tests: list[str]
    groups: list[str]
    view_id: str
    creation_time: str
    last_updated: str
    ends_at: str
    created_from: Optional[str]


@dataclass(frozen=True, init=True, repr=True, kw_only=True)
class CopyPlanPayload:
    plan: TempPlanPayload
    keepParticipants: bool
    replacements: dict[str, str]
    targetReleaseId: str
    targetReleaseName: str


class PlanTriggerPayload(TypedDict):
    plan_id: str | None
    release: str | None
    version: str | None
    common_params: dict[str, str]
    params: list[dict[str, str]]


class PlannerServiceException(Exception):
    pass


class PlanningService:

    VIEW_WIDGET_SETTINGS = [
        {
            "position": 1,
            "type": "githubIssues",
            "settings": {
                "submitDisabled": True,
                "aggregateByIssue": True
            }
        },
        {
            "position": 2,
            "type": "releaseStats",
            "settings": {
                "horizontal": False,
                "displayExtendedStats": True,
                "hiddenStatuses": ["not_run", "not_planned"]
            }
        },
        {
            "position": 3,
            "type": "testDashboard",
            "settings": {
                "targetVersion": True,
                "versionsIncludeNoVersion": False,
                "productVersion": None
            }
        }
    ]

    def version(self):
        return "v1"

    def create_plan(self, payload: dict[str, Any]) -> ArgusReleasePlan:
        plan_request = CreatePlanPayload(**payload)

        try:
            existing = ArgusReleasePlan.filter(
                name=plan_request.name, target_version=plan_request.target_version).allow_filtering().get()
            if existing:
                raise PlannerServiceException(
                    f"Found existing plan {existing.name} ({existing.target_version}) with the same name and version", existing, plan_request)
        except ArgusReleasePlan.DoesNotExist:
            pass

        plan = ArgusReleasePlan()
        plan.name = plan_request.name
        plan.description = plan_request.description
        plan.owner = UUID(plan_request.owner)
        plan.target_version = plan_request.target_version
        plan.release_id = UUID(plan_request.release_id)
        plan.participants = plan_request.participants
        plan.assignee_mapping = {UUID(entity_id): UUID(user_id)
                                 for entity_id, user_id in plan_request.assignments.items()}
        plan.groups = plan_request.groups
        plan.tests = plan_request.tests
        if plan_request.created_from:
            plan.created_from = plan_request.created_from
        view = self.create_view_for_plan(plan)
        plan.view_id = view.id

        plan.save()

        return plan

    def update_plan(self, payload: dict[str, Any]) -> bool:
        plan_request = TempPlanPayload(**payload)

        try:
            existing = ArgusReleasePlan.filter(
                name=plan_request.name, target_version=plan_request.target_version).allow_filtering().get()
            if existing and existing.id != UUID(plan_request.id):
                raise PlannerServiceException(
                    f"Found existing plan {existing.name} ({existing.target_version}) with the same name and version", existing, plan_request)
        except ArgusReleasePlan.DoesNotExist:
            pass

        plan: ArgusReleasePlan = ArgusReleasePlan.get(id=plan_request.id)
        plan.owner = plan_request.owner
        plan.participants = plan_request.participants
        plan.assignee_mapping = plan_request.assignee_mapping
        plan.tests = plan_request.tests
        plan.groups = plan_request.groups
        plan.name = plan_request.name
        plan.target_version = plan_request.target_version
        plan.description = plan_request.description
        plan.last_updated = datetime.datetime.now(tz=datetime.UTC)
        plan.save()

        view = self.update_view_for_plan(plan)
        plan.view_id = view.id
        plan.save()

        return True

    def update_view_for_plan(self, plan: ArgusReleasePlan) -> ArgusUserView:
        service = UserViewService()
        release: ArgusRelease = ArgusRelease.get(id=plan.release_id)

        version_str = f" ({plan.target_version}) " if plan.target_version else ""
        view_name = f"{release.name} {version_str}- {plan.name}"

        view: ArgusUserView = ArgusUserView.get(id=plan.view_id)
        settings = json.loads(view.widget_settings)
        items = [f"test:{tid}" for tid in plan.tests]
        items = [*items, *[f"group:{gid}" for gid in plan.groups]]
        entities = service.parse_view_entity_list(items)
        view.tests = entities["tests"]
        view.display_name = view_name
        view.name = slugify(view_name)
        view.description = f"{plan.target_version or ''} Automatic view for the release plan \"{plan.name}\". {plan.description}"
        view.group_ids = entities["group"]

        dash = next(filter(lambda widget: widget["type"] == "testDashboard", settings), None)
        if dash:
            dash["settings"]["productVersion"] = plan.target_version
            dash["settings"]["targetVersion"] = bool(plan.target_version)

        view.widget_settings = json.dumps(settings)
        view.save()
        service.refresh_stale_view(view)
        return view

    def create_view_for_plan(self, plan: ArgusReleasePlan) -> ArgusUserView:
        service = UserViewService()
        release: ArgusRelease = ArgusRelease.get(id=plan.release_id)
        items = [f"test:{tid}" for tid in plan.tests]
        items = [*items, *[f"group:{gid}" for gid in plan.groups]]
        version_str = f" ({plan.target_version}) " if plan.target_version else ""
        view_name = f"{release.name} {version_str}- {plan.name}"
        settings = deepcopy(self.VIEW_WIDGET_SETTINGS)
        if plan.target_version:
            settings[2]["settings"]["productVersion"] = plan.target_version
        else:
            settings[2]["settings"]["targetVersion"] = False
        view = service.create_view(
            name=slugify(view_name),
            display_name=view_name,
            description=f"{plan.target_version or ''} Automatic view for the release plan \"{plan.name}\". {plan.description}",
            items=items,
            plan_id=plan.id,
            widget_settings=json.dumps(settings),
        )

        view.save()
        service.refresh_stale_view(view)
        return view

    def change_plan_owner(self, plan_id: UUID | str, new_owner: UUID | str) -> bool:
        user: User = User.get(id=new_owner)
        plan: ArgusReleasePlan = ArgusReleasePlan.get(id=plan_id)

        plan.owner = user.id
        plan.last_updated = datetime.datetime.now(tz=datetime.UTC)

        plan.save()
        return True

    def get_plan(self, plan_id: str | UUID) -> ArgusReleasePlan:
        return ArgusReleasePlan.get(id=plan_id)

    def get_gridview_for_release(self, release_id: str | UUID) -> dict[str, dict]:
        release = ArgusRelease.get(id=release_id)
        release = TestLookup.index_mapper(release, "release")
        groups: list[ArgusGroup] = list(ArgusGroup.filter(release_id=release_id).all())
        tests: list[ArgusTest] = list(ArgusTest.filter(release_id=release_id).all())

        groups = {str(g.id): TestLookup.index_mapper(g, "group") for g in groups if g.enabled}

        tests_by_group = reduce(lambda acc, test: acc[str(test.group_id)].append(test) or acc, tests, defaultdict(list))

        res = {
            "tests": {str(t.id): TestLookup.index_mapper(t) for t in tests if t.enabled and groups.get(str(t.group_id), {}).get("enabled", False)},
            "groups": groups,
            "testByGroup": tests_by_group
        }

        for group in res["groups"].values():
            group["release"] = release["name"]

        for test in res["tests"].values():
            g = res["groups"][str(test["group_id"])]
            test["group"] = g["pretty_name"] or g["name"]
            test["release"] = release["name"]

        return res

    def copy_plan(self, payload: CopyPlanPayload) -> ArgusReleasePlan:

        try:
            existing = ArgusReleasePlan.filter(
                name=payload.plan.name, target_version=payload.plan.target_version).allow_filtering().get()
            if existing:
                raise PlannerServiceException(
                    f"Found existing plan {existing.name} ({existing.target_version}) with the same name and version", existing, payload)
        except ArgusReleasePlan.DoesNotExist:
            pass

        original_plan: ArgusReleasePlan = ArgusReleasePlan.get(id=payload.plan.id)
        target_release: ArgusRelease = ArgusRelease.get(id=payload.targetReleaseId)
        original_release: ArgusRelease = ArgusRelease.get(id=original_plan.release_id)

        original_tests: list[ArgusTest] = ArgusTest.filter(id__in=original_plan.tests).all()
        original_groups: list[ArgusGroup] = ArgusGroup.filter(id__in=original_plan.groups).all()
        target_tests: list[ArgusTest] = ArgusTest.filter(release_id=target_release.id).all()
        target_groups: list[ArgusGroup] = ArgusGroup.filter(release_id=target_release.id).all()

        tests_by_build_id = {t.build_system_id: t for t in target_tests}
        groups_by_build_id = {g.build_system_id: g for g in target_groups}

        new_tests = []
        new_groups = []
        new_assignee_mapping = {}

        for test in original_tests:
            original_assignee = original_plan.assignee_mapping.get(test.id)
            new_build_id = test.build_system_id.replace(original_release.name, target_release.name, 1)
            new_test = tests_by_build_id.get(new_build_id)
            new_test_id = new_test.id if new_test else payload.replacements.get(test.id)
            if new_test_id:
                new_tests.append(new_test_id)
                if original_assignee and payload.keepParticipants:
                    new_assignee_mapping[new_test_id] = original_assignee

        for group in original_groups:
            original_assignee = original_plan.assignee_mapping.get(group.id)
            new_build_id = group.build_system_id.replace(original_release.name, target_release.name, 1)
            new_group = groups_by_build_id.get(new_build_id)
            new_group_id = new_group.id if new_group else payload.replacements.get(group.id)
            if new_group_id:
                new_groups.append(new_group_id)
                if original_assignee and payload.keepParticipants:
                    new_assignee_mapping[new_group_id] = original_assignee

        new_plan = ArgusReleasePlan()
        new_plan.release_id = target_release.id
        new_plan.owner = payload.plan.owner
        new_plan.name = payload.plan.name
        new_plan.description = payload.plan.description
        if payload.keepParticipants:
            new_plan.participants = payload.plan.participants
        new_plan.assignee_mapping = new_assignee_mapping
        new_plan.tests = new_tests
        new_plan.groups = new_groups
        new_plan.target_version = payload.plan.target_version
        view = self.create_view_for_plan(new_plan)
        new_plan.view_id = view.id

        new_plan.save()

        return new_plan

    def check_plan_copy_eligibility(self, plan_id: str | UUID, target_release_id: str | UUID) -> dict:
        target_release: ArgusRelease = ArgusRelease.get(id=target_release_id)
        plan: ArgusReleasePlan = ArgusReleasePlan.get(id=plan_id)
        original_release: ArgusRelease = ArgusRelease.get(id=plan.release_id)

        original_tests: list[ArgusTest] = ArgusTest.filter(id__in=plan.tests).all()
        original_groups: list[ArgusGroup] = ArgusGroup.filter(id__in=plan.groups).all()

        target_tests: list[ArgusTest] = ArgusTest.filter(release_id=target_release.id).all()
        target_groups: list[ArgusGroup] = ArgusGroup.filter(release_id=target_release.id).all()

        tests_by_build_id = {t.build_system_id: t for t in target_tests}
        groups_by_build_id = {g.build_system_id: g for g in target_groups}

        missing_tests = []
        missing_groups = []
        status = "passed"
        for test in original_tests:
            new_build_id = test.build_system_id.replace(original_release.name, target_release.name, 1)
            new_group = tests_by_build_id.get(new_build_id)
            if not new_group:
                t = TestLookup.index_mapper(test)
                t["release"] = original_release.name
                missing_tests.append(t)

        for group in original_groups:
            new_build_id = group.build_system_id.replace(original_release.name, target_release.name, 1)
            new_group = groups_by_build_id.get(new_build_id)
            if not new_group:
                g = TestLookup.index_mapper(group)
                g["release"] = original_release.name
                missing_groups.append(g)

        if len(missing_tests) > 0 or len(missing_groups) > 0:
            status = "failed"

        return {
            "status": status,
            "targetRelease": target_release,
            "originalRelease": original_release,
            "missing": {
                "tests": missing_tests,
                "groups": missing_groups,
            }
        }

    def release_planner(self, release_name: str) -> dict[str, Any]:
        release: ArgusRelease = ArgusRelease.get(name=release_name)

        plans: list[ArgusReleasePlan] = self.get_plans_for_release(release.id)

        return {
            "release": release,
            "plans": plans,
        }

    def get_plans_for_release(self, release_id: str | UUID) -> list[ArgusReleasePlan]:
        return list(ArgusReleasePlan.filter(release_id=release_id).all())

    def delete_plan(self, plan_id: str | UUID):
        plan: ArgusReleasePlan = ArgusReleasePlan.get(id=plan_id)
        if plan.view_id:
            view: ArgusUserView = ArgusUserView.get(id=plan.view_id)
            view.delete()

        plan.delete()
        return True

    def get_assignee_for_test(self, test_id: str | UUID, target_version: str = None) -> UUID | None:
        dml = ArgusReleasePlan.filter(tests__contains=test_id, complete=False)
        if target_version:
            dml.filter(target_version=target_version)
        potential_plans: list[ArgusReleasePlan] = dml.allow_filtering().all()
        for plan in potential_plans:
            # Use the most recent plan
            return plan.assignee_mapping.get(test_id, plan.owner)
        return None

    def get_assignee_for_group(self, group_id: str | UUID, target_version: str = None) -> UUID | None:
        dml = ArgusReleasePlan.filter(groups__contains=group_id, complete=False)
        if target_version:
            dml.filter(target_version=target_version)
        potential_plans: list[ArgusReleasePlan] = dml.allow_filtering().all()
        for plan in potential_plans:
            # Use the most recent plan
            return plan.assignee_mapping.get(group_id, plan.owner)
        return None

    def get_assignments_for_groups(self, release_id: str | UUID, version: str = None, plan_id: UUID = None) -> dict[str, UUID]:
        release: ArgusRelease = ArgusRelease.get(id=release_id)
        if not plan_id:
            plans: list[ArgusReleasePlan] = list(ArgusReleasePlan.filter(release_id=release.id).all())
            plans = plans if not version else [plan for plan in plans if plan.target_version == version]
        else:
            plans = [ArgusReleasePlan.get(id=plan_id)]

        all_assignments = {}
        for plan in reversed(plans):
            # TODO: (gid, [user_id]) Should be changed to gid, user_id once old scheduling mechanism is completely removed
            all_assignments.update(map(lambda group_id: (
                str(group_id), [plan.assignee_mapping.get(group_id,  plan.owner)]), plan.groups))

        return all_assignments

    def get_assignments_for_tests(self, group_id: str | UUID, version: str = None, plan_id: UUID | str = None) -> dict[str, UUID]:
        group: ArgusGroup = ArgusGroup.get(id=group_id)
        release: ArgusRelease = ArgusRelease.get(id=group.release_id)
        if not plan_id:
            plans: list[ArgusReleasePlan] = list(ArgusReleasePlan.filter(release_id=release.id).all())
            plans = plans if not version else [plan for plan in plans if plan.target_version == version]
        else:
            plans = [ArgusReleasePlan.get(id=plan_id)]

        all_assignments = {}

        def get_assignee(test_id: UUID, mapping: dict[UUID, UUID]):
            test_assignment = mapping.get(test_id)
            return test_assignment

        for plan in reversed(plans):
            # TODO: (tid, [user_id]) Should be changed to tid, user_id once old scheduling mechanism is completely removed
            all_assignments.update(map(lambda test_id: (str(test_id), [get_assignee(
                test_id, plan.assignee_mapping) or plan.owner]), plan.tests))

        return all_assignments

    def complete_plan(self, plan_id: str | UUID) -> bool:
        plan: ArgusReleasePlan = ArgusReleasePlan(id=plan_id).get()
        plan.completed = True

        plan.save()
        return plan.completed

    def resolve_plan(self, plan_id: str | UUID) -> list[dict[str, Any]]:
        plan: ArgusReleasePlan = ArgusReleasePlan.get(id=plan_id)

        release: ArgusRelease = ArgusRelease.get(id=plan.release_id)
        tests: list[ArgusTest] = []
        for batch in chunk(plan.tests):
            tests.extend(ArgusTest.filter(id__in=batch).all())
        test_groups: list[ArgusGroup] = ArgusGroup.filter(id__in=list({t.group_id for t in tests})).all()
        test_groups = {g.id: g for g in test_groups}
        groups: list[ArgusGroup] = list(ArgusGroup.filter(id__in=plan.groups).all())

        mapped = [TestLookup.index_mapper(entity, "group" if isinstance(
            entity, ArgusGroup) else "test") for entity in [*tests, *groups]]

        for ent in mapped:
            ent["release"] = release.name
            if group_id := ent.get("group_id"):
                group = test_groups.get(group_id)
                ent["group"] = group.pretty_name or group.name

        return mapped

    def trigger_jobs(self, payload: PlanTriggerPayload) -> bool:

        release_name = payload.get("release")
        plan_id = payload.get("plan_id")
        version = payload.get("version")

        condition_set = (bool(release_name), bool(plan_id), bool(version))

        match condition_set:
            case (True, False, False):
                release = ArgusRelease.get(name=release_name)
                filter_expr = {"release_id__eq": release.id}
            case (False, True, False):
                filter_expr = {"id__eq": plan_id}
            case (False, False, True):
                filter_expr = {"target_version__eq": version}
            case (True, False, True):
                release = ArgusRelease.get(name=release_name)
                filter_expr = {"target_version__eq": version, "release_id__eq": release.id}
            case _:
                raise PlannerServiceException("No version, release name or plan id specified.", payload)

        plans: list[ArgusReleasePlan] = list(ArgusReleasePlan.filter(**filter_expr).allow_filtering().all())

        if len(plans) == 0:
            return False, "No plans to trigger"

        common_params = payload.get("common_params", {})
        params = payload.get("params", [])
        test_ids = [test_id for plan in plans for test_id in plan.tests]
        group_ids = [group_id for plan in plans for group_id in plan.groups]

        tests = []
        for batch in chunk(test_ids):
            tests.extend(ArgusTest.filter(id__in=batch).all())

        for batch in (chunk(group_ids)):
            tests.extend(ArgusTest.filter(group_id__in=batch).allow_filtering().all())

        tests = list({test for test in tests})

        LOGGER.info("Will trigger %s tests...", len(tests))

        service = JenkinsService()
        failures = []
        successes = []
        for test in tests:
            try:
                latest_build_number = service.latest_build(test.build_system_id)
                if latest_build_number == -1:
                    failures.append(test.build_system_id)
                    continue
                raw_params = service.retrieve_job_parameters(test.build_system_id, latest_build_number)
                job_params = {param["name"]: param["value"] for param in raw_params if param.get("value")}
                backend = job_params.get("backend")
                match backend.split("-"):
                    case ["aws", *_]:
                        region_key = "region"
                    case ["gce", *_]:
                        region_key = "gce_datacenter"
                    case ["azure", *_]:
                        region_key = "azure_region_name"
                    case _:
                        raise PlannerServiceException(f"Unknown backend encountered: {backend}", backend)

                job_params = None
                for param_set in params:
                    if param_set["test"] == "longevity" and backend == param_set["backend"]:
                        job_params = dict(param_set)
                        job_params.pop("type", None)
                        region = job_params.pop("region", None)
                        job_params[region_key] = region
                        break
                if not job_params:
                    raise PlannerServiceException(
                        f"Parameters not found for job {test.build_system_id}", test.build_system_id)
                final_params = {**job_params, **common_params, **job_params}
                queue_item = service.build_job(test.build_system_id, final_params, g.user.username)
                info = service.get_queue_info(queue_item)
                url = info.get("url", info.get("taskUrl", ""))
                successes.append(url)
            except Exception:
                LOGGER.error("Failed to trigger %s", test.build_system_id, exc_info=True)
                failures.append(test.build_system_id)

        return {
            "jobs": successes,
            "failed_to_execute": failures,
        }
