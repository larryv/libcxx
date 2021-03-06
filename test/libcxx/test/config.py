import locale
import os
import platform
import re
import shlex
import sys

import lit.Test  # pylint: disable=import-error,no-name-in-module
import lit.util  # pylint: disable=import-error,no-name-in-module

from libcxx.test.format import LibcxxTestFormat
from libcxx.test.compiler import CXXCompiler


class Configuration(object):
    # pylint: disable=redefined-outer-name
    def __init__(self, lit_config, config):
        self.lit_config = lit_config
        self.config = config
        self.cxx = None
        self.libcxx_src_root = None
        self.obj_root = None
        self.cxx_library_root = None
        self.env = {}
        self.use_system_cxx_lib = False
        self.use_clang_verify = False
        self.long_tests = None

        if platform.system() not in ('Darwin', 'FreeBSD', 'Linux'):
            self.lit_config.fatal("unrecognized system")

    def get_lit_conf(self, name, default=None):
        val = self.lit_config.params.get(name, None)
        if val is None:
            val = getattr(self.config, name, None)
            if val is None:
                val = default
        return val

    def get_lit_bool(self, name, default=None):
        conf = self.get_lit_conf(name)
        if conf is None:
            return default
        if conf.lower() in ('1', 'true'):
            return True
        if conf.lower() in ('', '0', 'false'):
            return False
        self.lit_config.fatal(
            "parameter '{}' should be true or false".format(name))

    def configure(self):
        self.configure_cxx()
        self.configure_triple()
        self.configure_src_root()
        self.configure_obj_root()
        self.configure_cxx_library_root()
        self.configure_use_system_cxx_lib()
        self.configure_use_clang_verify()
        self.configure_ccache()
        self.configure_env()
        self.configure_compile_flags()
        self.configure_link_flags()
        self.configure_sanitizer()
        self.configure_features()
        # Print the final compile and link flags.
        self.lit_config.note('Using flags: %s' % self.cxx.flags)
        self.lit_config.note('Using compile flags: %s' % self.cxx.compile_flags)
        self.lit_config.note('Using link flags: %s' % self.cxx.link_flags)
        # Print as list to prevent "set([...])" from being printed.
        self.lit_config.note('Using available_features: %s' %
                             list(self.config.available_features))
        self.lit_config.note('Using environment: %r' % self.env)

    def get_test_format(self):
        return LibcxxTestFormat(
            self.cxx,
            self.use_clang_verify,
            exec_env=self.env)

    def configure_cxx(self):
        # Gather various compiler parameters.
        cxx = self.get_lit_conf('cxx_under_test')

        # If no specific cxx_under_test was given, attempt to infer it as
        # clang++.
        if cxx is None:
            clangxx = lit.util.which('clang++',
                                     self.config.environment['PATH'])
            if clangxx:
                cxx = clangxx
                self.lit_config.note(
                    "inferred cxx_under_test as: %r" % cxx)
        if not cxx:
            self.lit_config.fatal('must specify user parameter cxx_under_test '
                                  '(e.g., --param=cxx_under_test=clang++)')
        self.cxx = CXXCompiler(cxx)
        cxx_type = self.cxx.type
        maj_v, min_v, _ = self.cxx.version
        if cxx_type is not None:
            self.config.available_features.add(cxx_type)
            self.config.available_features.add('%s-%s.%s' % (
                cxx_type, maj_v, min_v))


    def configure_src_root(self):
        self.libcxx_src_root = self.get_lit_conf(
            'libcxx_src_root', os.path.dirname(self.config.test_source_root))

    def configure_obj_root(self):
        self.obj_root = self.get_lit_conf('libcxx_obj_root',
                                          self.libcxx_src_root)

    def configure_cxx_library_root(self):
        self.cxx_library_root = self.get_lit_conf('cxx_library_root',
                                                  self.obj_root)

    def configure_use_system_cxx_lib(self):
        # This test suite supports testing against either the system library or
        # the locally built one; the former mode is useful for testing ABI
        # compatibility between the current headers and a shipping dynamic
        # library.
        self.use_system_cxx_lib = self.get_lit_bool('use_system_cxx_lib')
        if self.use_system_cxx_lib is None:
            # Default to testing against the locally built libc++ library.
            self.use_system_cxx_lib = False
            self.lit_config.note(
                "inferred use_system_cxx_lib as: %r" % self.use_system_cxx_lib)

    def configure_use_clang_verify(self):
        '''If set, run clang with -verify on failing tests.'''
        self.use_clang_verify = self.get_lit_bool('use_clang_verify')
        if self.use_clang_verify is None:
            # TODO: Default this to True when using clang.
            self.use_clang_verify = False
            self.lit_config.note(
                "inferred use_clang_verify as: %r" % self.use_clang_verify)

    def configure_ccache(self):
        use_ccache = self.get_lit_bool('use_ccache', False)
        if use_ccache:
            self.cxx.use_ccache = True
            self.lit_config.note('enabling ccache')

    def configure_features(self):
        additional_features = self.get_lit_conf('additional_features')
        if additional_features:
            for f in additional_features.split(','):
                self.config.available_features.add(f.strip())

        # Figure out which of the required locales we support
        locales = {
            'Darwin': {
                'en_US.UTF-8': 'en_US.UTF-8',
                'cs_CZ.ISO8859-2': 'cs_CZ.ISO8859-2',
                'fr_FR.UTF-8': 'fr_FR.UTF-8',
                'fr_CA.ISO8859-1': 'cs_CZ.ISO8859-1',
                'ru_RU.UTF-8': 'ru_RU.UTF-8',
                'zh_CN.UTF-8': 'zh_CN.UTF-8',
            },
            'FreeBSD': {
                'en_US.UTF-8': 'en_US.UTF-8',
                'cs_CZ.ISO8859-2': 'cs_CZ.ISO8859-2',
                'fr_FR.UTF-8': 'fr_FR.UTF-8',
                'fr_CA.ISO8859-1': 'fr_CA.ISO8859-1',
                'ru_RU.UTF-8': 'ru_RU.UTF-8',
                'zh_CN.UTF-8': 'zh_CN.UTF-8',
            },
            'Linux': {
                'en_US.UTF-8': 'en_US.UTF-8',
                'cs_CZ.ISO8859-2': 'cs_CZ.ISO-8859-2',
                'fr_FR.UTF-8': 'fr_FR.UTF-8',
                'fr_CA.ISO8859-1': 'fr_CA.ISO-8859-1',
                'ru_RU.UTF-8': 'ru_RU.UTF-8',
                'zh_CN.UTF-8': 'zh_CN.UTF-8',
            },
            'Windows': {
                'en_US.UTF-8': 'English_United States.1252',
                'cs_CZ.ISO8859-2': 'Czech_Czech Republic.1250',
                'fr_FR.UTF-8': 'French_France.1252',
                'fr_CA.ISO8859-1': 'French_Canada.1252',
                'ru_RU.UTF-8': 'Russian_Russia.1251',
                'zh_CN.UTF-8': 'Chinese_China.936',
            },
        }

        default_locale = locale.setlocale(locale.LC_ALL)
        for feature, loc in locales[platform.system()].items():
            try:
                locale.setlocale(locale.LC_ALL, loc)
                self.config.available_features.add(
                    'locale.{0}'.format(feature))
            except locale.Error:
                self.lit_config.warning('The locale {0} is not supported by '
                                        'your platform. Some tests will be '
                                        'unsupported.'.format(loc))
        locale.setlocale(locale.LC_ALL, default_locale)

        # Write an "available feature" that combines the triple when
        # use_system_cxx_lib is enabled. This is so that we can easily write
        # XFAIL markers for tests that are known to fail with versions of
        # libc++ as were shipped with a particular triple.
        if self.use_system_cxx_lib:
            self.config.available_features.add(
                'with_system_cxx_lib=%s' % self.config.target_triple)

        # Some linux distributions have different locale data than others.
        # Insert the distributions name and name-version into the available
        # features to allow tests to XFAIL on them.
        if sys.platform.startswith('linux'):
            name, ver, _ = platform.linux_distribution()
            name = name.lower().strip()
            ver = ver.lower().strip()
            if name:
                self.config.available_features.add(name)
            if name and ver:
                self.config.available_features.add('%s-%s' % (name, ver))

        # Simulator testing can take a really long time for some of these tests
        # so add a feature check so we can REQUIRES: long_tests in them
        self.long_tests = self.get_lit_bool('long_tests')
        if self.long_tests is None:
            # Default to running long tests.
            self.long_tests = True
            self.lit_config.note(
                "inferred long_tests as: %r" % self.long_tests)

        if self.long_tests:
            self.config.available_features.add('long_tests')

    def configure_compile_flags(self):
      no_default_flags = self.get_lit_bool('no_default_flags', False)
      if not no_default_flags:
        self.configure_default_compile_flags()
      # Configure extra flags
      compile_flags_str = self.get_lit_conf('compile_flags', '')
      self.cxx.compile_flags += shlex.split(compile_flags_str)

    def configure_default_compile_flags(self):
        # Try and get the std version from the command line. Fall back to
        # default given in lit.site.cfg is not present. If default is not
        # present then force c++11.
        std = self.get_lit_conf('std', 'c++11')
        self.cxx.compile_flags += ['-std={0}'.format(std)]
        self.config.available_features.add(std)
        # Configure include paths
        self.cxx.compile_flags += ['-nostdinc++']
        self.configure_compile_flags_header_includes()
        if sys.platform.startswith('linux'):
            self.cxx.compile_flags += ['-D__STDC_FORMAT_MACROS',
                                       '-D__STDC_LIMIT_MACROS',
                                       '-D__STDC_CONSTANT_MACROS']
        # Configure feature flags.
        self.configure_compile_flags_exceptions()
        self.configure_compile_flags_rtti()
        enable_32bit = self.get_lit_bool('enable_32bit', False)
        if enable_32bit:
            self.cxx.flags += ['-m32']
        # Configure threading features.
        enable_threads = self.get_lit_bool('enable_threads', True)
        enable_monotonic_clock = self.get_lit_bool('enable_monotonic_clock',
                                                   True)
        if not enable_threads:
            self.configure_compile_flags_no_threads()
            if not enable_monotonic_clock:
                self.configure_compile_flags_no_monotonic_clock()
        elif not enable_monotonic_clock:
            self.lit_config.fatal('enable_monotonic_clock cannot be false when'
                                  ' enable_threads is true.')
        # Use verbose output for better errors
        self.cxx.flags += ['-v']
        sysroot = self.get_lit_conf('sysroot')
        if sysroot:
            self.cxx.flags += ['--sysroot', sysroot]
        gcc_toolchain = self.get_lit_conf('gcc_toolchain')
        if gcc_toolchain:
            self.cxx.flags += ['-gcc-toolchain', gcc_toolchain]

        self.cxx.flags += ['-target', self.config.target_triple]

    def configure_compile_flags_header_includes(self):
        self.cxx.compile_flags += ['-I' + self.libcxx_src_root + '/test/support']
        libcxx_headers = self.get_lit_conf('libcxx_headers',
                                           self.libcxx_src_root + '/include')
        if not os.path.isdir(libcxx_headers):
            self.lit_config.fatal("libcxx_headers='%s' is not a directory."
                                  % libcxx_headers)
        self.cxx.compile_flags += ['-I' + libcxx_headers]

    def configure_compile_flags_exceptions(self):
        enable_exceptions = self.get_lit_bool('enable_exceptions', True)
        if enable_exceptions:
            self.config.available_features.add('exceptions')
        else:
            self.cxx.compile_flags += ['-fno-exceptions']

    def configure_compile_flags_rtti(self):
        enable_rtti = self.get_lit_bool('enable_rtti', True)
        if enable_rtti:
            self.config.available_features.add('rtti')
        else:
            self.cxx.compile_flags += ['-fno-rtti', '-D_LIBCPP_NO_RTTI']

    def configure_compile_flags_no_threads(self):
        self.cxx.compile_flags += ['-D_LIBCPP_HAS_NO_THREADS']
        self.config.available_features.add('libcpp-has-no-threads')

    def configure_compile_flags_no_monotonic_clock(self):
        self.cxx.compile_flags += ['-D_LIBCPP_HAS_NO_MONOTONIC_CLOCK']
        self.config.available_features.add('libcpp-has-no-monotonic-clock')

    def configure_link_flags(self):
        no_default_flags = self.get_lit_bool('no_default_flags', False)
        if not no_default_flags:
          self.cxx.link_flags += ['-nodefaultlibs']

          # Configure library path
          self.configure_link_flags_cxx_library_path()
          self.configure_link_flags_abi_library_path()

          # Configure libraries
          self.configure_link_flags_cxx_library()
          self.configure_link_flags_abi_library()
          self.configure_extra_library_flags()

        link_flags_str = self.get_lit_conf('link_flags', '')
        self.cxx.link_flags += shlex.split(link_flags_str)

    def configure_link_flags_cxx_library_path(self):
        libcxx_library = self.get_lit_conf('libcxx_library')
        # Configure libc++ library paths.
        if libcxx_library is not None:
            # Check that the given value for libcxx_library is valid.
            if not os.path.isfile(libcxx_library):
                self.lit_config.fatal(
                    "libcxx_library='%s' is not a valid file." %
                    libcxx_library)
            if self.use_system_cxx_lib:
                self.lit_config.fatal(
                    "Conflicting options: 'libcxx_library' cannot be used "
                    "with 'use_system_cxx_lib=true'")
            self.cxx.link_flags += ['-Wl,-rpath,' +
                                    os.path.dirname(libcxx_library)]
        elif not self.use_system_cxx_lib:
            self.cxx.link_flags += ['-L' + self.cxx_library_root,
                                    '-Wl,-rpath,' + self.cxx_library_root]

    def configure_link_flags_abi_library_path(self):
        # Configure ABI library paths.
        abi_library_path = self.get_lit_conf('abi_library_path', '')
        if abi_library_path:
            self.cxx.link_flags += ['-L' + abi_library_path,
                                    '-Wl,-rpath,' + abi_library_path]

    def configure_link_flags_cxx_library(self):
        libcxx_library = self.get_lit_conf('libcxx_library')
        if libcxx_library:
            self.cxx.link_flags += [libcxx_library]
        else:
            self.cxx.link_flags += ['-lc++']

    def configure_link_flags_abi_library(self):
        cxx_abi = self.get_lit_conf('cxx_abi', 'libcxxabi')
        if cxx_abi == 'libstdc++':
            self.cxx.link_flags += ['-lstdc++']
        elif cxx_abi == 'libsupc++':
            self.cxx.link_flags += ['-lsupc++']
        elif cxx_abi == 'libcxxabi':
            self.cxx.link_flags += ['-lc++abi']
        elif cxx_abi == 'libcxxrt':
            self.cxx.link_flags += ['-lcxxrt']
        elif cxx_abi == 'none':
            pass
        else:
            self.lit_config.fatal(
                'C++ ABI setting %s unsupported for tests' % cxx_abi)

    def configure_extra_library_flags(self):
        enable_threads = self.get_lit_bool('enable_threads', True)
        llvm_unwinder = self.get_lit_conf('llvm_unwinder', False)
        if sys.platform == 'darwin':
            self.cxx.link_flags += ['-lSystem']
        elif sys.platform.startswith('linux'):
            if not llvm_unwinder:
                self.cxx.link_flags += ['-lgcc_eh']
            self.cxx.link_flags += ['-lc', '-lm']
            if enable_threads:
                self.cxx.link_flags += ['-lpthread']
            self.cxx.link_flags += ['-lrt']
            if llvm_unwinder:
                self.cxx.link_flags += ['-lunwind', '-ldl']
            else:
                self.cxx.link_flags += ['-lgcc_s']
        elif sys.platform.startswith('freebsd'):
            self.cxx.link_flags += ['-lc', '-lm', '-pthread', '-lgcc_s']
        else:
            self.lit_config.fatal("unrecognized system: %r" % sys.platform)

    def configure_sanitizer(self):
        san = self.get_lit_conf('use_sanitizer', '').strip()
        if san:
            # Search for llvm-symbolizer along the compiler path first
            # and then along the PATH env variable.
            symbolizer_search_paths = os.environ.get('PATH', '')
            cxx_path = lit.util.which(self.cxx.path)
            if cxx_path is not None:
                symbolizer_search_paths = (
                    os.path.dirname(cxx_path) +
                    os.pathsep + symbolizer_search_paths)
            llvm_symbolizer = lit.util.which('llvm-symbolizer',
                                             symbolizer_search_paths)
            # Setup the sanitizer compile flags
            self.cxx.compile_flags += ['-g', '-fno-omit-frame-pointer']
            if sys.platform.startswith('linux'):
                self.cxx.link_flags += ['-ldl']
            if san == 'Address':
                self.cxx.compile_flags += ['-fsanitize=address']
                if llvm_symbolizer is not None:
                    self.env['ASAN_SYMBOLIZER_PATH'] = llvm_symbolizer
                self.config.available_features.add('asan')
            elif san == 'Memory' or san == 'MemoryWithOrigins':
                self.cxx.compile_flags += ['-fsanitize=memory']
                if san == 'MemoryWithOrigins':
                    self.cxx.compile_flags += ['-fsanitize-memory-track-origins']
                if llvm_symbolizer is not None:
                    self.env['MSAN_SYMBOLIZER_PATH'] = llvm_symbolizer
                self.config.available_features.add('msan')
            elif san == 'Undefined':
                self.cxx.compile_flags += ['-fsanitize=undefined',
                                       '-fno-sanitize=vptr,function',
                                       '-fno-sanitize-recover', '-O3']
                self.config.available_features.add('ubsan')
            elif san == 'Thread':
                self.cxx.compile_flags += ['-fsanitize=thread']
                self.config.available_features.add('tsan')
            else:
                self.lit_config.fatal('unsupported value for '
                                      'use_sanitizer: {0}'.format(san))

    def configure_triple(self):
        # Get or infer the target triple.
        self.config.target_triple = self.get_lit_conf('target_triple')
        # If no target triple was given, try to infer it from the compiler
        # under test.
        if not self.config.target_triple:
            target_triple = self.cxx.getTriple()
            # Drop sub-major version components from the triple, because the
            # current XFAIL handling expects exact matches for feature checks.
            # Example: x86_64-apple-darwin14.0.0 -> x86_64-apple-darwin14
            # The 5th group handles triples greater than 3 parts
            # (ex x86_64-pc-linux-gnu).
            target_triple = re.sub(r'([^-]+)-([^-]+)-([^.]+)([^-]*)(.*)',
                                   r'\1-\2-\3\5', target_triple)
            # linux-gnu is needed in the triple to properly identify linuxes
            # that use GLIBC. Handle redhat and opensuse triples as special
            # cases and append the missing `-gnu` portion.
            if target_triple.endswith('redhat-linux') or \
               target_triple.endswith('suse-linux'):
                target_triple += '-gnu'
            self.config.target_triple = target_triple
            self.lit_config.note(
                "inferred target_triple as: %r" % self.config.target_triple)

    def configure_env(self):
        if sys.platform == 'darwin' and not self.use_system_cxx_lib:
            libcxx_library = self.get_lit_conf('libcxx_library')
            if libcxx_library:
                cxx_library_root = os.path.dirname(libcxx_library)
            else:
                cxx_library_root = self.cxx_library_root
            self.env['DYLD_LIBRARY_PATH'] = cxx_library_root
