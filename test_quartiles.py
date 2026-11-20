"""Test global cohort eligibility and quartile boundaries independently of live APIs."""

import unittest
from unittest.mock import patch

from refresh_quartiles import source_record, rank_sources
from catalogue import snapshot
import server


class QuartileTests(unittest.TestCase):
    def source(self, score=2.5):
        return {"id": "https://openalex.org/S1", "type": "journal", "is_core": True, "issn": ["1234-5678"],
                "summary_stats": {"2yr_mean_citedness": score},
                "counts_by_year": [{"year": 2023, "works_count": 5}, {"year": 2024, "works_count": 5}],
                "topics": [{"count": 80, "subfield": {"id": "A", "display_name": "Combustion"}},
                           {"count": 15, "subfield": {"id": "B", "display_name": "Computational methods"}},
                           {"count": 5, "subfield": {"id": "C", "display_name": "Incidental field"}}]}

    def test_cohort_uses_publication_window_and_dominant_subjects(self):
        row = source_record(self.source(), 2026)
        self.assertEqual(set(row["fields"]), {"A", "B"})
        raw = self.source()
        raw["counts_by_year"] = [{"year": 2025, "works_count": 1000}]
        self.assertIsNone(source_record(raw, 2026))
        raw = self.source()
        raw["type"] = "repository"
        self.assertIsNone(source_record(raw, 2026))
        raw = self.source()
        raw["is_core"] = False
        self.assertIsNone(source_record(raw, 2026))
        raw = self.source()
        raw["id"] = "javascript:alert(1)"
        self.assertIsNone(source_record(raw, 2026))

    def test_zero_is_a_valid_score_but_missing_or_invalid_scores_are_not(self):
        self.assertEqual(source_record(self.source(0), 2026)["score"], 0)
        for score in (None, "", True, -1, float("nan"), float("inf")):
            with self.subTest(score=score):
                self.assertIsNone(source_record(self.source(score), 2026))

    def test_each_quartile_boundary_and_tied_ranks(self):
        rows = [{"id": str(rank), "score": 21 - rank, "fields": {"A": "Field"}} for rank in range(1, 21)]
        result = rank_sources(rows)
        self.assertEqual([result[str(rank)]["fields"][0]["quartile"] for rank in range(1, 21)],
                         [1] * 5 + [2] * 5 + [3] * 5 + [4] * 5)
        rows[5]["score"] = rows[4]["score"]
        result = rank_sources(rows)
        self.assertEqual(result["5"]["fields"], result["6"]["fields"])
        self.assertEqual(result["6"]["fields"][0]["rank"], 5)

    def test_small_or_constant_groups_do_not_get_fabricated_quartiles(self):
        row = {"id": "S1", "score": 2, "fields": {"A": "Field"}}
        self.assertEqual(rank_sources([row]), {})
        self.assertEqual(rank_sources([dict(row, id=str(i)) for i in range(20)]), {})

    def test_api_enrichment_preserves_unknowns_and_the_source_edition(self):
        data = {"edition": 2026, "snapshot_date": "2026-10-14", "citation_year": 2025, "cohort": "CWTS Core journals",
                "publication_years": [2023, 2024], "journals": {"1": {"fields": [{"quartile": 2}]}}}
        rows = [{"jufo_id": 1}, {"jufo_id": 2}]
        with patch.object(server, "snapshot", return_value=data):
            server.add_quartiles(rows)
        self.assertEqual(rows[0]["quartiles"]["edition"], 2026)
        self.assertIsNone(rows[1]["quartiles"])
        self.assertIn("quartiles", server.compact_result(rows[0]))

    def test_shipped_quartiles_reach_the_offline_search_api(self):
        handler = server.Handler.__new__(server.Handler)
        handler.path = "/api/search?q=2666-352X&mode=fast"
        with (patch.object(server, "download", side_effect=AssertionError("No live metric request")),
              patch.object(handler, "send_json") as response):
            handler.do_GET()
        self.assertEqual(response.call_args.args[0], 200)
        metric = response.call_args.args[1]["results"][0]["quartiles"]
        self.assertEqual(metric["source_id"], "https://openalex.org/S4210188498")
        self.assertEqual(metric["cohort"], "CWTS Core journals")
        self.assertEqual(metric["publication_years"], [metric["edition"] - 3, metric["edition"] - 2])
        self.assertTrue(metric["fields"])
        data = snapshot("quartiles")
        self.assertGreater(data["global_cohort"], len(data["journals"]))
        for row in data["journals"].values():
            self.assertTrue(1 <= len(row["fields"]) <= 3)
            for field in row["fields"]:
                self.assertIn(field["quartile"], (1, 2, 3, 4))
                self.assertTrue(1 <= field["rank"] <= field["total"])
                self.assertGreaterEqual(field["total"], 20)


if __name__ == "__main__":
    unittest.main()
