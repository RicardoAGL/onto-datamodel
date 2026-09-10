"""Generate a Mermaid erDiagram from the grounded ontology.

Ports the Mermaid ID/label sanitization approach already proven in
internal dbt tooling I've built elsewhere, rather than re-deriving Mermaid's
identifier and escaping rules from scratch -- that codebase already
fixed the edge cases (IDs starting with a digit, name collisions, type
strings with parens, labels containing quotes) against real dbt
projects. Ported to Python here because the source, a Pydantic Entity,
lives in this pipeline, not in that tool's own node model.

One improvement over the source it's ported from: that tool's generic
dependency graph only has "depends_on" edges, so every relationship
renders with the same crow's-foot notation. Our Relationship objects
carry real cardinality (many-to-one / one-to-many / one-to-one), so this
renders the actual semantics -- and since a relationship is often
declared on both entities it connects (once as "many-to-one", once as
the mirrored "one-to-many"), this also dedupes by unordered entity pair
before rendering, so each real relationship appears exactly once.
"""
import re


def sanitize_mermaid_id(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9]", "_", name).upper()
    if re.match(r"^[0-9_]", sanitized):
        sanitized = f"E_{sanitized}"
    return sanitized or "UNNAMED"


def sanitize_attribute_name(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if re.match(r"^[0-9_]", sanitized):
        sanitized = f"col_{sanitized}"
    return sanitized


def sanitize_label(label: str) -> str:
    return label.replace('"', "'")


# Crow's-foot notation, keyed by cardinality as declared from the FIRST
# entity's perspective in the pair (entity_a --- entity_b):
#   "many-to-one"  : entity_a is the "many" side -> }o--|| (many, zero-or-more -- exactly one)
#   "one-to-many"  : entity_a is the "one" side  -> ||--o{ (exactly one -- zero-or-more)
#   "one-to-one"   : ||--||
_NOTATION = {
    "many-to-one": "}o--||",
    "one-to-many": "||--o{",
    "one-to-one": "||--||",
}


def _dedupe_relationships(entities: list) -> list[dict]:
    """One rendered edge per unordered entity pair, even if declared on
    both sides. Prefers whichever declaration names the FK-holder
    unambiguously (many-to-one or one-to-one over one-to-many)."""
    seen: dict[frozenset, dict] = {}
    for ent in entities:
        for rel in ent.relationships:
            pair = frozenset({ent.name, rel.to_entity})
            candidate = dict(a=ent.name, b=rel.to_entity, cardinality=rel.cardinality, label=rel.description)
            existing = seen.get(pair)
            if existing is None or (existing["cardinality"] == "one-to-many" and rel.cardinality != "one-to-many"):
                seen[pair] = candidate
    return list(seen.values())


def generate_mermaid_erd(entities: list) -> str:
    lines = ["erDiagram"]
    id_by_name = {ent.name: sanitize_mermaid_id(ent.name) for ent in entities}

    for rel in _dedupe_relationships(entities):
        notation = _NOTATION.get(rel["cardinality"], "--")
        a, b = id_by_name[rel["a"]], id_by_name[rel["b"]]
        label = sanitize_label(rel["label"][:40] + ("…" if len(rel["label"]) > 40 else ""))
        lines.append(f'    {a} {notation} {b} : "{label}"')

    for ent in entities:
        eid = id_by_name[ent.name]
        if not ent.columns:
            lines.append(f"    {eid}")
            continue
        lines.append(f"    {eid} {{")
        for col in ent.columns:
            role_marker = {"primary_key": "PK", "foreign_key": "FK"}.get(col.role, "")
            attr_name = sanitize_attribute_name(col.name)
            lines.append(f"        string {attr_name} {role_marker}".rstrip())
        lines.append("    }")

    return "\n".join(lines)


if __name__ == "__main__":
    from generate_customers_entity import customers
    from generate_orders_entity import orders
    from generate_remaining_entities import ALL_REMAINING

    print(generate_mermaid_erd([customers, orders] + ALL_REMAINING))
