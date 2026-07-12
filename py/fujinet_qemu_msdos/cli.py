"""Command-line interface for fujinet-qemu-msdos image tools."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .inject import DriverConfig, build_qcow2, resolve_path


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
        default=os.environ.get("OUTPUT_IMAGE", ""),
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
    parser.add_argument(
        "--fuji-port",
        default=os.environ.get("FUJI_PORT", ""),
        help="FUJINET.SYS FUJI_PORT option for CONFIG.SYS (env: FUJI_PORT)",
    )
    parser.add_argument(
        "--fuji-bps",
        default=os.environ.get("FUJI_BPS", "115200"),
        help="FUJINET.SYS FUJI_BPS option for CONFIG.SYS (env: FUJI_BPS, default: 115200)",
    )
    parser.add_argument(
        "--fuji-batch-sectors",
        default=os.environ.get("FUJI_BATCH_SECTORS", ""),
        help="FUJINET.SYS FUJI_BATCH_SECTORS option (env: FUJI_BATCH_SECTORS)",
    )
    parser.add_argument(
        "--fuji-readahead-sectors",
        default=os.environ.get("FUJI_READAHEAD_SECTORS", ""),
        help="FUJINET.SYS FUJI_READAHEAD_SECTORS option (env: FUJI_READAHEAD_SECTORS)",
    )
    parser.add_argument(
        "--fuji-io-retries",
        default=os.environ.get("FUJI_IO_RETRIES", ""),
        help="FUJINET.SYS FUJI_IO_RETRIES option (env: FUJI_IO_RETRIES)",
    )
    parser.add_argument(
        "--fuji-auto-downshift",
        default=os.environ.get("FUJI_AUTO_DOWNSHIFT", ""),
        help="FUJINET.SYS FUJI_AUTO_DOWNSHIFT option (env: FUJI_AUTO_DOWNSHIFT)",
    )
    parser.add_argument(
        "--fuji-debug-io",
        default=os.environ.get("FUJI_DEBUG_IO", ""),
        help="FUJINET.SYS FUJI_DEBUG_IO option (env: FUJI_DEBUG_IO)",
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

    if args.output.strip():
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
            driver_config=DriverConfig(
                fuji_port=args.fuji_port.strip(),
                fuji_bps=args.fuji_bps.strip(),
                batch_sectors=args.fuji_batch_sectors.strip(),
                readahead_sectors=args.fuji_readahead_sectors.strip(),
                io_retries=args.fuji_io_retries.strip(),
                auto_downshift=args.fuji_auto_downshift.strip(),
                debug_io=args.fuji_debug_io.strip(),
            ),
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
