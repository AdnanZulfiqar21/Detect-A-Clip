"""Checks that the evaluation primitives reproduce the roadmap's stated F05 arithmetic.

If any of these fail, either the interval code or the roadmap arithmetic is wrong, and
the discrepancy must be reported rather than the test adjusted.
"""
import math

from dac_l0.eval.protocol import Z95, wilson_interval
from dac_l0.index.builder import TOTAL_INSTALLED_INDEX_BUDGET_BYTES
from dac_l0.sampler import MAX_APP_OWNED_FRAMES, RGBA_BYTES_PER_FRAME


def test_z_value_matches_roadmap():
    assert Z95 == 1.959963984540054


def test_precision_500_allows_at_most_15_errors():
    # "Lower preregistered 95 % bound ≥95 %… with n = 500 this allows ≤15 errors."
    assert wilson_interval(485, 500)[0] >= 0.95
    assert wilson_interval(484, 500)[0] < 0.95


def test_clean_recall_needs_873_of_1000():
    assert wilson_interval(873, 1000)[0] >= 0.85
    assert wilson_interval(872, 1000)[0] < 0.85


def test_edited_recall_needs_729_of_1000():
    assert wilson_interval(729, 1000)[0] >= 0.70
    assert wilson_interval(728, 1000)[0] < 0.70


def test_unknown_false_verified_allows_at_most_11_of_1000():
    assert wilson_interval(11, 1000)[1] <= 0.02
    assert wilson_interval(12, 1000)[1] > 0.02


def test_ux_7_of_8_interval_matches_roadmap_approximation():
    lo, hi = wilson_interval(7, 8)
    assert round(lo, 2) == 0.53 and round(hi, 2) == 0.98


def test_index_capacity_table_rows():
    b = TOTAL_INSTALLED_INDEX_BUDGET_BYTES
    assert b == 250_000_000
    rows = {528: (473_484, 263.05), 144: (1_736_111, 964.5), 48: (5_208_333, 2893.5)}
    for bpv, (vecs, hours2) in rows.items():
        v = b // bpv
        assert v == vecs
        assert abs(v * 2 / 3600 - hours2) < 0.1
    # 528 B row: ≈132 two-hour films, ≈351 45-minute episodes, 658 h at 5 s
    v = b // 528
    h2 = v * 2 / 3600
    assert round(h2 / 2) == 132
    assert round(h2 * 60 / 45) == 351
    assert round(v * 5 / 3600) == 658


def test_1000_films_payload_estimate():
    vectors = 1000 * 120 * 60 // 2
    assert vectors == 3_600_000
    assert vectors * 528 == 1_900_800_000  # 1.9008 GB
    assert round(vectors * 528 / 2**30, 2) == 1.77


def test_app_owned_frame_buffer_bound():
    assert RGBA_BYTES_PER_FRAME * MAX_APP_OWNED_FRAMES == 2_764_800


def test_energy_threshold_example():
    assert abs(0.002 * 19.25 * 3600 - 138.6) < 1e-9
