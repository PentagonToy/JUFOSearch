"""On-demand JCT guidance for worldwide institutions and supported funders."""

import json
import re
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

JCT = "https://api.journalcheckertool.org"
FUNDERS = json.loads((Path(__file__).with_name("data") / "oa-funders.json").read_text())["funders"]
DEFAULT_INSTITUTION = {"id": "020hwjq30", "title": "Aalto University", "country": "Finland"}
ROR = re.compile(r"0[a-z0-9]{6}[0-9]{2}")


class JournalMismatch(RuntimeError):
    """JCT resolved a different journal, so no policy verdict is usable."""


def fetch(url):
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "JUFOSearch/1.0"})
    with urlopen(request, timeout=10) as response:
        raw = response.read(512001)
    if len(raw) > 512000:
        raise ValueError("Unexpected OA response size")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Unexpected OA response")
    return data


@lru_cache(maxsize=128)
def institutions(query, day):
    data = fetch(JCT + "/suggest/institution/" + quote(query, safe=""))
    rows = [{"id": row["id"], "title": row["title"], "country": row.get("country") or "Not specified"}
            for row in data.get("data", [])
            if ROR.fullmatch(row.get("id", ""))
            and isinstance(row.get("title"), str)]
    return sorted(rows, key=lambda row: (row["country"], row["title"].casefold()))


@lru_cache(maxsize=128)
def institution_country(ror, day):
    data = fetch("https://api.ror.org/v2/organizations/" + ror)
    if data.get("id") != "https://ror.org/" + ror or data.get("status") != "active":
        raise ValueError("Institution is not active in ROR")
    return {row.get("geonames_details", {}).get("country_code") for row in data.get("locations", [])}


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "svg"):
            self.hidden += 1
        if tag in ("p", "br", "li"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "svg"):
            self.hidden = max(0, self.hidden - 1)
        if tag in ("p", "li"):
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(html):
    parser = PlainText()
    parser.feed(html)
    return " ".join("".join(parser.parts).split())


@lru_cache(maxsize=64)
def language(funder, day):
    return fetch(JCT + "/funder_language/" + funder)


def validate(issn, funder, ror):
    if not re.fullmatch(r"[0-9]{4}-[0-9]{3}[0-9X]", issn):
        raise ValueError("Select a journal with a valid ISSN")
    if funder not in {row["id"] for row in FUNDERS}:
        raise ValueError("Select a funder supported by JCT")
    if not ROR.fullmatch(ror):
        raise ValueError("Select an institution from the suggestions")


@lru_cache(maxsize=128)
def check(identifiers, funder, ror, hour):
    for index, identifier in enumerate(identifiers):
        try:
            return calculate(identifier, funder, ror, hour)
        except JournalMismatch:
            if index == len(identifiers) - 1:
                raise


@lru_cache(maxsize=128)
def calculate(issn, funder, ror, hour):
    validate(issn, funder, ror)
    parameters = {"issn": issn, "funder": funder, "ror": ror}
    with ThreadPoolExecutor(max_workers=3) as pool:
        institution = pool.submit(institution_country, ror, hour // 24)
        wording = pool.submit(language, funder, hour // 24)
        data = fetch(JCT + "/calculate?" + urlencode(parameters))
        institution.result()
        pack = wording.result().get("cards", {})
    request = data.get("request", {})
    journals = request.get("journal", [])
    if len(journals) != 1 or issn not in journals[0].get("issn", []):
        raise JournalMismatch("JCT could not match this journal's ISSN. Select the exact journal on JCT.")
    if (type(data.get("compliant")) is not bool
            or not any(issn in row.get("issn", []) for row in request.get("journal", []))
            or not any(row.get("id") == funder for row in request.get("funder", []))
            or not any(row.get("id") == ror for row in request.get("institution", []))):
        raise RuntimeError("JCT could not confirm the selected combination")
    values = {"title": request["journal"][0].get("title", issn),
              "publisher": request["journal"][0].get("publisher", "the publisher"),
              "institution": request["institution"][0].get("title", ror),
              "funder": request["funder"][0].get("title", funder)}
    for route in data.get("results", []):
        for log in route.get("log", []):
            for key, value in log.get("parameters", {}).items():
                if key == "end_date" and isinstance(value, list) and value:
                    values[key] = str(value[0])
        for qualification in route.get("qualifications", []):
            caveat = qualification.get("oa_exception_caveat", {}).get("caveat")
            if isinstance(caveat, str):
                values["oa_exception_caveat"] = caveat
    cards = []
    for card in data.get("cards", []):
        text = pack.get(card.get("id"), {})
        title = plain_text(text.get("title", "Check JCT guidance"))
        conditions = text.get("body", {}).get("default", "See the full guidance in JCT.")
        for key, value in values.items():
            conditions = conditions.replace("{" + key + "}", plain_text(str(value)))
        paragraph = re.search(r"<p\b[^>]*>(.*?)</p>", conditions, re.I | re.S)
        summary = plain_text(paragraph[1] if paragraph else conditions)
        if card["id"] in ("ta", "ta_aq") and values.get("end_date"):
            summary = "Agreement ends " + values["end_date"] + ". Check author eligibility and conditions below."
            if card["id"] == "ta_aq":
                summary = "Corresponding author must qualify. " + summary
        conditions = plain_text(conditions)
        if re.search(r"\{[a-z_]+\}", conditions):
            conditions = "See the full conditions in JCT."
            summary = conditions
        cards.append({"id": card["id"], "title": title, "available": card.get("compliant") is True,
                      "summary": summary, "conditions": conditions})
    if data["compliant"] != any(card["available"] for card in cards):
        raise RuntimeError("JCT returned inconsistent publishing routes")
    return {"compliant": data["compliant"], "cards": cards,
            "checked": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "https://journalcheckertool.org/?" + urlencode(parameters),
            "institution": values["institution"], "funder": values["funder"], "ror": ror}
