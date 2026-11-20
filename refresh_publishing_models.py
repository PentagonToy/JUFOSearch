"""Fill publishing-model gaps from positive OpenAlex evidence and publisher lists."""

import argparse
import gzip
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

from catalogue import index
from refresh_catalogue import TARGET, write_manifest, write_snapshot

PUBLISHERS = [
    ("springer-hybrid", "Springer Nature", "Hybrid OA", "pdf", 1000,
     "https://cms-resources.apps.public.k8s.springernature.io/springer-cms/rest/v1/content/27820862/data/v3"),
    ("springer-gold", "Springer Nature", "Gold OA", "pdf", 300,
     "https://cms-resources.apps.public.k8s.springernature.io/springer-cms/rest/v1/content/27820860/data/v3"),
    ("wiley-hybrid", "Wiley", "Hybrid OA", "xlsx", 500,
     "https://authorservices.wiley.com/asset/Wiley-Journal-APCs-OnlineOpen.xlsx"),
    ("wiley-gold", "Wiley", "Gold OA", "xlsx", 100,
     "https://authorservices.wiley.com/asset/Wiley-Journal-APCs-Open-Access.xlsx"),
    ("aip-contract", "AIP Publishing / SURF title list", None, "pdf", 30,
     "https://www.openaccess.nl/sites/default/files/documents/2026-03/SURF%20-%20AIP%20Agreement%202026-2028_Redacted_0.pdf"),
]
ISSN = re.compile(r"(?<![0-9])[0-9]{4}-?[0-9]{3}[0-9X](?![0-9])", re.I)
NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def identifiers(text):
    found = set()
    for value in ISSN.findall(text.upper()):
        compact = value.replace("-", "")
        digits = [10 if char == "X" else int(char) for char in compact]
        if sum(value * weight for value, weight in zip(digits, range(8, 0, -1))) % 11 == 0:
            found.add(compact)
    return found


def xlsx_text(path):
    with zipfile.ZipFile(path) as bundle:
        shared = ["".join(node.itertext()) for node in ET.fromstring(bundle.read("xl/sharedStrings.xml"))]
        sheet = ET.fromstring(bundle.read("xl/worksheets/sheet1.xml"))
        values = []
        for cell in sheet.findall(".//x:c", NS):
            value = cell.findtext("x:v", namespaces=NS)
            if value is not None:
                values.append(shared[int(value)] if cell.get("t") == "s" else value)
            elif cell.get("t") == "inlineStr":
                values.append("".join(cell.itertext()))
    return "\n".join(values)


def pdf_text(path, cache):
    if shutil.which("pdftotext"):
        command = ["pdftotext", str(path), "-"]
    elif sys.platform == "darwin":
        command = ["/usr/bin/swift", "-module-cache-path", str(cache / "swift-cache"),
                   str(Path(__file__).parent / "tools/pdf_text.swift"), str(path)]
    else:
        raise OSError("Publisher PDF refresh needs pdftotext, or macOS with Swift/PDFKit")
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def aip_models(text):
    pattern = r"([0-9]{4}-[0-9]{3}[0-9X])((?:(?![0-9]{4}-[0-9]{3}[0-9X]).){0,300}?)(Hybrid|Gold OA)"
    result = {}
    for match in re.finditer(pattern, text, flags=re.S | re.I):
        for key in identifiers(match[1]):
            result[key] = "Hybrid OA" if match[3].casefold() == "hybrid" else "Gold OA"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--openalex-sources", required=True, type=Path,
                        help="Previously downloaded public Sources directory containing manifest.json")
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    by_id, _, _, _, issns = index()
    models = {}
    openalex_matches = defaultdict(list)
    manifest = json.loads((args.openalex_sources / "manifest.json").read_text())
    if manifest.get("entity") != "sources":
        raise ValueError("Expected a public OpenAlex Sources snapshot")
    scanned = 0
    for part in manifest["files"]:
        pieces = part["url"].split("/")
        path = args.openalex_sources / (pieces[-2] + "-" + pieces[-1])
        if path.stat().st_size != part["meta"]["content_length"]:
            raise ValueError("Incomplete public source part")
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                scanned += 1
                row = json.loads(line)
                if row.get("type") != "journal" or not isinstance(row.get("is_oa"), bool):
                    continue
                if not re.fullmatch(r"https://openalex\.org/S[0-9]+", row.get("id", "")):
                    continue
                keys = set().union(*(issns.get(value.replace("-", "").upper(), set()) for value in row.get("issn") or []))
                if len(keys) == 1:
                    key = next(iter(keys))
                    model = "Gold OA" if row["is_oa"] or row.get("is_in_doaj") is True else "Not fully OA"
                    openalex_matches[key].append({"model": model, "provider": "OpenAlex", "source": row["id"],
                                                 "as_of": manifest["date"], "checked": today})
    if scanned != manifest["record_count"]:
        raise ValueError("Incomplete OpenAlex source snapshot")
    for key, matches in openalex_matches.items():
        if len({row["model"] for row in matches}) == 1:
            models[key] = matches[0]

    publisher_matches = defaultdict(list)
    counts = {}
    for name, provider, model, kind, minimum, url in PUBLISHERS:
        path = args.cache / (name + "." + kind)
        if (not path.exists() or date.fromtimestamp(path.stat().st_mtime) != date.today()
                or (kind == "xlsx" and not zipfile.is_zipfile(path))):
            temporary = path.with_suffix(".tmp")
            subprocess.run(["curl", "--fail", "--silent", "--show-error", "--location", "--proto", "=https", "--proto-redir", "=https",
                            "--max-time", "60", "--max-filesize", "15000000", url, "-o", str(temporary)], check=True)
            temporary.replace(path)
        text = xlsx_text(path) if kind == "xlsx" else pdf_text(path, args.cache)
        entries = aip_models(text) if model is None else dict.fromkeys(identifiers(text), model)
        if len(entries) < minimum:
            raise ValueError(f"Unexpectedly incomplete {provider} publishing list")
        counts[name] = len(entries)
        for issn, value in entries.items():
            keys = issns.get(issn, set())
            if len(keys) == 1:
                publisher_matches[next(iter(keys))].append({"model": value, "provider": provider,
                    "source": url, "as_of": "2026 title list", "checked": today})
    for key, matches in publisher_matches.items():
        if len({row["model"] for row in matches}) == 1:
            models[key] = matches[0]
        else:
            models.pop(key, None)

    # Supplements fill missing model fields; they never establish Aalto funding eligibility
    write_snapshot("publishing-models.json.gz", {"checked": today, "publisher_counts": counts,
        "journals": {str(key): value for key, value in models.items() if key in by_id}})
    previous = json.loads((TARGET / "manifest.json").read_text())
    write_manifest({**previous["counts"], "publishing_model_records": len(models)}, previous["checked"])
    print(f"Prepared {len(models)} publishing-model supplements; lists: {counts}", flush=True)


if __name__ == "__main__":
    main()
