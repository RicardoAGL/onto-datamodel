"""Citation validator: checks that an ontology Entity's claims are actually
traceable, rather than trusting the `source` field's assertion.

Per Sec 11.4/12.5's silent-vs-flagged principle, applied here to grounding
instead of doc generation: structural claims (column exists with this exact
description, relationship exists with this exact FK) are MECHANICALLY
CHECKABLE against structural_facts.json -- these either pass or fail, no
judgment call. Prose claims (grain, summary, cardinality reasoning) require
reading SQL and can't be fully automated -- these get flagged for human
review, never silently trusted OR silently rejected.

This is the ContextGem pattern applied to our own pipeline: an unsourced
or wrong citation should fail loud, not become a trusted-looking ontology
entry.

Review items returned here are structured (see review_signoffs.review_key),
not raw strings -- so a signoff can be tied to a stable id plus a hash of
the exact claim text, and review_signoffs.py can tell "already signed off"
apart from "needs a human" without re-parsing prose.
"""
import json
import os
import sys
from pathlib import Path

from schema import Entity
# status_of is imported here (not just entity_status_rollup, which is what
# main() actually calls) so `validate_grounding.status_of` resolves to the
# exact same function object as `review_signoffs.status_of` -- see M1 T6's
# test_status_functions_are_single_sourced_not_copies, which asserts identity.
from review_signoffs import entity_status_rollup, review_key, reviewer_display, status_of, text_hash


def _review(entity_name: str, kind: str, text: str, target: str | None = None) -> dict:
    key = review_key(entity_name, kind, target)
    return {"key": key, "text": text, "text_hash": text_hash(text)}


def validate_entity(entity: Entity, facts: dict) -> tuple[list[str], list[dict]]:
    """Returns (failures, needs_human_review). `review` items are dicts,
    see _review() -- not raw strings."""
    failures = []
    review = []

    if entity.name not in facts["models"]:
        failures.append(f"entity '{entity.name}' does not exist in structural_facts.json at all")
        return failures, review

    model_facts = facts["models"][entity.name]

    for col in entity.columns:
        manifest_col = model_facts["columns"].get(col.name)

        if col.source == "manifest":
            if manifest_col is None:
                failures.append(
                    f"{entity.name}.{col.name}: marked source=manifest but "
                    f"column does not exist in structural_facts.json"
                )
                continue
            actual_desc = manifest_col["description"]
            if actual_desc is None:
                failures.append(
                    f"{entity.name}.{col.name}: marked source=manifest but "
                    f"structural_facts.json has no description for it -- "
                    f"claimed description was invented: {col.description!r}"
                )
            elif actual_desc.strip() != col.description.strip():
                failures.append(
                    f"{entity.name}.{col.name}: description does not match "
                    f"the manifest exactly.\n    claimed:  {col.description!r}\n"
                    f"    manifest: {actual_desc!r}"
                )
        else:
            # Non-manifest source (a SQL citation). If a manifest
            # description genuinely exists for this column, the claim IS
            # mechanically checkable regardless of what `source` says --
            # `source` is a free-form string written by the same agent
            # whose claim is being audited, and must not be able to opt a
            # claim out of a check that already applies to it (security
            # review F2). Only fall through to a review item when there is
            # truly nothing to compare against.
            manifest_desc = manifest_col["description"] if manifest_col else None
            if manifest_desc is not None:
                if manifest_desc.strip() != col.description.strip():
                    failures.append(
                        f"{entity.name}.{col.name}: source={col.source!r}, "
                        f"but a manifest description exists for this column "
                        f"and does not match.\n    claimed:  {col.description!r}\n"
                        f"    manifest: {manifest_desc!r}"
                    )
            else:
                # B2: a primary_key claim on a column that doesn't exist in
                # the manifest at all is exactly as fabricated as an
                # uncited relationship (see the relationship check below) --
                # fold that into the review text so a human signing off can
                # see the unproven key claim, not just the bare citation.
                unproven_key_note = ""
                if col.role == "primary_key" and manifest_col is None:
                    unproven_key_note = (
                        " Also unproven: this column is claimed as "
                        "primary_key but does not exist in "
                        "structural_facts.json at all -- no test backs it."
                    )
                review.append(_review(
                    entity.name, "column-source",
                    f"{entity.name}.{col.name}: source={col.source!r} -- "
                    f"verify this citation by hand, not mechanically "
                    f"checkable.{unproven_key_note}",
                    target=col.name,
                ))

        # Structural cross-check regardless of source: does the declared
        # role match what the manifest's tests actually prove?
        if manifest_col is not None:
            if col.role == "primary_key" and not (manifest_col["unique"] and manifest_col["not_null"]):
                failures.append(
                    f"{entity.name}.{col.name}: marked primary_key but "
                    f"structural_facts.json shows unique={manifest_col['unique']}, "
                    f"not_null={manifest_col['not_null']} -- not actually proven "
                    f"as a key by any test"
                )
        elif col.role == "primary_key":
            # B2: no manifest entry at all means no test could possibly
            # have proven this key claim -- that's not a lesser case than
            # the unique/not_null failure above, it's the same failure with
            # nothing to even check.
            failures.append(
                f"{entity.name}.{col.name}: marked primary_key but the "
                f"column does not exist in structural_facts.json at all -- "
                f"no test, no manifest entry, nothing proves this key claim"
            )

    known_relationships = {
        (r["from_model"], r["from_column"], r["to_model"], r["to_column"])
        for r in facts["relationships"]
    }
    for rel in entity.relationships:
        key = (entity.name, rel.from_column, rel.to_entity, rel.to_column)
        # Also check the reverse direction, since a relationship from the
        # "many" side's perspective may be declared on either entity.
        reverse_key = (rel.to_entity, rel.to_column, entity.name, rel.from_column)
        if key not in known_relationships and reverse_key not in known_relationships:
            failures.append(
                f"{entity.name} -> {rel.to_entity} via {rel.from_column}: "
                f"no matching relationships test found in "
                f"structural_facts.json -- this FK claim is unsupported"
            )
        else:
            # FK existence is proven; cardinality reasoning is not
            # mechanically checkable from structural facts alone. Include
            # the actual claim + citation so a reviewer can judge it from
            # this text alone, without opening the source file.
            review.append(_review(
                entity.name, "relationship",
                f"{entity.name} -> {rel.to_entity} (cardinality={rel.cardinality!r}): "
                f"\"{rel.description}\" -- FK existence is proven, but this "
                f"reasoning requires reading the SQL. Citation: {rel.source}",
                target=rel.to_entity,
            ))

    # Grain is never mechanically checkable -- it always requires reading
    # the model's actual SQL logic. Always flagged, never auto-passed.
    # Include the citation, not just the claim, for the same reason.
    review.append(_review(
        entity.name, "grain",
        f"{entity.name}: \"{entity.grain}\" -- requires human verification. "
        f"Citation: {entity.grain_source}",
    ))

    return failures, review


def compute_exit_code(all_failures: list, all_unsigned: list) -> int:
    """FAILURES (mechanically disproven) always block -- a genuine break,
    and Hard Gate 3 (CI must be green before next task) exists precisely
    to catch this. NEEDS SIGNOFF alone does not block -- expected during
    normal development, nothing is actually wrong yet, just not reviewed.
    This is deliberately NOT the same severity: CI was permanently red
    from the day it was created (2026-08-18) until this changed
    (2026-08-25) because both cases exited 1 identically, and a
    chronically-red CI trains everyone -- agent included -- to stop
    looking at it. Note to evaluate (Ricardo, 2026-08-25): this is a
    first pass at the split; revisit if it turns out to hide something
    that should have blocked."""
    return 1 if all_failures else 0


def summarize_clean_status(all_unauthorized_signed: list[str]) -> str:
    """The final all-clear line, printed only once there are no failures and
    no pending signoffs left. B1: reporting only, does not feed
    compute_exit_code() and takes no part in the exit code -- an
    unauthorized-but-recorded signoff (ADR-002: the write is honest, not
    refused) is still a signoff for the purposes of `is_signed_off`, so
    without this it would clear the queue and print exactly the same
    unconditional "Clean" line as a real, authorized review. Takes the
    list of unauthorized keys as a parameter rather than re-deriving it
    from signoffs/routing itself, same "caller decides the scope" shape
    as entity_status_rollup."""
    if all_unauthorized_signed:
        return (
            f"{len(all_unauthorized_signed)} item(s) signed off by an "
            f"unauthorized signer -- review before treating this as clean: "
            f"{', '.join(all_unauthorized_signed)}"
        )
    return (
        "Clean: no mechanically-checkable failures, and every "
        "non-mechanical claim has a human signoff on file."
    )


def main():
    facts_path = Path("structural_facts.json")
    if not facts_path.exists():
        print("structural_facts.json not found -- run extract_structural_facts.py first", file=sys.stderr)
        sys.exit(1)
    with open(facts_path) as f:
        facts = json.load(f)

    from generate_customers_entity import customers
    from generate_orders_entity import orders
    from generate_remaining_entities import ALL_REMAINING
    from generate_questionnaire import load_routing
    from review_signoffs import load_signoffs, is_signed_off

    signoffs = load_signoffs()
    routing = load_routing()
    all_failures = []
    all_unsigned = []
    all_unauthorized_signed = []
    for entity in [customers, orders] + ALL_REMAINING:
        failures, review = validate_entity(entity, facts)
        all_failures.extend(failures)
        unsigned = [r for r in review if not is_signed_off(r, signoffs)]
        signed = [r for r in review if is_signed_off(r, signoffs)]
        all_unsigned.extend(unsigned)
        all_unauthorized_signed.extend(
            r["key"] for r in signed if signoffs[r["key"]].get("signer_authorized") is False
        )

        print(f"=== {entity.name} ===")
        print(f"FAILURES (mechanically disproven, must fix): {len(failures)}")
        for f in failures:
            print(f"  ✗ {f}")
        print(f"NEEDS SIGNOFF (not mechanically checkable, no human confirmation on file): {len(unsigned)}")
        for r in unsigned:
            print(f"  ? [{r['key']}] {r['text']}")
        if signed:
            print(f"SIGNED OFF: {len(signed)}")
            for r in signed:
                print(f"  ✓ [{r['key']}] signed by {reviewer_display(signoffs[r['key']])}")
        # M1 T6 -- display-only status rollup (signed/routed/routing-stale/
        # unreviewed). Purely additive: does not feed compute_exit_code(),
        # here or anywhere else. review_signoffs.entity_status_rollup is
        # the single place this counting logic lives; generate_questionnaire
        # list's "STATUS ROLLUP" line imports the exact same function, so
        # the two surfaces cannot silently drift apart (see
        # test_status_functions_are_single_sourced_not_copies).
        rollup = entity_status_rollup(review, signoffs, routing)
        print(
            f"STATUS: {rollup['signed']} signed / {rollup['routed']} routed / "
            f"{rollup['routing-stale']} routing-stale / {rollup['unreviewed']} unreviewed"
        )
        print()

    if all_failures:
        print(f"BLOCKED: {len(all_failures)} mechanically-disproven claim(s). Fix the entity, don't sign off around this.")
        sys.exit(compute_exit_code(all_failures, all_unsigned))
    if all_unsigned:
        msg = (f"{len(all_unsigned)} review item(s) awaiting human signoff -- "
               f"not blocking (expected during normal development), but not "
               f"silently ignorable either. Run 'python3 scripts/review_signoffs.py list' "
               f"then 'sign <key> \"<Name, Role>\"'.")
        # GitHub Actions warning annotation -- shows up in the checks UI even
        # though the job itself passes, so "green" never means "nothing to
        # look at." Plain print locally, where the ::warning:: syntax would
        # just be noise.
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning::{msg}")
        else:
            print(f"WARNING: {msg}")
        sys.exit(compute_exit_code(all_failures, all_unsigned))
    print(summarize_clean_status(all_unauthorized_signed))
    sys.exit(compute_exit_code(all_failures, all_unsigned))


if __name__ == "__main__":
    main()
