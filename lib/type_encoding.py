from dataclasses import dataclass, field
from typing import List, Optional

TYPE_SPECIFIERS = {
    "c": "char",
    "i": "int",
    "s": "short",
    "l": "long",
    "q": "long_long",
    "C": "unsigned_char",
    "I": "unsigned_int",
    "S": "unsigned_short",
    "L": "unsigned_long",
    "Q": "unsigned_long_long",
    "f": "float",
    "d": "double",
    "v": "void",
    "*": "string",
    "@": "object",
    "#": "class_object",
    ":": "selector",
    "?": "unknown",
    "B": "bool",
    "b": "bit_field",
}


@dataclass
class TypeEncoding:
    specifier: str
    type_name: str = ""
    modifiers: List[str] = field(default_factory=list)
    nested: Optional["TypeEncoding"] = None

    def __str__(self) -> str:
        parts = self.modifiers + [self.specifier]
        base = "".join(parts)
        if self.type_name:
            base += f'("{self.type_name}")'
        if self.nested:
            base += self.nested.__str__()
        return base


_MODIFIER_MAP = {
    "r": "const",
    "V": "oneway",
    "N": "in",
    "o": "out",
    "O": "bycopy",
    "R": "byref",
    "A": "_atomic",
    "n": "inout",
}


def _parse_one(encoded_str: str, start: int) -> tuple[Optional[TypeEncoding], int]:
    i = start
    modifiers = []
    while i < len(encoded_str) and encoded_str[i] in "rVNoORAn":
        modifiers.append(_MODIFIER_MAP.get(encoded_str[i], ""))
        i += 1

    if i >= len(encoded_str):
        return None, i

    ch = encoded_str[i]

    if ch in TYPE_SPECIFIERS:
        i += 1
        type_name = ""
        if ch == "@" and i < len(encoded_str) and encoded_str[i] == '"':
            i += 1
            end = encoded_str.find('"', i)
            if end == -1:
                type_name = encoded_str[i:]
                i = len(encoded_str)
            else:
                type_name = encoded_str[i:end]
                i = end + 1
        return TypeEncoding(
            specifier=ch, type_name=type_name, modifiers=modifiers
        ), i

    if ch == "^":
        i += 1
        inner, i = _parse_one(encoded_str, i)
        return TypeEncoding(
            specifier="^", modifiers=modifiers, nested=inner
        ), i

    if ch == "{":
        j = i + 1
        depth = 1
        while j < len(encoded_str) and depth > 0:
            if encoded_str[j] == "{":
                depth += 1
            elif encoded_str[j] == "}":
                depth -= 1
            j += 1
        inner = encoded_str[i + 1 : j - 1]
        name_end = inner.find("=")
        if name_end != -1:
            struct_name = inner[:name_end]
            fields = parse_type_encoding(inner[name_end + 1:])
        else:
            struct_name = inner
            fields = []
        return TypeEncoding(
            specifier="struct",
            type_name=struct_name,
            modifiers=modifiers,
            nested=fields[0] if len(fields) == 1 else None,
        ), j

    if ch == "[":
        j = i + 1
        while j < len(encoded_str) and encoded_str[j].isdigit():
            j += 1
        count_str = encoded_str[i + 1:j]
        if not count_str:
            return None, j
        array_count = int(count_str)
        inner, j = _parse_one(encoded_str, j)
        return TypeEncoding(
            specifier="[",
            type_name=str(array_count),
            modifiers=modifiers,
            nested=inner,
        ), j

    if ch == "(":
        j = i + 1
        depth = 1
        while j < len(encoded_str) and depth > 0:
            if encoded_str[j] == "(":
                depth += 1
            elif encoded_str[j] == ")":
                depth -= 1
            j += 1
        inner = encoded_str[i + 1 : j - 1]
        fields = parse_type_encoding(inner)
        return TypeEncoding(
            specifier="union",
            type_name=inner,
            modifiers=modifiers,
            nested=fields[0] if len(fields) == 1 else None,
        ), j

    return None, i + 1


def parse_type_encoding(encoded_str: str) -> list[TypeEncoding]:
    result = []
    i = 0
    while i < len(encoded_str):
        te, i = _parse_one(encoded_str, i)
        if te is not None:
            result.append(te)
    return result
