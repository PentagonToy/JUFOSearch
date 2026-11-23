"""Related venues must remain comparable and preserve source evidence."""

import unittest
import gzip
import json
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import patch

import catalogue
import recommendations
import server
from scripts.refresh_fees import prices
from scripts.prepare_search import build_peer_tables


class RecommendationTests(unittest.TestCase):
    def test_cached_recommendations_do_not_share_mutable_response_rows(self):
        rows, _ = recommendations.recommend(88900)
        expected = rows[0]["recommendation_reason"]
        rows[0]["recommendation_reason"] = "response mutation"
        again, _ = recommendations.recommend(88900)
        self.assertEqual(again[0]["recommendation_reason"], expected)

    def peer_database(self, rows, data):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        with sqlite3.connect(folder / "journals.sqlite3") as connection:
            connection.execute("CREATE TABLE journals (id INTEGER PRIMARY KEY)")
            connection.executemany("INSERT INTO journals VALUES (?)", ((key,) for key in rows))
            build_peer_tables(connection, list(rows.values()), data.get("vocabulary", {}),
                              data.get("peers", {}), data.get("metrics", {}))
        return folder

    def test_stale_search_index_is_rejected_instead_of_silently_using_old_metadata(self):
        catalogue.snapshot.cache_clear()
        try:
            with tempfile.TemporaryDirectory() as folder, patch.object(catalogue, "DATA", Path(folder)):
                path = Path(folder)
                (path / "search.json.gz").write_bytes(gzip.compress(json.dumps({"version":1,"sources":{"catalogue":"old","topics":"ok"}}).encode()))
                (path / "manifest.json").write_text(json.dumps({"files":{"catalogue":{"sha256":"new"},"topics":{"sha256":"ok"}}}))
                with self.assertRaises(ValueError):
                    catalogue.snapshot("search")
        finally:
            catalogue.snapshot.cache_clear()

    def test_combustion_query_retains_its_domain_when_pdf_also_matches_other_fields(self):
        rows, _ = server.search_prepared("ml, pasr, pdf")
        self.assertTrue(rows)
        self.assertTrue(all("pasr" in row["profile_keywords"] for row in rows))
        self.assertIn(91703, {row["jufo_id"] for row in rows})
    def test_fee_prices_validate_currency_amount_and_conflicts(self):
        self.assertEqual(prices({"apc_prices":[{"price":0,"currency":"EUR"},{"price":False,"currency":"USD"},
                                               {"price":-1,"currency":"GBP"},{"price":3,"currency":"bad"}]}),
                         [{"currency":"EUR","amount":0}])
        self.assertEqual(prices({"apc_prices":[{"price":1,"currency":"EUR"},{"price":2,"currency":"EUR"}]}), [])
        self.assertEqual(prices({"apc_paid":{"value":20}}), [])

    def test_list_prices_and_aalto_support_remain_separate(self):
        row = catalogue.hydrate(catalogue.search_titles("AECS")[0])[0]
        server.add_publishing_models([row])
        self.assertIn({"currency":"EUR","amount":1790}, row["apc"]["prices"])
        self.assertNotIn("agreement", row)
        self.assertEqual(row["apc"]["snapshot_date"], "2026-10-14")
    def test_shipped_aecs_peers_are_bounded_comparable_and_not_promoted_by_prestige(self):
        rows, notice = recommendations.recommend(88900)
        self.assertIsNone(notice)
        ids = [row["jufo_id"] for row in rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertLessEqual(len(ids), 12)
        self.assertTrue({53762, 53763} <= set(ids[:6]))
        self.assertIn(53957, ids)
        self.assertTrue({88900, 60428, 53760, 91703}.isdisjoint(ids))
        metrics = catalogue.snapshot("quartiles")["journals"]
        reference = metrics["88900"]
        for row in rows:
            self.assertEqual(row["level"], 1)
            self.assertTrue(row["is_active"])
            metric = metrics[str(row["jufo_id"])]
            self.assertLessEqual(recommendations.field_distance(reference, metric), 1)
            self.assertLessEqual(max(reference["score"], metric["score"]) / min(reference["score"], metric["score"]), 2.5)
            self.assertTrue(row["recommendation_reason"])

    def test_missing_standing_is_not_a_zero_or_a_peer_promise(self):
        rows = {1: {"jufo_id": 1, "level": None, "is_active": True}}
        with patch.object(catalogue, "DATA", self.peer_database(rows, {})):
            self.assertEqual(recommendations.recommend(1)[0], [])
            with self.assertRaises(KeyError):
                recommendations.recommend(2)

    def test_real_zero_scores_can_match_without_division_or_metric_fabrication(self):
        rows = {key: {"jufo_id": key, "level": 1, "is_active": True} for key in (1, 2, 3)}
        fields = [{"id": "f", "quartile": 4}]
        data = {"metrics": {str(key): {"score": score, "fields": fields} for key, score in ((1, 0), (2, 0), (3, 2))},
                "peers": {key: {"t": 1} for key in rows}, "vocabulary": {"t": ["Shared topic"]}}
        with patch.object(catalogue, "DATA", self.peer_database(rows, data)):
            self.assertEqual([row["jufo_id"] for row in recommendations.recommend(1)[0]], [2])

    def test_peer_lookup_does_not_load_search_or_profile_snapshots(self):
        with patch.object(catalogue, "snapshot", side_effect=AssertionError("No bulk parsing on peer lookup")):
            self.assertEqual(len(recommendations.recommend(88900)[0]), 12)

    def test_runtime_search_uses_compiled_indices_and_loads_only_matching_details(self):
        catalogue.index.cache_clear()
        catalogue.topic_index.cache_clear()
        original = catalogue.snapshot
        def prepared_only(name):
            self.assertNotIn(name, {"catalogue", "topics"})
            return original(name)
        with patch.object(catalogue, "snapshot", side_effect=prepared_only):
            rows, _ = server.search_prepared("0045-7930")
            rows[0]["recommendation_reason"] = "Preserved evidence"
            result = catalogue.hydrate(rows)[0]
            self.assertEqual(result["recommendation_reason"], "Preserved evidence")
            self.assertIn("2026", result["level_history"])
            self.assertIn("license", result["external"])
            self.assertTrue(server.search_prepared("ml, sgs")[0])

    def test_probability_density_function_requires_fluid_or_combustion_context(self):
        self.assertEqual(server.keyword_topics("pdf"), {"pdf": "pdf"})
        topics = server.keyword_topics("ML, PaSR, PDF")
        self.assertEqual(topics["probability density function"], "PDF")

    def test_recommendation_route_rejects_bad_and_unknown_identifiers(self):
        handler = server.Handler.__new__(server.Handler)
        for query, expected in (("-1", 400), ("1 OR 1", 400), ("123456789", 400), ("99999999", 404)):
            handler.path = "/api/recommend?id=" + query
            with patch.object(handler, "send_json") as response:
                handler.do_GET()
            self.assertEqual(response.call_args.args[0], expected)


if __name__ == "__main__":
    unittest.main()
