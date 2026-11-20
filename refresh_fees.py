"""Prepare dated list APCs from a downloaded public OpenAlex Sources snapshot."""

import argparse
import gzip
import json
import math
import re
from pathlib import Path

from catalogue import index
from refresh_catalogue import TARGET, write_manifest, write_snapshot


def prices(row):
    values = {}
    for entry in row.get("apc_prices") or []:
        amount, currency = entry.get("price"), entry.get("currency")
        if (isinstance(amount, bool) or not isinstance(amount, (int, float))
                or not math.isfinite(amount) or amount < 0
                or not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency)):
            continue
        if currency in values and values[currency] != amount:
            return []
        values[currency] = amount
    return [{"currency": key, "amount": value} for key, value in sorted(values.items())]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.sources / "manifest.json").read_text())
    if manifest.get("entity") != "sources":
        raise ValueError("Expected the public Sources snapshot")
    identifiers = index()[4]
    found, ambiguous = {}, set()
    count = 0
    for part in manifest["files"]:
        pieces = part["url"].split("/")
        path = args.sources / (pieces[-2] + "-" + pieces[-1])
        if path.stat().st_size != part["meta"]["content_length"]:
            raise ValueError("Incomplete source file")
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                count += 1
                row = json.loads(line)
                if row.get("type") != "journal" or not re.fullmatch(r"https://openalex.org/S[0-9]+", row.get("id", "")):
                    continue
                listed = prices(row)
                if not listed:
                    continue
                keys = set().union(*(identifiers.get(issn.replace("-", "").upper(), set()) for issn in row.get("issn") or []))
                if len(keys) != 1:
                    continue
                key = str(next(iter(keys)))
                if key in found and (found[key]["source"] != row["id"] or found[key]["prices"] != listed):
                    ambiguous.add(key)
                found[key] = {"prices": listed, "source": row["id"], "snapshot_date": manifest["date"],
                              "updated": row.get("updated_date", "")[:10]}
    if count != manifest["record_count"]:
        raise ValueError("Incomplete source snapshot")
    for key in ambiguous:
        found.pop(key, None)
    write_snapshot("fees.json.gz", {"journals": found, "snapshot_date": manifest["date"]})
    previous = json.loads((TARGET / "manifest.json").read_text())
    write_manifest({"listed_apc_journals": len(found)}, previous["checked"])
    print(f"Prepared dated APC prices for {len(found)} journals")


if __name__ == "__main__":
    main()
