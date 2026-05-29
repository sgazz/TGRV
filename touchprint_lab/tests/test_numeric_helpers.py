from __future__ import annotations

import unittest
import warnings

import numpy as np

from touchprint_lab.utils.numeric import safe_nanstd, safe_nanvar


class NumericHelpersTests(unittest.TestCase):
    def _assert_no_warnings(self, func, values, default=0.0):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = func(values, default=default)
        self.assertEqual(caught, [])
        return result

    def test_empty_input(self) -> None:
        self.assertEqual(self._assert_no_warnings(safe_nanvar, []), 0.0)
        self.assertEqual(self._assert_no_warnings(safe_nanstd, []), 0.0)

    def test_single_sample_input(self) -> None:
        values = [3.5]
        self.assertEqual(self._assert_no_warnings(safe_nanvar, values), 0.0)
        self.assertEqual(self._assert_no_warnings(safe_nanstd, values), 0.0)

    def test_nan_only_input(self) -> None:
        values = [np.nan, np.nan]
        self.assertEqual(self._assert_no_warnings(safe_nanvar, values), 0.0)
        self.assertEqual(self._assert_no_warnings(safe_nanstd, values), 0.0)

    def test_normal_multi_sample_input(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0]
        self.assertAlmostEqual(self._assert_no_warnings(safe_nanvar, values), 1.25)
        self.assertAlmostEqual(self._assert_no_warnings(safe_nanstd, values), np.sqrt(1.25))


if __name__ == "__main__":
    unittest.main()
