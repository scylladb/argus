import re
import string
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from argus.backend.error_handlers import APIException
from argus.backend.models.chat import GLOBAL_SCOPE, ChatSkill
from argus.backend.models.web import User
from argus.backend.service.chat.prompt import TEMPLATE
from argus.backend.util.common import select_rows

PLACEHOLDERS = ("identity", "entity_kind", "entity_name", "date", "tool_rules", "scope", "memories", "summary",
                "skills")
REQUIRED = ("tool_rules", "scope", "memories", "summary")
MODES = ("always", "on_demand", "off")
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
DESCRIPTION_LIMIT = 300
CONTENT_LIMIT = 20000
TEMPLATE_LIMIT = 30000
SKILL_COLUMNS = ("name", "description", "content", "mode", "updated_by", "updated_at", "system_template",
                 "template_updated_by", "template_updated_at")


class ChatSkillError(APIException):
    pass


@dataclass(slots=True, frozen=True)
class Skill:
    name: str
    description: str
    content: str
    mode: str
    updated_by: UUID | None = None
    updated_at: datetime | None = None


@dataclass(slots=True, frozen=True)
class PromptSetup:
    template: str
    edited: bool
    skills: list[Skill] = field(default_factory=list)
    updated_by: UUID | None = None
    updated_at: datetime | None = None

    @property
    def always(self) -> list[Skill]:
        return [skill for skill in self.skills if skill.mode == "always"]

    @property
    def on_demand(self) -> list[Skill]:
        return [skill for skill in self.skills if skill.mode == "on_demand"]

    def skills_text(self) -> str:
        """The Skills section of the system prompt: the text of each always-on skill, then the list of skills
        the model loads with load_skill."""
        parts = [f"### {skill.name}\n\n{skill.content.strip()}" for skill in self.always]
        if self.on_demand:
            listed = "\n".join(f"- {skill.name}: {skill.description}" for skill in self.on_demand)
            parts.append(f"Load one of these with load_skill when the question needs it:\n\n{listed}")
        return "## Skills\n\n" + "\n\n".join(parts) + "\n" if parts else ""


def check_template(template: str) -> None:
    if len(template) > TEMPLATE_LIMIT:
        raise ChatSkillError(f"The system prompt must be at most {TEMPLATE_LIMIT} characters")
    try:
        names = {re.split(r"[.\[]", name)[0] for _, name, _, _ in string.Formatter().parse(template)
                 if name is not None}
    except ValueError as exception:
        raise ChatSkillError(f"The system prompt has a stray brace ({exception}); write {{{{ and }}}} for a "
                             "literal brace") from exception
    if unknown := sorted(names - set(PLACEHOLDERS)):
        raise ChatSkillError(f"Unknown placeholder {', '.join('{' + name + '}' for name in unknown)}; the "
                             f"placeholders are {', '.join('{' + name + '}' for name in PLACEHOLDERS)}")
    if missing := [name for name in REQUIRED if name not in names]:
        raise ChatSkillError(f"The system prompt must keep {', '.join('{' + name + '}' for name in missing)}")


class SkillService:
    """Skills, the prompt add-ons an administrator writes, and the editable system prompt."""

    @staticmethod
    async def _rows() -> list[dict]:
        return await select_rows(ChatSkill.find(scope=GLOBAL_SCOPE), *SKILL_COLUMNS)

    async def prompt_setup(self) -> PromptSetup:
        rows = await self._rows()
        skills = sorted((Skill(name=row["name"], description=row["description"] or "", content=row["content"] or "",
                               mode=row["mode"] or "off", updated_by=row["updated_by"], updated_at=row["updated_at"])
                         for row in rows if row["name"] is not None), key=lambda skill: skill.name)
        stored = rows[0]["system_template"] if rows else None
        return PromptSetup(template=stored or TEMPLATE, edited=bool(stored), skills=skills,
                           updated_by=rows[0]["template_updated_by"] if rows else None,
                           updated_at=rows[0]["template_updated_at"] if rows else None)

    async def save_skill(self, name: str, description: str, content: str, mode: str, user: User) -> Skill:
        if not NAME_RE.match(name):
            raise ChatSkillError("A skill name has 1 to 64 letters, digits, - or _")
        if mode not in MODES:
            raise ChatSkillError(f"The mode must be one of {', '.join(MODES)}")
        description, content = description.strip(), content.strip()
        if not content or len(content) > CONTENT_LIMIT:
            raise ChatSkillError(f"The skill text must have 1 to {CONTENT_LIMIT} characters")
        if mode == "on_demand" and not description:
            raise ChatSkillError("An on-demand skill needs a description, so the model knows when to load it")
        if len(description) > DESCRIPTION_LIMIT:
            raise ChatSkillError(f"The description must be at most {DESCRIPTION_LIMIT} characters")
        await ChatSkill(name=name).update(description=description, content=content, mode=mode, updated_by=user.id,
                                          updated_at=datetime.now(UTC))
        return next(skill for skill in (await self.prompt_setup()).skills if skill.name == name)

    async def delete_skill(self, name: str) -> None:
        if not any(skill.name == name for skill in (await self.prompt_setup()).skills):
            raise ChatSkillError(f"No skill named {name}")
        await ChatSkill(name=name).delete()

    async def save_template(self, template: str, user: User) -> PromptSetup:
        check_template(template)
        await ChatSkill.find(scope=GLOBAL_SCOPE).update(system_template=template, template_updated_by=user.id,
                                                         template_updated_at=datetime.now(UTC))
        return await self.prompt_setup()

    async def reset_template(self, user: User) -> PromptSetup:
        await ChatSkill.find(scope=GLOBAL_SCOPE).update(system_template=None, template_updated_by=user.id,
                                                         template_updated_at=datetime.now(UTC))
        return await self.prompt_setup()


def template_json(setup: PromptSetup) -> dict:
    return {"template": setup.template, "default": TEMPLATE, "edited": setup.edited, "placeholders": PLACEHOLDERS,
            "required": REQUIRED, "updated_by": setup.updated_by, "updated_at": setup.updated_at}
