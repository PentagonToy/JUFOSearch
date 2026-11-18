"""Regression tests for journal search without upstream requests."""

import json
import io
import unittest
from datetime import datetime
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import server


class JournalSearchTests(unittest.TestCase):
    def test_parallel_batches_preserve_every_record_at_page_boundaries(self):
        for count in (0, 99, 100, 101, 400, 500, 501):
            with self.subTest(count=count):
                rows = [{"jufo_id": index, "title": f"Journal {index}"} for index in range(count)]

                def lookup(query, size=100, offset=0):
                    return rows[offset:offset + size]

                with (patch.object(server, "search_journal", side_effect=lambda query, offset: lookup(query, offset=offset)),
                      patch.object(server, "search_jufo", side_effect=lookup)):
                    results, offset = server.search_journal_batch("Journal", pages=5)
                    if offset is not None:
                        remaining, end = server.search_journal_batch("Journal", offset=offset, pages=5)
                        results.extend(remaining)
                        self.assertIsNone(end)
                    self.assertEqual(results, rows)

    def test_batch_failure_is_reported_instead_of_losing_a_page(self):
        with (patch.object(server, "search_journal", return_value=[{}] * 100),
              patch.object(server, "search_jufo", side_effect=OSError("Unavailable"))):
            with self.assertRaises(OSError):
                server.search_journal_batch("Science", pages=5)

    def test_topic_detection_preserves_titles_identifiers_and_initials(self):
        cases = [
            ("0045-7930", [], False),
            ("Fuel", [{"title": "Fuel"}], False),
            ("C&F", [{"title": "Computers and fluids", "matched_acronym": "C&F"}], False),
            ("application in engineering combustion", [{"title": "Applications in energy and combustion science"}], False),
            ("turbulent combustion", [{"title": "Combustion and flame"}], True),
            ("ml", [{"title": "Machine learning"}], True),
            ("cfd", [], True),
            ("physcis", [], True),
        ]
        for query, rows, expected in cases:
            with self.subTest(query=query):
                self.assertEqual(server.needs_topic_search(query, rows), expected)

    def test_auto_search_merges_topic_evidence_without_duplicates(self):
        handler = server.Handler.__new__(server.Handler)
        handler.path = "/api/search?q=ml&mode=auto&batch=5"
        title = {"jufo_id": 1, "title": "Machine learning"}
        related = [dict(title, examples=[{"doi": "10.1/example", "title": "Machine learning study"}]),
                   {"jufo_id": 2, "title": "Neural networks"}]
        with (patch.object(server, "search_journal_batch", return_value=([title], None)) as journals,
              patch.object(server, "search_topic", return_value=(related, [])) as topics,
              patch.object(server, "add_agreements"),
              patch.object(handler, "send_json") as response):
            handler.do_GET()
            journals.assert_called_once_with("machine learning", 0, 5)
            topics.assert_called_once_with("machine learning")
            data = response.call_args.args[1]
            self.assertEqual([row["jufo_id"] for row in data["results"]], [1, 2])
            self.assertEqual(data["results"][0]["examples"], related[0]["examples"])
            self.assertEqual(data["topic"], "machine learning")

    def test_auto_search_retains_title_matches_when_crossref_fails(self):
        handler = server.Handler.__new__(server.Handler)
        handler.path = "/api/search?q=turbulent+combustion&mode=auto"
        title = {"jufo_id": 1, "title": "Combustion and flame"}
        with (patch.object(server, "search_journal_batch", return_value=([title], None)),
              patch.object(server, "search_topic", side_effect=OSError("Unavailable")),
              patch.object(server, "add_agreements"),
              patch.object(handler, "send_json") as response):
            handler.do_GET()
            self.assertEqual(response.call_args.args[0], 200)
            data = response.call_args.args[1]
            self.assertEqual(data["results"][0]["jufo_id"], 1)
            self.assertTrue(data["notices"])

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

    def test_title_search_ranks_exact_match_beyond_first_thirty(self):
        rows = [{"jufo_id": index, "title": f"Science journal {index}"} for index in range(40)]
        target = {"jufo_id": 100, "title": "Science", "is_active": True}
        rows.append(target)

        def download(url):
            parameters = parse_qs(urlsplit(url).query)
            size = int(parameters["_size"][0])
            offset = int(parameters.get("_from", ["0"])[0])
            return json.dumps(rows[offset:offset + size]).encode()

        with patch.object(server, "download", side_effect=download):
            self.assertEqual(server.search_journal("Science")[0], target)
            self.assertEqual(server.search_journal("Science", offset=40), [target])

    def test_journal_mode_preserves_topic_shortcut_titles(self):
        handler = server.Handler.__new__(server.Handler)
        for query in ("physics", "ml", "cfd"):
            handler.path = f"/api/search?q={query}"
            with (patch.object(server, "search_journal", return_value=[]) as journals,
                  patch.object(server, "search_topic") as topics,
                  patch.object(server, "add_agreements"),
                  patch.object(handler, "send_json") as response):
                handler.do_GET()
                journals.assert_called_once_with(query, 0)
                topics.assert_not_called()
                self.assertIsNone(response.call_args.args[1]["topic"])

    def test_invalid_page_is_rejected_before_upstream_search(self):
        handler = server.Handler.__new__(server.Handler)
        for offset in ("-1", "abc", "100000", "1.5"):
            handler.path = f"/api/search?q=Science&offset={offset}"
            with (patch.object(server, "search_journal") as journals,
                  patch.object(handler, "send_json") as response):
                handler.do_GET()
                journals.assert_not_called()
                self.assertEqual(response.call_args.args[0], 400)

    def test_explicit_topic_shortcut_and_title_pagination(self):
        handler = server.Handler.__new__(server.Handler)
        handler.path = "/api/search?q=ml&mode=topic"
        with (patch.object(server, "search_topic", return_value=([], [])) as topics,
              patch.object(server, "add_agreements"),
              patch.object(handler, "send_json")):
            handler.do_GET()
            topics.assert_called_once_with("machine learning")

        handler.path = "/api/search?q=Science&offset=100"
        rows = [{"jufo_id": index} for index in range(100)]
        with (patch.object(server, "search_journal", return_value=rows) as journals,
              patch.object(server, "add_agreements"),
              patch.object(handler, "send_json") as response):
            handler.do_GET()
            journals.assert_called_once_with("Science", 100)
            self.assertEqual(response.call_args.args[1]["next_offset"], 200)

    def test_acronym_forms_from_title(self):
        self.assertTrue({"caf", "cf", "c&f", "cnf"} <= server.title_acronyms("Computers and Fluids"))
        self.assertIn("aecs", server.title_acronyms("Applications in Energy and Combustion Science"))

    def test_generated_index_retains_collisions(self):
        index = server.acronym_index()
        for key in ("c&f", "cnf"):
            with self.subTest(key=key):
                self.assertTrue({53760, 53957} <= set(index[key]))
        self.assertIn(88900, index["aecs"])
        self.assertTrue({59847, 60001} <= set(index["jcp"]))

    def test_acronym_candidates_use_live_records_and_stay_distinct(self):
        def records(url):
            jufo_id = int(url.rsplit("/", 1)[-1])
            return json.dumps([{"jufo_id": jufo_id, "is_active": jufo_id != 3}]).encode()

        with (patch.object(server, "acronym_index", return_value={"cnf": [1, 2, 3]}),
              patch.object(server, "download", side_effect=records)):
            for term in ("cnf", "C.N.F.", "C N F"):
                with self.subTest(term=term):
                    self.assertEqual(server.acronym_results(term), [
                        {"jufo_id": 1, "is_active": True, "matched_acronym": "CNF"},
                        {"jufo_id": 2, "is_active": True, "matched_acronym": "CNF"},
                    ])

    def test_issn_keeps_priority(self):
        with patch.object(server, "search_jufo", return_value=[]) as lookup:
            self.assertEqual(server.search_journal("“００４５–７９３０”"), [])
        lookup.assert_called_once_with("0045-7930")

    def test_exact_title_precedes_generated_acronym(self):
        row = {"jufo_id": 1, "title": "Fuel", "is_active": True}
        with (patch.object(server, "search_jufo", return_value=[row]),
              patch.object(server, "acronym_results") as lookup):
            self.assertEqual(server.search_journal("“FUEL”"), [row])
        lookup.assert_not_called()

    def test_agreement_matches_issn_when_jufo_lists_an_imprint(self):
        journal = {"is_active": True, "publisher_name": "Pergamon Press", "issnl": "0045-7930"}
        with (patch.object(server, "datetime") as clock,
              patch.object(server, "agreements", return_value=({"00457930": {(100, "Hybrid", "https://www.sciencedirect.com/science/journal/00457930")}}, "2026-11-05"))):
            clock.now.return_value = datetime(2026, 11, 5)
            server.add_agreements([journal])
        self.assertEqual(journal["agreement"]["discount"], 100)
        self.assertEqual(journal["agreement"]["publisher"], "Elsevier")

    def test_unordered_words_rank_by_overlap_and_deduplicate(self):
        target = {"jufo_id": 1, "title": "Computers and Fluids", "is_active": True}
        other = {"jufo_id": 2, "title": "Experiments in Fluids", "is_active": True}

        def lookup(query, size=30):
            return {"computer": [target], "fluid": [other, target]}.get(query, [])

        with patch.object(server, "search_jufo", side_effect=lookup):
            self.assertEqual(server.search_journal("Fluids computers JUFO"), [target, other])


if __name__ == "__main__":
    unittest.main()
