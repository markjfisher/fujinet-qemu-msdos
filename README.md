# QEMU with FujiNet

This repository supports two MS-DOS workflows:

- `run-qemu`: the original legacy `fujinet-firmware` workflow.
- `run-qemu-nio`: the NIO workflow using `fujinet-nio` FujiBus over TCP serial.

The NIO workflow should be used for the clean MS-DOS NIO driver. It does not use
the legacy Atari/SIO-derived FujiNet transport.

## Using fujinet-nio

Build the POSIX TCP FujiBus profile in `fujinet-nio`:

```sh
cd /path/to/fujinet-nio
./build.sh -cp fujibus-tcp-debug
```

Build the MS-DOS NIO driver in `fujinet-msdos`:

```sh
cd /path/to/fujinet-msdos
make -C sys FUJINET_TRANSPORT=NIO
```

Optionally build the MS-DOS NIO test applications in `nio-apps`:

```sh
cd /path/to/nio-apps
make -C msdos clean all
```

Create the NIO boot image by cloning `msdos.qcow2` and replacing
`C:\FUJINET.SYS` with the newly built NIO driver. If the `nio-apps` tools were
built, this also copies `NIOPROBE.EXE` and `NIOREAD.EXE` into `C:\`:

```sh
./build-nio-qcow
```

Run QEMU with `fujinet-nio`:

```sh
./run-qemu-nio
```

`run-qemu-nio` starts `fujinet-nio` from
`../fujinet-nio/build/fujibus-tcp-debug/fujinet-nio`, waits for the TCP serial
listener, and then launches QEMU with `msdos-nio.qcow2`.

At the MS-DOS prompt, run:

```dos
NIOPROBE
NIOREAD
```

Use `DIR` to confirm the tools are present on `C:\`.

The script also creates a separate raw FAT image at
`fujinet-data/dos/fn-dos.img` if it does not exist. This is the disk exposed by
NIO `DiskService`; the QEMU boot qcow image is not mounted by NIO.

Generated NIO config:

```yaml
mounts:
  - slot: 1
    uri: "host:/dos/fn-dos.img"
    mode: "rw"
    enabled: true
    sector_size_hint: 512
channel:
  tcp_host: "127.0.0.1"
  tcp_port: 65504
```

Key `run-qemu-nio` options:

| Flag | Env var | Default | Description |
|---|---|---|---|
| `-m`, `--memory` | `MEMORY` | `64` | RAM in MB for the QEMU machine |
| `-d`, `--hda` | `HDA` | `msdos-nio.qcow2` | NIO hard disk image path |
| `-f`, `--fda` | `FDA` | _(none)_ | Floppy disk image path |
| `-b`, `--boot` | `BOOT` | `c` | Boot device (`c` = hard disk, `a` = floppy) |
| `-p`, `--port` | `FUJINET_PORT` | `65504` | FujiNet NIO TCP serial port |
| `-N`, `--nio-bin` | `FUJINET_NIO_BIN` | `../fujinet-nio/build/fujibus-tcp-debug/fujinet-nio` | fujinet-nio binary |
| `-D`, `--nio-disk` | `NIO_DISK` | `fujinet-data/dos/fn-dos.img` | Raw FAT disk exposed by NIO |
| `-n`, `--no-pkill` | `PKILL_ENABLED=false` | _(pkill enabled)_ | Skip killing existing fujinet-nio processes |

`--nio-disk` must point under `fujinet-data/`, because `fujinet-nio` exposes
that directory as its `host:` filesystem.

## Using run-qemu

`run-qemu` starts FujiNet and launches QEMU with the correct serial configuration. Before using it, build the firmware first (see below).

```sh
./run-qemu
```

Key options (all can also be set via environment variables of the same name):

| Flag | Env var | Default | Description |
|---|---|---|---|
| `-m`, `--memory` | `MEMORY` | `64` | RAM in MB for the QEMU machine |
| `-d`, `--hda` | `HDA` | `msdos.qcow2` | Hard disk image path |
| `-f`, `--fda` | `FDA` | _(none)_ | Floppy disk image path |
| `-b`, `--boot` | `BOOT` | `c` | Boot device (`c` = hard disk, `a` = floppy) |
| `-p`, `--port` | `FUJINET_PORT` | `65504` | FujiNet network port |
| `-F`, `--fujinet-path` | `FUJINET_FIRMWARE_PATH` | `../fujinet-firmware` | Path to the fujinet-firmware repo |
| `-n`, `--no-pkill` | `PKILL_ENABLED=false` | _(pkill enabled)_ | Skip killing existing fujinet processes |

Examples:

```sh
# Boot from floppy
./run-qemu --fda disks/Disk1.img --boot a

# Use a custom firmware path, more memory, and skip pkill
./run-qemu --fujinet-path /opt/fujinet --memory 128 --no-pkill
```

## Build fujinet-firmware for Serial (RS232)

In the `fujinet-firmware` cloned source directory, run:

```sh
./build.sh -p RS232
```

The resulting binary and supporting files will be placed in `distfiles/`, which `run-qemu` uses via the `fujinet/` symlink.

## Setting up QEMU

### Create a hard disk 

```sh
qemu-img create -f qcow msdos.qcow2 200M
```

>**_NOTE:_** This repository contains a pre-build MS-DOS 6.22 200MB hard disk image for convenience.  If a new hard disk is created then it will need the operating system, FujiNet driver, & any other FujiNet commands installed to it before it will work with the virtual FujiNet device that runs alongside QEMU.

### Install MS-DOS 

```sh
qemu-system-i386 -hda msdos.disk -m 64 -L  -fda disks/Disk1.img -boot a
```

When the installer prompts to insert Disk #2... 

1. `ctrl-alt-2` - get to the Qemu console
1. `eject floppy0` - eject the floppy
1. `change floppy0 disks/Disk2.img` - insert Disk #2
1. `ctrl-alt-1` - change back to the emulator screen

### Booting to the Hard Drive

```sh
qemu-system-i386 -hda msdos.qcow2 -m 64 -L . -serial tcp:localhost:65504,reconnect=1 -boot c
```
