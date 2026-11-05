"""Regression tests for journal search without upstream requests."""

import json
import unittest
from datetime import datetime
from unittest.mock import patch

import server


class JournalSearchTests(unittest.TestCase):
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
