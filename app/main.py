"""FastAPI application exposing the Turnpike reconstruction service."""

from __future__ import annotations

import logging
from collections import Counter

from fastapi import FastAPI

from .errors import ApiError, install_exception_handlers
from .schemas import ErrorResponse, ReconstructRequest, ReconstructResponse
from .turnpike import BudgetExceededError, pairwise_distances, reconstruct

logger = logging.getLogger("turnpike")

app = FastAPI(
    title="Turnpike Reconstruction Service",
    version="1.0.0",
    summary="Rebuild restriction-site maps from capillary-electrophoresis distance multisets.",
)
install_exception_handlers(app)


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/v1/reconstruct",
    response_model=ReconstructResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Validation or consistency failure."},
        503: {"model": ErrorResponse, "description": "Search budget exceeded."},
    },
)
def reconstruct_endpoint(payload: ReconstructRequest) -> ReconstructResponse:
    length = payload.length
    cuts = payload.cuts
    distances = payload.distances

    expected = cuts * (cuts - 1) // 2
    actual = len(distances)
    if actual != expected:
        # 0-based index of the first extra element, or of the first missing one.
        first_offending = min(actual, expected)
        raise ApiError(
            422,
            "distance_count_mismatch",
            f"expected exactly {expected} distances for {cuts} cut points, got {actual}",
            {
                "expected": expected,
                "actual": actual,
                "first_offending_index": first_offending,
            },
        )

    for index, value in enumerate(distances):
        if not 1 <= value <= length:
            raise ApiError(
                422,
                "distance_out_of_range",
                f"distance at index {index} is {value}, outside the allowed range [1, {length}]",
                {"index": index, "value": value, "min": 1, "max": length},
            )

    try:
        classes = reconstruct(length, cuts, distances)
    except BudgetExceededError as exc:
        raise ApiError(
            503,
            "search_budget_exceeded",
            "instance exceeded the deterministic search budget",
            {"node_budget": exc.budget},
        ) from exc

    witnesses = [list(canonical) for canonical in classes[:2]]

    # Every witness must regenerate the exact input multiset; a mismatch
    # would be an internal defect, never something to ship silently.
    input_counts = Counter(distances)
    for witness in witnesses:
        if pairwise_distances(witness) != input_counts:
            logger.error("witness %r failed the regeneration check", witness)
            raise ApiError(
                500,
                "internal_inconsistency",
                "a reconstructed witness failed its regeneration check",
                {},
            )

    if not classes:
        status = "impossible"
    elif len(classes) == 1:
        status = "unique"
    else:
        status = "ambiguous"
    return ReconstructResponse(
        status=status, solutions=witnesses, equivalence_classes=len(classes)
    )
