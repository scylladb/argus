import functools
import json
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from coodie.exceptions import DocumentNotFound
from pydantic import BaseModel, BeforeValidator, Field, ValidationError

from argus.backend.error_handlers import APIException
from argus.backend.models.web import ArgusEvent, ArgusTest, ArgusUserView, User
from argus.backend.plugins.core import PluginModelBase
from argus.backend.plugins.sct.service import SCTService
from argus.backend.plugins.sct.testrun import SCTEvent, SCTEventSeverity
from argus.backend.service.chat import sct_params
from argus.backend.service.chat.actions import (
    Seed,
    adjust_start,
    job_parameters,
    new_action,
    plans_in_scope,
    propose_investigation,
    propose_link,
    propose_start,
    propose_unlink,
    refresh_zeus,
    resolve_labeled_tests,
    resolve_plan,
    zeus_cards,
)
from argus.backend.service.chat.entity import ChatEntity
from argus.backend.service.chat.history import ChatHistoryService
from argus.backend.service.chat.llm import ToolCall, ToolSpec
from argus.backend.service.chat.mcp import McpServerService, chat_tool_name
from argus.backend.service.chat.memory import ChatMemoryService
from argus.backend.service.chat.people import load_people, person
from argus.backend.service.chat.plans import PlanChanges, build_plan_diff, plan_labels, plan_stamp
from argus.backend.service.chat.prompt import truncate
from argus.backend.service.chat.resolve import (
    EXPANSION_LIMIT,
    Scope,
    TestReferenceError,
    ToolScopeError,
    load_scope,
    resolve_release,
    resolve_run_reference,
    resolve_test_reference,
    resolve_tests,
    run_url,
)
from argus.backend.service.chat.skills import SkillService
from argus.backend.service.issue_service import IssueService
from argus.backend.service.jenkins_service import JenkinsService
from argus.backend.service.release_summary import ReleaseSummaryService
from argus.backend.service.testrun import TestRunService
from argus.backend.service.zeus_client import ZeusClient
from argus.backend.util.common import select_rows
from argus.backend.util.encoders import ArgusJSONEncoder
from argus.common.versions import parse_version

LOGGER = logging.getLogger(__name__)
SUMMARY_TEST_LIMIT = 60
RELEASE_TEST_LIMIT = 300
VIEW_TEST_LIMIT = 100
COMMENT_LIMIT = 3
STATUS_GROUPS = {
    "failed": {"failed", "test_error", "error"},
    "passed": {"passed"},
    "aborted": {"aborted"},
    "in_progress": {"created", "running"},
}


@dataclass(slots=True)
class ToolContext:
    entity: ChatEntity
    user: User
    node: UUID


@dataclass(slots=True)
class ToolOutcome:
    content: str
    error: bool = False
    action: dict | None = None
    card_state: str = "pending"


def always() -> bool:
    return True


@dataclass(slots=True, frozen=True)
class Tool:
    spec: ToolSpec
    args: type[BaseModel]
    run: Callable[[ToolContext, BaseModel], Awaitable[object]]
    available: Callable[[], bool] = always


TOOLS: dict[str, Tool] = {}


def _as_list(value: object) -> object:
    return [value] if isinstance(value, str) else value


StringList = Annotated[list[str], BeforeValidator(_as_list)]


def tool(name: str, description: str, args: type[BaseModel], available: Callable[[], bool] = always):
    def register(run):
        schema = args.model_json_schema()
        schema.pop("title", None)
        TOOLS[name] = Tool(ToolSpec(name, description, schema), args, run, available)
        return run
    return register


@dataclass(slots=True, frozen=True)
class ExternalTool:
    """A tool that exists for one answer only, such as an MCP server's tool: its spec carries the schema the
    model sees, and its arguments go to ``run`` unvalidated."""
    spec: ToolSpec
    run: Callable[[ToolContext, dict], Awaitable[object]]


@dataclass(slots=True, frozen=True)
class Toolbox:
    """The tools of one answer: the available built-in tools without the hidden ones, then the external ones."""
    hidden: frozenset[str] = frozenset()
    external: tuple[ExternalTool, ...] = ()

    def builtin(self, name: str) -> Tool | None:
        entry = TOOLS.get(name)
        return entry if entry and entry.available() and name not in self.hidden else None

    def find_external(self, name: str) -> ExternalTool | None:
        return next((entry for entry in self.external if entry.spec.name == name), None)

    def specs(self) -> list[ToolSpec]:
        return [entry.spec for name, entry in TOOLS.items() if self.builtin(name)] + [
            entry.spec for entry in self.external]


def tool_specs(box: Toolbox = Toolbox()) -> list[ToolSpec]:
    return box.specs()


async def mcp_tools() -> tuple[ExternalTool, ...]:
    """The tools of the enabled MCP servers that an administrator switched on, from their stored lists."""
    taken = set(TOOLS)
    tools = []
    for entry in await McpServerService().enabled_tools():
        name = chat_tool_name(entry.server, entry.tool.name, taken)
        taken.add(name)
        description = f"[{entry.server}] {entry.tool.description}".strip()
        if entry.mode == "confirm":
            description += " A user confirms each call."
        schema = entry.tool.input_schema or {"type": "object", "properties": {}}
        tools.append(ExternalTool(ToolSpec(name, description, schema),
                                  functools.partial(run_mcp_tool, server=entry.server, tool=entry.tool.name,
                                                    mode=entry.mode)))
    return tuple(tools)


async def run_mcp_tool(ctx: ToolContext, arguments: dict, *, server: str, tool: str, mode: str) -> ToolOutcome:
    if mode == "confirm":
        return proposal_outcome(new_action("mcp_call", {"server": server, "tool": tool, "arguments": arguments}))
    text, error = await McpServerService().call(server, tool, arguments)
    return ToolOutcome(truncate(text) or "(no output)", error=error)


def to_json(value: object) -> str:
    return json.dumps(value, cls=ArgusJSONEncoder, ensure_ascii=False)


async def run_tool(ctx: ToolContext, call: ToolCall, box: Toolbox = Toolbox()) -> ToolOutcome:
    entry = box.builtin(call.name)
    external = None if entry else box.find_external(call.name)
    if entry is None and external is None:
        offered = ", ".join(spec.name for spec in box.specs())
        return ToolOutcome(f"There is no tool {call.name}. Available: {offered}", error=True)
    try:
        raw = json.loads(call.arguments or "{}")
        args = entry.args.model_validate(raw) if entry else raw
        if not isinstance(args, (dict, BaseModel)):
            raise ValueError("the arguments must be a JSON object")
    except (json.JSONDecodeError, ValidationError, ValueError) as exception:
        return ToolOutcome(f"Invalid arguments for {call.name}: {exception}", error=True)
    try:
        result = await (entry.run(ctx, args) if entry else external.run(ctx, args))
    except (ToolScopeError, TestReferenceError, APIException) as exception:
        return ToolOutcome(str(exception), error=True)
    except Exception as exception:  # noqa: BLE001 - the model gets the failure and can recover
        LOGGER.exception("Chat tool %s failed", call.name)
        return ToolOutcome(f"The tool {call.name} failed: {exception.__class__.__name__}: {exception}", error=True)
    if isinstance(result, ToolOutcome):
        return result
    return ToolOutcome(truncate(to_json(result)))


def _status_matches(status: str, wanted: set[str] | None) -> bool:
    if not wanted:
        return True
    return any(status in STATUS_GROUPS.get(group, {group}) for group in wanted)


async def entity_summaries(entity: ChatEntity, scope: Scope | None = None) -> list[dict]:
    service = ReleaseSummaryService()
    if entity.test_ids is None:
        return [await service.get(release_id) for release_id in entity.release_ids]
    scope = scope or await load_scope(entity)
    by_release: dict[UUID, set[UUID]] = defaultdict(set)
    for test in scope.tests:
        by_release[test.release_id].add(test.id)
    return [await service.get(release_id, test_ids) for release_id, test_ids in by_release.items()]


class SummaryArgs(BaseModel):
    version: str | None = Field(None, description="A version such as 2025.1.0~rc2; its tests are listed")
    family: str | None = Field(None, description="A final version such as 2025.1.0, with its rcs")
    statuses: StringList | None = Field(None, description="Only list tests in these states: failed, passed, "
                                                         "aborted, in_progress")


@tool("get_summary", "The release summary: counts per version family and version, and with a version or "
                     "statuses, the tests of each version with their latest status.", SummaryArgs)
async def get_summary(ctx: ToolContext, args: SummaryArgs) -> dict:
    wanted = set(args.statuses or []) or None
    list_tests = bool(args.version or wanted)
    releases = []
    for summary in await entity_summaries(ctx.entity):
        families = []
        for family in summary["families"]:
            if args.family and family["family"] != args.family:
                continue
            versions = [version for version in family["versions"]
                        if not args.version or version["version"] == args.version]
            if args.version and not versions:
                continue
            entries = []
            for version in versions:
                entry = {"version": version["version"], "counts": version["counts"]}
                if list_tests:
                    entry["tests"] = [
                        {"test": test["test_name"], "group": test["group_name"], "status": test["status"],
                         "run_id": test["run_id"], "build_number": test["build_number"]}
                        for test in version["tests"] if _status_matches(test["status"], wanted)
                    ][:SUMMARY_TEST_LIMIT]
                entries.append(entry)
            open_issues = [{"key": issue["key"], "title": issue["title"], "novelty": issue["novelty"]}
                           for issue in family["rollup"]["issues"] if issue["status"] == "open"]
            families.append({"family": family["family"], "rollup": family["rollup"]["counts"],
                             "versions": entries, "open_issues": open_issues if list_tests or args.family else
                             len(open_issues)})
        releases.append({"release": summary["release_name"], "families": families,
                         "findings": [finding["content"] for finding in summary.get("findings", [])]})
    return {"releases": releases}


class ReleaseArgs(BaseModel):
    release: str | None = Field(None, description="A release id, name or pretty name; defaults to every release "
                                                  "of this chat")


@tool("read_release", "The enabled groups and tests of a release in this chat, with each test's Jenkins job "
                      "(build_system_id).", ReleaseArgs)
async def read_release(ctx: ToolContext, args: ReleaseArgs) -> dict:
    scope = await load_scope(ctx.entity)
    releases = [resolve_release(scope, args.release)] if args.release else list(scope.releases.values())
    release_ids = {release.id for release in releases}
    tests = [test for test in scope.tests if test.release_id in release_ids and test.enabled
             and scope.groups.get(test.group_id) and scope.groups[test.group_id].enabled]
    result = {
        "name": releases[0].name if len(releases) == 1 else None,
        "releases": [release.name for release in releases],
        "groups": sorted({scope.groups[test.group_id].name for test in tests}),
        "tests": [{"name": test.name, "group": scope.groups[test.group_id].name, "test_id": test.id,
                   "build_system_id": test.build_system_id, "release": scope.releases[test.release_id].name}
                  for test in sorted(tests, key=scope.label)][:RELEASE_TEST_LIMIT],
    }
    if len(tests) > RELEASE_TEST_LIMIT:
        result["truncated"] = f"{len(tests) - RELEASE_TEST_LIMIT} more tests not shown"
    return result


class NoArgs(BaseModel):
    pass


@tool("read_view", "The view of this chat: its description, releases, plan, and tests.", NoArgs)
async def read_view(ctx: ToolContext, args: NoArgs) -> dict:
    if ctx.entity.type != "view":
        raise ToolScopeError(f"This chat belongs to the release {ctx.entity.name}, not to a view")
    view = await ArgusUserView.get(id=ctx.entity.id)
    scope = await load_scope(ctx.entity)
    labels = sorted(scope.label(test) for test in scope.tests)
    return {"name": view.display_name or view.name, "description": view.description, "plan_id": view.plan_id,
            "releases": sorted(release.name for release in scope.releases.values()),
            "test_count": len(labels), "tests": labels[:VIEW_TEST_LIMIT]}


class RunsArgs(BaseModel):
    test: str = Field(description="A test id, name, pretty name, group/test, release/group/test, Jenkins job "
                                  "path or URL")
    version: str | None = Field(None, description="Only runs of this version, such as 2025.1.0~rc4")
    limit: int = Field(10, ge=1, le=20)


RUN_FIELDS = ("id", "status", "build_number", "start_time", "end_time", "investigation_status", "build_job_url")
RUN_COLUMNS = (*RUN_FIELDS, "assignee", "scylla_version", "product_version")
RUN_SCAN_LIMIT = 200


def normalized_version(raw: str | None) -> str | None:
    parsed = parse_version(raw)
    return str(parsed) if parsed else raw


@tool("get_runs", "The most recent runs of one test, newest first, with the version of each run.", RunsArgs)
async def get_runs(ctx: ToolContext, args: RunsArgs) -> dict:
    scope = await load_scope(ctx.entity)
    test = resolve_test_reference(scope, args.test)
    plugin = TestRunService().get_plugin(plugin_name=test.plugin_name)
    if plugin is None:
        raise ToolScopeError(f"The test {scope.label(test)} has no runs plugin")
    scan = RUN_SCAN_LIMIT if args.version else args.limit
    rows = await select_rows(plugin.model.find(build_id=test.build_system_id).limit(scan), *RUN_COLUMNS)
    wanted = normalized_version(args.version) if args.version else None
    runs = []
    for row in rows:
        version = normalized_version(row["scylla_version"] or row["product_version"])
        if wanted and version != wanted:
            continue
        runs.append({**{key: row[key] for key in RUN_FIELDS}, "version": version, "assignee": row["assignee"]})
        if len(runs) == args.limit:
            break
    people = await load_people(run["assignee"] for run in runs)
    for run in runs:
        run["assignee"] = person(run["assignee"], people)
    return {"test": scope.label(test), "runs": runs}


RUN_REFERENCE = "A run id, build_id#number, a test reference with #number, or a Jenkins build URL"


class RunArgs(BaseModel):
    run: str = Field(description=RUN_REFERENCE)


def _issue_entry(issue) -> dict:
    data = issue.model_dump() if hasattr(issue, "model_dump") else dict(issue)
    return {"key": data.get("key") or data.get("number"), "title": data.get("title") or data.get("summary"),
            "url": data.get("url") or data.get("permalink"), "state": data.get("state") or data.get("status")}


@tool("read_run", "One test run: status, build, version, linked issues, and its latest comments.", RunArgs)
async def read_run(ctx: ToolContext, args: RunArgs) -> dict:
    service = TestRunService()
    run = await resolve_run_reference(ctx.entity, await load_scope(ctx.entity), args.run)
    run_type = await service.get_test_type_for_run(run.id)
    try:
        test = await ArgusTest.get(id=run.test_id)
    except DocumentNotFound:
        test = None
    issues = await IssueService().get(filter_key="run_id", filter_id=run.id)
    comments = (await service.get_run_comments(run.id))[-COMMENT_LIMIT:]
    people = await load_people([run.assignee, *(comment.user_id for comment in comments)])
    events = await sct_error_digest(run.id) if run_type == SCT_PLUGIN_NAME else None
    return {
        "id": run.id, "test": test.name if test else None, "status": run.status,
        "investigation_status": run.investigation_status, "build_id": run.build_id,
        "build_number": getattr(run, "build_number", None), "build_job_url": run.build_job_url,
        "version": getattr(run, "scylla_version", None) or getattr(run, "product_version", None),
        "start_time": run.start_time, "end_time": run.end_time, "assignee": person(run.assignee, people),
        "issues": [_issue_entry(issue) for issue in issues],
        "events": events,
        "comments": [{"author": person(comment.user_id, people), "message": truncate(comment.message, 500),
                      "posted_at": comment.posted_at} for comment in comments],
    }


class PlanArgs(BaseModel):
    plan: str | None = Field(None, description="Plan id, key (release#n) or name; defaults to every plan")


@tool("get_plan", "Release plans of this chat: target version, tests, groups, and the labels of each.", PlanArgs)
async def get_plan(ctx: ToolContext, args: PlanArgs) -> dict:
    scope = await load_scope(ctx.entity)
    plans = await plans_in_scope(scope)
    if args.plan:
        plans = [resolve_plan(plans, args.plan)]
    tests_by_id = {test.id: test for test in scope.tests}
    people = await load_people(user_id for plan in plans
                               for user_id in (plan.owner, *plan.participants, *plan.assignee_mapping.values()))
    result = []
    for plan in plans:
        options = json.loads(plan.options) if plan.options else {}
        result.append({
            "id": plan.id, "key": plan.key, "name": plan.name, "target_version": plan.target_version,
            "completed": plan.completed, "release": scope.releases[plan.release_id].name,
            "owner": person(plan.owner, people), "participants": [person(user, people) for user in plan.participants],
            "tests": [{"name": tests_by_id[test_id].name, "group": scope.group_name(tests_by_id[test_id]),
                       "labels": options.get(str(test_id), {}).get("labels", []),
                       "assignee": planned_assignee(plan, test_id, people)}
                      for test_id in plan.tests if test_id in tests_by_id],
            "groups": [{"name": scope.groups[group_id].name,
                        "labels": options.get(str(group_id), {}).get("labels", []),
                        "assignee": planned_assignee(plan, group_id, people)}
                       for group_id in plan.groups if group_id in scope.groups],
        })
    return {"plans": result}


class PlanLabelsArgs(BaseModel):
    plan: str = Field(description="Plan id, key (release#n) or name")


@tool("get_plan_labels", "Every label of a release plan with the tests and groups that carry it, and whether "
                         "each is enabled. Use execute_plan_tests with dry_run to see what a selection starts.",
      PlanLabelsArgs)
async def get_plan_labels(ctx: ToolContext, args: PlanLabelsArgs) -> dict:
    scope = await load_scope(ctx.entity)
    return plan_labels(resolve_plan(await plans_in_scope(scope), args.plan), scope)


ENTITY = "test or group reference"


class EditPlanArgs(BaseModel):
    plan: str = Field(description="Plan id, key (release#n) or name")
    add_tests: StringList = Field(default_factory=list, description=f"Tests to add; a {ENTITY} (a group adds its "
                                                                     "enabled tests)")
    remove_tests: StringList = Field(default_factory=list, description=f"Tests to remove; a {ENTITY}")
    remove_groups: StringList = Field(default_factory=list, description="Groups of the plan to remove")
    assign: dict[str, str] = Field(default_factory=dict,
                                   description=f"{{{ENTITY}: username or full name}}; $owner unassigns")
    unassign: StringList = Field(default_factory=list, description="Entities that go back to the plan owner")
    add_labels: dict[str, StringList] = Field(default_factory=dict, description=f"{{{ENTITY}: [labels]}}")
    remove_labels: dict[str, StringList] = Field(default_factory=dict, description=f"{{{ENTITY}: [labels]}}")
    name: str | None = None
    description: str | None = None
    target_version: str | None = None
    completed: bool | None = None


@tool("edit_plan", "Propose an edit of a release plan: add or remove tests, remove groups, assign or unassign, "
                   "add or remove labels, rename, change the description or the target version, mark it "
                   "completed. A user confirms the card.", EditPlanArgs)
async def edit_plan(ctx: ToolContext, args: EditPlanArgs) -> ToolOutcome:
    scope = await load_scope(ctx.entity)
    plan = resolve_plan(await plans_in_scope(scope), args.plan)
    changes = PlanChanges(**args.model_dump(exclude={"plan"}))
    diff, summary = await build_plan_diff(plan, scope, changes)
    proposal = {"plan_id": str(plan.id), "plan": plan.name, "key": plan.key, "last_updated": plan_stamp(plan),
                "diff": diff, "summary": summary}
    return proposal_outcome(new_action("edit_plan", proposal))


class LoadSkillArgs(BaseModel):
    name: str = Field(description="The skill's name, as the system prompt lists it")


@tool("load_skill", "Load the full text of an on-demand skill that the system prompt lists.", LoadSkillArgs)
async def load_skill(ctx: ToolContext, args: LoadSkillArgs) -> dict:
    skills = (await SkillService().prompt_setup()).on_demand
    skill = next((skill for skill in skills if skill.name.lower() == args.name.strip().lower()), None)
    if skill is None:
        raise ToolScopeError(f"No on-demand skill {args.name}; the skills are "
                             f"{', '.join(skill.name for skill in skills) or 'none'}")
    return {"skill": skill.name, "content": skill.content}


class ReadMemoryArgs(BaseModel):
    query: str | None = Field(None, description="Only memories containing this text")


@tool("read_memory", "The memories of this chat: conventions (notes) and findings, with their ids.",
      ReadMemoryArgs)
async def read_memory(ctx: ToolContext, args: ReadMemoryArgs) -> dict:
    memories = await ChatMemoryService().in_scope(ctx.entity)
    if args.query:
        memories = [memory for memory in memories if args.query.lower() in memory["content"].lower()]
    people = await load_people(memory["updated_by"] for memory in memories)
    return {"memories": [{"id": memory["id"], "kind": memory["kind"], "content": memory["content"],
                          "scope": f"{memory['entity_type']} {memory['entity_name']}",
                          "author": person(memory["updated_by"], people)} for memory in memories]}


class WriteMemoryArgs(BaseModel):
    op: Literal["add", "update", "delete"]
    memory_id: UUID | None = Field(None, description="Required to update or delete")
    content: str | None = None
    kind: Literal["note", "finding"] | None = Field(None, description="note: a convention; finding: shows in "
                                                                      "the release summary")
    scope: str | None = Field(None, description="In a view chat, a release name to store it on that release")


@tool("write_memory", "Add, update or delete a memory. Users can revert any change.", WriteMemoryArgs)
async def write_memory(ctx: ToolContext, args: WriteMemoryArgs) -> dict:
    service = ChatMemoryService()
    match args.op:
        case "add":
            scope = None
            if args.scope and ctx.entity.type == "view":
                scope = (await load_scope(ctx.entity)).release_named(args.scope).id
            memory = await service.create(ctx.entity, args.content or "", args.kind or "note", ctx.user,
                                          scope=scope, source_node=ctx.node)
        case "update":
            if args.memory_id is None:
                raise ToolScopeError("memory_id is required to update a memory")
            memory = await service.update(ctx.entity, args.memory_id, ctx.user, content=args.content,
                                          kind=args.kind, source_node=ctx.node)
        case _:
            if args.memory_id is None:
                raise ToolScopeError("memory_id is required to delete a memory")
            memory = await service.delete(ctx.entity, args.memory_id, ctx.user, source_node=ctx.node)
            return {"deleted": memory["id"]}
    return {"id": memory["id"], "kind": memory["kind"], "content": memory["content"],
            "scope": f"{memory['entity_type']} {memory['entity_name']}"}


def proposal_outcome(action: dict) -> ToolOutcome:
    empty = {"execute_tests": "tests", "zeus_investigation": "runs"}.get(action["kind"])
    if empty and not action["proposal"][empty]:
        reasons = "; ".join(f"{entry['test']}: {entry['reason']}" for entry in action["rejected"])
        return ToolOutcome(f"Nothing can be proposed. {reasons}", error=True)
    summary = {
        "status": "awaiting_confirmation",
        "note": "Argus shows this proposal to the users as a card. Nothing happens until one of them confirms "
                "it. Tell the user to confirm the card, and list what it does.",
        "kind": action["kind"],
    }
    if action["kind"] == "execute_tests":
        summary["note"] += " To change its parameters before it runs, call adjust_run_params."
        summary["proposed"] = [{"test": test["test"], "overrides": test["overrides"], "seed": test["seed"],
                                "build_number": test["build_number"]} for test in action["proposal"]["tests"]]
        summary["rejected"] = action["rejected"]
    elif action["kind"] == "zeus_investigation":
        summary["proposed"] = [{"run_id": run["run_id"], "test": run["test"]} for run in action["proposal"]["runs"]]
        summary["rejected"] = action["rejected"]
        summary["note"] += (" Zeus answers one investigation at a time, each in up to 30 minutes; the card shows "
                            "each report when it is done.")
    elif action["kind"] == "mcp_call":
        summary.update(server=action["proposal"]["server"], tool=action["proposal"]["tool"])
    elif action["kind"] == "edit_plan":
        summary["plan"] = action["proposal"]["plan"]
        summary["changes"] = action["proposal"]["summary"]
    else:
        summary["proposal"] = action["proposal"]
    return ToolOutcome(to_json(summary), action=action)


SEED_DESCRIPTION = ("Where the parameters come from before the overrides: last_build (default), defaults (the "
                    "job's configured defaults), or build (with build_number)")


class StartArgs(BaseModel):
    params: dict[str, str] = Field(default_factory=dict,
                                   description="Job parameters to override for every test, e.g. {\"backend\": \"gce\"}")
    per_test: dict[str, dict[str, str]] = Field(default_factory=dict,
                                                description="Overrides for single tests, by test reference; they "
                                                            "win over params")
    seed: Literal["last_build", "defaults", "build"] | None = Field(None, description=SEED_DESCRIPTION)
    build_number: int | None = Field(None, description="The build to take the parameters from, with seed build")


def per_test_overrides(scope: Scope, per_test: dict[str, dict[str, str]]) -> dict[UUID, dict[str, str]]:
    return {resolve_test_reference(scope, reference).id: overrides for reference, overrides in per_test.items()}


class ExecuteTestsArgs(StartArgs):
    tests: StringList = Field(min_length=1, max_length=50,
                             description="Tests by id, name, pretty name, group/test, release/group/test, Jenkins "
                                         "job path or URL; a group or a release stands for its enabled tests")


@tool("execute_tests", "Propose starting tests in Jenkins with the parameters of their last build (or another "
                       "seed), overridden by params and per_test. Each override is checked against the job's "
                       "parameters and, for SCT jobs, the rules of the parameter wizard.", ExecuteTestsArgs)
async def execute_tests(ctx: ToolContext, args: ExecuteTestsArgs) -> ToolOutcome:
    scope = await load_scope(ctx.entity)
    seed = Seed.of(args.seed, args.build_number)
    tests, rejected = [], []
    for reference in args.tests:
        try:
            tests.extend(resolve_tests(scope, [reference]))
        except TestReferenceError as exception:
            rejected.append({"test": reference, "reason": str(exception)})
    if len({test.id for test in tests}) > EXPANSION_LIMIT:
        raise TestReferenceError(f"That is more than {EXPANSION_LIMIT} tests; name fewer tests or groups")
    action = await propose_start(scope, tests, args.params, rejected, per_test_overrides(scope, args.per_test), seed)
    return proposal_outcome(action)


class ExecutePlanArgs(StartArgs):
    plan: str = Field(description="Plan id, key (release#n) or name")
    labels: StringList = Field(min_length=1, description="Plan labels, such as week1")
    match_all: bool = Field(False, description="Only tests that carry every label")
    dry_run: bool = Field(False, description="Only list the tests the labels select; propose nothing")


@tool("execute_plan_tests", "Propose starting the tests of a release plan that carry the labels. A labelled "
                            "group stands for its tests. With dry_run, only list them.", ExecutePlanArgs)
async def execute_plan_tests(ctx: ToolContext, args: ExecutePlanArgs) -> ToolOutcome | dict:
    scope = await load_scope(ctx.entity)
    plan = resolve_plan(await plans_in_scope(scope), args.plan)
    tests = resolve_labeled_tests(scope, plan, args.labels, args.match_all)
    if args.dry_run:
        return {"plan": plan.name, "labels": args.labels, "match_all": args.match_all,
                "tests": [scope.label(test) for test in tests]}
    seed = Seed.of(args.seed, args.build_number)
    return proposal_outcome(await propose_start(scope, tests, args.params, [],
                                                per_test_overrides(scope, args.per_test), seed))


class JobParamsArgs(BaseModel):
    test: str = Field(description="Test reference")
    seed: Literal["last_build", "defaults", "build"] | None = Field(None, description=SEED_DESCRIPTION)
    build_number: int | None = Field(None, description="The build, with seed build")


@tool("get_job_params", "Read a test's Jenkins job parameters with their current values and allowed values, "
                        "grouped as the SCT parameter wizard groups them. Read it before overriding a parameter "
                        "you are not sure of.", JobParamsArgs)
async def get_job_params(ctx: ToolContext, args: JobParamsArgs) -> dict:
    scope = await load_scope(ctx.entity)
    test = resolve_test_reference(scope, args.test)
    if not test.build_system_id:
        raise ToolScopeError(f"{scope.label(test)} has no Jenkins job")
    seed = Seed.of(args.seed, args.build_number)
    job = await job_parameters(JenkinsService(), test, seed)
    params = {param["name"]: param.get("value") for param in job}
    groups: dict[str, list[dict]] = defaultdict(list)
    for field in sct_params.fields(params, job, test.plugin_name == SCT_PLUGIN_NAME):
        groups[field.pop("group")].append(field)
    return {"test": scope.label(test), **seed.as_json(), "groups": groups}


class AdjustArgs(BaseModel):
    card: UUID | None = Field(None, description="The start card; by default the latest pending one")
    tests: StringList = Field(default_factory=list, description="Only these tests of the card; by default all")
    set: dict[str, str] = Field(default_factory=dict, description="Parameters to override")
    unset: StringList = Field(default_factory=list, description="Overrides to drop, back to the seed's value")
    seed: Literal["last_build", "defaults", "build"] | None = Field(None, description=SEED_DESCRIPTION)
    build_number: int | None = Field(None, description="The build, with seed build")


async def latest_start_card(ctx: ToolContext) -> UUID:
    _, nodes = await ChatHistoryService(ctx.entity).read()
    pending = [node for node in nodes if node.role == "action" and node.action_state == "pending"
               and not node.hidden and json.loads(node.action)["kind"] == "execute_tests"]
    if not pending:
        raise ToolScopeError("There is no pending start card in this chat")
    return max(pending, key=lambda node: node.node.time).node


@tool("adjust_run_params", "Change the parameters of a pending start card before anyone confirms it: set or "
                           "unset overrides for all its tests or some, or take the parameters from another seed. "
                           "Every test is checked again; nothing changes if one fails.", AdjustArgs)
async def adjust_run_params(ctx: ToolContext, args: AdjustArgs) -> dict:
    node = args.card or await latest_start_card(ctx)
    only = None
    if args.tests:
        scope = await load_scope(ctx.entity)
        only = {str(resolve_test_reference(scope, reference).id) for reference in args.tests}
    seed = Seed.of(args.seed, args.build_number) if args.seed or args.build_number else None
    _, action = await adjust_start(ctx.entity, node, set_params=args.set, unset=list(args.unset), only=only,
                                   seed=seed)
    return {"status": "card updated", "card": node,
            "tests": [{"test": test["test"], "overrides": test["overrides"], "seed": test["seed"],
                       "build_number": test["build_number"]} for test in action["proposal"]["tests"]]}


class LinkArgs(BaseModel):
    run: str = Field(description=RUN_REFERENCE)
    url: str = Field(description="The issue URL")


@tool("link_issue", "Propose linking an issue to a test run.", LinkArgs)
async def link_issue(ctx: ToolContext, args: LinkArgs) -> ToolOutcome:
    return proposal_outcome(await propose_link(ctx.entity, args.run, args.url))


class UnlinkArgs(BaseModel):
    run: str = Field(description=RUN_REFERENCE)
    issue: str = Field(description="The issue key, number, or URL")


@tool("unlink_issue", "Propose removing an issue from a test run.", UnlinkArgs)
async def unlink_issue(ctx: ToolContext, args: UnlinkArgs) -> ToolOutcome:
    return proposal_outcome(await propose_unlink(ctx.entity, args.run, args.issue))


def planned_assignee(plan, entity_id: UUID, people) -> dict | None:
    return person(plan.assignee_mapping.get(entity_id, plan.owner), people)


def zeus_configured() -> bool:
    return ZeusClient().configured()


REPORT_LIMIT = 4000


class InvestigateArgs(BaseModel):
    runs: StringList = Field(min_length=1, description="The runs to investigate, at most 5, each as " +
                             RUN_REFERENCE[0].lower() + RUN_REFERENCE[1:])
    question: str | None = Field(None, description="What Zeus should focus on, in the user's words")


@tool("investigate_runs", "Propose asking Zeus, the test investigation agent, to investigate test runs. Zeus "
                          "reads the run's logs, events and issues and writes a report.", InvestigateArgs,
      available=zeus_configured)
async def investigate_runs(ctx: ToolContext, args: InvestigateArgs) -> ToolOutcome:
    return proposal_outcome(await propose_investigation(ctx.entity, ctx.user, args.runs, args.question))


class InvestigationArgs(BaseModel):
    run: str | None = Field(None, description="The run whose Zeus report to find: " + RUN_REFERENCE)


ZEUS_ACK = "queued autoinvestigation"
ZEUS_CHUNK_SECONDS = 300
ZEUS_CHUNK_HEADER = "## nemesis:"
DISCUSSION_MESSAGE_LIMIT = 3000


def is_zeus(user: User | None) -> bool:
    return bool(user and user.service_user and "zeus" in (user.username or "").lower())


def posted(comment) -> datetime:
    return datetime.fromtimestamp(comment.posted_at, UTC)


async def discussion_report(run) -> tuple[str, datetime, User] | None:
    """Zeus's latest report in the run's discussion; a long report arrives as consecutive comments."""
    comments = await TestRunService().get_run_comments(run.id)
    people = await load_people(comment.user_id for comment in comments)
    reports = [comment for comment in comments if is_zeus(people.get(comment.user_id))
               and comment.message.strip().lower() != ZEUS_ACK]
    if not reports:
        return None
    parts = [reports[-1]]
    for comment in reversed(reports[:-1]):
        if comment.user_id != parts[0].user_id or parts[0].posted_at - comment.posted_at > ZEUS_CHUNK_SECONDS:
            break
        parts.insert(0, comment)
    parts.sort(key=lambda part: (part.posted_at, part.message.lstrip().startswith(ZEUS_CHUNK_HEADER)))
    text = "\n\n".join(part.message.strip() for part in parts)
    return text, posted(parts[-1]), people[parts[-1].user_id]


@tool("get_investigation", "Zeus's report on a run: from the run's discussion, where Zeus posts its "
                           "investigations, or from an investigation queued in this chat. Without a run, the "
                           "state of every investigation queued in this chat. A report found in the discussion is "
                           "shown to the user as a card; summarize it, do not repeat it.", InvestigationArgs)
async def get_investigation(ctx: ToolContext, args: InvestigationArgs) -> ToolOutcome | dict:
    run = None
    if args.run:
        scope = await load_scope(ctx.entity)
        run = await resolve_run_reference(ctx.entity, scope, args.run)
    found = []
    for card in await zeus_cards(ctx.entity):
        action = await refresh_zeus(ctx.entity, card)
        for result in action["results"]:
            if run is None or result["run_id"] == str(run.id):
                found.append({"source": "chat", "run_id": result["run_id"], "test": result["test"],
                              "status": result["status"],
                              "response": truncate(result["response"], REPORT_LIMIT) if result.get("response")
                              else None,
                              "error": result.get("error"), "completed_at": result.get("completed_at")})
    card = None
    if run is not None and (report := await discussion_report(run)):
        text, at, author = report
        test = next((candidate for candidate in scope.tests if candidate.id == run.test_id), None)
        label = scope.label(test) if test else run.build_id
        found.append({"source": "discussion", "run_id": str(run.id), "test": label, "status": "completed",
                      "response": truncate(text, REPORT_LIMIT), "error": None, "completed_at": at})
        card = {"kind": "zeus_report", "rejected": [], "confirmed_by": None, "confirmed_at": None,
                "dismissed_by": None, "results": [],
                "proposal": {"run_id": str(run.id), "test": label, "build_number": run.build_number,
                             "url": run_url(run), "report": text, "posted_at": at,
                             "author": person(author.id, {author.id: author})}}
    if not found:
        raise ToolScopeError(f"No Zeus report for the run {args.run}: none in its discussion, and none queued "
                             "from this chat" if args.run else "No Zeus investigation was queued from this chat")
    if card is None:
        return {"investigations": found}
    return ToolOutcome(truncate(to_json({"investigations": found})), action=card, card_state="done")


class DiscussionArgs(BaseModel):
    run: str = Field(description=RUN_REFERENCE)
    limit: int = Field(20, ge=1, le=50, description="The latest comments to read")


@tool("get_comments", "The comments of a run with their authors, oldest first. Comments by Zeus are marked.",
      DiscussionArgs)
async def get_comments(ctx: ToolContext, args: DiscussionArgs) -> dict:
    run = await resolve_run_reference(ctx.entity, await load_scope(ctx.entity), args.run)
    comments = (await TestRunService().get_run_comments(run.id))[-args.limit:]
    people = await load_people(comment.user_id for comment in comments)
    return {"run_id": run.id, "comments": [
        {"author": person(comment.user_id, people), "zeus": is_zeus(people.get(comment.user_id)),
         "posted_at": posted(comment), "message": truncate(comment.message, DISCUSSION_MESSAGE_LIMIT)}
        for comment in comments]}


POST_COMMENT_LIMIT = 5000


class PostCommentArgs(BaseModel):
    run: str = Field(description=RUN_REFERENCE)
    message: str = Field(min_length=1, max_length=POST_COMMENT_LIMIT,
                         description="The comment in Markdown; @username mentions notify that user")


@tool("post_comment", "Propose posting a comment on a run. A user confirms the card, and the comment is posted "
                      "as that user.", PostCommentArgs)
async def post_comment(ctx: ToolContext, args: PostCommentArgs) -> ToolOutcome:
    scope = await load_scope(ctx.entity)
    run = await resolve_run_reference(ctx.entity, scope, args.run)
    test = next((test for test in scope.tests if test.id == run.test_id), None)
    proposal = {"run_id": str(run.id), "test_id": str(run.test_id),
                "test": scope.label(test) if test else str(run.test_id), "build_number": run.build_number,
                "run_url": run_url(run), "message": args.message.strip()}
    return proposal_outcome(new_action("post_comment", proposal))


USER_LIMIT = 50


class UsersArgs(BaseModel):
    user_ids: Annotated[list[UUID], BeforeValidator(_as_list)] = Field(min_length=1, max_length=USER_LIMIT)


@tool("get_users", "Name the Argus users behind user ids: their username and full name.", UsersArgs)
async def get_users(ctx: ToolContext, args: UsersArgs) -> dict:
    people = await load_people(args.user_ids)
    return {"users": [person(user_id, people) for user_id in dict.fromkeys(args.user_ids)]}


class AssigneesArgs(BaseModel):
    tests: StringList = Field(min_length=1, max_length=30,
                              description="Tests by id, name, pretty name, group/test, release/group/test, Jenkins "
                                          "job path or URL; a group stands for its enabled tests")
    version: str | None = Field(None, description="Only the plans that target this version")


@tool("get_assignees", "Who is assigned to tests: the assignee of each active release plan that holds the test "
                       "(its own or its group's), the test's and the group's assignees, and who the last run is "
                       "assigned to.", AssigneesArgs)
async def get_assignees(ctx: ToolContext, args: AssigneesArgs) -> dict:
    scope = await load_scope(ctx.entity)
    tests = resolve_tests(scope, args.tests)
    plans = [plan for plan in await plans_in_scope(scope) if PluginModelBase._is_plan_active(plan)
             and (not args.version or plan.target_version == args.version)]
    service = TestRunService()
    last_runs = {test.id: (await service.get_runs_by_test_id(test.id, [], None, None, False, 1) or [None])[0]
                 for test in tests}
    people = await load_people([
        *(user for plan in plans for user in (plan.owner, *plan.assignee_mapping.values())),
        *(user for test in tests for user in test.assignee),
        *(user for test in tests for user in getattr(scope.groups.get(test.group_id), "assignee", [])),
        *(run.get("assignee") for run in last_runs.values() if run),
    ])
    entries = []
    for test in tests:
        planned = []
        for plan in plans:
            if test.group_id in plan.groups:
                assignee = plan.assignee_mapping.get(test.group_id, plan.owner)
            elif test.id in plan.tests:
                assignee = plan.assignee_mapping.get(test.id, plan.owner)
            else:
                continue
            planned.append({"plan": plan.name, "target_version": plan.target_version,
                            "assignee": person(assignee, people)})
        group = scope.groups.get(test.group_id)
        run = last_runs[test.id]
        entries.append({
            "test": scope.label(test),
            "plans": planned,
            "test_assignees": [person(user, people) for user in test.assignee],
            "group_assignees": [person(user, people) for user in (group.assignee if group else [])],
            "last_run": {"id": run["id"], "status": run["status"], "build_number": run["build_number"],
                         "assignee": person(run.get("assignee"), people)} if run else None,
        })
    return {"tests": entries}


SCT_PLUGIN_NAME = "scylla-cluster-tests"
EVENT_MESSAGE_LIMIT = 800
DIGEST_EVENTS = 5
SERIOUS = [SCTEventSeverity.CRITICAL, SCTEventSeverity.ERROR]


def sct_event_entry(event: dict) -> dict:
    entry = {"ts": event["ts"], "severity": event["severity"], "type": event.get("event_type"),
             "node": event.get("node"), "nemesis": event.get("nemesis_name"),
             "message": truncate(event["message"], EVENT_MESSAGE_LIMIT)}
    if event.get("summary"):
        entry["summary"] = event["summary"]
    if event.get("duplicate_id"):
        entry["duplicate_of"] = event["duplicate_id"]
    return entry


async def sct_error_digest(run_id: UUID) -> dict:
    counts = {severity.value: await SCTEvent.find(run_id=run_id, severity=severity.value).count()
              for severity in SERIOUS}
    first = await SCTService.get_events(run_id, DIGEST_EVENTS, SERIOUS, None)
    return {"counts": counts, "first": [sct_event_entry(event) for event in first][:DIGEST_EVENTS]}


class RunEventsArgs(BaseModel):
    run: str = Field(description=RUN_REFERENCE)
    kind: Literal["test", "activity"] = Field("test", description="test: the events the test reported (SCT); "
                                                                  "activity: who changed the run in Argus")
    severities: Annotated[list[SCTEventSeverity], BeforeValidator(_as_list)] = Field(
        default_factory=lambda: list(SERIOUS), description="For test events: CRITICAL, ERROR, WARNING, NORMAL, DEBUG")
    limit: int = Field(20, ge=1, le=50, description="Events per severity")


@tool("get_run_events", "The events of one run: the test's own events (errors, criticals, nemeses of an SCT "
                        "run), or the run's activity in Argus (status, assignee, investigation, comments, issues).",
      RunEventsArgs)
async def get_run_events(ctx: ToolContext, args: RunEventsArgs) -> dict:
    run = await resolve_run_reference(ctx.entity, await load_scope(ctx.entity), args.run)
    if args.kind == "activity":
        events = sorted(await ArgusEvent.find(run_id=run.id).all(), key=lambda event: event.created_at)
        people = await load_people(event.user_id for event in events)
        return {"run_id": run.id, "events": [
            {"kind": event.kind, "at": event.created_at, "by": person(event.user_id, people),
             "details": truncate(event.body, EVENT_MESSAGE_LIMIT)} for event in events]}
    if await TestRunService().get_test_type_for_run(run.id) != SCT_PLUGIN_NAME:
        raise ToolScopeError("Only Scylla Cluster Tests runs report test events; use kind=activity for this run")
    events = await SCTService.get_events(run.id, args.limit, args.severities, None)
    return {"run_id": run.id, "events": [sct_event_entry(event) for event in events]}


@tool("show_run", "Show a run to the user as a card with a link that opens it in Argus.", RunArgs)
async def show_run(ctx: ToolContext, args: RunArgs) -> ToolOutcome:
    scope = await load_scope(ctx.entity)
    run = await resolve_run_reference(ctx.entity, scope, args.run)
    test = next((candidate for candidate in scope.tests if candidate.id == run.test_id), None)
    card = {"run_id": str(run.id), "test_id": str(run.test_id), "test": scope.label(test) if test else run.build_id,
            "build_number": run.build_number, "status": run.status,
            "version": getattr(run, "scylla_version", None) or getattr(run, "product_version", None),
            "url": run_url(run)}
    action = {"kind": "show_run", "proposal": card, "rejected": [], "confirmed_by": None, "confirmed_at": None,
              "dismissed_by": None, "results": []}
    return ToolOutcome(to_json({"shown": card, "note": "The user sees a card that opens this run."}), action=action,
                       card_state="done")
