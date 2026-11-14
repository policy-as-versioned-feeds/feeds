import json
import unittest

DATE = r"^\d{4}-\d{2}-\d{2}$"
with open("threat-register/feed.json") as f:
    FEED = json.load(f)


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0


class FeedShape(unittest.TestCase):
    def test_envelope(self):
        self.assertEqual(set(FEED), {"feed", "version", "published_by", "published_at", "currency", "note", "rows"})
        self.assertEqual((FEED["feed"], FEED["published_by"], FEED["currency"]), ("threat-register", "feeds", "GBP"))
        self.assertRegex(FEED["version"], r"^[0-9]+\.[0-9]+\.[0-9]+$")
        self.assertRegex(FEED["published_at"], DATE)
        self.assertTrue(FEED["note"].startswith("A demonstration party, not affiliated with"))

    def test_rows(self):
        ids = [r["id"] for r in FEED["rows"]]
        self.assertTrue(ids)
        self.assertEqual(len(ids), len(set(ids)))
        for r in FEED["rows"]:
            self.assertEqual(set(r), {"id", "party", "events_a_year", "events_basis", "loss_an_event", "loss_basis", "penalty", "needs"})
            self.assertTrue(r["id"] and r["party"])

    def test_three_point_values(self):
        for r in FEED["rows"]:
            for v in (r["events_a_year"], r["loss_an_event"]):
                if v is not None:
                    self.assertTrue(len(v) == 3 and all(map(number, v)) and v == sorted(v), r["id"])

    def test_bases(self):
        for r in FEED["rows"]:
            for b in (r["events_basis"], r["loss_basis"]):
                self.assertEqual(set(b), {"kind", "as_of", "text"}, r["id"])
                self.assertIn(b["kind"], {"editorial", "published", "counted"})
                self.assertRegex(b["as_of"], DATE)
                self.assertTrue(b["text"])

    def test_penalty_and_needs(self):
        for r in FEED["rows"]:
            if r["penalty"] is not None:
                self.assertEqual(set(r["penalty"]), {"regime", "tier"}, r["id"])
                self.assertTrue(r["penalty"]["regime"])
            for n in r["needs"]:
                self.assertEqual(set(n), {"capability", "source"}, r["id"])
                self.assertIn(n["capability"], {"egress", "inbound"})
                self.assertTrue(n["source"])


if __name__ == "__main__":
    unittest.main()
