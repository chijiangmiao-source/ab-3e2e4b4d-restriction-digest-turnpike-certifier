"""Unit tests for the Turnpike reconstruction core."""

from collections import Counter

import pytest

from app.turnpike import (
    BudgetExceededError,
    canonical_form,
    pairwise_distances,
    reconstruct,
)


class TestCanonicalForm:
    def test_picks_lexicographically_smaller_of_set_and_mirror(self):
        # mirror of (0, 1, 4, 6) is (0, 2, 5, 6); the original is smaller
        assert canonical_form((0, 1, 4, 6), 6) == (0, 1, 4, 6)
        # mirror of (0, 2, 5, 6) is (0, 1, 4, 6); the mirror wins
        assert canonical_form((0, 2, 5, 6), 6) == (0, 1, 4, 6)

    def test_symmetric_set_is_its_own_canonical_form(self):
        assert canonical_form((0, 3, 5, 8), 8) == (0, 3, 5, 8)


class TestPairwiseDistances:
    def test_counts_duplicates(self):
        assert pairwise_distances([0, 3, 5, 8]) == Counter({2: 1, 3: 2, 5: 2, 8: 1})


class TestReconstruct:
    def test_unique_golomb_ruler(self):
        distances = [11, 2, 5, 7, 8, 1, 4, 3, 6, 9]  # unsorted on purpose
        assert reconstruct(11, 5, distances) == [(0, 2, 7, 8, 11)]

    def test_ambiguous_homometric_pair(self):
        # The classic 6-point homometric pair sharing one distance multiset.
        distances = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 17]
        assert reconstruct(17, 6, distances) == [
            (0, 1, 4, 10, 12, 17),
            (0, 1, 8, 11, 13, 17),
        ]

    def test_mirror_mates_collapse_to_one_class(self):
        # Distances of {0, 5, 7, 13, 16, 17}: the mirror of a homometric
        # solution must not produce a third equivalence class.
        distances = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 17]
        classes = reconstruct(17, 6, distances)
        assert len(classes) == 2

    def test_duplicate_distances_are_significant(self):
        # {0, 3, 5, 8}: distances 3 and 5 each occur twice; dropping the
        # duplicates would describe a different, impossible instance.
        assert reconstruct(8, 4, [2, 3, 3, 5, 5, 8]) == [(0, 3, 5, 8)]
        assert reconstruct(8, 4, [2, 3, 5, 8, 3, 5]) == [(0, 3, 5, 8)]
        assert reconstruct(8, 3, [2, 3, 8]) == []  # same values, wrong count

    def test_impossible_when_max_distance_is_not_length(self):
        assert reconstruct(10, 3, [3, 4, 5]) == []

    def test_impossible_when_length_distance_repeats(self):
        assert reconstruct(10, 4, [1, 2, 3, 4, 10, 10]) == []

    def test_impossible_unsatisfiable_branch(self):
        assert reconstruct(10, 3, [1, 2, 10]) == []

    def test_two_cut_points(self):
        assert reconstruct(7, 2, [7]) == [(0, 7)]
        assert reconstruct(7, 2, [3]) == []

    def test_large_length_does_not_enumerate_coordinates(self):
        # Would hang for minutes if the search scanned the coordinate range.
        distances = [123456789, 876543211, 10**9]
        assert reconstruct(10**9, 3, distances) == [(0, 123456789, 10**9)]

    def test_canonical_representative_is_the_lexicographically_smaller(self):
        # a = 123456789 < 876543211 = L - a, so the point stays left.
        classes = reconstruct(10**9, 3, [123456789, 876543211, 10**9])
        assert classes == [(0, 123456789, 10**9)]
        # Swapping the roles puts the mirror on the left instead.
        classes = reconstruct(10**9, 3, [876543211, 123456789, 10**9])
        assert classes == [(0, 123456789, 10**9)]

    def test_every_witness_regenerates_the_input_multiset(self):
        distances = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 17]
        for solution in reconstruct(17, 6, distances):
            assert pairwise_distances(solution) == Counter(distances)

    def test_search_is_deterministic_across_runs(self):
        distances = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 17]
        first = reconstruct(17, 6, distances)
        for _ in range(5):
            assert reconstruct(17, 6, distances) == first

    def test_node_budget_is_enforced(self):
        with pytest.raises(BudgetExceededError):
            reconstruct(17, 6, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 17], node_budget=1)
