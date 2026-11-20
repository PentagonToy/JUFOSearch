"""Regression tests for journal search without upstream requests."""

import json
import io
import gzip
import unittest
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import patch

import server


class JournalSearchTests(unittest.TestCase):
    def test_json_compression_preserves_utf8_and_length(self):
        handler = server.Handler.__new__(server.Handler)
        handler.headers = {"Accept-Encoding": "gzip"}
        handler.wfile = io.BytesIO()
        body = json.dumps({"publisher": "Şükrü"}, ensure_ascii=False).encode()
        with (patch.object(handler, "send_response"), patch.object(handler, "end_headers"),
              patch.object(handler, "send_header") as header):
            handler.respond(200, "application/json", body)
        encoded = handler.wfile.getvalue()
        self.assertEqual(gzip.decompress(encoded), body)
        header.assert_any_call("Content-Length", str(len(encoded)))
        header.assert_any_call("Content-Encoding", "gzip")
        handler.headers = {"Accept-Encoding": "gzip;q=0"}
        handler.wfile = io.BytesIO()
        with (patch.object(handler, "send_response"), patch.object(handler, "end_headers"),
              patch.object(handler, "send_header")):
            handler.respond(200, "application/json", body)
        self.assertEqual(handler.wfile.getvalue(), body)

    def test_crossref_requests_are_spaced_without_parallel_calls(self):
        with (patch.object(server, "download", return_value=b'{"message":{"items":[]}}'),
              patch.object(server, "crossref_checked", 0),
              patch.object(server.time, "monotonic", return_value=100),
              patch.object(server.time, "sleep") as sleep):
            server.topic_works("subgrid scale")
            server.topic_works("machine learning")
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0, 1.1])

    def test_crossref_rate_limit_gets_one_bounded_retry(self):
        limited = server.HTTPError(server.CROSSREF, 429, "Rate limited", {"Retry-After": "1"}, None)
        with (patch.object(server, "download", side_effect=[limited, b'{"message":{"items":[]}}']) as download,
              patch.object(server.time, "sleep")):
            self.assertEqual(server.topic_works("reactor"), [])
        self.assertEqual(download.call_count, 2)

        for code, delay in [(429, "60"), (429, "Wed, 18 Nov 2026 12:00:00 GMT"), (503, "1")]:
            error = server.HTTPError(server.CROSSREF, code, "Unavailable", {"Retry-After": delay}, None)
            with (patch.object(server, "download", side_effect=error) as download,
                  patch.object(server.time, "sleep")):
                with self.assertRaises(server.HTTPError):
                    server.topic_works("reactor")
                self.assertEqual(download.call_count, 1)

    def test_macos_preserves_rate_limit_status_for_the_shared_retry(self):
        error = server.subprocess.CalledProcessError(22, "curl", stderr=b"curl: (22) HTTP error: 429")
        with patch.object(server.subprocess, "run", side_effect=error):
            with self.assertRaises(server.HTTPError) as caught:
                server.download_macos(server.CROSSREF, 8)
        self.assertEqual(caught.exception.code, 429)

    def test_keyword_lists_expand_deduplicate_and_preserve_phrases(self):
        expected = {"computational fluid dynamics": "CFD", "machine learning": "ML",
                    "subgrid scale": "SGS", "turbulence chemistry interaction": "TCI"}
        self.assertEqual(server.keyword_topics("CFD, ML, SGS, TCI"), expected)
        self.assertEqual(server.keyword_topics("cfd ML sgs tci"), expected)
        self.assertEqual(server.keyword_topics("CFD, cfd, machine learning"),
                         {"computational fluid dynamics": "CFD", "machine learning": "machine learning"})
        self.assertEqual(server.keyword_topics("C&F"), {"c&f": "C&F"})
        self.assertEqual(server.keyword_topics("ml, pasr"),
                         {"machine learning": "ML", "partially stirred reactor": "pasr"})

    def test_keyword_matching_handles_hyphens_plurals_and_method_names(self):
        title = "Neural-network sub-grid-scale models for large-eddy simulations"
        for topic in ("computational fluid dynamics", "machine learning", "subgrid scale"):
            self.assertTrue(server.matches_topic(topic, title))
        self.assertTrue(server.matches_topic("turbulence chemistry interaction", "Turbulence–chemistry interactions in flames"))
        self.assertTrue(server.matches_topic("machine learning", "ML for turbulence"))
        self.assertFalse(server.matches_topic("machine learning", "Clinical scale measurements"))
        self.assertFalse(server.matches_topic("turbulence chemistry interaction", title))

    def test_keyword_article_search_retains_only_evidenced_concepts(self):
        payload = {"message": {"items": [
            {"DOI": "10.1/sgs", "title": ["Neural-network sub-grid-scale models for large-eddy simulations"],
             "container-title": ["Fluid journal"], "ISSN": ["1234-5678"]},
            {"DOI": "10.1/other", "title": ["Machine learning for medical imaging"],
             "container-title": ["Clinical journal"], "ISSN": ["1234-5679"]},
        ]}}
        topics = server.keyword_topics("CFD, ML, SGS, TCI")
        with patch.object(server, "download", return_value=json.dumps(payload).encode()):
            venues = server.topic_works("subgrid scale", keywords=topics)
        self.assertEqual(len(venues), 1)
        self.assertEqual(venues[0]["works"]["10.1/sgs"]["keywords"], ["CFD", "ML", "SGS"])

    def test_keyword_search_merges_issn_variants_and_ranks_shared_articles(self):
        topics = server.keyword_topics("CFD, ML, SGS, TCI")
        shared = {"title": "Neural SGS LES", "doi": "10.1/shared", "keywords": ["CFD", "ML", "SGS"]}
        flame = {"title": "TCI flow model", "doi": "10.1/flame", "keywords": ["CFD", "TCI"]}
        generic = {"title": "ML paper", "doi": "10.1/ml", "keywords": ["ML"]}

        def articles(topic, keywords=None, minimum=1):
            if topic == "subgrid scale":
                raise OSError("Unavailable")
            return [
                {"issns": ("1234-5678",), "works": {shared["doi"]: shared}},
                {"issns": ("1234-5679",), "works": {flame["doi"]: flame}},
                {"issns": ("1234-5680",), "works": {generic["doi"]: generic}},
            ]

        def venue(identifiers):
            return {"jufo_id": 2 if identifiers[0] == "1234-5680" else 1, "title": "Journal", "is_active": True}

        with (patch.object(server, "topic_works", side_effect=articles),
              patch.object(server, "find_venue", side_effect=venue)):
            rows, notices = server.search_keywords(topics)
        self.assertEqual([row["jufo_id"] for row in rows], [1])
        self.assertEqual(rows[0]["matched_keywords"], ["CFD", "ML", "SGS", "TCI"])
        self.assertEqual(rows[0]["keyword_total"], 4)
        self.assertEqual(len(rows[0]["examples"]), 2)
        self.assertEqual(notices, ["SGS article lookup unavailable."])

    def test_keyword_search_reports_total_source_failure(self):
        with patch.object(server, "topic_works", side_effect=OSError("Unavailable")):
            with self.assertRaises(OSError):
                server.search_keywords(server.keyword_topics("CFD, ML"))

    def test_combined_search_checks_abstracts_without_returning_their_text(self):
        payload = {"message": {"items": [
            {"DOI": "10.1/closure", "title": ["A data-driven <i>PaSR</i> closure"],
             "abstract": "<jats:p>Neural networks improve partially stirred reactor models.</jats:p>",
             "container-title": ["Combustion journal"], "ISSN": ["1234-5678"]},
            {"DOI": "10.1/ml", "title": ["Machine learning for finance"],
             "container-title": ["Finance journal"], "ISSN": ["1234-5679"]},
        ]}}
        topics = server.keyword_topics("ml, pasr")
        with patch.object(server, "download", return_value=json.dumps(payload).encode()) as download:
            venues = server.topic_works(" ".join(topics), keywords=topics, minimum=2)
        parameters = parse_qs(urlsplit(download.call_args.args[0]).query)
        self.assertIn("query.bibliographic", parameters)
        self.assertIn("abstract", parameters["select"][0])
        self.assertIn(f"from-pub-date:{datetime.now().year - 9}-01-01", parameters["filter"][0])
        self.assertEqual(len(venues), 1)
        work = venues[0]["works"]["10.1/closure"]
        self.assertEqual(work["title"], "A data-driven PaSR closure")
        self.assertEqual(work["keywords"], ["ML", "pasr"])
        self.assertEqual(work["abstract_keywords"], ["ML"])
        self.assertNotIn("abstract", work)

    def test_keyword_search_queries_the_combination_before_individual_concepts(self):
        topics = server.keyword_topics("ml, reactor")
        with patch.object(server, "topic_works", return_value=[]) as lookup:
            server.search_keywords(topics)
        self.assertEqual([call.args[0] for call in lookup.call_args_list],
                         ["machine learning reactor", "machine learning", "reactor"])
        self.assertEqual(lookup.call_args_list[0].kwargs["minimum"], 2)

    def test_keyword_search_keeps_examples_for_less_frequent_keywords(self):
        works = {str(index): {"doi": str(index), "title": "Paper", "keywords": keywords}
                 for index, keywords in enumerate([["CFD", "ML"], ["CFD", "ML"], ["CFD", "ML"], ["TCI"]])}
        venues = [{"issns": ("1234-5678",), "works": works}]
        with (patch.object(server, "topic_works", return_value=venues),
              patch.object(server, "find_venue", return_value={"jufo_id": 1})):
            rows, _ = server.search_keywords(server.keyword_topics("CFD, ML, TCI"))
        self.assertEqual(len(rows[0]["examples"]), 3)
        self.assertTrue(any("TCI" in work["keywords"] for work in rows[0]["examples"]))

    def test_keyword_search_stops_new_lookups_when_time_budget_expires(self):
        with (patch.object(server.time, "monotonic", side_effect=[0, 1, 26, 26]),
              patch.object(server, "topic_works", return_value=[]) as lookup):
            rows, notices = server.search_keywords(server.keyword_topics("CFD, ML"))
        self.assertEqual(rows, [])
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(notices, ["CFD article lookup unavailable.", "ML article lookup unavailable."])


    def test_invalid_keyword_lists_are_rejected(self):
        handler = server.Handler.__new__(server.Handler)
        for query in (",,,", "a,b,c,d,e,f,g,h,i"):
            handler.path = "/api/search?" + urlencode({"q": query, "mode": "auto"})
            with (patch.object(server, "search_keywords") as keywords,
                  patch.object(handler, "send_json") as response):
                handler.do_GET()
                keywords.assert_not_called()
                self.assertEqual(response.call_args.args[0], 400)


    def test_compact_result_retains_publishing_and_history_information(self):
        row = {"jufo_id": 1, "title": "Journal", "country": {"id": "FI"}, "year_start": 2024,
               "level_history": {"2026": "1"}, "agreement": {"discount": 15, "licence": "CC BY"},
               "external": {"oa_info": {"is_diamondOA": True}, "license": {"channel": "CC BY"},
                            "index_info": ["WOS"], "volume": 100}}
        compact = server.compact_result(row)
        self.assertEqual(compact["agreement"], row["agreement"])
        self.assertEqual(compact["level_history"], row["level_history"])
        self.assertEqual(compact["year_start"], 2024)
        self.assertEqual(compact["external"]["oa_info"], row["external"]["oa_info"])
        self.assertNotIn("country", compact)
        self.assertNotIn("volume", compact["external"])

    def test_success_is_cacheable_and_errors_are_not_cached(self):
        handler = server.Handler.__new__(server.Handler)
        handler.wfile = io.BytesIO()
        with (patch.object(handler, "send_response"), patch.object(handler, "end_headers"),
              patch.object(handler, "send_header") as header):
            handler.send_json(200, {"results": []})
            header.assert_any_call("Cache-Control", "public, max-age=0, s-maxage=300")
            header.reset_mock()
            handler.send_json(502, {"error": "Unavailable"})
            header.assert_any_call("Cache-Control", "no-store")
            header.reset_mock()
            handler.send_json(200, {"results": [], "notices": ["Source temporarily unavailable"]})
            header.assert_any_call("Cache-Control", "no-store")
            header.reset_mock()
            handler.send_json(200, {"results": [{"agreement_status": "unavailable"}], "notices": []})
            header.assert_any_call("Cache-Control", "no-store")

    def test_api_json_preserves_unicode_publisher_names(self):
        handler = server.Handler.__new__(server.Handler)
        with patch.object(handler, "respond") as response:
            handler.send_json(200, {"publisher_name": "Şükrü Dursun · Éditions · Göteborg"})
        body = response.call_args.args[2]
        self.assertEqual(json.loads(body.decode("utf-8"))["publisher_name"], "Şükrü Dursun · Éditions · Göteborg")


    def test_invalid_page_is_rejected_before_upstream_search(self):
        handler = server.Handler.__new__(server.Handler)
        for offset in ("-1", "abc", "100000", "1.5"):
            handler.path = f"/api/search?q=Science&offset={offset}"
            with (patch.object(server, "search_journal") as journals,
                  patch.object(handler, "send_json") as response):
                handler.do_GET()
                journals.assert_not_called()
                self.assertEqual(response.call_args.args[0], 400)


    def test_issn_keeps_priority(self):
        with patch.object(server, "search_jufo", return_value=[]) as lookup:
            self.assertEqual(server.search_journal("“００４５–７９３０”"), [])
        lookup.assert_called_once_with("0045-7930", offset=0)

    def test_agreement_matches_issn_when_jufo_lists_an_imprint(self):
        journal = {"is_active": True, "publisher_name": "Pergamon Press", "issnl": "0045-7930"}
        with (patch.object(server, "datetime") as clock,
              patch.object(server, "agreements", return_value=({"00457930": {(100, "Hybrid", "https://www.sciencedirect.com/science/journal/00457930")}}, "2026-11-05"))):
            clock.now.return_value = datetime(2026, 11, 5)
            server.add_agreements([journal])
        self.assertEqual(journal["agreement"]["discount"], 100)
        self.assertEqual(journal["agreement"]["publisher"], "Elsevier")


if __name__ == "__main__":
    unittest.main()
