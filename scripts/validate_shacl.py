"""SHACL structural validation of the exported OWL ontology.

Complements validate_grounding.py, does not replace it: SHACL checks that
the RDF graph is well-formed per shapes.ttl (every class has a grain
annotation, every property has a source citation, cardinality values are
one of the three allowed) -- it CANNOT check that a claim's *text* actually
matches the dbt manifest. That's still validate_grounding.py's job, and
it stays the source of truth for correctness. SHACL adds a standards-based
structural layer on top, most useful once the ontology leaves Python (e.g.
hand-edited directly in Protege), where Pydantic's own validation at
construction time no longer applies.
"""
import sys
from pathlib import Path

from pyshacl import validate as shacl_validate
from rdflib import Graph

SHAPES_PATH = "shapes.ttl"


def validate_owl(ontology_path: str = "ontology.ttl", shapes_path: str = SHAPES_PATH):
    data_graph = Graph().parse(ontology_path, format="turtle")
    shapes_graph = Graph().parse(shapes_path, format="turtle")
    conforms, _results_graph, results_text = shacl_validate(
        data_graph,
        shacl_graph=shapes_graph,
        inference="none",
    )
    return conforms, results_text


def main():
    if not Path("ontology.ttl").exists():
        print("ontology.ttl not found -- run generate_owl.py first", file=sys.stderr)
        sys.exit(1)

    conforms, results_text = validate_owl()
    print(results_text)
    if not conforms:
        print(
            "BLOCKED: SHACL shape violations found -- the OWL export "
            "doesn't satisfy shapes.ttl.",
            file=sys.stderr,
        )
        sys.exit(1)
    print("Clean: OWL export conforms to shapes.ttl.")


if __name__ == "__main__":
    main()
