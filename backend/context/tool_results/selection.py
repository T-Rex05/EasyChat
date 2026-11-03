"""Key-agnostic, bounded candidates; these are observations, not relevance judgments."""
import heapq
import json

from .json_locations import JsonLocations


def other_fields(content, protected_key):
    index = JsonLocations(content)
    if index.status != "ok":
        return [], None, index.status
    candidates, count = [], 0
    for order, (pointer, start, end) in enumerate(index.scalar_spans()):
        key = pointer.rsplit("/", 1)[-1].replace("~1", "/").replace("~0", "~")
        if protected_key(key):
            continue
        count += 1
        if end - start > 256:
            continue  # Never shorten a value and present the fragment as exact.
        fact = {"pointer": pointer, "key": key, "value": json.loads(content[start:end])}
        priority = (-pointer.count("/"), -order)
        item = (*priority, fact)
        if len(candidates) < 64:
            heapq.heappush(candidates, item)
        elif priority > candidates[0][:2]:
            heapq.heapreplace(candidates, item)
    return [item[2] for item in sorted(candidates, reverse=True)], count, "ok"
