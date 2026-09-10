# ADR-001: Citation-grounded ontology generation, not free-form generation

**Status**: Accepted (retroactive — written 2026-08-25 when WoW was
formally adopted; the decision itself was made and built 2026-08-17
through 2026-08-25, informally, before this ADR existed. See "Why
retroactive" at the end.)

## Context

Ontology generation is one of the places LLMs most reliably hallucinate:
asked to describe a data model, they produce plausible-sounding grain
statements, column meanings, and relationships that aren't actually true
of the project in front of them, because nothing forces every claim to
be checked against a real fact. The PyData Amsterdam 2026 talk needs a
live-demoable pipeline that proves a narrower, falsifiable claim instead
of just asserting "AI can draft your data model" and hoping it's true.

## Decision

Every claim in a generated ontology carries a citation. A validator
mechanically checks citations that can be checked (column exists,
description matches the manifest exactly, FK relationship is proven by
a `relationships` test) and flags — never silently trusts — the ones
that require human judgment (grain, cardinality reasoning, business
meaning). The claim is narrow on purpose: not "the ontology is
guaranteed correct," but "wrong claims fail loud instead of reading
plausibly."

Built as a five-stage pipeline, each stage independently testable:

1. **Extract** (`scripts/extract_structural_facts.py`) — pull structural
   facts from `manifest.json`, zero LLM cost, deterministic.
2. **Draft** (`generate_<entity>.py`, one per entity) — an agent proposes
   `Entity`/`ColumnFact`/`Relationship` claims, each with a `source`
   citation.
3. **Validate** (`validate_grounding.py`) — mechanically checks every
   citable claim; splits into `failures` (auto-reject) and `review`
   (flag for a human, never auto-pass).
4. **Signoff** (`review_signoffs.py`) — a review item only clears once a
   specific, authorized human deliberately signs it (see ADR-002 for
   the authorization mechanism, added 2026-08-25).
5. **Export** (`generate_owl.py` + `validate_shacl.py`) — the validated
   ontology translates to real OWL/Turtle, checked against SHACL shapes
   — a standards-based structural layer, additive to (not replacing)
   step 3's citation-correctness check.

Proven on jaffle_shop (10 entities, 3 derived metrics) and cross-tested
against a real production dbt project (private, not named in this
repo) — found and fixed one real portability bug (ref() quote-style
parsing) that jaffle_shop's clean manifest could never have surfaced.

## Alternatives considered

- **Free-form LLM ontology generation, reviewed after the fact** —
  rejected: review-after-the-fact is exactly the failure mode (a
  plausible-sounding wrong answer is hard to catch by inspection; this
  is the whole reason the talk exists).
- **A third-party ontology-generation tool** (OntoCast, open-ontologies,
  OntoBricks) — rejected for the live demo specifically: all sit at
  150-230 GitHub stars, none installed or run by us before deciding,
  too risky to depend on live on stage. Referenced as color commentary,
  not depended on.
- **SHACL/OWL as the primary validation mechanism from the start** —
  rejected for v1: SHACL validates graph structure, it cannot validate
  that a claim's text matches the dbt manifest, which is the actual
  hallucination risk. Built the citation-grounding layer first, added
  OWL/SHACL as an additive standards-compliance layer once that held
  (2026-08-25, same day as this ADR).

## Consequences

- Grain and cardinality reasoning are **permanently** human-review
  items, not a gap future tooling closes — this is the actual boundary
  of what's mechanically checkable, documented in `AGENTS.md`'s "Honest
  gaps" section so it doesn't get oversold on stage.
- The four core files (`scripts/extract_structural_facts.py`,
  `schema.py`, `validate_grounding.py`, `review_signoffs.py`) are
  explicitly generic — zero jaffle_shop-specific code, meant to travel
  to any dbt project as-is (proven, not just claimed, per the
  cross-project test above).
- Everything downstream (the authorized-signer mechanism, ADR-002; the
  OWL/SHACL export) had to preserve this ADR's core discipline: no
  claim without a citation, no automatic trust, flag rather than guess.

## Why retroactive

WoW was adopted 2026-08-25, after this decision was already built and
proven. Writing it up now rather than back-dating fake history: the
actual commits (`feb74a7` through `f92444d` on `spike/ontology-extraction`)
are the real record of how this was built, in what order, including two
real bugs found and fixed along the way. This ADR captures the decision
that record represents, for a session that wasn't there to read the
commits directly.
