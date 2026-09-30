import pandas as pd
import pytest

from scripts.audit_sbj_data import combine, lf_sha256


def test_combine_accounts_for_every_pitch_without_inventing_trackman():
    quality = pd.DataFrame({"pitch_id": ["a", "b"], "review_level": ["none", "structural"]})
    coverage = pd.DataFrame({"pitch_id": ["b", "a"], "match_status": ["unmatched", "matched"],
                             "unmatched_reason": ["game_unmapped", ""]})
    result = combine(quality, coverage)
    assert result.pitch_id.tolist() == ["a", "b"]
    assert result.match_status.tolist() == ["matched", "unmatched"]
    assert combine(quality, None).match_status.tolist() == ["trackman_unavailable"] * 2
    with pytest.raises(ValueError, match="pitch sets differ"):
        combine(quality, coverage.iloc[:1])


def test_trackman_hash_ignores_checkout_line_endings(tmp_path):
    source = tmp_path / "trackman.csv"
    source.write_bytes(b"a,b\r\n1,2\r\n")
    crlf_hash = lf_sha256(source)
    source.write_bytes(b"a,b\n1,2\n")
    assert lf_sha256(source) == crlf_hash
