#!/usr/bin/env python3

import os
import sys

# tricky way to beat the case when package is not installed and script is called via symlink
# we need to add package path to the os.path variable first, then module is available for import
path = os.path.dirname(os.readlink(os.path.abspath(__file__)))
if path not in sys.path:
    sys.path.insert(0, path)

import optparse
import platform

from fmakefile.makefile import ProjectParser

# ()()()()()()()()()()()()()()()()()() DEFINE ARGUMENTS ()()()()()()()()()()()()()()()()()() #

parser = optparse.OptionParser()

parser.add_option('--debug',
                  dest='debug',
                  action='store_true',
                  default=False,
                  help='show debug information')

parser.add_option('--drop-execute-flag',
                  dest='drop_execute_flag',
                  action='store_true',
                  default=False,
                  help='force make all source files not callable (POSIX systems)')

parser.add_option('--encoding',
                  dest='encoding',
                  action='store',
                  help='specify encoding to be used for sourse files')

parser.add_option('--extensions',
                  dest='extensions',
                  action='store',
                  help='specify source files extensions (separate with ;)')

parser.add_option('--compiler',
                  dest='compiler',
                  action='store',
                  help='specify compiler')

parser.add_option('--appname',
                  dest='appname',
                  action='store',
                  help='specify application name')

parser.add_option('--obj-extension',
                  dest='object_extension',
                  action='store',
                  help='specify extension for object files')

parser.add_option('--dependence',
                  dest='dependency',
                  action='store',
                  help='specify dependence (object files, modules)')

parser.add_option('--makefile-name',
                  dest='makefile_name',
                  action='store',
                  help='specify name for makefile')

parser.add_option('--ignore-paths',
                  dest='ignore_paths',
                  action='store',
                  help='ignore path (separate with ;)')

parser.add_option('--ignore-modules',
                  dest='ignore_modules',
                  action='store',
                  help='specify dependencies to ignore (separate with ;)')

parser.add_option('--ignore-includes',
                  dest='ignore_includes',
                  action='store',
                  help='specify included files to be ignore (separate with ;)')

parser.add_option('--config',
                  dest='configuration',
                  action='store',
                  default='release',
                  help='select required configuration (debug, release)')

parser.add_option('--pparams',
                  dest='pcompiler_params',
                  action='store',
                  help='specify primary compiler parameters')

parser.add_option('--sparams',
                  dest='scompiler_params',
                  action='store',
                  help='specify secondary compiler parameters')

parser.add_option('--make',
                  dest='make',
                  action='store_true',
                  default=False,
                  help='call make')

# ()()()()()()()()()()()()()()()()()() PARSE ARGUMENTS ()()()()()()()()()()()()()()()()()() #

(options, args) = parser.parse_args()

if options.debug:
    collect = {}
    for option in parser.option_list:
        key = option.dest
        if key:
            value = getattr(options, key)
            if value:
                collect[option._long_opts[0]] = value

    width = max([len(key) for key in collect])

    print('Ran with arguments:')
    for key, value in collect.items():
        print('    %s%s  %s' % (key, ' '*(width-len(key)), value))
    print()


if options.ignore_paths:
    options.ignore_paths = options.ignore_paths.split(';')

if options.ignore_modules:
    options.ignore_modules = options.ignore_modules.split(';')

if options.ignore_includes:
    options.ignore_includes = options.ignore_includes.split(';')

if options.extensions:
    options.extensions = options.extensions.split(';')

if options.dependency:
    allowed = ('object files', 'modules')
    if options.dependency not in allowed:
        raise ValueError('Unexpected value for --dependence option. Expected %s' % (allowed))

if options.configuration and any([options.pcompiler_params, options.scompiler_params]):
    raise ValueError('--config option is incompatible with --pparams and --sparams.')

if options.configuration:
    allowed = ('debug', 'release')
    if options.configuration not in allowed:
        raise ValueError('Unexpected value for --config option. Expected %s' % (allowed))

    if options.configuration == 'debug':
        pparams = ProjectParser.DEFAULTS['pcompiler_params']
        options.pcompiler_params = pparams.replace('/O3', '/O1').replace('-O3', '-O1')

skip, external = ('make', 'configuration', None), {}
for option in parser.option_list:
    key = option.dest
    if key not in skip:
        value = getattr(options, key)
        if value:
            external[key] = value

# ()()()()()()()()()()()()()()()()()() RUN ()()()()()()()()()()()()()()()()()() #

fparser = ProjectParser(**external)
fparser.create_makefile('.')

if options.make:
    if platform.system() == 'Windows':
        os.system('nmake -f ' + fparser.makefile_name)
    elif platform.system() == 'Linux':
        os.system('make -f ' + fparser.makefile_name)
