"""检查分级的回归保护：只在临时 Git 仓库操作，不接触业务数据或模型。"""

import configparser
import importlib.util
import json
from pathlib import Path
import re
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "ci_change_scope", ROOT / "scripts/ci_change_scope.py"
)
scope = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scope)


@pytest.mark.parametrize(
    "paths,expected",
    [
        (["README.md"], False),
        (["AGENTS.md", "CHANGELOG.md", "docs/开发.md"], False),
        (["docs/adr/0044-local-ai.md"], False),
        (["docs/带 空格\n的说明.md"], False),
        (["docs/行业知识/品牌避坑.md"], True),
        (["docs/行业知识/子目录/README.md"], True),
        (["docs/开发.md", "backend/app/main.py"], True),
        (["frontend/src/views/home/index.vue"], True),
        (["backend/tests/test_auth.py"], True),
        (["backend/pytest.ini"], True),
        ([".github/workflows/ci.yml"], True),
        (["scripts/ci_change_scope.py"], True),
        ([".env.example"], True),
        (["Makefile"], True),
        (["docs/example.py"], True),
        (["other/README.md"], True),
        (["docs/../backend/README.md"], True),
        ([], True),
    ],
)
def test_scope_whitelist(paths, expected):
    assert scope.requires_full_checks(paths) is expected


def test_diff_range_covers_push_and_pull_request():
    # 验证整次推送的 before..after，不能只比较 HEAD 的最后一个提交。
    base, head = "a" * 40, "b" * 40
    assert (
        scope.diff_range("push", {"before": base, "after": head}) == f"{base}..{head}"
    )
    event = {"pull_request": {"base": {"sha": base}, "head": {"sha": head}}}
    assert scope.diff_range("pull_request", event) == f"{base}...{head}"


@pytest.mark.parametrize(
    "base", [None, "", "0" * 40, "HEAD~1", "a" * 39, "a" * 40 + "; echo unsafe"]
)
def test_unknown_or_invalid_revision_never_skips(base):
    assert scope.diff_range("push", {"before": base, "after": "b" * 40}) is None


def git(repository, *arguments):
    # 所有写入均发生在 pytest 的临时目录；不提交到项目仓库。
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=CI Scope Test",
            "-c",
            "user.email=ci-scope@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            *arguments,
        ],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "README.md").write_text("# 初始说明\n", encoding="utf-8")
    (tmp_path / "module.py").write_text("# 初始源码\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "initial")
    return tmp_path


@pytest.mark.parametrize(
    "path,expected",
    [
        ("docs/开发.md", False),
        ("docs/带 空格\n的说明.md", False),
        ("docs/行业知识/说明.md", True),
        ("backend/module.py", True),
    ],
)
def test_real_git_changes(repository, path, expected):
    before = git(repository, "rev-parse", "HEAD")
    target = repository / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# 检查范围样例\n", encoding="utf-8")
    git(repository, "add", ".")
    git(repository, "commit", "-qm", "change")
    assert scope.inspect_changes(repository, f"{before}..HEAD") is expected


def test_renaming_code_to_document_still_runs_full_checks(repository):
    before = git(repository, "rev-parse", "HEAD")
    (repository / "docs").mkdir()
    git(repository, "mv", "module.py", "docs/module.md")
    git(repository, "commit", "-qm", "rename")
    assert scope.inspect_changes(repository, f"{before}..HEAD") is True


def test_earlier_code_commit_is_not_hidden_by_latest_docs(repository):
    before = git(repository, "rev-parse", "HEAD")
    (repository / "module.py").write_text("# 改动源码\n", encoding="utf-8")
    git(repository, "commit", "-qam", "code change")
    (repository / "README.md").write_text("# 更新说明\n", encoding="utf-8")
    git(repository, "commit", "-qam", "docs change")
    assert scope.inspect_changes(repository, f"{before}..HEAD") is True
    assert scope.inspect_changes(repository, "HEAD~1..HEAD") is False


@pytest.mark.parametrize("invalid_range", [False, True])
def test_git_or_whitespace_failure_is_not_success(repository, invalid_range):
    before = git(repository, "rev-parse", "HEAD")
    (repository / "README.md").write_text("# 尾部空格  \n", encoding="utf-8")
    git(repository, "commit", "-qam", "whitespace error")
    revision_range = f"{'f' * 40 if invalid_range else before}..HEAD"
    with pytest.raises(subprocess.CalledProcessError):
        scope.inspect_changes(repository, revision_range)


def test_missing_event_conservatively_runs_full(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    assert scope.main() == 0
    assert capsys.readouterr().out == "run_full=true\n"


@pytest.mark.parametrize("run_full", [False, True])
def test_main_outputs_only_safe_boolean(tmp_path, monkeypatch, capsys, run_full):
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({"before": "a" * 40, "after": "b" * 40}), encoding="utf-8"
    )
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setattr(scope, "inspect_changes", lambda *_: run_full)
    assert scope.main() == 0
    assert capsys.readouterr().out == f"run_full={str(run_full).lower()}\n"


def test_main_failure_does_not_emit_success(tmp_path, monkeypatch, capsys):
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({"before": "a" * 40, "after": "b" * 40}), encoding="utf-8"
    )
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")

    def fail(*_):
        raise subprocess.CalledProcessError(2, ["git", "diff", "--check"])

    monkeypatch.setattr(scope, "inspect_changes", fail)
    assert scope.main() == 2
    assert capsys.readouterr().out == ""


def test_coverage_only_in_explicit_full_entrypoints():
    settings = configparser.ConfigParser()
    settings.read(ROOT / "backend/pytest.ini")
    assert "--cov" not in settings.get("pytest", "addopts", fallback="")
    for filename in ("Makefile", ".github/workflows/ci.yml"):
        assert (
            "--cov=app --cov-report=term --cov-fail-under=45"
            in (ROOT / filename).read_text()
        )


@pytest.mark.parametrize(
    "target,arguments",
    [
        ("check-docs", []),
        (
            "check-backend",
            [
                "TESTS=tests/test_check_workflow.py",
                "FILES=tests/test_check_workflow.py",
            ],
        ),
        ("check-frontend", ["FILES=src/views/home/index.vue"]),
    ],
)
def test_quick_targets_do_not_start_unrelated_checks(target, arguments):
    # make -n 只展开命令，不重复运行测试或构建，也不启动业务服务。
    commands = subprocess.run(
        ["make", "-n", target, *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    for heavy_command in (
        "--cov=app",
        "pnpm build",
        "alembic",
        "docker compose",
        "pnpm e2e",
    ):
        assert heavy_command not in commands
    if target == "check-backend":
        assert "--no-cov tests/test_check_workflow.py" in commands
        assert "ruff check tests/test_check_workflow.py" in commands
    elif target == "check-frontend":
        assert "pnpm typecheck" in commands
        assert "oxlint src/views/home/index.vue" in commands
        assert "eslint src/views/home/index.vue" in commands


def test_api_type_check_reuses_dependencies_and_pins_lockfile_version():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    lockfile = (ROOT / "frontend/pnpm-lock.yaml").read_text()
    version = re.search(
        r"openapi-typescript:\n\s+specifier:[^\n]+\n\s+version: ([\d.]+)", lockfile
    )[1]
    assert f"npx --yes openapi-typescript@{version} " in workflow
    assert workflow.count("pip install -r requirements.txt") == 1
    backend_job = workflow.split("  backend-test:", 1)[1].split("  frontend-check:", 1)[
        0
    ]
    assert "Generate and check API types" in backend_job
    for job in ("backend-test", "frontend-check", "docker-check"):
        job_body = workflow.split(f"  {job}:", 1)[1]
        assert job_body.startswith(
            "\n    needs: change-scope\n    if: needs.change-scope.outputs.run_full == 'true'"
        )
