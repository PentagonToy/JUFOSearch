"""Serve the local journal finder and query its public sources."""

import argparse
import io
import json
import re
import subprocess
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen
from zoneinfo import ZoneInfo

JUFO = "https://jufo-rest.csc.fi/v2.1"
CROSSREF = "https://api.crossref.org/works"
TOPIC_ALIASES = {
    "physcis": "physics",
    "ml": "machine learning",
    "cfd": "computational fluid dynamics",
}
TITLE_STOP_WORDS = {"a", "an", "and", "for", "in", "of", "on", "the", "jufo"}
TOPIC_STARTERS = {
    "physics": ("0031-9007", "0034-4885", "1367-2630", "2211-3797"),
    "machine learning": ("0885-6125", "1532-4435", "0893-6080", "0162-8828",
                         "2666-8270", "2632-2153", "2993-5210"),
    "computational fluid dynamics": ("1070-6631", "0021-9991", "0045-7825", "0142-727X"),
}
TOPIC_DISCIPLINES = {
    "physics": {"114", "115"},
    "machine learning": {"113", "213"},
    "computational fluid dynamics": {"114", "214"},
}
ISSN_FIELDS = ("issn_electronic", "issn_print", "issnl")
LIST_URL = (
    "https://extra.kansalliskirjasto.fi/finelib_julkinen/lehtilistat/"
    "Elsevier/Freedom_publishing_title_list.xlsx"
)
AGREEMENT_END = date(2026, 12, 31)
AALTO_AGREEMENTS = "https://www.aalto.fi/en/services/open-access-agreements-by-publisher"
# Title-level observations from Aalto SciFree, matched against JUFO by ISSN.
# Quota availability can change before an agreement expires.
SCIFREE_CHECKED = "2026-11-05"
SCIFREE_TITLES = {
    "29935210": {
        "publisher": "Wiley", "status": "quota_exhausted", "model": "Pure OA",
        "until": "2026-12-31", "article_types": "Primary research articles and reviews",
        "quota": ("The 2026 Wiley full open access quota ran out in early September. "
                  "The hybrid quota ran out in late October. Aalto lists limited additional "
                  "funding for full open access journals. Contact acris@aalto.fi."),
        "guidelines": "https://finelib.fi/open-access-publishing-in-wiley-journals/",
    },
    "08856125": {
        "publisher": "Springer", "discount": 100, "model": "Hybrid",
        "until": "2027-12-31",
        "article_types": "Original papers, reviews, brief communications and continuing education",
        "quota": "The fee waiver depends on quota availability at acceptance.",
    },
    "26322153": {
        "publisher": "IOP Publishing", "discount": 100, "model": "Pure OA",
        "until": "2027-12-31",
        "article_types": "Research papers, focus collections, letters and reviews",
        "quota": "Aalto lists no article quota for this agreement.",
    },
}
ROOT = Path(__file__).resolve().parent / "public"
ASSETS = {"/": ("index.html", "text/html"), "/style.css": ("style.css", "text/css"),
          "/app.js": ("app.js", "text/javascript")}
ISSN = re.compile(r"[0-9]{4}-?[0-9]{3}[0-9X]", re.I)
NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
list_lock = Lock()
list_cache = (0, None, None)


def download(url, timeout=8):
    if sys.platform != "darwin":
        with urlopen(url, timeout=timeout) as response:
            payload = response.read(4_000_001)
    else:
        payload = download_macos(url, timeout)
    if len(payload) > 4_000_000:
        raise ValueError("Unexpected response size")
    return payload


def download_macos(url, timeout):
    # Use the system trust store for the FinELib HTTPS endpoint.
    try:
        return subprocess.run(
            ["/usr/bin/curl", "--fail", "--silent", "--show-error", "--location",
             "--proto", "=https", "--proto-redir", "=https", "--max-time", str(timeout),
             "--max-filesize", "4000000", url],
            check=True, capture_output=True,
        ).stdout
    except subprocess.CalledProcessError as error:
        raise OSError("Could not retrieve the upstream source") from error


def parse_title_list(payload):
    with zipfile.ZipFile(io.BytesIO(payload)) as workbook:
        strings = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
        shared = ["".join(node.itertext()) for node in strings]
        sheet = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))

    headers = {}
    journals = {}
    required = {"Publication title", "Online identifier", "APC discount (%)", "Publishing model"}
    for row in sheet.findall("x:sheetData/x:row", NS):
        values = {}
        for cell in row:
            value = cell.findtext("x:v", namespaces=NS)
            if value is not None:
                column = cell.get("r").rstrip("0123456789")
                values[column] = shared[int(value)] if cell.get("t") == "s" else value
        if not headers:
            if required <= set(values.values()):
                headers = {label: column for column, label in values.items()}
            continue
        issn = values.get(headers["Online identifier"], "").strip().upper()
        discount = values.get(headers["APC discount (%)"])
        if ISSN.fullmatch(issn) and discount in {"15", "100"}:
            key = issn.replace("-", "")
            title_url = values.get(headers.get("Title URL"), "")
            entry = (int(discount), values.get(headers["Publishing model"], ""), title_url)
            journals.setdefault(key, set()).add(entry)
    if not journals:
        raise ValueError("Unexpected FinELib title list format")
    return journals


def agreements():
    global list_cache
    with list_lock:
        if time.monotonic() >= list_cache[0]:
            try:
                titles = parse_title_list(download(LIST_URL))
                checked = datetime.now(ZoneInfo("Europe/Helsinki")).date().isoformat()
                list_cache = (time.monotonic() + 3600, titles, checked)
            except (OSError, ValueError, KeyError, IndexError, zipfile.BadZipFile, ET.ParseError):
                list_cache = (time.monotonic() + 60, None, None)
        return list_cache[1:]


def search_jufo(query, size=30):
    is_issn = ISSN.fullmatch(query)
    if is_issn:
        compact = query.replace("-", "").upper()
        query = compact[:4] + "-" + compact[4:]
    parameters = {"issn" if is_issn else "name": query, "type": "series", "_size": size}
    rows = json.loads(download(f"{JUFO}/search?{urlencode(parameters)}"))
    if not isinstance(rows, list):
        raise ValueError("Unexpected JUFO response")
    return sorted(rows, key=lambda row: (row.get("title", "").casefold() != query.casefold(),
                                         row.get("is_active") is not True))


def folded(text):
    return "".join(char for char in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(char))


def title_keywords(text):
    return list(dict.fromkeys(
        word.removesuffix("s") if len(word) > 4 and not word.endswith(("ss", "ics")) else word
        for word in re.findall(r"[^\W_]+", folded(text))
        if len(word) > 2 and word not in TITLE_STOP_WORDS
    ))


def acronym_key(text):
    return re.sub(r"[^\w&]|_", "", folded(text))


def title_acronyms(title):
    words = re.findall(r"[^\W_]+|&", folded(title))
    if len(words) < 2:
        return set()
    words = ["and" if word == "&" else word for word in words]
    significant = [word for word in words if word not in TITLE_STOP_WORDS or word == "and"]
    keys = {
        "".join(word[0] for word in words),
        "".join(word[0] for word in significant if word != "and"),
    }
    if "and" in significant:
        for conjunction in ("&", "n"):
            keys.add("".join(conjunction if word == "and" else word[0] for word in significant))
    return keys


@lru_cache(maxsize=1)
def acronym_index():
    path = Path(__file__).with_name("journal-acronyms.json")
    return json.loads(path.read_text(encoding="utf-8"))


def acronym_results(query):
    if not re.fullmatch(r"(?:[^\W_]|[&.\s])+", query):
        return []
    parts = query.replace(".", " ").replace("&", " ").split()
    if len(parts) > 1 and any(len(part) != 1 for part in parts):
        return []
    key = acronym_key(query)
    if not 2 <= len(key) <= 8:
        return []
    ids = acronym_index().get(key, ())
    if not ids:
        return []

    def current_record(jufo_id):
        return json.loads(download(f"{JUFO}/channel/{jufo_id}"))

    with ThreadPoolExecutor(max_workers=6) as pool:
        return [dict(row, matched_acronym=key.upper())
                for batch in pool.map(current_record, ids[:30])
                for row in batch if row.get("is_active")]


def normalise_journal_query(query):
    query = unicodedata.normalize("NFKC", query).strip().strip('"“”').strip()
    query = re.sub(r"\s+jufo$", "", query, flags=re.I)
    return re.sub(r"[‐‑‒–−]", "-", query)


def search_journal(query):
    query = normalise_journal_query(query)
    if ISSN.fullmatch(query):
        return search_jufo(query)
    rows = search_jufo(query)
    if any(row["title"].casefold() == query.casefold() for row in rows):
        return rows
    aliases = acronym_results(query)
    if aliases:
        alias_ids = {row["jufo_id"] for row in aliases}
        return (aliases + [row for row in rows if row["jufo_id"] not in alias_ids])[:30]
    terms = title_keywords(query)
    if rows or len(terms) < 2:
        return rows

    with ThreadPoolExecutor(max_workers=4) as pool:
        batches = pool.map(lambda term: search_jufo(term, size=60), terms[:4])
        candidates = {row["jufo_id"]: row for batch in batches for row in batch}

    overlaps = {
        key: set(terms).intersection(title_keywords(row["title"]))
        for key, row in candidates.items()
    }
    frequency = {term: sum(term in match for match in overlaps.values()) for term in terms}
    return sorted(
        (row for key, row in candidates.items() if overlaps[key]),
        key=lambda row: (
            -len(overlaps[row["jufo_id"]]),
            row.get("is_active") is not True,
            -sum(1 / frequency[term] for term in overlaps[row["jufo_id"]]),
        ),
    )[:30]


def journal_identifiers(row):
    return {row[field].replace("-", "").upper() for field in ISSN_FIELDS if row.get(field)}


def find_venue(identifiers):
    keys = {issn.replace("-", "").upper() for issn in identifiers}
    for issn in identifiers:
        matches = [row for row in search_jufo(issn)
                   if row.get("is_active") and keys & journal_identifiers(row)]
        if len(matches) == 1:
            return matches[0]
    return None


def topic_works(topic):
    since = date.today().year - 4
    parameters = {
        "query.title": topic,
        "filter": f"type:journal-article,from-pub-date:{since}-01-01",
        "rows": 60,
        "select": "DOI,title,container-title,ISSN",
    }
    data = json.loads(download(f"{CROSSREF}?{urlencode(parameters)}", timeout=15))
    terms = set(re.findall(r"[^\W_]+", topic.casefold()))
    venues = {}
    for item in data["message"]["items"]:
        titles = item.get("title") or []
        names = item.get("container-title") or []
        identifiers = {issn for issn in item.get("ISSN", []) if ISSN.fullmatch(issn)}
        doi = item.get("DOI")
        if not (titles and names and identifiers and doi):
            continue
        if not terms <= set(re.findall(r"[^\W_]+", titles[0].casefold())):
            continue
        key = (names[0].casefold(), tuple(sorted(identifiers)))
        venue = venues.setdefault(key, {"issns": key[1], "works": {}})
        venue["works"][doi] = {"title": titles[0], "doi": doi}
    return sorted(venues.values(), key=lambda venue: -len(venue["works"]))[:8]


def search_topic(topic):
    starters = TOPIC_STARTERS.get(topic, ())
    disciplines = TOPIC_DISCIPLINES.get(topic)
    matches = {}
    notices = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        articles = pool.submit(topic_works, topic)
        pending = [(pool.submit(find_venue, (issn,)), None) for issn in starters]
        try:
            venues = articles.result()
        except (OSError, ValueError, KeyError, TypeError):
            if not pending:
                raise OSError("Article search is temporarily unavailable.") from None
            notices.append("Article search is temporarily unavailable. Showing topic starting points.")
            venues = []
        pending.extend((pool.submit(find_venue, venue["issns"][:2]), venue)
                       for venue in venues)
        incomplete = False
        for future, venue in pending:
            try:
                row = future.result()
            except (OSError, ValueError):
                incomplete = True
                continue
            if row is None:
                continue
            if venue and disciplines and not disciplines.intersection(
                field["id"] for field in row.get("okm_disciplines", [])
            ):
                continue
            match = matches.setdefault(row["jufo_id"], row)
            if venue:
                examples = list(venue["works"].values())
                match["examples"] = list({work["doi"]: work for work in
                                          match.get("examples", []) + examples}.values())[:2]
        if incomplete:
            if not matches:
                raise OSError("JUFO is temporarily unavailable.")
            notices.append("Some journal records could not be checked in JUFO.")
    return list(matches.values()), notices


def add_agreements(rows):
    today = datetime.now(ZoneInfo("Europe/Helsinki")).date()
    lookup = any(row.get("is_active") and journal_identifiers(row) for row in rows)
    titles, checked = agreements() if lookup and today <= AGREEMENT_END else (None, None)
    for row in rows:
        row["agreement"] = None
        row["agreement_status"] = "unverified"
        if not row.get("is_active"):
            continue
        identifiers = journal_identifiers(row)
        verified = identifiers & SCIFREE_TITLES.keys()
        if len(verified) == 1:
            entry = SCIFREE_TITLES[next(iter(verified))]
            if SCIFREE_CHECKED <= today.isoformat() <= entry["until"]:
                row["agreement"] = {
                    "licence": "CC BY", "checked": SCIFREE_CHECKED,
                    "guidelines": AALTO_AGREEMENTS, **entry,
                }
            else:
                row["agreement_status"] = "expired"
            continue
        if titles is None:
            if (row.get("publisher_name") or "").casefold().startswith("elsevier"):
                row["agreement_status"] = "expired" if today > AGREEMENT_END else "unavailable"
        else:
            matches = set()
            for key in identifiers:
                matches.update(titles.get(key, ()))
            if len(matches) == 1:
                discount, model, title_url = matches.pop()
                row["agreement"] = {"discount": discount, "model": model, "source": LIST_URL,
                                    "until": AGREEMENT_END.isoformat(), "checked": checked,
                                    "publisher": "Elsevier", "licence": "CC BY",
                                    "journal_url": title_url if title_url.startswith("https://www.sciencedirect.com/") else None,
                                    "guidelines": AALTO_AGREEMENTS, "article_types": "Peer-reviewed articles",
                                    "quota": "Aalto reports that the quota was removed for the rest of 2026."}


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, media, body):
        self.send_response(status)
        self.send_header("Content-Type", f"{media}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, data):
        self.respond(status, "application/json", json.dumps(data).encode())

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path in ASSETS:
            filename, media = ASSETS[url.path]
            self.respond(200, media, (ROOT / filename).read_bytes())
        elif url.path == "/api/search":
            parameters = parse_qs(url.query)
            query = parameters.get("q", [""])[0].strip()
            if not 2 <= len(query) <= 160:
                self.send_json(400, {"error": "Enter a journal title, ISSN or research topic."})
                return
            normalised = " ".join(query.casefold().split())
            topic = TOPIC_ALIASES.get(normalised, normalised)
            topic_mode = not ISSN.fullmatch(normalise_journal_query(query)) and (
                parameters.get("mode") == ["topic"] or topic in TOPIC_STARTERS
            )
            try:
                results, notices = search_topic(topic) if topic_mode else (search_journal(query), [])
                add_agreements(results)
            except (OSError, ValueError):
                service = "Topic search" if topic_mode else "JUFO"
                self.send_json(502, {"error": f"{service} is temporarily unavailable. Try again shortly."})
            else:
                self.send_json(200, {"results": results, "notices": notices,
                                     "topic": topic if topic_mode else None})
        else:
            self.send_error(404)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        print(f"JUFOSearch is running at http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
