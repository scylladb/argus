import re
from dataclasses import dataclass

VERSION_RE = re.compile(r"^(?P<base>\d+\.\d+(?:\.\d+)?)(?:[~.-](?P<pre>rc\d+|dev))?(?:[.~-].*)?$")
FINAL_RANK = 1_000_000


@dataclass(frozen=True, slots=True)
class ScyllaVersion:
    base: str
    pre: str | None = None

    def __str__(self) -> str:
        return f"{self.base}~{self.pre}" if self.pre else self.base

    @property
    def family(self) -> str:
        return self.base

    def sort_key(self) -> tuple[tuple[int, ...], int]:
        if self.pre is None:
            rank = FINAL_RANK
        elif self.pre == "dev":
            rank = 0
        else:
            rank = 1 + int(self.pre.removeprefix("rc"))
        return tuple(int(part) for part in self.base.split(".")), rank


def parse_version(raw: str | None) -> ScyllaVersion | None:
    if not raw:
        return None
    match = VERSION_RE.match(raw.strip())
    if not match:
        return None
    base = match.group("base")
    if base.count(".") == 1:
        base = f"{base}.0"
    return ScyllaVersion(base=base, pre=match.group("pre"))
