"""Find subject neighbours within the reference journal's recorded standing."""

import math
import json
import sqlite3
import zlib
from contextlib import closing
from functools import lru_cache
from pathlib import Path

import catalogue


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
    rows, notice = cached_peers(reference, str(catalogue.DATA))
    return [dict(row) for row in rows], notice


@lru_cache(maxsize=128)
def cached_peers(reference, source):
    try:
        with closing(sqlite3.connect((Path(source) / "journals.sqlite3").as_uri() + "?mode=ro&immutable=1", uri=True)) as connection:
            seed = connection.execute("SELECT level, score, profile, fields FROM peer_profiles WHERE id=?", (reference,)).fetchone()
            if seed is None:
                if not connection.execute("SELECT 1 FROM journals WHERE id=?", (reference,)).fetchone():
                    raise KeyError(reference)
                return [], "Comparable journal data unavailable."
            level, score, raw_profile, fields = seed
            profile = json.loads(zlib.decompress(raw_profile))
            metric = {"score": score, "fields": json.loads(fields)}
            lower = math.nextafter(score / 2.5, -math.inf)
            upper = math.nextafter(score * 2.5, math.inf)
            records = connection.execute("SELECT id, score, profile, fields FROM peer_profiles WHERE level=? AND score BETWEEN ? AND ? AND id<>?",
                                         (level, lower, upper, reference)).fetchall()
            rows = select_peers(level, metric, profile, records)
            for row in rows:
                topic = row.pop("recommendation_topic")
                row["recommendation_reason"] = connection.execute("SELECT name FROM topic_names WHERE id=?", (topic,)).fetchone()[0]
            return rows, None
    except (sqlite3.Error, zlib.error) as error:
        raise ValueError("Comparable journal data unavailable") from error


def select_peers(level, metric, profile, records):
    profiles = {}
    candidates = []
    for key, score, raw_profile, fields in records:
        other = json.loads(zlib.decompress(raw_profile))
        profiles[key] = other
        candidate_metric = {"score": score, "fields": json.loads(fields)}
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
        candidate = {"jufo_id": key, "level": level, "is_active": True, "recommendation_topic": shared[0]}
        candidates.append((similarity, proximity, key, candidate))

    selected = []
    while candidates and len(selected) < 12:
        front = [item for item in candidates if not any(
            other[0] >= item[0] and other[1] >= item[1] and other[:2] != item[:2] for other in candidates)]
        while front and len(selected) < 12:
            # shortcut: provisional tie-break within the two-axis front; validate with researcher review
            best = max(front, key=lambda item: (
                .6 * math.sqrt(item[0]) + .4 * item[1]
                - .12 * max((overlap(profiles[item[2]], profiles[old[2]]) for old in selected), default=0),
                -item[2]))
            selected.append(best)
            front.remove(best)
            candidates.remove(best)
    return [row for _, _, _, row in selected]
