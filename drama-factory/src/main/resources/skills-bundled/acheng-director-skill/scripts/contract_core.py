"""Small shared primitives for versioned production contracts."""
import hashlib
import json


def need(condition, message):
    if not condition:
        raise ValueError(message)


def prose(value):
    return isinstance(value, str) and len(value.strip()) >= 3 and value.strip().lower() not in {"unknown", "todo", "tbd", "n/a"}


def indexed(items, label, allow_empty=False):
    need(isinstance(items, list) and (items or allow_empty), f"{label}: list required")
    need(all(isinstance(x, dict) and isinstance(x.get("id"), str) and x["id"].strip() for x in items), f"{label}: object/id required")
    result = {x["id"]: x for x in items}
    need(len(result) == len(items), f"{label}: duplicate id")
    return result


def content_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()
