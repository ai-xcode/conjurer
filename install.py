#!/usr/bin/env python3
"""install.py — Cross-platform installer for Conjurer.

Works on Linux, macOS, and Windows. Idempotent. Re-running is safe.

What it does:
  1. Find your ComfyUI install (auto-detect; you can override with --comfyui).
  2. Symlink (or junction, or copy on Windows without dev mode) this project
     into <ComfyUI>/custom_nodes/conjurer.
  3. Copy starter workflows into <ComfyUI>/user/default/workflows/conjurer-starter/.
  4. Install runtime deps into ComfyUI's venv if requirements.txt exists.

Usage:
  python install.py                                # auto-detect ComfyUI
  python install.py --comfyui /path/to/ComfyUI    # override
  python install.py --copy-mode                    # always copy, never symlink
  python install.py --uninstall                    # remove the install
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

THIS = Path(__file__).resolve().parent
NODE_NAME = "conjurer"


def find_comfyui() -> Path | None:
    """Best-effort ComfyUI install detection. Checks common paths per OS."""
    candidates: list[Path] = []
    home = Path.home()

    if sys.platform == "win32":
        candidates += [
            home / "Documents" / "ComfyUI" / "ComfyUI",
            home / "ComfyUI",
            Path("C:/ComfyUI"),
            home / "Documents" / "ComfyUI_windows_portable" / "ComfyUI",
        ]
    elif sys.platform == "darwin":
        candidates += [
            home / "ComfyUI",
            home / "Documents" / "ComfyUI",
            Path("/Applications/ComfyUI"),
        ]
    else:  # linux + bsd
        candidates += [
            home / "ComfyUI",
            Path("/opt/ComfyUI"),
            Path("/usr/local/ComfyUI"),
        ]

    for c in candidates:
        if (c / "main.py").is_file() and (c / "custom_nodes").is_dir():
            return c
    return None


def make_link(src: Path, dst: Path, copy_mode: bool = False) -> str:
    """Create a link/junction/copy from src to dst. Returns the method used."""
    if dst.exists() or dst.is_symlink():
        # If it's already pointing where we want, nothing to do
        try:
            if dst.is_symlink() and dst.resolve() == src.resolve():
                return "already-linked"
        except OSError:
            pass
        # Otherwise refuse to overwrite — user must remove manually
        raise RuntimeError(
            f"{dst} already exists. Remove it first if you want to reinstall."
        )

    if copy_mode:
        shutil.copytree(src, dst, symlinks=False)
        return "copied"

    # Try plain symlink first (works on macOS, Linux, and Windows w/ dev mode)
    try:
        os.symlink(src, dst, target_is_directory=True)
        return "symlinked"
    except (OSError, NotImplementedError) as e:
        pass

    # Windows fallback: directory junction (no admin needed)
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
                check=True, capture_output=True,
            )
            return "junction"
        except subprocess.CalledProcessError:
            pass

    # Last resort: copy
    shutil.copytree(src, dst, symlinks=False)
    return "copied (fallback)"


def install_starters(comfyui: Path) -> int:
    """Copy starter workflows into ComfyUI's user workflows folder."""
    src_dir = THIS / "workflows" / "starter"
    if not src_dir.is_dir():
        return 0
    dst_dir = comfyui / "user" / "default" / "workflows" / "conjurer-starter"
    dst_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for f in src_dir.glob("*.json"):
        dst = dst_dir / f.name
        if not dst.exists():
            shutil.copy2(f, dst)
            copied += 1
    return copied


def install_deps(comfyui: Path) -> bool:
    """Install our runtime deps into ComfyUI's venv if it has one."""
    req = THIS / "requirements.txt"
    if not req.is_file():
        return False

    pip = None
    for candidate in [
        comfyui / "venv" / "bin" / "pip",                # linux/mac
        comfyui / "venv" / "Scripts" / "pip.exe",        # windows
        comfyui / ".venv" / "bin" / "pip",               # alt
        comfyui / ".venv" / "Scripts" / "pip.exe",       # alt windows
    ]:
        if candidate.is_file():
            pip = candidate
            break

    if pip is None:
        print("  ! ComfyUI venv not found — skipping dep install. "
              "Install requirements.txt manually if Conjurer fails to import.")
        return False

    try:
        subprocess.run(
            [str(pip), "install", "--quiet", "-r", str(req)],
            check=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ! pip install failed: {e}")
        return False


def uninstall(comfyui: Path) -> None:
    """Remove the link/copy. Leaves starter workflows alone (user may have edited)."""
    target = comfyui / "custom_nodes" / NODE_NAME
    if not (target.exists() or target.is_symlink()):
        print(f"  Nothing to remove at {target}")
        return
    if target.is_symlink():
        target.unlink()
        print(f"  ✓ removed symlink: {target}")
    elif target.is_dir():
        shutil.rmtree(target)
        print(f"  ✓ removed directory: {target}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--comfyui", type=Path,
                    help="Path to ComfyUI install (auto-detected if omitted)")
    ap.add_argument("--copy-mode", action="store_true",
                    help="Always copy instead of symlinking. Slower & loses edits.")
    ap.add_argument("--uninstall", action="store_true",
                    help="Remove the install instead of creating it")
    args = ap.parse_args()

    comfyui = args.comfyui or find_comfyui()
    if comfyui is None:
        print("ERROR: couldn't find ComfyUI. Pass --comfyui /path/to/ComfyUI", file=sys.stderr)
        print("Looked in common locations for your OS. Did you install ComfyUI?",
              file=sys.stderr)
        return 1

    if not (comfyui / "main.py").is_file():
        print(f"ERROR: {comfyui}/main.py not found — that doesn't look like a ComfyUI install.",
              file=sys.stderr)
        return 1

    print(f"  ComfyUI:  {comfyui}")
    print(f"  Source:   {THIS}")

    if args.uninstall:
        print()
        uninstall(comfyui)
        return 0

    target = comfyui / "custom_nodes" / NODE_NAME

    print()
    try:
        method = make_link(THIS, target, copy_mode=args.copy_mode)
        print(f"  ✓ install method: {method}")
        print(f"  ✓ {target} → {THIS}")
    except Exception as e:
        print(f"  ✗ install failed: {e}", file=sys.stderr)
        return 1

    n = install_starters(comfyui)
    print(f"  ✓ starter workflows: {n} copied")

    if install_deps(comfyui):
        print("  ✓ deps installed into ComfyUI's venv")

    print()
    print("Now restart ComfyUI. Then open it in your browser and look for")
    print("the ✨ Conjurer button (top-right corner of the UI).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
