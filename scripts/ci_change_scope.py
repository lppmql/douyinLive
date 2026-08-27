"""CI 变更分级：只有明确的普通文档改动才能跳过重检查。

仅依赖 Python 标准库，分类阶段不需要安装业务依赖或启动数据库。
输出只有 run_full=true/false，便于安全写入 GitHub Actions 的 GITHUB_OUTPUT。
"""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


ROOT_DOCUMENTS = {"README.md", "CHANGELOG.md", "AGENTS.md"}


def is_plain_document(path: str) -> bool:
    """白名单之外全部按代码处理；行业知识会被程序加载，不允许跳过。"""
    parts = PurePosixPath(path).parts
    if ".." in parts or path.startswith("docs/行业知识/"):
        return False
    return path in ROOT_DOCUMENTS or (path.startswith("docs/") and path.endswith(".md"))


def requires_full_checks(paths: list[str]) -> bool:
    # 空差异不能证明本次只有文档，保守保留完整检查。
    return not paths or any(not is_plain_document(path) for path in paths)


def diff_range(event_name: str, event: dict) -> str | None:
    """push 覆盖整次推送；PR 采用共同祖先到 head，避免只检查最后一个提交。"""
    if event_name == "push":
        base, head, separator = event.get("before"), event.get("after"), ".."
    elif event_name == "pull_request":
        pull_request = event.get("pull_request", {})
        base = pull_request.get("base", {}).get("sha")
        head = pull_request.get("head", {}).get("sha")
        separator = "..."
    else:
        return None
    for revision in (base, head):
        if not isinstance(revision, str) or not re.fullmatch(
            r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", revision
        ):
            return None
        if set(revision) == {"0"}:
            return None
    return f"{base}{separator}{head}"


def inspect_changes(repository: Path, revision_range: str) -> bool:
    """用完整 Git 差异分类；关闭重命名折叠，保留旧路径的删除风险。"""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", "-z", revision_range, "--"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    paths = [
        path.decode("utf-8", errors="surrogateescape")
        for path in result.stdout.split(b"\0")
        if path
    ]
    # 即使只是说明文档，也校验整次提交的空白错误；不能无条件绿灯。
    subprocess.run(
        ["git", "diff", "--check", revision_range, "--"],
        cwd=repository,
        check=True,
        stdout=sys.stderr,
    )
    return requires_full_checks(paths)


def main() -> int:
    try:
        event = json.loads(
            Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8")
        )
        revision_range = diff_range(os.environ.get("GITHUB_EVENT_NAME", ""), event)
    except (KeyError, OSError, ValueError, TypeError, AttributeError):
        revision_range = None
    if revision_range is None:
        print("无法确定完整变更范围，保留全量检查。", file=sys.stderr)
        run_full = True
    else:
        try:
            run_full = inspect_changes(
                Path(__file__).resolve().parents[1], revision_range
            )
        except subprocess.CalledProcessError as exc:
            # Git 范围不完整时不能悄悄当成文档；格式错误同样让分类任务失败。
            print("Git 差异或格式检查失败，禁止跳过检查。", file=sys.stderr)
            return exc.returncode or 1
    print(f"run_full={str(run_full).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
