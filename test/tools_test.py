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

import io
import os
from pathlib import Path
import subprocess
import sys
from typing import List, Tuple

from binary_cache_builder import BinaryCacheBuilder
from simpleperf_utils import (
    AdbHelper, Addr2Nearestline, AddrRange, BinaryFinder, Disassembly, Objdump,
    ReadElf, SourceFileSearcher, bytes_to_str, get_script_dir, is_windows, remove)
from . test_utils import TestBase, TestHelper


class TestTools(TestBase):
    def test_addr2nearestline(self):
        self.run_addr2nearestline_test(True)
        self.run_addr2nearestline_test(False)

    def run_addr2nearestline_test(self, with_function_name):
        test_map = {
            '/simpleperf_runtest_two_functions_arm64': [
                {
                    'func_addr': 0x112c,
                    'addr': 0x112c,
                    'source': 'system/extras/simpleperf/runtest/two_functions.cpp:20',
                    'function': 'main',
                },
                {
                    'func_addr': 0x104c,
                    'addr': 0x105c,
                    'source': "system/extras/simpleperf/runtest/two_functions.cpp:7",
                    'function': "Function1()",
                },
            ],
            '/simpleperf_runtest_two_functions_arm': [
                {
                    'func_addr': 0x1304,
                    'addr': 0x131a,
                    'source': """system/extras/simpleperf/runtest/two_functions.cpp:8
                                 system/extras/simpleperf/runtest/two_functions.cpp:22""",
                    'function': """Function1()
                                   main""",
                },
                {
                    'func_addr': 0x1304,
                    'addr': 0x131c,
                    'source': """system/extras/simpleperf/runtest/two_functions.cpp:16
                                 system/extras/simpleperf/runtest/two_functions.cpp:23""",
                    'function': """Function2()
                                   main""",
                }
            ],
            '/simpleperf_runtest_two_functions_x86_64': [
                {
                    'func_addr': 0x19e0,
                    'addr': 0x19f6,
                    'source': """system/extras/simpleperf/runtest/two_functions.cpp:8
                                 system/extras/simpleperf/runtest/two_functions.cpp:22""",
                    'function': """Function1()
                                   main""",
                },
                {
                    'func_addr': 0x19e0,
                    'addr': 0x1a19,
                    'source': """system/extras/simpleperf/runtest/two_functions.cpp:16
                                 system/extras/simpleperf/runtest/two_functions.cpp:23""",
                    'function': """Function2()
                                   main""",
                }
            ],
            '/simpleperf_runtest_two_functions_x86': [
                {
                    'func_addr': 0x16e0,
                    'addr': 0x16f6,
                    'source': """system/extras/simpleperf/runtest/two_functions.cpp:8
                                 system/extras/simpleperf/runtest/two_functions.cpp:22""",
                    'function': """Function1()
                                   main""",
                },
                {
                    'func_addr': 0x16e0,
                    'addr': 0x1710,
                    'source': """system/extras/simpleperf/runtest/two_functions.cpp:16
                                 system/extras/simpleperf/runtest/two_functions.cpp:23""",
                    'function': """Function2()
                                   main""",
                }
            ],
        }

        binary_finder = BinaryFinder(TestHelper.testdata_dir, ReadElf(TestHelper.ndk_path))
        addr2line = Addr2Nearestline(TestHelper.ndk_path, binary_finder, with_function_name)
        for dso_path in test_map:
            test_addrs = test_map[dso_path]
            for test_addr in test_addrs:
                addr2line.add_addr(dso_path, None, test_addr['func_addr'], test_addr['addr'])
        addr2line.convert_addrs_to_lines(4)
        for dso_path in test_map:
            dso = addr2line.get_dso(dso_path)
            self.assertIsNotNone(dso, dso_path)
            test_addrs = test_map[dso_path]
            for test_addr in test_addrs:
                expected_files = []
                expected_lines = []
                expected_functions = []
                for line in test_addr['source'].split('\n'):
                    items = line.split(':')
                    expected_files.append(items[0].strip())
                    expected_lines.append(int(items[1]))
                for line in test_addr['function'].split('\n'):
                    expected_functions.append(line.strip())
                self.assertEqual(len(expected_files), len(expected_functions))

                if with_function_name:
                    expected_source = list(zip(expected_files, expected_lines, expected_functions))
                else:
                    expected_source = list(zip(expected_files, expected_lines))

                actual_source = addr2line.get_addr_source(dso, test_addr['addr'])
                if is_windows():
                    self.assertIsNotNone(actual_source, 'for %s:0x%x' %
                                         (dso_path, test_addr['addr']))
                    for i, source in enumerate(actual_source):
                        new_source = list(source)
                        new_source[0] = new_source[0].replace('\\', '/')
                        actual_source[i] = tuple(new_source)

                self.assertEqual(actual_source, expected_source,
                                 'for %s:0x%x, expected source %s, actual source %s' %
                                 (dso_path, test_addr['addr'], expected_source, actual_source))

    def test_addr2nearestline_parse_output(self):
        output = """
0x104c
system/extras/simpleperf/runtest/two_functions.cpp:6:0

0x1094
system/extras/simpleperf/runtest/two_functions.cpp:9:10

0x10bb
system/extras/simpleperf/runtest/two_functions.cpp:11:1

0x10bc
system/extras/simpleperf/runtest/two_functions.cpp:13:0

0x1104
system/extras/simpleperf/runtest/two_functions.cpp:16:10

0x112b
system/extras/simpleperf/runtest/two_functions.cpp:18:1

0x112c
system/extras/simpleperf/runtest/two_functions.cpp:20:0

0x113c
system/extras/simpleperf/runtest/two_functions.cpp:22:5

0x1140
system/extras/simpleperf/runtest/two_functions.cpp:23:5

0x1147
system/extras/simpleperf/runtest/two_functions.cpp:21:3
        """
        dso = Addr2Nearestline.Dso(None)
        binary_finder = BinaryFinder(TestHelper.testdata_dir, ReadElf(TestHelper.ndk_path))
        addr2line = Addr2Nearestline(TestHelper.ndk_path, binary_finder, False)
        addr_map = addr2line.parse_line_output(output, dso)
        expected_addr_map = {
            0x104c: [('system/extras/simpleperf/runtest/two_functions.cpp', 6)],
            0x1094: [('system/extras/simpleperf/runtest/two_functions.cpp', 9)],
            0x10bb: [('system/extras/simpleperf/runtest/two_functions.cpp', 11)],
            0x10bc: [('system/extras/simpleperf/runtest/two_functions.cpp', 13)],
            0x1104: [('system/extras/simpleperf/runtest/two_functions.cpp', 16)],
            0x112b: [('system/extras/simpleperf/runtest/two_functions.cpp', 18)],
            0x112c: [('system/extras/simpleperf/runtest/two_functions.cpp', 20)],
            0x113c: [('system/extras/simpleperf/runtest/two_functions.cpp', 22)],
            0x1140: [('system/extras/simpleperf/runtest/two_functions.cpp', 23)],
            0x1147: [('system/extras/simpleperf/runtest/two_functions.cpp', 21)],
        }
        self.assertEqual(len(expected_addr_map), len(addr_map))
        for addr in expected_addr_map:
            expected_source_list = expected_addr_map[addr]
            source_list = addr_map[addr]
            self.assertEqual(len(expected_source_list), len(source_list))
            for expected_source, source in zip(expected_source_list, source_list):
                file_path = dso.file_id_to_name[source[0]]
                self.assertEqual(file_path, expected_source[0])
                self.assertEqual(source[1], expected_source[1])

    def test_objdump(self):
        test_map = {
            '/simpleperf_runtest_two_functions_arm64': {
                'start_addr': 0x112c,
                'len': 28,
                'expected_items': [
                    ('main', 0),
                    ('two_functions.cpp:20', 0),
                    ('1134:      	add	x29, sp, #0x10', 0x1134),
                ],
            },
            '/simpleperf_runtest_two_functions_arm': {
                'start_addr': 0x1304,
                'len': 40,
                'expected_items': [
                    ('main', 0),
                    ('two_functions.cpp:20', 0),
                    ('1318:      	bne	0x1312 <main+0xe>', 0x1318),
                ],
            },
            '/simpleperf_runtest_two_functions_x86_64': {
                'start_addr': 0x19e0,
                'len': 151,
                'expected_items': [
                    ('main', 0),
                    ('two_functions.cpp:20', 0),
                    (r'19f0:      	movl	%eax, 0x2462(%rip)', 0x19f0),
                ],
            },
            '/simpleperf_runtest_two_functions_x86': {
                'start_addr': 0x16e0,
                'len': 65,
                'expected_items': [
                    ('main', 0),
                    ('two_functions.cpp:20', 0),
                    (r'16f7:      	cmpl	$0x5f5e100, %ecx', 0x16f7),
                ],
            },
        }
        binary_finder = BinaryFinder(TestHelper.testdata_dir, ReadElf(TestHelper.ndk_path))
        objdump = Objdump(TestHelper.ndk_path, binary_finder)
        for dso_path in test_map:
            dso = test_map[dso_path]
            dso_info = objdump.get_dso_info(dso_path, None)
            self.assertIsNotNone(dso_info, dso_path)
            addr_range = AddrRange(dso['start_addr'], dso['len'])
            disassembly = objdump.disassemble_function(dso_info, addr_range)
            self.assertTrue(disassembly, dso_path)
            self._check_disassembly(disassembly, dso_path, dso)

            result = objdump.disassemble_functions(dso_info, [addr_range])
            self.assertTrue(result, dso_path)
            self.assertEqual(len(result), 1)
            self._check_disassembly(result[0], dso_path, dso)

    def _check_disassembly(self, disassembly: Disassembly, dso_path: str, dso) -> None:
        disassemble_code = disassembly.lines
        i = 0
        for expected_line, expected_addr in dso['expected_items']:
            found = False
            while i < len(disassemble_code):
                line, addr = disassemble_code[i]
                if addr == expected_addr and expected_line in line:
                    found = True
                    i += 1
                    break
                i += 1
            if not found:
                s = '\n'.join('%s:0x%x' % item for item in disassemble_code)
                self.fail('for %s, %s:0x%x not found in disassemble code:\n%s' %
                          (dso_path, expected_line, expected_addr, s))

    def test_objdump_parse_disassembly_for_functions(self):
        # Parse kernel disassembly.
        s = """
ffffffc008000000 <_text>:
; _text():
; arch/arm64/kernel/head.S:60
ffffffc008000000:      	ccmp	x18, #0x0, #0xd, pl
ffffffc008000004:      	b	0xffffffc009b2a37c <primary_entry>

ffffffc008000008 <$d.1>:
ffffffc008000008: 00 00 00 00  	.word	0x00000000
ffffffc0089bbb30 <readl>:
; readl():
; include/asm-generic/io.h:218
ffffffc0089bbb30:      	paciasp
ffffffc0089bbb34:      	stp	x29, x30, [sp, #-0x30]!
        """
        addr_ranges = [AddrRange(0xffffffc008000000, 8),
                       AddrRange(0xffffffc008000010, 10),
                       AddrRange(0xffffffc0089bbb30, 20)]
        binary_finder = BinaryFinder(TestHelper.testdata_dir, ReadElf(TestHelper.ndk_path))
        objdump = Objdump(TestHelper.ndk_path, binary_finder)
        result = objdump._parse_disassembly_for_functions(io.StringIO(s), addr_ranges)
        self.assertEqual(len(result), 3)
        self.assertEqual(
            result[0].lines,
            [('ffffffc008000000 <_text>:', 0xffffffc008000000),
             ('; _text():', 0),
             ('; arch/arm64/kernel/head.S:60', 0),
             ('ffffffc008000000:      	ccmp	x18, #0x0, #0xd, pl', 0xffffffc008000000),
             ('ffffffc008000004:      	b	0xffffffc009b2a37c <primary_entry>',
                0xffffffc008000004),
             ('', 0)])
        self.assertEqual(len(result[1].lines), 0)
        self.assertEqual(result[2].lines, [
            ('ffffffc0089bbb30 <readl>:', 0xffffffc0089bbb30),
            ('; readl():', 0),
            ('; include/asm-generic/io.h:218', 0),
            ('ffffffc0089bbb30:      	paciasp', 0xffffffc0089bbb30),
            ('ffffffc0089bbb34:      	stp	x29, x30, [sp, #-0x30]!', 0xffffffc0089bbb34),
            ('', 0)])

        # Parse user space library disassembly.
        s = """
0000000000200000 <art::gc::collector::ConcurrentCopying::ProcessMarkStack()>:
; art::gc::collector::ConcurrentCopying::ProcessMarkStack():
; art/runtime/gc/collector/concurrent_copying.cc:2121
  200000:      	stp	x29, x30, [sp, #-0x20]!
  200004:      	stp	x20, x19, [sp, #0x10]
        """
        addr_ranges = [AddrRange(0x200000, 8)]
        result = objdump._parse_disassembly_for_functions(io.StringIO(s), addr_ranges)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].lines, [
            ('0000000000200000 <art::gc::collector::ConcurrentCopying::ProcessMarkStack()>:',
                0x200000),
            ('; art::gc::collector::ConcurrentCopying::ProcessMarkStack():', 0),
            ('; art/runtime/gc/collector/concurrent_copying.cc:2121', 0),
            ('  200000:      	stp	x29, x30, [sp, #-0x20]!', 0x200000),
            ('  200004:      	stp	x20, x19, [sp, #0x10]', 0x200004),
            ('', 0)])

    def test_objdump_whole(self):
        binary_finder = BinaryFinder(TestHelper.testdata_dir, ReadElf(TestHelper.ndk_path))
        objdump = Objdump(TestHelper.ndk_path, binary_finder)
        dso_info = objdump.get_dso_info("/simpleperf_runtest_two_functions_arm64", None)
        disassembly = objdump.disassemble_whole(dso_info)
        self.assertEqual(len(disassembly), 98)
        self.assertEqual(disassembly[4492], '    118c: d61f0220     \tbr\tx17')

    def test_objdump_plt(self):
        binary_finder = BinaryFinder(TestHelper.testdata_dir, ReadElf(TestHelper.ndk_path))
        objdump = Objdump(TestHelper.ndk_path, binary_finder)
        dso_info = objdump.get_dso_info("/simpleperf_runtest_two_functions_arm64", None)
        symbols = objdump.get_plt_symbols(dso_info)
        self.assertEqual(len(symbols), 2)
        self.assertEqual(symbols, [(4464, 16, '__libc_init@plt'), (4480, 16, 'atoi@plt')])

    def test_readelf(self):
        test_map = {
            'simpleperf_runtest_two_functions_arm64': {
                'arch': 'arm64',
                'build_id': '0xb4f1b49b0fe9e34e78fb14e5374c930c00000000',
                'sections': ['.note.gnu.build-id', '.dynsym', '.text', '.rodata', '.eh_frame',
                             '.eh_frame_hdr', '.debug_info',  '.debug_line', '.symtab'],
            },
            'simpleperf_runtest_two_functions_arm': {
                'arch': 'arm',
                'build_id': '0x6b5c2ee980465d306b580c5a8bc9767f00000000',
            },
            'simpleperf_runtest_two_functions_x86_64': {
                'arch': 'x86_64',
            },
            'simpleperf_runtest_two_functions_x86': {
                'arch': 'x86',
            }
        }
        readelf = ReadElf(TestHelper.ndk_path)
        for dso_path in test_map:
            dso_info = test_map[dso_path]
            path = os.path.join(TestHelper.testdata_dir, dso_path)
            self.assertEqual(dso_info['arch'], readelf.get_arch(path))
            if 'build_id' in dso_info:
                self.assertEqual(dso_info['build_id'], readelf.get_build_id(path), dso_path)
            if 'sections' in dso_info:
                sections = readelf.get_sections(path)
                for section in dso_info['sections']:
                    self.assertIn(section, sections)
        self.assertEqual(readelf.get_arch('not_exist_file'), 'unknown')
        self.assertEqual(readelf.get_build_id('not_exist_file'), '')
        self.assertEqual(readelf.get_sections('not_exist_file'), [])

    def test_source_file_searcher(self):
        searcher = SourceFileSearcher(
            [TestHelper.testdata_path('SimpleperfExampleCpp'),
             TestHelper.testdata_path('SimpleperfExampleKotlin')])

        def format_path(path):
            return os.path.join(TestHelper.testdata_dir, path.replace('/', os.sep))
        # Find a C++ file with pure file name.
        self.assertEqual(
            format_path('SimpleperfExampleCpp/app/src/main/cpp/native-lib.cpp'),
            searcher.get_real_path('native-lib.cpp'))
        # Find a C++ file with an absolute file path.
        self.assertEqual(
            format_path('SimpleperfExampleCpp/app/src/main/cpp/native-lib.cpp'),
            searcher.get_real_path('/data/native-lib.cpp'))
        # Find a Java file.
        self.assertEqual(
            format_path(
                'SimpleperfExampleCpp/app/src/main/java/simpleperf/example/cpp/MainActivity.java'),
            searcher.get_real_path('cpp/MainActivity.java'))
        # Find a Kotlin file.
        self.assertEqual(
            format_path(
                'SimpleperfExampleKotlin/app/src/main/java/simpleperf/example/kotlin/' +
                'MainActivity.kt'),
            searcher.get_real_path('MainActivity.kt'))

    def test_is_elf_file(self):
        self.assertTrue(ReadElf.is_elf_file(TestHelper.testdata_path(
            'simpleperf_runtest_two_functions_arm')))
        with open('not_elf', 'wb') as fh:
            fh.write(b'\x90123')
        try:
            self.assertFalse(ReadElf.is_elf_file('not_elf'))
        finally:
            remove('not_elf')

    def test_binary_finder(self):
        # Create binary_cache.
        binary_cache_builder = BinaryCacheBuilder(TestHelper.ndk_path, False)
        elf_name = 'simpleperf_runtest_two_functions_arm'
        elf_path = TestHelper.testdata_path(elf_name)
        readelf = ReadElf(TestHelper.ndk_path)
        build_id = readelf.get_build_id(elf_path)
        self.assertGreater(len(build_id), 0)
        binary_cache_builder.binaries[elf_name] = build_id

        filename_without_build_id = '/data/symfs_without_build_id/elf'
        binary_cache_builder.binaries[filename_without_build_id] = ''

        binary_cache_builder.copy_binaries_from_symfs_dirs([TestHelper.testdata_dir])
        binary_cache_builder.create_build_id_list()

        # Test BinaryFinder.
        path_in_binary_cache = binary_cache_builder.find_path_in_cache(elf_name)
        binary_finder = BinaryFinder(binary_cache_builder.binary_cache_dir, readelf)
        # Find binary using build id.
        path = binary_finder.find_binary('[not_exist_file]', build_id)
        self.assertEqual(path, path_in_binary_cache)
        # Find binary using path.
        path = binary_finder.find_binary(filename_without_build_id, None)
        self.assertIsNotNone(path)
        # Find binary using absolute path.
        path = binary_finder.find_binary(str(path_in_binary_cache), None)
        self.assertEqual(path, path_in_binary_cache)

        # The binary should has a matched build id.
        path = binary_finder.find_binary('/' + elf_name, 'wrong_build_id')
        self.assertIsNone(path)

    # Bionic symbol version tags introduced up through Android 10 (API 29), matching
    # simpleperf_ndk's min_sdk_version: "29" (see bionic/libc/libc.map.txt).
    # Using an explicit allowlist catches lettered tags (LIBC_R..LIBC_V), numeric
    # tags (LIBC_36+), and platform-only tags (LIBC_PRIVATE, LIBC_PLATFORM, LIBC_DEPRECATED).
    API_29_LIBC_VERSIONS = frozenset({'LIBC', 'LIBC_N', 'LIBC_O', 'LIBC_P', 'LIBC_Q'})
    FORBIDDEN_PLATFORM_LIBC_VERSIONS = frozenset({
        'LIBC_PRIVATE', 'LIBC_PLATFORM', 'LIBC_DEPRECATED',
    })

    @classmethod
    def _find_disallowed_libc_symbols(
            cls, dynsym_output: str, arch: str) -> Tuple[int, List[str]]:
        """Returns (libc_undef_count, disallowed_symbols) from llvm-readelf --dyn-syms output."""
        libc_count = 0
        disallowed: List[str] = []
        for line in dynsym_output.splitlines():
            parts = line.split()
            # Format: Num: Value Size Type Bind Vis [Other] Ndx Name [VersionIndex]
            if len(parts) < 8 or not parts[0].endswith(':') or 'UND' not in parts[6:]:
                continue
            bind = parts[4]
            und_idx = parts.index('UND', 6)
            if und_idx + 1 >= len(parts) or bind == 'WEAK':
                continue
            symbol = parts[und_idx + 1]
            if '@' not in symbol:
                continue
            _, _, version = symbol.partition('@')
            version = version.lstrip('@')
            if version != 'LIBC' and not version.startswith('LIBC_'):
                continue
            libc_count += 1
            if arch == 'riscv64':
                # In Soong (build/soong/cc/api_level.go), MinApiForArch(Riscv64) is FutureApiLevel
                # rather than API 29, so riscv64 legitimately links newer public LIBC_* symbols
                # (e.g. copy_file_range@LIBC_U), but must still avoid platform-private symbols.
                if version in cls.FORBIDDEN_PLATFORM_LIBC_VERSIONS:
                    disallowed.append(symbol)
            elif version not in cls.API_29_LIBC_VERSIONS:
                disallowed.append(symbol)
        return libc_count, disallowed

    def test_android_simpleperf_libc_symbol_versions(self):
        # Verify parser catches post-Q, numeric, and platform-private non-WEAK symbols.
        sample_output = """
   Num:    Value          Size Type    Bind   Vis       Ndx Name
     0: 0000000000000000     0 NOTYPE  LOCAL  DEFAULT   UND
     1: 0000000000000000     0 FUNC    GLOBAL DEFAULT   UND __libc_init@LIBC
    11: 0000000000000000     0 FUNC    GLOBAL DEFAULT   UND __fwrite_chk@LIBC_N
    45: 0000000000000000     0 FUNC    WEAK   DEFAULT   UND android_fdsan_close_with_tag@LIBC_Q
    46: 0000000000000000     0 FUNC    WEAK   DEFAULT   UND optional_future_sym@LIBC_S
   192: 0000000000000000     0 FUNC    GLOBAL DEFAULT   UND process_madvise@LIBC_S
   193: 0000000000000000     0 FUNC    GLOBAL DEFAULT   UND newer_api@LIBC_36 (4)
   194: 0000000000000000     0 FUNC    GLOBAL DEFAULT   UND internal_api@LIBC_PRIVATE
"""
        count, bad_arm64 = self._find_disallowed_libc_symbols(sample_output, 'arm64')
        self.assertEqual(count, 5)
        self.assertEqual(
            bad_arm64,
            ['process_madvise@LIBC_S', 'newer_api@LIBC_36', 'internal_api@LIBC_PRIVATE'],
        )
        _, bad_riscv64 = self._find_disallowed_libc_symbols(sample_output, 'riscv64')
        self.assertEqual(bad_riscv64, ['internal_api@LIBC_PRIVATE'])

        android_bin_dir = Path(get_script_dir()) / 'bin' / 'android'
        binaries: List[Path] = []
        seen_paths = set()

        def add_binary(path: Path) -> None:
            resolved = path.resolve()
            if resolved not in seen_paths and path.is_file():
                seen_paths.add(resolved)
                binaries.append(path)

        if android_bin_dir.is_dir():
            prebuilt_binaries = sorted(android_bin_dir.glob('*/simpleperf'))
            found_archs = {p.parent.name for p in prebuilt_binaries}
            for required_arch in ('arm', 'arm64', 'x86', 'x86_64'):
                self.assertIn(
                    required_arch, found_archs, f'Missing bin/android/{required_arch}/simpleperf'
                )
            for binary in prebuilt_binaries:
                add_binary(binary)

        candidate_dirs = [
            Path(sys.argv[0]).resolve().parent,
            TestHelper.test_base_dir.parent,
            Path(get_script_dir()).resolve().parent,
        ]
        for candidate_dir in candidate_dirs:
            for binary_name in ('simpleperf_ndk', 'simpleperf_ndk32'):
                add_binary(candidate_dir / binary_name)

        self.assertTrue(
            binaries,
            'No Android simpleperf binaries found in bin/android/*/simpleperf or '
            'simpleperf_ndk/simpleperf_ndk32',
        )

        ndk_path = getattr(TestHelper, 'ndk_path', None)
        readelf = ReadElf(ndk_path)
        failures = []
        for binary in binaries:
            arch = readelf.get_arch(binary)
            self.assertNotEqual(arch, 'unknown', f'Failed to detect ELF arch of {binary}')
            output = bytes_to_str(subprocess.check_output(
                [readelf.readelf_path, '--dyn-syms', '-W', str(binary)]))
            libc_count, disallowed = self._find_disallowed_libc_symbols(output, arch)
            self.assertGreater(
                libc_count, 0, f'Failed to parse any @LIBC dynamic symbols from {binary}')
            if disallowed:
                label = (
                    f'bin/android/{arch}/{binary.name}'
                    if binary.parent.parent == android_bin_dir
                    else f'{binary.name} ({arch})'
                )
                failures.append(f'{label}: {", ".join(disallowed)}')
        if failures:
            self.fail(
                'Found non-WEAK undefined Bionic symbols newer than @LIBC_Q (API 29):\n  '
                + '\n  '.join(failures)
            )

class TestDeviceTools(TestBase):
    def test_adb_stderr_logging(self):
        adb = AdbHelper()
        if not adb.is_device_available():
            self.skipTest("No device available")

        # Test that success doesn't log warning
        try:
            with self.assertLogs(level='WARNING') as cm:
                adb.run_and_return_output(['shell', 'echo hello >&2'], log_stderr=True)
            self.fail(f"Warning was logged on success: {cm.output}")
        except AssertionError as e:
            if "no logs of level WARNING or higher" not in str(e):
                raise

        # Test that failure still logs warning
        with self.assertLogs(level='WARNING') as cm:
            adb.run_and_return_output(['shell', 'non_existent_command_xyz'], log_stderr=True)
        has_expected_log = any(
            'non_existent_command_xyz' in log or 'not found' in log for log in cm.output)
        self.assertTrue(has_expected_log)
