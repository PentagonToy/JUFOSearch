"""Calculate subject quartiles from the free, global OpenAlex Sources snapshot."""

import argparse
import gzip
import json
import math
import re
import subprocess
from bisect import bisect_right
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

from catalogue import index
from refresh_catalogue import TARGET, write_manifest, write_snapshot

MANIFEST = "https://openalex.s3.amazonaws.com/data/jsonl/sources/manifest.json"


def source_record(row, edition):
    if not re.fullmatch(r"https://openalex\.org/S[0-9]+", row.get("id", "")):
        return None
    score = (row.get("summary_stats") or {}).get("2yr_mean_citedness")
    if row.get("type") != "journal" or row.get("is_core") is not True:
        return None
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    if not math.isfinite(score) or score < 0:
        return None
    count = sum(item.get("works_count", 0) for item in row.get("counts_by_year") or []
                if item["year"] in (edition - 3, edition - 2))
    if count < 10:
        return None

    fields = defaultdict(int)
    names = {}
    for topic in row.get("topics") or []:
        field = topic.get("subfield")
        if field and topic.get("count", 0) > 0:
            fields[field["id"]] += topic["count"]
            names[field["id"]] = field["display_name"]
    total = sum(fields.values())
    selected = sorted(fields, key=lambda key: (-fields[key], key))[:3]
    selected = {key: names[key] for key in selected if fields[key] >= total * .1}
    if not selected:
        return None

    return {"id": row["id"], "issn": row.get("issn") or [], "score": score, "fields": selected}


def rank_sources(records, minimum=20):
    groups = defaultdict(list)
    for row in records:
        for field in row["fields"]:
            groups[field].append(row["score"])
    groups = {key: sorted(values) for key, values in groups.items()
              if len(values) >= minimum and len(set(values)) > 1}

    ranked = {}
    for row in records:
        fields = []
        for key, name in row["fields"].items():
            if key not in groups:
                continue
            values = groups[key]
            rank = len(values) - bisect_right(values, row["score"]) + 1
            quartile = min(4, 4 * (rank - 1) // len(values) + 1)
            fields.append({"id": key, "name": name, "quartile": quartile, "rank": rank, "total": len(values)})
        if fields:
            ranked[row["id"]] = {"source_id": row["id"], "score": row["score"], "fields": fields}

    return ranked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True, type=Path, help="Execution artefact directory for public source files")
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    with urlopen(MANIFEST, timeout=30) as response:
        manifest = json.load(response)
    if manifest.get("entity") != "sources" or manifest.get("format") != "jsonl":
        raise ValueError("Unexpected OpenAlex Sources manifest")
    edition = int(manifest["date"][:4])
    cache = args.cache / manifest["date"]
    cache.mkdir(exist_ok=True)
    (cache / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def fetch(entry):
        url = urlsplit(entry["url"])
        if url.scheme != "s3" or url.netloc != "openalex" or not url.path.startswith("/data/jsonl/sources/"):
            raise ValueError("Unexpected source-file location")
        path = cache / (url.path.split("/")[-2] + "-" + url.path.split("/")[-1])
        expected = entry["meta"]["content_length"]
        if not path.exists() or path.stat().st_size != expected:
            temporary = path.with_suffix(".tmp")
            subprocess.run(["curl", "--fail", "--silent", "--show-error", "--proto", "=https",
                            "--retry", "2", "--max-time", "180", "--max-filesize", str(expected),
                            "https://openalex.s3.amazonaws.com" + url.path, "-o", str(temporary)], check=True)
            if temporary.stat().st_size != expected:
                raise ValueError("Incomplete OpenAlex source part")
            temporary.replace(path)
        return path

    records = []
    scanned = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for part, (entry, path) in enumerate(zip(manifest["files"], pool.map(fetch, manifest["files"]))):
            count = 0
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                for line in stream:
                    count += 1
                    record = source_record(json.loads(line), edition)
                    if record:
                        records.append(record)
            if count != entry["meta"]["record_count"]:
                raise ValueError("Source part record count mismatch")
            scanned += count
            if part % 20 == 0:
                print(f"Sources: {part + 1}/{len(manifest['files'])} parts, {scanned} records checked", flush=True)
    if scanned != manifest["record_count"] or len({row["id"] for row in records}) != len(records):
        raise ValueError("Incomplete or duplicate global source cohort")
    if len(records) < 10000:
        raise ValueError("Unexpectedly small research-journal cohort")

    ranked = rank_sources(records)
    identifiers = index()[4]
    matches = defaultdict(list)
    for row in records:
        if row["id"] not in ranked:
            continue
        keys = set().union(*(identifiers.get(issn.replace("-", "").upper(), set()) for issn in row["issn"]))
        if len(keys) == 1:
            matches[next(iter(keys))].append(ranked[row["id"]])
    journals = {str(key): rows[0] for key, rows in matches.items() if len(rows) == 1}
    write_snapshot("quartiles.json.gz", {
        "edition": edition, "snapshot_date": manifest["date"], "source": MANIFEST,
        "metric": "summary_stats.2yr_mean_citedness", "citation_year": edition - 1,
        "publication_years": [edition - 3, edition - 2], "minimum_publications": 10,
        "minimum_category_size": 20, "cohort": "CWTS Core journals", "global_cohort": len(records), "journals": journals,
    })
    existing = json.loads((TARGET / "manifest.json").read_text())
    write_manifest({**existing["counts"], "quartile_journals": len(journals)}, existing["checked"])
    print(f"Ranked {len(journals)} JUFO records against {len(records)} eligible global journals", flush=True)


if __name__ == "__main__":
    main()
