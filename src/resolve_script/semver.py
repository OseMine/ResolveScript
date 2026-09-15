"""Minimal SemVer 2.0 parsing and range matching (no external deps)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_VERSION_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


class SemVerError(ValueError):
    pass


@dataclass(frozen=True)
class Version:
    major: int
    minor: int = 0
    patch: int = 0
    prerelease: str = ""

    def __post_init__(self) -> None:
        if self.major < 0 or self.minor < 0 or self.patch < 0:
            raise SemVerError(f"negative version component: {self!r}")

    @classmethod
    def parse(cls, text: str) -> Version:
        match = _VERSION_RE.match(text.strip())
        if not match:
            raise SemVerError(f"'{text}' is not a valid SemVer version")
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
            prerelease=match.group(4) or "",
        )

    @staticmethod
    def _pre_key(value: str) -> tuple[int, ...]:
        # numeric identifiers sort lower than alphanumeric ones
        result: list[int] = []
        for part in value.split("."):
            if part.isdigit():
                result.append(0)
                result.append(int(part))
            else:
                result.append(1)
                result.append(len(part))
                result.append(sum(ord(c) for c in part))
        return tuple(result)

    def _release_key(self) -> tuple:
        return (self.major, self.minor, self.patch)

    def __lt__(self, other: Version) -> bool:  # noqa: D105
        a, b = self._release_key(), other._release_key()
        if a != b:
            return a < b
        if self.prerelease == other.prerelease:
            return False
        if not self.prerelease:
            return False  # release > prerelease
        if not other.prerelease:
            return True
        return Version._pre_key(self.prerelease) < Version._pre_key(other.prerelease)

    def __le__(self, other: Version) -> bool:  # noqa: D105
        return self == other or self < other

    def __gt__(self, other: Version) -> bool:  # noqa: D105
        return not (self <= other)

    def __ge__(self, other: Version) -> bool:  # noqa: D105
        return not (self < other)

    def __str__(self) -> str:
        text = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            text += f"-{self.prerelease}"
        return text


# ---------------------------------------------------------------------------
# ranges
# ---------------------------------------------------------------------------
_COMPARATOR_RE = re.compile(
    r"^\s*(>=|<=|>|<|=|~|\^)?\s*"
    r"((0|[1-9]\d*)(?:\.(0|[1-9]\d*))?(?:\.(0|[1-9]\d*))?(?:-[0-9A-Za-z.\-]+)?)"
    r"\s*$"
)


def _parse_lenient(raw: str) -> Version:
    if _VERSION_RE.match(raw):
        return Version.parse(raw)
    return _first_three(raw)


def _comparator_matches(op: str | None, version: Version, raw: str) -> bool:
    if op == "~":
        # npm tilde on partials: ~1 => <2.0.0 ; ~1.0 / ~1.2.3 => <1.1.0 / <1.3.0
        target = _first_three(raw)
        core_parts = _core_only(raw).split(".")
        if len(core_parts) == 1:
            upper = Version(target.major + 1, 0, 0)
        else:
            upper = Version(target.major, target.minor + 1, 0)
        return version >= target and version < upper
    if op == "^":
        # ^1.2.3 => >=1.2.3 <2.0.0 ; ^0.2.3 => >=0.2.3 <0.3.0 ; ^0.0.3 => >=0.0.3 <0.0.4
        target = _first_three(raw)
        if target.major > 0:
            upper = Version(target.major + 1, 0, 0)
        elif target.minor > 0:
            upper = Version(0, target.minor + 1, 0)
        else:
            upper = Version(0, 0, target.patch + 1)
        return version >= target and version < upper

    core = _core_only(raw)
    if op in (None, ""):
        if _has_prerelease(raw):
            return version == _parse_lenient(raw) or version == Version.parse(core)
        return version == _parse_lenient(raw)

    target = _parse_lenient(core)
    # pre-release versions only compare against the same [major,minor,patch]
    if version.prerelease and version._release_key() != target._release_key():
        return False

    if op == ">=":
        return version >= target
    if op == "<=":
        return version <= target
    if op == ">":
        return version > target
    if op == "<":
        return version < target
    if op == "=":
        return version == target
    return version >= target  # ">=x" fallback


def _first_three(raw: str) -> Version:
    parts = raw.replace("-", ".").split(".")[:3]
    return Version(_int(parts, 0), _int(parts, 1), _int(parts, 2))


def _core_only(raw: str) -> str:
    return raw.split("-")[0].split("+")[0]


def _has_prerelease(raw: str) -> bool:
    return "-" in raw


def _int(parts: list[str], index: int) -> int:
    if len(parts) > index and parts[index]:
        try:
            return int(parts[index])
        except ValueError:
            return 0
    return 0


def _xy_floor(raw: str) -> Version:
    parts = raw.replace("-", ".").split(".")
    pieces: list[int] = []
    for part in parts:
        if part in ("x", "X", "*"):
            break
        try:
            pieces.append(int(part))
        except ValueError:
            break
    return Version(pieces[0] if pieces else 0, pieces[1] if len(pieces) > 1 else 0, pieces[2] if len(pieces) > 2 else 0)


def _xy_ceil(raw: str) -> Version:
    parts = raw.replace("-", ".").split(".")
    major = 0
    for part in parts:
        if part.isdigit():
            major = int(part)
        else:
            break
    return Version(major + 1 if major else 1, 0, 0)


def matches(version: Version, range_text: str) -> bool:
    """True if ``version`` satisfies the npm-style ``range_text``."""
    range_text = (range_text or "*").strip()
    if range_text in ("", "*", "x", "X"):
        return True
    if _VERSION_RE.match(range_text):
        return version == Version.parse(range_text)
    for clause in range_text.replace(",", " ").split():
        if clause.startswith("-"):
            continue
        match = _COMPARATOR_RE.match(clause)
        if match:
            op, raw = match.group(1), match.group(2)
            # handle x-ranges like 1.x or 1
            if any(c in raw for c in "xX*") or raw.count(".") < 1:
                lo = _xy_floor(raw)
                hi = _xy_ceil(raw)
                return lo <= version < hi
            if not _comparator_matches(op, version, raw):
                return False
        elif "-" in clause and clause.count("-") == 1:
            lo, hi = clause.split("-")
            if not (version >= Version.parse(_core_only(lo))):
                return False
            if hi.strip() and not (version <= Version.parse(_core_only(hi))):
                return False
    return True


def pick_best(candidates: list[str], range_text: str | None = None) -> str | None:
    """Return the highest version satisfying the range (or the highest overall)."""
    best: Version | None = None
    best_text: str | None = None
    for text in candidates:
        try:
            version = Version.parse(text)
        except SemVerError:
            continue
        if range_text and not matches(version, range_text):
            continue
        if best is None or version > best:
            best, best_text = version, text
    return best_text
