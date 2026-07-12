"""Build a raw MS-DOS FAT image from an apps manifest."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .inject import load_apps_manifest, resolve_path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def create_msdos_img_script(root: Path) -> Path:
    return root / "scripts" / "create_msdos_img.py"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    root = repo_root()
    parser = argparse.ArgumentParser(
        description="Build a raw MS-DOS FAT image from an apps YAML manifest.",
    )
    parser.add_argument(
        "-a",
        "--apps-manifest",
        required=True,
        help="YAML manifest with apps entries",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output raw FAT .img",
    )
    parser.add_argument(
        "--repo-root",
        default=str(root),
        help="Root used to resolve relative manifest paths",
    )
    parser.add_argument(
        "-l",
        "--label",
        default="NIOAPPS",
        help="MS-DOS volume label",
    )
    parser.add_argument(
        "-s",
        "--size-mb",
        type=int,
        default=None,
        help="Image size in MiB",
    )
    parser.add_argument(
        "-p",
        "--preset",
        choices=("1440", "2880"),
        default="1440",
        help="Floppy-style image size in KiB when --size-mb is omitted",
    )
    parser.add_argument(
        "-f",
        "--fat",
        type=int,
        choices=(12, 16),
        default=None,
        help="FAT type",
    )
    parser.add_argument(
        "-c",
        "--cluster-sectors",
        type=int,
        default=None,
        help="Sectors per cluster for mkfs.fat -s",
    )
    parser.add_argument(
        "--no-list",
        action="store_true",
        help="Do not print mdir listing after creation",
    )

    args = parser.parse_args(argv)
    args.repo_root = Path(args.repo_root).resolve()
    args.manifest_path = resolve_path(args.apps_manifest, args.repo_root)
    args.output_path = resolve_path(args.output, args.repo_root)
    return args


def stage_manifest(manifest: Path, root: Path, stage: Path) -> int:
    apps = load_apps_manifest(manifest, root)
    copied = 0
    skipped: list[str] = []

    for app in apps:
        if not app.src.is_file():
            if app.required:
                raise FileNotFoundError(f"Required app not found: {app.src}")
            skipped.append(f"{app.name} ({app.src})")
            continue
        shutil.copy2(app.src, stage / app.name)
        copied += 1

    if skipped:
        print("Skipping optional app(s) not found:", file=sys.stderr)
        for item in skipped:
            print(f"  {item}", file=sys.stderr)

    if copied == 0:
        raise ValueError(f"No manifest apps were available to copy: {manifest}")

    return copied


def build_apps_image(args: argparse.Namespace) -> None:
    script = create_msdos_img_script(repo_root())
    if not script.is_file():
        raise FileNotFoundError(f"MS-DOS image tool not found: {script}")
    if not args.manifest_path.is_file():
        raise FileNotFoundError(f"Apps manifest not found: {args.manifest_path}")

    with tempfile.TemporaryDirectory(prefix="fujinet-msdos-apps.") as tmpdir:
        stage = Path(tmpdir)
        copied = stage_manifest(args.manifest_path, args.repo_root, stage)
        print(f"Staged {copied} app(s) from {args.manifest_path}")

        cmd = [
            sys.executable,
            str(script),
            "-i",
            str(stage),
            "-o",
            str(args.output_path),
            "-l",
            args.label,
            "-p",
            args.preset,
        ]
        if args.size_mb is not None:
            cmd.extend(["-s", str(args.size_mb)])
        if args.fat is not None:
            cmd.extend(["-f", str(args.fat)])
        if args.cluster_sectors is not None:
            cmd.extend(["-c", str(args.cluster_sectors)])
        if args.no_list:
            cmd.append("--no-list")

        subprocess.run(cmd, check=True)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build_apps_image(args)
    except (FileNotFoundError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
