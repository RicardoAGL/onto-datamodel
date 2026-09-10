"""Signoff store for review items the validator can't check mechanically.

`validate_grounding.py` already splits every claim into `failures`
(mechanically disproven -> auto-reject) and `review` (mechanically
unfalsifiable -> needs a human). Until now nothing enforced that a human
actually looked at the `review` list -- a run could print ten review items
and still exit 0. This closes that gap: a review item only counts as
resolved once a human has explicitly signed it off, and the signoff is
tied to a hash of the item's exact text, so if the underlying claim
changes, the old signoff no longer applies and the item goes back to
"needs signoff" -- never silently carried forward.

Same shape as this project's own PR review gate (pr-review + security-expert
before merge): the machine clears what it can, a named human clears the
rest, and "done" means both happened, not just the first one.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

SIGNOFFS_PATH = Path("review_signoffs.json")
AUTHORIZED_SIGNERS_PATH = Path("AUTHORIZED_SIGNERS.md")


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def review_key(entity_name: str, kind: str, target: str | None = None) -> str:
    """Stable id for a review item, independent of its prose. `kind` is one
    of "grain", "relationship", "column-source". `target` is the column
    name or the related entity name; omitted for grain (one per entity)."""
    parts = [entity_name, kind] + ([target] if target else [])
    return ":".join(parts)


def load_signoffs() -> dict:
    if not SIGNOFFS_PATH.exists():
        return {}
    with open(SIGNOFFS_PATH) as f:
        return json.load(f)


def save_signoffs(signoffs: dict) -> None:
    with open(SIGNOFFS_PATH, "w") as f:
        json.dump(signoffs, f, indent=2, sort_keys=True)
        f.write("\n")


def is_signed_off(item: dict, signoffs: dict) -> bool:
    """True only if a signoff exists for this item's key AND its recorded
    hash matches the item's CURRENT text. A stale signoff (text changed
    since it was recorded) is treated as not-signed-off, not as an error
    and not as still-valid -- it just goes back in the queue."""
    record = signoffs.get(item["key"])
    if record is None:
        return False
    return record.get("text_hash") == item["text_hash"]


def reviewer_display(record: dict) -> str:
    """The text shown wherever a signoff's reviewer is printed. B1: an
    unauthorized-but-recorded signoff (see sign()'s docstring -- the write
    is honest, not refused) must not display identically to an authorized
    one, or every surface that shows `reviewer` silently launders the
    distinction the record itself preserves. `signer_authorized is False`
    specifically, not falsy/missing: a record from before this field
    existed has no key at all, and absence must read as unmarked, not as
    an invented "unauthorized" claim the record never made."""
    marker = " (UNAUTHORIZED)" if record.get("signer_authorized") is False else ""
    return f"{record['reviewer']}{marker}"


def status_of(item: dict, signoffs: dict, routing: dict) -> str:
    """Where one review item sits in the human-review lifecycle -- ONE of
    four states on a single axis: unreviewed -> routed -> signed, with
    routing-stale as a degraded `routed` (the underlying claim changed
    after routing, same "flag, never silently trust" discipline
    is_signed_off already applies to a stale signoff). `routing` is a
    plain dict (M1 T1's questionnaire_routing.json, already loaded by the
    caller) -- this module never reads that file itself and stays generic.

    Exclusion ("should this item count toward a measurement") is a
    DIFFERENT question on an orthogonal axis and is deliberately not a
    fifth state here -- see docs/plans/M1-questionnaire-generator-plan.md
    Sec R2.4 for the full reasoning. Do not add an `exclusions` parameter
    or an `"excluded"` return value to this function: that would collapse
    two independent facts into one symbol (an excluded-but-unreviewed item
    would lose its unreviewed-ness) and would make the state unrecoverable
    (an item overwritten to "excluded" has no prior state to return to).
    """
    if is_signed_off(item, signoffs):
        return "signed"
    if item["key"] not in routing:
        return "unreviewed"
    # Reuse generate_questionnaire.is_routing_stale's hash comparison
    # rather than re-deriving it here -- the exact copy-drifts-from-the-
    # original bug this repo already found once
    # (test_ci_exit_severity.py's compute_exit_code duplicate,
    # test_validate_metrics_reuses_the_same_function_not_a_copy).
    #
    # Deferred (function-local), not a module-level, import: generate_
    # questionnaire.py already imports text_hash/status_of/
    # entity_status_rollup FROM this module at ITS top level, so a
    # top-level import here in the other direction would be a real
    # circular import at module-LOAD time. A function-local import has no
    # such problem -- by the time status_of() actually runs, both modules
    # have long finished loading -- and it means importing this module
    # alone (with an empty routing dict, e.g. before M1's routing feature
    # is used at all) never touches generate_questionnaire.py: the import
    # only happens once there is an actual routing entry for this key to
    # check for staleness.
    from generate_questionnaire import is_routing_stale

    return "routing-stale" if is_routing_stale(item, routing) else "routed"


def entity_status_rollup(review_items: list[dict], signoffs: dict, routing: dict) -> dict:
    """Counts review items by status. Takes `review_items` as a parameter
    and NEVER fetches them itself (no importing entities, no reading
    structural_facts.json in here) -- this is what lets a future
    health-score milestone apply exclusion as an input filter in front of
    this rollup (`entity_status_rollup(scored, signoffs, routing)`)
    without ever touching this function's signature. Despite the name
    (matching the plan's own naming, since the intended per-entity use is
    what makes a future score drillable), this works on any list of
    review items -- callers decide the scope, one entity's items or all
    of them.

    Returns COUNTS, never a percentage: {"signed": 1, "unreviewed": 1} and
    {"signed": 50, "unreviewed": 50} are both "50%" and are not the same
    situation -- a percentage would discard exactly the information a
    future weighting scheme needs. See the plan's R1.4/R2.5 for the full
    set of constraints this keeps open.
    """
    rollup = {"signed": 0, "routed": 0, "routing-stale": 0, "unreviewed": 0, "total": 0}
    for item in review_items:
        rollup[status_of(item, signoffs, routing)] += 1
        rollup["total"] += 1
    return rollup


_SIGNER_LINE = re.compile(r"^-\s*(.+?)\s*,\s*(.+?)\s*$")


def load_authorized_signers(path: Path = AUTHORIZED_SIGNERS_PATH) -> list[dict]:
    """Parses '- Name, Role' lines from AUTHORIZED_SIGNERS.md's ## Signers
    section. Not a secret yet, deliberately -- see that file's own
    "In a real setting" section for what replaces this on a real project."""
    if not path.exists():
        return []
    signers = []
    in_signers_section = False
    for line in path.read_text().splitlines():
        if line.strip() == "## Signers":
            in_signers_section = True
            continue
        if in_signers_section and line.startswith("## "):
            break  # next section -- stop reading
        if in_signers_section:
            match = _SIGNER_LINE.match(line)
            if match:
                signers.append({"name": match.group(1), "role": match.group(2)})
    return signers


def verify_signer(typed: str, authorized: list[dict] | None = None) -> dict:
    """typed is exactly what a human typed to sign off, e.g. 'Ricardo
    Granados, Analytics Engineer'. Always returns a parsed result, never
    raises -- an unauthorized attempt gets recorded honestly by the
    caller (see sign()), not silently discarded. Matching is exact
    (case-sensitive, whitespace-trimmed): a typo in the role you claim is
    exactly the kind of sloppy acknowledgment this exists to catch."""
    if authorized is None:
        authorized = load_authorized_signers()
    if "," in typed:
        name, role = typed.split(",", 1)
        name, role = name.strip(), role.strip()
    else:
        name, role = typed.strip(), ""
    is_authorized = any(a["name"] == name and a["role"] == role for a in authorized)
    return {"name": name, "role": role, "authorized": is_authorized}


def sign(
    key: str,
    text: str,
    reviewer: str,
    note: str = "",
    signer_role: str = "",
    signer_authorized: bool | None = None,
    agent_model: str = "",
    signed_at: str = "",
) -> None:
    """Writes the local signoff record. This is NOT the enforcement point
    -- an unauthorized attempt is still written (so it's visible in a
    reviewable branch/PR, per AGENTS.md Step 5), not refused. Real
    enforcement is the human's own signed git commit plus branch
    protection, outside this function's control entirely.

    agent_model is honest, not fabricated: a human running this CLI alone
    (no agent involved) leaves it blank, and agent_attestation is
    recorded as None -- absence here means "no agent," not "unknown."
    """
    signoffs = load_signoffs()
    signoffs[key] = {
        "text_hash": text_hash(text),
        "reviewer": reviewer,
        "note": note,
        "signer_role": signer_role,
        "signer_authorized": signer_authorized,
        "agent_attestation": (
            {"model": agent_model, "proposed_at": signed_at} if agent_model else None
        ),
    }
    save_signoffs(signoffs)


def main():
    """CLI: list pending review items, verify a signer, or sign one off.

    Usage:
      python3 scripts/review_signoffs.py list
      python3 scripts/review_signoffs.py verify "<Name, Role>"
      python3 scripts/review_signoffs.py sign <key> "<Name, Role>" ["<note>"] ["<agent_model>"]

    "<Name, Role>" must match a line in AUTHORIZED_SIGNERS.md exactly to
    count as authorized -- see verify_signer()'s docstring. An
    unauthorized sign still writes the record (not silently refused), it
    just won't clear GitHub's branch protection when the change is
    pushed for review.
    """
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

    if len(sys.argv) < 2 or sys.argv[1] == "list":
        signoffs = load_signoffs()
        pending = [r for r in all_review if not is_signed_off(r, signoffs)]
        signed = [r for r in all_review if is_signed_off(r, signoffs)]
        print(f"PENDING SIGNOFF ({len(pending)}):")
        for r in pending:
            print(f"  key: {r['key']}")
            print(f"    {r['text']}")
        print(f"\nALREADY SIGNED OFF ({len(signed)}):")
        for r in signed:
            rec = signoffs[r["key"]]
            print(f"  {r['key']} -- signed by {reviewer_display(rec)}")
        return

    if sys.argv[1] == "verify":
        typed = sys.argv[2]
        result = verify_signer(typed)
        status = "AUTHORIZED" if result["authorized"] else "NOT AUTHORIZED"
        print(f"{result['name']}, {result['role']} -- {status}")
        if not result["authorized"]:
            print("Not on AUTHORIZED_SIGNERS.md. A signoff can still be "
                  "recorded and pushed for review, but won't clear branch "
                  "protection to merge.", file=sys.stderr)
        return

    if sys.argv[1] == "sign":
        key = sys.argv[2]
        reviewer_input = sys.argv[3]
        note = sys.argv[4] if len(sys.argv) > 4 else ""
        agent_model = sys.argv[5] if len(sys.argv) > 5 else ""
        match = next((r for r in all_review if r["key"] == key), None)
        if match is None:
            print(f"No current review item with key {key!r} -- run 'list' first", file=sys.stderr)
            sys.exit(1)
        verified = verify_signer(reviewer_input)
        sign(
            key, match["text"], verified["name"], note,
            signer_role=verified["role"],
            signer_authorized=verified["authorized"],
            agent_model=agent_model,
        )
        status = "AUTHORIZED" if verified["authorized"] else "NOT AUTHORIZED -- recorded, but won't clear branch protection"
        print(f"Signed off: {key} by {verified['name']}, {verified['role']} ({status})")
        return

    print(__doc__, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
