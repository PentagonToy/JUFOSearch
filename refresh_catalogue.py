"""Prepare JUFO records, OpenAlex topic profiles and FinELib terms before search."""

import argparse
import gzip
import hashlib
import io
import json
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode

from server import JUFO, LIST_URL, compact_result, download, parse_title_list

BULK = "https://jufo-rest.csc.fi/v1.1/massa.json.zip"
TARGET = Path(__file__).with_name("data")


def cached_json(url, cache):
    path = cache / (hashlib.sha256(url.encode()).hexdigest() + ".json")
    if path.exists() and datetime.fromtimestamp(path.stat().st_mtime).date() == date.today():
        return json.loads(path.read_bytes())

    for attempt in range(3):
        try:
            data = json.loads(download(url, timeout=30))
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def write_snapshot(name, data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    target = TARGET / name
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(gzip.compress(payload, mtime=0))
    temporary.replace(target)
    print(f"Saved {name}: {len(payload)} bytes before compression", flush=True)


def write_manifest(counts, checked):
    manifest_path = TARGET / "manifest.json"
    if manifest_path.exists():
        counts = {**json.loads(manifest_path.read_text())["counts"], **counts}
    files = {}
    for path in sorted([*TARGET.glob("*.json.gz"), *TARGET.glob("*.sqlite3")]):
        payload = path.read_bytes()
        files[path.name.removesuffix(".json.gz")] = {"filename": path.name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
    manifest = {"checked": checked, "counts": counts, "files": files,
                "sources": [JUFO, BULK, "https://api.openalex.org", LIST_URL]}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True, help="Directory for resumable source downloads")
    parser.add_argument("--bulk", type=Path, required=True, help="Official CSC massa.json.zip export")
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    TARGET.mkdir(exist_ok=True)

    with zipfile.ZipFile(args.bulk) as bundle:
        bulk = json.loads(bundle.read(bundle.namelist()[0]))
    expected = {int(row["Jufo_ID"]) for row in bulk if row["Type"].casefold() == "lehti/sarja"}

    def page(offset):
        return cached_json(f"{JUFO}/search?type=series&_size=100&_from={offset}", args.cache)

    records = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for index, rows in enumerate(pool.map(page, range(0, len(expected) + 100, 100))):
            if not isinstance(rows, list):
                raise ValueError("Unexpected JUFO page")
            records.update((row["jufo_id"], row) for row in rows)
            if index % 50 == 0:
                print(f"JUFO: {len(records)} unique records", flush=True)
        missing = sorted(expected - records.keys())
        for rows in pool.map(lambda key: cached_json(f"{JUFO}/channel/{key}", args.cache), missing):
            records.update((row["jufo_id"], row) for row in rows)
    if not expected <= records.keys():
        raise ValueError("Incomplete JUFO catalogue; previous snapshot preserved")

    journals = []
    for row in records.values():
        journals.append({**compact_result(row), "title_other": row.get("title_other"),
                         "abbreviation": row.get("abbreviation")})
    today = date.today().isoformat()
    write_snapshot("catalogue.json.gz", {"checked": today, "source": JUFO, "journals": journals})

    # Query only registered ISSNs; do not download the global Works database
    identifiers = sorted({row[field] for row in journals for field in
                          ("issnl", "issn_print", "issn_electronic") if row.get(field)})
    batches = [identifiers[start:start + 75] for start in range(0, len(identifiers), 75)]

    def sources(issns):
        parameters = {"filter": "issn:" + "|".join(issns), "per-page": 200,
                      "select": "id,issn,topics"}
        data = cached_json("https://api.openalex.org/sources?" + urlencode(parameters), args.cache)
        if data["meta"]["count"] > len(data["results"]):
            raise ValueError("OpenAlex source batch was truncated")
        return data["results"]

    profiles = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for index, rows in enumerate(pool.map(sources, batches)):
            profiles.update((row["id"], row) for row in rows)
            if index % 50 == 0:
                print(f"OpenAlex: {index + 1}/{len(batches)} batches", flush=True)

    topics = {}
    page_number = 1
    while True:
        data = cached_json("https://api.openalex.org/topics?" + urlencode({
            "per-page": 200, "page": page_number,
            "select": "id,display_name,description,keywords"}), args.cache)
        for row in data["results"]:
            row["keywords"] = [keyword["display_name"] if isinstance(keyword, dict) else keyword
                               for keyword in row.get("keywords") or []]
            topics[row["id"]] = row
        if page_number * 200 >= data["meta"]["count"]:
            break
        page_number += 1
    sources_compact = [{"id": row["id"], "issn": row.get("issn") or [],
                        "topics": [[topic["id"], topic["count"]] for topic in row.get("topics") or []]}
                       for row in profiles.values()]
    write_snapshot("topics.json.gz", {"checked": today, "topics": list(topics.values()),
                                      "sources": sources_compact})

    titles = parse_title_list(download(LIST_URL, timeout=30))
    write_snapshot("agreements.json.gz", {"checked": today, "titles": {
        key: sorted(values) for key, values in titles.items()}})
    write_manifest({"jufo_series": len(journals), "openalex_sources": len(profiles), "topics": len(topics)}, today)
    from prepare_search import prepare
    prepare()


if __name__ == "__main__":
    main()
