from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "third_party.lock.yml"


def run(args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd or ROOT, check=check, text=True, capture_output=True)


def load_lock() -> dict[str, Any]:
    return yaml.safe_load(LOCK_PATH.read_text(encoding="utf-8"))


def clone_all() -> None:
    for name, repo in load_lock()["repositories"].items():
        path = ROOT / repo["path"]
        if path.exists():
            print(f"{name}: exists")
            continue
        run(["git", "clone", "--depth", "1", "--filter=blob:none", repo["url"], str(path)])
        run(["git", "checkout", repo["commit"]], cwd=path)
        run(["git", "switch", "-c", repo["branch"]], cwd=path)
        print(f"{name}: cloned {repo['commit']}")


def status() -> None:
    for name, repo in load_lock()["repositories"].items():
        path = ROOT / repo["path"]
        if not path.exists():
            print(f"{name}: missing")
            continue
        head = run(["git", "rev-parse", "HEAD"], cwd=path).stdout.strip()
        state = run(["git", "status", "-sb"], cwd=path).stdout.strip()
        marker = "OK" if head == repo["commit"] else "DRIFT"
        print(f"{name}: {marker} {head}\n{state}")


def apply_patches(check_only: bool = False) -> None:
    for name, repo in load_lock()["repositories"].items():
        path = ROOT / repo["path"]
        patch = ROOT / repo["patch"]
        if not path.exists():
            raise SystemExit(f"{name}: missing clone at {path}")
        if not patch.exists():
            raise SystemExit(f"{name}: missing patch at {patch}")
        if check_only:
            clean = run(["git", "apply", "--check", str(patch)], cwd=path, check=False)
            if clean.returncode == 0:
                print(f"{name}: clean-apply verified")
                continue
            reverse = run(["git", "apply", "--reverse", "--check", str(patch)], cwd=path, check=False)
            if reverse.returncode == 0:
                print(f"{name}: already-applied verified")
                continue
            raise SystemExit(f"{name}: patch verification failed\n{clean.stderr}\n{reverse.stderr}")
        run(["git", "apply", "--whitespace=nowarn", str(patch)], cwd=path)
        print(f"{name}: applied")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["clone", "status", "apply-patches", "verify-patches"])
    args = parser.parse_args()
    if args.command == "clone":
        clone_all()
    elif args.command == "status":
        status()
    elif args.command == "apply-patches":
        apply_patches(check_only=False)
    elif args.command == "verify-patches":
        apply_patches(check_only=True)


if __name__ == "__main__":
    main()
