from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def pretty_print(
    data: Mapping[str, Any] | Iterable[Mapping[str, Any]], columns: int = 90
) -> str:
    lines = []
    if isinstance(data, Mapping):
        items: Iterable[Mapping[str, Any]] = (data,)
    elif isinstance(data, Iterable):
        items = data
    else:
        raise TypeError("data must be a mapping or an iterable of mappings")

    for item in items:
        if not isinstance(item, Mapping):
            raise TypeError("all items must be mappings")

        for key, value in item.items():
            key_str = _format_key(key)
            value_str = _format_value(value, columns)
            lines.append(f"{key_str}: {value_str}")

    return "\n".join(lines)


def _format_key(key: Any) -> str:
    key_str = str(key)
    if len(key_str) > 20:
        key_str = key_str[:17] + "..."
    return key_str.ljust(20)


def _format_value(value: Any, columns: int) -> str:
    value_str = str(value)
    wrap_width = max(columns - 22, 1)
    indent = "\n" + " " * 22

    lines = []
    for part in value_str.splitlines() or [""]:
        remaining = part
        while len(remaining) > wrap_width:
            split_at = remaining.rfind(" ", 0, wrap_width + 1)
            if split_at <= 0:
                split_at = wrap_width
            lines.append(remaining[:split_at].rstrip())
            remaining = remaining[split_at:].lstrip()
        lines.append(remaining)

    return indent.join(lines)
