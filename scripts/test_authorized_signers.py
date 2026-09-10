"""Tests for the authorized-signer check and the extended signoff record.

Same negative-control principle as test_grounding.py/test_owl.py: prove
an unauthorized attempt is recorded honestly (not silently rejected, not
silently accepted) before trusting the mechanism on stage.
"""
from review_signoffs import load_authorized_signers, load_signoffs, sign, verify_signer


def test_real_authorized_signers_file_parses():
    signers = load_authorized_signers()
    assert {"name": "Ricardo Granados", "role": "Analytics Engineer"} in signers


def test_verify_signer_matches_authorized_entry():
    result = verify_signer("Ricardo Granados, Analytics Engineer")
    assert result == {"name": "Ricardo Granados", "role": "Analytics Engineer", "authorized": True}


def test_verify_signer_rejects_unlisted_name():
    result = verify_signer("Someone Else, Marketing")
    assert result["authorized"] is False
    # still parses and returns what was typed -- an unauthorized attempt
    # is recorded honestly, never silently discarded.
    assert result["name"] == "Someone Else"
    assert result["role"] == "Marketing"


def test_verify_signer_rejects_role_mismatch():
    """Same name, wrong role -- not a fuzzy match. A typo in the role you
    claim is exactly the kind of sloppy acknowledgment this check exists
    to catch, not smooth over."""
    result = verify_signer("Ricardo Granados, Marketing")
    assert result["authorized"] is False


def test_verify_signer_handles_missing_comma():
    """No role typed at all -- can't match anything in
    AUTHORIZED_SIGNERS.md (which always has a role), so this is always
    unauthorized, not a crash."""
    result = verify_signer("Ricardo Granados")
    assert result["authorized"] is False
    assert result["role"] == ""


def test_sign_records_agent_attestation_and_authorization(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sign(
        key="customers:grain",
        text="some grain claim",
        reviewer="Ricardo Granados",
        note="confirmed against the SQL",
        signer_role="Analytics Engineer",
        signer_authorized=True,
        agent_model="claude-sonnet-5",
        signed_at="2026-08-25T18:30:00+00:00",
    )
    record = load_signoffs()["customers:grain"]
    assert record["reviewer"] == "Ricardo Granados"
    assert record["signer_role"] == "Analytics Engineer"
    assert record["signer_authorized"] is True
    assert record["agent_attestation"] == {
        "model": "claude-sonnet-5",
        "proposed_at": "2026-08-25T18:30:00+00:00",
    }


def test_sign_still_writes_unauthorized_attempts(tmp_path, monkeypatch):
    """An unauthorized signer is still recorded, not refused -- the local
    write isn't the enforcement point. Enforcement is the human's signed
    commit plus branch protection; a hidden/discarded attempt would give
    the wrong impression that nothing happened."""
    monkeypatch.chdir(tmp_path)
    sign(
        key="orders:grain",
        text="some other claim",
        reviewer="Someone Else",
        signer_role="Marketing",
        signer_authorized=False,
        agent_model="claude-sonnet-5",
    )
    record = load_signoffs()["orders:grain"]
    assert record["signer_authorized"] is False


def test_sign_without_agent_model_records_no_attestation(tmp_path, monkeypatch):
    """A human running review_signoffs.py alone, with no agent involved,
    should not get a fabricated agent_attestation -- absence is honest
    here, not a bug."""
    monkeypatch.chdir(tmp_path)
    sign(key="orders:grain", text="x", reviewer="Ricardo Granados")
    record = load_signoffs()["orders:grain"]
    assert record["agent_attestation"] is None
