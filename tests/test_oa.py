"""OA checks preserve official context, qualifications and unknown outcomes."""

import unittest
from unittest.mock import patch

import oa_policy as oa
import server


class OACheckTests(unittest.TestCase):
    def setUp(self):
        for function in (oa.check, oa.calculate, oa.institutions, oa.institution_country, oa.language):
            function.cache_clear()
        self.result = {
            "compliant": True,
            "request": {"journal": [{"issn": ["2666-352X"], "title": "A journal", "publisher": "A publisher"}],
                        "funder": [{"id": "academyoffinlandaka", "title": "Research Council of Finland"}],
                        "institution": [{"id": "020hwjq30", "title": "Aalto University"}]},
            "results": [{"route": "ta", "log": [{"parameters": {"end_date": ["2026-12-31"]}}]}],
            "cards": [{"id": "ta_aq", "compliant": True}],
        }
        self.pack = {"cards": {"ta_aq": {"title": "Transformative <br>agreement", "body": {
            "default": "<p>Corresponding author at {institution} only.</p><p>Expires {end_date}.</p>"}}}}

    def test_supported_scope_is_enforced_before_calculation(self):
        with patch.object(oa, "fetch") as fetch:
            for values in [("not-issn", "academyoffinlandaka", "020hwjq30"),
                           ("2666-352X", "unsupported-funder", "020hwjq30"),
                           ("2666-352X", "academyoffinlandaka", "../secret")]:
                with self.assertRaises(ValueError):
                    oa.calculate(*values, 0)
            fetch.assert_not_called()
    def test_institution_suggestions_include_all_countries_and_sort_by_country(self):
        with patch.object(oa, "fetch", return_value={"data": [
            oa.DEFAULT_INSTITUTION,
            {"id": "052gg0110", "title": "Oxford", "country": "United Kingdom"},
            {"id": "invalid", "title": "Damaged record", "country": "Finland"},
        ]}):
            self.assertEqual([row["country"] for row in oa.institutions("university", 1)], ["Finland", "United Kingdom"])

    def test_conditions_and_context_survive_without_html_or_funding_claims(self):
        with (patch.object(oa, "institution_country", return_value={"FI"}),
              patch.object(oa, "fetch", return_value=self.result) as fetch,
              patch.object(oa, "language", return_value=self.pack)):
            result = oa.calculate("2666-352X", "academyoffinlandaka", "020hwjq30", 0)
            self.assertEqual(result["cards"], [{"id": "ta_aq", "title": "Transformative agreement", "available": True,
                "summary": "Corresponding author must qualify. Agreement ends 2026-12-31. Check author eligibility and conditions below.",
                "conditions": "Corresponding author at Aalto University only. Expires 2026-12-31."}])
            self.assertNotIn("apc", result)
            self.assertIn("funder=academyoffinlandaka", result["source"])
            oa.calculate("2666-352X", "academyoffinlandaka", "020hwjq30", 0)
            self.assertEqual(fetch.call_count, 1)

    def test_mismatched_or_unknown_response_is_not_a_negative_verdict(self):
        with (patch.object(oa, "institution_country", return_value={"FI"}),
              patch.object(oa, "fetch", return_value=self.result)):
            for field, value in (("compliant", None), ("compliant", 1), ("request", {})):
                original = self.result[field]
                self.result[field] = value
                with self.assertRaises(RuntimeError):
                    oa.calculate("2666-352X", "academyoffinlandaka", "020hwjq30", 0)
                self.result[field] = original

    def test_markup_is_text_only_and_unresolved_conditions_link_to_jct(self):
        self.assertEqual(oa.plain_text('<p>CC BY</p><script>bad()</script><svg>icon</svg><p>No embargo</p>'), "CC BY No embargo")
        self.pack["cards"]["ta_aq"]["body"]["default"] = "Unknown condition {new_field}"
        with (patch.object(oa, "institution_country", return_value={"FI"}),
              patch.object(oa, "fetch", return_value=self.result),
              patch.object(oa, "language", return_value=self.pack)):
            result = oa.calculate("2666-352X", "academyoffinlandaka", "020hwjq30", 0)
            self.assertEqual(result["cards"][0]["conditions"], "See the full conditions in JCT.")

    def test_upstream_failure_remains_an_error_with_retry(self):
        handler = server.Handler.__new__(server.Handler)
        handler.path = "/api/oa?issn=2666-352X&funder=academyoffinlandaka&ror=020hwjq30"
        with patch.object(oa, "calculate", side_effect=OSError), patch.object(handler, "send_json") as send:
            handler.do_GET()
            self.assertEqual(send.call_args.args[0], 502)
            self.assertNotIn("compliant", send.call_args.args[1])

    def test_different_journal_is_not_accepted_even_with_a_policy_verdict(self):
        self.result["request"]["journal"][0]["issn"] = ["2798-172X"]
        with (patch.object(oa, "institution_country", return_value={"FI"}),
              patch.object(oa, "fetch", return_value=self.result)):
            for compliant in (True, False):
                self.result["compliant"] = compliant
                with self.assertRaises(oa.JournalMismatch):
                    oa.calculate("1532-172X", "academyoffinlandaka", "020hwjq30", 0)

    def test_matching_negative_result_is_a_verdict_not_an_error(self):
        self.result["compliant"] = False
        self.result["cards"] = [{"id": "journal_non_compliant", "compliant": False}]
        with (patch.object(oa, "institution_country", return_value={"FI"}),
              patch.object(oa, "fetch", return_value=self.result),
              patch.object(oa, "language", return_value={})):
            result = oa.calculate("2666-352X", "academyoffinlandaka", "020hwjq30", 0)
            self.assertFalse(result["compliant"])
            self.assertFalse(result["cards"][0]["available"])

    def test_journal_mismatch_has_a_distinct_api_response(self):
        handler = server.Handler.__new__(server.Handler)
        handler.path = "/api/oa?issn=1532-172X&funder=academyoffinlandaka&ror=020hwjq30"
        with patch.object(oa, "calculate", side_effect=oa.JournalMismatch("Different journal")), patch.object(handler, "send_json") as send:
            handler.do_GET()
            self.assertEqual(send.call_args.args[0], 409)
            self.assertEqual(send.call_args.args[1]["code"], "journal_mismatch")
            self.assertNotIn("compliant", send.call_args.args[1])

    def test_summary_preserves_the_funders_actual_license_instruction(self):
        self.result["results"] = []
        self.pack["cards"]["ta_aq"]["body"]["default"] = '<p>Go ahead and submit. Select a <a href="#">CC BY</a> licence.</p><p>Extra conditions.</p>'
        with (patch.object(oa, "institution_country", return_value={"FI"}),
              patch.object(oa, "fetch", return_value=self.result),
              patch.object(oa, "language", return_value=self.pack)):
            result = oa.calculate("2666-352X", "academyoffinlandaka", "020hwjq30", 0)
            self.assertEqual(result["cards"][0]["summary"], "Go ahead and submit. Select a CC BY licence.")

    def test_worldwide_funder_inventory_has_unique_official_ids(self):
        self.assertEqual(len(oa.FUNDERS), len({row["id"] for row in oa.FUNDERS}))
        self.assertTrue({"wellcome", "nationalhealthandmedicalresearchcouncil", "academyoffinlandaka"}
                        <= {row["id"] for row in oa.FUNDERS})
        self.assertTrue(all(row["country"] for row in oa.FUNDERS))

    def test_non_nordic_institution_is_allowed_without_relaxing_identity_checks(self):
        self.result["request"]["institution"][0] = {"id":"052gg0110", "title":"University of Oxford"}
        with (patch.object(oa, "institution_country", return_value={"GB"}),
              patch.object(oa, "fetch", return_value=self.result), patch.object(oa, "language", return_value=self.pack)):
            result = oa.calculate("2666-352X", "academyoffinlandaka", "052gg0110", 0)
            self.assertTrue(result["compliant"])
            self.assertEqual(result["institution"], "University of Oxford")

    def test_inactive_ror_identity_is_still_rejected(self):
        with patch.object(oa, "fetch", return_value={"id":"https://ror.org/052gg0110", "status":"inactive"}):
            with self.assertRaises(ValueError):
                oa.institution_country("052gg0110", 0)

    def test_success_without_an_available_route_is_not_confirmed(self):
        self.result["cards"] = []
        with (patch.object(oa, "institution_country", return_value={"FI"}),
              patch.object(oa, "fetch", return_value=self.result),
              patch.object(oa, "language", return_value=self.pack)):
            with self.assertRaises(RuntimeError):
                oa.calculate("2666-352X", "academyoffinlandaka", "020hwjq30", 0)

    def test_registered_alternate_is_tried_after_canonical_identity_mismatch(self):
        handler = server.Handler.__new__(server.Handler)
        handler.path = "/api/oa?issn=1873-2704&journal=65455&funder=academyoffinlandaka&ror=020hwjq30"
        row = {"issn_electronic": "1873-2704", "issn_print": "1540-7489", "issnl": "1540-7489"}
        with (patch.object(server, "hydrate", return_value=[row]),
              patch.object(oa, "calculate", side_effect=[oa.JournalMismatch(), {"compliant": True}]) as calculate,
              patch.object(handler, "send_json") as send):
            handler.do_GET()
            self.assertEqual([call.args[0] for call in calculate.call_args_list], ["1540-7489", "1873-2704"])
            self.assertEqual(send.call_args.args, (200, {"compliant": True}))

    def test_real_negative_verdict_does_not_trigger_identifier_fallback(self):
        handler = server.Handler.__new__(server.Handler)
        handler.path = "/api/oa?issn=1873-2704&journal=65455&funder=academyoffinlandaka&ror=020hwjq30"
        row = {"issn_electronic": "1873-2704", "issn_print": "1540-7489"}
        with (patch.object(server, "hydrate", return_value=[row]),
              patch.object(oa, "calculate", return_value={"compliant": False}) as calculate,
              patch.object(handler, "send_json") as send):
            handler.do_GET()
            calculate.assert_called_once()
            self.assertEqual(send.call_args.args, (200, {"compliant": False}))

    def test_unrelated_identifier_cannot_be_substituted_for_a_reference(self):
        handler = server.Handler.__new__(server.Handler)
        handler.path = "/api/oa?issn=2666-352X&journal=65455&funder=academyoffinlandaka&ror=020hwjq30"
        with (patch.object(server, "hydrate", return_value=[{"issn_print": "1540-7489"}]),
              patch.object(oa, "calculate") as calculate, patch.object(handler, "send_json") as send):
            handler.do_GET()
            calculate.assert_not_called()
            self.assertEqual(send.call_args.args[0], 400)

    def test_all_registered_identifiers_must_not_resolve_to_other_journals(self):
        handler = server.Handler.__new__(server.Handler)
        handler.path = "/api/oa?issn=1873-2704&journal=65455&funder=academyoffinlandaka&ror=020hwjq30"
        with (patch.object(server, "hydrate", return_value=[{"issn_electronic":"1873-2704","issn_print":"1540-7489"}]),
              patch.object(oa, "calculate", side_effect=oa.JournalMismatch()) as calculate,
              patch.object(handler, "send_json") as send):
            handler.do_GET()
            self.assertEqual(calculate.call_count, 2)
            self.assertEqual(send.call_args.args[0], 409)

    def test_canonical_issn_avoids_online_mismatch_and_repeated_checks_are_cached(self):
        handler = server.Handler.__new__(server.Handler)
        handler.path = "/api/oa?issn=1873-2704&journal=65455&funder=academyoffinlandaka&ror=020hwjq30"
        row = {"issn_electronic":"1873-2704", "issn_print":"1540-7489", "issnl":"1540-7489"}
        with (patch.object(server, "hydrate", return_value=[row]),
              patch.object(oa, "calculate", return_value={"compliant":True}) as calculate,
              patch.object(handler, "send_json")):
            handler.do_GET()
            handler.do_GET()
            calculate.assert_called_once()
            self.assertEqual(calculate.call_args.args[0], "1540-7489")


if __name__ == "__main__":
    unittest.main()
