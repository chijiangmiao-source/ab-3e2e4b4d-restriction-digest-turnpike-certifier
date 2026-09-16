"""One-shot acceptance checks against a running API instance.

Targets ``API_BASE_URL`` (default ``http://127.0.0.1:8000``), exercises the
documented request semantics end to end, and exits 0 only if every check
passes.  Used as the ``verify`` service in docker-compose.yml, but also
runnable directly:  ``API_BASE_URL=http://host:port python verify.py``.
"""

from __future__ import annotations

import os
import sys
import time
from collections import Counter

import httpx

BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

UNIQUE_BODY = {"length": 11, "cuts": 5, "distances": [11, 2, 5, 7, 8, 1, 4, 3, 6, 9]}
AMBIGUOUS_BODY = {
    "length": 17,
    "cuts": 6,
    "distances": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 17],
}
IMPOSSIBLE_BODY = {"length": 10, "cuts": 3, "distances": [1, 2, 10]}

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"[{'PASS' if condition else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def pairwise(points: list[int]) -> Counter[int]:
    counts: Counter[int] = Counter()
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            counts[points[j] - points[i]] += 1
    return counts


def wait_for_api(client: httpx.Client) -> bool:
    for _ in range(60):
        try:
            if client.get("/health").status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(1)
    return False


def main() -> int:
    print(f"acceptance target: {BASE_URL}")
    with httpx.Client(base_url=BASE_URL, timeout=httpx.Timeout(15.0, connect=2.0)) as client:
        check("GET /health responds 200", wait_for_api(client))
        if failures:
            return report()

        # --- unique reconstruction -------------------------------------
        r = client.post("/v1/reconstruct", json=UNIQUE_BODY)
        ok = r.status_code == 200 and r.json() == {
            "status": "unique",
            "solutions": [[0, 2, 7, 8, 11]],
            "equivalence_classes": 1,
        }
        check("unique instance yields its single canonical solution", ok, r.text)

        # --- ambiguous reconstruction ----------------------------------
        r = client.post("/v1/reconstruct", json=AMBIGUOUS_BODY)
        ok = r.status_code == 200 and r.json() == {
            "status": "ambiguous",
            "solutions": [[0, 1, 4, 10, 12, 17], [0, 1, 8, 11, 13, 17]],
            "equivalence_classes": 2,
        }
        check("homometric instance yields the two smallest canonical witnesses", ok, r.text)

        # --- impossible instance ---------------------------------------
        r = client.post("/v1/reconstruct", json=IMPOSSIBLE_BODY)
        ok = r.status_code == 200 and r.json() == {
            "status": "impossible",
            "solutions": [],
            "equivalence_classes": 0,
        }
        check("impossible instance reports no partial result", ok, r.text)

        # --- every witness regenerates the input multiset --------------
        regeneration_ok = True
        for body in (UNIQUE_BODY, AMBIGUOUS_BODY):
            for witness in client.post("/v1/reconstruct", json=body).json()["solutions"]:
                canonical = witness <= sorted(body["length"] - x for x in witness)
                regeneration_ok &= (
                    witness[0] == 0
                    and witness[-1] == body["length"]
                    and len(witness) == body["cuts"]
                    and pairwise(witness) == Counter(body["distances"])
                    and canonical
                )
        check("witnesses are canonical and regenerate the input distances", regeneration_ok)

        # --- determinism ------------------------------------------------
        first = client.post("/v1/reconstruct", json=AMBIGUOUS_BODY).content
        check(
            "repeated requests are byte-identical",
            all(client.post("/v1/reconstruct", json=AMBIGUOUS_BODY).content == first for _ in range(3)),
        )
        shuffled = dict(UNIQUE_BODY, distances=list(reversed(UNIQUE_BODY["distances"])))
        check(
            "distance order does not change the response",
            client.post("/v1/reconstruct", json=shuffled).content
            == client.post("/v1/reconstruct", json=UNIQUE_BODY).content,
        )

        # --- structured errors ------------------------------------------
        r = client.post("/v1/reconstruct", json={"length": 10, "cuts": 3, "distances": [1, 10]})
        err = r.json().get("error", {})
        check(
            "count mismatch is a structured 422 naming the first slot",
            r.status_code == 422
            and err.get("code") == "distance_count_mismatch"
            and err.get("details", {}).get("first_offending_index") == 2
            and err.get("details", {}).get("expected") == 3,
            r.text,
        )

        r = client.post("/v1/reconstruct", json={"length": 10, "cuts": 3, "distances": [1, 0, 11]})
        err = r.json().get("error", {})
        check(
            "out-of-range value is a structured 422 naming the first item",
            r.status_code == 422
            and err.get("code") == "distance_out_of_range"
            and err.get("details", {}).get("index") == 1
            and err.get("details", {}).get("value") == 0,
            r.text,
        )

        r = client.post("/v1/reconstruct", json={"length": 10, "cuts": 33, "distances": []})
        check(
            "schema violation is a structured 422",
            r.status_code == 422 and r.json().get("error", {}).get("code") == "validation_error",
            r.text,
        )

    return report()


def report() -> int:
    if failures:
        print(f"\n{len(failures)} acceptance check(s) FAILED: {', '.join(failures)}")
        return 1
    print("\nall acceptance checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
