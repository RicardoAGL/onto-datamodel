"""Tests for the OWL export + SHACL validation layer.

Same negative-control principle as test_grounding.py: a SHACL validator
that only ever passes correct input isn't proven, it could just as easily
be a rubber stamp. These tests deliberately build graphs missing a
required annotation or carrying an invalid value, and assert pyshacl
actually catches each one -- plus one test proving the export encodes
real OWL semantics (a functional property), not just a text label.
"""
from pyshacl import validate as shacl_validate
from rdflib import Graph, Literal, OWL, RDF, RDFS

from generate_owl import EX, build_graph
from schema import Entity, Relationship


def _shapes_graph() -> Graph:
    return Graph().parse("shapes.ttl", format="turtle")


def test_real_ontology_conforms_to_shacl_shapes():
    from generate_customers_entity import customers
    from generate_orders_entity import orders

    g = build_graph([customers, orders])
    conforms, _, results_text = shacl_validate(g, shacl_graph=_shapes_graph(), inference="none")
    assert conforms, results_text


def test_class_missing_grain_is_caught():
    g = Graph()
    cls = EX.Broken
    g.add((cls, RDF.type, OWL.Class))
    g.add((cls, RDFS.comment, Literal("has a summary but no grain")))
    # deliberately no ex:grain, no ex:grainSource
    conforms, _, results_text = shacl_validate(g, shacl_graph=_shapes_graph(), inference="none")
    assert not conforms
    assert "grain" in results_text.lower()


def test_column_missing_source_is_caught():
    g = Graph()
    prop = EX.broken_column
    g.add((prop, RDF.type, OWL.DatatypeProperty))
    g.add((prop, RDFS.comment, Literal("has a description")))
    g.add((prop, EX.role, Literal("attribute")))
    # deliberately no ex:source -- an unsourced column claim
    conforms, _, _ = shacl_validate(g, shacl_graph=_shapes_graph(), inference="none")
    assert not conforms


def test_relationship_bad_cardinality_is_caught():
    g = Graph()
    prop = EX.broken_relationship
    g.add((prop, RDF.type, OWL.ObjectProperty))
    g.add((prop, EX.source, Literal("some citation")))
    g.add((prop, EX.cardinality, Literal("many-to-many")))  # not an allowed value
    conforms, _, _ = shacl_validate(g, shacl_graph=_shapes_graph(), inference="none")
    assert not conforms


def test_many_to_one_relationship_becomes_functional_property():
    """Real OWL semantics survive the export, not just a text label."""
    customer = Entity(name="customers", grain="x", grain_source="x", summary="x", columns=[], relationships=[])
    order = Entity(
        name="orders", grain="x", grain_source="x", summary="x", columns=[],
        relationships=[Relationship(
            to_entity="customers", from_column="customer_id", to_column="customer_id",
            cardinality="many-to-one", description="each order belongs to one customer",
            source="orders.sql line 12",
        )],
    )
    g = build_graph([customer, order])
    prop = EX["orders_customer_id_to_customers"]
    assert (prop, RDF.type, OWL.FunctionalProperty) in g
    assert (prop, RDF.type, OWL.InverseFunctionalProperty) not in g


def test_one_to_one_relationship_becomes_functional_and_inverse_functional():
    a = Entity(name="a", grain="x", grain_source="x", summary="x", columns=[], relationships=[])
    b = Entity(
        name="b", grain="x", grain_source="x", summary="x", columns=[],
        relationships=[Relationship(
            to_entity="a", from_column="a_id", to_column="a_id",
            cardinality="one-to-one", description="each b has exactly one a",
            source="b.sql line 1",
        )],
    )
    g = build_graph([a, b])
    prop = EX["b_a_id_to_a"]
    assert (prop, RDF.type, OWL.FunctionalProperty) in g
    assert (prop, RDF.type, OWL.InverseFunctionalProperty) in g
