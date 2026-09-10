"""Ontology schema for the PyData tutorial.

Design principles this encodes (from the AI Data Modeling Toolkit design
note, Sec 11 and Sec 12.8):

- Grain is a first-class, mandatory field (dbt-wow's own grain-gate: no
  model description is complete without a written grain statement).
- Every semantic field (grain, summary, relationship description) carries
  a `source` citation -- either "manifest" (already true in the dbt
  project, zero judgment involved) or a specific grounding reference
  (a SQL line, a column description) if it required reasoning over the
  actual model logic. Nothing is allowed to just be an unsourced claim.
- Per the minimal-ontology-principle (Sec 12.8): the `summary` field
  should capture the delta -- what this entity means specifically in
  THIS project -- not a generic restatement of what a "customer" or
  "order" conceptually is. Column descriptions that already exist in
  the dbt project (schema.yml) are reused as-is, not regenerated.
"""
from typing import Literal
from pydantic import BaseModel, Field


class ColumnFact(BaseModel):
    name: str
    description: str
    role: Literal["primary_key", "foreign_key", "attribute"]
    source: str = Field(
        description="Where this description came from: 'manifest' if it "
        "already existed in schema.yml, or a specific citation (file:line "
        "or SQL fragment) if it required reading the model's SQL to confirm."
    )


class Relationship(BaseModel):
    to_entity: str
    from_column: str
    to_column: str
    cardinality: Literal["many-to-one", "one-to-many", "one-to-one"]
    description: str = Field(
        description="Business-meaningful label for this relationship, "
        "e.g. 'each order belongs to one customer' -- not just the raw FK."
    )
    source: str = Field(
        description="Citation for the cardinality/description claim -- "
        "structural facts alone can prove FK existence, but cardinality "
        "beyond many-to-one needs grounding in the actual model logic."
    )


class Entity(BaseModel):
    name: str
    grain: str = Field(
        description="Mandatory grain statement in business language: "
        "'One row represents [one X] for [one Y]'. Per the dbt-wow gate, "
        "no entity is complete without this."
    )
    grain_source: str = Field(
        description="Citation for the grain claim -- must point at the "
        "actual model SQL (a GROUP BY, a source grain, a JOIN pattern), "
        "not be asserted from the model name alone."
    )
    summary: str = Field(
        description="What this entity means specifically in THIS project "
        "-- the delta from generic/obvious meaning, per the "
        "minimal-ontology-principle. Not a restatement of what a "
        "'customer' or 'order' conceptually is in general."
    )
    columns: list[ColumnFact]
    relationships: list[Relationship]


class Ontology(BaseModel):
    entities: list[Entity]


class MetricDefinition(BaseModel):
    """A business metric grounded in the ontology, not asserted freely.

    Same discipline as Entity, one layer up: a metric can only be trusted
    if every column it references actually exists in the already-validated
    ontology. `references` is checked mechanically (validate_metrics.py);
    `rationale` and `caveats` are judgment calls, same as grain -- flagged
    for review, never auto-passed.
    """
    name: str
    grain: str = Field(description="The level this metric is computed at, "
        "e.g. 'per customer', 'per product', 'per store' -- must match "
        "the grain of the entity/entities it's built from.")
    formula: str = Field(description="Human-readable expression using "
        "'entity.column' references, e.g. "
        "'customers.lifetime_spend / customers.order_count'.")
    references: list[str] = Field(description="Every 'entity.column' path "
        "the formula depends on -- checked against the validated ontology, "
        "not asserted. A metric referencing a column that doesn't exist "
        "fails exactly like a fabricated relationship would.")
    rationale: str = Field(description="Why this metric is meaningful for "
        "THIS project specifically, not a generic definition of the metric.")
    caveats: str = Field(description="Known edge cases or limitations -- "
        "division by zero, denormalization gaps, anything that makes this "
        "metric less clean than the formula alone suggests. Required, not "
        "optional: a metric with no caveats field should still say 'none "
        "identified', not omit the question.")
    source: str = Field(description="Citation into the ontology entities/"
        "columns this metric is grounded in.")
