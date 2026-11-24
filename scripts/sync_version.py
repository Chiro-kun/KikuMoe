#!/usr/bin/env python3
"""Centralized version synchronization script for KikuMoe.

Single Source of Truth (SSOT): version.yml

Usage:
    python scripts/sync_version.py             # Sync pyproject & version_info from version.yml
    python scripts/sync_version.py 2.0.0-beta5  # Bump version in version.yml and sync all files
    python scripts/sync_version.py --check     # Check if all files match version.yml
    python scripts/sync_version.py --version   # Print current version from version.yml
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_YML = REPO_ROOT / "version.yml"
PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"
VERSION_INFO_TXT = REPO_ROOT / "packaging" / "windows" / "version_info.txt"


def read_version_yml(path: Path = VERSION_YML) -> str:
    """Read the version string from version.yml."""
    if not path.is_file():
        raise FileNotFoundError(f"Version file not found: {path}")
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^version:\s*['\"]?([^'\"\s]+)['\"]?", text, re.MULTILINE)
    if not m:
        raise ValueError(f"Could not parse 'version:' from {path}")
    return m.group(1).strip()


def parse_numeric_tuple(version_str: str) -> tuple[int, int, int, int]:
    """Parse version string into a 4-integer tuple for Windows PE version resources."""
    numbers = [int(n) for n in re.findall(r"\d+", version_str)]
    while len(numbers) < 4:
        numbers.append(0)
    return tuple(numbers[:4])  # type: ignore[return-value]


def sync_pyproject(version_str: str, path: Path = PYPROJECT_TOML, dry_run: bool = False) -> bool:
    """Sync version in pyproject.toml. Returns True if modified or out-of-sync."""
    if not path.is_file():
        return False
    content = path.read_text(encoding="utf-8")
    new_content, count = re.subn(
        r'^(version\s*=\s*)"[^"]+"',
        rf'\g<1>"{version_str}"',
        content,
        flags=re.MULTILINE,
    )
    if count == 0:
        # If version was not present under [tool.poetry], insert it after name
        new_content, count = re.subn(
            r'^(name\s*=\s*"[^"]+"\n)',
            rf'\g<1>version = "{version_str}"\n',
            content,
            flags=re.MULTILINE,
        )
    if content != new_content:
        if not dry_run:
            path.write_text(new_content, encoding="utf-8")
        return True
    return False


def generate_version_info_content(version_str: str) -> str:
    """Generate packaging/windows/version_info.txt content from version string."""
    filevers = parse_numeric_tuple(version_str)
    return f"""# UTF-8
# Auto-generated from version.yml by scripts/sync_version.py or kikumoe.spec
#
# For more details about fixed file info 'ffi' see:
# http://msdn.microsoft.com/en-us/library/ms646997.aspx

VSVersionInfo(
  ffi=FixedFileInfo(
    # filevers and prodvers should be always a tuple with four items: (1, 2, 3, 4)
    filevers={filevers},
    prodvers={filevers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'KikuMoe'),
        StringStruct(u'FileDescription', u'KikuMoe Client'),
        StringStruct(u'FileVersion', u'{version_str}'),
        StringStruct(u'InternalName', u'KikuMoe'),
        StringStruct(u'LegalCopyright', u'\\xa9 2026 KikuMoe. All rights reserved.'),
        StringStruct(u'OriginalFilename', u'KikuMoe.exe'),
        StringStruct(u'ProductName', u'KikuMoe'),
        StringStruct(u'ProductVersion', u'{version_str}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""


def sync_version_info(
    version_str: str, path: Path = VERSION_INFO_TXT, dry_run: bool = False
) -> bool:
    """Sync packaging/windows/version_info.txt. Returns True if modified or out-of-sync."""
    desired = generate_version_info_content(version_str)
    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        if existing == desired:
            return False
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(desired, encoding="utf-8")
    return True


def bump_version_in_yml(new_version: str, path: Path = VERSION_YML) -> None:
    """Write new version to version.yml."""
    new_version = new_version.lstrip("v").strip()
    path.write_text(f"version: {new_version}\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Centralized version synchronization tool for KikuMoe."
    )
    parser.add_argument(
        "bump_to",
        nargs="?",
        default=None,
        help="Optional new version to bump to (e.g. 2.0.0-beta5).",
    )
    parser.add_argument(
        "--bump",
        dest="bump_flag",
        default=None,
        help="Explicit version bump argument.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if files match version.yml without modifying them.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the current version from version.yml.",
    )

    args = parser.parse_args()

    current_version = read_version_yml()

    if args.version:
        print(current_version)
        return 0

    target_bump = args.bump_flag or args.bump_to
    if target_bump:
        new_version = target_bump.lstrip("v").strip()
        print(f"Bumping version from {current_version} to {new_version}...")
        bump_version_in_yml(new_version)
        current_version = new_version

    if args.check:
        mismatches: list[str] = []
        if sync_pyproject(current_version, dry_run=True):
            mismatches.append(f"pyproject.toml does not match version.yml ({current_version})")
        if sync_version_info(current_version, dry_run=True):
            mismatches.append(
                f"packaging/windows/version_info.txt does not match version.yml ({current_version})"
            )

        if mismatches:
            print("ERROR: Version mismatch detected:")
            for m in mismatches:
                print(f"  - {m}")
            print("\nRun 'python scripts/sync_version.py' to synchronize all files.")
            return 1
        print(f"All files match version.yml ({current_version}).")
        return 0

    # Synchronization mode
    updated = []
    if sync_pyproject(current_version):
        updated.append("pyproject.toml")
    if sync_version_info(current_version):
        updated.append("packaging/windows/version_info.txt")

    if updated:
        print(f"Synchronized version {current_version} to: {', '.join(updated)}")
    else:
        print(f"All files already in sync with version.yml ({current_version}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
