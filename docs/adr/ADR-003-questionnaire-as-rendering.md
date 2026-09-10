# ADR-003: The questionnaire is a rendering, not a new representation

**Status**: Accepted (retroactive — written 2026-08-26, after M1's PLAN
phase produced three revisions and all six EXECUTE tasks landed on
`spike/ontology-extraction`. See "Why retroactive" at the end.)

## Context

`validate_grounding.py` already splits every ontology claim it can't
mechanically check into `review` items — `{"key", "text", "text_hash"}`
(`validate_grounding.py:30`) — and `review_signoffs.is_signed_off()`
(`review_signoffs.py:52`) ties a signoff to a hash of exactly that
`text`. That string is written for an engineer reading console output:

```
customers -> orders (cardinality='one-to-many'): "..." -- FK existence is
proven, but this reasoning requires reading the SQL. Citation: ...
```

M1 needed to get some of these claims in front of a domain expert who
has never seen `structural_facts.json` and should never have to. The
naive move — render `item["text"]` into a document — would look
finished and would defeat the entire pipeline's thesis: ADR-001's
discipline is "no claim without a citation, no automatic trust, flag
rather than guess," and shipping raw internal jargon labelled as a
"question" is itself a kind of unflagged, untrustworthy claim about what
a human will understand.

M1's PLAN phase went through three revisions before EXECUTE (`docs/plans/
M1-questionnaire-generator-plan.md`), because Ricardo's answers to the
plan's open questions repeatedly corrected assumptions the original
proposal had made silently. This ADR records what was actually decided
and built across all three revisions and all six EXECUTE tasks (T0, T1,
T2, T3, T6, T4) — not the shape of the original, pre-revision proposal.

## Decision

### 1. The questionnaire renders the validated objects; it is never a new representation of a claim

`text` / `text_hash` (from `review_signoffs.review_key()` / `text_hash()`)
stay the canonical identity of a claim, untouched by M1. Changing them
would invalidate every existing signoff. `generate_questionnaire.py`'s
`_claim_and_source()` pulls the rendered claim and its citation straight
from the validated `Entity` / `ColumnFact` / `Relationship` objects —
**never** from a review item's `item["text"]` — because those objects
already carry business-meaningful prose by schema contract
(`schema.py`'s `Relationship.description` mandate is the concrete
example: "each order belongs to one customer," not just the raw FK).
`key` and `text_hash` still travel through every rendered question, as a
traceability token, but only as an identifier — never as the rendered
prose itself.

`build_questionnaire_items()` takes both the review items and the
entities as separate inputs specifically to keep this split visible in
the interface: the key/hash come from one, the prose from the other.
`test_render_contains_no_jargon_leak_against_real_entities` (NC-1) exists
to catch a shortcut back to `item["text"]` and fails loudly if that
shortcut is ever taken.

### 2. Routing is explicit input, never inferred

There is no classifier and no schema field distinguishing
"human-answerable" from "expert-only." A human decides, in the moment of
conversation, that a given review item needs to go to a specific person
in business language — that decision previously persisted nowhere.
`generate_questionnaire.route()` records it as given: `question` is a
plain string an agent drafts in conversation and passes straight through;
the module never generates, paraphrases, judges, or classifies it. This
mirrors ADR-001's own "no claim without a citation" discipline one level
up — a generated question would be exactly the kind of plausible-sounding
but unverified artifact this pipeline exists to avoid producing.

### 3. Routing is not authorization

`routed_by` is provenance only. It is deliberately **not**
authorization-checked against `AUTHORIZED_SIGNERS.md`
(`review_signoffs.verify_signer()`, ADR-002). Routing means "I don't
know, ask someone else" — the opposite of approving a claim. Applying
ADR-002's signer-authorization discipline to a request for help would be
gatekeeping the wrong thing. `generate_questionnaire.py`'s module
docstring states this explicitly, and the file imports nothing from
`AUTHORIZED_SIGNERS.md`'s verification path.

### 4. Confidentiality is enforced by a gitignored directory, not a filename pattern or a documented plea

The original design (§2.3 of the plan) specced a root-level
`questionnaire.md` with a `.gitignore` glob (`questionnaire*.md`). Once
the design moved to one file per entity (see §5 below), the glob's
weakness became visible: it only catches a file that keeps the
generator's own prefix and `.md` extension. A real filled artifact
routinely won't — it becomes `customers-answers.docx` after a
`md-to-docx` render, or `customers (comments).md`, or a screenshot
dropped next to it. Every one of those slips past a filename glob.

The corrected mechanism: `.gitignore` covers the whole `questionnaires/`
directory. A gitignored directory catches anything placed inside it,
regardless of what it is named or what format it's in.
`test_gitignore_covers_the_directory_not_just_the_generators_own_filename`
asserts `git check-ignore` succeeds for `questionnaires/customers.md`,
`questionnaires/customers-answers.docx`, and a `--out-dir` subdirectory
case — the `.docx` case is exactly what the old glob would have missed,
and `test_gitignore_directory_rule_would_have_missed_the_docx_case_under_the_old_glob`
pins that gap mechanically (via `fnmatch`) rather than leaving it as a
comment that can go stale. `questionnaire_routing.json` stays tracked —
it is an input, not a derived artifact, and it doubles as the worked
jaffle_shop routing example.

### 5. The traceability token is a visible reference line, not invisible metadata — verified against the real downstream parser, not assumed

The original design (§2.4) put the per-question traceability token in an
HTML comment: `<!-- item: customers:grain | claim-fingerprint: ... -->`,
chosen as "the cheap thing that makes M2 trivial." Before committing to
it, the actual downstream tool this document is meant to survive —
`md-to-docx.js`, a real hand-rolled Markdown parser reachable from this
session, not a `marked`/`remark`-based one — was read directly rather
than assumed compatible. It special-cases exactly three HTML comments
(`pagebreak`, `landscape`, `portrait`); everything else falls through to
a plain paragraph.

That reading surfaced two independent failures in the original design,
both real defects, not style preferences:

1. **It renders as visible literal junk.** Every question in every Word
   render would carry a line of raw comment syntax — in the one document
   whose entire design brief was "no jargon."
2. **It does not survive the round trip.** An HTML comment does not
   survive a docx export and a domain expert answering in Word or
   Confluence. So even if it were hidden, the answer would come back with
   no link to the review item it answers — breaking the exact "map an
   answer back to what it grounds" step M2 is meant to build on.

Corrected to a visible, deliberately quiet line as the last line of each
question block:

```
*Reference: customers:grain · 3f9a2b1c8d7e6f50 — please leave this line as it is.*
```

Real text survives Word, Confluence, copy-paste, and a screenshot-and-
retype. `·` replaces `|` because a pipe risks tripping the parser's table
detector. Being visible is now a feature, not a leak: a reader who
deletes the line is making a visible edit, not silently destroying
invisible metadata. NC-1's banned-token check is scoped to exclude this
line (it is a key and a hash, not jargon prose), and
`test_reference_line_present_for_every_rendered_question` pins the
opposite failure mode — the line must never be silently dropped either.

This same verification pass also found NC-1's original banned-token list
(`structural_facts.json` among them) fails against this project's real
data: several real `relationship` items cite their source as
`"structural_facts.json relationships[]: ..."` verbatim, which is
correctly-rendered citation text, not a leak. NC-1 was corrected to scope
its check to the claim/question prose only, excluding both the reference
line and the citation value — the same "verified against real data,
found the original design didn't survive contact with it" pattern as the
token correction above, on a smaller scale.

### 6. Role is a field on the question block, not a section heading

The original per-entity design (Revision 1) put each owner role as a
`## For: <Role>` heading inside the entity file. Reading `md-to-docx.js`'s
heading support (`#{1,4}` only — H1 through H4) showed this breaks
combined-mode: `# title -> ## entity -> ### For: Role -> #### Q1` is
exactly four levels with zero headroom, and — the more important problem
— it makes the question block **structurally different** between a
per-entity file and a combined one, which would force M2 to parse two
shapes for the same kind of thing.

Corrected: role moved inside the question block as a field
(`**Who this is for:** <Role>`), and questions are always `### Q{n}` in
both formats. `_render_question_block()` is the single function both
`render_markdown()` (per-entity) and `render_combined()` (`--combine`)
call to produce a question block — the byte-identical guarantee is
structural, not a claim, and is regression-tested directly
(`test_combine_question_block_is_byte_identical_to_per_entity_rendering`).
This is also what makes `--combine` a pure concatenation rather than a
second renderer that could drift from the first.

### 7. Exclusion is a second axis, never a fifth status state

Ricardo asked whether `validate_grounding.py` should distinguish "routed,
awaiting an expert" from "nobody has looked at this," and separately
raised a future health-score's need to exclude certain items (e.g. the
pre-existing metric-signoff bug's items) from a measurement without
hiding that they're unreviewed. The plan's Revision 2 (R2.4) concluded
these are two different questions and must stay on two different axes:

- **Status** answers "where is this claim in the human-review lifecycle?"
  — `review_signoffs.status_of()` returns exactly one of `"unreviewed"`,
  `"routed"`, `"routing-stale"`, or `"signed"`, computed from `signoffs`
  and `routing` (the T1 store), with `"routing-stale"` a degraded
  `"routed"` rather than a fifth branch.
- **Exclusion** answers "should this item count toward a measurement?" —
  a deliberately different, and deliberately unbuilt, question.

Folding exclusion into `status_of()` as a fifth return value would
collapse two independent facts into one symbol: an item can be both
`"unreviewed"` and excluded at once, and overwriting its status to
`"excluded"` would discard the first fact and leave no path back to it
once the excluding reason no longer applies. `status_of()`'s signature is
exactly `(item, signoffs, routing)`, with no `exclusions` parameter, and
`entity_status_rollup()` takes `review_items` as a parameter it never
fetches itself — both held as explicit, reviewer-checked constraints
(T6's report confirms both by direct inspection and by test). A future
health-score milestone applies exclusion as an input filter composed at
the call site — `entity_status_rollup(scored, signoffs, routing)`, where
`scored` is pre-filtered — never as a change to either function's
signature or return shape.

## Alternatives considered

- **Routing folded into `review_signoffs.json` as a third state** — one
  file, one mechanism, genuinely tempting. Rejected because ADR-002 is
  emphatic that file is a *signature* record; folding an unsigned routing
  note into it muddies "this file records who approved what."
- **An LLM drafting the question inside the generator** — rejected. The
  entire point of `question` is that it is a human input, never
  generated — the same "no claim without a citation" discipline this
  pipeline applies to ontology claims, applied one level up to the
  questions asking about them. A generated question is exactly the kind
  of plausible-sounding, unverified text ADR-001 exists to prevent.
- **Automatic classification of review items into human-answerable vs.
  expert-only** — rejected per the design note's explicit position (and
  Ricardo's own confirmation): the human decides in the moment which
  branch a review item takes. No classifier was designed or built, and
  none should be added later without revisiting this decision.
- **A single combined document, or one file per role, as the default
  grain** — rejected in favor of one file per entity (Revision 1, R1.3).
  A combined document turns provenance into a search problem for M2's
  future write stage; a per-role file bakes a person's organizational
  position into a filename that outlives it, and collides with this
  repo's own de-naming discipline. The entity is this repo's grain
  everywhere else already (`review_key()`, source file names, the
  validator's console blocks, the OWL export) — anything else would make
  the questionnaire the one artifact out of alignment with the rest of
  the pipeline. `--combine` was added later (Revision 3) as an explicit,
  separate flag for the "send one document" case, built as a
  concatenation of the same per-entity blocks rather than a competing
  default.

## Consequences

**What this locks in for M2.** Mapping an answer back to what it grounds
becomes a two-lookup chain with no searching, on both halves of the
design:

```
questionnaires/customers.md   ->  entity "customers"  ->  generate_customers_entity.py
      (file name)                  (review_key() prefix)      (suggest_fixes._source_file())

Reference: customers:grain · 3f9a2b1c8d7e6f50   ->   review key   ->   the exact field to edit
      (per-question reference line)                  (already canonical)   (kind = grain|relationship|column-source)
```

Both halves reuse mappings that already existed in the repo
(`suggest_fixes.ENTITY_SOURCE_FILE` / `_source_file()`, and
`review_key()`'s own `kind`/`target` encoding) rather than duplicating
them — consistent with this repo's standing rule against a second copy
of a decision drifting from the first
(`test_ci_exit_severity.py`'s own identity-test precedent, which T6's
`test_status_functions_are_single_sourced_not_copies` repeats for the
status model).

**What this deliberately leaves open.** M1 builds only the interface M2
will consume — `key` + `text_hash` on every rendered question, and
`is_routing_stale()` to detect a claim that changed after routing. M2's
actual capture/summarize/extract/validate/write mechanism is **not**
designed here: whether the answer comes back as a filled Markdown file,
a transcript, or a chat reply is explicitly still open, and no
round-trip parser was built in M1 on the bet that one might not be
needed. Likewise, a health-score milestone (Part B of Ricardo's original
question) is deferred entirely — this ADR's §7 exists only to make sure
that milestone can be built as a pure addition (a new store, two new
functions, a filter composed at the call site) rather than a rework of
anything M1 shipped.

**What this costs at the confidentiality boundary.** The gitignored
`questionnaires/` directory only protects the repository — it stops
working the moment a rendered file is emailed or pasted into SharePoint,
which `--combine` was built specifically to support. The one mitigation
that survives that boundary is written onto the document itself: the
combined output's provenance header carries a handling note in prose
("store it accordingly; it is deliberately not kept in the source code
repository"), because the mechanical gitignore control has no reach past
the repo's edge.

## Why retroactive

M1's plan document went through three revisions between its initial
proposal and EXECUTE dispatch, each correcting an assumption the
previous version had made silently — the per-entity grain, the
gitignored directory instead of a glob, the visible reference line
instead of an HTML comment, and the exclusion-as-a-second-axis reasoning
were all conclusions reached *during* planning and execution, not known
up front. Writing this ADR after all six EXECUTE tasks landed, rather
than alongside the original proposal, means it records what was actually
decided and verified — including two corrections (§5, §6) found only by
reading a real downstream parser instead of assuming compatibility —
rather than a design that looked complete on paper and was later proven
wrong in three separate places. The full history, including the
questions that were still open at each stage and how they were answered,
is preserved verbatim in `docs/plans/M1-questionnaire-generator-plan.md`
for anyone who wants the blow-by-blow rather than the settled decision.
