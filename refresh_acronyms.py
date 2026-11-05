"""Build the journal acronym index from CSC's nightly JUFO export."""

import io
import json
import zipfile
from collections import defaultdict
from pathlib import Path
from urllib.request import urlopen

from server import acronym_key, title_acronyms

SOURCE = "https://jufo-rest.csc.fi/v1.1/massa.json.zip"
TARGET = Path(__file__).with_name("journal-acronyms.json")


def main():
    with urlopen(SOURCE, timeout=30) as response:
        archive = response.read(12_000_001)
    if len(archive) > 12_000_000:
        raise ValueError("Unexpected JUFO archive size")
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        records = json.loads(bundle.read(bundle.namelist()[0]))

    index = defaultdict(set)
    for row in records:
        if (row["Type"].casefold() != "lehti/sarja" or row["Active"] != "Active"
                or row["Scientific"] != "1"):
            continue
        keys = title_acronyms(row["Name"]) | title_acronyms(row.get("Other_Title") or "")
        if row.get("Abbreviation"):
            keys.add(acronym_key(row["Abbreviation"]))
        for key in keys:
            if 2 <= len(key) <= 8:
                index[key].add(int(row["Jufo_ID"]))
    lines = [f"  {json.dumps(key)}: {json.dumps(sorted(ids))}" for key, ids in sorted(index.items())]
    if not lines:
        raise ValueError("JUFO export contained no acronym candidates")
    TARGET.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")
    print(f"Wrote {len(index):,} acronym keys to {TARGET.name}")


if __name__ == "__main__":
    main()
