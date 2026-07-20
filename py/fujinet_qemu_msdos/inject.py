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
FAT_DIR_RE = re.compile(r"^[A-Z0-9]{1,8}$")
REQUIRED_TOOLS = ("qemu-img", "fdisk", "mcopy", "mdir", "mmd", "mdeltree")


@dataclass(frozen=True)
class AppEntry:
    src: Path
    name: str
    required: bool = True


@dataclass(frozen=True)
class DriverConfig:
    fuji_port: str = ""
    fuji_bps: str = "115200"
    batch_sectors: str = ""
    io_retries: str = ""
    auto_downshift: str = ""
    debug_io: str = ""


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


def validate_fat_dir(name: str) -> str:
    upper = name.strip().strip("\\/").upper()
    if not FAT_DIR_RE.match(upper):
        raise ValueError(f"FAT directory name required (e.g. FNAPPS), got: {name!r}")
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


def mmd(raw_image: Path, offset: int, name: str) -> None:
    image_spec = f"{raw_image}@@{offset}"
    subprocess.run(["mmd", "-i", image_spec, f"::{name}"], check=False)


def mdeltree(raw_image: Path, offset: int, name: str) -> None:
    image_spec = f"{raw_image}@@{offset}"
    subprocess.run(
        ["mdeltree", "-i", image_spec, f"::{name}"],
        check=False,
        text=True,
        input="y\n",
        capture_output=True,
    )


def mdir(raw_image: Path, offset: int, names: list[str]) -> None:
    image_spec = f"{raw_image}@@{offset}"
    args = ["mdir", "-i", image_spec]
    args.extend(f"::{name}" for name in names)
    run_checked(args)


def read_dos_file(raw_image: Path, offset: int, name: str) -> str:
    image_spec = f"{raw_image}@@{offset}"
    with tempfile.TemporaryDirectory(prefix="fujinet-msdos-read.") as tmpdir:
        dest = Path(tmpdir) / name
        result = subprocess.run(
            ["mcopy", "-i", image_spec, f"::{name}", str(dest)],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            return ""
        return dest.read_text(encoding="ascii", errors="ignore")


def write_dos_file(raw_image: Path, offset: int, name: str, contents: str) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="ascii",
        newline="",
        suffix=".dos",
        prefix="fujinet-msdos-write.",
        delete=False,
    ) as handle:
        path = Path(handle.name)
        handle.write(contents)

    try:
        mcopy(raw_image, offset, path, name)
        mdir(raw_image, offset, [name])
    finally:
        path.unlink(missing_ok=True)


def inject_driver(raw_image: Path, offset: int, driver: Path) -> None:
    print(f"Injecting driver at FAT offset {offset}...", flush=True)
    mcopy(raw_image, offset, driver, "FUJINET.SYS")
    mdir(raw_image, offset, ["FUJINET.SYS"])


def driver_config_line(config: DriverConfig) -> str:
    parts = ["DEVICE=FUJINET.SYS"]
    if config.fuji_port:
        parts.append(f"FUJI_PORT={config.fuji_port}")
    if config.fuji_bps:
        parts.append(f"FUJI_BPS={config.fuji_bps}")
    if config.batch_sectors:
        parts.append(f"FUJI_BATCH_SECTORS={config.batch_sectors}")
    if config.io_retries:
        parts.append(f"FUJI_IO_RETRIES={config.io_retries}")
    if config.auto_downshift:
        parts.append(f"FUJI_AUTO_DOWNSHIFT={config.auto_downshift}")
    if config.debug_io:
        parts.append(f"FUJI_DEBUG_IO={config.debug_io}")
    return " ".join(parts)


def inject_config(raw_image: Path, offset: int, config: DriverConfig) -> None:
    existing = read_dos_file(raw_image, offset, "CONFIG.SYS")
    lines: list[str] = []
    have_files = False
    have_buffers = False

    for raw_line in existing.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()
        upper = stripped.upper()
        if not stripped:
            continue
        if (
            (upper.startswith("DEVICE=") or upper.startswith("DEVICEHIGH="))
            and "FUJINET.SYS" in upper
        ):
            continue
        if upper.startswith("FILES="):
            have_files = True
        if upper.startswith("BUFFERS="):
            have_buffers = True
        lines.append(line)

    if not have_files:
        lines.append("FILES=20")
    if not have_buffers:
        lines.append("BUFFERS=10")
    lines.append(driver_config_line(config))

    contents = "\r\n".join(lines) + "\r\n"
    print(f"Injecting CONFIG.SYS: {driver_config_line(config)}", flush=True)
    write_dos_file(raw_image, offset, "CONFIG.SYS", contents)


def split_path_entries(value: str) -> list[str]:
    return [entry.strip() for entry in value.split(";") if entry.strip()]


def normalise_dos_path(value: str) -> str:
    return value.replace("/", "\\").rstrip("\\").upper()


def path_line_parts(line: str) -> tuple[str, str] | None:
    stripped = line.lstrip()
    indent = line[: len(line) - len(stripped)]
    upper = stripped.upper()
    if upper.startswith("SET PATH="):
        return indent + stripped[:9], stripped[9:].strip()
    if upper.startswith("PATH="):
        return indent + stripped[:5], stripped[5:].strip()
    if upper.startswith("PATH "):
        return indent + stripped[:5], stripped[5:].strip()
    return None


def append_path_entry(
    existing_value: str,
    entry: str,
    remove_entries: list[str],
) -> str:
    wanted = normalise_dos_path(entry)
    removals = {normalise_dos_path(item) for item in remove_entries}
    entries: list[str] = []

    for item in split_path_entries(existing_value):
        normalised = normalise_dos_path(item)
        if normalised in removals:
            continue
        if normalised == wanted:
            continue
        entries.append(item)

    entries.append(entry)
    return ";".join(entries)


def inject_autoexec_path(
    raw_image: Path,
    offset: int,
    apps_dir: str,
    legacy_dirs: list[str],
) -> None:
    existing = read_dos_file(raw_image, offset, "AUTOEXEC.BAT")
    lines: list[str] = []
    path_seen = False
    apps_path = f"C:\\{apps_dir}"
    legacy_paths = [f"C:\\{name}" for name in legacy_dirs]

    for raw_line in existing.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip()
        if not line:
            continue

        parts = path_line_parts(line)
        if parts is None:
            lines.append(line)
            continue

        prefix, value = parts
        value = append_path_entry(value, apps_path, legacy_paths)
        lines.append(f"{prefix}{value}")
        path_seen = True

    if not path_seen:
        lines.append(f"PATH C:\\DOS;{apps_path}")

    contents = "\r\n".join(lines) + "\r\n"
    print(f"Injecting AUTOEXEC.BAT PATH entry: {apps_path}", flush=True)
    write_dos_file(raw_image, offset, "AUTOEXEC.BAT", contents)


def remove_legacy_dirs(
    raw_image: Path,
    offset: int,
    apps_dir: str,
    legacy_dirs: list[str],
) -> None:
    for name in legacy_dirs:
        fat_name = validate_fat_dir(name)
        if fat_name == apps_dir:
            continue
        print(f"Removing legacy app directory C:\\{fat_name} if present...", flush=True)
        mdeltree(raw_image, offset, fat_name)


def inject_apps(
    raw_image: Path,
    offset: int,
    apps: list[AppEntry],
    apps_dir: str,
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
    mmd(raw_image, offset, apps_dir)
    for app in apps:
        if not app.src.is_file():
            continue
        dest = f"/{apps_dir}/{app.name}"
        print(f"  {app.src} -> C:\\{apps_dir}\\{app.name}", flush=True)
        mcopy(raw_image, offset, app.src, dest)

    injected_paths = [f"/{apps_dir}/{name}" for name in injected]
    mdir(raw_image, offset, [apps_dir, *injected_paths])
    return injected_paths


def build_qcow2(
    *,
    repo_root: Path,
    base_image: Path,
    output_image: Path,
    driver: Path,
    apps_manifest: Path | None,
    driver_config: DriverConfig,
    apps_dir: str = "FNAPPS",
    legacy_app_dirs: list[str] | None = None,
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
    apps_dir = validate_fat_dir(apps_dir)
    legacy_app_dirs = legacy_app_dirs or ["FN"]
    legacy_app_dirs = [validate_fat_dir(name) for name in legacy_app_dirs]

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
        remove_legacy_dirs(raw_image, offset, apps_dir, legacy_app_dirs)
        inject_driver(raw_image, offset, driver)
        inject_config(raw_image, offset, driver_config)

        if apps:
            inject_autoexec_path(raw_image, offset, apps_dir, legacy_app_dirs)
            inject_apps(raw_image, offset, apps, apps_dir)

        print(f"Writing qcow2 image: {output_image}", flush=True)
        if output_image.exists():
            output_image.unlink()
        run_checked(
            ["qemu-img", "convert", "-O", "qcow2", str(raw_image), str(output_image)]
        )
        subprocess.run(["qemu-img", "info", str(output_image)], check=True)
    finally:
        raw_image.unlink(missing_ok=True)
