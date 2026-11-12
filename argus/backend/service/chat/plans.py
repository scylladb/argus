"""Plan labels and plan edits from the chat, with the command line tool's rules
(cli/internal/services/planner.go: BuildUpdateRequest, applyOptionsDiff, the participants and the empty-plan
checks)."""
import json
from dataclasses import dataclass, field
from uuid import UUID

from argus.backend.models.plan import ArgusReleasePlan
from argus.backend.models.web import ArgusGroup, ArgusTest, User
from argus.backend.service.chat.history import as_utc
from argus.backend.service.chat.resolve import Scope, TestReferenceError
from argus.backend.service.planner_service import PlanDiffPayload
from argus.backend.util.common import select_rows

OWNER_REFERENCES = {"$owner", "owner"}


@dataclass(slots=True)
class PlanChanges:
    add_tests: list[str] = field(default_factory=list)
    remove_tests: list[str] = field(default_factory=list)
    remove_groups: list[str] = field(default_factory=list)
    assign: dict[str, str] = field(default_factory=dict)
    unassign: list[str] = field(default_factory=list)
    add_labels: dict[str, list[str]] = field(default_factory=dict)
    remove_labels: dict[str, list[str]] = field(default_factory=dict)
    name: str | None = None
    description: str | None = None
    target_version: str | None = None
    completed: bool | None = None


def plan_stamp(plan: ArgusReleasePlan) -> str | None:
    return as_utc(plan.last_updated).isoformat() if plan.last_updated else None


def plan_options(plan: ArgusReleasePlan) -> dict[str, dict]:
    return json.loads(plan.options) if plan.options else {}


def plan_labels(plan: ArgusReleasePlan, scope: Scope) -> dict:
    """Every label of the plan with the tests and groups that carry it."""
    tests = {test.id: test for test in scope.tests}
    labels: dict[str, list[dict]] = {}
    for entity_id, option in plan_options(plan).items():
        entity_uuid = UUID(entity_id)
        if test := tests.get(entity_uuid):
            entity = {"test": scope.label(test), "enabled": bool(test.enabled)}
        elif group := scope.groups.get(entity_uuid):
            entity = {"group": group.name, "enabled": bool(group.enabled),
                      "tests": sum(1 for test in scope.tests if test.group_id == group.id and test.enabled)}
        else:
            entity = {"id": entity_id, "missing": True}
        for label in option.get("labels", []):
            labels.setdefault(label, []).append(entity)
    return {"plan": plan.name, "key": plan.key,
            "labels": [{"label": label, "entities": entities} for label, entities in sorted(labels.items())]}


def entity_reference(scope: Scope, reference: str) -> ArgusTest | ArgusGroup:
    tests = scope.find_tests(reference)
    if len(tests) == 1:
        return tests[0]
    if len(tests) > 1:
        raise TestReferenceError(f"{reference} matches several tests: "
                                 f"{', '.join(scope.label(test) for test in tests[:10])}. Be more precise.")
    groups = scope.find_groups(reference)
    if len(groups) == 1:
        return groups[0]
    if groups:
        raise TestReferenceError(f"{reference} matches several groups: {', '.join(group.name for group in groups)}")
    raise TestReferenceError(f"No test or group {reference} in this chat's scope")


async def find_user(reference: str) -> User:
    wanted = reference.strip().lstrip("@").lower()
    rows = await select_rows(User.find(), "id", "username", "full_name")
    found = [row for row in rows if wanted in (str(row["id"]), (row["username"] or "").lower(),
                                               (row["full_name"] or "").lower())]
    if len(found) != 1:
        hint = "several users" if found else "no user"
        raise TestReferenceError(f"{reference} matches {hint}; name the user by username")
    return User.model_construct(id=found[0]["id"], username=found[0]["username"], full_name=found[0]["full_name"])


def describe_user(user: User) -> str:
    return f"{user.full_name or user.username} (@{user.username})"


class DiffBuilder:
    def __init__(self, plan: ArgusReleasePlan, scope: Scope) -> None:
        self.plan = plan
        self.scope = scope
        self.tests = list(plan.tests or [])
        self.groups = list(plan.groups or [])
        self.options = plan_options(plan)
        self.mapping = {UUID(str(key)): UUID(str(value)) for key, value in (plan.assignee_mapping or {}).items()}
        self.diff: dict = {"id": str(plan.id)}
        self.summary: list[str] = []

    def name_of(self, entity_id: UUID) -> str:
        if test := next((test for test in self.scope.tests if test.id == entity_id), None):
            return self.scope.label(test)
        if group := self.scope.groups.get(entity_id):
            return f"group {group.name}"
        return str(entity_id)

    def entity(self, reference: str) -> ArgusTest | ArgusGroup:
        entity = entity_reference(self.scope, reference)
        if entity.release_id != self.plan.release_id:
            raise TestReferenceError(f"{reference} belongs to another release than the plan {self.plan.name}")
        return entity

    def targets(self, reference: str) -> list[UUID]:
        """The plan entities a reference stands for: a test, a group of the plan, or a group's enabled tests."""
        entity = self.entity(reference)
        if isinstance(entity, ArgusTest):
            return [entity.id]
        if entity.id in self.groups:
            self.whole_group(entity)
            return [entity.id]
        return [test.id for test in self.scope.enabled_tests(group=entity)]

    def whole_group(self, group: ArgusGroup) -> None:
        if self.scope.partial:
            raise TestReferenceError(f"The group {group.name} holds tests outside this view; a view chat changes "
                                     "a plan group test by test")

    def ensure_in_plan(self, entity_id: UUID) -> None:
        if entity_id in self.tests or entity_id in self.groups:
            return
        self.tests.append(entity_id)
        self.diff.setdefault("tests_add", []).append(str(entity_id))
        self.summary.append(f"+ {self.name_of(entity_id)}")

    def remove_entity(self, entity_id: UUID) -> None:
        if entity_id in self.tests:
            self.tests.remove(entity_id)
            self.diff.setdefault("tests_remove", []).append(str(entity_id))
        elif entity_id in self.groups:
            self.groups.remove(entity_id)
            self.diff.setdefault("groups_remove", []).append(str(entity_id))
        else:
            return
        self.mapping.pop(entity_id, None)
        self.summary.append(f"- {self.name_of(entity_id)}")

    async def build(self, changes: PlanChanges) -> tuple[dict, list[str]]:
        for reference in changes.add_tests:
            for entity_id in self.targets(reference):
                self.ensure_in_plan(entity_id)
        for reference in changes.remove_tests:
            entity = self.entity(reference)
            if not isinstance(entity, ArgusTest) and entity.id in self.groups:
                self.whole_group(entity)
            ids = [entity.id] if isinstance(entity, ArgusTest) or entity.id in self.groups else \
                [test.id for test in self.scope.tests if test.group_id == entity.id]
            for entity_id in ids:
                self.remove_entity(entity_id)
        for reference in changes.remove_groups:
            group = self.entity(reference)
            if isinstance(group, ArgusTest) or group.id not in self.groups:
                raise TestReferenceError(f"{reference} is not a group of the plan {self.plan.name}")
            self.whole_group(group)
            self.remove_entity(group.id)
        for reference, user_reference in changes.assign.items():
            if user_reference.strip().lower() in OWNER_REFERENCES:
                changes.unassign.append(reference)
                continue
            user = await find_user(user_reference)
            for entity_id in self.targets(reference):
                self.ensure_in_plan(entity_id)
                self.mapping[entity_id] = user.id
                self.diff.setdefault("assignee_mapping_set", {})[str(entity_id)] = str(user.id)
                self.summary.append(f"assign {self.name_of(entity_id)} to {describe_user(user)}")
        for reference in changes.unassign:
            for entity_id in self.targets(reference):
                if self.mapping.pop(entity_id, None) is not None:
                    self.diff.setdefault("assignee_mapping_remove", []).append(str(entity_id))
                    self.summary.append(f"unassign {self.name_of(entity_id)} (back to the owner)")
        self.apply_labels(changes)
        self.apply_scalars(changes)
        self.apply_participants()
        if not self.tests and not self.groups:
            raise TestReferenceError("That would leave the plan without tests or groups")
        if not self.summary:
            raise TestReferenceError("Nothing to change")
        return self.diff, self.summary

    def apply_labels(self, changes: PlanChanges) -> None:
        touched: dict[UUID, tuple[list[str], set[str]]] = {}
        for reference, labels in changes.add_labels.items():
            for entity_id in self.targets(reference):
                self.ensure_in_plan(entity_id)
                touched.setdefault(entity_id, ([], set()))[0].extend(labels)
        for reference, labels in changes.remove_labels.items():
            for entity_id in self.targets(reference):
                touched.setdefault(entity_id, ([], set()))[1].update(label.lower() for label in labels)
        for entity_id, (added, removed) in touched.items():
            key = str(entity_id)
            current = self.options.get(key, {}).get("labels", [])
            final = [label for label in dict.fromkeys([*current, *added]) if label.lower() not in removed]
            if final == current:
                continue
            if final:
                self.diff.setdefault("options_set", {})[key] = {"labels": final}
            elif key in self.options:
                self.diff.setdefault("options_remove", []).append(key)
            self.summary.append(f"labels of {self.name_of(entity_id)}: {', '.join(final) or 'none'} "
                                f"(were {', '.join(current) or 'none'})")

    def apply_scalars(self, changes: PlanChanges) -> None:
        for name, label in (("name", "name"), ("description", "description"), ("target_version", "target version"),
                            ("completed", "completed")):
            value = getattr(changes, name)
            if value is None or value == getattr(self.plan, name):
                continue
            self.diff[name] = value
            self.summary.append(f"{label}: {getattr(self.plan, name)} → {value}")

    def apply_participants(self) -> None:
        before = {UUID(str(user)) for user in (self.plan.assignee_mapping or {}).values()}
        entities = set(self.tests) | set(self.groups)
        after = {user for key, user in self.mapping.items() if key in entities}
        current = set(self.plan.participants or [])
        owner = self.plan.owner
        added = sorted(str(user) for user in after - current - {owner})
        dropped = sorted(str(user) for user in (current & before) - after)
        if added:
            self.diff["participants_add"] = added
        if dropped:
            self.diff["participants_remove"] = dropped


async def build_plan_diff(plan: ArgusReleasePlan, scope: Scope, changes: PlanChanges) -> tuple[dict, list[str]]:
    return await DiffBuilder(plan, scope).build(changes)


def plan_diff_payload(diff: dict) -> PlanDiffPayload:
    def uuids(key: str) -> list[UUID]:
        return [UUID(value) for value in diff.get(key, [])]

    return PlanDiffPayload(
        id=diff["id"], name=diff.get("name"), description=diff.get("description"),
        target_version=diff.get("target_version"), completed=diff.get("completed"),
        tests_add=uuids("tests_add"), tests_remove=uuids("tests_remove"), groups_remove=uuids("groups_remove"),
        participants_add=uuids("participants_add"), participants_remove=uuids("participants_remove"),
        assignee_mapping_set={UUID(key): UUID(value) for key, value in diff.get("assignee_mapping_set", {}).items()},
        assignee_mapping_remove=uuids("assignee_mapping_remove"),
        options_set=diff.get("options_set", {}), options_remove=diff.get("options_remove", []))
