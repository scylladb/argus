from functools import partial
from datetime import UTC, datetime

import humanize

from argus.backend.models.web import User
from argus.backend.util.common import get_build_number
from argus.backend.util.module_loaders import is_filter, export_functions


export_filters = partial(export_functions, module_name=__name__, attr="is_filter")


@is_filter("from_timestamp")
def from_timestamp_filter(timestamp: int):
    return datetime.fromtimestamp(timestamp, UTC)


@is_filter("safe_user")
def safe_user(user: User):
    user_dict = dict(user.items())
    del user_dict["password"]
    return user_dict


@is_filter("formatted_date")
def formatted_date(date: datetime | None):
    if date:
        return date.strftime("%d/%m/%Y %H:%M:%S")
    return "#unknown"


@is_filter("severity_to_color")
def severity_to_color(severity: str):
    COLORS = {
        "NORMAL": "#0dcaf0",
        "WARNING": "#ffc107",
        "CRITICAL": "#8b1a26",
        "ERROR": "#dc3545",
        "DEBUG": "#212529",
    }
    return COLORS.get(severity, COLORS["DEBUG"])


@is_filter("status_to_color")
def status_to_color(status: str):
    COLORS = {
        "failed": "#dc3545",
        "test_error": "#fd7e14",
        "aborted": "#212529",
        "running": "#ffc107",
        "created": "#0dcaf0",
        "passed": "#198754",
        "error": "#d63384",
    }
    return COLORS.get(status, COLORS["error"])

@is_filter("build_url_to_build_number")
def build_url_to_build_number(build_url: str):
    return get_build_number(build_url)


@is_filter("get_scylla_full_version")
def get_scylla_full_version(packages: list[dict]):
    f = filter(lambda p: p["name"] == "scylla-server", packages)
    package = next(f, None)
    if not package:
        return ""
    return f"{package["version"]}.{package["date"]}.{package["revision_id"]} (buildId: {package["build_id"]})"

@is_filter("get_kernel_version")
def get_kernel_version(packages: list[dict]):
    f = filter(lambda p: p["name"] == "kernel", packages)
    package = next(f, None)
    if not package:
        return ""
    return package["version"]

@is_filter("nemesis_duration")
def nemesis_duration(start_time: int, end_time: int):
    if not end_time:
        return 0
    return humanize.naturaldelta(end_time - start_time)

@is_filter("nemesis_status_to_emoji")
def nemesis_status_to_emoji(status: str):
    EMOJI = {
        "failed": "❌",
        "skipped": "➡️",
        "running": "🔄",
        "succeeded": "✅",
        "terminated": "🛑",
    }
    return EMOJI.get(status, EMOJI["terminated"])
