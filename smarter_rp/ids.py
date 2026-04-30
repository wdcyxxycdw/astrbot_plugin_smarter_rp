from __future__ import annotations

import hashlib
import json


def make_stable_id(prefix: str, *parts: object) -> str:
    raw = json.dumps(
        [(type(part).__module__, type(part).__qualname__, part) for part in parts],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"
