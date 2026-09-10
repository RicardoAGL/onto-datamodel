"""Questionnaire routing store -- M1 T1.

M2's design note (`docs/plans/M1-questionnaire-generator-plan.md` Sec 1) is
emphatic that the questionnaire is a *rendering* of the already-validated
`Entity`/`ColumnFact`/`Relationship` objects, never a new representation --
`text`/`text_hash` (from `review_signoffs.review_key`/`text_hash`) stay the
canonical identity of a claim. This module adds the one thing that currently
persists nowhere: the human decision to route a review item to a specific
person, in business language, because nobody in this conversation can answer
it themselves.

Routing is explicit input, never inferred. There is no classifier here and
none should ever be added -- `question` is a plain string an agent drafts in
conversation with a human and passes straight through; this module never
generates, paraphrases, or judges it.

Routing is also deliberately NOT authorization-checked against
`AUTHORIZED_SIGNERS.md`. That file exists to gate who may *approve* a claim
(see `review_signoffs.verify_signer`, ADR-002). Routing means the opposite --
"I don't know, ask someone else" -- so applying the same authorization
discipline here would be gatekeeping a request for help, which is not what
it is.

Same JSON-file pattern as `review_signoffs.py` (`load_signoffs`/
`save_signoffs`/`is_signed_off`), deliberately not folded into that file:
`review_signoffs.json` is a *signature* record (ADR-002), and an unsigned
routing note does not belong inside it.

M1 T2 adds the renderer: `build_questionnaire_items` joins routing against
the CURRENT review items and the already-validated `Entity`/`ColumnFact`/
`Relationship` objects, and `render_markdown`/`render_combined` turn that
into Markdown. Per Sec 1, this is a *rendering* of those objects, never a
re-emission of a review item's own `text` -- `text`/`text_hash` stay the
claim's identity only, the prose always comes from the objects. The
traceability token on each question is a visible reference line, not an
HTML comment (verified against the real `md-to-docx.js` parser -- an HTML
comment renders as visible junk and does not survive the Word round-trip,
R3.3 #1); role is a field inside the question block, not a heading, so the
question block itself is byte-identical whether the entity is rendered
alone or as one section of a `--combine`d document (R3.3 #2).
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from review_signoffs import entity_status_rollup, load_signoffs, status_of, text_hash
from suggest_fixes import _source_file

ROUTING_PATH = Path("questionnaire_routing.json")


def load_routing() -> dict:
    if not ROUTING_PATH.exists():
        return {}
    with open(ROUTING_PATH) as f:
        return json.load(f)


def save_routing(routing: dict) -> None:
    with open(ROUTING_PATH, "w") as f:
        json.dump(routing, f, indent=2, sort_keys=True)
        f.write("\n")


def route(
    key: str,
    text: str,
    owner_role: str,
    question: str,
    routed_by: str = "",
    routed_at: str = "",
) -> None:
    """Writes the local routing record. Unconditional given a key/text --
    same split as review_signoffs.sign(): this function trusts its caller,
    the membership guard lives one layer up (see route_if_current / main's
    `route` subcommand), exactly where sign()'s own key-lookup guard lives
    in review_signoffs.py's main() rather than in sign() itself.

    routed_by/routed_at are honest, not fabricated: an unset routed_at is
    recorded as "" -- absence here means "no timestamp given," matching
    sign()'s agent_model/agent_attestation honesty principle.
    """
    routing = load_routing()
    routing[key] = {
        "text_hash": text_hash(text),
        "owner_role": owner_role,
        "question": question,
        "routed_by": routed_by,
        "routed_at": routed_at,
    }
    save_routing(routing)


def is_routing_stale(item: dict, routing: dict) -> bool:
    """True only if a routing record exists for this item's key AND its
    recorded hash does NOT match the item's CURRENT text_hash. Mirrors
    review_signoffs.is_signed_off()'s staleness comparison exactly, with
    inverted sense to match this function's name: an item with no routing
    record at all is not "stale" -- it is simply unrouted, a different fact
    that build_questionnaire_items (T2) is responsible for distinguishing.
    """
    record = routing.get(item["key"])
    if record is None:
        return False
    return record.get("text_hash") != item["text_hash"]


def route_if_current(
    key: str,
    all_review: list[dict],
    owner_role: str,
    question: str,
    routed_by: str = "",
    routed_at: str = "",
) -> bool:
    """Looks `key` up against `all_review` (the CURRENT review items) and
    only writes a routing record if found -- byte-for-byte the same safety
    property as review_signoffs.py's `sign` CLI guard
    ("No current review item with key {key!r} -- run 'list' first"). Returns
    True if a record was written, False if rejected (nothing written in that
    case).

    Takes `all_review` as a parameter rather than loading it itself, same
    principle T2's build_questionnaire_items and T6's entity_status_rollup
    are designed around: this stays testable without pulling in the real
    entity graph or structural_facts.json.
    """
    match = next((r for r in all_review if r["key"] == key), None)
    if match is None:
        return False
    route(key, match["text"], owner_role, question, routed_by=routed_by, routed_at=routed_at)
    return True


CARDINALITY_PROSE = {
    "many-to-one": "Each {entity} links to exactly one {other}; one {other} can have many {entity}.",
    "one-to-many": "Each {entity} can have many {other}; each {other} links to exactly one {entity}.",
    "one-to-one": "Each {entity} links to exactly one {other}, and the reverse also holds.",
}


def _parse_key(key: str) -> tuple[str, str, str | None]:
    """Splits a review_key() back into (entity_name, kind, target) -- the
    reverse of review_signoffs.review_key()'s own construction (":".join of
    [entity_name, kind] + ([target] if target else []))."""
    parts = key.split(":")
    entity_name, kind = parts[0], parts[1]
    target = parts[2] if len(parts) > 2 else None
    return entity_name, kind, target


def _find_relationship(entity, to_entity: str):
    for rel in entity.relationships:
        if rel.to_entity == to_entity:
            return rel
    raise ValueError(
        f"{entity.name}: no relationship to {to_entity!r} found, but a "
        f"review item claims one -- entity and review items have drifted"
    )


def _find_column(entity, name: str):
    for col in entity.columns:
        if col.name == name:
            return col
    raise ValueError(
        f"{entity.name}: no column {name!r} found, but a review item claims "
        f"one -- entity and review items have drifted"
    )


def _claim_and_source(entity, kind: str, target: str | None) -> tuple[str, str]:
    """Pulls (claim, source) straight from the validated Entity/Relationship/
    ColumnFact objects -- NEVER from a review item's item["text"]. This is
    Sec 1's load-bearing constraint: text/text_hash stay the claim's
    cryptographic identity, but the *rendered* claim and citation always
    come from the objects, which already carry business-meaningful prose by
    schema contract. NC-1 exists to catch a shortcut back to item["text"].
    """
    if kind == "grain":
        return entity.grain, entity.grain_source
    if kind == "relationship":
        rel = _find_relationship(entity, target)
        prose = CARDINALITY_PROSE[rel.cardinality].format(entity=entity.name, other=rel.to_entity)
        return f"{prose} {rel.description}", rel.source
    if kind == "column-source":
        col = _find_column(entity, target)
        return col.description, col.source
    raise ValueError(f"unknown review item kind {kind!r} in key {target!r}")


def build_questionnaire_items(
    review_items: list[dict], entities: list, routing: dict
) -> tuple[list[dict], list[dict]]:
    """Joins review items x entities x routing. Returns (renderable, stale):

    - renderable: routed items whose recorded hash still matches the item's
      CURRENT text_hash -- safe to render as an answerable question.
    - stale: routed items whose recorded hash does NOT match -- the claim
      changed after routing. Surfaced, never silently rendered (NC-4).

    An item with no routing record at all is neither renderable nor stale --
    it's simply not routed yet. That's `list`'s concern (T1), not this
    function's; build_questionnaire_items only ever emits items a human
    actually asked to route.
    """
    by_name = {entity.name: entity for entity in entities}
    renderable, stale = [], []
    for item in review_items:
        record = routing.get(item["key"])
        if record is None:
            continue
        entity_name, kind, target = _parse_key(item["key"])
        claim, source = _claim_and_source(by_name[entity_name], kind, target)
        built = {
            "key": item["key"],
            "text_hash": item["text_hash"],
            "entity_name": entity_name,
            "owner_role": record["owner_role"],
            "question": record["question"],
            "claim": claim,
            "source": source,
            "routed_by": record.get("routed_by", ""),
            "routed_at": record.get("routed_at", ""),
        }
        if is_routing_stale(item, routing):
            stale.append(built)
        else:
            renderable.append(built)
    return renderable, stale


def _render_question_block(item: dict, n: int) -> str:
    """Renders one question, Q{n} through its reference line. Used by both
    render_markdown (per-entity) and render_combined -- the SAME function,
    not a re-derived copy -- so the question block is byte-identical between
    the two output formats by construction (R3.3 #2): `--combine` is a pure
    concatenation, never a second renderer.

    Role is a field (`**Who this is for:**`), not a heading -- R3.3 #2's
    correction, since `## For: <Role>` would exceed md-to-docx.js's H1-H4
    limit once nested inside a combined document, and would make the
    question block structurally different between the two formats.

    The reference line is real, visible text, `·` not `|` -- R3.3 #1's
    correction. An HTML comment here would render as visible literal junk
    through md-to-docx.js AND be destroyed on the Word round-trip, breaking
    the entire point of the token (M2's answer-to-claim mapping).
    """
    return "\n".join([
        f"### Q{n} — {item['question']}",
        "",
        f"**Who this is for:** {item['owner_role']}",
        "",
        "**The question**",
        item["question"],
        "",
        "**What we currently believe**",
        item["claim"],
        "",
        "**Where that came from**",
        item["source"],
        "",
        "**Answer**",
        "",
        "> _(please write your answer here)_",
        "",
        f"*Reference: {item['key']} · {item['text_hash']} — please leave this line as it is.*",
    ])


def render_markdown(
    entity_name: str, items: list[dict], stale: list[dict], generated_at: str = ""
) -> str:
    """Renders one entity's questionnaire -- the per-entity file (R1.3): one
    file per entity, never per role, never one combined document. `items`
    are that entity's renderable questions (already filtered by --owner, if
    any, by the caller); `stale` are that entity's stale routings, surfaced
    in their own section rather than silently dropped (NC-4).
    """
    lines = [
        f"# Questions about {entity_name}",
        "",
        f"Generated {generated_at} — a rendered view; please write answers directly in this document.",
        "",
        "A few open questions came up while building this project's data "
        "model, and they need a business answer rather than a technical "
        "guess. Please write your answer directly beneath each question "
        "below; nothing else in this document needs to change.",
        "",
    ]
    for n, item in enumerate(items, start=1):
        lines.append(_render_question_block(item, n))
        lines.append("")

    if stale:
        lines += [
            "## ⚠ Not included — the underlying claim changed after these were routed",
            "",
            "These need re-routing before they're sent to anyone.",
            "",
        ]
        for item in stale:
            when = item["routed_at"] or "an earlier date"
            lines.append(f"- `{item['key']}` (routed to {item['owner_role']} on {when})")
        lines.append("")

    return "\n".join(lines)


def _git(*args: str) -> str | None:
    """Trimmed stdout, or None if git is unavailable or the command fails
    (e.g. not a git checkout) -- honest absence, never a fabricated
    'unknown' placeholder. Mirrors sign()'s agent_model honesty principle,
    applied to the combined document's provenance header (R3.2)."""
    try:
        result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return result.stdout.strip() or None


_REPO_SLUG_RE = re.compile(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$")


def _repo_slug() -> str | None:
    """`git remote get-url origin`, normalised to 'owner/repo'. Deliberately
    derived at runtime rather than reusing generate_owl.py's hardcoded EX
    namespace (R3.2, a small existing duplication) -- fixing that is out of
    M1's scope."""
    url = _git("remote", "get-url", "origin")
    if not url:
        return None
    match = _REPO_SLUG_RE.search(url)
    return match.group(1) if match else None


def _project_name() -> str | None:
    repo = _repo_slug()
    return repo.split("/")[-1] if repo else None


def _provenance_header(entities_items: list[tuple[str, list[dict]]], generated_at: str = "") -> str:
    """The combined document's header (R3.2) -- combined output ONLY, never
    per-entity files. A bulleted list plus a single-paragraph blockquote,
    not YAML front matter and not consecutive `**Label:** value` lines --
    both verified against the real md-to-docx.js parser to render wrong
    (R3.1). Every field is derived honestly: omitted, never fabricated,
    when it can't be determined (git fields; 'Return to' when routed_by
    isn't uniform across the included items) -- same principle as sign()'s
    honest-absence handling of agent_model.
    """
    all_items = [item for _, items in entities_items for item in items]
    roles = {item["owner_role"] for item in all_items}
    name = _project_name()

    lines = [
        f"# Data model questions — {name}" if name else "# Data model questions",
        "",
        f"- **Generated:** {generated_at}",
    ]

    repo = _repo_slug()
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    commit = _git("rev-parse", "--short", "HEAD")
    if repo and branch and commit:
        lines.append(f"- **Source:** {repo}, branch `{branch}`, commit `{commit}`")

    lines.append(
        f"- **Covers:** {len(entities_items)} entities · {len(all_items)} questions · {len(roles)} roles"
    )

    routed_by = {item["routed_by"] for item in all_items if item["routed_by"]}
    if len(routed_by) == 1:
        lines.append(f"- **Return to:** {next(iter(routed_by))}")

    lines += [
        "",
        "> **A generated snapshot, not a living document.** It was produced "
        "from this project's validated data model on the date above; if the "
        "model has changed since, regenerate it rather than editing this "
        "copy. It contains internal data-model detail and, once answered, "
        "business answers — store it accordingly; it is deliberately not "
        "kept in the source code repository.",
    ]
    return "\n".join(lines)


def render_combined(entities_items: list[tuple[str, list[dict]]], generated_at: str = "") -> str:
    """The `--combine` output: the provenance header (R3.2) followed by each
    entity's routed questions as a top-level `##` section. Deliberately
    excludes stale-claim sections -- those describe internal model churn,
    and this is the document that leaves the repo.

    Built with _render_question_block, the exact function render_markdown
    also uses -- pure concatenation, never a second renderer, so the two
    output formats cannot drift apart (R3.3 #2).
    """
    parts = [_provenance_header(entities_items, generated_at=generated_at)]
    for entity_name, items in entities_items:
        section = [f"## {entity_name}", ""]
        for n, item in enumerate(items, start=1):
            section.append(_render_question_block(item, n))
            section.append("")
        parts.append("\n".join(section).rstrip("\n"))
    return "\n\n".join(parts) + "\n"


def _load_all_entities() -> list:
    """The same [customers, orders] + ALL_REMAINING construction used
    throughout this repo (review_signoffs.py main(), validate_grounding.py
    main(), suggest_fixes.py main()) -- a minimal M1-local helper (per the
    plan's accepted-risk note: not a refactor of those five existing
    callers, zero blast radius on files that just stabilized). Used here by
    both _load_all_review and the render CLI so this file itself doesn't
    grow a second copy of the same three-import triple."""
    from generate_customers_entity import customers
    from generate_orders_entity import orders
    from generate_remaining_entities import ALL_REMAINING

    return [customers, orders] + ALL_REMAINING


def _load_all_review() -> list[dict]:
    """Entity-only review items, same scope and construction as
    review_signoffs.py main()'s all_review (R1.1: metric review items are
    out of scope for M1 -- see that decision's own ticket)."""
    from validate_grounding import validate_entity

    with open("structural_facts.json") as f:
        facts = json.load(f)

    all_review = []
    for entity in _load_all_entities():
        _, review = validate_entity(entity, facts)
        all_review.extend(review)
    return all_review


def _parse_render_args(args: list[str]) -> dict:
    """Parses the render subcommand's flags. Factored out of main() so it's
    testable without touching the filesystem or the real entity graph --
    same separation-of-concerns route_if_current already applies to the
    `route` guard."""
    parsed = {"owner": None, "out_dir": Path("questionnaires"), "combine": False}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--owner":
            parsed["owner"] = args[i + 1]
            i += 2
        elif arg == "--out-dir":
            parsed["out_dir"] = Path(args[i + 1])
            i += 2
        elif arg == "--combine":
            parsed["combine"] = True
            i += 1
        else:
            raise ValueError(f"unrecognized render argument: {arg!r}")
    return parsed


def main():
    """CLI: list routing status, route an item to a human, or render.

    Usage:
      python3 scripts/generate_questionnaire.py list
      python3 scripts/generate_questionnaire.py route <key> "<Owner Role>" "<the question in business terms>" ["<routed_by>"]
      python3 scripts/generate_questionnaire.py render [--owner "<Role>"] [--out-dir <dir>] [--combine]

    `list` also prints a STATUS ROLLUP line (M1 T6) -- counts of
    signed/routed/routing-stale/unreviewed across all current review
    items, via review_signoffs.entity_status_rollup (the single place that
    logic lives; validate_grounding.py's per-entity output shows the same
    thing at a finer grain, both importing from the same module so the two
    surfaces cannot drift apart).

    `route` looks the key up against the current review items and refuses
    to write anything if it isn't found there -- same safety property as
    review_signoffs.py's `sign`.

    `render` writes one Markdown file per entity with at least one routed
    (or stale-routed) question into `--out-dir` (default `questionnaires/`),
    skipping entities with nothing to show. `--owner` filters which
    questions render, still into per-entity files. `--combine` additionally
    writes a single `combined.md` concatenating the filtered per-entity
    questions under one provenance header -- the per-entity files remain
    the authored/traceable form either way.
    """
    all_review = _load_all_review()

    if len(sys.argv) < 2 or sys.argv[1] == "list":
        routing = load_routing()
        signoffs = load_signoffs()
        rollup = entity_status_rollup(all_review, signoffs, routing)
        print(
            f"STATUS ROLLUP: {rollup['signed']} signed / {rollup['routed']} routed / "
            f"{rollup['routing-stale']} routing-stale / {rollup['unreviewed']} unreviewed "
            f"({rollup['total']} total)\n"
        )

        routed, stale, pending = [], [], []
        for item in all_review:
            if item["key"] not in routing:
                pending.append(item)
            elif is_routing_stale(item, routing):
                stale.append(item)
            else:
                routed.append(item)

        print(f"ROUTED ({len(routed)}):")
        for item in routed:
            rec = routing[item["key"]]
            print(f"  {item['key']} -- routed to {rec['owner_role']}")

        print(f"\nSTALE ROUTING ({len(stale)}):")
        for item in stale:
            rec = routing[item["key"]]
            print(f"  {item['key']} -- was routed to {rec['owner_role']}, "
                  "but the claim changed since -- needs re-routing")

        print(f"\nPENDING, NOT ROUTED ({len(pending)}):")
        for item in pending:
            print(f"  key: {item['key']}")
            print(f"    {item['text']}")
        return

    if sys.argv[1] == "route":
        key = sys.argv[2]
        owner_role = sys.argv[3]
        question = sys.argv[4]
        routed_by = sys.argv[5] if len(sys.argv) > 5 else ""
        written = route_if_current(key, all_review, owner_role, question, routed_by=routed_by)
        if not written:
            print(f"No current review item with key {key!r} -- run 'list' first", file=sys.stderr)
            sys.exit(1)
        print(f"Routed: {key} -> {owner_role}")
        return

    if sys.argv[1] == "render":
        try:
            opts = _parse_render_args(sys.argv[2:])
        except ValueError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)

        routing = load_routing()
        entities = _load_all_entities()
        renderable, stale = build_questionnaire_items(all_review, entities, routing)
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        def _for_entity(pool, entity_name):
            return [
                item for item in pool
                if item["entity_name"] == entity_name
                and (opts["owner"] is None or item["owner_role"] == opts["owner"])
            ]

        opts["out_dir"].mkdir(parents=True, exist_ok=True)
        written = []
        for entity in entities:
            items = _for_entity(renderable, entity.name)
            entity_stale = _for_entity(stale, entity.name)
            if not items and not entity_stale:
                continue
            content = render_markdown(entity.name, items, entity_stale, generated_at=generated_at)
            out_path = opts["out_dir"] / f"{entity.name}.md"
            out_path.write_text(content)
            print(f"  wrote {out_path} (source: {_source_file(entity.name)})")
            if items:
                written.append((entity.name, items))

        if opts["combine"]:
            combined_path = opts["out_dir"] / "combined.md"
            combined_path.write_text(render_combined(written, generated_at=generated_at))
            print(f"  wrote {combined_path} (combined view, {len(written)} entities)")

        print(f"Rendered {len(written)} entity file(s) with routed questions to {opts['out_dir']}/")
        return

    print(__doc__, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
