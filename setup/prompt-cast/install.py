"""프롬프트 방송 받는 쪽(prompt-cast-recv)을 이 PC 의 Claude Code 에 설치하고 확인한다.

이 폴더(setup/prompt-cast)를 로컬 marketplace 「sure-lab-cast」로 등록해 user 범위로 설치한다 —
plugin 은 이 폴더에서 바로 읽힌다(저장소를 지우거나 옮기면 다시 실행).
종료 코드: 0 설치 · 확인 끝 · 1 설치나 확인 실패 · 2 claude 없음 또는 버전 낮음 ·
3 같은 이름이 다른 폴더로 등록돼 있음(지우지 않고 멈춤 — 승인 뒤 --replace).
사용: python setup/prompt-cast/install.py [--replace]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARKET = "sure-lab-cast"
PLUGIN = "prompt-cast-recv"
PLUGIN_ID = f"{PLUGIN}@{MARKET}"
MIN_VERSION = (2, 1, 292)  # install --marketplace


def find_claude():
    # claude.exe 를 먼저 — claude.cmd 는 cmd.exe 를 거쳐 한글 경로 인수가 깨질 수 있다
    return shutil.which("claude.exe") or shutil.which("claude")


def run_claude(exe, args, cwd=None, timeout=120):
    try:
        # 빈 표준입력 — 안 주면 -p 가 입력을 3초 기다린다
        run = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", cwd=cwd, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return 124, "", f"{timeout}초 안에 끝나지 않음: claude {' '.join(args)}"
    return run.returncode, run.stdout, run.stderr


def same(a, b):
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def last_json(text):
    for line in reversed(text.strip().splitlines()):
        if line.lstrip().startswith(("{", "[")):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def row(item, value, state):
    print(f"| {item} | {value} | {state} |")


def main(argv=None):
    parser = argparse.ArgumentParser(description="프롬프트 방송 받는 쪽 설치")
    parser.add_argument("--replace", action="store_true",
                        help=f"다른 폴더로 등록된 {MARKET} 를 지우고 이 폴더로 다시 등록(그 마켓의 plugin 도 지워진다)")
    args = parser.parse_args(argv)
    print("| 항목 | 값 | 상태 |")
    print("|---|---|---|")

    if not (HERE / PLUGIN / ".claude-plugin" / "plugin.json").is_file():
        row("원본 폴더", HERE / PLUGIN, "빠짐")
        return 1

    exe = find_claude()
    if exe is None:
        row("claude", "명령 없음", "빠짐")
        print("Claude Code 를 설치하고 새 터미널에서 다시 실행한다: PowerShell `irm https://claude.ai/install.ps1 | iex`")
        return 2
    code, out, err = run_claude(exe, ["--version"])
    found = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
    if code != 0 or not found:
        row("claude", (out + err).strip() or f"exit {code}", "실패")
        return 2
    version = tuple(int(n) for n in found.groups())
    if version < MIN_VERSION:
        row("claude", ".".join(map(str, version)), "낮음")
        print(f"{'.'.join(map(str, MIN_VERSION))} 이상이 필요하다 — `claude update` 뒤 다시 실행한다.")
        return 2
    row("claude", ".".join(map(str, version)), "OK")

    code, out, err = run_claude(exe, ["plugin", "marketplace", "list", "--json"])
    markets = last_json(out)
    if code != 0 or not isinstance(markets, list):
        row("마켓 목록", (out + err).strip()[:300] or f"exit {code}", "실패")
        return 1
    taken = [m for m in markets if m.get("name") == MARKET]
    if taken and not same(taken[0].get("path", ""), HERE):
        old = taken[0].get("path") or taken[0].get("installLocation") or "?"
        if not args.replace:
            row("마켓 등록", f"{MARKET} → {old}", "다른 폴더")
            print(f"같은 이름 「{MARKET}」이 다른 폴더로 등록돼 있다: {old}")
            print(f"이 폴더({HERE})로 바꾸려면 승인받은 뒤 `--replace` 로 다시 실행한다 — 옛 등록과 그 plugin 이 지워진다.")
            return 3
        code, out, err = run_claude(exe, ["plugin", "marketplace", "remove", MARKET, "--json"])
        result = last_json(out) or {}
        if code != 0 or result.get("outcome") != "ok":
            row("옛 등록 지우기", (result.get("message") or out + err).strip()[:300], "실패")
            return 1
        row("옛 등록 지우기", old, "OK")

    code, out, err = run_claude(exe, ["plugin", "install", PLUGIN, "--marketplace", str(HERE), "--scope", "user", "--json"])
    result = last_json(out) or {}
    if code != 0 or result.get("outcome") != "ok":
        row("설치", (result.get("message") or out + err).strip()[:500], "실패")
        return 1
    row("설치", f"{PLUGIN_ID} (user)", "OK")

    code, out, err = run_claude(exe, ["plugin", "list", "--json"])
    plugins = last_json(out)
    entry = [p for p in plugins if p.get("id") == PLUGIN_ID] if isinstance(plugins, list) else []
    if code != 0 or not entry:
        row("설치 목록", (out + err).strip()[:300] or f"{PLUGIN_ID} 없음", "실패")
        return 1
    entry = entry[0]
    if entry.get("errors"):
        row("설치 목록", "; ".join(map(str, entry["errors"])), "실패")
        return 1
    if entry.get("enabled") is not True:
        row("켜짐", "꺼져 있음", "실패")
        print(f"승인받은 뒤 `claude plugin enable {PLUGIN_ID}` 를 실행하고 다시 확인한다.")
        return 1
    if not same(entry.get("readFromFolder", ""), HERE / PLUGIN):
        row("읽는 폴더", entry.get("readFromFolder") or "없음", "실패")
        return 1
    row("읽는 폴더", entry["readFromFolder"], "OK")

    # 저장소 밖(홈)에서 — 이 저장소 Hook 이 같이 돌지 않게
    # mod 명령은 로그인 없이 답한다 — 「Not logged in」이 나오면 mod 가 /cast-connect 를 못 받은 것이다
    code, out, err = run_claude(exe, ["-p", "/cast-connect"], cwd=str(Path.home()), timeout=180)
    answer = (out + err).strip()
    if code != 0 or "강사 PC" not in answer:
        row("mod 응답", answer[:300] or f"exit {code}", "실패")
        print("mod 가 /cast-connect 에 답하지 않았다 — 위 응답을 그대로 보고한다.")
        return 1
    row("mod 응답", answer.splitlines()[0][:120], "OK")

    print()
    print("- 이미 열려 있던 Claude 창(지금 이 창 포함)은 `/reload-plugins` 를 치거나 새 창을 연다.")
    print("- 강의 시작 때 강사 화면의 `/cast-connect 강사IP:8790` 줄을 그대로 입력한다.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
