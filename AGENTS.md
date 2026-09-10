# AGENTS.md — Grounded Ontology Generation Tutorial

You are an AI coding agent (Claude Code, Codex, Cursor, or similar) helping
someone work through this tutorial. This file is your instructions — it is
deliberately agent-agnostic, so it works the same regardless of which tool
is reading it.

## What this tutorial proves

Ontology generation is one of the places LLMs most reliably hallucinate:
asked to describe a data model, they produce plausible-sounding grain
statements, column meanings, and relationships that are not actually true
of the project in front of them — because nothing forces every claim to be
checked against a real fact.

This repo proves a narrower, falsifiable claim instead: **if every claim in
a generated ontology carries a citation, and a validator mechanically checks
citations that can be checked while flagging (never silently trusting) the
ones that can't, hallucination becomes catchable rather than invisible.**
It is not "the ontology is guaranteed correct" — it is "wrong claims fail
loud instead of reading plausibly."

## What's generic vs. project-specific

This matters if you're taking this home to your own dbt project — these
five files have **zero jaffle_shop-specific code** and should work as-is
against any dbt project's `manifest.json`:

- `scripts/extract_structural_facts.py`
- `scripts/schema.py`
- `scripts/validate_grounding.py`
- `scripts/review_signoffs.py`
- `scripts/generate_questionnaire.py`

The only project-specific part is `generate_<entity>.py` — one small file
per entity, written by you (the agent) reading that project's actual SQL.
That's the part you redo per project. Everything else is the tool.

Same relationship, one level down: `scripts/generate_questionnaire.py` is generic,
but the routing decisions it records (which review item, sent to which
role, in what words) are this project's own — kept in
`questionnaire_routing.json`, the project-specific counterpart to a
generic tool, exactly like `structural_facts.json` is
`extract_structural_facts.py`'s project-specific output and
`review_signoffs.json` is `scripts/review_signoffs.py`'s.

## Prerequisites

- A dbt project that builds — you need `target/manifest.json` to exist
  (`dbt run` or `dbt compile` produces it). This repo ships jaffle_shop
  pre-wired for that; swap in your own project's `dbt_project.yml` /
  `profiles.yml` when you take this elsewhere.
- Python 3.11+, with `pydantic` and `pytest` installed (`uv sync` or
  `pip install -r requirements.txt` if one exists in your fork).
- You, the agent, with read access to the repo and a shell.
- A human who can answer "does this claim actually check out" — this
  tutorial does NOT remove that person, see Step 6.

## The runbook

**Step 0 — orient.** Read this file and `scripts/schema.py` before generating
anything. `scripts/schema.py`'s field docstrings encode the actual rules you must
follow in Step 4 — they are not just documentation, they're the contract.

**Step 1 — build the dbt project**, if `target/manifest.json` doesn't
already exist: `dbt run && dbt docs generate` (or `dbt compile` is enough
if you don't need the catalog).

**Step 2 — extract structural facts** (zero LLM cost, pure Python):
```
python3 scripts/extract_structural_facts.py
```
Produces `structural_facts.json` — every column's description exactly as
it exists in the manifest, plus `unique`/`not_null` flags and the FK graph
from `relationships` tests. This is the ONLY source of truth the validator
in Step 5 checks against. If a claim isn't traceable to this file (or to a
real line of SQL you can point at), it doesn't get to claim `source="manifest"`.

**Step 3 — pick one model and generate its Entity.** Create
`generate_<model>_entity.py` following the pattern of
`scripts/generate_customers_entity.py` / `scripts/generate_orders_entity.py`. Rules,
non-negotiable:
- Every `ColumnFact.description` with `source="manifest"` must be copied
  **verbatim** from `structural_facts.json` — not paraphrased, not
  "cleaned up." A paraphrase that drops a detail (a unit, a qualifier) is
  exactly the failure mode this whole exercise exists to catch.
- If a column has no manifest description, you may still document it, but
  `source` must say so honestly (e.g. a note that it's inferred from SQL)
  — never mark an invented description as `source="manifest"`.
- `grain` and every `Relationship.cardinality`/`description` must cite the
  actual SQL logic that proves it (a `GROUP BY`, a `JOIN` cardinality) —
  never asserted from the model or column name alone.
- Only declare a `Relationship` if a matching entry actually exists in
  `structural_facts.json`'s `relationships` list. If the FK is real in the
  data but no `relationships` test documents it, that's a genuine gap in
  the project's test coverage — say so in the entity's `summary`, don't
  paper over it with an uncited relationship.

**Step 4 — validate:**
```
python3 scripts/validate_grounding.py
```
Two outcomes matter differently:
- **FAILURES** — mechanically disproven. Fix the entity; there is no
  legitimate way around a failure.
- **NEEDS SIGNOFF** — not mechanically checkable (grain, cardinality
  reasoning). This is expected, not a bug — go to Step 5.

**Step 5 — human signoff, conversational, forced acknowledgment, never
agent-authorized.** A review item only clears once a specific,
authorized person deliberately signs it — the agent proposes, it never
approves on anyone's behalf, and there's a real mechanical gate behind
that, not just a polite instruction:

1. Present each pending item one at a time, in plain language, with its
   citation — not a raw dump of `scripts/validate_grounding.py`'s output.
2. Ask directly: does this look right?
   - **If they don't know** — don't guess, and don't force an answer on
     the spot. Ask directly who would (a role, not necessarily a name)
     and what the actual question is. That's a real gap to go find an
     answer for, not something to resolve in this session by asserting
     a plausible-sounding claim. See Step 5a for what to do with that
     role and question — it's a real mechanism now, not a dead end.
   - **If yes** — do NOT sign it yourself. Ask them to type their full
     name and role exactly, e.g. `Ricardo Granados, Analytics Engineer`
     — a deliberate typed act, not a "yes" in chat, same idea as a
     license agreement's "I agree" button that won't light up until
     you've actually scrolled through it. Treat their literal next
     message as the only valid answer to that specific question.
3. Run `python3 scripts/review_signoffs.py verify "<what they typed>"` first —
   check it against `AUTHORIZED_SIGNERS.md` (see that file for what this
   is and isn't a security boundary). Then run
   `python3 scripts/review_signoffs.py sign <key> "<what they typed>" "<note>"
   "<your own model name>"` — yes, even if unauthorized. **An
   unauthorized attempt still gets recorded and still gets pushed for
   review** (see Step 5b) — it is not silently discarded, and it is not
   silently accepted either.
4. **You never run `git commit` for this.** Stage the change
   (`git add review_signoffs.json`) and hand control back explicitly:
   "staged, here's the diff, your call to commit." The human's own
   signed commit — using a key you do not have — is the actual
   signature. Nothing you do locally can substitute for it.

The signoff record carries both a human signature and an agent
attestation, and they are not the same kind of thing: `reviewer`/
`signer_role`/`signer_authorized` is what the human typed, checked
against `AUTHORIZED_SIGNERS.md` (a soft, local check); `agent_attestation`
(model name, timestamp) is your own honest provenance record, not a
signature — pass your real model identity, never a placeholder. The
signoff is tied to a hash of the item's exact text — if the claim's
wording changes later, the old signoff stops applying automatically.

**Step 5a — routing: recording "I don't know, ask someone else."** When
Step 5's "if they don't know" branch fires, the role and the question
don't just stay in the conversation — record them, so they survive
compaction and a new session:

```
python3 scripts/generate_questionnaire.py route <key> "<Owner Role>" "<the question, in business terms>" ["<your name, role>"]
```

This is deliberately **not** authorization the way `sign` is — `route`
has no check against `AUTHORIZED_SIGNERS.md`. Routing means "ask someone
else," the opposite of approving a claim, so gatekeeping who's allowed to
ask a question would be backwards. It does keep `sign`'s other safety
property: `route` refuses to write anything for a key that isn't a real,
current review item, with the same `"No current review item with key
... -- run 'list' first"` message — a typo in the key fails loud instead
of silently creating an orphan routing record.

Once one or more items are routed, produce an actual document to hand to
that person:

```
python3 scripts/generate_questionnaire.py render [--owner "<Role>"] [--out-dir <dir>] [--combine]
```

- By default this writes one Markdown file per entity
  (`questionnaires/<entity>.md`), containing only that entity's *routed*
  questions — never the whole review backlog, and never a question whose
  underlying claim changed after it was routed (that surfaces in its own
  "not included, needs re-routing" section instead, so nobody signs off
  on a question that no longer matches what the model actually claims).
- `--owner "<Role>"` filters to just that person's questions, still one
  file per entity — combine with `--out-dir` when a specific role's
  questions need to go to just them, not everyone's.
- `--combine` additionally writes one `combined.md` concatenating the
  (filtered) per-entity files under a single provenance header (repo,
  branch, commit, what's covered, who to return it to) — the form meant
  for actually being sent (email, Confluence, Word). The per-entity files
  remain the authored, traceable form either way.
- Every rendered question carries its citation ("Where that came from")
  and ends with a quiet reference line
  (`*Reference: <key> · <hash> — please leave this line as it is.*`) —
  that line is what lets a returned answer be matched back to the exact
  claim it grounds. Leave it in place when an answer comes back.

**Confidentiality split, mechanical, not just documented**: the whole
`questionnaires/` directory is gitignored — not a filename glob, so a
filled-in questionnaire is still caught even after it's been renamed or
re-exported to `.docx`. `questionnaire_routing.json` (the routing
record — key, role, question, no answers) stays tracked; it's an input,
and in this repo it doubles as the worked jaffle_shop example.

**Status, at a glance**: every review item is in exactly one of four
states, shown both by `scripts/generate_questionnaire.py list`'s `STATUS ROLLUP`
line and by `scripts/validate_grounding.py`'s per-entity `STATUS:` line:

- `unreviewed` — nobody has looked at it yet.
- `routed` — sent to a role via the mechanism above, awaiting an answer.
- `routing-stale` — was routed, but the claim's text changed since, so
  the recorded question no longer matches what's actually being
  claimed — flagged, never silently carried forward, needs re-routing.
- `signed` — a human has explicitly signed off (Step 5).

**Step 5b — what happens next depends on authorization**, enforced by
GitHub, not by you: push the branch and open a PR either way. Branch
protection (require PRs, require signed commits) means nothing reaches
`main` without going through this regardless of what anyone claims
locally. If the typed signer wasn't authorized, say so plainly in the PR
— it's still visible and reviewable, just can't merge without someone
who is. See `AUTHORIZED_SIGNERS.md`'s "In a real setting" section and
`CODEOWNERS` for how this gets real multi-person teeth outside a
solo-maintainer demo repo.

**Step 6 — repeat** for more models. `scripts/test_grounding.py` has a running
regression suite (`python3 -m pytest scripts/test_grounding.py -v`) including
negative controls that prove the validator actually catches bad claims,
not just passes good ones — worth reading before you trust it.

**Step 7 (stretch)** — once several entities are grounded, try deriving a
business metric from the ontology (e.g. "customer lifetime value" from
`customers.lifetime_spend`) and hold the same standard: cite which
entities/columns it's built from, run it past the same validation
discipline rather than asserting it freely.

**Step 8 — the hard mode: `stg_kiosk_sales`.** Every model up to this
point already had good manifest descriptions, which is the easy case.
This one doesn't. Story: jaffle_shop piloted a kiosk channel at the
Downtown store, wired up fast by whoever was free, never reconciled with
the rest of the model. Two real traps, both intentional:
- `order_total` here is a column name it shares with the `orders` mart —
  but it's a DAILY total across all kiosk sales that day, not one
  order's total. Same name, completely different grain. Copying the
  `orders.order_total` description onto this column, or assuming it
  means the same thing, is exactly the mistake this whole discipline
  exists to catch.
- Its schema.yml description ("The order total") is tautological —
  present, traceable to the manifest, and says nothing. `source="manifest"`
  passing validation is not the same as the documentation being any good.
- `store_id` is a real foreign key to `stg_stores`, but no `relationships`
  test declares it — same undocumented-real-relationship pattern already
  present in `order_items`/`products`. Don't invent a `Relationship`
  object for it; that's exactly what `scripts/validate_grounding.py` would (and
  should) fail on.

Run `python3 scripts/validate_coverage.py` first — it'll show this model as a
live, unresolved gap. Ground it yourself, following Step 3's rules
exactly. This is deliberately the one piece of the tutorial nobody has
pre-solved.

**Step 9 — export to OWL, validate with SHACL.** Once `scripts/validate_grounding.py`
passes clean (all mechanical failures fixed, every review item signed
off), run `python3 scripts/generate_owl.py`. It translates the validated Pydantic
ontology into a real OWL ontology (`ontology.ttl`) — every entity becomes
an `owl:Class`, every column an `owl:DatatypeProperty`, every relationship
an `owl:ObjectProperty` (with `owl:FunctionalProperty`/
`owl:InverseFunctionalProperty` encoding many-to-one/one-to-one — real OWL
semantics, not just a text label), and every citation carried over as an
annotation so "no claim without a source" survives the translation. This
is the piece that's genuinely reusable outside this exercise: open
`ontology.ttl` in Protege or GraphDB, no Python or jaffle_shop required.

Then run `python3 scripts/validate_shacl.py`, which checks `ontology.ttl` against
`shapes.ttl` — a standards-based structural layer (every class has a
grain, every property has a source, cardinality values are one of the
three allowed) that matters most once the ontology leaves Python, e.g.
if someone hand-edits the `.ttl` directly. It does NOT replace
`scripts/validate_grounding.py`: SHACL can prove the graph is well-formed, it
cannot prove a claim's text actually matches the dbt manifest — that
stays this pipeline's own job. `scripts/test_owl.py` has the same negative-control
discipline as `scripts/test_grounding.py`, including a test that the exported
`FunctionalProperty` semantics are actually there, not just annotated.

## Honest gaps — don't oversell these on stage

- The OWL/SHACL layer (Step 9) validates *structure* (required fields
  present, cardinality values legal) — it does not re-check citation
  correctness against the dbt manifest. That mechanical check is still
  `scripts/validate_grounding.py`'s job alone; SHACL is additive, not a
  replacement.
- Grain and cardinality reasoning are permanently human-review items, not
  something any future tooling fully automates — that's not a gap to
  close, it's the actual boundary of what's mechanically checkable.
