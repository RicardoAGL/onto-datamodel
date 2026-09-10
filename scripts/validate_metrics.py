"""Validator for MetricDefinition -- same discipline as validate_grounding.py,
one layer up: a metric can only be trusted if every column it references
actually exists in the already-validated ontology. This is what "grounded
afterward" means in practice -- the ontology isn't just documentation, it's
the thing a metric definition gets checked against before anyone treats it
as real.

Two failure classes, same silent-vs-flagged split as before:
- A reference to an entity/column that doesn't exist in the ontology is a
  mechanical failure -- exactly as fabricated as an uncited relationship.
- Whether the formula actually computes what the rationale claims is a
  judgment call -- flagged for human review, never auto-passed.
"""
import json
import os
import sys

from review_signoffs import review_key, text_hash
from schema import Entity, MetricDefinition
from validate_grounding import compute_exit_code


def _metric_review(metric_name: str, text: str) -> dict:
    key = review_key(metric_name, "metric-formula")
    return {"key": key, "text": text, "text_hash": text_hash(text)}


def validate_metric(metric: MetricDefinition, entities: dict[str, Entity]) -> tuple[list[str], list[dict]]:
    failures = []

    for ref in metric.references:
        entity_name, _, col_name = ref.partition(".")
        if entity_name not in entities:
            failures.append(
                f"{metric.name}: references entity '{entity_name}' "
                f"(from '{ref}') which does not exist anywhere in the ontology"
            )
            continue
        if col_name:
            col_names = {c.name for c in entities[entity_name].columns}
            if col_name not in col_names:
                failures.append(
                    f"{metric.name}: references '{ref}' but column "
                    f"'{col_name}' does not exist on entity '{entity_name}' "
                    f"in the ontology -- this reference is fabricated"
                )

    # Formula correctness and caveat-completeness require reading the
    # formula against its stated rationale -- not mechanically checkable.
    review = [_metric_review(
        metric.name,
        f"{metric.name}: verify the formula '{metric.formula}' actually "
        f"computes what the rationale claims, and that caveats are complete "
        f"-- not mechanically checkable",
    )]
    return failures, review


def main():
    from generate_customers_entity import customers
    from generate_metrics import ALL_METRICS
    from generate_orders_entity import orders
    from generate_remaining_entities import ALL_REMAINING
    from review_signoffs import is_signed_off, load_signoffs

    entities = {e.name: e for e in [customers, orders] + ALL_REMAINING}
    signoffs = load_signoffs()

    all_failures = []
    all_unsigned = []
    for metric in ALL_METRICS:
        failures, review = validate_metric(metric, entities)
        all_failures.extend(failures)
        unsigned = [r for r in review if not is_signed_off(r, signoffs)]
        all_unsigned.extend(unsigned)

        print(f"=== {metric.name} ===")
        print(f"  formula: {metric.formula}")
        print(f"  FAILURES: {len(failures)}")
        for f in failures:
            print(f"    ✗ {f}")
        print(f"  NEEDS SIGNOFF: {len(unsigned)}")
        for r in unsigned:
            print(f"    ? [{r['key']}] {r['text']}")
        print()

    # Same severity split as validate_grounding.py (2026-08-25): a
    # fabricated reference is a real break and blocks; a metric awaiting
    # signoff is expected mid-development and doesn't -- reusing
    # compute_exit_code() rather than re-deriving the same decision here,
    # so the two validators can't silently drift apart on this again.
    if all_failures:
        print(f"BLOCKED: {len(all_failures)} fabricated reference(s) -- a metric cited a column that doesn't exist in the ontology.")
        sys.exit(compute_exit_code(all_failures, all_unsigned))
    if all_unsigned:
        msg = (f"{len(all_unsigned)} metric(s) awaiting human signoff on formula "
               f"correctness -- not blocking, but not silently ignorable either.")
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning::{msg}")
        else:
            print(f"WARNING: {msg}")
        sys.exit(compute_exit_code(all_failures, all_unsigned))
    print("Clean: every metric reference traces to a real ontology column, and every formula has a human signoff on file.")
    sys.exit(compute_exit_code(all_failures, all_unsigned))


if __name__ == "__main__":
    main()
