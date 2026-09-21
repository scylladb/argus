import ast
import json
import re

from argus.backend.models.web import ArgusTest

HEADING_PATTERN = re.compile(r"^\s*#{1,6}\s*TestMetadata\s*:?\s*$", re.IGNORECASE)
PAIR_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_.-]*)\s*:\s*(.*)$")
JENKINSFILE_PATTERN = re.compile(r"^\S+\.jenkinsfile$", re.IGNORECASE)
DESCRIPTION_KEY = "description"


def parse_test_metadata(description: str | None) -> dict[str, str] | None:
    if not description:
        return None

    lines = description.replace("\r\n", "\n").split("\n")
    heading_index = next((index for index, line in enumerate(lines) if HEADING_PATTERN.match(line)), None)
    if heading_index is None:
        return None

    metadata = _parse_pairs(lines[heading_index + 1:])
    prose = _parse_prose(lines[:heading_index])
    if prose:
        metadata.setdefault(DESCRIPTION_KEY, prose)

    return metadata or None


def apply_test_metadata(test: ArgusTest, description: str | None) -> bool:
    parsed = parse_test_metadata(description)
    if parsed is None or parsed == test.test_metadata:
        return False

    test.test_metadata = parsed
    return True


def _parse_pairs(lines: list[str]) -> dict[str, str]:
    pairs: dict[str, str] = {}
    started = False
    for line in lines:
        if not started and not line.strip():
            continue
        match = PAIR_PATTERN.match(line)
        if not match:
            break
        started = True
        pairs[match.group(1)] = _format_value(match.group(2).strip())

    return pairs


def _parse_prose(lines: list[str]) -> str:
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if line.strip():
            current.append(line.strip())
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))

    for paragraph in reversed(paragraphs):
        if paragraph.startswith("#") or JENKINSFILE_PATTERN.match(paragraph):
            continue
        return paragraph

    return ""


def _format_value(value: str) -> str:
    if not value.startswith("["):
        return value

    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return value

    if not isinstance(parsed, list):
        return value

    return json.dumps([str(item) for item in parsed])
