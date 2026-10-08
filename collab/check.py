"""eAA 창구의 기준·원격 SHA·메시지 번호·실험 등록을 검사한다."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEGACY_GATES = "analysis/arm_angle/sinker_anchor_20261007/gates.md"
GATES = {
    "EAA-SI1": (LEGACY_GATES,),
    "EAA-SUP1": (LEGACY_GATES,),
    "EAA-CL1": (LEGACY_GATES,),
    "EAA-CL*": ("analysis/arm_angle/claude_review_20261007/gates.md",),
}

REQUIRED = ("id", "from", "to", "date", "type", "re", "master", "model_version", "model_sha256", "work")


def gate_paths(ident):
    return GATES.get(ident, GATES["EAA-CL*"] if ident.startswith("EAA-CL") else ())

def git(*args):
    return subprocess.run(["git", *args], cwd=HERE, capture_output=True)


def pushed(sha, branch):
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        return "전체40자SHA가 아님"
    if git("rev-parse", "--verify", "-q", f"origin/{branch}").returncode:
        return f"origin/{branch} 없음: fetch 필요"
    if git("cat-file", "-e", f"{sha}^{{commit}}").returncode:
        return "커밋 객체 없음"
    if git("merge-base", "--is-ancestor", sha, f"origin/{branch}").returncode:
        return "인용 SHA가 해당 원격 브랜치에서 도달 불가"
    return None


def front_matter(path):
    found = re.match(r"---\n(.*?)\n---\n", path.read_text(), re.S)
    if not found:
        return {}
    return {k.strip(): v.strip() for k, v in
            (line.split(":", 1) for line in found.group(1).splitlines() if ":" in line)}


def check_messages(folder, current_id, current_sha):
    errors, seen = [], set()
    files = sorted(folder.glob("*.md"))
    for path in files:
        head = front_matter(path)
        match = re.fullmatch(r"(\d{4})-(claude|gpt|user)-[a-z0-9-]+\.md", path.name)
        if not match or any(not head.get(k) for k in REQUIRED):
            errors.append(f"{path.name}: 파일명 또는 필수 머리말 오류")
            continue
        if (head["id"], head["from"]) != match.groups():
            errors.append(f"{path.name}: id/from이 파일명과 다름")
        if head["id"] in seen:
            errors.append(f"{path.name}: 메시지 번호 중복")
        if any(name.strip() not in {"gpt", "claude", "user"} for name in head["to"].split(",")):
            errors.append(f"{path.name}: 수신 역할 오류")
        if head["re"] != "-" and any(x.strip() not in seen or x.strip() >= head["id"] for x in head["re"].split(",")):
            errors.append(f"{path.name}: re는 앞선 메시지여야 함")
        seen.add(head["id"])
        problem = pushed(head["master"], "master")
        if problem:
            errors.append(f"{path.name}: master {problem}")
        if head["work"] != "-":
            for item in head["work"].split(","):
                branch, _, sha = item.strip().partition("@")
                problem = pushed(sha, branch)
                if problem:
                    errors.append(f"{path.name}: work {problem}")
        if "## 다음 차례" not in path.read_text():
            errors.append(f"{path.name}: 다음 차례 없음")
    if files:
        latest = front_matter(files[-1])
        if latest.get("model_version") != current_id or latest.get("model_sha256") != current_sha:
            errors.append("최신 메시지의 운영 ID/SHA가 origin/master와 다름")
    return errors


def check_status(path, current_id, current_sha):
    text, errors, ids = path.read_text(), [], set()
    if f"MODEL_ID `{current_id}`" not in text or current_sha not in text:
        errors.append("STATUS의 운영 ID/SHA가 origin/master와 다름")
    section = text.split("## 실험 ID", 1)[-1].split("\n## ", 1)[0]
    for row in re.findall(r"^\|(.+)\|\s*$", section, re.M):
        cells = [c.strip().strip("`") for c in row.split("|")]
        if cells[0] == "ID" or set(cells[0]) <= {"-", " "}:
            continue
        if len(cells) != 6:
            errors.append("실험 등록 행의 열 수가 6이 아님")
            continue
        ident = cells[0]
        if ident in ids:
            errors.append(f"실험 ID 중복: {ident}")
        ids.add(ident)
        branch, _, sha = cells[3].partition("@")
        problem = pushed(sha, branch)
        if problem:
            errors.append(f"{ident}: 등록 {problem}")
            continue
        registered = False
        for path in gate_paths(ident):
            result = git("show", f"{sha}:{path}")
            if result.returncode == 0 and re.search(
                    rf"^## {re.escape(ident)}[.\s(]", result.stdout.decode(), re.M):
                registered = True
                break
        if not registered:
            errors.append(f"{ident}: 등록 SHA에 gates 절 없음")
    return errors


def main():
    result = git("show", "origin/master:data/models/estimated_arm_angle_v3.json")
    if result.returncode:
        print("오류: origin/master 운영 모델을 읽을 수 없음. fetch 필요")
        return 1
    current_id = json.loads(result.stdout)["model_id"]
    current_sha = hashlib.sha256(result.stdout).hexdigest()
    errors = check_messages(HERE / "messages", current_id, current_sha)
    errors += check_status(HERE / "STATUS.md", current_id, current_sha)
    for error in errors:
        print("오류:", error)
    print(f"eAA 창구 검사: 오류 {len(errors)}건 (운영 {current_id}, SHA {current_sha})")
    return bool(errors)


if __name__ == "__main__":
    sys.exit(main())
