"""Tests for the questionnaire routing store, renderer, and status model --
M1 T1 + T2 + T3 + T6.

Same negative-control discipline as test_grounding.py/test_authorized_signers.py:
each control gets a falsification pair, proving the guard actually has teeth
rather than passing by accident (e.g. by refusing everything, or by being
hardcoded to one answer).
"""
import fnmatch
import json
import subprocess
from pathlib import Path

import pytest
from schema import ColumnFact, Entity, Relationship

from review_signoffs import (
    entity_status_rollup,
    load_signoffs,
    review_key,
    status_of,
    text_hash,
)

from generate_questionnaire import (
    CARDINALITY_PROSE,
    _parse_render_args,
    _render_question_block,
    build_questionnaire_items,
    is_routing_stale,
    load_routing,
    render_combined,
    render_markdown,
    route,
    route_if_current,
    save_routing,
)


# --- route() -- the pure write, mirrors review_signoffs.sign(): unconditional
# given a key/text, no membership check of its own (that's route_if_current's
# and the CLI's job, same split as sign()/main()'s `sign` handler).


def test_route_writes_a_record_tied_to_the_items_hash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    route(
        key="customers:grain",
        text="one row per customer",
        owner_role="Retail Operations Lead",
        question="When we count a customer, what actually counts as one?",
        routed_by="Ricardo Granados, Analytics Engineer",
    )
    record = load_routing()["customers:grain"]
    assert record["text_hash"] == text_hash("one row per customer")
    assert record["owner_role"] == "Retail Operations Lead"
    assert record["question"] == "When we count a customer, what actually counts as one?"
    assert record["routed_by"] == "Ricardo Granados, Analytics Engineer"


def test_route_with_no_routed_at_records_empty_string_not_fabricated(tmp_path, monkeypatch):
    """Mirrors test_sign_without_agent_model_records_no_attestation's honesty
    principle -- absence is honest, not a bug. Nothing here should invent a
    timestamp on the caller's behalf."""
    monkeypatch.chdir(tmp_path)
    route(key="orders:grain", text="x", owner_role="Store Ops", question="q?")
    record = load_routing()["orders:grain"]
    assert record["routed_at"] == ""


def test_route_with_explicit_routed_at_records_that_exact_string(tmp_path, monkeypatch):
    """Falsification of the test above: supplying a real timestamp must
    record that exact string -- proves the field isn't just always blank."""
    monkeypatch.chdir(tmp_path)
    route(
        key="orders:grain",
        text="x",
        owner_role="Store Ops",
        question="q?",
        routed_at="2026-08-26T09:00:00+00:00",
    )
    record = load_routing()["orders:grain"]
    assert record["routed_at"] == "2026-08-26T09:00:00+00:00"


# --- is_routing_stale() -- mirrors is_signed_off()'s staleness comparison.


def test_is_routing_stale_true_when_recorded_hash_differs_from_current():
    old_text = "grain: one row per customer"
    new_text = "grain: one row per customer, aggregated lifetime metrics"
    item = {"key": review_key("customers", "grain"), "text": new_text, "text_hash": text_hash(new_text)}
    routing = {item["key"]: {"text_hash": text_hash(old_text), "owner_role": "Retail Ops", "question": "q?"}}
    assert is_routing_stale(item, routing) is True


def test_is_routing_stale_false_when_recorded_hash_matches_current():
    """Falsification of the test above: matching hashes must report False --
    proves the check isn't hardcoded to True."""
    text = "grain: one row per customer"
    item = {"key": review_key("customers", "grain"), "text": text, "text_hash": text_hash(text)}
    routing = {item["key"]: {"text_hash": text_hash(text), "owner_role": "Retail Ops", "question": "q?"}}
    assert is_routing_stale(item, routing) is False


def test_is_routing_stale_false_when_item_has_no_routing_record():
    """A never-routed item isn't 'stale' -- it's simply not routed yet.
    Distinguishing that from staleness is build_questionnaire_items' job in
    T2; is_routing_stale itself must not conflate the two."""
    item = {"key": review_key("orders", "grain"), "text": "x", "text_hash": text_hash("x")}
    assert is_routing_stale(item, routing={}) is False


# --- route_if_current() -- the membership guard `route`'s CLI subcommand
# uses, same safety property as review_signoffs.py's `sign` guard ("No
# current review item with key {key!r}"). Factored out as its own function
# (rather than left inline in main()) so it's testable without needing the
# real entity graph or structural_facts.json -- same principle T2's
# build_questionnaire_items already applies: take review items as a
# parameter, never fetch them.


def test_route_if_current_rejects_a_key_not_in_the_review_set(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    all_review = [{"key": "customers:grain", "text": "t", "text_hash": text_hash("t")}]
    result = route_if_current(
        "orders:grain", all_review, owner_role="Store Ops", question="q?"
    )
    assert result is False
    assert load_routing() == {}


def test_route_if_current_accepts_a_key_that_is_in_the_review_set(tmp_path, monkeypatch):
    """Falsification of the test above: run it with a valid key and assert
    the record IS written -- proves the guard isn't simply refusing
    everything."""
    monkeypatch.chdir(tmp_path)
    all_review = [{"key": "customers:grain", "text": "t", "text_hash": text_hash("t")}]
    result = route_if_current(
        "customers:grain", all_review, owner_role="Store Ops", question="q?"
    )
    assert result is True
    record = load_routing()["customers:grain"]
    assert record["owner_role"] == "Store Ops"
    assert record["text_hash"] == text_hash("t")


# --- honest baseline against the real entities/review items, same style as
# test_real_entities_review_items_are_pending_with_no_signoffs_file.


def test_real_entities_review_items_are_unrouted_with_no_routing_file():
    import json

    from generate_customers_entity import customers
    from generate_orders_entity import orders
    from generate_remaining_entities import ALL_REMAINING
    from validate_grounding import validate_entity

    with open("structural_facts.json") as f:
        facts = json.load(f)

    all_review = []
    for entity in [customers, orders] + ALL_REMAINING:
        _, review = validate_entity(entity, facts)
        all_review.extend(review)

    routing = {}
    for item in all_review:
        assert item["key"] not in routing
        assert is_routing_stale(item, routing) is False


# ============================================================================
# M1 T2 -- renderer, --combine, provenance header
# ============================================================================

# --- fixtures -----------------------------------------------------------


def _minimal_entity(name="widgets", grain="one row per widget",
                     grain_source="widgets.sql GROUP BY id", relationships=None,
                     columns=None):
    return Entity(
        name=name,
        grain=grain,
        grain_source=grain_source,
        summary="test fixture entity",
        columns=columns if columns is not None else [
            ColumnFact(name="id", description="widget id", role="primary_key", source="manifest"),
        ],
        relationships=relationships if relationships is not None else [],
    )


def _routing_record(text_hash_value, owner_role="Ops Lead", question="q?", routed_by=""):
    return {
        "text_hash": text_hash_value,
        "owner_role": owner_role,
        "question": question,
        "routed_by": routed_by,
        "routed_at": "",
    }


def _real_entities_and_review():
    with open("structural_facts.json") as f:
        facts = json.load(f)

    from generate_customers_entity import customers
    from generate_orders_entity import orders
    from generate_remaining_entities import ALL_REMAINING
    from validate_grounding import validate_entity

    entities = [customers, orders] + ALL_REMAINING
    all_review = []
    for entity in entities:
        _, review = validate_entity(entity, facts)
        all_review.extend(review)
    return entities, all_review


def _strip_evidence_lines(markdown: str) -> str:
    """Strips BOTH the reference line and the 'Where that came from' citation
    value from the jargon check -- a correction discovered verifying NC-1
    against the real entities, same class of finding as R3.1/R3.3.

    Sec 2.4 is explicit that the citation line is allowed to be
    file-path-shaped ("that is fine -- it is labelled as evidence... not as
    an instruction to the reader"). For grain items that citation is a SQL
    file path, which never collides with the banned list. But a real
    relationship item's citation in THIS project is
    "structural_facts.json relationships[]: ..." verbatim (see
    generate_orders_entity.py:115, generate_remaining_entities.py's several
    relationship sources) -- exactly one of NC-1's banned tokens, present
    by design, not as a leak. NC-1 must check the CLAIM prose (question,
    "what we currently believe", "who this is for") for jargon, not the
    citation field the plan itself says must stay intact.
    """
    lines = markdown.splitlines()
    cleaned = []
    skip_until_blank = False
    for line in lines:
        if line.startswith("*Reference:"):
            continue
        if line == "**Where that came from**":
            cleaned.append(line)
            skip_until_blank = True
            continue
        if skip_until_blank:
            if line.strip() == "":
                skip_until_blank = False
                cleaned.append(line)
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


BANNED_TOKENS = [
    "cardinality=", "source=", "structural_facts.json", "review_signoffs",
    "text_hash", "FK", "mechanically checkable",
]


# --- NC-1: jargon leak (the primary control) -----------------------------


def test_render_contains_no_jargon_leak_against_real_entities():
    entities, all_review = _real_entities_and_review()
    # Route one item of each kind actually present, up to 3 kinds.
    routing, seen_kinds = {}, set()
    for item in all_review:
        kind = item["key"].split(":")[1]
        if kind not in seen_kinds:
            routing[item["key"]] = _routing_record(item["text_hash"])
            seen_kinds.add(kind)

    renderable, stale = build_questionnaire_items(all_review, entities, routing)
    assert renderable  # sanity: the fixture actually exercised something
    by_entity = {}
    for item in renderable:
        by_entity.setdefault(item["entity_name"], []).append(item)

    for entity_name, items in by_entity.items():
        doc = render_markdown(entity_name, items, [], generated_at="2026-08-26")
        cleaned = _strip_evidence_lines(doc)
        for token in BANNED_TOKENS:
            assert token not in cleaned, f"{token!r} leaked into the rendered doc for {entity_name}"


def test_banned_tokens_do_appear_in_raw_item_text_falsification():
    """Falsification of NC-1: the SAME token check against the raw
    item["text"] strings must produce hits. That pairing is what proves the
    render-side test has teeth rather than passing because the tokens
    happen to be rare -- if a shortcut back to item["text"] were taken,
    NC-1 above would fail immediately."""
    _, all_review = _real_entities_and_review()
    raw_text = " ".join(item["text"] for item in all_review)
    hits = [token for token in BANNED_TOKENS if token in raw_text]
    assert hits, "expected banned tokens to appear in raw item text -- if none do, NC-1 tests nothing"


def test_reference_line_present_for_every_rendered_question():
    """Companion to NC-1: quiet but never absent. The reference line is
    scoped out of the jargon check above precisely because it's expected
    content (a key + a hash, not jargon prose) -- this proves it's still
    there on every single question, not silently dropped along with the
    banned tokens."""
    entities, all_review = _real_entities_and_review()
    routing = {item["key"]: _routing_record(item["text_hash"]) for item in all_review}
    renderable, _ = build_questionnaire_items(all_review, entities, routing)
    by_entity = {}
    for item in renderable:
        by_entity.setdefault(item["entity_name"], []).append(item)

    for entity_name, items in by_entity.items():
        doc = render_markdown(entity_name, items, [], generated_at="2026-08-26")
        for item in items:
            expected = f"*Reference: {item['key']} · {item['text_hash']} — please leave this line as it is.*"
            assert expected in doc


def test_reference_line_is_visible_text_not_an_html_comment():
    """Regression guard for R3.3 #1: the token must never regress to
    `<!-- item: ... -->` -- verified to render as visible junk through
    md-to-docx.js AND be destroyed on the Word round-trip."""
    entity = _minimal_entity()
    item = {"key": "widgets:grain", "text": "raw", "text_hash": text_hash("raw")}
    routing = {item["key"]: _routing_record(item["text_hash"])}
    renderable, _ = build_questionnaire_items([item], [entity], routing)
    doc = render_markdown("widgets", renderable, [], generated_at="d")
    assert "<!--" not in doc
    assert "·" in doc  # the reference line's separator, not "|"


def test_role_is_a_field_not_a_heading():
    """Regression guard for R3.3 #2: `## For: <Role>` must never come
    back -- it breaks the docx heading-depth limit once nested inside a
    combined document."""
    entity = _minimal_entity()
    item = {"key": "widgets:grain", "text": "raw", "text_hash": text_hash("raw")}
    routing = {item["key"]: _routing_record(item["text_hash"], owner_role="Retail Operations Lead")}
    renderable, _ = build_questionnaire_items([item], [entity], routing)
    doc = render_markdown("widgets", renderable, [], generated_at="d")
    assert "## For:" not in doc
    assert "**Who this is for:** Retail Operations Lead" in doc


# --- NC-2: evidence is never dropped --------------------------------------


def test_grain_source_citation_is_never_dropped():
    entity = _minimal_entity(grain_source="SENTINEL_ABC123 widgets.sql GROUP BY id")
    item = {"key": "widgets:grain", "text": "irrelevant raw text", "text_hash": text_hash("irrelevant raw text")}
    routing = {item["key"]: _routing_record(item["text_hash"])}
    renderable, _ = build_questionnaire_items([item], [entity], routing)
    doc = render_markdown("widgets", renderable, [], generated_at="d")
    assert "SENTINEL_ABC123 widgets.sql GROUP BY id" in doc


def test_a_different_unsupplied_sentinel_is_absent_falsification():
    """Falsification of NC-2: a sentinel that was never supplied anywhere
    must not appear -- proves the presence check above is a real substring
    match, not a tautology that would pass regardless of content."""
    entity = _minimal_entity(grain_source="SENTINEL_ABC123 widgets.sql GROUP BY id")
    item = {"key": "widgets:grain", "text": "irrelevant raw text", "text_hash": text_hash("irrelevant raw text")}
    routing = {item["key"]: _routing_record(item["text_hash"])}
    renderable, _ = build_questionnaire_items([item], [entity], routing)
    doc = render_markdown("widgets", renderable, [], generated_at="d")
    assert "SENTINEL_NEVER_SUPPLIED_XYZ" not in doc


# --- NC-3: only routed items appear ---------------------------------------


def test_only_routed_items_are_renderable():
    e1 = _minimal_entity("widgets", grain="ONLY_WIDGETS_GRAIN_MARKER")
    e2 = _minimal_entity("gadgets", grain="ONLY_GADGETS_GRAIN_MARKER")
    e3 = _minimal_entity("gizmos", grain="ONLY_GIZMOS_GRAIN_MARKER")
    items = [
        {"key": "widgets:grain", "text": "t1", "text_hash": text_hash("t1")},
        {"key": "gadgets:grain", "text": "t2", "text_hash": text_hash("t2")},
        {"key": "gizmos:grain", "text": "t3", "text_hash": text_hash("t3")},
    ]
    routing = {"widgets:grain": _routing_record(text_hash("t1"))}
    renderable, stale = build_questionnaire_items(items, [e1, e2, e3], routing)

    assert len(renderable) == 1
    assert renderable[0]["key"] == "widgets:grain"

    doc = render_markdown("widgets", renderable, [], generated_at="d")
    assert "ONLY_WIDGETS_GRAIN_MARKER" in doc
    assert "ONLY_GADGETS_GRAIN_MARKER" not in doc
    assert "ONLY_GIZMOS_GRAIN_MARKER" not in doc


def test_routing_a_second_item_grows_the_count_falsification():
    """Falsification of NC-3: route a second item and the renderable count
    must go to 2 -- proves the join isn't hard-filtered to one, and proves
    it isn't dumping everything pending regardless of routing."""
    e1 = _minimal_entity("widgets", grain="ONLY_WIDGETS_GRAIN_MARKER")
    e2 = _minimal_entity("gadgets", grain="ONLY_GADGETS_GRAIN_MARKER")
    items = [
        {"key": "widgets:grain", "text": "t1", "text_hash": text_hash("t1")},
        {"key": "gadgets:grain", "text": "t2", "text_hash": text_hash("t2")},
    ]
    routing = {
        "widgets:grain": _routing_record(text_hash("t1")),
        "gadgets:grain": _routing_record(text_hash("t2")),
    }
    renderable, stale = build_questionnaire_items(items, [e1, e2], routing)
    assert len(renderable) == 2


# --- NC-4: stale routing is surfaced, never silently sent ------------------


def test_stale_routing_is_never_silently_rendered():
    entity = _minimal_entity("widgets")
    item = {"key": "widgets:grain", "text": "new text", "text_hash": text_hash("new text")}
    routing = {"widgets:grain": _routing_record(text_hash("old text"), owner_role="Ops")}
    renderable, stale = build_questionnaire_items([item], [entity], routing)

    assert renderable == []
    assert len(stale) == 1
    assert stale[0]["key"] == "widgets:grain"

    doc = render_markdown("widgets", [], stale, generated_at="d")
    assert "⚠ Not included" in doc
    assert "### Q1" not in doc  # never rendered as an answerable question


def test_matching_hashes_move_the_item_into_renderable_falsification():
    """Falsification of NC-4: make the hashes match and the item must move
    into the main body -- proves staleness isn't hardcoded either way."""
    entity = _minimal_entity("widgets")
    item = {"key": "widgets:grain", "text": "same text", "text_hash": text_hash("same text")}
    routing = {"widgets:grain": _routing_record(text_hash("same text"))}
    renderable, stale = build_questionnaire_items([item], [entity], routing)
    assert len(renderable) == 1
    assert stale == []


# --- NC-5: cardinality prose contains no cardinality jargon -----------------


@pytest.mark.parametrize("cardinality", ["many-to-one", "one-to-many", "one-to-one"])
def test_cardinality_prose_has_no_jargon_token_and_the_plain_prose_is_present(cardinality):
    rel = Relationship(
        to_entity="orders", from_column="customer_id", to_column="id",
        cardinality=cardinality, description="each order belongs to one customer",
        source="orders.sql JOIN",
    )
    entity = _minimal_entity("customers", columns=[], relationships=[rel])
    item = {"key": "customers:relationship:orders", "text": "raw", "text_hash": text_hash("raw")}
    routing = {item["key"]: _routing_record(item["text_hash"])}
    renderable, _ = build_questionnaire_items([item], [entity], routing)
    doc = render_markdown("customers", renderable, [], generated_at="d")

    assert cardinality not in doc
    expected_prose = CARDINALITY_PROSE[cardinality].format(entity="customers", other="orders")
    assert expected_prose in doc
    # falsification: the enum token DOES exist in the source Relationship
    # object -- proves the absence check above compares against a real
    # input, not against something that was never going to appear anyway.
    assert rel.cardinality == cardinality


# --- --combine: header, per-entity/combined byte-identical question block --


def test_combine_produces_a_provenance_header_with_required_fields():
    entity = _minimal_entity("widgets")
    item = {"key": "widgets:grain", "text": "raw", "text_hash": text_hash("raw")}
    routing = {item["key"]: _routing_record(item["text_hash"], owner_role="Ops Lead")}
    renderable, _ = build_questionnaire_items([item], [entity], routing)
    combined = render_combined([("widgets", renderable)], generated_at="2026-08-26")

    assert combined.startswith("# Data model questions")
    assert "- **Generated:** 2026-08-26" in combined
    assert "- **Covers:** 1 entities · 1 questions · 1 roles" in combined
    assert "generated snapshot, not a living document" in combined
    assert "## widgets" in combined


def test_combine_header_is_not_yaml_front_matter_or_run_on_label_lines():
    """Regression guard for R3.1: neither form survives the real
    md-to-docx.js parser (front matter's `---` is dropped; consecutive
    `**Label:** value` lines collapse into one run-on paragraph)."""
    entity = _minimal_entity("widgets")
    item = {"key": "widgets:grain", "text": "raw", "text_hash": text_hash("raw")}
    routing = {item["key"]: _routing_record(item["text_hash"])}
    renderable, _ = build_questionnaire_items([item], [entity], routing)
    combined = render_combined([("widgets", renderable)], generated_at="2026-08-26")

    header = combined.split("## widgets")[0]
    assert not header.strip().startswith("---")
    assert "- **Generated:**" in header  # a bulleted field, not a bare label line


def test_combine_return_to_omitted_when_routed_by_is_not_uniform():
    e1, e2 = _minimal_entity("widgets"), _minimal_entity("gadgets")
    i1 = {"key": "widgets:grain", "text": "t1", "text_hash": text_hash("t1")}
    i2 = {"key": "gadgets:grain", "text": "t2", "text_hash": text_hash("t2")}
    routing = {
        "widgets:grain": _routing_record(text_hash("t1"), routed_by="Alice, Analytics Engineer"),
        "gadgets:grain": _routing_record(text_hash("t2"), routed_by="Bob, Analytics Engineer"),
    }
    renderable, _ = build_questionnaire_items([i1, i2], [e1, e2], routing)
    by_entity = {}
    for item in renderable:
        by_entity.setdefault(item["entity_name"], []).append(item)
    combined = render_combined(list(by_entity.items()), generated_at="d")
    assert "**Return to:**" not in combined


def test_combine_return_to_present_when_routed_by_is_uniform():
    """Falsification of the test above: a single shared routed_by value
    must appear -- proves omission isn't unconditional."""
    e1, e2 = _minimal_entity("widgets"), _minimal_entity("gadgets")
    i1 = {"key": "widgets:grain", "text": "t1", "text_hash": text_hash("t1")}
    i2 = {"key": "gadgets:grain", "text": "t2", "text_hash": text_hash("t2")}
    routing = {
        "widgets:grain": _routing_record(text_hash("t1"), routed_by="Alice, Analytics Engineer"),
        "gadgets:grain": _routing_record(text_hash("t2"), routed_by="Alice, Analytics Engineer"),
    }
    renderable, _ = build_questionnaire_items([i1, i2], [e1, e2], routing)
    by_entity = {}
    for item in renderable:
        by_entity.setdefault(item["entity_name"], []).append(item)
    combined = render_combined(list(by_entity.items()), generated_at="d")
    assert "- **Return to:** Alice, Analytics Engineer" in combined


def test_combine_question_block_is_byte_identical_to_per_entity_rendering():
    """The load-bearing property of R3.3 #2: --combine must be pure
    concatenation, not a second renderer. Proven directly, not by
    inspection: the exact block _render_question_block produces for an
    item is present verbatim in BOTH the per-entity file and the combined
    document."""
    entity = _minimal_entity("widgets")
    item = {"key": "widgets:grain", "text": "raw", "text_hash": text_hash("raw")}
    routing = {item["key"]: _routing_record(item["text_hash"])}
    renderable, _ = build_questionnaire_items([item], [entity], routing)

    block = _render_question_block(renderable[0], 1)
    per_entity_doc = render_markdown("widgets", renderable, [], generated_at="d")
    combined_doc = render_combined([("widgets", renderable)], generated_at="d")

    assert block in per_entity_doc
    assert block in combined_doc


def test_provenance_header_appears_only_in_combined_output_never_per_entity():
    entity = _minimal_entity("widgets")
    item = {"key": "widgets:grain", "text": "raw", "text_hash": text_hash("raw")}
    routing = {item["key"]: _routing_record(item["text_hash"])}
    renderable, _ = build_questionnaire_items([item], [entity], routing)
    per_entity_doc = render_markdown("widgets", renderable, [], generated_at="d")
    assert "generated snapshot, not a living document" not in per_entity_doc
    assert not per_entity_doc.startswith("# Data model questions")


# --- --owner / --out-dir flag parsing --------------------------------------


def test_parse_render_args_defaults():
    opts = _parse_render_args([])
    assert opts == {"owner": None, "out_dir": Path("questionnaires"), "combine": False}


def test_parse_render_args_reads_owner_out_dir_and_combine():
    opts = _parse_render_args(["--owner", "Store Ops", "--out-dir", "sent/", "--combine"])
    assert opts["owner"] == "Store Ops"
    assert opts["out_dir"] == Path("sent/")
    assert opts["combine"] is True


def test_parse_render_args_rejects_unrecognized_flag_falsification():
    """Falsification of the two tests above: an unrecognized flag must
    raise, proving the parser doesn't just silently accept anything."""
    with pytest.raises(ValueError):
        _parse_render_args(["--bogus"])


# --- import, don't duplicate ------------------------------------------------


def test_source_file_helper_is_imported_from_suggest_fixes_not_duplicated():
    """Identity, not equality -- same guard style as T6's planned
    single-sourcing test. generate_questionnaire must import
    suggest_fixes._source_file rather than re-deriving the entity->file
    map (R1.3)."""
    import suggest_fixes

    from generate_questionnaire import _source_file as gq_source_file

    assert gq_source_file is suggest_fixes._source_file


# --- honest baseline against the real entities/routing, combined path -----


def test_real_entities_render_cleanly_end_to_end_with_synthetic_routing():
    """Not a claim about the seeded routing file (T3's job, ships empty from
    T1) -- an end-to-end smoke test that the real Entity objects survive
    the full build -> render -> combine path without error, across every
    review-item kind that actually exists in this project."""
    entities, all_review = _real_entities_and_review()
    routing = {item["key"]: _routing_record(item["text_hash"]) for item in all_review}
    renderable, stale = build_questionnaire_items(all_review, entities, routing)
    assert stale == []  # every hash freshly matched, nothing should be stale
    assert len(renderable) == len(all_review)

    by_entity = {}
    for item in renderable:
        by_entity.setdefault(item["entity_name"], []).append(item)
    for entity_name, items in by_entity.items():
        render_markdown(entity_name, items, [], generated_at="2026-08-26")  # must not raise
    render_combined(list(by_entity.items()), generated_at="2026-08-26")  # must not raise


# ============================================================================
# M1 T3 -- confidentiality split, mechanically enforced
# ============================================================================

# --- NC-6: a filled/renamed questionnaire cannot be committed ---------------
#
# Run against the repo's REAL .gitignore (no tmp_path/monkeypatch.chdir --
# git check-ignore has to see the actual committed .gitignore, the thing
# this test is a claim about). None of the paths below need to exist on
# disk; `git check-ignore` reasons about the path string against the
# ignore rules, same as `git status` would.


def _check_ignored(path: str) -> bool:
    result = subprocess.run(["git", "check-ignore", "-q", path])
    return result.returncode == 0


def test_gitignore_covers_the_directory_not_just_the_generators_own_filename():
    """NC-6, strengthened per R1.3: a directory-level ignore has to catch a
    filled/renamed artifact under every shape it can plausibly take, not
    just the exact `<entity>.md` name the generator itself writes --
    the whole reason `questionnaires/` beat a `questionnaire*.md` glob."""
    assert _check_ignored("questionnaires/customers.md")
    # renamed after a docx export -- the case a `questionnaire*.md` glob
    # would silently miss, since it keeps neither the prefix nor the
    # extension (R1.3's actual motivating example).
    assert _check_ignored("questionnaires/customers-answers.docx")
    # a --out-dir subdirectory (T2's own --out-dir flag) -- still inside
    # the gitignored tree, no extra rule needed.
    assert _check_ignored("questionnaires/store-ops/customers.md")


def test_gitignore_does_not_ignore_generate_questionnaire_py_falsification():
    """Falsification of NC-6: the identical check-ignore call against a real
    tracked file must FAIL -- proving the assertions above test real
    ignoredness, not that `git check-ignore` trivially returns 0 for any
    path handed to it."""
    assert not _check_ignored("generate_questionnaire.py")


def test_gitignore_directory_rule_would_have_missed_the_docx_case_under_the_old_glob():
    """Documents (mechanically, not just in prose) why the directory beat
    the glob the plan originally specced (Sec 2.3), superseded by R1.3.
    fnmatch is the right stand-in for a gitignore glob's matching logic on
    a single filename component -- both are shell-glob semantics, and
    `questionnaire*.md` has no directory separator so it matches purely on
    basename, which is exactly the property being tested here."""
    old_glob = "questionnaire*.md"
    assert fnmatch.fnmatch("questionnaire.md", old_glob)  # the case the plan first specced
    assert not fnmatch.fnmatch("customers-answers.docx", old_glob)  # the case that slips through
    # ...whereas the actual `questionnaires/` directory rule, verified above,
    # catches the very same renamed file every time.


# --- honest baseline: the tracked, seeded routing file against real entities


def test_seeded_routing_renders_the_two_seeded_items_with_zero_stale():
    """Same style as test_real_entities_have_exactly_the_one_deliberate_
    coverage_gap: rendering the TRACKED (committed, seeded) routing file
    against the real entities right now produces exactly the two genuinely
    routed jaffle_shop items and nothing stale. This is meant to fail
    loudly later if someone edits stg_stores' grain or the
    stg_orders->stg_stores relationship without re-routing -- that's the
    correct alarm, not a bug to prevent (NC-4's whole point one level up)."""
    entities, all_review = _real_entities_and_review()
    routing = load_routing()  # the real, tracked questionnaire_routing.json
    renderable, stale = build_questionnaire_items(all_review, entities, routing)

    assert stale == []
    assert {item["key"] for item in renderable} == {
        "stg_stores:grain",
        "stg_orders:relationship:stg_stores",
    }

    # must actually render without raising -- the honest end-to-end claim,
    # not just that the join produced the right keys.
    by_entity = {}
    for item in renderable:
        by_entity.setdefault(item["entity_name"], []).append(item)
    for entity_name, items in by_entity.items():
        render_markdown(entity_name, items, [], generated_at="2026-08-26")


# ============================================================================
# M1 T6 -- status model (review_signoffs.status_of / entity_status_rollup)
# ============================================================================
#
# status_of/entity_status_rollup live in review_signoffs.py, not here --
# see the plan's R1.4/R2.1: routing is passed in as a plain dict, so that
# module never needs to read questionnaire_routing.json itself and stays
# one of the four generic, portable files. Both surfaces that display a
# status (this file's `list` and validate_grounding.py's per-entity block)
# import the SAME two functions from there; the identity test at the
# bottom of this section is the guard against a copy silently drifting
# from the original -- the exact bug
# test_validate_metrics_reuses_the_same_function_not_a_copy already exists
# to catch one layer down.


def _status_item(key="widgets:grain", claim="one row per widget"):
    return {"key": key, "text": claim, "text_hash": text_hash(claim)}


def test_status_of_is_unreviewed_with_no_signoff_and_no_routing():
    item = _status_item()
    assert status_of(item, signoffs={}, routing={}) == "unreviewed"


def test_status_of_is_routed_when_a_routing_entry_matches_the_current_hash():
    """The state T6 introduces -- routed, but not yet signed."""
    item = _status_item()
    routing = {item["key"]: _routing_record(item["text_hash"])}
    assert status_of(item, signoffs={}, routing=routing) == "routed"


def test_status_of_signing_a_routed_item_flips_it_to_signed_falsification():
    """Negative control from the dispatch: a routed item must NOT be
    reported as signed. Falsification -- sign the exact same item and the
    state must flip to 'signed', proving 'routed' isn't just this
    function's default return regardless of signoff state."""
    item = _status_item()
    routing = {item["key"]: _routing_record(item["text_hash"])}
    assert status_of(item, signoffs={}, routing=routing) == "routed"

    signoffs = {item["key"]: {"text_hash": item["text_hash"]}}
    assert status_of(item, signoffs=signoffs, routing=routing) == "signed"


def test_status_of_reports_routing_stale_when_recorded_hash_differs_from_current():
    item = _status_item()
    stale_routing = {item["key"]: _routing_record(text_hash("an older, since-changed claim"))}
    assert status_of(item, signoffs={}, routing=stale_routing) == "routing-stale"


def test_status_of_matching_hash_reports_routed_not_stale_falsification():
    """Falsification of the routing-stale test above: a matching hash must
    report 'routed' -- proving the stale check isn't hardcoded to fire
    whenever a routing record exists at all."""
    item = _status_item()
    routing = {item["key"]: _routing_record(item["text_hash"])}
    assert status_of(item, signoffs={}, routing=routing) == "routed"


def test_entity_status_rollup_counts_the_four_states_and_sums_to_total():
    items = [_status_item(f"{name}:grain", f"one row per {name}") for name in ("a", "b", "c", "d")]
    signoffs = {items[0]["key"]: {"text_hash": items[0]["text_hash"]}}  # a -> signed
    routing = {
        items[1]["key"]: _routing_record(items[1]["text_hash"]),  # b -> routed
        items[2]["key"]: _routing_record(text_hash("stale")),     # c -> routing-stale
        # d has no routing record -> unreviewed
    }
    rollup = entity_status_rollup(items, signoffs, routing)
    assert rollup == {"signed": 1, "routed": 1, "routing-stale": 1, "unreviewed": 1, "total": 4}


def test_entity_status_rollup_never_fetches_review_items_itself():
    """R2.4's blocking constraint, made mechanical: an empty input list must
    return all zeros -- proving the rollup only ever counts what it was
    handed, never reaching for the real entity graph or
    structural_facts.json behind the caller's back."""
    rollup = entity_status_rollup([], signoffs={}, routing={})
    assert rollup == {"signed": 0, "routed": 0, "routing-stale": 0, "unreviewed": 0, "total": 0}


def test_entity_status_rollup_counts_sum_to_total_for_real_entities_current_routing():
    """Honest baseline, this repo's own style (mirrors
    test_real_entities_review_items_are_pending_with_no_signoffs_file and
    T3's test_seeded_routing_renders_the_two_seeded_items_with_zero_stale):
    against the REAL entities, the REAL tracked questionnaire_routing.json,
    and the real (currently absent) review_signoffs.json, the rollup
    should report exactly the two items T3 routed as "routed", zero
    "signed" (no signoffs file exists yet), zero "routing-stale", and
    everything else "unreviewed". This is meant to fail loudly -- the
    correct alarm, not a bug to prevent -- if stg_stores' grain or the
    stg_orders->stg_stores relationship is ever edited without
    re-routing, or if something gets signed off without this expectation
    being updated alongside it."""
    _, all_review = _real_entities_and_review()
    routing = load_routing()      # the real, tracked questionnaire_routing.json
    signoffs = load_signoffs()    # the real (currently absent) review_signoffs.json

    rollup = entity_status_rollup(all_review, signoffs, routing)

    assert rollup["total"] == len(all_review)
    assert rollup["signed"] == 0
    assert rollup["routing-stale"] == 0
    assert rollup["routed"] == 2
    assert rollup["unreviewed"] == len(all_review) - 2
    assert (rollup["signed"] + rollup["routed"] + rollup["routing-stale"]
            + rollup["unreviewed"]) == rollup["total"]


def test_status_functions_are_single_sourced_not_copies():
    """Same guard as test_validate_metrics_reuses_the_same_function_not_a_copy,
    for the same reason: two surfaces showing the same status must not be
    able to drift apart. Identity, not equality -- a copy that happens to
    agree today would still fail this."""
    import review_signoffs
    import validate_grounding
    import generate_questionnaire

    assert validate_grounding.status_of is review_signoffs.status_of
    assert generate_questionnaire.status_of is review_signoffs.status_of


# --- T6-b: both surfaces actually show the rollup, not just import it ------


def test_generate_questionnaire_list_prints_the_status_rollup(capsys, monkeypatch):
    import sys

    import generate_questionnaire

    monkeypatch.setattr(sys, "argv", ["generate_questionnaire.py", "list"])
    generate_questionnaire.main()
    out = capsys.readouterr().out

    _, all_review = _real_entities_and_review()
    routing = load_routing()
    signoffs = load_signoffs()
    rollup = entity_status_rollup(all_review, signoffs, routing)
    assert (
        f"STATUS ROLLUP: {rollup['signed']} signed / {rollup['routed']} routed / "
        f"{rollup['routing-stale']} routing-stale / {rollup['unreviewed']} unreviewed "
        f"({rollup['total']} total)"
    ) in out


def test_validate_grounding_status_line_reflects_the_real_rollup_for_stg_stores(capsys):
    """validate_grounding.py's per-entity block gets one added display-only
    line (T6-b). stg_stores has exactly one review item (its grain -- no
    relationships, every column source=manifest) and it is one of the two
    items T3 routed, so its rollup is unambiguous: 0 signed, 1 routed,
    0 routing-stale, 0 unreviewed. Display-only: this test asserts nothing
    about the exit code (see test_ci_exit_severity.py for that, unchanged
    by this task)."""
    import validate_grounding

    with pytest.raises(SystemExit):
        validate_grounding.main()
    out = capsys.readouterr().out

    assert "=== stg_stores ===" in out
    stg_stores_block = out.split("=== stg_stores ===")[1].split("=== ")[0]
    assert "STATUS: 0 signed / 1 routed / 0 routing-stale / 0 unreviewed" in stg_stores_block


def test_validate_grounding_status_line_does_not_touch_compute_exit_code():
    """Blocking constraint, made mechanical rather than just argued in the
    report: this task adds no parameter to compute_exit_code and no new
    call site that could change its result -- its signature is exactly
    what test_ci_exit_severity.py already pins."""
    import inspect

    from validate_grounding import compute_exit_code

    assert list(inspect.signature(compute_exit_code).parameters) == ["all_failures", "all_unsigned"]
