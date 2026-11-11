#!/usr/bin/env python3
#
# Copyright (C) 2021 The Android Open Source Project
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
"""test_utils.py: utils for testing.
"""

import logging
from multiprocessing.connection import Connection
import os
from pathlib import Path
import re
import shutil
import sys
import subprocess
import time
from typing import List, Optional, Tuple, Union
import unittest

from simpleperf_utils import remove, get_android_top, AdbHelper, is_windows, bytes_to_str

INFERNO_SCRIPT = str(Path(__file__).parents[1] / ('inferno.bat' if is_windows() else 'inferno.sh'))
IS_ATEST: bool = True


def run_unit_tests(custom_module_name):
    import sys
    main_module = sys.modules['__main__']
    for name, obj in vars(main_module).items():
        if isinstance(obj, type) and issubclass(obj, unittest.TestCase):
            if obj.__module__ == '__main__':
                obj.__module__ = custom_module_name
    unittest.main()


def build_testdata(testdata_dir: Path):
    # Ensure the base directory exists
    testdata_dir.mkdir(parents=True, exist_ok=True)

    script_test_dir = Path(__file__).resolve().parent
    script_dir = script_test_dir.parent
    project_root = script_dir.parent

    # Prioritized list of sources
    source_dirs = [
        script_test_dir / 'script_testdata',
        script_test_dir / 'testdata',
        project_root / 'testdata',
        project_root / 'demo',
        project_root / 'runtest',
    ]

    # Add Android tree paths if available
    android_top = get_android_top()
    if android_top:
        source_dirs.extend([
            android_top / 'system/extras/simpleperf/runtest',
            android_top / 'system/extras/simpleperf/testdata',
        ])

    for source_dir in source_dirs:
        if not source_dir.is_dir():
            continue
        for src_path in source_dir.iterdir():
            dest_path = testdata_dir / src_path.name
            # The "idempotent" check: skip if the file/folder already exists
            # in our destination to prevent redundant work.
            if dest_path.exists():
                continue

            if src_path.suffix == ".bp":
                continue

            try:
                if src_path.is_file():
                    # copy2 preserves metadata like timestamps
                    shutil.copy2(src_path, dest_path)
                elif src_path.is_dir():
                    # dirs_exist_ok (Py 3.8+) allows merging if folders overlap
                    shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
            except (IOError, OSError) as e:
                # Log the error but keep going so one bad file doesn't break the test suite
                print(
                    f"Warning: Failed to copy {src_path} to {dest_path}: {e}")


class TestHelper:
    """ Keep global test options. """

    def __init__(self):
        raise RuntimeError("TestHelper is a static utility class and should not be instantiated.")

    @classmethod
    def init(
            cls, test_dir: str, testdata_dir: str, use_browser: bool, ndk_path: Optional[str],
            device_serial_number: Optional[str],
            progress_conn: Optional[Connection]):
        """
            When device_serial_number is None, no Android device is used.
            When device_serial_number is '', use the default Android device.
            When device_serial_number is not empty, select Android device by serial number.
        """
        cls.script_dir = Path(__file__).resolve().parents[1]
        cls.test_base_dir = Path(test_dir).resolve()
        cls.test_base_dir.mkdir(parents=True, exist_ok=True)
        cls.testdata_dir = Path(testdata_dir).resolve()
        cls.browser_option = [] if use_browser else ['--no_browser']
        cls.ndk_path = ndk_path
        cls.progress_conn = progress_conn
        cls.min_android_version = 10
        cls._gui_supported = None
        cls._is_emulator = None

        # Logs can come from multiple processes. So use append mode to avoid overwrite.
        if IS_ATEST:
            cls.log_fh = sys.stdout
            logging.basicConfig(level=logging.ERROR)
        else:
            cls.log_fh = open(cls.test_base_dir / 'test.log', 'a')
            logging.getLogger().handlers.clear()
            logging.getLogger().addHandler(logging.StreamHandler(cls.log_fh))
            os.close(sys.stderr.fileno())
            os.dup2(cls.log_fh.fileno(), sys.stderr.fileno())

        if device_serial_number is not None:
            if device_serial_number:
                os.environ['ANDROID_SERIAL'] = device_serial_number
            cls.adb = AdbHelper(enable_switch_to_root=True)
            cls.android_version = cls.adb.get_android_version()
            cls.device_features = None
            cls.adb.run(['shell', 'input', 'keyevent', 'KEYCODE_WAKEUP'])
            cls.adb.run(['shell', 'wm', 'dismiss-keyguard'])

    @classmethod
    def log(cls, s: str):
        cls.log_fh.write(s + '\n')
        # Child processes can also write to log file, so flush it immediately to keep the order.
        cls.log_fh.flush()

    @classmethod
    def testdata_path(cls, testdata_name: str) -> str:
        """ Return the path of a test data. """
        # Define candidate locations in order of priority
        candidates = [
            cls.testdata_dir / testdata_name,
            Path(__file__).resolve().parents[1] / 'test/script_testdata' / testdata_name
        ]

        android_top = get_android_top()
        if android_top:
            top = android_top / 'system/extras/simpleperf'
            candidates.extend([
                top / 'scripts/test/script_testdata' / testdata_name,
                top / 'testdata' / testdata_name,
                top / 'demo' / testdata_name
            ])

        # Return the first one that actually exists
        for path in candidates:
            if path.exists():
                return str(path)

        # Fallback to the first path if none exist (standard behavior for this method)
        return str(candidates[0])

    @classmethod
    def get_test_dir(cls, test_name: str) -> Path:
        """ Return the dir to run a test. """
        return cls.test_base_dir / test_name

    @classmethod
    def script_path(cls, script_name: str) -> str:
        """ Return the dir of python scripts. """
        return str(cls.script_dir / script_name)

    @classmethod
    def get_device_features(cls):
        if cls.device_features is None:
            args = [sys.executable, cls.script_path(
                'run_simpleperf_on_device.py'), 'list', '--show-features']
            output = subprocess.check_output(args, stderr=TestHelper.log_fh)
            output = bytes_to_str(output)
            cls.device_features = output.split()
        return cls.device_features

    @classmethod
    def is_trace_offcpu_supported(cls):
        return 'trace-offcpu' in cls.get_device_features()

    @classmethod
    def is_emulator(cls) -> bool:
        if cls._is_emulator is None:
            # Match Build.IS_EMULATOR: ro.boot.qemu on Android >= 12, ro.kernel.qemu on < 12.
            prop = 'ro.boot.qemu' if cls.android_version >= 12 else 'ro.kernel.qemu'
            cls._is_emulator = cls.adb.get_property(prop) == '1'
        return cls._is_emulator

    @classmethod
    def get_32bit_abi(cls):
        if not cls.adb.is_device_available():
            return None
        prop = cls.adb.get_property('ro.product.cpu.abilist32')
        return prop.strip().split(',')[0] if prop else None

    @classmethod
    def get_kernel_version(cls) -> Tuple[int]:
        output = cls.adb.check_run_and_return_output(['shell', 'uname', '-r'])
        m = re.search(r'^(\d+)\.(\d+)', output)
        assert m
        return (int(m.group(1)), int(m.group(2)))

    @classmethod
    def write_progress(cls, progress: str):
        if cls.progress_conn:
            cls.progress_conn.send(progress)

    @classmethod
    def meets_min_android_version(cls) -> bool:
        return cls.android_version >= cls.min_android_version

    @classmethod
    def is_gui_supported(cls) -> bool:
        if cls._gui_supported is None:
            try:
                import tkinter
                root = tkinter.Tk()
                root.destroy()
                cls._gui_supported = True
            except Exception:
                cls._gui_supported = False
        return cls._gui_supported


class TestBase(unittest.TestCase):
    def setUp(self):
        """ Run each test in a separate dir. """
        self.test_dir = TestHelper.get_test_dir(f'{self.__class__.__name__}.{self._testMethodName}')
        self.test_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(self.test_dir)
        TestHelper.log(f'begin test {self.__class__.__name__}.{self._testMethodName}')

    def run(self, result=None):
        start_time = time.time()
        ret = super(TestBase, self).run(result)
        if result.errors and result.errors[-1][0] == self:
            status = 'FAILED'
            err_info = result.errors[-1][1]
        elif result.failures and result.failures[-1][0] == self:
            status = 'FAILED'
            err_info = result.failures[-1][1]
        elif result.skipped and result.skipped[-1][0] == self:
            status = 'SKIPPED'
        else:
            status = 'OK'

        time_taken = time.time() - start_time
        TestHelper.log(
            'end test %s.%s %s (%.3fs)' %
            (self.__class__.__name__, self._testMethodName, status, time_taken))
        if status == 'FAILED':
            TestHelper.log(err_info)

        # Remove test data for passed tests to save space.
        if status == 'OK':
            remove(self.test_dir)
        TestHelper.write_progress(
            '%s.%s  %s  %.3fs' %
            (self.__class__.__name__, self._testMethodName, status, time_taken))
        return ret

    def run_cmd(self, args: List[str], return_output=False, drop_output=True) -> str:
        if args[0] == 'report_html.py' or args[0] == INFERNO_SCRIPT:
            args += TestHelper.browser_option
        if TestHelper.ndk_path:
            if args[0] in ['app_profiler.py', 'binary_cache_builder.py', 'pprof_proto_generator.py',
                           'report_html.py', 'annotate.py']:
                args += ['--ndk_path', TestHelper.ndk_path]

        if args[0].endswith('.py'):
            python_exe = sys.executable if sys.executable else 'python3'
            module_name = args[0][:-3].replace('/', '.').replace('\\', '.')
            args = [python_exe, '-m', module_name] + args[1:]

        env = os.environ.copy()
        zip_root = str(Path(__file__).resolve().parents[2])
        scripts_dir = os.path.join(zip_root, 'scripts')

        current_path = env.get('PYTHONPATH', '')
        path_list: list[str] = current_path.split(os.pathsep) if current_path else []

        # Add your paths
        for p in [scripts_dir, zip_root]:
            if p not in path_list:
                path_list.insert(0, p)  # insert at start to keep priority

        android_top = get_android_top()
        if android_top:
            source_scripts_dir = android_top / 'system/extras/simpleperf/scripts'
            source_root = android_top / 'system/extras/simpleperf'
            for p in [source_root, source_scripts_dir]:
                if p not in path_list:
                    path_list.insert(0, str(p))

        # Prepend the directory containing the scripts under test so it takes priority over
        # ANDROID_BUILD_TOP/system/extras/simpleperf/scripts:
        # - system/extras/simpleperf/scripts (for system/extras/simpleperf/scripts/test/)
        # - prebuilts/simpleperf (for prebuilts/simpleperf/test/, which has no scripts/ subdir)
        local_scripts_dir = str(Path(__file__).resolve().parents[1])
        if local_scripts_dir in path_list:
            path_list.remove(local_scripts_dir)
        path_list.insert(0, local_scripts_dir)

        env['PYTHONPATH'] = os.pathsep.join(path_list)

        use_shell = args[0].endswith('.bat')

        if return_output:
            stdout_fd = subprocess.PIPE
            drop_output = False
        elif drop_output:
            stdout_fd = subprocess.DEVNULL
        else:
            stdout_fd = None

        try:
            subproc = subprocess.Popen(args, stdout=stdout_fd,
                                       stderr=subprocess.PIPE, shell=use_shell, env=env)
            stdout_data, stderr_data = subproc.communicate()
            output_data = bytes_to_str(stdout_data)
            stderr_data = bytes_to_str(stderr_data)
            returncode = subproc.returncode

        except OSError:
            returncode = None
            stderr_data = "OSError"

        self.assertEqual(returncode, 0, msg=f"failed to run cmd: {args}\nstderr: {stderr_data}")

        if return_output:
            return output_data
        return ''

    def check_strings_in_file(self, filename, strings: List[Union[str, re.Pattern]]):
        self.check_exist(filename=filename)
        with open(filename, 'r') as fh:
            self.check_strings_in_content(fh.read(), strings)

    def check_exist(self, filename=None, dirname=None):
        if filename:
            self.assertTrue(os.path.isfile(filename), filename)
        if dirname:
            self.assertTrue(os.path.isdir(dirname), dirname)

    def check_strings_in_content(self, content: str, strings: List[Union[str, re.Pattern]]):
        fulfilled = []
        for s in strings:
            if isinstance(s, re.Pattern):
                fulfilled.append(s.search(content))
            else:
                pattern = re.escape(s).replace(r'\ ', r'\s*')
                fulfilled.append(re.search(pattern, content))
        self.check_fulfilled_entries(fulfilled, strings)

    def check_fulfilled_entries(self, fulfilled, entries):
        failed_entries = []
        for ok, entry in zip(fulfilled, entries):
            if not ok:
                failed_entries.append(entry)

        if failed_entries:
            self.fail('failed in below entries: %s' % (failed_entries,))

    def wait_for_pid(self,
                     package_name: str,
                     timeout: float = 10.0,
                     to_exit: bool = False,
                     poll_interval: float = 0.5,
                     ) -> int:
        """
        Waits for a specific Android process to either start or exit.

        Args:
            package_name: The name of the package/process to check.
            timeout: Maximum time to wait in seconds. Defaults to 10.0.
            to_exit: If True, waits for the process to terminate. If False, waits for it to start.
            poll_interval: Time in seconds to sleep between polls. Defaults to 0.5.

        Returns:
            int: The PID of the process if waiting to start, or -1 if waiting to exit.
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            success, output = TestHelper.adb.run_and_return_output(['shell', 'pidof', package_name])

            if not to_exit:
                # We are waiting for the process to START
                if success and output:
                    pids: list[str] = output.strip().split()
                    if pids:
                        try:
                            return int(pids[0])
                        except ValueError:
                            # Ignore non-integer output (e.g., adb warnings) and keep polling
                            pass
            else:
                # We are waiting for the process to EXIT
                if not success:
                    return -1

            time.sleep(poll_interval)

        action: str = 'exit' if to_exit else 'start'
        self.fail(f"Timed out after {timeout}s waiting for process '{package_name}' to {action}")
