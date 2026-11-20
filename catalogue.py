"""Search prepared public metadata without upstream requests."""

import gzip
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
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


@lru_cache(maxsize=5)
def snapshot(name):
    with gzip.open(DATA / (name + ".json.gz"), "rt", encoding="utf-8") as stream:
        return json.load(stream)


@lru_cache(maxsize=1)
def index():
    rows = snapshot("catalogue")["journals"]
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
    # Correct a misspelling only when ordinary title matching found nothing
    if not candidates and not exact and not aliases:
        for term in terms:
            for correction in get_close_matches(term, tokens.keys(), n=2, cutoff=.8):
                hits.update(tokens[correction])
        candidates = set(hits)
    candidates |= exact | aliases
    ordered = sorted(candidates, key=lambda key: (
        key not in exact, key not in aliases, -hits[key],
        -sum(1 / len(tokens[term]) for term in terms if key in tokens.get(term, ())),
        by_id[key].get("is_active") is not True, folded(by_id[key]["title"]), key))
    rows = [dict(by_id[key]) for key in ordered]
    for row in rows:
        if row["jufo_id"] in aliases and row["jufo_id"] not in exact:
            row["matched_acronym"] = re.sub(r"[^\w&]|_", "", folded(query)).upper()

    return rows, bool(exact or aliases)


@lru_cache(maxsize=1)
def topic_index():
    data = snapshot("topics")
    vocabulary = {}
    for topic in data["topics"]:
        text = " ".join([topic["display_name"], topic.get("description") or "",
                         " ".join(topic.get("keywords") or [])])
        terms = words(text)
        vocabulary[topic["id"]] = (topic["display_name"], terms, words(topic["display_name"]))

    profiles = defaultdict(dict)
    identifiers = index()[4]
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

    return vocabulary, postings


def search_profiles(concepts, variants, hints=None):
    vocabulary, postings = topic_index()
    by_id = index()[0]
    matched = {}
    for concept, label in concepts.items():
        phrases = [(terms, 1) for phrase in variants.get(concept, (concept,)) if (terms := words(phrase))]
        phrases.extend((words(phrase), .8) for phrase in (hints or {}).get(concept, ()))
        scores = []
        for key, (_, terms, heading) in vocabulary.items():
            score = 0
            for phrase, confidence in phrases:
                # Keep a specific method intact; broader discovery uses explicit hints
                if not phrase <= terms:
                    continue
                if confidence < 1 and not phrase & heading:
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
