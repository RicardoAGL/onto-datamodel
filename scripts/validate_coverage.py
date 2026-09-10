"""Coverage-gap check -- "Direction B" drift, distinct from citation
grounding ("Direction A", validate_grounding.py).

Direction A checks: does an existing claim still hold against the facts?
Direction B checks: does the manifest have anything no claim mentions at
all? A validator that only does A cannot see a column that's real in the
project but was never documented -- there's no claim to check, so nothing
fails. This is a plain set-difference against structural_facts.json, zero
LLM cost, and it's the other half of what "check drift from the spec"
actually requires (seen on a real production dbt project: a seven-item
drift case that included undocumented columns as one item -- Direction A
alone would have missed that one).

Informational, not a hard gate: an incomplete ontology isn't wrong the
way a fabricated claim is wrong, and demanding 100% coverage before any
PR merges is a much higher bar than demanding existing claims be true.
"""
import json


def find_coverage_gaps(all_entities: list, facts: dict) -> list[dict]:
    entities_by_name = {e.name: e for e in all_entities}
    gaps = []

    for model_name, model_facts in facts["models"].items():
        if model_name not in entities_by_name:
            gaps.append(dict(model=model_name, column=None,
                note="entire model has no ontology entity at all"))
            continue

        claimed_cols = {c.name for c in entities_by_name[model_name].columns}
        for col_name, col_facts in model_facts["columns"].items():
            if col_name not in claimed_cols:
                gaps.append(dict(model=model_name, column=col_name,
                    note=f"real column (manifest description: {col_facts['description']!r}) "
                         f"not documented in the ontology"))
    return gaps


def main():
    from generate_customers_entity import customers
    from generate_orders_entity import orders
    from generate_remaining_entities import ALL_REMAINING

    with open("structural_facts.json") as f:
        facts = json.load(f)

    all_entities = [customers, orders] + ALL_REMAINING
    gaps = find_coverage_gaps(all_entities, facts)

    print(f"COVERAGE GAPS (informational, not blocking): {len(gaps)}")
    for g in gaps:
        if g["column"] is None:
            print(f"  ○ {g['model']}: {g['note']}")
        else:
            print(f"  ○ {g['model']}.{g['column']}: {g['note']}")
    if not gaps:
        print("  none -- every real column in every modeled entity is documented")


if __name__ == "__main__":
    main()
