"""Negative-control tests for the citation validator.

A validator that only ever passes correct input isn't proven -- it could
just as easily be a rubber stamp. These tests deliberately inject wrong
claims and assert the validator actually catches each one. Same principle
already used elsewhere in this project: measure with a negative control,
not just a plausible-looking positive result.
"""
import json

import pytest

from review_signoffs import is_signed_off, review_key, text_hash
from schema import ColumnFact, Entity, Relationship
from validate_grounding import validate_entity


@pytest.fixture
def facts():
    with open("structural_facts.json") as f:
        return json.load(f)


def test_false_primary_key_claim_is_caught(facts):
    bad_pk = Entity(
        name="customers",
        grain="x",
        grain_source="x",
        summary="x",
        columns=[
            ColumnFact(
                name="first_name",  # real column, but NOT unique+not_null
                description="Customer's first name",
                role="primary_key",  # false claim
                source="manifest",
            ),
        ],
        relationships=[],
    )
    failures, _ = validate_entity(bad_pk, facts)
    assert any("marked primary_key but" in f for f in failures)


def test_fabricated_relationship_is_caught(facts):
    bad_rel = Entity(
        name="customers",
        grain="x",
        grain_source="x",
        summary="x",
        columns=[],
        relationships=[
            Relationship(
                to_entity="products",  # customers has no relationship to products
                from_column="customer_id",
                to_column="product_id",
                cardinality="one-to-many",
                description="fabricated relationship",
                source="fabricated",
            ),
        ],
    )
    failures, _ = validate_entity(bad_rel, facts)
    assert any("no matching relationships test found" in f for f in failures)


def test_fabricated_manifest_description_is_caught(facts):
    bad_desc = Entity(
        name="customers",
        grain="x",
        grain_source="x",
        summary="x",
        columns=[
            ColumnFact(
                name="customer_id",
                description="This is a completely made up description",
                role="primary_key",
                source="manifest",
            ),
        ],
        relationships=[],
    )
    failures, _ = validate_entity(bad_desc, facts)
    assert any("does not match the manifest exactly" in f for f in failures)


def test_fabricated_description_is_caught_even_with_a_non_manifest_source(facts):
    """F2 (security review): `source` is a free-form string written by the
    same agent whose claim is being audited -- it must not be able to opt
    a claim out of a check that already applies to it. customer_id has a
    real manifest description ("Unique identifier for a customer"); citing
    a SQL line instead of "manifest" must not let a fabricated description
    slip past as a mere review item."""
    bad_desc = Entity(
        name="customers",
        grain="x", grain_source="x", summary="x",
        columns=[
            ColumnFact(
                name="customer_id",
                description="This is a completely made up description",
                role="attribute",  # not primary_key -- isolates F2 from B2
                source="stg_customers.sql:12 renamed CTE",  # not "manifest"
            ),
        ],
        relationships=[],
    )
    failures, review = validate_entity(bad_desc, facts)
    assert any("customer_id" in f and "does not match" in f for f in failures)
    assert not any(r["key"] == "customers:column-source:customer_id" for r in review)


def test_fabricated_description_with_non_manifest_source_and_no_manifest_entry_stays_a_review_item(facts):
    """Falsification for F2's fix: a column that genuinely has NO manifest
    description (a real SQL-only claim) must still be a review item, not a
    failure -- the fix must only close the self-selection path, not punish
    the legitimate case."""
    bad_rel = Entity(
        name="customers",
        grain="x", grain_source="x", summary="x",
        columns=[
            ColumnFact(
                name="totally_made_up_col",
                description="I invented this",
                role="attribute",
                source="models/stg_customers.sql:12",
            ),
        ],
        relationships=[],
    )
    failures, review = validate_entity(bad_rel, facts)
    assert failures == []
    assert any(r["key"] == "customers:column-source:totally_made_up_col" for r in review)


def test_manifest_source_column_that_matches_stays_clean(facts):
    """Falsification: a genuinely correct source='manifest' column must
    still pass with zero failures after the F2/B2 fix -- the legitimate
    mechanically-checkable case is untouched."""
    good = Entity(
        name="customers",
        grain="x", grain_source="x", summary="x",
        columns=[
            ColumnFact(
                name="customer_id",
                description="Unique identifier for a customer",
                role="primary_key",
                source="manifest",
            ),
        ],
        relationships=[],
    )
    failures, _ = validate_entity(good, facts)
    assert failures == []


def test_primary_key_claim_on_a_column_absent_from_the_manifest_is_caught(facts):
    """B2 (correctness review): role="primary_key" cited via a non-manifest
    source on a column that doesn't exist in structural_facts.json at all
    is exactly as fabricated as an uncited relationship -- it must fail,
    not silently pass because the membership guard skipped the key proof."""
    bad_pk = Entity(
        name="stg_customers",
        grain="x", grain_source="x", summary="x",
        columns=[
            ColumnFact(
                name="totally_made_up_col",
                description="I invented this",
                role="primary_key",
                source="models/stg_customers.sql:12",
            ),
        ],
        relationships=[],
    )
    failures, review = validate_entity(bad_pk, facts)
    assert any(
        "totally_made_up_col" in f and "primary_key" in f and "does not exist" in f
        for f in failures
    ), failures
    # The review item for the citation itself must also surface the
    # unproven key claim, so a human signing off can see what they're
    # approving -- not just "verify this citation by hand".
    col_source_items = [r for r in review if r["key"] == "stg_customers:column-source:totally_made_up_col"]
    assert len(col_source_items) == 1
    assert "primary_key" in col_source_items[0]["text"] or "unproven" in col_source_items[0]["text"]


def test_real_generated_entities_pass_clean(facts):
    """The positive case: the actual generated entities should have zero
    mechanically-checkable failures. If this test starts failing, either
    the entities regressed or structural_facts.json changed underneath
    them (e.g. jaffle_shop's schema.yml was edited) -- worth knowing
    either way, not something to silently ignore."""
    from generate_customers_entity import customers
    from generate_orders_entity import orders
    from generate_remaining_entities import ALL_REMAINING

    for entity in [customers, orders] + ALL_REMAINING:
        failures, _ = validate_entity(entity, facts)
        assert failures == [], f"{entity.name}: {failures}"


# --- Signoff gate: review items are flagged, not silently trusted, until a
# human explicitly confirms them. These are negative controls for the gate
# itself -- same principle as above, applied one layer up.


def test_unsigned_review_item_is_pending():
    item = {"key": review_key("customers", "grain"), "text": "some grain claim", "text_hash": text_hash("some grain claim")}
    assert is_signed_off(item, signoffs={}) is False


def test_matching_signoff_clears_the_item():
    text = "some grain claim"
    item = {"key": review_key("customers", "grain"), "text": text, "text_hash": text_hash(text)}
    signoffs = {item["key"]: {"text_hash": text_hash(text), "reviewer": "Ricardo Granados"}}
    assert is_signed_off(item, signoffs) is True


def test_stale_signoff_is_treated_as_pending_not_valid():
    """If the claim's text changes after it was signed off, the old signoff
    must NOT silently carry forward -- that would let a claim change
    underneath an approval nobody re-checked."""
    old_text = "grain: one row per customer"
    new_text = "grain: one row per customer, aggregated lifetime metrics"
    item = {"key": review_key("customers", "grain"), "text": new_text, "text_hash": text_hash(new_text)}
    signoffs = {item["key"]: {"text_hash": text_hash(old_text), "reviewer": "Ricardo Granados"}}
    assert is_signed_off(item, signoffs) is False


def test_real_entities_review_items_are_pending_with_no_signoffs_file():
    """Honest baseline: nothing has been reviewed yet, so every review item
    on the real entities should currently show as pending. This is the gate
    actually doing its job, not a bug -- if this test ever finds review
    items pre-cleared without a real review_signoffs.json entry, something
    is silently passing what should be blocked."""
    from generate_customers_entity import customers
    from generate_orders_entity import orders
    from generate_remaining_entities import ALL_REMAINING

    with open("structural_facts.json") as f:
        facts = json.load(f)

    for entity in [customers, orders] + ALL_REMAINING:
        _, review = validate_entity(entity, facts)
        assert len(review) > 0, f"{entity.name}: expected at least one review item (grain, if nothing else)"
        for item in review:
            assert is_signed_off(item, signoffs={}) is False


# --- B1: an unauthorized-but-recorded signoff must not read as if it were a
# clean, fully-reviewed run. is_signed_off's own comparison stays untouched
# (ADR-002: refusing the write would leave nothing to show in a reviewable
# branch/PR) -- these are reporting-layer tests only, same "flag, never
# silently accept" discipline is_signed_off already applies to staleness,
# applied here to authorization instead.


def test_reviewer_display_marks_an_unauthorized_signoff():
    from review_signoffs import reviewer_display

    record = {"reviewer": "Someone Else", "signer_authorized": False}
    assert reviewer_display(record) == "Someone Else (UNAUTHORIZED)"


def test_reviewer_display_leaves_an_authorized_signoff_unmarked():
    """Falsification: the marker must not leak onto the ordinary case."""
    from review_signoffs import reviewer_display

    record = {"reviewer": "Ricardo Granados", "signer_authorized": True}
    assert reviewer_display(record) == "Ricardo Granados"


def test_reviewer_display_treats_a_missing_field_as_unmarked():
    """Records written before this field existed have no signer_authorized
    key at all -- absence must not be treated as unauthorized (that would
    invent a fact the record never claimed), same honesty principle as
    sign()'s agent_attestation-absence handling."""
    from review_signoffs import reviewer_display

    record = {"reviewer": "Ricardo Granados"}
    assert reviewer_display(record) == "Ricardo Granados"


def test_summarize_clean_status_is_the_unconditional_message_when_nothing_is_unauthorized():
    from validate_grounding import summarize_clean_status

    assert summarize_clean_status([]) == (
        "Clean: no mechanically-checkable failures, and every "
        "non-mechanical claim has a human signoff on file."
    )


def test_summarize_clean_status_does_not_claim_clean_when_a_signoff_is_unauthorized():
    """Falsification of the test above: a non-empty list must suppress the
    unconditional 'Clean' wording, not just append to it."""
    from validate_grounding import summarize_clean_status

    msg = summarize_clean_status(["customers:grain"])
    assert "Clean:" not in msg
    assert "customers:grain" in msg
    assert "unauthorized" in msg.lower()


def test_validate_grounding_report_flags_an_unauthorized_signoff_end_to_end(tmp_path, monkeypatch, capsys):
    """Full main() run, not just the pure functions in isolation. Two
    synthetic entities, each with exactly one review item (grain -- always
    present per validate_entity), both SIGNED so no review item is left
    pending -- the only way to reach the final-summary branch at all. One
    signoff is authorized, the other is recorded (per ADR-002, honestly
    written rather than refused) as NOT authorized: the report must say so
    explicitly and must NOT print the unconditional 'Clean' message --
    while still exiting 0, since this is a reporting fix, not a new
    blocking condition."""
    import generate_customers_entity
    import generate_orders_entity
    import generate_remaining_entities
    import validate_grounding

    customers_entity = Entity(
        name="customers", grain="one row per customer",
        grain_source="models/customers.sql", summary="x", columns=[], relationships=[],
    )
    orders_entity = Entity(
        name="orders", grain="one row per order",
        grain_source="models/orders.sql", summary="x", columns=[], relationships=[],
    )
    monkeypatch.setattr(generate_customers_entity, "customers", customers_entity)
    monkeypatch.setattr(generate_orders_entity, "orders", orders_entity)
    monkeypatch.setattr(generate_remaining_entities, "ALL_REMAINING", [])

    monkeypatch.chdir(tmp_path)
    with open("structural_facts.json", "w") as f:
        json.dump(
            {"models": {"customers": {"columns": {}}, "orders": {"columns": {}}}, "relationships": []},
            f,
        )

    customers_grain_text = (
        'customers: "one row per customer" -- requires human verification. '
        "Citation: models/customers.sql"
    )
    orders_grain_text = (
        'orders: "one row per order" -- requires human verification. '
        "Citation: models/orders.sql"
    )
    with open("review_signoffs.json", "w") as f:
        json.dump(
            {
                "customers:grain": {
                    "text_hash": text_hash(customers_grain_text),
                    "reviewer": "Someone Else",
                    "signer_authorized": False,
                },
                "orders:grain": {
                    "text_hash": text_hash(orders_grain_text),
                    "reviewer": "Ricardo Granados",
                    "signer_authorized": True,
                },
            },
            f,
        )

    with pytest.raises(SystemExit) as exc:
        validate_grounding.main()

    assert exc.value.code == 0  # reporting-only -- must not become a new blocking condition
    out = capsys.readouterr().out
    assert "Clean: no mechanically-checkable failures" not in out
    assert "unauthorized" in out.lower()
    assert "Someone Else (UNAUTHORIZED)" in out
    assert "Ricardo Granados (UNAUTHORIZED)" not in out  # falsification: the authorized signoff stays unmarked


def test_validate_grounding_report_still_prints_clean_when_every_signoff_is_authorized(tmp_path, monkeypatch, capsys):
    """Falsification of the test above: the same two-entity setup, but both
    signoffs authorized, must still produce the ordinary, unmarked Clean
    report -- this fix must only change behavior for the unauthorized case."""
    import generate_customers_entity
    import generate_orders_entity
    import generate_remaining_entities
    import validate_grounding

    customers_entity = Entity(
        name="customers", grain="one row per customer",
        grain_source="models/customers.sql", summary="x", columns=[], relationships=[],
    )
    orders_entity = Entity(
        name="orders", grain="one row per order",
        grain_source="models/orders.sql", summary="x", columns=[], relationships=[],
    )
    monkeypatch.setattr(generate_customers_entity, "customers", customers_entity)
    monkeypatch.setattr(generate_orders_entity, "orders", orders_entity)
    monkeypatch.setattr(generate_remaining_entities, "ALL_REMAINING", [])

    monkeypatch.chdir(tmp_path)
    with open("structural_facts.json", "w") as f:
        json.dump(
            {"models": {"customers": {"columns": {}}, "orders": {"columns": {}}}, "relationships": []},
            f,
        )

    customers_grain_text = (
        'customers: "one row per customer" -- requires human verification. '
        "Citation: models/customers.sql"
    )
    orders_grain_text = (
        'orders: "one row per order" -- requires human verification. '
        "Citation: models/orders.sql"
    )
    with open("review_signoffs.json", "w") as f:
        json.dump(
            {
                "customers:grain": {
                    "text_hash": text_hash(customers_grain_text),
                    "reviewer": "Ricardo Granados",
                    "signer_authorized": True,
                },
                "orders:grain": {
                    "text_hash": text_hash(orders_grain_text),
                    "reviewer": "Ricardo Granados",
                    "signer_authorized": True,
                },
            },
            f,
        )

    with pytest.raises(SystemExit) as exc:
        validate_grounding.main()

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "Clean: no mechanically-checkable failures, and every non-mechanical claim has a human signoff on file." in out
    assert "UNAUTHORIZED" not in out


# --- suggest_fixes.py: proves the auto-fix suggester actually proposes the
# correct manifest text, and stays silent when there's nothing to fix.


def test_suggest_fixes_proposes_the_correct_manifest_text(facts):
    from suggest_fixes import suggest_description_fixes

    bad_entity = Entity(
        name="customers",
        grain="x", grain_source="x", summary="x",
        columns=[ColumnFact(
            name="lifetime_spend",
            description="Total amount spent by this customer",  # wrong: drops "across all orders in USD"
            role="attribute", source="manifest",
        )],
        relationships=[],
    )
    suggestions = suggest_description_fixes(bad_entity, facts)
    assert len(suggestions) == 1
    assert suggestions[0]["suggested"] == "Total amount spent across all orders in USD"
    assert suggestions[0]["current"] == "Total amount spent by this customer"


def test_suggest_fixes_is_silent_on_a_correct_claim(facts):
    from suggest_fixes import suggest_description_fixes

    good_entity = Entity(
        name="customers",
        grain="x", grain_source="x", summary="x",
        columns=[ColumnFact(
            name="lifetime_spend",
            description="Total amount spent across all orders in USD",  # exact manifest text
            role="attribute", source="manifest",
        )],
        relationships=[],
    )
    assert suggest_description_fixes(good_entity, facts) == []


def test_real_entities_have_no_suggested_fixes(facts):
    """Honest baseline: the real entities are currently clean, so there
    should be nothing to suggest."""
    from generate_customers_entity import customers
    from generate_orders_entity import orders
    from generate_remaining_entities import ALL_REMAINING
    from suggest_fixes import suggest_description_fixes

    for entity in [customers, orders] + ALL_REMAINING:
        assert suggest_description_fixes(entity, facts) == [], f"{entity.name} has an unexpected suggested fix"


# --- validate_coverage.py: proves the coverage-gap check actually finds a
# real, planted gap, and stays silent when nothing's missing.


def test_coverage_gap_is_found_for_an_undocumented_column(facts):
    from validate_coverage import find_coverage_gaps

    incomplete_customers = Entity(
        name="customers",
        grain="x", grain_source="x", summary="x",
        columns=[ColumnFact(name="customer_id", description="Unique identifier for a customer", role="primary_key", source="manifest")],
        relationships=[],
    )
    gaps = find_coverage_gaps([incomplete_customers], facts)
    gap_columns = {g["column"] for g in gaps if g["model"] == "customers"}
    assert "lifetime_spend" in gap_columns  # real column, not claimed by this deliberately-incomplete entity


# --- generate_erd.py: proves the dedup and sanitization logic, ported
# from patterns already proven across internal dbt tooling I've built elsewhere,
# actually holds on our data shape.


def test_erd_dedupes_a_relationship_declared_on_both_sides():
    from generate_erd import generate_mermaid_erd

    a = Entity(name="a", grain="x", grain_source="x", summary="x", columns=[],
        relationships=[Relationship(to_entity="b", from_column="b_id", to_column="b_id",
            cardinality="many-to-one", description="a belongs to b", source="x")])
    b = Entity(name="b", grain="x", grain_source="x", summary="x", columns=[],
        relationships=[Relationship(to_entity="a", from_column="b_id", to_column="b_id",
            cardinality="one-to-many", description="b has many a", source="x")])

    erd = generate_mermaid_erd([a, b])
    edge_lines = [l for l in erd.splitlines() if "--" in l]
    assert len(edge_lines) == 1, f"expected exactly one edge, got: {edge_lines}"


def test_erd_sanitizes_names_that_would_break_mermaid():
    from generate_erd import sanitize_attribute_name, sanitize_mermaid_id

    assert sanitize_mermaid_id("123-weird name!") == "E_123_WEIRD_NAME_"
    assert sanitize_attribute_name("1st_column") == "col_1st_column"


def test_real_entities_have_exactly_the_one_deliberate_coverage_gap():
    """Honest baseline: after completing customers.py and orders.py, every
    real column in every modeled entity should be documented -- EXCEPT
    stg_kiosk_sales, which is deliberately left ungrounded (see
    models/staging/stg_kiosk_sales.sql's own comment and
    scripts/generate_kiosk_seed.py): a "new channel, wired up fast, not
    yet reconciled" table for attendees to ground live on tutorial day.
    If this test ever finds a DIFFERENT gap, or the kiosk gap disappears
    without a real generate_kiosk_sales_entity.py existing, something
    changed that this baseline needs to know about."""
    from generate_customers_entity import customers
    from generate_orders_entity import orders
    from generate_remaining_entities import ALL_REMAINING
    from validate_coverage import find_coverage_gaps

    with open("structural_facts.json") as f:
        facts = json.load(f)

    gaps = find_coverage_gaps([customers, orders] + ALL_REMAINING, facts)
    assert gaps == [{"model": "stg_kiosk_sales", "column": None,
        "note": "entire model has no ontology entity at all"}], f"unexpected coverage gaps: {gaps}"
