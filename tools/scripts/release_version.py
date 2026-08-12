#!/usr/bin/env python3
"""Synchronize and validate IR-Trigger release metadata."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = ROOT / "VERSION"
MANIFEST_FILE = ROOT / "custom_components" / "ir_trigger" / "manifest.json"
HACS_FILE = ROOT / "hacs.json"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")


def _read_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def _validate_version(version: str) -> None:
    if not SEMVER.fullmatch(version):
        raise ValueError(f"Invalid semantic version: {version!r}")


def set_version(version: str) -> None:
    """Write the canonical version to every version-bearing file."""
    _validate_version(version)
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    manifest["version"] = version
    VERSION_FILE.write_text(f"{version}\n", encoding="utf-8")
    MANIFEST_FILE.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )


def check_version(tag: str | None = None) -> None:
    """Fail if metadata, HACS packaging, or an optional release tag disagrees."""
    version = _read_version()
    _validate_version(version)
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    if manifest.get("version") != version:
        raise ValueError(
            f"manifest.json version {manifest.get('version')!r} does not match VERSION {version!r}"
        )
    hacs = json.loads(HACS_FILE.read_text(encoding="utf-8"))
    if hacs.get("zip_release") is not True or hacs.get("filename") != "ir_trigger.zip":
        raise ValueError("hacs.json must select zip release artifact ir_trigger.zip")
    if tag is not None and tag != f"v{version}":
        raise ValueError(f"Release tag {tag!r} must equal 'v{version}'")
    print(f"IR-Trigger release metadata is consistent: {version}")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    set_parser = subparsers.add_parser("set", help="synchronize release versions")
    set_parser.add_argument("version")
    check_parser = subparsers.add_parser("check", help="validate release metadata")
    check_parser.add_argument("--tag")
    args = parser.parse_args()
    try:
        if args.command == "set":
            set_version(args.version)
            check_version()
        else:
            check_version(args.tag)
    except (OSError, ValueError, json.JSONDecodeError) as err:
        print(f"release metadata error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
