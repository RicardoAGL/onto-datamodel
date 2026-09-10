"""Auto-proposed fixes for FAILURES -- not a judgment call, a mechanical
correction. When a description fails because it doesn't match the
manifest, the correct text is already sitting in structural_facts.json --
this isn't a guess, it's the same ground truth the failure was checked
against. Never auto-applies: prints a copy-pasteable correction, the same
"read+copy, don't auto-mutate" principle already used for signoffs
(review_signoffs.py) and for the same reason -- a fix that silently
rewrites source code removes the human from a decision, even a
mechanical-looking one.

Deliberately does NOT attempt to suggest fixes for review-item claims
(grain, cardinality reasoning) -- those require judgment, and a
suggested "fix" for something explicitly flagged as unfalsifiable would
reintroduce exactly the hallucination risk this whole pipeline exists to
prevent. This stays scoped to the one failure class where the correct
answer is mechanically provable: a manifest-description mismatch.
"""
import json

ENTITY_SOURCE_FILE = {
    "customers": "generate_customers_entity.py",
    "orders": "generate_orders_entity.py",
}


def _source_file(entity_name: str) -> str:
    return ENTITY_SOURCE_FILE.get(entity_name, "generate_remaining_entities.py")


def suggest_description_fixes(entity, facts: dict) -> list[dict]:
    """Returns one suggestion per column whose source=manifest description
    doesn't match structural_facts.json exactly. Empty list if the entity
    is clean -- this only ever proposes a fix for a real, mechanically
    provable mismatch, never for anything else."""
    model_facts = facts["models"].get(entity.name)
    if model_facts is None:
        return []

    suggestions = []
    for col in entity.columns:
        if col.source != "manifest":
            continue
        col_facts = model_facts["columns"].get(col.name)
        if col_facts is None or col_facts["description"] is None:
            continue
        actual = col_facts["description"]
        if actual.strip() != col.description.strip():
            suggestions.append(dict(
                entity=entity.name,
                column=col.name,
                current=col.description,
                suggested=actual,
                file=_source_file(entity.name),
            ))
    return suggestions


def main():
    from generate_customers_entity import customers
    from generate_orders_entity import orders
    from generate_remaining_entities import ALL_REMAINING

    with open("structural_facts.json") as f:
        facts = json.load(f)

    all_suggestions = []
    for entity in [customers, orders] + ALL_REMAINING:
        all_suggestions.extend(suggest_description_fixes(entity, facts))

    print(f"SUGGESTED FIXES (mechanically proven, not applied automatically): {len(all_suggestions)}")
    for s in all_suggestions:
        print(f"  → {s['entity']}.{s['column']} in {s['file']}")
        print(f"      current:   {s['current']!r}")
        print(f"      suggested: {s['suggested']!r}")
    if not all_suggestions:
        print("  none -- every manifest-sourced description matches exactly")


if __name__ == "__main__":
    main()
