import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from argus.backend.error_handlers import APIException, DataValidationError
from argus.backend.models.chat import ChatHistory
from argus.backend.models.plan import ArgusReleasePlan
from argus.backend.models.web import ArgusTest, User
from argus.backend.service.chat import sct_params
from argus.backend.service.chat.entity import ChatEntity
from argus.backend.service.chat.history import ChatHistoryService
from argus.backend.service.chat.mcp import McpServerService
from argus.backend.service.chat.plans import plan_diff_payload, plan_stamp
from argus.backend.service.chat.resolve import (
    Scope,
    TestReferenceError,
    ToolScopeError,
    load_scope,
    resolve_run_reference,
    run_url,
)
from argus.backend.service.issue_service import IssueService
from argus.backend.service.jenkins_service import JenkinsService
from argus.backend.service.planner_service import PlanningService
from argus.backend.service.testrun import TestRunService
from argus.backend.service.zeus_client import ZeusClient, ZeusError
from argus.backend.util.common import gather_limited
from argus.backend.util.encoders import ArgusJSONEncoder

LOGGER = logging.getLogger(__name__)
JOB_CONCURRENCY = 5
SCT_PLUGIN = "scylla-cluster-tests"
ZEUS_RUN_LIMIT = 5
ZEUS_REFRESH_SECONDS = 15
ZEUS_OPEN_STATES = ("queued", "processing")
MCP_RESULT_LIMIT = 20000


class ChatActionError(APIException):
    pass


def _json(value: object) -> str:
    return json.dumps(value, cls=ArgusJSONEncoder, ensure_ascii=False)


def new_action(kind: str, proposal: dict, rejected: list[dict] | None = None) -> dict:
    return {"kind": kind, "proposal": proposal, "rejected": rejected or [], "confirmed_by": None,
            "confirmed_at": None, "dismissed_by": None, "results": []}


SEEDS = ("last_build", "defaults", "build")


@dataclass(slots=True, frozen=True)
class Seed:
    """Where a start takes its parameters from before the overrides: the last build, the job's defaults, or
    one build."""
    kind: str = "last_build"
    build_number: int | None = None

    @classmethod
    def of(cls, kind: str | None, build_number: int | None = None) -> "Seed":
        kind = kind or ("build" if build_number else "last_build")
        if kind not in SEEDS:
            raise ChatActionError(f"seed must be one of {', '.join(SEEDS)}")
        if kind == "build" and not build_number:
            raise ChatActionError("A build seed needs build_number")
        return cls(kind, build_number if kind == "build" else None)

    def as_json(self) -> dict:
        return {"seed": self.kind, "build_number": self.build_number}


async def job_parameters(jenkins: JenkinsService, test: ArgusTest, seed: Seed) -> list[dict]:
    return await jenkins.retrieve_job_parameters(test.build_system_id, seed.build_number,
                                                 from_defaults=seed.kind == "defaults")


async def _check_start(jenkins: JenkinsService, scope: Scope, test: ArgusTest, overrides: dict[str, str],
                       seed: Seed) -> tuple[dict | None, dict | None]:
    label = scope.label(test)
    if not test.build_system_id:
        return None, {"test": label, "reason": "The test has no Jenkins job"}
    try:
        job = await job_parameters(jenkins, test, seed)
    except Exception as exception:  # noqa: BLE001 - one unreachable job must not hide the others
        return None, {"test": label, "reason": f"Jenkins did not return the job parameters: {exception}"}
    by_name = {param["name"]: param for param in job}
    for name, value in overrides.items():
        if name not in by_name:
            return None, {"test": label, "reason": f"The job has no parameter {name}"}
        choices = by_name[name].get("choices")
        if choices and value not in choices:
            return None, {"test": label, "reason": f"{value} is not a choice of {name} ({', '.join(choices)})"}
    params = {name: param.get("value") for name, param in by_name.items()}
    sct = test.plugin_name == SCT_PLUGIN
    if sct:
        params, changed = sct_params.normalize(params, overrides)
        if reason := await sct_params.check(params, changed):
            return None, {"test": label, "reason": reason}
        try:
            JenkinsService.validate_sct_version_source(params)
        except DataValidationError as exception:
            return None, {"test": label, "reason": str(exception)}
    else:
        params |= overrides
    return {"test_id": str(test.id), "test": label, "name": test.name, "group": scope.group_name(test),
            "build_system_id": test.build_system_id, "params": params, "overrides": dict(overrides),
            **seed.as_json(), "fields": sct_params.fields(params, job, sct)}, None


async def propose_start(scope: Scope, tests: list[ArgusTest], overrides: dict[str, str], rejected: list[dict],
                        per_test: dict[UUID, dict[str, str]] | None = None, seed: Seed = Seed()) -> dict:
    jenkins = JenkinsService()
    unique = list({test.id: test for test in tests}.values())
    per_test = per_test or {}
    checked = await gather_limited(
        (_check_start(jenkins, scope, test, overrides | per_test.get(test.id, {}), seed) for test in unique),
        limit=JOB_CONCURRENCY)
    proposed = [entry for entry, _ in checked if entry]
    rejected = rejected + [reason for _, reason in checked if reason]
    return new_action("execute_tests", {"tests": proposed}, rejected)


async def adjust_start(entity: ChatEntity, node: UUID, *, replace: dict[str, dict[str, str]] | None = None,
                       set_params: dict[str, str] | None = None, unset: list[str] | None = None,
                       only: set[str] | None = None, seed: Seed | None = None) -> tuple[ChatHistory, dict]:
    """Recompute a pending start card with changed overrides or another seed. ``replace`` gives tests their
    whole overrides by test id; ``set_params`` and ``unset`` change the overrides of the tests in ``only``,
    or of every test. Nothing changes unless every test still passes."""
    card = await locate_card(entity, node)
    action = json.loads(card.action)
    if action["kind"] != "execute_tests":
        raise ChatActionError("Only a card that starts tests has parameters")
    if card.action_state != "pending":
        raise ChatActionError(f"This card is already {card.action_state}")
    scope = await load_scope(entity)
    tests = {str(test.id): test for test in scope.tests}
    jenkins = JenkinsService()

    async def recheck(entry: dict) -> tuple[dict | None, dict | None]:
        test = tests.get(entry["test_id"])
        if test is None:
            return None, {"test": entry["test"], "reason": "The test is no longer in this chat's scope"}
        overrides = dict(entry["overrides"])
        if replace is not None and entry["test_id"] in replace:
            overrides = dict(replace[entry["test_id"]])
        elif only is None or entry["test_id"] in only:
            overrides = {name: value for name, value in (overrides | (set_params or {})).items()
                         if name not in set(unset or [])}
        entry_seed = seed or Seed.of(entry.get("seed"), entry.get("build_number"))
        return await _check_start(jenkins, scope, test, overrides, entry_seed)

    checked = await gather_limited((recheck(entry) for entry in action["proposal"]["tests"]), limit=JOB_CONCURRENCY)
    if failures := [reason for _, reason in checked if reason]:
        raise ChatActionError("; ".join(f"{failure['test']}: {failure['reason']}" for failure in failures))
    action["proposal"]["tests"] = [entry for entry, _ in checked]
    result = await card.update(if_conditions={"action_state": "pending"}, action=_json(action),
                               updated_at=datetime.now(UTC))
    if not result.applied:
        raise ChatActionError(f"This card is already {(result.existing or {}).get('action_state')}")
    await ChatHistoryService(entity).touch()
    return card, action


def resolve_plan(plans: list[ArgusReleasePlan], reference: str) -> ArgusReleasePlan:
    for plan in plans:
        if reference in (str(plan.id), plan.key, plan.name):
            return plan
    names = ", ".join(sorted(plan.name for plan in plans)) or "none"
    raise TestReferenceError(f"No plan {reference} in this chat's releases; plans: {names}")


async def plans_in_scope(scope: Scope) -> list[ArgusReleasePlan]:
    service = PlanningService()
    return [plan for release_id in scope.releases for plan in await service.get_plans_for_release(release_id)]


def resolve_labeled_tests(scope: Scope, plan: ArgusReleasePlan, labels: list[str], match_all: bool) -> list[ArgusTest]:
    """The plan's tests whose plan entity carries the labels; a labelled group
    stands for its enabled tests. Matching ignores case."""
    wanted = {label.lower() for label in labels}
    options = json.loads(plan.options) if plan.options else {}
    available: set[str] = set()
    tests_by_id = {test.id: test for test in scope.tests}
    selected: dict[UUID, ArgusTest] = {}
    for entity_id, option in options.items():
        entity_labels = option.get("labels", [])
        available.update(entity_labels)
        lowered = {label.lower() for label in entity_labels}
        if not (wanted <= lowered if match_all else wanted & lowered):
            continue
        entity_uuid = UUID(entity_id)
        if (test := tests_by_id.get(entity_uuid)) and test.enabled:
            selected[test.id] = test
        elif (group := scope.groups.get(entity_uuid)) and group.enabled:
            selected.update({test.id: test for test in scope.tests if test.group_id == group.id and test.enabled})
    if not selected:
        listed = ", ".join(sorted(available)) or "none"
        raise TestReferenceError(f"No test of the plan {plan.name} carries {', '.join(labels)}; "
                                 f"its labels are: {listed}")
    return sorted(selected.values(), key=scope.label)


def _field(issue, *names: str):
    data = issue.model_dump() if hasattr(issue, "model_dump") else dict(issue)
    return next((data[name] for name in names if data.get(name) is not None), None)


async def propose_link(entity: ChatEntity, run_reference: str, url: str) -> dict:
    if not url.startswith(("http://", "https://")):
        raise ToolScopeError("An issue is linked by its URL")
    run = await resolve_run_reference(entity, await load_scope(entity), run_reference)
    return new_action("link_issue", {"run_id": str(run.id), "test_id": str(run.test_id), "issue_url": url,
                                     "run_url": run_url(run)})


async def propose_unlink(entity: ChatEntity, run_reference: str, reference: str) -> dict:
    run = await resolve_run_reference(entity, await load_scope(entity), run_reference)
    wanted = reference.strip().lower()
    for issue in await IssueService().get(filter_key="run_id", filter_id=run.id):
        names = {str(_field(issue, name) or "").lower() for name in ("key", "url", "number", "id")}
        if wanted in names or wanted.lstrip("#") in names:
            return new_action("unlink_issue", {
                "run_id": str(run.id), "test_id": str(run.test_id), "run_url": run_url(run),
                "issue_id": str(_field(issue, "id")),
                "issue_key": _field(issue, "key", "number"), "issue_url": _field(issue, "url")})
    raise ToolScopeError(f"The run {run_reference} has no issue {reference}")


def run_version(run) -> str | None:
    return getattr(run, "scylla_version", None) or getattr(run, "product_version", None)


def zeus_prompt(run, test_label: str, release_name: str, entity: ChatEntity, user: User,
                question: str | None) -> str:
    version = run_version(run) or "no version"
    prompt = (f"Investigate the test run {run.id} ({test_label}, {run.status}, {version}) of the release "
              f"{release_name}. Requested by {user.full_name or user.username} from the Argus chat of "
              f"{entity.name}.")
    return f"{prompt}\n\n{question.strip()}" if question and question.strip() else prompt


async def propose_investigation(entity: ChatEntity, user: User, run_references: list[str],
                                question: str | None) -> dict:
    if len(run_references) > ZEUS_RUN_LIMIT:
        raise ToolScopeError(f"Zeus takes at most {ZEUS_RUN_LIMIT} runs per request, since it answers one at a "
                             "time; pick the most important runs")
    scope = await load_scope(entity)
    tests = {test.id: test for test in scope.tests}
    runs, rejected, seen = [], [], set()
    for reference in run_references:
        try:
            run = await resolve_run_reference(entity, scope, reference)
        except (ToolScopeError, TestReferenceError) as exception:
            rejected.append({"test": reference, "reason": str(exception)})
            continue
        if run.id in seen:
            continue
        seen.add(run.id)
        test = tests.get(run.test_id)
        label = scope.label(test) if test else str(run.test_id)
        release = scope.releases.get(run.release_id)
        runs.append({"run_id": str(run.id), "test_id": str(run.test_id), "url": run_url(run), "test": label,
                     "status": run.status,
                     "version": run_version(run),
                     "prompt": zeus_prompt(run, label, release.name if release else "", entity, user, question)})
    return new_action("zeus_investigation", {"runs": runs, "question": question}, rejected)


def refresh_due(refreshed_at: str | None, now: datetime) -> bool:
    if not refreshed_at:
        return True
    return now - datetime.fromisoformat(refreshed_at) >= timedelta(seconds=ZEUS_REFRESH_SECONDS)


async def refresh_zeus(entity: ChatEntity, card: ChatHistory, force: bool = False) -> dict:
    """Re-read the open Zeus tasks of a confirmed card, at most every ZEUS_REFRESH_SECONDS."""
    action = json.loads(card.action)
    if action["kind"] != "zeus_investigation" or card.action_state != "done":
        return action
    pending = [result for result in action["results"]
               if result.get("task_id") and result.get("status") in ZEUS_OPEN_STATES]
    now = datetime.now(UTC)
    if not pending or not (force or refresh_due(action.get("refreshed_at"), now)):
        return action
    client = ZeusClient()
    for result in pending:
        try:
            task = await client.status(result["task_id"])
        except ZeusError as exception:
            result["refresh_error"] = str(exception)
            continue
        result.update(status=task.get("status"), response=task.get("response"), error=task.get("error"),
                      started_at=task.get("started_at"), completed_at=task.get("completed_at"), refresh_error=None)
    action["refreshed_at"] = now.isoformat()
    await ChatHistoryService(entity).flush(card, action=_json(action))
    return action


async def zeus_cards(entity: ChatEntity) -> list[ChatHistory]:
    return [node for node in await ChatHistoryService(entity).nodes()
            if node.role == "action" and node.action and node.action_state == "done"
            and json.loads(node.action)["kind"] == "zeus_investigation"]


async def _queue_investigations(action: dict) -> list[dict]:
    client = ZeusClient()
    results = []
    for run in action["proposal"]["runs"]:
        result = {"run_id": run["run_id"], "test": run["test"], "task_id": None, "status": "queued",
                  "response": None, "error": None, "started_at": None, "completed_at": None}
        try:
            result["task_id"] = await client.investigate(run["prompt"])
        except ZeusError as exception:
            result.update(status="failed", error=str(exception))
        results.append(result)
    action["refreshed_at"] = datetime.now(UTC).isoformat()
    return results


async def locate_card(entity: ChatEntity, node: UUID) -> ChatHistory:
    card = await ChatHistory.find_one(entity_id=entity.id, node=node)
    if card is None or card.role != "action":
        raise ChatActionError(f"No action card {node} in this chat")
    return card


async def claim(entity: ChatEntity, node: UUID, user: User, state: str,
                auto: bool = False) -> tuple[ChatHistory, dict]:
    card = await locate_card(entity, node)
    if card.hidden:
        raise ChatActionError("This card belongs to an undone question")
    stored_state = card.action_state
    result = await card.update(if_conditions={"action_state": "pending"}, action_state=state)
    if not result.applied:
        current = (result.existing or {}).get("action_state") or stored_state
        raise ChatActionError(f"This card is already {current}")
    card = await locate_card(entity, node)
    action = json.loads(card.action)
    now = datetime.now(UTC)
    if state == "running":
        action.update(confirmed_by=user.id, confirmed_at=now, auto=auto)
    else:
        action.update(dismissed_by=user.id)
    await ChatHistoryService(entity).flush(card, action=_json(action))
    return card, json.loads(card.action)


async def _start_job(jenkins: JenkinsService, test: dict, user: User) -> dict:
    result = {"build_system_id": test["build_system_id"], "test": test["test"], "queue_item": None,
              "build_number": None, "error": None}
    try:
        result["queue_item"] = await jenkins.build_job(build_id=test["build_system_id"], params=test["params"],
                                                       requested_by=user)
        number = await jenkins.next_build_number(build_id=test["build_system_id"])
        result["build_number"] = number if number and number > 0 else None
    except Exception as exception:  # noqa: BLE001 - the card shows each test's failure
        LOGGER.warning("The chat could not start %s", test["build_system_id"], exc_info=True)
        result["error"] = str(exception)
    return result


async def execute(entity: ChatEntity, card: ChatHistory, action: dict, user: User) -> dict:
    proposal = action["proposal"]
    try:
        match action["kind"]:
            case "execute_tests":
                jenkins = JenkinsService()
                results = await gather_limited((_start_job(jenkins, test, user) for test in proposal["tests"]),
                                               limit=JOB_CONCURRENCY)
            case "link_issue":
                issue = await IssueService().submit(issue_url=proposal["issue_url"], test_id=UUID(proposal["test_id"]),
                                                    run_id=UUID(proposal["run_id"]), user=user)
                results = [{"issue": issue, "error": None}]
            case "zeus_investigation":
                results = await _queue_investigations(action)
            case "post_comment":
                await TestRunService().post_run_comment(test_id=UUID(proposal["test_id"]),
                                                        run_id=UUID(proposal["run_id"]), message=proposal["message"],
                                                        reactions={}, mentions=[], user=user)
                results = [{"test": proposal["test"], "error": None}]
            case "mcp_call":
                text, failed = await McpServerService().call(proposal["server"], proposal["tool"],
                                                             proposal["arguments"])
                results = [{"server": proposal["server"], "tool": proposal["tool"],
                            "text": text[:MCP_RESULT_LIMIT], "error": text[:500] if failed else None}]
            case "edit_plan":
                plan = await ArgusReleasePlan.get(id=UUID(proposal["plan_id"]))
                if plan_stamp(plan) != proposal["last_updated"]:
                    raise ChatActionError("The plan changed since this was proposed; ask for the edit again")
                await PlanningService().update_plan(plan_diff_payload(proposal["diff"]), user)
                results = [{"plan": proposal["plan"], "error": None}]
            case "unlink_issue":
                await IssueService().delete(issue_id=UUID(proposal["issue_id"]), run_id=UUID(proposal["run_id"]),
                                            user=user)
                results = [{"issue": proposal["issue_key"], "error": None}]
            case kind:
                results = [{"error": f"Unknown action {kind}"}]
    except asyncio.CancelledError:
        action["results"] = [{"error": "The server stopped while this card ran; check which of it started"}]
        await ChatHistoryService(entity).flush(card, action=_json(action), action_state="done")
        raise
    except Exception as exception:  # noqa: BLE001 - the card records the failure
        LOGGER.warning("The chat action %s failed", card.node, exc_info=True)
        results = [{"error": str(exception)}]
    action["results"] = results
    await ChatHistoryService(entity).flush(card, action=_json(action), action_state="done")
    return action
