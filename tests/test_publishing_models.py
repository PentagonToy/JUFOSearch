"""Publishing types must come from evidence, independently of institutional funding."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from catalogue import search_titles, snapshot
from scripts.refresh_publishing_models import identifiers, aip_models, xlsx_text
import server


class PublishingModelTests(unittest.TestCase):
    def test_issn_checksums_and_compact_identifiers(self):
        self.assertEqual(identifiers("Print 1070-6631; online 10897666; invalid 1089-7667"), {"10706631", "10897666"})

    def test_aip_types_do_not_cross_an_unlabelled_journal_row(self):
        text = "Physics of Fluids 1089-7666 https://pubs.aip.org/aip/pof Hybrid\nAIP Advances 2158-3226 URL Gold OA"
        self.assertEqual(aip_models(text), {"10897666":"Hybrid OA", "21583226":"Gold OA"})
        text = "Unlabelled 1089-7666\nAIP Advances 2158-3226 URL Gold OA"
        self.assertNotIn("10897666", aip_models(text))

    def test_unused_spreadsheet_strings_are_not_model_records(self):
        namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "list.xlsx"
            with zipfile.ZipFile(path, "w") as bundle:
                bundle.writestr("xl/sharedStrings.xml", f'<sst xmlns="{namespace}"><si><t>10897666</t></si><si><t>2158-3226</t></si></sst>')
                bundle.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{namespace}"><sheetData><row><c t="s"><v>0</v></c></row></sheetData></worksheet>')
            self.assertEqual(identifiers(xlsx_text(path)), {"10897666"})

    def test_bulk_supplements_include_multiple_publishers_and_no_funding_promise(self):
        data = snapshot("publishing-models")
        self.assertGreater(data["publisher_counts"]["springer-hybrid"], 1000)
        self.assertGreater(data["publisher_counts"]["wiley-hybrid"], 1000)
        self.assertGreater(data["publisher_counts"]["aip-contract"], 30)
        self.assertGreater(len(data["journals"]), 10000)
        for row in data["journals"].values():
            self.assertIn(row["model"], ("Gold OA", "Hybrid OA", "Not fully OA"))
            self.assertNotIn("discount", row)
            self.assertNotIn("licence", row)
        rows = search_titles("Physics of fluids")[0]
        server.add_publishing_models(rows)
        self.assertEqual(rows[0]["publishing_model"]["model"], "Hybrid OA")
        self.assertNotIn("agreement", rows[0])


if __name__ == "__main__":
    unittest.main()
