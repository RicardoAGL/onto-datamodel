# Authorized signers

People authorized to sign off review items and approve changes to the
ontology. Checked by `review_signoffs.py verify` before a signoff is
recorded, and referenced by the conversational protocol in `AGENTS.md`
Step 5.

**Not a secret, deliberately, for now.** This is demo/tutorial scope: a
plain, git-diffable file anyone with write access to the repo could edit
— it is the *soft* check (forces a deliberate, typed acknowledgment; catches
typos and honest mistakes) not the *hard* one. The hard gate is GitHub's
own branch protection (require PRs, require signed commits) plus, once
this is a real multi-person project, `CODEOWNERS` — see "In a real
setting" below.

## Signers

Format: one `- Full Name, Role` line per person. Matched exactly
(case-sensitive, whitespace-trimmed) by `review_signoffs.py verify`.

- Ricardo Granados, Analytics Engineer

## In a real setting (outside this demo)

This file is the right shape for a solo-maintainer tutorial repo, and
deliberately not enough for a real production project with an actual
team:

- **This file → a real identity check.** SSO-backed, or a secrets-manager
  entry, or GitHub team membership — not a plain file anyone with write
  access could add themselves to.
- **`CODEOWNERS` becomes load-bearing, not documentation.** On this repo
  it's inert (see the file itself) — a solo maintainer approving their
  own PR proves nothing. On a real team (e.g. a real client project), a
  second, genuinely independent person's approval is what actually
  enforces authorization, and GitHub's "require review from code owners"
  branch protection setting makes that structural, not a request.
- **The signed-commit requirement stays identical either way** — that
  part already has real teeth even solo, since the agent never holds the
  human's private key.
