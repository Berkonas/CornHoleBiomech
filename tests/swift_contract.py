"""Check JSON written by the Python engine against the app's Swift `Decodable` structs.

The app decodes most engine files with `try?`: one wrong type anywhere (a dict where the struct wants a list,
a null where it wants a string, 3.0 where it wants an Int, a NaN token) silently drops the whole document, and a
card, the replay or the video disappears. This parser reads the stored properties of every `Decodable` /
`Codable` struct in the app's sources, so the contract follows the Swift code without a second copy.

Usage (tests): `problems("ReplayDocument", json.load(...))` → list of "path: problem" strings.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

SOURCES = Path(__file__).resolve().parents[1] / "app" / "CornholeBiomechanics" / "Sources" / "CornholeBiomechanics"

_STRUCT = re.compile(r"\b(struct|enum|extension)\s+([A-Za-z_][\w.]*)\s*(?::\s*([^{]*))?\{")
_PROP = re.compile(r"^\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:(?:private|fileprivate|internal|public)(?:\(set\))?\s+)*"
                   r"(var|let)\s+`?(\w+)`?\s*:\s*([^={]+?)\s*(=\s*.*)?$")


def _blocks(text: str):
    """(kind, name, conformances, body, start, end) for every type or extension block, nested ones included."""
    for m in _STRUCT.finditer(text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        yield m.group(1), m.group(2), m.group(3) or "", text[m.end():i - 1], m.start(), i


def _coding_keys(body: str) -> dict[str, str]:
    """Swift property → JSON key from a nested `enum CodingKeys` (empty when there is none)."""
    m = None
    for candidate in re.finditer(r"enum\s+CodingKeys\s*:[^{]*\{([^}]*)\}", body):
        prefix = body[:candidate.start()]
        if prefix.count("{") == prefix.count("}"):      # the type's own keys, not a nested type's
            m = candidate
            break
    if not m:
        return {}
    out = {}
    for case in re.findall(r"case\s+([^\n]+)", m.group(1)):
        for item in case.split(","):
            item = item.strip()
            if not item:
                continue
            name, _, raw = item.partition("=")
            name = name.strip().strip("`")
            out[name] = raw.strip().strip('"') if raw else name
    return out


def _top_level_lines(body: str) -> list[str]:
    """Lines of `body` at brace depth 0 (a type's own members, not nested types' or functions')."""
    out, depth, line = [], 0, []
    for ch in body:
        if ch == "{":
            if depth == 0:
                out.append("".join(line) + "{")
                line = []
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == "\n":
            if depth == 0:
                out.append("".join(line))
            line = []
        elif depth == 0:
            line.append(ch)
    out.append("".join(line))
    return out


class Registry:
    def __init__(self, sources: Path = SOURCES):
        self.structs: dict[str, dict[str, Any]] = {}     # full name ("ReplayDocument.Point") → spec
        self.string_enums: set[str] = set()
        self.custom: set[str] = set()                     # full names with a hand-written init(from:)
        for path in sorted(sources.glob("*.swift")):
            text = re.sub(r"//[^\n]*", "", path.read_text())
            self._scan(text)

    def _scan(self, text: str) -> None:
        blocks = list(_blocks(text))
        def full_name(index: int) -> str:
            kind, name, _, _, start, end = blocks[index]
            parents = [j for j, b in enumerate(blocks) if b[4] < start and b[5] >= end and j != index]
            if not parents:
                return name
            parent = max(parents, key=lambda j: blocks[j][4])
            return f"{full_name(parent)}.{name}"
        for index, (kind, name, conformances, body, start, end) in enumerate(blocks):
            full = full_name(index)
            own = "\n".join(_top_level_lines(body))
            if kind == "extension":
                if re.search(r"init\s*\(\s*from\s+decoder", own):
                    self.custom.add(name)
                continue
            if kind == "enum":
                if re.search(r"\bString\b", conformances):
                    self.string_enums.add(name)
                continue
            if re.search(r"init\s*\(\s*from\s+decoder", own):
                self.custom.add(full)
            if not re.search(r"\b(Decodable|Codable)\b", conformances):
                continue
            props = {}
            lines = [part for raw in _top_level_lines(body) for part in raw.split(";")]
            renames = _coding_keys(body)
            for line in lines:
                if re.match(r"^\s*(static|class)\b", line):
                    continue
                m = _PROP.match(line)
                if not m or line.rstrip().endswith("{"):
                    continue
                keyword, prop, typ, default = m.groups()
                if keyword == "let" and default:
                    continue          # a `let` with a value is never decoded
                if renames and prop not in renames:
                    continue          # left out of an explicit CodingKeys: not decoded
                props[renames.get(prop, prop)] = typ.strip()
            self.structs[full] = {"props": props}

    def resolve(self, typ: str, scope: str) -> str | None:
        """Swift name lookup: innermost enclosing scope first, then global, then a unique suffix match."""
        parts = scope.split(".") if scope else []
        for i in range(len(parts), -1, -1):
            candidate = ".".join(parts[:i] + [typ])
            if candidate in self.structs or candidate in self.custom:
                return candidate
        matches = [n for n in list(self.structs) + list(self.custom) if n.endswith("." + typ)]
        return matches[0] if len(set(matches)) == 1 else None

    # -- validation ---------------------------------------------------------------------------------------------
    def problems(self, type_name: str, value: Any, path: str = "$") -> list[str]:
        return self._check(type_name.strip(), value, path, "")

    def _check(self, typ: str, value: Any, path: str, scope: str) -> list[str]:
        typ = typ.strip()
        if typ.endswith("?"):
            return [] if value is None else self._check(typ[:-1], value, path, scope)
        if typ.startswith("[") and typ.endswith("]"):
            inner = typ[1:-1]
            depth, colon = 0, None
            for i, ch in enumerate(inner):
                if ch in "[(":
                    depth += 1
                elif ch in "])":
                    depth -= 1
                elif ch == ":" and depth == 0:
                    colon = i
                    break
            if colon is not None:
                if not isinstance(value, dict):
                    return [f"{path}: expected a dictionary, got {type(value).__name__}"]
                out = []
                for k, v in value.items():
                    out += self._check(inner[colon + 1:], v, f"{path}.{k}", scope)
                return out
            if not isinstance(value, list):
                return [f"{path}: expected a list, got {type(value).__name__}"]
            out = []
            for i, v in enumerate(value):
                out += self._check(inner, v, f"{path}[{i}]", scope)
            return out
        if value is None:
            return [f"{path}: null where {typ} is required"]
        if typ in ("Double", "CGFloat", "Float"):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return [f"{path}: expected a number, got {type(value).__name__}"]
            if value != value or value in (float("inf"), float("-inf")):
                return [f"{path}: NaN/Infinity (JSONDecoder rejects the whole file)"]
            return []
        if typ == "Int":
            if isinstance(value, bool) or not isinstance(value, int):
                return [f"{path}: expected an integer, got {value!r}"]
            return []
        if typ == "Bool":
            return [] if isinstance(value, bool) else [f"{path}: expected true/false, got {value!r}"]
        if typ in ("String", "UUID", "Date", "URL") or typ in self.string_enums:
            return [] if isinstance(value, str) else [f"{path}: expected a string, got {value!r}"]
        name = self.resolve(typ, scope)
        if name is None or name in self.custom:
            return []         # unknown (enum with payloads, typealias …) or a hand-written, tolerant decoder
        spec = self.structs[name]
        if not isinstance(value, dict):
            return [f"{path}: expected an object ({name}), got {type(value).__name__}"]
        out = []
        for prop, ptyp in spec["props"].items():
            if prop not in value:
                if not ptyp.strip().endswith("?"):
                    out.append(f"{path}.{prop}: missing (required {ptyp})")
                continue
            out += self._check(ptyp, value[prop], f"{path}.{prop}", name)
        return out


_registry: Registry | None = None


def problems(type_name: str, value: Any) -> list[str]:
    global _registry
    if _registry is None:
        _registry = Registry()
    return _registry.problems(type_name, value)
