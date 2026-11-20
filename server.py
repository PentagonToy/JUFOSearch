"""Serve the local journal finder and query its public sources."""

import argparse
import gzip
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
from html import unescape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from catalogue import search_titles, search_profiles, snapshot

JUFO = "https://jufo-rest.csc.fi/v2.1"
CROSSREF = "https://api.crossref.org/works"
TOPIC_ALIASES = {
    "physcis": "physics",
    "ml": "machine learning",
    "cfd": "computational fluid dynamics",
    "sgs": "subgrid scale",
    "tci": "turbulence chemistry interaction",
    "pasr": "partially stirred reactor",
}
TOPIC_VARIANTS = {
    "computational fluid dynamics": ("computational fluid dynamics", "cfd", "large eddy simulation", "direct numerical simulation"),
    "machine learning": ("machine learning", "deep learning", "neural network", "ml", "random forest", "support vector machine", "reinforcement learning", "symbolic regression", "clustering"),
    "subgrid scale": ("subgrid scale", "subgrid", "subfilter scale", "sgs"),
    "turbulence chemistry interaction": ("turbulence chemistry interaction", "turbulent chemistry interaction", "turbulence chemistry", "tci"),
    "partially stirred reactor": ("partially stirred reactor", "pasr"),
}
# Broader discovery terms only; article evidence still requires the original concepts
PROFILE_HINTS = {
    "partially stirred reactor": ("turbulent combustion",),
    "subgrid scale": ("large eddy simulation",),
    "turbulence chemistry interaction": ("turbulent combustion",),
}
TITLE_STOP_WORDS = {"a", "an", "and", "for", "in", "of", "on", "the", "jufo"}
ISSN_FIELDS = ("issn_electronic", "issn_print", "issnl")
RESULT_FIELDS = (
    "jufo_id", "title", "publisher_name", *ISSN_FIELDS, "website", "is_active",
    "level", "level_history", "year_start", "okm_disciplines", "matched_acronym", "examples",
    "topic_match", "matched_keywords", "keyword_total", "agreement", "agreement_status",
    "profile_keywords", "matched_topics", "quartiles", "publishing_model",
)
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
          "/app.js": ("app.js", "text/javascript"), "/theme.js": ("theme.js", "text/javascript")}
ISSN = re.compile(r"[0-9]{4}-?[0-9]{3}[0-9X]", re.I)
NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
crossref_lock = Lock()
crossref_checked = 0


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
        if error.returncode == 22 and b"429" in (error.stderr or b""):
            raise HTTPError(url, 429, "Too many requests", None, None) from error
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


@lru_cache(maxsize=1)
def agreements():
    data = snapshot("agreements")
    return {key: {tuple(value) for value in values} for key, values in data["titles"].items()}, data["checked"]


def search_jufo(query, size=100, offset=0):
    rows, _ = search_titles(query)
    return rows[offset:offset + size]


def search_prepared(query):
    query = normalise_journal_query(query)
    normalised = " ".join(query.casefold().split())
    title_query = TOPIC_ALIASES.get(normalised, query)
    rows, exact = search_titles(title_query)
    if exact and normalised not in TOPIC_ALIASES:
        return rows, False

    concepts = keyword_topics(query)
    multiple = len(concepts) > 1 or bool(re.search(r"[,;，]", query))
    terms = set(title_keywords(query))
    title_overlap = any(len(terms.intersection(title_keywords(row["title"]))) >= max(2, len(terms) - 1)
                        for row in rows)
    if not multiple and rows and normalised not in TOPIC_ALIASES and (len(terms) < 2 or title_overlap):
        return rows, False

    related = search_profiles(concepts, TOPIC_VARIANTS, PROFILE_HINTS)
    matches = {row["jufo_id"]: row for row in ([] if multiple else rows)}
    for row in related:
        matches[row["jufo_id"]] = row

    return list(matches.values()), True


def folded(text):
    return "".join(char for char in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(char))


def title_keywords(text):
    return list(dict.fromkeys(
        word.removesuffix("s") if len(word) > 4 and not word.endswith(("ss", "ics")) else word
        for word in re.findall(r"[^\W_]+", folded(text))
        if len(word) > 2 and word not in TITLE_STOP_WORDS
    ))


def normalise_journal_query(query):
    query = unicodedata.normalize("NFKC", query).strip().strip('"“”').strip()
    query = re.sub(r"\s+jufo$", "", query, flags=re.I)
    return re.sub(r"[‐‑‒–−]", "-", query)


def search_journal(query, offset=0):
    return search_jufo(normalise_journal_query(query), offset=offset)


def search_journal_batch(query, offset=0, pages=1):
    rows = search_jufo(normalise_journal_query(query), size=pages * 100, offset=offset)
    return rows, offset + len(rows) if len(rows) == pages * 100 else None


def keyword_topics(query):
    query = normalise_journal_query(query)
    parts = re.split(r"[,;，]+", query)
    words = query.split()
    if len(parts) == 1 and len(words) > 1 and all(word.casefold() in TOPIC_ALIASES for word in words):
        parts = words

    topics = {}
    for part in parts:
        normalised = " ".join(part.casefold().split())
        if normalised:
            topic = TOPIC_ALIASES.get(normalised, normalised)
            label = normalised.upper() if normalised in TOPIC_ALIASES and len(normalised) <= 3 else part.strip()
            topics.setdefault(topic, label)

    return topics


def topic_words(text):
    text = re.sub(r"\bsub[-\s]+grid\b", "subgrid", folded(text))
    words = set(title_keywords(text))
    words.update(word for word in re.findall(r"[^\W_]+", text)
                 if len(word) <= 2 and word not in TITLE_STOP_WORDS)
    return words


def matches_topic(topic, title):
    words = topic_words(title)
    for variant in TOPIC_VARIANTS.get(topic, (topic,)):
        terms = topic_words(variant)
        if terms and terms <= words:
            return True
    return False


def compact_result(row):
    result = {field: row[field] for field in RESULT_FIELDS if field in row}
    external = row.get("external") or {}
    result["external"] = {field: external[field] for field in ("oa_info", "license", "index_info")
                          if field in external}
    return result


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


def topic_works(topic, keywords=None, minimum=1):
    global crossref_checked
    since = date.today().year - 9
    parameters = {
        "query.bibliographic" if keywords else "query.title": topic,
        "filter": f"type:journal-article,from-pub-date:{since}-01-01",
        "rows": 60,
        "select": "DOI,title,container-title,ISSN,abstract",
    }
    # Crossref's public list endpoint permits one request per second and one in flight.
    with crossref_lock:
        for attempt in range(2):
            time.sleep(max(0, 1.1 - (time.monotonic() - crossref_checked)))
            crossref_checked = time.monotonic()
            try:
                data = json.loads(download(f"{CROSSREF}?{urlencode(parameters)}", timeout=15))
                break
            except HTTPError as error:
                retry_after = error.headers.get("Retry-After", "1") if error.headers else "1"
                if error.code != 429 or attempt or not retry_after.isdigit() or int(retry_after) > 2:
                    raise
                time.sleep(max(1, int(retry_after)))
    venues = {}
    for item in data["message"]["items"]:
        titles = item.get("title") or []
        names = item.get("container-title") or []
        identifiers = {issn for issn in item.get("ISSN", []) if ISSN.fullmatch(issn)}
        doi = item.get("DOI")
        if not (titles and names and identifiers and doi):
            continue
        title = unescape(re.sub(r"</?[A-Za-z][^>]*>", "", titles[0]))
        abstract = unescape(re.sub(r"<[^>]*>", " ", item.get("abstract") or ""))
        text = title + " " + abstract
        matched = [label for term, label in (keywords or {topic: topic}).items() if matches_topic(term, text)]
        if len(matched) < minimum or (minimum == 1 and not matches_topic(topic, text)):
            continue
        key = (names[0].casefold(), tuple(sorted(identifiers)))
        venue = venues.setdefault(key, {"issns": key[1], "works": {}})
        work = {"title": title, "doi": doi}
        if keywords:
            work["keywords"] = matched
            work["abstract_keywords"] = [label for term, label in keywords.items()
                                         if label in matched and not matches_topic(term, title)]
        venue["works"][doi] = work
    if keywords:
        return sorted(venues.values(), key=lambda venue: keyword_rank(list(venue["works"].values())))[:24 if minimum > 1 else 12]
    return sorted(venues.values(), key=lambda venue: -len(venue["works"]))[:8]


def keyword_rank(works):
    coverage = {keyword for work in works for keyword in work["keywords"]}
    return (-max((len(work["keywords"]) for work in works), default=0), -len(coverage), -len(works))


def search_keywords(topics):
    venues = {}
    notices = []
    successful = 0
    deadline = time.monotonic() + 25
    lookups = [(" ".join(topics), "Combined keyword", 2)] if len(topics) > 1 else []
    lookups.extend((topic, label, 1) for topic, label in topics.items())
    for topic, label, minimum in lookups:
        try:
            if time.monotonic() >= deadline:
                raise OSError("Article lookup budget exhausted")
            batch = topic_works(topic, keywords=topics, minimum=minimum)
        except (OSError, ValueError, KeyError, TypeError):
            notices.append(f"{label} article lookup unavailable.")
            continue
        successful += 1
        for venue in batch:
            key = tuple(sorted(venue["issns"]))
            match = venues.setdefault(key, {"issns": key, "works": {}})
            match["works"].update(venue["works"])
    if not successful:
        raise OSError("Article search is temporarily unavailable.")

    candidates = [venue for venue in venues.values()
                  if len(topics) == 1 or any(len(work["keywords"]) >= 2 for work in venue["works"].values())]
    candidates = sorted(candidates, key=lambda venue: keyword_rank(list(venue["works"].values())))[:32]
    matches = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        pending = [(venue, pool.submit(find_venue, venue["issns"][:2])) for venue in candidates]
        for venue, future in pending:
            try:
                row = future.result()
            except (OSError, ValueError):
                if "Some JUFO records unavailable." not in notices:
                    notices.append("Some JUFO records unavailable.")
                continue
            if row is None:
                continue
            match = matches.setdefault(row["jufo_id"], dict(row, examples=[], matched_keywords=[], keyword_total=len(topics)))
            works = {work["doi"]: work for work in match["examples"]}
            works.update(venue["works"])
            match["examples"] = sorted(works.values(), key=lambda work: -len(work["keywords"]))
            coverage = {keyword for work in match["examples"] for keyword in work["keywords"]}
            match["matched_keywords"] = [label for label in topics.values() if label in coverage]

    results = sorted(matches.values(), key=lambda row: keyword_rank(row["examples"]))
    for row in results:
        remaining = row["examples"]
        examples = []
        covered = set()
        for _ in range(min(3, len(remaining))):
            work = max(remaining, key=lambda item: (len(set(item["keywords"]) - covered), len(item["keywords"])))
            examples.append(work)
            covered.update(work["keywords"])
            remaining.remove(work)
        row["examples"] = examples
    return results, notices


def search_topic(topic):
    return search_profiles(keyword_topics(topic), TOPIC_VARIANTS, PROFILE_HINTS), []


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


def add_quartiles(rows):
    data = snapshot("quartiles")
    context = {key: data[key] for key in ("edition", "snapshot_date", "citation_year", "publication_years", "cohort")}
    for row in rows:
        entry = data["journals"].get(str(row["jufo_id"]))
        row["quartiles"] = {**entry, **context} if entry else None


def add_publishing_models(rows):
    data = snapshot("publishing-models")["journals"]
    for row in rows:
        row["publishing_model"] = data.get(str(row["jufo_id"]))


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, media, body, cache="no-store"):
        encodings = getattr(self, "headers", {}).get("Accept-Encoding", "").lower().split(",")
        compressed = media == "application/json" and "gzip" in {value.strip() for value in encodings}
        if compressed:
            body = gzip.compress(body, compresslevel=3)
        self.send_response(status)
        self.send_header("Content-Type", f"{media}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", cache)
        if media == "application/json":
            self.send_header("Vary", "Accept-Encoding")
        if compressed:
            self.send_header("Content-Encoding", "gzip")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, data):
        cacheable = (status == 200 and not data.get("notices")
                     and all(row.get("agreement_status") != "unavailable" for row in data.get("results", [])))
        cache = "public, max-age=0, s-maxage=300" if cacheable else "no-store"
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
        self.respond(status, "application/json", body, cache=cache)

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
            mode = parameters.get("mode", ["journal"])[0]
            if mode not in {"journal", "auto", "fast", "topic", "articles"}:
                self.send_json(400, {"error": "Invalid search mode."})
                return
            topics = keyword_topics(query)
            if mode in {"auto", "topic", "fast", "articles"} and (not topics or len(topics) > 8):
                self.send_json(400, {"error": "Enter between 1 and 8 keywords."})
                return
            topic_mode = (parameters.get("mode") == ["topic"]
                          and not ISSN.fullmatch(normalise_journal_query(query)))
            offset_text = parameters.get("offset", ["0"])[0]
            if not offset_text.isascii() or not offset_text.isdigit() or len(offset_text) > 5:
                self.send_json(400, {"error": "Invalid search page. Start a new search."})
                return
            offset = int(offset_text)
            pages_text = parameters.get("batch", ["1"])[0]
            if pages_text not in {"1", "5"}:
                self.send_json(400, {"error": "Invalid search batch. Start a new search."})
                return
            pages = int(pages_text)
            try:
                next_offset = None
                notices = []
                if mode in {"fast", "auto"}:
                    results, topic_mode = search_prepared(query)
                    if len(results) > offset + 1000:
                        next_offset = offset + 1000
                    results = results[offset:offset + 1000]
                elif mode == "articles":
                    topic_mode = True
                    results, notices = search_keywords(topics)
                elif topic_mode:
                    results, notices = search_topic(topic)
                    if len(results) > offset + 1000:
                        next_offset = offset + 1000
                    results = results[offset:offset + 1000]
                else:
                    results, next_offset = search_journal_batch(query, offset, pages)
                add_agreements(results)
                add_quartiles(results)
                add_publishing_models(results)
            except (OSError, ValueError):
                service = "Topic search" if topic_mode else "JUFO"
                self.send_json(502, {"error": f"{service} is temporarily unavailable. Try again shortly."})
            else:
                self.send_json(200, {"results": [compact_result(row) for row in results], "notices": notices,
                                     "next_offset": next_offset,
                                     "catalogue_checked": snapshot("catalogue")["checked"],
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
