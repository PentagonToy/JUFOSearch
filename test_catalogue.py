"""Prepared search must preserve identity, coverage and source meanings offline."""

import unittest
import hashlib
import json
from datetime import datetime
from unittest.mock import patch

import catalogue
import server


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"jufo_id": 1, "title": "Computers and Fluids", "issnl": "0045-7930", "is_active": True, "level": 1},
            {"jufo_id": 2, "title": "Combustion and Flame", "issnl": "0010-2180", "is_active": True, "level": 3},
            {"jufo_id": 3, "title": "Şükrü's New Journal", "is_active": True, "level": None},
            {"jufo_id": 4, "title": "Retired Journal", "is_active": False, "level": 0},
        ]
        self.data = {
            "publishing-models": {"journals": {}},
            "quartiles": {"edition": 2026, "snapshot_date": "2026-10-14", "citation_year": 2025, "cohort": "CWTS Core journals",
                          "publication_years": [2023, 2024], "journals": {}},
            "catalogue": {"checked": "2026-11-20", "journals": self.rows},
            "topics": {"topics": [
                {"id": "T1", "display_name": "Machine learning", "description": "Neural networks and machine learning", "keywords": []},
                {"id": "T2", "display_name": "Partially stirred reactor", "description": "Turbulent combustion reactor modelling", "keywords": []},
                {"id": "T3", "display_name": "Nuclear reactors", "description": "Nuclear reactor physics, machine learning, turbulent combustion", "keywords": []},
            ], "sources": [
                {"issn": ["0045-7930"], "topics": [["T1", 20], ["T2", 80]]},
                {"issn": ["0010-2180"], "topics": [["T3", 100]]},
            ]},
        }
        catalogue.index.cache_clear()
        catalogue.topic_index.cache_clear()
        self.source = patch.object(catalogue, "snapshot", side_effect=lambda name: self.data[name])
        self.source.start()
        self.network = patch.object(server, "download", side_effect=AssertionError("Search must be offline"))
        self.network.start()

    def tearDown(self):
        self.source.stop()
        self.network.stop()
        catalogue.index.cache_clear()
        catalogue.topic_index.cache_clear()

    def test_identifiers_initials_unicode_and_unordered_title_words(self):
        for query in ("Computers and fluids", "Fluids computers JUFO", "００４５–７９３０", "computres fluids"):
            with self.subTest(query=query):
                self.assertEqual(catalogue.search_titles(query)[0][0]["jufo_id"], 1)
        for query in ("C&F", "cnf", "C.N.F.", "C N F"):
            with self.subTest(query=query):
                rows, exact = catalogue.search_titles(query)
                self.assertTrue(exact)
                self.assertEqual({row["jufo_id"] for row in rows}, {1, 2})
        self.assertEqual(catalogue.search_titles("sukru")[0][0]["jufo_id"], 3)

    def test_full_results_include_inactive_and_unclassified_without_truncation(self):
        self.rows.extend({"jufo_id": key, "title": f"Journal {key}", "is_active": True} for key in range(10, 611))
        rows, _ = catalogue.search_titles("journal")
        self.assertEqual(len(rows), 603)
        by_id = {row["jufo_id"]: row for row in rows}
        self.assertIsNone(by_id[3]["level"])
        self.assertEqual(by_id[4]["level"], 0)
        self.assertFalse(by_id[4]["is_active"])

    def test_profile_search_requires_two_concepts_and_never_invents_paper_evidence(self):
        rows = catalogue.search_profiles(server.keyword_topics("ml, pasr"), server.TOPIC_VARIANTS)
        self.assertEqual([row["jufo_id"] for row in rows], [1])
        self.assertEqual(rows[0]["profile_keywords"], ["ML", "pasr"])
        self.assertNotIn("examples", rows[0])
        self.assertNotIn("profile_keywords", self.rows[0])
        self.assertEqual(catalogue.search_profiles({"unknown nonsense": "unknown"}, {}), [])

    def test_broader_hints_need_subject_heading_support(self):
        rows = catalogue.search_profiles(server.keyword_topics("ml, pasr"), server.TOPIC_VARIANTS, server.PROFILE_HINTS)
        self.assertEqual([row["jufo_id"] for row in rows], [1])

    def test_exact_titles_with_commas_keep_priority_over_topic_search(self):
        self.rows.append({"jufo_id": 5, "title": "Energy, sustainability and society"})
        with patch.object(server, "search_profiles", side_effect=AssertionError("Exact title")):
            rows, topic = server.search_prepared("Energy, sustainability and society")
        self.assertFalse(topic)
        self.assertEqual(rows[0]["jufo_id"], 5)

    def test_exact_title_precedes_initials_and_bad_issns_do_not_fuzzy_match(self):
        self.rows.extend([{"jufo_id": 5, "title": "Fuel"},
                          {"jufo_id": 6, "title": "Fluid Universal Energy Letters"}])
        rows, exact = catalogue.search_titles("Fuel")
        self.assertTrue(exact)
        self.assertEqual(rows[0]["jufo_id"], 5)
        self.assertEqual(catalogue.search_titles("0000-0000")[0], [])

    def test_auto_and_fast_routes_have_no_network_dependency(self):
        handler = server.Handler.__new__(server.Handler)
        for mode in ("auto", "fast"):
            handler.path = f"/api/search?q=ml,pasr&mode={mode}"
            with (patch.object(server, "snapshot", side_effect=lambda name: self.data[name]),
                  patch.object(server, "add_agreements"), patch.object(handler, "send_json") as response):
                handler.do_GET()
            self.assertEqual(response.call_args.args[0], 200)
            data = response.call_args.args[1]
            self.assertEqual(data["results"][0]["jufo_id"], 1)
            self.assertIsNone(data["next_offset"])

    def test_legacy_paging_preserves_boundaries(self):
        self.rows.extend({"jufo_id": key, "title": f"Journal {key}"} for key in range(10, 611))
        full = catalogue.search_titles("journal")[0]
        first, offset = server.search_journal_batch("journal", pages=5)
        rest, end = server.search_journal_batch("journal", offset=offset, pages=5)
        self.assertEqual(first + rest, full)
        self.assertIsNone(end)

    def test_large_fast_results_are_complete_across_response_boundaries(self):
        self.rows.extend({"jufo_id": key, "title": f"Journal {key}"} for key in range(10, 1211))
        handler = server.Handler.__new__(server.Handler)
        combined = []
        offset = 0
        while True:
            handler.path = f"/api/search?q=journal&mode=fast&offset={offset}"
            with (patch.object(server, "snapshot", side_effect=lambda name: self.data[name]),
                  patch.object(server, "add_agreements"), patch.object(handler, "send_json") as response):
                handler.do_GET()
            data = response.call_args.args[1]
            self.assertLessEqual(len(data["results"]), 1000)
            combined.extend(data["results"])
            if data["next_offset"] is None:
                break
            offset = data["next_offset"]
        self.assertEqual(len(combined), 1203)
        self.assertEqual(len({row["jufo_id"] for row in combined}), 1203)


class SnapshotTests(unittest.TestCase):
    def test_snapshot_set_matches_its_manifest(self):
        manifest = json.loads((catalogue.DATA / "manifest.json").read_text())
        for name, expected in manifest["files"].items():
            payload = (catalogue.DATA / (name + ".json.gz")).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), expected["sha256"])
            self.assertEqual(len(payload), expected["bytes"])

    def test_shipped_sources_preserve_rich_records_and_search_offline(self):
        with patch.object(server, "download", side_effect=AssertionError("No upstream request")):
            data = catalogue.snapshot("catalogue")
            self.assertGreaterEqual(len(data["journals"]), 38080)
            self.assertEqual(len({row["jufo_id"] for row in data["journals"]}), len(data["journals"]))
            rows, _ = server.search_prepared("0045-7930")
            self.assertEqual(rows[0]["jufo_id"], 53957)
            self.assertIn("2026", rows[0]["level_history"])
            self.assertIn("license", rows[0]["external"])
            with patch.object(server, "datetime") as clock:
                clock.now.return_value = datetime(2026, 11, 20)
                server.add_agreements(rows)
            self.assertEqual(rows[0]["agreement"]["discount"], 100)
            for query in ("ml, pasr", "CFD, ML, SGS, TCI"):
                rows, _ = server.search_prepared(query)
                self.assertIn(88900, [row["jufo_id"] for row in rows[:25]])
                if "CFD" in query:
                    self.assertIn(53957, [row["jufo_id"] for row in rows])
            topics = catalogue.snapshot("topics")["topics"]
            self.assertGreaterEqual(len(topics), 4500)
            self.assertTrue(all(isinstance(word, str) for topic in topics for word in topic["keywords"]))


if __name__ == "__main__":
    unittest.main()
