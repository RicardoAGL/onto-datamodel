# ADR-002: A signed git commit is the signature, not a JSON field

**Status**: Accepted (retroactive, written alongside ADR-001 — see that
ADR's "Why retroactive" note, same reasoning applies here.)

## Context

The first version of the conversational signoff protocol (`AGENTS.md`
Step 5, commit `a3e1f6e`) had the agent run `review_signoffs.py sign`
itself once a human confirmed in chat. Ricardo caught the gap directly:
this is an unenforced claim — nothing mechanically proves a human
actually confirmed anything, the same failure mode ADR-001's whole
pipeline exists to catch, just applied to itself.

## Decision

Two distinct things get recorded, and they are not the same kind of
signature:

- **The human's signature** is their own SSH-signed git commit — real,
  non-repudiable, cryptographically tied to their identity via a key the
  agent does not have access to. The agent stages the change
  (`review_signoffs.json`) and explicitly hands control back; it never
  runs `git commit` for this.
- **The agent's attestation** (`agent_attestation`: model name,
  timestamp) is honest provenance metadata, not a signature — there is
  no meaningful private key for an LLM to hold. It exists so a future,
  more capable model reviewing the same ontology has a real signal
  ("this was approved under model X") rather than none.

A forced, typed acknowledgment gates the whole thing before any of this:
the agent asks the human to type their full name and role exactly (not
a casual "yes"), checks it against `AUTHORIZED_SIGNERS.md`
(`verify_signer()`), and records the result — authorized or not,
**always written, never silently refused**. Refusing the local write
would mean nothing to show in the branch/PR that follows.

`AUTHORIZED_SIGNERS.md` is deliberately a plain, non-secret repo file
for now (demo scope) — the *soft* check, forcing acknowledgment and
catching typos. The *hard* check is GitHub-native: branch protection
(require PRs, require signed commits) plus `CODEOWNERS`, documented as
**inert on this solo-maintainer repo** (self-approval satisfies nothing)
until a real second person is added — see `AUTHORIZED_SIGNERS.md`'s "In
a real setting" section.

## Alternatives considered

- **A Claude-Code-specific Skill** for this whole protocol — rejected,
  reverses the earlier explicit decision (2026-08-18) that `AGENTS.md`
  stays agent-agnostic so any AI coding agent an attendee brings can run
  the tutorial. Extended `AGENTS.md` itself instead.
- **A blocking `input()` prompt** for the typed acknowledgment —
  rejected: this session runs as a background job; a blocking terminal
  read would just hang. Used the conversational turn itself as the
  forced-acknowledgment mechanism instead — the agent's next message
  must contain the literal typed answer, which works for any
  chat-based coding agent, not just an interactive terminal.
- **Enabling "require review from Code Owners" immediately** — rejected
  for now: with only one person listed, self-approval doesn't satisfy
  GitHub's own check, which would lock the sole maintainer out of
  merging their own PRs. Documented as inert until a real team exists.

## Consequences

- Branch protection (require PRs, require signed commits) is a
  GitHub Pro / public-repo feature, and couldn't be turned on while
  this repo was still private — this ADR's hard-gate half was designed
  before it could actually be made live. Enable it once the repo has
  at least one real reviewer beyond the sole maintainer, per the
  "require review from Code Owners" trap noted in `CODEOWNERS`.
- `sign()`'s schema grew (`signer_role`, `signer_authorized`,
  `agent_attestation`), backward compatible — no existing test or call
  site broke (34/34 passing after the change).
