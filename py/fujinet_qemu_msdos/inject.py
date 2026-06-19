"""Inject FUJINET.SYS and optional apps into an MS-DOS qcow2 image."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

FAT83_RE = re.compile(r"^[A-Z0-9]{1,8}\.[A-Z0-9]{1,3}$")
REQUIRED_TOOLS = ("qemu-img", "fdisk", "mcopy", "mdir")


@dataclass(frozen=True)
class AppEntry:
    src: Path
    name: str
    required: bool = True


def resolve_path(path: str, repo_root: Path) -> Path:
    expanded = os.path.expanduser(os.path.expandvars(path.strip()))
    candidate = Path(expanded)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    return candidate.resolve()


def validate_fat83(name: str) -> str:
    upper = name.upper()
    if not FAT83_RE.match(upper):
        raise ValueError(
            f"FAT 8.3 name required (e.g. BWCN.EXE), got: {name!r}"
        )
    return upper


def load_apps_manifest(manifest: Path, repo_root: Path) -> list[AppEntry]:
    data = yaml.safe_load(manifest.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{manifest}: expected a YAML mapping at top level")

    raw_apps = data.get("apps")
    if raw_apps is None:
        return []
    if not isinstance(raw_apps, list):
        raise ValueError(f"{manifest}: 'apps' must be a list")

    entries: list[AppEntry] = []
    for index, item in enumerate(raw_apps):
        if not isinstance(item, dict):
            raise ValueError(f"{manifest}: apps[{index}] must be a mapping")
        if "src" not in item or "name" not in item:
            raise ValueError(
                f"{manifest}: apps[{index}] requires 'src' and 'name' keys"
            )

        src = resolve_path(str(item["src"]), repo_root)
        name = validate_fat83(str(item["name"]))
        required = bool(item.get("required", True))
        entries.append(AppEntry(src=src, name=name, required=required))

    return entries


def require_tools() -> None:
    missing = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]
    if missing:
        raise RuntimeError(
            "Missing required tool(s): "
            + ", ".join(missing)
            + " (install mtools and qemu-img)"
        )


def run_checked(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=True)


def partition_start_sector(raw_image: Path) -> int:
    result = run_checked(["fdisk", "-l", str(raw_image)])
    raw = str(raw_image)

    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue

        if parts[0] == f"{raw}1" and parts[1] == "*" and parts[2].isdigit():
            return int(parts[2])
        if parts[0] == f"{raw}1" and parts[1].isdigit():
            return int(parts[1])
        if parts[0].endswith("1") and parts[1] == "*" and parts[2].isdigit():
            return int(parts[2])
        if parts[0].endswith("1") and parts[1].isdigit():
            return int(parts[1])

    raise RuntimeError(
        f"Could not determine first partition start sector in {raw_image}"
    )


def mcopy(raw_image: Path, offset: int, src: Path, dest_name: str) -> None:
    image_spec = f"{raw_image}@@{offset}"
    run_checked(["mcopy", "-o", "-i", image_spec, str(src), f"::{dest_name}"])


def mdir(raw_image: Path, offset: int, names: list[str]) -> None:
    image_spec = f"{raw_image}@@{offset}"
    args = ["mdir", "-i", image_spec]
    args.extend(f"::{name}" for name in names)
    run_checked(args)


def inject_driver(raw_image: Path, offset: int, driver: Path) -> None:
    print(f"Injecting driver at FAT offset {offset}...", flush=True)
    mcopy(raw_image, offset, driver, "FUJINET.SYS")
    mdir(raw_image, offset, ["FUJINET.SYS"])


def inject_apps(
    raw_image: Path,
    offset: int,
    apps: list[AppEntry],
) -> list[str]:
    injected: list[str] = []
    skipped: list[str] = []

    for app in apps:
        if not app.src.is_file():
            if app.required:
                raise FileNotFoundError(f"Required app not found: {app.src}")
            skipped.append(f"{app.name} ({app.src})")
            continue
        injected.append(app.name)

    if skipped:
        print("Skipping optional app(s) not found:", file=sys.stderr)
        for item in skipped:
            print(f"  {item}", file=sys.stderr)

    if not injected:
        print("No apps to inject.", file=sys.stderr, flush=True)
        return []

    print("Injecting applications...", flush=True)
    for app in apps:
        if not app.src.is_file():
            continue
        print(f"  {app.src} -> C:\\{app.name}", flush=True)
        mcopy(raw_image, offset, app.src, app.name)

    mdir(raw_image, offset, injected)
    return injected


def build_qcow2(
    *,
    repo_root: Path,
    base_image: Path,
    output_image: Path,
    driver: Path,
    apps_manifest: Path | None,
) -> None:
    require_tools()

    if not base_image.is_file():
        raise FileNotFoundError(f"Base image not found: {base_image}")
    if not driver.is_file():
        raise FileNotFoundError(
            f"Driver not found: {driver}\n"
            "Build fujinet-msdos first, or pass --driver /path/to/fujinet.sys"
        )

    apps: list[AppEntry] = []
    if apps_manifest is not None:
        if not apps_manifest.is_file():
            raise FileNotFoundError(f"Apps manifest not found: {apps_manifest}")
        apps = load_apps_manifest(apps_manifest, repo_root)

    output_image.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        suffix=".raw",
        prefix="fujinet-msdos-nio.",
        delete=False,
    ) as handle:
        raw_image = Path(handle.name)

    try:
        print("Converting base image to temporary raw image...", flush=True)
        run_checked(["qemu-img", "convert", "-O", "raw", str(base_image), str(raw_image)])

        offset = partition_start_sector(raw_image) * 512
        inject_driver(raw_image, offset, driver)

        if apps:
            inject_apps(raw_image, offset, apps)

        print(f"Writing qcow2 image: {output_image}", flush=True)
        if output_image.exists():
            output_image.unlink()
        run_checked(
            ["qemu-img", "convert", "-O", "qcow2", str(raw_image), str(output_image)]
        )
        subprocess.run(["qemu-img", "info", str(output_image)], check=True)
    finally:
        raw_image.unlink(missing_ok=True)
