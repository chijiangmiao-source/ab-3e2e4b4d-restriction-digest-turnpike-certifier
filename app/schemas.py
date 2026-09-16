"""Request/response schemas for the reconstruction API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

MAX_LENGTH = 1_000_000_000
MAX_CUTS = 32


class ReconstructRequest(BaseModel):
    """Capillary-electrophoresis distance multiset for one fragment.

    ``distances`` must hold exactly ``cuts * (cuts - 1) // 2`` integers,
    each in ``[1, length]``; repeated values are significant and kept.
    """

    model_config = ConfigDict(extra="forbid")

    length: StrictInt = Field(
        ge=2,
        le=MAX_LENGTH,
        description="Total fragment length L.",
        examples=[11],
    )
    cuts: StrictInt = Field(
        ge=2,
        le=MAX_CUTS,
        description="Number of cut points n, including the endpoints 0 and L.",
        examples=[5],
    )
    distances: list[StrictInt] = Field(
        description="Multiset of all n(n-1)/2 pairwise distances; order is irrelevant, duplicates must be preserved.",
        examples=[[1, 2, 3, 4, 5, 6, 7, 8, 9, 11]],
    )


class ReconstructResponse(BaseModel):
    """Reconstruction outcome.

    ``solutions`` holds canonical representatives (lexicographically smaller
    of each mirror pair): the single one for ``unique``, the two
    lexicographically smallest distinct ones for ``ambiguous``, and none for
    ``impossible``.
    """

    status: Literal["unique", "ambiguous", "impossible"]
    solutions: list[list[int]]
    equivalence_classes: int = Field(
        description="Total number of distinct mirror-equivalence classes found."
    )


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any]


class ErrorResponse(BaseModel):
    error: ErrorBody
