"""API-level tests over the FastAPI application."""

from collections import Counter

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

UNIQUE_BODY = {"length": 11, "cuts": 5, "distances": [11, 2, 5, 7, 8, 1, 4, 3, 6, 9]}
AMBIGUOUS_BODY = {
    "length": 17,
    "cuts": 6,
    "distances": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 17],
}


def pairwise(points):
    counts = Counter()
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            counts[points[j] - points[i]] += 1
    return counts


class TestHappyPaths:
    def test_unique(self):
        response = client.post("/v1/reconstruct", json=UNIQUE_BODY)
        assert response.status_code == 200
        body = response.json()
        assert body == {
            "status": "unique",
            "solutions": [[0, 2, 7, 8, 11]],
            "equivalence_classes": 1,
        }

    def test_ambiguous_returns_two_smallest_canonical_witnesses(self):
        response = client.post("/v1/reconstruct", json=AMBIGUOUS_BODY)
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ambiguous"
        assert body["solutions"] == [[0, 1, 4, 10, 12, 17], [0, 1, 8, 11, 13, 17]]
        assert body["equivalence_classes"] == 2

    def test_impossible_reports_no_partial_result(self):
        response = client.post(
            "/v1/reconstruct", json={"length": 10, "cuts": 3, "distances": [1, 2, 10]}
        )
        assert response.status_code == 200
        assert response.json() == {
            "status": "impossible",
            "solutions": [],
            "equivalence_classes": 0,
        }

    def test_witnesses_regenerate_the_input_multiset(self):
        for body in (UNIQUE_BODY, AMBIGUOUS_BODY):
            response = client.post("/v1/reconstruct", json=body)
            assert response.status_code == 200
            for witness in response.json()["solutions"]:
                assert witness[0] == 0
                assert witness[-1] == body["length"]
                assert len(witness) == body["cuts"]
                assert witness == sorted(witness)
                assert pairwise(witness) == Counter(body["distances"])

    def test_solutions_are_canonical(self):
        response = client.post("/v1/reconstruct", json=AMBIGUOUS_BODY)
        for witness in response.json()["solutions"]:
            mirror = sorted(AMBIGUOUS_BODY["length"] - x for x in witness)
            assert witness <= mirror

    def test_distance_order_does_not_change_the_response(self):
        shuffled = dict(UNIQUE_BODY, distances=list(reversed(UNIQUE_BODY["distances"])))
        assert client.post("/v1/reconstruct", json=shuffled).content == client.post(
            "/v1/reconstruct", json=UNIQUE_BODY
        ).content

    def test_repeated_requests_are_byte_identical(self):
        first = client.post("/v1/reconstruct", json=AMBIGUOUS_BODY).content
        for _ in range(3):
            assert client.post("/v1/reconstruct", json=AMBIGUOUS_BODY).content == first


class TestStructuredErrors:
    def test_too_few_distances_points_at_first_missing_slot(self):
        response = client.post(
            "/v1/reconstruct", json={"length": 10, "cuts": 3, "distances": [1, 10]}
        )
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "distance_count_mismatch"
        assert error["details"] == {
            "expected": 3,
            "actual": 2,
            "first_offending_index": 2,
        }

    def test_too_many_distances_points_at_first_extra_element(self):
        response = client.post(
            "/v1/reconstruct",
            json={"length": 10, "cuts": 3, "distances": [1, 2, 10, 4, 5]},
        )
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "distance_count_mismatch"
        assert error["details"] == {
            "expected": 3,
            "actual": 5,
            "first_offending_index": 3,
        }

    def test_out_of_range_reports_first_offending_item(self):
        response = client.post(
            "/v1/reconstruct",
            json={"length": 10, "cuts": 3, "distances": [1, 0, 11]},
        )
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "distance_out_of_range"
        assert error["details"] == {"index": 1, "value": 0, "min": 1, "max": 10}

    def test_out_of_range_above_length(self):
        response = client.post(
            "/v1/reconstruct",
            json={"length": 10, "cuts": 3, "distances": [11, 2, 10]},
        )
        assert response.status_code == 422
        assert response.json()["error"]["details"]["index"] == 0

    def test_count_is_checked_before_values(self):
        # The out-of-range 99 sits beyond the expected count, so the count
        # mismatch (not the value) must be reported.
        response = client.post(
            "/v1/reconstruct",
            json={"length": 10, "cuts": 3, "distances": [1, 2, 3, 99]},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "distance_count_mismatch"

    @pytest.mark.parametrize(
        "override",
        [
            {"length": 1},
            {"length": 10**9 + 1},
            {"length": 11.5},
            {"length": True},
            {"cuts": 1},
            {"cuts": 33},
            {"cuts": "5"},
        ],
    )
    def test_schema_violations(self, override):
        body = dict(UNIQUE_BODY, **override)
        response = client.post("/v1/reconstruct", json=body)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_non_integer_distance_is_a_schema_violation(self):
        body = dict(UNIQUE_BODY, distances=[11, 2, 5, 7, 8, 1, 4, 3, 6, "9"])
        response = client.post("/v1/reconstruct", json=body)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_unknown_fields_are_rejected(self):
        body = dict(UNIQUE_BODY, enzyme="EcoRI")
        response = client.post("/v1/reconstruct", json=body)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_error_responses_are_byte_identical(self):
        body = {"length": 10, "cuts": 3, "distances": [1, 0, 11]}
        first = client.post("/v1/reconstruct", json=body).content
        assert client.post("/v1/reconstruct", json=body).content == first


class TestHealth:
    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
