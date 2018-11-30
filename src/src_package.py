# @mindmaze_header@
'''
Class to handle source packages, build them and generates binary packages.
'''

import importlib
import os
from glob import glob
import re
from subprocess import STDOUT, run
import tarfile
from typing import Set
from workspace import Workspace
from binary_package import BinaryPackage
from common import *
from file_utils import *
from mm_version import Version
from settings import PKGDATADIR


def _get_install_prefix() -> str:
    if os.name == 'nt':
        return '/m/'
    else:  # if not windows, then linux
        return '/run/mmpack/'


def _unpack_deps_version(item):
    ''' helper to allow simpler mmpack dependency syntax

    expected full mmpack dependency syntax is:
        <name>: [min_version, max_version]

    this allows the additional with implicit 'any' as maximum:
        <name>: min_version
        <name>: any
    '''
    try:
        name, minv, maxv = item
        return (name, Version(minv), Version(maxv))
    except ValueError:
        name, minv = item  # if that fails, let the exception be raised
        minv = Version(minv)
        maxv = Version('any')
        return (name, minv, maxv)


class SrcPackage(object):
    # pylint: disable=too-many-instance-attributes
    '''
    Source package class.
    '''
    def __init__(self, name: str, url: str=None, tag: str=None):
        # pylint: disable=too-many-arguments
        self.name = name
        self.tag = tag
        self.srcname = name
        if tag:
            self.srcname += '_' + tag
        self.version = None
        self.url = url
        self.maintainer = None

        self.description = ''
        self.pkg_tags = ['MindMaze']

        self.build_options = None
        self.build_system = None
        self.build_depends = []

        self._specs = None  # raw dictionary version of the specfile
        # dict of (name, BinaryPackage) generated from the source package
        self._packages = {}
        self.install_files_set = set()
        self._metadata_files_list = []

    def _local_build_path(self) -> str:
        'internal helper: build and return the local build path'
        wrk = Workspace()
        return wrk.builddir(self.name) + '/{0}_{1}'.format(self.name, self.tag)

    def _local_install_path(self, withprefix: bool=False) -> str:
        'internal helper: build and return the local install path'
        installdir = self._local_build_path() + '/install'
        if withprefix:
            installdir += _get_install_prefix()

        os.makedirs(installdir, exist_ok=True)
        return installdir

    def _guess_build_system(self):
        ''' helper: guesses the project build system

        Raises:
            RuntimeError: could not guess project build system
        '''
        pushdir(self._local_build_path())
        if os.path.exists('configure.ac'):
            self.build_system = 'autotools'
        elif os.path.exists('CMakeLists.txt'):
            self.build_system = 'cmake'
        elif os.path.exists('Makefile'):
            self.build_system = 'makefile'
        elif os.path.exists('setup.py'):
            self.build_system = 'python'
        else:
            raise RuntimeError('could not guess project build system')

        popdir()

    def load_specfile(self, specfile: str=None) -> None:
        ''' Load the specfile and store it as its dictionary equivalent
        '''
        wrk = Workspace()
        if not specfile:
            specfile = '{0}/{1}/mmpack/specs'.format(wrk.sources,
                                                     self.srcname)
        dprint('loading specfile: ' + specfile)
        self._specs = yaml_load(specfile)

    def _get_matching_files(self, pcre: str) -> Set[str]:
        ''' given some pcre, return the set of matching files from
            self.install_files_set.
            Those files are removed from the source install file set.
        '''
        matching_set = set()
        for inst_file in self.install_files_set:
            if re.match(pcre, inst_file):
                matching_set.add(inst_file)

        self.install_files_set.difference_update(matching_set)
        return matching_set

    def _format_description(self, binpkg: BinaryPackage, pkgname: str,
                            pkg_type: str=None):
        ''' Format BinaryPackage's description.

        If the package is a default target, concat the global project
        description with the additional spcific one. Otherwise, only
        use the specific description.

        Raises: ValueError if the description is empty for custom packages
        '''
        try:
            description = self._specs[pkgname]['description']
        except KeyError:
            description = None

        if binpkg.name in (self.name, self.name + '-devel',
                           self.name + '-doc', self.name + '-debug'):
            binpkg.description = self.description
            if description:
                binpkg.description += '\n' + description
        else:
            if not description and pkg_type == 'custom':
                raise ValueError('Source package {0} has no description'
                                 .format(pkgname))
            elif not description and pkg_type == 'library':
                binpkg.description = self.description + '\n'
                binpkg.description += 'automatically generated around SONAME '
                binpkg.description += self.name
            binpkg.description = description

    def _remove_ignored_files(self):
        if 'ignore' in self._specs['general']:
            for regex in self._specs['general']['ignore']:
                _ = self._get_matching_files(regex)
        # remove *.la and *.def files
        _ = self._get_matching_files(r'.*\.la$')
        _ = self._get_matching_files(r'.*\.def$')

    def _parse_specfile_general(self) -> None:
        ''' Parses the mmpack/specs file's general section.
        This will:
            - fill all the main fields of the source package.
            - prune the ignore files from the install_files_list
        '''
        for key, value in self._specs['general'].items():
            if key == 'name':
                self.name = value
            elif key == 'version':
                self.version = Version(value)
            elif key == 'maintainer':
                self.maintainer = value
            elif key == 'url':
                self.url = value
            elif key == 'description':
                self.description = value
            elif key == 'build-options':
                self.build_options = value
            elif key == 'build-depends':
                self.build_depends = value
            elif key == 'build-system':
                self.build_system = value

    def _binpkg_get_create(self, binpkg_name: str,
                           pkg_type: str=None) -> BinaryPackage:
        'Returns the newly create BinaryPackage if any'
        if binpkg_name not in self._packages:
            host_arch = get_host_arch_dist()
            binpkg = BinaryPackage(binpkg_name, self.version,
                                   self.name, host_arch, self.tag)
            self._format_description(binpkg, binpkg_name, pkg_type)
            self._packages[binpkg_name] = binpkg
            dprint('created package ' + binpkg_name)
            return binpkg
        return self._packages[binpkg_name]

    def parse_specfile(self) -> None:
        '''
            - create BinaryPackage skeleton entries foreach custom and default
              entries.
        '''
        self._parse_specfile_general()

        host_arch = get_host_arch_dist()
        sysdeps_key = 'sysdepends-' + get_host_dist()

        # create skeleton for explicit packages
        for pkg in self._specs.keys():
            if pkg != 'general':
                binpkg = BinaryPackage(pkg, self.version, self.name,
                                       host_arch, self.tag)
                self._format_description(binpkg, pkg)

                if 'depends' in self._specs[pkg]:
                    for dep in self._specs[pkg]['depends']:
                        item = list(dep.items())[0]
                        name, minv, maxv = _unpack_deps_version(item)
                        binpkg.add_depend(name, minv, maxv)
                if sysdeps_key in self._specs[pkg]:
                    for dep in self._specs[pkg][sysdeps_key]:
                        binpkg.add_sysdepend(dep)
                self._packages[pkg] = binpkg

    def create_source_archive(self) -> str:
        ''' Create git archive (source package).

        Returns: the name of the archive file
        '''
        wrk = Workspace()
        wrk.srcclean(self.srcname)
        pushdir(wrk.sources)
        sources_archive_name = '{0}_{1}_src.tar.gz' \
                               .format(self.srcname, self.tag)
        iprint('cloning ' + self.url)
        cmd = 'git clone --quiet --branch {0} {1} {2}' \
              .format(self.tag, self.url, self.srcname)
        shell(cmd)
        pushdir(self.srcname)
        cmd = 'git archive --format=tar.gz --prefix={0}/ {1}' \
              ' > {2}/{3}'.format(self.srcname, self.tag,
                                  wrk.sources, sources_archive_name)
        shell(cmd)
        popdir()  # repository name

        # copy source package to package repository
        cmd = 'cp -vf {0} {1}'.format(sources_archive_name, wrk.packages)
        shell(cmd)
        popdir()  # workspace sources directory

        return sources_archive_name

    def _rename_source_package(self):
        'copy source package to package repository'
        wrk = Workspace()
        pushdir(wrk.sources)

        old_src_name = '{0}_{1}_src.tar.gz'.format(self.srcname, self.tag)
        new_src_name = '{0}_{1}_src.tar.gz'.format(self.name, self.version)
        cmd = 'mv -vf {0}/{1} {0}/{2}'.format(wrk.packages,
                                              old_src_name,
                                              new_src_name)
        shell(cmd)

        popdir()  # repository name

    def _build_env(self, skip_tests: bool):
        build_env = os.environ.copy()
        build_env['SRCDIR'] = self._local_build_path()
        build_env['BUILDDIR'] = self._local_build_path() + '/build'
        build_env['DESTDIR'] = self._local_install_path()
        build_env['PREFIX'] = _get_install_prefix()
        build_env['LD_RUN_PATH'] = os.path.join(_get_install_prefix(), 'lib')
        build_env['SKIP_TESTS'] = str(skip_tests)
        if self.build_options:
            build_env['OPTS'] = self.build_options

        if get_host_dist() == 'windows':
            build_env['MSYSTEM'] = 'MINGW64'
            for var in ('SRCDIR', 'BUILDDIR', 'DESTDIR', 'PREFIX'):
                build_env[var] = shell('cygpath -u ' + build_env[var]).strip()
            for var in ('ACLOCAL_PATH',):
                build_env[var] = shell('cygpath -up ' + build_env[var]).strip()
        return build_env

    def _strip_dirs_from_install_files(self):
        tmp = {x for x in self.install_files_set if not os.path.isdir(x)}
        self.install_files_set = tmp

    def local_install(self, source_pkg: str, skip_tests: bool=False) -> None:
        ''' local installation of the package from the source package

        guesses build system if none given.
        fills private var: _install_list before returning

        Returns:
            the list of all the installed files
        Raises:
            NotImplementedError: the specified build system is not supported
        '''
        wrk = Workspace()
        wrk.clean(self.name)

        pushdir(wrk.packages)
        archive = tarfile.open(source_pkg, 'r:gz')
        archive.extractall(wrk.builddir(self.name))
        archive.close()
        popdir()  # workspace packages directory

        # we're ready to build, so we have all the information at hand
        # name the source package correctly with its version name
        # and copy it with the other generated packages
        self._rename_source_package()

        pushdir(self._local_build_path())
        os.makedirs('build')
        os.makedirs(self._local_install_path(), exist_ok=True)

        if not self.build_system:
            self._guess_build_system()
        if not self.build_system:
            errmsg = 'Unknown build system: ' + self.build_system
            raise NotImplementedError(errmsg)

        build_script = ['sh',
                        '{0}/build-{1}'.format(PKGDATADIR, self.build_system)]
        log_file = open('build.log', 'wb')
        dprint('[shell] {0}'.format(' '.join(build_script)))
        ret = run(build_script, env=self._build_env(skip_tests),
                  stderr=STDOUT, stdout=log_file)
        if ret.returncode != 0:
            errmsg = 'Failed to build ' + self.name + '\n'
            errmsg += 'See build.log file for what went wrong\n'
            raise RuntimeError(errmsg)

        popdir()  # local build directory

        pushdir(self._local_install_path(True))
        self.install_files_set = set(glob('**', recursive=True))
        self._strip_dirs_from_install_files()
        popdir()

    def _ventilate_custom_packages(self):
        ''' Ventilates files explicited in the specfile before
            giving them to the default target.
        '''
        for binpkg in self._packages:
            for regex in self._packages[binpkg]['files']:
                matching_set = self._get_matching_files(regex)
                self._packages[binpkg].install_files.update(matching_set)

        # check that at least on file is present in each of the custom packages
        # raise an error if the described package was expecting one
        # Note: meta-packages are empty and accepted
        for binpkg in self._packages:
            if not self._packages[binpkg] and self._packages[binpkg]['files']:
                errmsg = 'Custom package {0} is empty !'.format(binpkg)
                raise FileNotFoundError(errmsg)

    def _ventilate_pkg_create(self):
        ''' first ventilation pass (after custom packages):
            check amongst the remaining files if one of them would trigger
            the creation of a new package.
            Eg. a dynamic library will be given its own binary package
        '''
        ventilated = set()
        for file in self.install_files_set:
            libtype = is_dynamic_library(file)
            if libtype in ('elf', 'pe'):
                format_module = importlib.import_module(libtype + '_utils')
                soname = format_module.soname(file)
                name, version = parse_soname(soname)
                binpkgname = name + version  # libxxx.0.1.2 -> libxxx<ABI>
                pkg = self._binpkg_get_create(binpkgname, 'library')
                pkg.install_files.add(file)
                ventilated.add(file)

                # add the soname file to the same package
                so_filename = os.path.dirname(file) + '/' + soname
                pkg.install_files.add(so_filename)
                ventilated.add(so_filename)

        self.install_files_set.difference_update(ventilated)

    def _get_fallback_package(self, bin_pkg_name: str) -> BinaryPackage:
        '''
        if a binary package is already created, use it
        if there is no binary package yet, try to fallback with a library pkg
        finally, create and fallback a binary package
        '''

        if bin_pkg_name in self._packages:
            return self._packages[bin_pkg_name]
        else:
            libpkg = None
            for pkgname in self._packages:
                if (pkgname.startswith('lib')
                        and not (pkgname.endswith('-devel')
                                 or pkgname.endswith('-doc')
                                 or pkgname.endswith('-debug'))):
                    if libpkg:
                        # works if there's only one candidate
                        return None
                    libpkg = pkgname
            if libpkg:
                dprint('Return default package: ' + libpkg)
                return self._binpkg_get_create(libpkg)
            dprint('Return default package: ' + bin_pkg_name)
            return self._binpkg_get_create(bin_pkg_name)

    def ventilate(self):
        ''' Ventilate files.
        Must be called after local-install, otherwise it will return dummy
        packages with no files.

        Naming:
          For source package 'xxx1' named after project 'xxx' of version 1.0.0
          create packages xxx1, xxx1-devel, xxx1-doc

          There is no conflict between the source and the binary package names
          because the packages types are different.
        '''
        pushdir(self._local_install_path(True))

        bin_pkg_name = self.name
        doc_pkg_name = self.name + '-doc'
        devel_pkg_name = self.name + '-devel'
        debug_pkg_name = self.name + '-debug'

        self._remove_ignored_files()
        self._ventilate_custom_packages()
        self._ventilate_pkg_create()

        tmpset = set()
        for filename in self.install_files_set:
            if is_binary(filename) or is_exec_manpage(filename):
                pkg = self._binpkg_get_create(bin_pkg_name)
            elif is_documentation(filename) or is_doc_manpage(filename):
                pkg = self._binpkg_get_create(doc_pkg_name)
            elif is_devel(filename):
                pkg = self._binpkg_get_create(devel_pkg_name)
            elif is_debugsym(filename):
                pkg = self._binpkg_get_create(debug_pkg_name)
            else:
                # skip this. It will be put in a default fallback
                # package at the end of the ventilation process
                continue

            pkg.install_files.add(filename)
            tmpset.add(filename)

        self.install_files_set.difference_update(tmpset)

        # deal with the remaining files:
        if self.install_files_set:
            pkg = self._get_fallback_package(bin_pkg_name)
            pkg.install_files.update(self.install_files_set)

        popdir()

    def generate_binary_packages(self):
        'create all the binary packages'
        instdir = self._local_install_path(True)
        pushdir(instdir)

        # we need all of the provide infos before starting the dependencies
        for pkgname, binpkg in self._packages.items():
            binpkg.gen_provides()

        for pkgname, binpkg in self._packages.items():
            binpkg.gen_dependencies(self._packages.values())
            binpkg.create(instdir)
            iprint('generated package: {}'.format(pkgname))
        popdir()  # local install path

    def __repr__(self):
        return u'{}'.format(self.__dict__)
