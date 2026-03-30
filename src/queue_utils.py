from __future__ import annotations

from typing import Any


def put_latest(q: Any, item: Any) -> bool:
    try:
        while True:
            q.get_nowait()
    except Exception:
        pass
    try:
        q.put_nowait(item)
        return True
    except Exception:
        return False


def drain_latest(q: Any) -> Any:
    latest = None
    got = False
    while True:
        try:
            latest = q.get_nowait()
            got = True
        except Exception:
            break
    return latest if got else None


def drain_all(q: Any) -> list[Any]:
    items: list[Any] = []
    while True:
        try:
            items.append(q.get_nowait())
        except Exception:
            break
    return items
