"""협업 창구 검사: 메시지 머리말과 STATUS.md의 실험 ID 레지스트리가 원격 상태와 맞는지 확인합니다.

지금까지 두 에이전트가 어긋난 원인(낡은 기준 커밋, 원격에 없는 브랜치·커밋 인용, 실험 ID 중복)을
글로 당부하는 대신 기계로 막습니다. 표준 라이브러리만 씁니다.

사용 (저장소 안 어디서든):
    git fetch origin master collab/claude-gpt <메시지가 인용하는 작업 브랜치들>
    python collab/check.py

종료 코드 0이면 통과입니다. 오류는 고친 뒤 커밋하고, 경고는 메시지 본문에 사유를 적습니다.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MESSAGES = HERE / "messages"
REQUIRED = ("id", "from", "to", "date", "type", "re", "master", "model_version", "work")
NAMES = {"claude", "gpt", "user"}
SHA = re.compile(r"^[0-9a-f]{40}$")
errors: list[str] = []
warnings: list[str] = []


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True)


def pushed(sha: str, branch: str) -> str | None:
    """sha가 origin/<branch>에서 도달 가능하면 None, 아니면 이유를 돌려줍니다."""
    if not SHA.match(sha):
        return f"전체 40자 SHA가 아닙니다: {sha}"
    if git("rev-parse", "--verify", "-q", f"origin/{branch}").returncode:
        return f"origin/{branch}가 없습니다 (git fetch origin {branch} 필요, 또는 원격에 없는 브랜치)"
    if git("cat-file", "-e", f"{sha}^{{commit}}").returncode:
        return f"{sha[:12]} 커밋을 찾을 수 없습니다 (미푸시이거나 fetch 누락)"
    if git("merge-base", "--is-ancestor", sha, f"origin/{branch}").returncode:
        return f"{sha[:12]}가 origin/{branch}에 없습니다 (미푸시 또는 다른 브랜치)"
    return None


def model_version() -> str | None:
    source = git("show", "origin/master:src/visualbaseball/zone_decision.py").stdout
    found = re.search(r"^MODEL_VERSION\s*=\s*'([^']+)'", source, re.M)
    return found.group(1) if found else None


def front_matter(path: Path) -> dict[str, str] | None:
    found = re.match(r"---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
    if not found:
        return None
    pairs = (line.split(":", 1) for line in found.group(1).splitlines() if ":" in line)
    return {key.strip(): value.strip() for key, value in pairs}


def check_messages(current: str | None) -> None:
    seen: dict[str, Path] = {}
    files = sorted(MESSAGES.glob("*.md"))
    for path in files:
        where = f"messages/{path.name}"
        name = re.match(r"^(\d{4})-([a-z]+)-[0-9a-z-]+\.md$", path.name)
        head = front_matter(path)
        if not name or head is None:
            errors.append(f"{where}: 파일 이름은 NNNN-보낸이-주제.md, 첫 줄부터 --- 머리말이 있어야 합니다")
            continue
        missing = [key for key in REQUIRED if not head.get(key)]
        if missing:
            errors.append(f"{where}: 머리말 누락 {missing}")
            continue
        if head["id"] != name.group(1) or head["from"] != name.group(2):
            errors.append(f"{where}: 머리말 id/from이 파일 이름과 다릅니다")
        if head["id"] in seen:
            errors.append(f"{where}: id {head['id']}가 {seen[head['id']].name}와 겹칩니다. 나중 메시지의 번호를 올리십시오")
        seen[head["id"]] = path
        for person in (head["from"], *head["to"].split(",")):
            if person.strip() not in NAMES:
                errors.append(f"{where}: 알 수 없는 이름 {person.strip()} (허용 {sorted(NAMES)})")
        if head["re"] != "-":
            for ref in head["re"].split(","):
                if ref.strip() not in seen or ref.strip() >= head["id"]:
                    errors.append(f"{where}: re {ref.strip()}는 앞선 메시지 id여야 합니다")
        problem = pushed(head["master"], "master")
        if problem:
            errors.append(f"{where}: master {problem}")
        if head["work"] != "-":
            for item in head["work"].split(","):
                branch, _, sha = item.strip().partition("@")
                problem = pushed(sha, branch) if sha else f"'{item.strip()}'는 브랜치@SHA 형식이어야 합니다"
                if problem:
                    errors.append(f"{where}: work {problem}")
        text = path.read_text(encoding="utf-8")
        if "## 다음 차례" not in text:
            warnings.append(f"{where}: '## 다음 차례' 절이 없습니다")
    if files and current:
        last = front_matter(files[-1]) or {}
        if last.get("model_version") != current:
            errors.append(f"messages/{files[-1].name}: model_version {last.get('model_version')} ≠ origin/master {current}. "
                          "낡은 기준입니다. master를 fetch하고 다시 읽은 뒤 쓰십시오")


def check_status(current: str | None) -> None:
    text = (HERE / "STATUS.md").read_text(encoding="utf-8")
    found = re.search(r"MODEL_VERSION\s*`([^`]+)`", text)
    if current and (not found or found.group(1) != current):
        warnings.append(f"STATUS.md: 현행 MODEL_VERSION이 origin/master({current})와 다릅니다. '현행 기준'을 갱신하십시오")
    section = text.split("## 실험 ID", 1)[-1].split("\n## ", 1)[0]
    ids: set[str] = set()
    for row in re.findall(r"^\|(.+)\|\s*$", section, re.M):
        cells = [cell.strip() for cell in row.split("|")]
        if not cells[0] or cells[0] in ("ID",) or set(cells[0]) <= {"-", " "}:
            continue
        ident = cells[0].strip("`")
        if ident in ids:
            errors.append(f"STATUS.md: 실험 ID {ident}가 중복입니다")
        ids.add(ident)
        registered = cells[3].strip("`") if len(cells) > 3 else "-"
        if registered in ("-", ""):
            continue
        branch, _, sha = registered.partition("@")
        problem = pushed(sha, branch) if sha else f"등록 열 '{registered}'는 브랜치@SHA 형식이어야 합니다"
        if problem:
            errors.append(f"STATUS.md {ident}: 등록 {problem}")
            continue
        gates = git("show", f"{sha}:analysis/sbj_formula/gates.md").stdout
        if not re.search(rf"^## {re.escape(ident)}[.\s(]", gates, re.M):
            errors.append(f"STATUS.md {ident}: {sha[:12]}의 gates.md에 '## {ident}' 절이 없습니다")


def main() -> int:
    current = model_version()
    if current is None:
        errors.append("origin/master의 MODEL_VERSION을 읽지 못했습니다 (git fetch origin master 필요)")
    check_messages(current)
    check_status(current)
    for line in warnings:
        print("경고:", line)
    for line in errors:
        print("오류:", line)
    print(f"검사 끝: 오류 {len(errors)}건, 경고 {len(warnings)}건 (origin/master MODEL_VERSION {current})")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
