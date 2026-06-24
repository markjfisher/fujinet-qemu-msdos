# QEMU MS-DOS for FujiNet

This repository contains QEMU helpers and a base MS-DOS 6.22 hard disk image
for FujiNet testing.

There are two workflows:

- **NIO workflow**: current path for `fujinet-nio` and the clean MS-DOS NIO
  `FUJINET.SYS` driver.
- **Legacy workflow**: older `run-qemu` path for `fujinet-firmware` RS232
  testing.

New MS-DOS work should normally use the NIO workflow.

## NIO Quick Start

Build the NIO qcow2 image with driver and apps:

```sh
./build-nio-qcow --apps-manifest manifests/apps.yaml
```

Run it:

```sh
./run-qemu-nio --hda build/msdos-nio-apps.qcow2
```

The detailed NIO guide is in [docs/nio-workflow.md](docs/nio-workflow.md).
It covers prerequisites, building `fujinet-nio`, building `FUJINET.SYS`,
creating `manifests/apps.yaml`, creating raw FAT disk images, and the DOS
`FHOST` / `FIN` / `FMOUNT` workflow.

## Repository Contents

- `msdos.qcow2`: base MS-DOS boot image.
- `build-nio-qcow`: creates generated NIO qcow2 images under `build/`.
- `run-qemu-nio`: starts `fujinet-nio` and QEMU with FujiBus over TCP serial.
- `scripts/create_msdos_img.py`: creates raw FAT12/FAT16 images for mounting
  through FujiNet.
- `manifests/apps.example.yaml`: example app injection manifest.
- `fujinet-data/`: host filesystem root exposed to `fujinet-nio`.
- `run-qemu`: `fujinet-firmware` launcher.

Generated files under `build/` are not committed.

## Fujinet-firmware Script

`run-qemu` remains for the original `fujinet-firmware` RS232 workflow. It is not
used by the NIO driver. Prefer `build-nio-qcow` and `run-qemu-nio` for current
MS-DOS NIO development.
