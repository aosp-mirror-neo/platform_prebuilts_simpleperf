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

import unittest
import sys
from pathlib import Path


import simpleperf_utils
from test.test_utils import build_testdata, TestHelper


def main():
    simpleperf_utils.Log.init('error')
    testdata_dir = 'testdata'
    TestHelper.init(test_dir='test_dir', testdata_dir=testdata_dir,
                    use_browser=False, ndk_path=None, device_serial_number="", progress_conn=None)
    build_testdata(Path(TestHelper.testdata_dir))

    test_targets = [
        # "test.api_profiler_test",
        # We can run the annotate test because it needs Texttable module.
        # "test.annotate_test",
        #
        # "test.app_profiler_test",
        # "test.app_test",
        ##
        # "test.binary_cache_builder_test",
        ##
        # "test.cpp_app_test",
        #
        # We can run the unwind test because it needs Texttable module.
        # "test.debug_unwind_reporter_test",
        ##
        # "test.etm_stack_test",
        # "test.gecko_profile_generator_test",
        ##
        # "test.inferno_test",
        # "test.java_app_test",
        # "test.kotlin_app_test",
        # "test.pprof_proto_generator_test",
        # "test.purgatorio_test",
        # "test.report_html_test",
        "test.report_lib_test",
        ##
        # "test.report_sample_test",
        # "test.run_simpleperf_on_device_test",
        # "test.sample_filter_test",
        # "test.stackcollapse_test",
        ##
        # Full tools_test needs demo/ sources; run the Bionic symbol version check on host.
        "test.tools_test.TestTools.test_android_simpleperf_libc_symbol_versions",
    ]

    suite = unittest.TestSuite()
    for target in test_targets:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromName(target))

    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())


if __name__ == "__main__":
    main()
