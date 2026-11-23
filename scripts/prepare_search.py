"""Prepare searchable title and topic postings before serving visitors."""

import hashlib
import json
import sqlite3
import zlib

from catalogue import DATA, build_title_index, build_topic_index, snapshot


def build_peer_tables(connection, journals, vocabulary, profiles, metrics):
    connection.execute("CREATE TABLE peer_profiles (id INTEGER PRIMARY KEY, level INTEGER, score REAL, profile BLOB, fields TEXT)")
    for row in journals:
        key = row["jufo_id"]
        metric = metrics.get(str(key))
        profile = profiles.get(key)
        if row.get("is_active") and row.get("level") in (1, 2, 3) and metric and profile:
            compact = {topic.removeprefix("https://openalex.org/"): value for topic, value in profile.items()}
            connection.execute("INSERT INTO peer_profiles VALUES (?, ?, ?, ?, ?)",
                               (key, row["level"], metric["score"], zlib.compress(json.dumps(compact).encode()), json.dumps(metric["fields"])))
    connection.execute("CREATE INDEX peer_standing ON peer_profiles(level, score)")
    connection.execute("CREATE TABLE topic_names (id TEXT PRIMARY KEY, name TEXT)")
    connection.executemany("INSERT INTO topic_names VALUES (?, ?)",
                           ((key.removeprefix("https://openalex.org/"), value[0]) for key, value in vocabulary.items()))


def prepare():
    from scripts.refresh_catalogue import write_manifest, write_snapshot

    snapshot.cache_clear()
    catalogue = snapshot("catalogue")
    _, titles, tokens, acronyms, identifiers = build_title_index(catalogue["journals"])
    vocabulary, postings, profiles = build_topic_index(snapshot("topics"), identifiers)
    data = {"version": 1, "sources": {name: hashlib.sha256((DATA / (name + ".json.gz")).read_bytes()).hexdigest()
                                     for name in ("catalogue", "topics")}}
    title_data = dict(data, checked=catalogue["checked"])
    for name, values in (("titles", titles), ("tokens", tokens), ("acronyms", acronyms), ("identifiers", identifiers)):
        title_data[name] = {term: sorted(ids) for term, ids in values.items()}
    fields = ("jufo_id", "title", "title_other", "abbreviation", "issnl", "issn_print", "issn_electronic", "publisher_name", "is_active", "level")
    title_data["journals"] = [{key: row[key] for key in fields if key in row} for row in catalogue["journals"]]
    write_snapshot("titles.json.gz", title_data)
    temporary = DATA / "journals.sqlite3.tmp"
    temporary.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary)
    try:
        connection.execute("CREATE TABLE journals (id INTEGER PRIMARY KEY, payload BLOB NOT NULL)")
        connection.executemany("INSERT INTO journals VALUES (?, ?)",
                               ((row["jufo_id"], zlib.compress(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode(), level=3))
                                for row in catalogue["journals"]))
        build_peer_tables(connection, catalogue["journals"], vocabulary, profiles, snapshot("quartiles")["journals"])
        connection.commit()
    finally:
        connection.close()
    temporary.replace(DATA / "journals.sqlite3")
    compact = lambda key: key.removeprefix("https://openalex.org/")
    data.update(vocabulary={compact(key): [name, sorted(terms), sorted(heading), sorted(strong)]
                            for key, (name, terms, heading, strong) in vocabulary.items()},
                postings={compact(key): values for key, values in postings.items()})
    write_snapshot("peers.json.gz", {str(key): {compact(topic): share for topic, share in values.items()}
                                    for key, values in profiles.items()})
    write_snapshot("search.json.gz", data)
    manifest = json.loads((DATA / "manifest.json").read_text())
    write_manifest(manifest["counts"], catalogue["checked"])
    print(f"Prepared {len(catalogue['journals'])} titles and {len(profiles)} topic profiles")


if __name__ == "__main__":
    prepare()
