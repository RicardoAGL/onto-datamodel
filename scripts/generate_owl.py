"""Export the validated Pydantic ontology to real OWL (Turtle).

Per the Sec 12.6 standards-first design note: this is the piece that makes
the ontology genuinely reusable outside this exercise -- a `.ttl` file any
RDF tool (Protege, GraphDB, plain rdflib) can open, not tied to jaffle_shop
or this codebase at all. It does NOT replace validate_grounding.py -- that
stays the source of truth for whether a claim is actually TRUE against the
dbt manifest (SHACL/OWL can't check that; see validate_shacl.py's own
docstring). This is a translation of an already-validated ontology into a
standards-based representation, not a re-grounding pass.

Run only after validate_grounding.py passes clean -- exporting an
unvalidated ontology would just be standards-compliant garbage.

Every citation (`source`, `grain_source`) is carried into the export as an
annotation, not dropped -- "every claim has a citation" is this pipeline's
core discipline, and it should survive translation into the standard, not
just live in the Python layer.
"""
from rdflib import Graph, Literal, Namespace, OWL, RDF, RDFS, URIRef, XSD

from schema import Entity

EX = Namespace("https://github.com/RicardoAGL/onto-datamodel/ontology#")

# OWL has no built-in vocabulary for "grain" or "citation source" -- these
# are declared as real owl:AnnotationProperty terms below (not just ad hoc
# literals dropped onto a resource), which is what keeps this a genuine OWL
# ontology rather than RDF wearing OWL syntax.
_ANNOTATION_PROPERTIES = [
    (EX.grain, "grain"),
    (EX.grainSource, "grain source"),
    (EX.role, "column role"),
    (EX.source, "citation source"),
    (EX.cardinality, "relationship cardinality"),
]


def _slug(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def entity_class_uri(entity_name: str) -> URIRef:
    return EX[_slug(entity_name)]


def build_graph(entities: list[Entity]) -> Graph:
    g = Graph()
    g.bind("ex", EX)
    g.bind("owl", OWL)

    for prop, label in _ANNOTATION_PROPERTIES:
        g.add((prop, RDF.type, OWL.AnnotationProperty))
        g.add((prop, RDFS.label, Literal(label)))

    entity_names = {e.name for e in entities}

    for entity in entities:
        cls = entity_class_uri(entity.name)
        g.add((cls, RDF.type, OWL.Class))
        g.add((cls, RDFS.label, Literal(entity.name)))
        g.add((cls, RDFS.comment, Literal(entity.summary)))
        g.add((cls, EX.grain, Literal(entity.grain)))
        g.add((cls, EX.grainSource, Literal(entity.grain_source)))

        for col in entity.columns:
            prop = EX[f"{entity.name}_{col.name}"]
            g.add((prop, RDF.type, OWL.DatatypeProperty))
            g.add((prop, RDFS.label, Literal(col.name)))
            g.add((prop, RDFS.domain, cls))
            g.add((prop, RDFS.range, XSD.string))
            g.add((prop, RDFS.comment, Literal(col.description)))
            g.add((prop, EX.role, Literal(col.role)))
            g.add((prop, EX.source, Literal(col.source)))

        for rel in entity.relationships:
            if rel.to_entity not in entity_names:
                # Exporting a subset of entities is a real possibility (e.g.
                # a single-model export); a relationship pointing outside
                # the exported set would be a dangling range. Skip it here
                # -- validate_grounding.py already proved the FK itself is
                # real against the dbt manifest, this is just export scope.
                continue
            prop = EX[f"{entity.name}_{rel.from_column}_to_{rel.to_entity}"]
            g.add((prop, RDF.type, OWL.ObjectProperty))
            g.add((prop, RDFS.label, Literal(rel.description)))
            g.add((prop, RDFS.domain, cls))
            g.add((prop, RDFS.range, entity_class_uri(rel.to_entity)))
            g.add((prop, RDFS.comment, Literal(rel.description)))
            g.add((prop, EX.cardinality, Literal(rel.cardinality)))
            g.add((prop, EX.source, Literal(rel.source)))
            # Real OWL semantics, not just a text label: many-to-one and
            # one-to-one both mean "at most one target per source" from
            # this property's direction, so a reasoner (not just a human
            # reading the annotation) can act on it. one-to-many is
            # deliberately left non-functional.
            if rel.cardinality in ("many-to-one", "one-to-one"):
                g.add((prop, RDF.type, OWL.FunctionalProperty))
            if rel.cardinality == "one-to-one":
                g.add((prop, RDF.type, OWL.InverseFunctionalProperty))

    return g


def main():
    from generate_customers_entity import customers
    from generate_orders_entity import orders
    from generate_remaining_entities import ALL_REMAINING

    entities = [customers, orders] + ALL_REMAINING
    g = build_graph(entities)
    g.serialize(destination="ontology.ttl", format="turtle")
    print(f"Wrote ontology.ttl -- {len(g)} triples, {len(entities)} classes.")


if __name__ == "__main__":
    main()
