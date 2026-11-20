"""Find subject neighbours within the reference journal's recorded standing."""

import math

from catalogue import index, snapshot


def overlap(first, second):
    common = sum(min(share, second.get(topic, 0)) for topic, share in first.items())
    return common / (2 - common)


def field_distance(first, second):
    a = {field["id"]: field for field in first["fields"]}
    b = {field["id"]: field for field in second["fields"]}
    common = a.keys() & b.keys()
    if common:
        return sum(abs(a[key]["quartile"] - b[key]["quartile"]) for key in common) / len(common)
    return abs(sum(f["quartile"] for f in a.values()) / len(a)
               - sum(f["quartile"] for f in b.values()) / len(b))


def recommend(reference):
    journals = index()[0]
    seed = journals.get(reference)
    if seed is None:
        raise KeyError(reference)
    if seed.get("level") not in (1, 2, 3) or not seed.get("is_active"):
        return [], "Comparable journal data unavailable."
    metrics = snapshot("quartiles")["journals"]
    profiles = snapshot("peers")
    metric = metrics.get(str(reference))
    profile = profiles.get(str(reference))
    if not metric or not profile:
        return [], "Comparable journal data unavailable."

    names = snapshot("search")["vocabulary"]
    candidates = []
    for key, candidate_metric in metrics.items():
        candidate = journals.get(int(key))
        other = profiles.get(key)
        if (int(key) == reference or not candidate or not candidate.get("is_active")
                or candidate.get("level") != seed["level"] or not other):
            continue
        similarity = overlap(profile, other)
        if similarity < .04 or field_distance(metric, candidate_metric) > 1:
            continue
        first, second = metric["score"], candidate_metric["score"]
        if first > 0 and second > 0:
            proximity = min(first, second) / max(first, second)
            if proximity < 1 / 2.5:
                continue
        else:
            if first != second:
                continue
            proximity = 1
        shared = sorted(profile.keys() & other.keys(), key=lambda topic: -min(profile[topic], other[topic]))
        reason = names[shared[0]][0]
        candidates.append((similarity, proximity, int(key), dict(candidate, recommendation_reason=reason)))

    selected = []
    while candidates and len(selected) < 12:
        front = [item for item in candidates if not any(
            other[0] >= item[0] and other[1] >= item[1] and other[:2] != item[:2] for other in candidates)]
        while front and len(selected) < 12:
            # shortcut: provisional tie-break within the two-axis front; validate with researcher review
            best = max(front, key=lambda item: (
                .6 * math.sqrt(item[0]) + .4 * item[1]
                - .12 * max((overlap(profiles[str(item[2])], profiles[str(old[2])]) for old in selected), default=0),
                -item[2]))
            selected.append(best)
            front.remove(best)
            candidates.remove(best)
    return [row for _, _, _, row in selected], None
