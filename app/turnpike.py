"""Turnpike (partial digest) reconstruction core.

Given the multiset of all pairwise distances between ``cuts`` restriction
sites on a fragment of total ``length``, rebuild the sorted cut positions.

The search is the classical backtracking reconstruction:

* distances are stored in a *counting multiset* (duplicates are kept and
  consumed one occurrence at a time);
* each branch places the point implied by the largest remaining distance --
  either ``widest`` or ``length - widest`` -- and is fully rolled back on
  failure (no coordinate range is ever enumerated);
* mirror images ``{length - x}`` are de-duplicated by canonicalising every
  solution to the lexicographically smaller of the set and its mirror.

No external constraint solver is used.
"""

from __future__ import annotations

from bisect import insort
from collections import Counter
from collections.abc import Iterable, Sequence

#: Deterministic cap on backtracking nodes so a single request cannot
#: monopolise the worker.  Far above anything a valid ``cuts <= 32``
#: instance needs in practice.
DEFAULT_NODE_BUDGET = 2_000_000


class BudgetExceededError(RuntimeError):
    """Raised when the deterministic search-node budget is exhausted."""

    def __init__(self, budget: int) -> None:
        super().__init__(f"search exceeded node budget of {budget}")
        self.budget = budget


def canonical_form(points: Sequence[int], length: int) -> tuple[int, ...]:
    """Canonical representative of a solution's mirror equivalence class.

    ``points`` must be sorted ascending.  The representative is the
    lexicographically smaller of the point tuple and its mirror
    ``{length - x}`` (itself sorted ascending).
    """
    ordered = tuple(points)
    mirror = tuple(length - x for x in reversed(ordered))
    return min(ordered, mirror)


def pairwise_distances(points: Sequence[int]) -> Counter[int]:
    """Counting multiset of all pairwise distances of sorted ``points``."""
    counts: Counter[int] = Counter()
    for i in range(len(points)):
        base = points[i]
        for j in range(i + 1, len(points)):
            counts[points[j] - base] += 1
    return counts


def reconstruct(
    length: int,
    cuts: int,
    distances: Iterable[int],
    *,
    node_budget: int = DEFAULT_NODE_BUDGET,
) -> list[tuple[int, ...]]:
    """Rebuild every distinct canonical cut-point set.

    ``distances`` must contain exactly ``cuts * (cuts - 1) // 2`` values in
    ``[1, length]`` (validated by the API layer); duplicates are significant.

    Returns the distinct canonical solutions sorted lexicographically.
    An empty list means the instance is impossible.
    """
    remaining: Counter[int] = Counter(distances)

    # The distance ``length`` is realised by the pair (0, length) alone,
    # so it must occur exactly once.
    if remaining.get(length, 0) != 1:
        return []
    remaining[length] -= 1
    if remaining[length] == 0:
        del remaining[length]

    placed = [0, length]
    solutions: set[tuple[int, ...]] = set()
    nodes = 0

    def backtrack() -> None:
        nonlocal nodes
        nodes += 1
        if nodes > node_budget:
            raise BudgetExceededError(node_budget)
        if not remaining:
            # Consumed distances pair up exactly when every point is placed.
            if len(placed) == cuts:
                solutions.add(canonical_form(placed, length))
            return
        widest = max(remaining)
        # The largest remaining distance must run from an unplaced point to
        # one of the two endpoints, so the point sits at ``widest`` or at
        # ``length - widest``.
        candidates = (widest,) if widest * 2 == length else (widest, length - widest)
        for candidate in candidates:
            deltas = [abs(candidate - p) for p in placed]
            needed = Counter(deltas)
            # Prune: every distance to an already placed point must still be
            # available with its multiplicity (a repeated candidate yields a
            # zero delta, which never is).
            if any(remaining.get(d, 0) < c for d, c in needed.items()):
                continue
            for d in deltas:
                remaining[d] -= 1
                if remaining[d] == 0:
                    del remaining[d]
            insort(placed, candidate)
            backtrack()
            # Roll the branch back: restore points and multiplicities.
            placed.remove(candidate)
            for d in deltas:
                remaining[d] = remaining.get(d, 0) + 1

    backtrack()
    return sorted(solutions)
