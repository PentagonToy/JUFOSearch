"""Search prepared public metadata without upstream requests."""

import gzip
import json
import math
import re
import sqlite3
import zlib
import unicodedata
from collections import Counter, defaultdict
from contextlib import closing
from difflib import get_close_matches
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).with_name("data")
STOP_WORDS = {"a", "an", "and", "for", "in", "of", "on", "the", "jufo"}


def folded(text):
    return "".join(char for char in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(char))


def words(text):
    text = re.sub(r"\bsub[-\s]+grid\b", "subgrid", folded(text))
    return {word.removesuffix("s") if len(word) > 4 and not word.endswith(("ss", "ics")) else word
            for word in re.findall(r"[^\W_]+", text) if len(word) > 2 and word not in STOP_WORDS}


def initials(title):
    parts = re.findall(r"[^\W_]+|&", folded(title))
    if len(parts) < 2:
        return set()
    parts = ["and" if word == "&" else word for word in parts]
    significant = [word for word in parts if word not in STOP_WORDS or word == "and"]
    keys = {"".join(word[0] for word in parts), "".join(word[0] for word in significant if word != "and")}
    if "and" in significant:
        keys.update("".join(join if word == "and" else word[0] for word in significant)
                    for join in ("&", "n"))
    return keys


def prefix_abbreviation(query, title):
    parts = [word for word in re.findall(r"[^\W_]+", folded(title)) if word not in STOP_WORDS]
    if not 2 <= len(parts) < len(query):
        return False
    positions = {0}
    for word in parts:
        positions = {position + size for position in positions
                     for size in range(1, min(len(word), len(query) - position) + 1)
                     if query.startswith(word[:size], position)}
        if not positions:
            return False
    return len(query) in positions


@lru_cache(maxsize=8)
def snapshot(name):
    with gzip.open(DATA / (name + ".json.gz"), "rt", encoding="utf-8") as stream:
        data = json.load(stream)
    if name in {"search", "titles"}:
        manifest = json.loads((DATA / "manifest.json").read_text())
        if data.get("version") != 1 or any(data["sources"].get(key) != manifest["files"][key]["sha256"]
                                           for key in ("catalogue", "topics")):
            raise ValueError("Search index is stale. Run python -m scripts.prepare_search")
    return data


def build_title_index(rows):
    titles, tokens, acronyms, identifiers = defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(set)
    by_id = {row["jufo_id"]: row for row in rows}
    for row in rows:
        key = row["jufo_id"]
        for title in (row["title"], row.get("title_other") or ""):
            if not title:
                continue
            titles[folded(title)].add(key)
            for word in words(title):
                tokens[word].add(key)
            for acronym in initials(title):
                if 2 <= len(acronym) <= 8:
                    acronyms[acronym].add(key)
        if row.get("abbreviation"):
            acronyms[re.sub(r"[^\w&]|_", "", folded(row["abbreviation"]))].add(key)
        for field in ("issnl", "issn_print", "issn_electronic"):
            if row.get(field):
                identifiers[row[field].replace("-", "").upper()].add(key)

    return by_id, titles, tokens, acronyms, identifiers


@lru_cache(maxsize=1)
def index():
    data = snapshot("titles")
    by_id = {row["jufo_id"]: row for row in data["journals"]}
    return (by_id, *(dict((term, set(ids)) for term, ids in data[name].items())
                     for name in ("titles", "tokens", "acronyms", "identifiers")))


def hydrate(rows):
    if not rows:
        return []
    keys = [row["jufo_id"] for row in rows]
    records = {}
    try:
        with closing(sqlite3.connect((DATA / "journals.sqlite3").as_uri() + "?mode=ro&immutable=1", uri=True)) as connection:
            for start in range(0, len(keys), 500):
                batch = keys[start:start + 500]
                query = "SELECT id, payload FROM journals WHERE id IN (" + ",".join("?" for _ in batch) + ")"
                records.update((key, json.loads(zlib.decompress(payload))) for key, payload in connection.execute(query, batch))
    except (sqlite3.Error, zlib.error) as error:
        raise ValueError("Journal details are unavailable") from error
    if len(records) != len(set(keys)):
        raise ValueError("Journal details are incomplete")
    return [{**row, **records[row["jufo_id"]]} for row in rows]


def search_titles(query):
    by_id, titles, tokens, acronyms, identifiers = index()
    query = unicodedata.normalize("NFKC", query).strip().strip('"“”').strip()
    query = re.sub(r"\s+jufo$", "", query, flags=re.I)
    query = re.sub(r"[‐‑‒–−]", "-", query)
    exact = titles.get(folded(query), set())
    issn = query.replace("-", "").upper()
    if re.fullmatch(r"[0-9]{7}[0-9X]", issn):
        return [dict(by_id[key]) for key in sorted(identifiers.get(issn, ()))], True

    key = re.sub(r"[^\w&]|_", "", folded(query))
    parts = query.replace(".", " ").replace("&", " ").split()
    abbreviated = len(parts) == 1 or all(len(part) == 1 for part in parts)
    aliases = acronyms.get(key, set()) if abbreviated and 2 <= len(key) <= 8 else set()
    terms = words(query)
    hits = Counter()
    for term in terms:
        hits.update(tokens.get(term, ()))
    complete = {key for key, count in hits.items() if count == len(terms)}
    candidates = complete or set(hits)
    prefix_scores = {}
    if not candidates and not exact and not aliases and abbreviated and key.isalpha() and 4 <= len(key) <= 12:
        possible = set().union(*(ids for initial, ids in acronyms.items()
                                 if initial.startswith(key[0]) and len(initial) < len(key)))
        for identifier in possible:
            row = by_id[identifier]
            if prefix_abbreviation(key, row["title"]):
                prefix_scores[identifier] = sum(word not in STOP_WORDS for word in re.findall(r"[^\W_]+", folded(row["title"])))
            elif row.get("title_other") and prefix_abbreviation(key, row["title_other"]):
                prefix_scores[identifier] = 0
        aliases = set(prefix_scores)
    # Correct a misspelling only when ordinary title matching found nothing
    if not candidates and not exact and not aliases:
        for term in terms:
            for correction in get_close_matches(term, tokens.keys(), n=2, cutoff=.8):
                hits.update(tokens[correction])
        candidates = set(hits)
    candidates |= exact | aliases
    ordered = sorted(candidates, key=lambda key: (
        key not in exact, key not in aliases, -prefix_scores.get(key, 0), -hits[key],
        -sum(1 / len(tokens[term]) for term in terms if key in tokens.get(term, ())),
        by_id[key].get("is_active") is not True, folded(by_id[key]["title"]), key))
    rows = [dict(by_id[key]) for key in ordered]
    for row in rows:
        if row["jufo_id"] in aliases and row["jufo_id"] not in exact:
            row["matched_acronym"] = re.sub(r"[^\w&]|_", "", folded(query)).upper()

    return rows, bool(exact or aliases)


def build_topic_index(data, identifiers):
    vocabulary = {}
    for topic in data["topics"]:
        text = " ".join([topic["display_name"], topic.get("description") or "",
                         " ".join(topic.get("keywords") or [])])
        terms = words(text)
        strong = words(topic["display_name"] + " " + " ".join(topic.get("keywords") or []))
        vocabulary[topic["id"]] = (topic["display_name"], terms, words(topic["display_name"]), strong)

    profiles = defaultdict(dict)
    for source in data["sources"]:
        matches = set().union(*(identifiers.get(issn.replace("-", "").upper(), set())
                                for issn in source.get("issn") or []))
        if len(matches) != 1:
            continue
        key = next(iter(matches))
        for topic, count in source.get("topics") or []:
            if topic in vocabulary:
                profiles[key][topic] = max(profiles[key].get(topic, 0), count)

    postings = defaultdict(list)
    for key, profile in profiles.items():
        total = sum(profile.values())
        if not total:
            continue
        for topic, count in profile.items():
            if count / total >= .005:
                postings[topic].append((key, count / total))

    normalized = {key: {topic: count / sum(profile.values()) for topic, count in profile.items()}
                  for key, profile in profiles.items() if sum(profile.values())}
    return vocabulary, postings, normalized


@lru_cache(maxsize=1)
def topic_index():
    data = snapshot("search")
    vocabulary = {key: (name, set(terms), set(heading), set(strong))
                  for key, (name, terms, heading, strong) in data["vocabulary"].items()}
    return vocabulary, data["postings"]


def search_profiles(concepts, variants, hints=None):
    vocabulary, postings = topic_index()
    by_id = index()[0]
    matched = {}
    for concept, label in concepts.items():
        phrases = [(terms, 1) for phrase in variants.get(concept, (concept,)) if (terms := words(phrase))]
        phrases.extend((words(phrase), .8) for phrase in (hints or {}).get(concept, ()))
        scores = []
        for key, (_, terms, heading, strong) in vocabulary.items():
            score = 0
            for phrase, confidence in phrases:
                # Keep a specific method intact; broader discovery uses explicit hints
                if not phrase <= terms:
                    continue
                if confidence < 1 and not phrase <= strong:
                    continue
                score = max(score, confidence * (1 + .25 * len(phrase & heading) / len(phrase)))
            if score:
                scores.append((score, key))
        matched[label] = dict((key, score) for score, key in scores)

    evidence = defaultdict(dict)
    for label, candidates in matched.items():
        for topic, value in candidates.items():
            for key, share in postings.get(topic, ()):
                found = (value * share, topic)
                if found > evidence[key].get(label, (0, "")):
                    evidence[key][label] = found

    ranked = []
    for key, found in evidence.items():
        if not by_id[key].get("is_active"):
            continue
        coverage = [label for label in concepts.values() if label in found]
        explanation = {vocabulary[topic][0] for _, topic in found.values()}
        score = math.exp(sum(math.log(value) for value, _ in found.values()) / len(found))
        row = dict(by_id[key], profile_keywords=coverage, keyword_total=len(concepts),
                   matched_topics=sorted(explanation), topic_match=True)
        ranked.append((len(coverage), score, key, row))

    # Match at least two concepts; profiles do not prove they co-occur in one paper
    return [item[3] for item in sorted(ranked, key=lambda item: (-item[0], -item[1], item[2]))
            if item[0] >= min(2, len(concepts))]
