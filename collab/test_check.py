"""메시지·원격 근거·실험 등록의 실제 오류를 차단하는 검사기 테스트."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import check

SHA = "a" * 40
MODEL_SHA = "b" * 64


def message(ident="0001", sender="gpt", re="-", model="eAA-v3"):
    return f"""---
id: {ident}
from: {sender}
to: claude
date: 2026-10-07
type: 검토
re: {re}
master: {SHA}
model_version: {model}
model_sha256: {MODEL_SHA}
work: experiment/example@{SHA}
---
## 다음 차례
claude
"""


def status(rows):
    return f"MODEL_ID `eAA-v3`, SHA {MODEL_SHA}\n## 실험 ID\n" + "\n".join(rows)


class ProtocolTests(unittest.TestCase):
    def test_valid_append_and_reply(self):
        with tempfile.TemporaryDirectory() as name, patch.object(check, "pushed", return_value=None):
            folder = Path(name)
            (folder / "0001-gpt-example.md").write_text(message())
            (folder / "0002-claude-reply.md").write_text(message("0002", "claude", "0001"))
            self.assertEqual(check.check_messages(folder, "eAA-v3", MODEL_SHA), [])

    def test_duplicate_number_and_future_reply_are_rejected(self):
        with tempfile.TemporaryDirectory() as name, patch.object(check, "pushed", return_value=None):
            folder = Path(name)
            (folder / "0001-gpt-example.md").write_text(message())
            (folder / "0001-claude-reply.md").write_text(message("0001", "claude", "0002"))
            errors = check.check_messages(folder, "eAA-v3", MODEL_SHA)
            self.assertTrue(any("번호 중복" in e for e in errors))
            self.assertTrue(any("앞선 메시지" in e for e in errors))

    def test_stale_model_and_sender_mismatch_are_rejected(self):
        with tempfile.TemporaryDirectory() as name, patch.object(check, "pushed", return_value=None):
            folder = Path(name)
            (folder / "0001-gpt-example.md").write_text(message(sender="claude", model="eAA-v2"))
            errors = check.check_messages(folder, "eAA-v3", MODEL_SHA)
            self.assertTrue(any("파일명과 다름" in e for e in errors))
            self.assertTrue(any("운영 ID/SHA" in e for e in errors))

    def test_short_missing_and_unreachable_sha_are_rejected(self):
        self.assertIn("40자", check.pushed("a" * 7, "experiment/example"))
        bad = subprocess.CompletedProcess([], 1, stdout=b"")
        ok = subprocess.CompletedProcess([], 0, stdout=b"")
        with patch.object(check, "git", return_value=bad):
            self.assertIn("fetch 필요", check.pushed(SHA, "experiment/example"))
        with patch.object(check, "git", side_effect=[ok, ok, bad]):
            self.assertIn("도달 불가", check.pushed(SHA, "experiment/example"))

    def test_unregistered_and_duplicate_experiment_are_rejected(self):
        row = f"| EAA-SI1 | 실험 | 완료 | experiment/example@{SHA} | gpt | 검토 |"
        with tempfile.TemporaryDirectory() as name, patch.object(check, "pushed", return_value=None), \
                patch.object(check, "git", return_value=subprocess.CompletedProcess([], 0, stdout=b"# empty\n")):
            path = Path(name) / "STATUS.md"
            path.write_text(status([row, row]))
            errors = check.check_status(path, "eAA-v3", MODEL_SHA)
            self.assertTrue(any("gates 절 없음" in e for e in errors))
            self.assertTrue(any("실험 ID 중복" in e for e in errors))

    def test_followup_cl_registration_uses_separate_path(self):
        row = f"| EAA-CL2 | 초안 | 미실행 | experiment/example@{SHA} | claude | 검토 |"
        valid = subprocess.CompletedProcess([], 0, stdout=b"## EAA-CL2 registration\n")
        with tempfile.TemporaryDirectory() as name, patch.object(check, "pushed", return_value=None), \
                patch.object(check, "git", return_value=valid) as mock_git:
            path = Path(name) / "STATUS.md"
            path.write_text(status([row]))
            self.assertEqual(check.check_status(path, "eAA-v3", MODEL_SHA), [])
            mock_git.assert_called_once_with(
                "show", f"{SHA}:analysis/arm_angle/claude_review_20261007/gates.md")

    def test_historical_and_unknown_registration_paths(self):
        self.assertEqual(check.gate_paths("EAA-CL1"), (check.LEGACY_GATES,))
        self.assertEqual(check.gate_paths("EAA-NEW1"), ())
        row = f"| EAA-CL2 | 초안 | 미실행 | experiment/example@{SHA} | claude | 검토 |"
        missing = subprocess.CompletedProcess([], 128, stdout=b"## EAA-CL2 invalid\n")
        with tempfile.TemporaryDirectory() as name, patch.object(check, "pushed", return_value=None), \
                patch.object(check, "git", return_value=missing):
            path = Path(name) / "STATUS.md"
            path.write_text(status([row]))
            self.assertTrue(any("gates 절 없음" in e for e in
                                check.check_status(path, "eAA-v3", MODEL_SHA)))

    def test_malformed_registry_fails_with_readable_error(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "STATUS.md"
            path.write_text(status(["| EAA-SI1 | 실험 | 등록 누락 | "]))
            self.assertEqual(check.check_status(path, "eAA-v3", MODEL_SHA), ["실험 등록 행의 열 수가 6이 아님"])


if __name__ == "__main__":
    unittest.main()
