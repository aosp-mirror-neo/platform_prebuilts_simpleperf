#!/usr/bin/env python3
#
# Copyright (C) 2026 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""Starts (headless by default), checks status of, lists, or stops Android test AVDs."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Dict, List, Optional, Set, Tuple

ACTIONS = {'start', 'status', 'stop', 'list'}


def find_sdk_tool(name: str, subdir: str, required: bool = True) -> Optional[str]:
    sdk = Path(os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
               or (Path.home() / 'Android/Sdk'))
    found = shutil.which(name, path=str(sdk / subdir)) or shutil.which(name)
    if not found and required:
        sys.exit(f"Error: Could not find '{name}' under {sdk / subdir} or in PATH.")
    return found


def avd_root() -> Path:
    return Path(os.environ.get('ANDROID_AVD_HOME') or (Path.home() / '.android/avd'))


def avd_info(avd: str) -> Tuple[Optional[Path], str, float]:
    """Returns (data_dir, api_display_str, sort_key)."""
    root = avd_root()
    ini = root / f'{avd}.ini'
    data_dir: Optional[Path] = None
    target_str: Optional[str] = None
    if ini.is_file():
        try:
            for line in ini.read_text(encoding='utf-8', errors='ignore').splitlines():
                if line.startswith('path='):
                    p = Path(line.split('=', 1)[1].strip())
                    if p.is_dir():
                        data_dir = p
                elif line.startswith('target='):
                    target_str = line.split('=', 1)[1].strip()
        except OSError:
            pass

    if not data_dir:
        fallback = root / f'{avd}.avd'
        if fallback.is_dir():
            data_dir = fallback

    api_display = '-'
    sort_key = 999.0
    if target_str:
        m = re.search(r'android-(\d+(?:\.\d+)?)', target_str)
        if m:
            val = float(m.group(1))
            sort_key = val
            api_display = str(int(val)) if val.is_integer() else str(val)
    return data_dir, api_display, sort_key


def discover_avds(emu: Optional[str]) -> List[str]:
    avds: List[str] = []
    if emu:
        try:
            res = subprocess.run([emu, '-list-avds'], capture_output=True, text=True, check=False)
            for line in res.stdout.splitlines():
                line = line.strip()
                if line and ' | ' not in line:
                    avds.append(line)
        except OSError:
            pass
    if not avds:
        root = avd_root()
        if root.is_dir():
            avds = [p.stem for p in root.glob('*.ini')]
    # Sort by API level ascending, then by name
    return sorted(avds, key=lambda a: (avd_info(a)[2], a))


def run_adb(adb: str, serial: str, *args: str, timeout: Optional[float] = 10.0) -> str:
    try:
        res = subprocess.run([adb, '-s', serial, *args], capture_output=True, text=True,
                             check=False, timeout=timeout)
        return res.stdout.strip() if res.returncode == 0 else ''
    except subprocess.TimeoutExpired:
        return ''


def adb_states(adb: str) -> Dict[str, str]:
    out = subprocess.run([adb, 'devices'], capture_output=True, text=True, check=False).stdout
    states: Dict[str, str] = {}
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            states[parts[0]] = parts[1]
    return states


def running_emulators(adb: str, states: Dict[str, str]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Returns (avd_to_port, serial_to_avd) for running emulators."""
    serials = [s for s in states if s.startswith('emulator-')]
    avd_to_port: Dict[str, str] = {}
    serial_to_avd: Dict[str, str] = {}

    def resolve_name(serial: str) -> Tuple[str, str]:
        if states.get(serial) == 'device':
            props = run_adb(
                adb, serial, 'shell',
                'getprop ro.boot.qemu.avd_name; getprop ro.kernel.qemu.avd_name')
            for line in props.splitlines():
                name = line.strip()
                if name:
                    return serial, name
        emu_name = run_adb(adb, serial, 'emu', 'avd', 'name')
        for line in emu_name.splitlines():
            name = line.strip()
            if name and name != 'OK' and not name.startswith('KO'):
                return serial, name
        return serial, ''

    with ThreadPoolExecutor(max_workers=max(1, len(serials))) as pool:
        for serial, name in pool.map(resolve_name, serials):
            port = serial.split('-', 1)[1]
            if name:
                avd_to_port[name] = port
                serial_to_avd[serial] = name
            else:
                serial_to_avd[serial] = serial
    return avd_to_port, serial_to_avd


def is_port_free(port: int, used_ports: Set[int]) -> bool:
    if port in used_ports:
        return False
    for p in (port, port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.1)
            if s.connect_ex(('127.0.0.1', p)) == 0:
                return False
    return True


def next_free_port(used_ports: Set[int]) -> str:
    for port in range(5554, 5682, 2):
        if is_port_free(port, used_ports):
            used_ports.add(port)
            return str(port)
    sys.exit('Error: No available emulator ports found between 5554 and 5680.')


def is_avd_running(avd: str, port: str, states: Dict[str, str]) -> bool:
    if f'emulator-{port}' in states:
        return True
    if shutil.which('pgrep'):
        pattern = f'emulator.*(-avd {avd}( |$)|-port {port}( |$))'
        return subprocess.run(['pgrep', '-f', pattern], capture_output=True).returncode == 0
    return False


def wait_for_boot(adb: str, avd: str, port: str, timeout: int, log_dir: Path) -> bool:
    serial = f'emulator-{port}'
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        adb_timeout = min(10.0, max(0.1, remaining))
        if run_adb(adb, serial, 'shell', 'getprop', 'sys.boot_completed',
                   timeout=adb_timeout) == '1':
            run_adb(adb, serial, 'shell', 'input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard',
                    timeout=10.0)
            return True
        sleep_time = min(2.0, max(0.0, deadline - time.monotonic()))
        if sleep_time > 0:
            time.sleep(sleep_time)
    print(f'Warning: Timed out waiting for {avd} ({serial}). '
          f'Check {log_dir / f"emulator-{avd}-{port}.log"}', file=sys.stderr)
    return False


def relative_test_cmd() -> str:
    test_py = Path(__file__).resolve().with_name('test.py')
    try:
        rel = test_py.relative_to(Path.cwd())
        return f'./{rel}' if not str(rel).startswith('.') else str(rel)
    except ValueError:
        return str(test_py)


def print_status(adb: str, specs: List[Tuple[str, str]]) -> None:
    states = adb_states(adb)

    def probe(item: Tuple[str, str]) -> Tuple[str, str, str, str]:
        avd, port = item
        serial = f'emulator-{port}' if port != '-' else '-'
        state = states.get(serial, 'offline') if serial != '-' else 'offline'
        if state != 'device':
            _, api_display, _ = avd_info(avd)
            return avd, serial, state, api_display
        props = run_adb(
            adb, serial, 'shell', 'getprop ro.build.version.sdk; getprop sys.boot_completed')
        lines = props.splitlines()
        sdk = lines[0].strip() if lines else '?'
        booted = len(lines) > 1 and lines[1].strip() == '1'
        return avd, serial, ('ready' if booted else 'booting'), sdk

    with ThreadPoolExecutor(max_workers=max(1, len(specs))) as pool:
        rows = list(pool.map(probe, specs))

    avd_width = max(6, max(len(r[0]) for r in rows)) if rows else 6
    print(f"{'AVD':<{avd_width}} {'SERIAL':<16} {'STATE':<10} {'API':<8}")
    print(f"{'---':<{avd_width}} {'------':<16} {'-----':<10} {'---':<8}")
    ready = []
    for avd, serial, state, sdk in rows:
        print(f'{avd:<{avd_width}} {serial:<16} {state:<10} {sdk:<8}')
        if state == 'ready':
            ready.append(f'{avd}:{serial}')
    if ready:
        print(f"\nTest command:\n  DISPLAY= WAYLAND_DISPLAY= {relative_test_cmd()} -d "
              f"{' '.join(ready)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('targets', nargs='*', metavar='[start|status|stop|list] [AVD[:PORT]]',
                        help='Action and optional AVD or AVD:PORT targets (default: start all)')
    parser.add_argument('--window', action='store_true', help='Show emulator GUI windows.')
    parser.add_argument('--no-wait', action='store_true', help='Do not wait for boot completion.')
    parser.add_argument('--timeout', type=int, default=180,
                        help='Boot timeout in seconds (default: 180).')
    args = parser.parse_args()

    targets = list(args.targets)
    action = targets.pop(0) if (targets and targets[0] in ACTIONS) else 'start'

    adb = find_sdk_tool('adb', 'platform-tools')
    subprocess.run([adb, 'start-server'], capture_output=True, check=False)

    emu = find_sdk_tool('emulator', 'emulator', required=(action == 'start'))
    discovered = discover_avds(emu)
    states = adb_states(adb)
    avd_to_port, serial_to_avd = running_emulators(adb, states)

    if action == 'list':
        print(f"{'AVD':<20} {'API':<8} {'SERIAL':<16} {'STATE':<10}")
        print(f"{'---':<20} {'---':<8} {'------':<16} {'-----':<10}")
        for avd in discovered:
            _, api_display, _ = avd_info(avd)
            port = avd_to_port.get(avd)
            serial = f'emulator-{port}' if port else '-'
            state = states.get(serial, 'offline') if port else 'offline'
            print(f'{avd:<20} {api_display:<8} {serial:<16} {state:<10}')
        return 0

    if action == 'status':
        specs: List[Tuple[str, str]] = []
        if targets:
            for t in targets:
                if ':' in t:
                    a, p = t.split(':', 1)
                elif t.startswith('emulator-'):
                    p = t.split('-', 1)[1]
                    a = serial_to_avd.get(t, t)
                elif t in avd_to_port:
                    a, p = t, avd_to_port[t]
                elif f'emulator-{t}' in states:
                    p = t
                    a = serial_to_avd.get(f'emulator-{t}', t)
                else:
                    a, p = t, '-'
                specs.append((a, p))
        else:
            for avd in discovered:
                specs.append((avd, avd_to_port.get(avd, '-')))
            # Include any running emulator serials not matched to discovered AVD names
            known_ports = {p for _, p in specs if p != '-'}
            for serial, state in states.items():
                if serial.startswith('emulator-'):
                    port = serial.split('-', 1)[1]
                    if port not in known_ports:
                        specs.append((serial_to_avd.get(serial, serial), port))
        print_status(adb, specs)
        return 0

    if action == 'stop':
        if not targets:
            # Stop all running emulators
            serials = [s for s in states if s.startswith('emulator-')]
            if not serials:
                print('No running emulators found.')
                return 0
            for serial in serials:
                avd_name = serial_to_avd.get(serial, serial)
                print(f'[stop] Stopping {avd_name} ({serial})...')
                run_adb(adb, serial, 'emu', 'kill')
            return 0

        for t in targets:
            if ':' in t:
                avd, port = t.split(':', 1)
                serial = f'emulator-{port}'
            elif t.startswith('emulator-'):
                serial = t
                avd = serial_to_avd.get(serial, serial)
            elif t in avd_to_port:
                avd = t
                serial = f'emulator-{avd_to_port[t]}'
            else:
                serial = f'emulator-{t}'
                avd = t
            if serial in states:
                print(f'[stop] Stopping {avd} ({serial})...')
                run_adb(adb, serial, 'emu', 'kill')
            else:
                print(f'[skip] {avd} ({serial}) is not online.')
        return 0

    # action == 'start'
    raw_targets = targets or discovered
    if not raw_targets:
        sys.exit('Error: No AVDs found to start. Create an AVD or check ANDROID_AVD_HOME.')

    used_ports: Set[int] = set()
    for serial in states:
        if serial.startswith('emulator-'):
            try:
                used_ports.add(int(serial.split('-', 1)[1]))
            except ValueError:
                pass

    specs_to_start: List[Tuple[str, str]] = []
    for t in raw_targets:
        if ':' in t:
            avd, port = t.split(':', 1)
            used_ports.add(int(port))
        elif t in avd_to_port:
            avd, port = t, avd_to_port[t]
        else:
            avd = t
            port = next_free_port(used_ports)
        specs_to_start.append((avd, port))

    assert emu is not None
    uid_suffix = str(os.getuid()) if hasattr(os, 'getuid') else 'shared'
    default_log_dir = Path(tempfile.gettempdir()) / f'simpleperf-emulators-{uid_suffix}'
    log_dir = Path(os.environ.get('EMULATOR_LOG_DIR') or default_log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    for avd, port in specs_to_start:
        serial = f'emulator-{port}'
        if is_avd_running(avd, port, states):
            print(f'[skip] {avd} ({serial}) is already running.')
            continue
        data_dir, _, _ = avd_info(avd)
        if data_dir and data_dir.is_dir():
            for lock in [*data_dir.glob('*.lock'), *data_dir.glob('*/*.lock')]:
                if lock.is_dir() and not lock.is_symlink():
                    shutil.rmtree(lock, ignore_errors=True)
                else:
                    lock.unlink(missing_ok=True)
        cmd = [emu, '-avd', avd, '-port', port, '-no-audio', '-no-boot-anim',
               '-no-snapshot-save', '-netdelay', 'none', '-netspeed', 'full']
        env = os.environ.copy()
        if not args.window:
            cmd += ['-no-window', '-gpu', 'swiftshader_indirect']
            env['DISPLAY'] = ''
            env['WAYLAND_DISPLAY'] = ''
        log_file = log_dir / f'emulator-{avd}-{port}.log'
        mode = 'windowed' if args.window else 'headless'
        print(f'[start] Launching {avd} on {serial} ({mode}) -> {log_file}')
        with open(log_file, 'ab') as log_fh:
            subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log_fh,
                             stderr=subprocess.STDOUT, env=env, start_new_session=True)

    if args.no_wait:
        return 0

    print(f'Waiting for emulators to finish booting (timeout: {args.timeout}s)...')
    with ThreadPoolExecutor(max_workers=max(1, len(specs_to_start))) as pool:
        results = list(pool.map(
            lambda sp: wait_for_boot(adb, sp[0], sp[1], args.timeout, log_dir), specs_to_start))
    print()
    print_status(adb, specs_to_start)
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
