"""install.py 시험 — 프롬프트 방송 받는 쪽(prompt-cast-recv) 설치 판정.

가짜 claude 는 2.1.309 실측 응답(10/24)을 흉내 낸다: install --json 한 줄 · 같은 이름 다른 폴더면 name_taken ·
marketplace remove 는 그 마켓 plugin 까지 지움 · mod 명령은 로그인 없이 답하고, mod 가 못 받은 명령은
로그인이 없으면 「Not logged in」.
마지막 시험 하나는 진짜 claude 로 빈 설정 폴더 · 한글 경로에서 돈다(claude 가 없으면 건너뛴다).
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "install.py"
MARKET = "sure-lab-cast"
PLUGIN_ID = f"prompt-cast-recv@{MARKET}"


def load():
    spec = importlib.util.spec_from_file_location("prompt_cast_install", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def same(a, b):
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


class FakeClaude:
    def __init__(self, version="2.1.309 (Claude Code)", logged_in=True, mod_answers=True,
                 market_path=None, installed=False, list_override=None, install_fail=None):
        self.version = version
        self.logged_in = logged_in
        self.mod_answers = mod_answers
        self.markets = {MARKET: str(market_path)} if market_path else {}
        self.plugins = {}
        if installed:
            self.plugins[PLUGIN_ID] = self._entry(market_path)
        self.list_override = list_override or {}
        self.install_fail = install_fail
        self.calls = []

    @staticmethod
    def _entry(market_path):
        return {"id": PLUGIN_ID, "version": "0.1.0", "scope": "user", "enabled": True,
                "readFromFolder": str(Path(market_path) / "prompt-cast-recv")}

    def __call__(self, exe, args, cwd=None, timeout=120):
        self.calls.append((list(args), cwd))
        if args == ["--version"]:
            return 0, self.version + "\n", ""
        if args[:3] == ["plugin", "marketplace", "list"]:
            rows = [{"name": n, "source": "directory", "path": p, "installLocation": p} for n, p in self.markets.items()]
            return 0, json.dumps(rows), ""
        if args[:3] == ["plugin", "marketplace", "remove"]:
            name = args[3]
            self.markets.pop(name, None)
            self.plugins = {k: v for k, v in self.plugins.items() if not k.endswith("@" + name)}
            return 0, json.dumps({"command": "marketplace-remove", "outcome": "ok", "marketplace": name}), ""
        if args[:2] == ["plugin", "install"]:
            path = args[args.index("--marketplace") + 1]
            if self.install_fail:
                return 1, json.dumps({"command": "install", "outcome": "failed", "message": self.install_fail,
                                      "failureCode": "invalid_source"}), "✘ " + self.install_fail
            if MARKET in self.markets and not same(self.markets[MARKET], path):
                msg = f'Marketplace "{MARKET}" is already added from a different source (dir:{self.markets[MARKET]}).'
                return 1, json.dumps({"command": "install", "outcome": "failed", "message": msg,
                                      "failureCode": "name_taken"}), "✘ Failed to add marketplace: " + msg
            self.markets[MARKET] = path
            if PLUGIN_ID in self.plugins:
                msg = f'Plugin "{PLUGIN_ID}" is already installed (scope: user)'
            else:
                self.plugins[PLUGIN_ID] = self._entry(path)
                msg = f"Successfully installed plugin: {PLUGIN_ID} (scope: user)"
            return 0, json.dumps({"command": "install", "outcome": "ok", "pluginId": PLUGIN_ID, "message": msg}), ""
        if args[:2] == ["plugin", "list"]:
            rows = [dict(v, **self.list_override) if k == PLUGIN_ID else v for k, v in self.plugins.items()]
            return 0, json.dumps(rows), ""
        if args[:1] == ["-p"]:
            if not self.logged_in:
                return 1, "Not logged in · Please run /login\n", ""
            if not self.mod_answers:
                return 0, "I can help with that. What would you like to connect?\n", ""
            return 0, "연결된 강사 PC 가 없습니다. 강사 화면의 줄을 그대로 입력하세요: /cast-connect 10.10.111.97:8790\n", ""
        raise AssertionError(f"예상 밖 호출: {args}")

    def ran(self, *head):
        return [a for a, _ in self.calls if a[: len(head)] == list(head)]


@pytest.fixture
def inst(monkeypatch):
    mod = load()
    monkeypatch.setattr(mod, "find_claude", lambda: "claude")
    return mod


def use(monkeypatch, mod, fake):
    monkeypatch.setattr(mod, "run_claude", fake)
    return fake


# G1 — 처음 설치
def test_first_install_ok(inst, monkeypatch, capsys):
    fake = use(monkeypatch, inst, FakeClaude())
    assert inst.main([]) == 0
    out = capsys.readouterr().out
    install = fake.ran("plugin", "install")
    assert len(install) == 1
    args = install[0]
    assert args[2] == "prompt-cast-recv"
    assert same(args[args.index("--marketplace") + 1], HERE)
    assert args[args.index("--scope") + 1] == "user"
    assert "--json" in args
    assert "/reload-plugins" in out
    assert "/cast-connect" in out


def test_mod_check_runs_outside_repo(inst, monkeypatch):
    # 저장소 안에서 -p 를 돌리면 그 저장소 Hook 이 같이 돈다 — 홈 폴더에서 확인한다
    fake = use(monkeypatch, inst, FakeClaude())
    assert inst.main([]) == 0
    cwd = [c for a, c in fake.calls if a[:1] == ["-p"]]
    assert len(cwd) == 1 and same(cwd[0], Path.home())


# G2 — 다시 실행
def test_rerun_is_ok(inst, monkeypatch):
    use(monkeypatch, inst, FakeClaude(market_path=HERE, installed=True))
    assert inst.main([]) == 0


# G3 — 같은 이름이 다른 폴더(옛 클론)로 등록됨
def test_other_folder_stops_without_removing(inst, monkeypatch, capsys):
    old = r"C:\Users\student\old-clone\setup\prompt-cast"
    fake = use(monkeypatch, inst, FakeClaude(market_path=old, installed=True))
    assert inst.main([]) == 3
    out = capsys.readouterr().out
    assert old in out
    assert "--replace" in out
    assert fake.ran("plugin", "marketplace", "remove") == []
    assert fake.ran("plugin", "install") == []


def test_replace_removes_then_installs(inst, monkeypatch):
    old = r"C:\Users\student\old-clone\setup\prompt-cast"
    fake = use(monkeypatch, inst, FakeClaude(market_path=old, installed=True))
    assert inst.main(["--replace"]) == 0
    names = [a[:3] for a, _ in fake.calls]
    assert names.index(["plugin", "marketplace", "remove"]) < names.index(["plugin", "install", "prompt-cast-recv"])
    assert fake.ran("plugin", "marketplace", "remove")[0][3] == MARKET


def test_replace_without_conflict_does_not_remove(inst, monkeypatch):
    fake = use(monkeypatch, inst, FakeClaude(market_path=HERE, installed=True))
    assert inst.main(["--replace"]) == 0
    assert fake.ran("plugin", "marketplace", "remove") == []


# G4 — claude 없음 · 버전 낮음
def test_no_claude(monkeypatch, capsys):
    mod = load()
    monkeypatch.setattr(mod, "find_claude", lambda: None)
    fake = use(monkeypatch, mod, FakeClaude())
    assert mod.main([]) == 2
    assert fake.calls == []
    assert "claude" in capsys.readouterr().out


def test_old_version(inst, monkeypatch, capsys):
    fake = use(monkeypatch, inst, FakeClaude(version="2.1.250 (Claude Code)"))
    assert inst.main([]) == 2
    assert fake.ran("plugin", "install") == []
    assert "claude update" in capsys.readouterr().out


# G5 — 설치됐다고 했지만 실제로는 안 도는 경우
def test_install_failed_reports_message(inst, monkeypatch, capsys):
    use(monkeypatch, inst, FakeClaude(install_fail="Path does not exist: X"))
    assert inst.main([]) == 1
    assert "Path does not exist: X" in capsys.readouterr().out


def test_list_errors_fail(inst, monkeypatch, capsys):
    use(monkeypatch, inst, FakeClaude(list_override={"errors": ["Marketplace sure-lab-cast failed to load: cache-miss"]}))
    assert inst.main([]) == 1
    assert "cache-miss" in capsys.readouterr().out


def test_read_from_other_folder_fail(inst, monkeypatch):
    use(monkeypatch, inst, FakeClaude(list_override={"readFromFolder": r"C:\elsewhere\prompt-cast-recv"}))
    assert inst.main([]) == 1


def test_disabled_fail(inst, monkeypatch, capsys):
    use(monkeypatch, inst, FakeClaude(list_override={"enabled": False}))
    assert inst.main([]) == 1
    assert f"claude plugin enable {PLUGIN_ID}" in capsys.readouterr().out


def test_mod_not_answering_fail(inst, monkeypatch):
    use(monkeypatch, inst, FakeClaude(mod_answers=False))
    assert inst.main([]) == 1


# G6 — 「Not logged in」 = mod 가 /cast-connect 를 못 받음(mod 명령은 로그인 없이 답한다 — 10/24 실측 6/6)
def test_not_logged_in_means_mod_missing(inst, monkeypatch, capsys):
    use(monkeypatch, inst, FakeClaude(logged_in=False))
    assert inst.main([]) == 1
    assert "Not logged in" in capsys.readouterr().out


# G7 — 수강생 템플릿에는 받는 쪽만
def test_template_has_recv_only():
    market = json.loads((HERE / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert market["name"] == MARKET
    assert [(p["name"], p["source"]) for p in market["plugins"]] == [("prompt-cast-recv", "./prompt-cast-recv")]
    plugin = json.loads((HERE / "prompt-cast-recv" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert plugin["name"] == "prompt-cast-recv"
    names = [p.relative_to(HERE).as_posix() for p in HERE.rglob("*") if "__pycache__" not in p.parts]
    assert not [n for n in names if any(w in n for w in ("send", "relay", "bcast", "start-cast"))]
    assert not (HERE / "prompt-cast-recv" / "hooks" / "recv.test.tsx").exists()


# G9 — 진짜 claude · 빈 설정 폴더 · 한글 경로
@pytest.mark.skipif(shutil.which("claude") is None, reason="claude 명령 없음 — 실 CLI 시험 건너뜀")
def test_real_cli_korean_path_empty_config(tmp_path):
    copy = tmp_path / "수강생 폴더" / "setup" / "prompt-cast"
    shutil.copytree(HERE, copy, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "test_*.py"))
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")}
    env["CLAUDE_CONFIG_DIR"] = str(cfg)
    env["PYTHONUTF8"] = "1"
    run = subprocess.run([sys.executable, str(copy / "install.py")], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", env=env, timeout=180)
    assert run.returncode == 0, run.stdout + run.stderr  # 로그인 없어도 mod 는 /cast-connect 에 답한다
    claude = load().find_claude()
    listed = subprocess.run([claude, "plugin", "list", "--json"], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", env=env, timeout=60)
    entry = [p for p in json.loads(listed.stdout) if p["id"] == PLUGIN_ID]
    assert len(entry) == 1
    assert entry[0]["enabled"] is True and not entry[0].get("errors")
    assert same(entry[0]["readFromFolder"], copy / "prompt-cast-recv")
