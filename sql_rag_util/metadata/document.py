"""Document structure shared by every metadata file: title, header, sections, bullets."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from sql_rag_util.exceptions import MetadataFormatError
from sql_rag_util.metadata.model import FORMAT_VERSION

__all__ = ["Bullet", "Document", "split_document", "bullets", "list_value", "prose", "only_subs", "json_sub"]

_TITLE = re.compile(r"^# (\S.*)$")
_KEY_LINE = re.compile(r"^([a-z_]+): (.*)$")
_SECTION = re.compile(r"^## (\S.*)$")
_BULLET = re.compile(r"^- ([^\[\]:]+?)(?: \[([^\]]*)\])?: (.*)$")
_SUB_BULLET = re.compile(r"^  - ([a-z_]+): (.*)$")
_CONTINUATION = re.compile(r"^ {2,}(?!- )(\S.*)$")


@dataclass(slots=True)
class Bullet:
    """One bullet with its flags, text, and sub-bullets."""

    name: str
    flags: tuple[str, ...]
    text: str
    line: int
    subs: dict[str, tuple[str, int]] = field(default_factory=dict)
    last_sub: str | None = None


@dataclass(slots=True)
class Document:
    """A split metadata file."""

    title: str
    header: dict[str, tuple[str, int]]
    sections: dict[str, tuple[int, list[tuple[int, str]]]]
    path: str

    def fail(self, message: str, line: int | None = None) -> MetadataFormatError:
        """Return an error located in this file."""
        return MetadataFormatError(message, path=self.path, line=line)


def split_document(text: str, path: str) -> Document:
    """Split ``text`` into title, header, and sections, enforcing the common rules."""
    if "\t" in text:
        line = text[: text.index("\t")].count("\n") + 1
        raise MetadataFormatError("tabs are not allowed", path=path, line=line)
    if "\r" in text:
        raise MetadataFormatError("line endings must be LF", path=path)
    lines = [(i + 1, raw.rstrip()) for i, raw in enumerate(text.split("\n"))]
    if not lines or not (title := _TITLE.match(lines[0][1])):
        raise MetadataFormatError("line 1 must be a level-one heading", path=path, line=1)
    if len(lines) < 3 or lines[1][1] != "" or lines[2][1] != f"format: {FORMAT_VERSION}":
        raise MetadataFormatError(f"line 3 must be 'format: {FORMAT_VERSION}' after a blank line", path=path, line=3)
    header: dict[str, tuple[str, int]] = {}
    index = 3
    while index < len(lines) and lines[index][1] != "":
        number, line = lines[index]
        match = _KEY_LINE.match(line)
        if not match:
            raise MetadataFormatError("expected 'key: value' in the header", path=path, line=number)
        if match.group(1) in header:
            raise MetadataFormatError(f"duplicate header key {match.group(1)!r}", path=path, line=number)
        header[match.group(1)] = (match.group(2), number)
        index += 1
    sections: dict[str, tuple[int, list[tuple[int, str]]]] = {}
    current: str | None = None
    for number, line in lines[index:]:
        if section := _SECTION.match(line):
            current = section.group(1)
            if current in sections:
                raise MetadataFormatError(f"section {current!r} appears twice", path=path, line=number)
            sections[current] = (number, [])
        elif current is None:
            if line:
                raise MetadataFormatError("content before the first section", path=path, line=number)
        else:
            sections[current][1].append((number, line))
    return Document(title.group(1), header, sections, path)


def bullets(doc: Document, lines: list[tuple[int, str]]) -> list[Bullet]:
    """Parse bullets, sub-bullets, and continuation lines."""
    out: list[Bullet] = []
    for number, line in lines:
        if not line:
            continue
        if match := _BULLET.match(line):
            flags = tuple(f.strip() for f in match.group(2).split(",")) if match.group(2) else ()
            out.append(Bullet(match.group(1).strip(), flags, match.group(3).strip(), number))
        elif (sub := _SUB_BULLET.match(line)) and out:
            key = sub.group(1)
            if key in out[-1].subs:
                raise doc.fail(f"duplicate sub-bullet {key!r}", number)
            out[-1].subs[key] = (sub.group(2).strip(), number)
            out[-1].last_sub = key
        elif (cont := _CONTINUATION.match(line)) and out:
            bullet = out[-1]
            if bullet.last_sub is not None:
                value, at = bullet.subs[bullet.last_sub]
                bullet.subs[bullet.last_sub] = (f"{value} {cont.group(1)}", at)
            else:
                bullet.text = f"{bullet.text} {cont.group(1)}"
        else:
            raise doc.fail("expected a bullet, a sub-bullet, or a continuation line", number)
    return out


def list_value(value: str) -> tuple[str, ...]:
    """Split a comma-separated value into trimmed items."""
    return tuple(item.strip() for item in value.split(",") if item.strip())


def prose(lines: list[tuple[int, str]]) -> str:
    """Join section lines into stripped prose."""
    return "\n".join(line for _, line in lines).strip()


def only_subs(doc: Document, bullet: Bullet, allowed: tuple[str, ...]) -> None:
    """Raise when a bullet carries a sub-bullet outside ``allowed``."""
    for key, (_, line) in bullet.subs.items():
        if key not in allowed:
            raise doc.fail(f"unknown sub-bullet {key!r}; allowed: {', '.join(allowed)}", line)


def json_sub(doc: Document, bullet: Bullet, key: str) -> object:
    """Return the parsed JSON of a required sub-bullet."""
    if key not in bullet.subs:
        raise doc.fail(f"{bullet.name!r} needs a '{key}:' sub-bullet", bullet.line)
    raw, line = bullet.subs[key]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise doc.fail(f"{key} is not valid JSON: {exc.msg}", line) from None

