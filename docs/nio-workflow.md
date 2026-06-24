# FujiNet NIO MS-DOS Workflow

This guide covers the NIO workflow for building and running an MS-DOS QEMU
image with the `fujinet-nio` MS-DOS driver and command-line tools.

## Prerequisites

Install the host tools:

```sh
qemu-system-i386 qemu-img dosfstools mtools netcat uv
```

The scripts expect these sibling repositories in your workspace, or equivalent
paths supplied with environment variables:

- `fujinet-nio`
- `fujinet-msdos`
- `nio-apps` if you want to build the sample MS-DOS command applications
- optionally `bounce-world-client-nio`

You will need Open Watcom in your shell

## Build Inputs

Build `fujinet-nio`:

```sh
cd /path/to/fujinet-nio
./build.sh -cp fujibus-tcp-debug
```

Build the MS-DOS NIO driver:

```sh
cd /path/to/fujinet-msdos
make -C sys FUJINET_TRANSPORT=NIO
```

Build the MS-DOS NIO applications:

```sh
cd /path/to/nio-apps
make -C msdos clean all
```

If you want to include MS-DOS Bouncy World Client for NIO:

```sh
cd /path/to/bounce-world-client-nio
export FUJINET_NIO_LIB=/path/to/fujinet-nio-lib
make clean && make
```

## App Manifest

`build-nio-qcow` can inject applications onto `C:\` using a YAML manifest.
Copy the example first:

```sh
cd /path/tofujinet-qemu-msdos
cp manifests/apps.example.yaml manifests/apps.yaml
```

Manifest entries map host files to MS-DOS 8.3 filenames:

```yaml
apps:
  - src: ${NIO_APPS_MSDOS}/bin/fhost.exe
    name: FHOST.EXE
  - src: ${NIO_APPS_MSDOS}/bin/fmount.exe
    name: FMOUNT.EXE
  - src: ${BOUNCE_WORLD_CLIENT_NIO}/build/bwcn.msdos.exe
    name: BWCN.EXE
    required: false
```

Fields:

- `src`: host path to copy. Supports environment variables such as
  `${NIO_APPS_MSDOS}` and `~`.
- `name`: destination filename on `C:\`. Use an MS-DOS 8.3 name.
- `required`: optional. Defaults to `true`; set `false` to skip missing files.

Typical environment:

```sh
export FUJINET_MSDOS=/path/to/fujinet-msdos
export NIO_APPS_MSDOS=/path/to/nio-apps/msdos
export FUJINET_NIO_LIB=/path/to/fujinet-nio-lib
export BOUNCE_WORLD_CLIENT_NIO=/path/to/bounce-world-client-nio
```

## Build The QEMU Image

Build a driver-only image:

```sh
./build-nio-qcow
```

This writes:

```text
build/msdos-nio.qcow2
```

Build a driver plus applications image:

```sh
./build-nio-qcow --apps-manifest manifests/apps.yaml
```

This writes:

```text
build/msdos-nio-apps.qcow2
```

`build-nio-qcow` clones the base `msdos.qcow2`, injects
`FUJINET.SYS`, then optionally copies manifest applications into the DOS
filesystem. Generated images under `build/` are not committed.

## Run The Emulator

Start QEMU with the app image:

```sh
./run-qemu-nio --hda build/msdos-nio-apps.qcow2
```

The script starts `fujinet-nio`, waits for the TCP serial listener, then starts
QEMU with the serial port connected to FujiBus over TCP.

The most common full sequence is:

```sh
./build-nio-qcow --apps-manifest manifests/apps.yaml
./run-qemu-nio --hda build/msdos-nio-apps.qcow2
```

Useful `run-qemu-nio` options:

| Flag | Env var | Default | Description |
|---|---|---|---|
| `-m`, `--memory` | `MEMORY` | `64` | RAM in MB for QEMU |
| `-d`, `--hda` | `HDA` | `build/msdos-nio.qcow2` | Boot hard disk image |
| `-f`, `--fda` | `FDA` | none | Optional floppy image |
| `-b`, `--boot` | `BOOT` | `c` | Boot device: `c` hard disk, `a` floppy |
| `-p`, `--port` | `FUJINET_PORT` | `65504` | FujiNet TCP serial port |
| `-N`, `--nio-bin` | `FUJINET_NIO_BIN` | `../fujinet-nio/build/fujibus-tcp-debug/fujinet-nio` | `fujinet-nio` binary |
| `-D`, `--nio-disk` | `NIO_DISK` | `fujinet-data/dos/fn-dos.img` | Default raw FAT image exposed as `host:/dos/fn-dos.img` |
| `-n`, `--no-pkill` | `PKILL_ENABLED=false` | pkill enabled | Do not kill existing `fujinet-nio` processes |

`run-qemu-nio` writes `fujinet-data/fujinet.yaml` on startup. By default slot 0
is configured as a pending mount for:

```text
host:/dos/fn-dos.img
```

For TNFS-hosted images, use `FHOST`, `FIN`, and `FMOUNT` from inside DOS.

## Create Mountable MS-DOS Images

The QEMU boot disk is qcow2. FujiNet drive images should be raw FAT images,
because `fujinet-nio` exposes them through DiskService as sector devices.

Use the local image script:

```sh
scripts/create_msdos_img.py \
  -i /path/to/folder-with/bin/ \
  -o /path/to/output/nio-apps.img \
  -l NIOAPPS
```

This creates a 1.44 MB FAT12 floppy-style image by default.

Create a larger FAT16 image:

```sh
scripts/create_msdos_img.py \
  -i /path/to/folder-with/bin/ \
  -o /path/to/output/nio-apps-16mb.img \
  --size-mb 16 \
  --fat 16 \
  --cluster-sectors 8 \
  -l NIO16MB
```

Notes:

- Input filenames must be MS-DOS 8.3 compatible.
- `.inf`, hidden dotfiles, and editor backup files ending in `~` are ignored.
- Larger FAT images work, but `DIR` reads more FAT/root-directory metadata over
  the serial block path. Prefer floppy-size images for small app collections.
- For FAT16 test images, 8 sectors per cluster is a good default for this
  workflow. Other valid FAT layouts should still mount.

## DOS Workflow

After booting QEMU, set the host and mount an image:

```dos
FHOST tnfs://some.server/msdos/
FIN 0 nio-apps.img
FMOUNT 0 D: RW
D:
DIR
```

Mount a second image on another DOS drive:

```dos
FIN 1 nio-apps-16mb.img
FMOUNT 1 E: RW
E:
DIR
```

Inspect drive-to-slot mappings:

```dos
FDRIVE
```

Useful tools on `C:\`:

- `FHOST.EXE`: show or set the current FujiNet host URI.
- `FLS.EXE`: list a TNFS/file path through FujiNet.
- `FIN.EXE`: select an image URI/path for a slot.
- `FMOUNT.EXE`: mount a slot onto a DOS drive.
- `FDRIVE.EXE`: show DOS drives, mapped slots, and selected images.
- `NIOPROBE.EXE`: probe DiskService directly.
- `NIOREAD.EXE`: read and dump a raw sector directly.
