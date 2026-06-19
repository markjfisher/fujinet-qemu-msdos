"""Command-line interface for fujinet-qemu-msdos image tools."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .inject import build_qcow2, resolve_path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_driver(fujinet_msdos: Path) -> Path:
    return fujinet_msdos / "sys" / "fujinet.sys"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    root = repo_root()
    build_dir = root / "build"

    parser = argparse.ArgumentParser(
        description="Build an MS-DOS qcow2 image with the NIO FUJINET.SYS driver.",
    )
    parser.add_argument(
        "-b",
        "--base",
        default=os.environ.get("BASE_IMAGE", str(root / "msdos.qcow2")),
        help="Base MS-DOS qcow/qcow2 image (env: BASE_IMAGE)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output qcow2 image (env: OUTPUT_IMAGE)",
    )
    parser.add_argument(
        "-m",
        "--msdos-dir",
        default=os.environ.get("FUJINET_MSDOS", ""),
        help="fujinet-msdos repository (env: FUJINET_MSDOS, required)",
    )
    parser.add_argument(
        "-d",
        "--driver",
        default=os.environ.get("DRIVER", ""),
        help="FUJINET.SYS to inject (env: DRIVER)",
    )
    parser.add_argument(
        "--apps-manifest",
        default=os.environ.get("APPS_MANIFEST", ""),
        help="YAML manifest of apps to inject (env: APPS_MANIFEST)",
    )
    parser.add_argument(
        "--repo-root",
        default=str(root),
        help="Repository root for resolving relative manifest paths",
    )

    args = parser.parse_args(argv)
    args.repo_root = Path(args.repo_root).resolve()
    args.base_image = resolve_path(args.base, args.repo_root)
    args.fujinet_msdos = (
        resolve_path(args.msdos_dir, args.repo_root) if args.msdos_dir else None
    )

    manifest = args.apps_manifest.strip()
    args.apps_manifest_path = (
        resolve_path(manifest, args.repo_root) if manifest else None
    )

    if args.driver.strip():
        args.driver_path = resolve_path(args.driver, args.repo_root)
    elif args.fujinet_msdos is not None:
        args.driver_path = default_driver(args.fujinet_msdos)
    else:
        args.driver_path = None

    if args.output:
        args.output_image = resolve_path(args.output, args.repo_root)
    elif args.apps_manifest_path is not None:
        args.output_image = build_dir / "msdos-nio-apps.qcow2"
    else:
        args.output_image = build_dir / "msdos-nio.qcow2"

    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.fujinet_msdos is None:
        print(
            "FUJINET_MSDOS is not defined.\n"
            "Set FUJINET_MSDOS to the fujinet-msdos repository "
            "(relative or absolute path).",
            file=sys.stderr,
        )
        return 1

    if not args.fujinet_msdos.is_dir():
        print(
            f"FUJINET_MSDOS does not exist: {args.fujinet_msdos}",
            file=sys.stderr,
        )
        return 1

    if args.driver_path is None:
        print("DRIVER is not defined and FUJINET_MSDOS was not provided.", file=sys.stderr)
        return 1

    try:
        build_qcow2(
            repo_root=args.repo_root,
            base_image=args.base_image,
            output_image=args.output_image,
            driver=args.driver_path,
            apps_manifest=args.apps_manifest_path,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
