"""Checks for failure detection, proxy metrics and faithful HAC replay."""
import random
import unittest
from rv4pptl.reproduction import score, check_equal, integrity_checks
from rv4pptl.case_study import hac, _sims
from rv4pptl.baselines import hac_replay


class ReproductionTests(unittest.TestCase):
    def test_missing_labels_are_not_negative(self):
        with self.assertRaisesRegex(ValueError, "Unlabeled"):
            score(["unseen"], {"true": [], "false": []}, {})

    def test_distinctness_counts_events(self):
        self.assertEqual(score(["a", "b", "c"], {"true": ["a", "b"], "false": ["c"]},
                               {"a": "event", "b": "event"}),
                         [3, 2, 1, "0.667", "0.500", "0.571"])

    def test_comparison_fails_on_different_result(self):
        with self.assertRaisesRegex(ValueError, "mismatch"):
            check_equal({"count": 1}, {"count": 2}, "fixture")

    def test_archived_inputs_are_unchanged(self):
        self.assertGreater(integrity_checks(), 10)

    def test_hac_preserves_original_routine(self):
        # Random title similarities, many ties, and multiple stopping ratios.
        for seed in range(8):
            rng = random.Random(seed)
            docs = sorted({"".join(rng.choices("abcde甲乙", k=8)) for _ in range(35)})
            sims = _sims(docs)
            for ratio in (0.07, 0.3, 0.8):
                with self.subTest(seed=seed, ratio=ratio):
                    self.assertEqual(hac_replay(docs, ratio, 15, sims),
                                     hac(docs, ratio, 15, sims))


if __name__ == "__main__":
    unittest.main()
