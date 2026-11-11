# Collect SPE data for AutoFDO and BOLT

[TOC]

## Introduction

The ARM Statistical Profiling Extension (SPE) is a hardware feature on ARMv8.2+ and ARMv9 CPUs that
statistically samples micro-architectural operations at a configurable interval. For each sampled
operation, hardware writes a record into a memory buffer with the program counter (`PC`), operation
type, events (such as architecturally retired, conditional branch not taken, and branch
mispredicted), execution latency, and—for branches—the target address (`TGT`).

Simpleperf supports recording ARM SPE branch samples and converting them with `simpleperf inject`
into profile input files for [AutoFDO](https://github.com/google/autofdo) and
[BOLT](https://github.com/llvm/llvm-project/tree/main/bolt).

Unlike Intel LBR, ARM BRBE, or CoreSight ETM, each SPE sample captures a single retired branch
rather than a multi-branch history stack or full instruction stream. Because `create_llvm_prof
--profiler text` expects basic-block execution ranges in addition to branch counts, `simpleperf
inject` decodes 4-byte A64 instructions from the target ELF binary and synthesizes executed
instruction ranges starting from taken branch targets (`TGT`) and not-taken conditional branch
fallthrough addresses (`PC + 4`).

## Requirements

SPE data collection requires hardware, firmware, kernel, and privilege support:

- **Hardware and EL3 firmware**:
  - An ARM64 CPU implementing `FEAT_SPE`, with a device tree node (`compatible =
    "arm,statistical-profiling-extension-v1"`) describing the SPE PMU and PPI interrupt.
  - EL3 firmware must grant non-secure world access to SPE registers (for example,
    `ENABLE_SPE_FOR_NS=1` in Trusted Firmware-A).
- **Kernel configuration**:
  - `CONFIG_ARM_SPE_PMU=y` or `CONFIG_ARM_SPE_PMU=m` (`arm_spe_pmu.ko`), exposing
    `/sys/bus/event_source/devices/arm_spe_0`.
  - `CONFIG_PID_IN_CONTEXTIDR=y` (enabled in Android GKI kernels) so the kernel writes each
    thread's `TID` into `CONTEXTIDR_EL1`, allowing SPE records to include `CONTEXT` packets for
    process/thread attribution in system-wide (`-a`) and multi-threaded recordings.
- **Root privileges (`adb root`)**:
  - Reading `/sys/bus/event_source/devices/arm_spe_0` and recording `CONTEXT` packets in the
    kernel `arm_spe_pmu` driver (`perf_allow_kernel()`) require root privileges on Android.

You can check whether SPE is available on a rooted device with:

```sh
$ adb root
$ adb shell ls /sys/bus/event_source/devices/arm_spe_0
$ adb shell simpleperf list arm_spe
```

## Recording SPE data

Use `simpleperf record` with the `arm_spe_0` event:

```sh
$ adb root
$ adb shell
(device) / # cd /data/local/tmp

# Record user-space branches for a standalone binary:
(device) /data/local/tmp # simpleperf record -e arm_spe_0/branch_filter=1,jitter=1/:u \
                           -c 4096 ./<binary_name>

# Record system-wide (user + kernel) branches for 10 seconds with compression:
(device) /data/local/tmp # simpleperf record -e arm_spe_0/branch_filter=1,jitter=1/ \
                           -c 16384 -a --duration 10 -z -o perf.data
```

### Recommended event options and flags

- **`branch_filter=1`**: Instructs SPE hardware to write only branch records to the AUX buffer. The
  sampling counter still counts all operations, so `branch_filter=1` preserves the same branch
  sample density while cutting AUX data volume by ~16x.
- **`jitter=1`**: Enables hardware pseudo-random perturbation on the sampling interval to prevent
  sampling bias when profiling tight periodic loops.
- **`:u` / `:k` modifiers**: Restrict SPE sampling to user space (`:u`) or kernel space (`:k`).
- **Sampling interval (`-c <count>`)**:
  - The kernel `arm_spe_pmu` driver only supports period-based sampling (`-c`), not frequency-based
    sampling (`-f`). If `-c` is omitted, `simpleperf` uses
    `/sys/bus/event_source/devices/arm_spe_0/caps/min_interval` (typically `1024`, or `4096` if
    unreadable).
  - At `-c 1024` with `branch_filter=1`, system-wide (`-a`) recording can generate ~40 MB/s of AUX
    data. Increase `-c` (for example `-c 16384` or `-c 65536`) to lower overhead and file size on
    longer or system-wide runs.
  - Sample counts are not scaled by `-c`, so only merge recordings collected with the same `-c`
    interval.
- **AUX buffer management (`--aux-buffer-size`, `--aux-flush-interval`, `-z`)**:
  - `--aux-buffer-size` sets the per-CPU kernel AUX ring buffer size (default `4m`; must be page
    aligned and a power of two).
  - `--aux-flush-interval` sets how often `simpleperf` flushes AUX data (default `100` ms).
  - `-z` compresses records and AUX data using zstd before writing `perf.data`.

## Converting SPE data

Converting SPE data into AutoFDO or BOLT text profiles requires reading the ARM64 ELF binaries so
`simpleperf inject` can map virtual addresses to file offsets and decode instructions to synthesize
execution ranges.

### Userspace binaries (AutoFDO and BOLT)

```sh
# Direct conversion on device (writes perf_inject.data in AutoFDO text format):
(device) /data/local/tmp # simpleperf inject -i perf.data --binary <binary_name> \
                           -o perf_inject.data

# Convert to BOLT format instead:
(device) /data/local/tmp # simpleperf inject -i perf.data --binary <binary_name> \
                           --output bolt -o perf_inject_bolt.data
```

To reduce storage and transfer size, you can first convert `perf.data` on the device into the
compact `branch-list` protobuf format (which deduplicates identical branch edges and not-taken
conditional branch samples by execution count), and later convert or merge `branch-list` files on
the host:

```sh
(device) /data/local/tmp # simpleperf inject -i perf.data --output branch-list -z \
                           -o branch_list.data
(device) /data/local/tmp # exit
(host) $ adb pull /data/local/tmp/branch_list.data
(host) $ simpleperf inject -i branch_list.data --binary <binary_name> \
         --symdir <unstripped_binary_dir> -o perf_inject.data
```

Multiple `perf.data` or `branch_list.data` files recorded with the same `-c` interval can be merged
in a single `simpleperf inject -i file1,file2,...` invocation.

### Kernel (`vmlinux`) and kernel modules

```sh
# 1. Record kernel SPE branch samples on device and convert to branch-list:
(device) /data/local/tmp # simpleperf record -e arm_spe_0/branch_filter=1,jitter=1/:k \
                           -c 16384 -a --duration 60 -z -o perf.data
(device) /data/local/tmp # simpleperf inject -i perf.data --output branch-list \
                           --binary kernel.kallsyms -z -o kernel_branch.data

# 2. Pull to host and convert using the matching unstripped vmlinux:
(host) $ adb pull /data/local/tmp/kernel_branch.data
(host) $ simpleperf inject -i kernel_branch.data --binary kernel.kallsyms \
         --symdir <dir_containing_vmlinux> -o kernel.autofdo
(host) $ create_llvm_prof --profiler text --binary=<dir_containing_vmlinux>/vmlinux \
         --profile=kernel.autofdo --out=kernel.llvm_profdata \
         --prof_sym_list=false --format=extbinary
```

## A complete example: `spe_test_loop.cpp`

`spe_test_loop.cpp` ([source](../runtest/spe_test_loop.cpp), [Android.bp](../runtest/Android.bp))
demonstrates the end-to-end workflow from recording SPE data to rebuilding with AutoFDO.

**Step 1: Build `spe_test_loop`**

```sh
(host) <AOSP>$ . build/envsetup.sh
(host) <AOSP>$ lunch aosp_arm64-trunk_staging-userdebug
(host) <AOSP>$ m spe_test_loop simpleperf_ndk
```

**Step 2: Run `spe_test_loop` on device and record SPE branch data**

```sh
(host) <AOSP>$ adb root
(host) <AOSP>$ adb push $ANDROID_PRODUCT_OUT/system/bin/spe_test_loop /data/local/tmp/
(host) <AOSP>$ adb shell
(device) / # cd /data/local/tmp
(device) /data/local/tmp # chmod a+x spe_test_loop
(device) /data/local/tmp # simpleperf record -e arm_spe_0/branch_filter=1,jitter=1/:u \
                           -c 1024 ./spe_test_loop
(device) /data/local/tmp # simpleperf inject -i perf.data --output branch-list \
                           -o branch_list.data
(device) /data/local/tmp # exit
(host) <AOSP>$ adb pull /data/local/tmp/branch_list.data
```

**Step 3: Convert to AutoFDO LLVM profile on host**

```sh
(host) <AOSP>$ simpleperf inject -i branch_list.data --binary spe_test_loop \
               --symdir $ANDROID_PRODUCT_OUT/symbols/system/bin \
               -o perf_inject_spe_test_loop.data
(host) <AOSP>$ cat perf_inject_spe_test_loop.data
6
4104-4118:1
4148-4150:2
4164-4178:37
4180-418c:1
4190-41a4:1791
41a8-41a8:1
0
4
4144->4104:1
4150->4180:1
4178->4164:36
41a4->4190:1789
// build_id: 0xabc72d01dd75dd5e24816b6596b816c900000000
// /data/local/tmp/spe_test_loop

(host) <AOSP>$ create_llvm_prof -profile perf_inject_spe_test_loop.data -profiler text \
               -binary $ANDROID_PRODUCT_OUT/symbols/system/bin/spe_test_loop \
               -out spe_test_loop.afdo -format extbinary
```

Note: Do not pass `--use_lbr=false` to `create_llvm_prof`; `simpleperf inject` already synthesizes
the range counts expected by `create_llvm_prof`'s default LBR/range mode.

**Step 4: Apply the AutoFDO profile when building `spe_test_loop`**

Follow Step 4 of [collect_etm_data_for_autofdo.md](./collect_etm_data_for_autofdo.md) (registering
`spe_test_loop.afdo` in `toolchain/pgo-profiles/sampling/` and enabling `afdo: true` on
`spe_test_loop` in `system/extras/simpleperf/runtest/Android.bp`), rebuild `m spe_test_loop`, and
confirm `-fprofile-sample-use=.../spe_test_loop.afdo` in `out/verbose.log.gz`.

To optimize `spe_test_loop` with BOLT instead, generate `--output bolt`, strip trailing `//`
comment lines (`sed -i '/^\/\//d'`), and run `perf2bolt --pa` followed by `llvm-bolt` as shown in
[collect_brbe_data_for_autofdo.md](./collect_brbe_data_for_autofdo.md).

## Related docs

- [Arm Architecture Reference Manual for A-profile architecture (SPE)][arm-arm]
- [Collect ETM data for AutoFDO](./collect_etm_data_for_autofdo.md)
- [Collect BRBE data for AutoFDO and BOLT](./collect_brbe_data_for_autofdo.md)
- [AutoFDO tool (`create_llvm_prof`)](https://github.com/google/autofdo)
- [BOLT post-link optimizer](https://github.com/llvm/llvm-project/tree/main/bolt)

[arm-arm]: https://developer.arm.com/documentation/ddi0487/latest/
