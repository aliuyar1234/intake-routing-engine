from __future__ import annotations

from typing import Any, Optional


def _decode_pointer_segment(seg: str) -> str:
    return seg.replace("~1", "/").replace("~0", "~")


def _split_pointer(path: str) -> list[str]:
    if path == "":
        return []
    if not path.startswith("/"):
        raise ValueError(f"json pointer must start with '/': {path}")
    parts = path.split("/")[1:]
    return [_decode_pointer_segment(p) for p in parts]


def _resolve_parent(doc: Any, path: str) -> tuple[Any, str]:
    parts = _split_pointer(path)
    if not parts:
        raise ValueError("json patch path must not be empty")
    parent = doc
    for seg in parts[:-1]:
        if isinstance(parent, dict):
            if seg not in parent:
                raise KeyError(f"json patch path segment not found: {seg}")
            parent = parent[seg]
        elif isinstance(parent, list):
            if seg == "-":
                raise ValueError("json patch '-' is only allowed in the final segment")
            try:
                idx = int(seg)
            except Exception as e:
                raise ValueError(f"json patch list index must be int: {seg}") from e
            if idx < 0 or idx >= len(parent):
                raise IndexError(f"json patch list index out of range: {idx}")
            parent = parent[idx]
        else:
            raise TypeError(f"json patch cannot traverse into {type(parent).__name__}")
    return parent, parts[-1]


def _require_value(op: dict, *, op_name: str) -> Any:
    if "value" in op:
        return op["value"]
    raise ValueError(f"json patch op '{op_name}' requires 'value'")


def apply_json_patch(doc: Any, patch_ops: list[dict]) -> Any:
    out = doc
    for op in patch_ops:
        if not isinstance(op, dict):
            raise ValueError("json patch ops must be objects")
        op_name = op.get("op")
        path = op.get("path")
        if not isinstance(op_name, str) or not op_name:
            raise ValueError("json patch op missing 'op'")
        if not isinstance(path, str):
            raise ValueError("json patch op missing 'path'")

        parent, key = _resolve_parent(out, path)

        if isinstance(parent, dict):
            if op_name == "add":
                parent[key] = _require_value(op, op_name=op_name)
            elif op_name == "replace":
                if key not in parent:
                    raise KeyError(f"json patch replace missing key: {key}")
                parent[key] = _require_value(op, op_name=op_name)
            elif op_name == "remove":
                if key not in parent:
                    raise KeyError(f"json patch remove missing key: {key}")
                del parent[key]
            else:
                raise ValueError(f"unsupported json patch op: {op_name}")
            continue

        if isinstance(parent, list):
            if key == "-":
                idx: Optional[int] = None
            else:
                try:
                    idx = int(key)
                except Exception as e:
                    raise ValueError(f"json patch list index must be int: {key}") from e

            if op_name == "add":
                val = _require_value(op, op_name=op_name)
                if idx is None:
                    parent.append(val)
                else:
                    if idx < 0 or idx > len(parent):
                        raise IndexError(f"json patch add index out of range: {idx}")
                    parent.insert(idx, val)
            elif op_name == "replace":
                val = _require_value(op, op_name=op_name)
                if idx is None:
                    raise ValueError("json patch replace does not support '-' index")
                if idx < 0 or idx >= len(parent):
                    raise IndexError(f"json patch replace index out of range: {idx}")
                parent[idx] = val
            elif op_name == "remove":
                if idx is None:
                    raise ValueError("json patch remove does not support '-' index")
                if idx < 0 or idx >= len(parent):
                    raise IndexError(f"json patch remove index out of range: {idx}")
                parent.pop(idx)
            else:
                raise ValueError(f"unsupported json patch op: {op_name}")
            continue

        raise TypeError(f"json patch target must be object or list, got: {type(parent).__name__}")

    return out

