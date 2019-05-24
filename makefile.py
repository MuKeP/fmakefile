#!/usr/bin/env python3

import os
import re
import sys
import optparse
import platform
import subprocess
import datetime


now = datetime.datetime.now()


class FortranCodeError(Exception):
    pass


class ArgumentError(Exception):
    pass


quotes_set = "'" + '"'
name_pattern = 'a-zA-Z0-9_'
available_modules = ['ifport', 'ifposix', 'ifcore', 'ifqwin', 'iflogm', 'ifcom', 'ifauto',
                     'dfport', 'dflib', 'dfwin', 'dflogm', 'dfauto', 'omp_lib']
ignore_warnings = '7000,7734,7954,8290,8291'


if platform.system() == 'Windows':
    null_device = 'nul'
elif platform.system() == 'Linux':
    null_device = '/dev/null'


def isQuoted(line, position):  # assuming that everything is fine with quotes
    if not any([(quote in line) for quote in quotes_set]):
        return False

    quote_status = -1
    for pos, symbol in enumerate(line):
        if pos == position:
            return True if quote_status != -1 else False

        if symbol in quotes_set:
            current_quote = quotes_set.index(symbol)

            if quote_status == -1:
                quote_status = current_quote
            elif quote_status == current_quote:
                quote_status = -1


def get_name_len(string):
    result = re.search('[^' + name_pattern + ']', string)
    return result.start() if result else None


def get_file_list(prefix, object_list, line_width=80):
    result = prefix + '= \\\n'
    while object_list:
        count = 0
        while True:
            count += 1

            width = sum([len(obj) for obj in object_list[:count]]) + (count-1) + 2
            if width > line_width:
                result += ' '.join(object_list[:count-1]) + ' \\\n'
                object_list = object_list[count-1:]
                break

            if count == len(object_list):
                result += ' '.join(object_list[:count]) + '\n'
                object_list = []
                break
    return result


def isKeyword(line, keyword, prev=False):
    try:
        ln, pos = len(keyword), line.index(keyword)
    except ValueError:
        return False  # keyword is not found in the line

    if ln+pos >= len(line):
        return True  # keyword len is equal to line len

    if prev:
        if pos != 0:
            if line[pos-1].isalpha():
                return False  # previous symbol is letter

    return not isQuoted(line, pos) and not line[ln+pos].isalpha()


def replaceExtension(name, exts, src):
    for ext in exts:
        if name.endswith(ext):
            return name.replace(ext, src)
    else:
        return name


parser = optparse.OptionParser()
parser.add_option('--config',
                  dest='configuration',
                  action='store',
                  default='release',
                  help='select required configuration (debug,release)')

parser.add_option('--compiler',
                  dest='compiler',
                  action='store',
                  default='ifort',
                  help='specify compiler')

parser.add_option('--pparams',
                  dest='compiler_pparams',
                  action='store',
                  default=None,
                  help='specify primary compiler parameters')

parser.add_option('--sparams',
                  dest='compiler_sparams',
                  action='store',
                  default=None,
                  help='specify secondary compiler parameters')

parser.add_option('--appname',
                  dest='appname',
                  action='store',
                  default='appname',
                  help='specify application name')

parser.add_option('--make',
                  dest='make',
                  action='store_true',
                  default=False,
                  help='call make')

parser.add_option('--ignore-path',
                  dest='ignore',
                  action='store',
                  default=None,
                  help='ignore path (separate by ;)')

parser.add_option('--obj-extension',
                  dest='obj_extension',
                  action='store',
                  default=None,
                  help='specify extension for object files')

parser.add_option('--makefile-name',
                  dest='mfname',
                  action='store',
                  default='Makefile',
                  help='specify name for makefile')

parser.add_option('--dependence',
                  dest='dependency',
                  action='store',
                  default='object files',
                  help='specify dependence (.obj or .mod file)')

parser.add_option('--ignore-dependency',
                  dest='ignore_deps',
                  action='store',
                  default=None,
                  help='specify dependencies to ignore (separate by ;)')

parser.add_option('--extension',
                  dest='extension',
                  action='store',
                  default=None,
                  help='specify source files extension (separate by ;)')

parser.add_option('--encoding',
                  dest='encoding',
                  action='store',
                  default='utf-8',
                  help='specify encoding to be used for sourse files')

parser.add_option('--debug',
                  dest='debug',
                  action='store_true',
                  default=False,
                  help='show debug information')

(options, args) = parser.parse_args()

# ()()()()()()()()()()()()()()()()()() PROCEED ARGUMENTS ()()()()()()()()()()()()()()()()()() #

if options.configuration not in ['debug', 'release']:
    raise ArgumentError('Invalid "--config" value. Should be in ("debug", "release").')

if options.dependency not in ['object files', 'modules']:
    raise ArgumentError('Invalid "--dependence" value. Should be in ("object files", "modules").')

if platform.system() == 'Windows':
    if options.appname.endswith('.x'):
        options.appname.replace('.x', '.exe')

    if not options.appname.endswith('.exe'):
        options.appname += '.exe'

elif platform.system() == 'Linux':
    if options.appname.endswith('.exe'):
        options.appname.replace('.exe', '.x')

    if not options.appname.endswith('.x'):
        options.appname += '.x'

if not options.obj_extension:
    options.obj_extension = '.obj'

if not options.compiler_pparams:
    if options.configuration == 'debug':
        if platform.system() == 'Windows':
            options.compiler_pparams = '/O1 /fpp /C /traceback /Qdiag-disable:' + ignore_warnings + ' /nologo'
        elif platform.system() == 'Linux':
            options.compiler_pparams = '-O1 -fpp -C -traceback -diag-disable ' + ignore_warnings

    if options.configuration == 'release':
        if platform.system() == 'Windows':
            options.compiler_pparams = '/O3 /fpp /Qdiag-disable:' + ignore_warnings + ' /nologo'
        elif platform.system() == 'Linux':
            options.compiler_pparams = '-O3 -fpp -diag-disable ' + ignore_warnings

if not options.compiler_sparams:
    if platform.system() == 'Windows':
        options.compiler_sparams = '/Qopenmp'
    elif platform.system() == 'Linux':
        options.compiler_sparams = '-qopenmp'

ignore_path_set = []
if options.ignore:
    ignore_path_set = options.ignore.split(';')

ignore_dependency = []
if options.ignore_deps:
    ignore_dependency = options.ignore_deps.split(';')

extension_set = ['.f90']
if options.extension:
    extension_set = options.extension.split(';')

available_modules.extend(ignore_dependency)
available_modules = list(set(available_modules))

if options.debug:
    print('Arguments:')
    print('--config', options.configuration)
    print('--compiler', options.compiler)
    print('--pparams', options.compiler_pparams)
    print('--sparams', options.compiler_sparams)
    print('--appname', options.appname)
    print('--make', options.make)
    print('--ignore-path', options.ignore)
    print('--obj-extension', options.obj_extension)
    print('--makefile-name', options.mfname)
    print('--dependence', options.dependency)
    print('--ignore-dependency', options.ignore_deps)
    print('--extension', options.extension)
    print('--encoding', options.encoding)
    print('--debug', options.debug)

# ()()()()()()()()()()()()()()()()()() PREPARE FILES ()()()()()()()()()()()()()()()()()() #

fileset = []
for (dirpath, dirnames, filenames) in os.walk('.'):  # collect all source files recursively
    fileset.extend([os.path.join(dirpath, file)
                    for file in filenames if any([file.endswith(ext) for ext in extension_set])])

if ignore_path_set:
    ignore_path_set = ['.' + os.path.sep + ignored for ignored in ignore_path_set]
    for file in fileset[::-1]:
        for ignored in ignore_path_set:
            if file.startswith(ignored):
                fileset.remove(file)

if platform.system() == 'Linux':
    subprocess.call(['chmod', 'a-x'] + fileset)

# ()()()()()()()()()()()()()()()()()() PARSE FILES ()()()()()()()()()()()()()()()()()() #

contains, program, module_location, empty_files, non_interfaced = {}, {}, {}, [], True
for file in fileset:  # location of program units
    filecontains = {'modules': [], 'subroutines': [], 'functions': [],
                    'dependencies': [], 'program': False}
    for line in open(file, 'r', encoding=options.encoding):  # assume that key statements are written without ;&!

        if '!' in line and not isQuoted(line, line.index('!')):
            line = line[:line.index('!')]  # remove comment

        uline = line.lower().strip()
        statement, *other = uline.split(' ')

        if isKeyword(statement, 'interface'):
            non_interfaced = False
            continue

        if uline.startswith('end interface') or uline.startswith('endinterface'):
            non_interfaced = True
            continue

        if isKeyword(statement, 'module') and other[0] != 'procedure':
            module_name = other[0].strip()
            filecontains['modules'].append(module_name)
            module_location[module_name] = file
            continue

        if isKeyword(statement, 'subroutine') and non_interfaced:
            filecontains['subroutines'].append(other[0][:get_name_len(other[0])])
            continue

        if isKeyword(statement, 'program'):
            if program:
                print('>>', program['name'], 'in', program['location'])
                print('>>', other[0], 'in', file)
                print()
                raise FortranCodeError('Found more than one program statement.')
            program = {'name': other[0], 'location': file}
            filecontains['program'] = True
            continue

        if isKeyword(statement, 'use', True):
            if other[0][:get_name_len(other[0])] not in available_modules:
                filecontains['dependencies'].append(other[0][:get_name_len(other[0])])
                continue

        if 'function' in uline and isKeyword(uline, 'function') and not uline.startswith('end') and non_interfaced:
            words = uline.split(' ')
            position = words.index('function')
            filecontains['functions'].append(words[position+1][:get_name_len(words[position+1])])
            continue
    empty_stream = not any([bool(filecontains[key]) for key in filecontains.keys()])

    if options.debug:
        print('*** File [%s]' % file, end=' ')
        if not empty_stream:
            print('info:')
            if filecontains['modules']:
                print('>>> modules     : %s' % filecontains['modules'])

            if filecontains['subroutines']:
                print('>>> subroutines : %s' % filecontains['subroutines'])

            if filecontains['functions']:
                print('>>> functions   : %s' % filecontains['functions'])

            if filecontains['dependencies']:
                print('>>> dependencies: %s' % list(set(filecontains['dependencies'])))
        else:
            print('is empty.')

        if filecontains['program']:
            print('!!! contains program entry.')
        print()

    # ++++++++++> needs to be tested <++++++++++
    if empty_stream and not filecontains['program']:
        empty_files.append(file)

    contains[file] = dict(filecontains)

for file in fileset:  # remove duplicates
    contains[file]['dependencies'] = list(set(contains[file]['dependencies']))

if empty_files:
    if options.debug:
        print()
        print('Empty stream(s):')
        for i, file in enumerate(empty_files):
            print('%2d) %s' % (i+1, file))
        print('Rename file(s) (name -> name~) to exclude them from the list.')
        print()
    raise FortranCodeError('Empty stream(s) found.')

if options.debug:
    print('Program', program['name'], 'enter is located in', program['location'])
    print('*' * 78)
    for file in fileset:
        print('File:', file)
        print('Modules:', contains[file]['modules'])
        print('Dependencies:', contains[file]['dependencies'])
        print('Subroutines:', contains[file]['subroutines'])
        print('Functions:', contains[file]['functions'])
        print('*' * 78)

# ()()()()()()()()()()()()()()()()()() RESOLVE DEPENDENCIES ()()()()()()()()()()()()()()()()()() #

for file in fileset:
    for module in contains[file]['modules']:
        if module in contains[file]['dependencies']:  # remove self-dependencies
            contains[file]['dependencies'].remove(module)

obj_order, modules_proc, files_unproc = [], [], fileset[:]
while files_unproc:
    for file in files_unproc:
        if all([(module in modules_proc) if contains[file]['dependencies'] else True
                for module in contains[file]['dependencies']]):
            modules_proc.extend(contains[file]['modules'])
            obj_order.append(file)
            files_unproc.remove(file)
            break
    else:
        print()
        print('Files with unresolved dependencies:')
        for file in files_unproc:
            print('Name', file)
            print('Dependencies:')
            k = 0
            for dep in contains[file]['dependencies']:
                if dep not in modules_proc:
                    k += 1
                    print('  %2d) %s' % (k, dep))
        print()
        raise FortranCodeError('Cannot resolve dependencies. Probably cross-dependence or some modules missing.')

# ()()()()()()()()()()()()()()()()()() MAKEFILE FORMATION ()()()()()()()()()()()()()()()()()() #

obj_string = get_file_list('OBJS',
                           [replaceExtension(obj, extension_set, options.obj_extension)
                            for obj in obj_order])

mod_string = get_file_list('MODS', [module + '.mod' for module in modules_proc])

mkfile = open(options.mfname, 'w')

mkfile.write('\n# %s #\n' % ('()'*25))
mkfile.write('# %s\n' % (now.strftime("%Y-%m-%d %H:%M")))
mkfile.write('# generated automatically with command line:\n')
mkfile.write('# {} {} \n'.format(os.path.split(sys.argv[0])[1], ' '.join(sys.argv[1:])))
mkfile.write('# paltform: {}\n'.format(platform.system()))
mkfile.write('# %s #\n\n' % ('()'*25))

mkfile.write('NAME={}\n'.format(options.appname))
mkfile.write('COM={}\n'.format(options.compiler))
mkfile.write('PFLAGS={}\n'.format(options.compiler_pparams))
mkfile.write('SFLAGS={}\n\n'.format(options.compiler_sparams))

mkfile.write(obj_string + '\n\n')
mkfile.write(mod_string + '\n\n')
mkfile.write('$(NAME): $(OBJS)\n')
mkfile.write('\t$(COM) $(OBJS) $(SFLAGS) -o $(NAME)\n\n')

for obj in obj_order:

    if options.dependency == 'object files':
        deps = [replaceExtension(module_location[dep], extension_set, options.obj_extension)
                for dep in contains[obj]['dependencies']]
    else:
        deps = [dep + '.mod' for dep in contains[obj]['dependencies']]

    deps.append(obj)
    mkfile.write(replaceExtension(obj, extension_set, options.obj_extension) + ': ' + ' '.join(deps) + '\n')
    mkfile.write('\t$(COM) -c $(PFLAGS) $(SFLAGS) {} -o {}\n'.format(
                 obj, replaceExtension(obj, extension_set, options.obj_extension)))

rm_recursive_obj = ('\tfind | grep -E "*\\' +
                    options.obj_extension + '" | xargs rm 2>' + null_device + '\n')

rm_recursive_mod = ('\tfind | grep -E "*\\' +
                    '.mod" | xargs rm 2>' + null_device + '\n')

if platform.system() == 'Windows':
    call_makefile = 'nmake -f ' + options.mfname
elif platform.system() == 'Linux':
    call_makefile = 'make -f ' + options.mfname

mkfile.write('\n.PHONY: rm_objs rm_mods rm_app clean cleanall remake build\n')

mkfile.write('\nrm_objs:\n')
mkfile.write('\trm -f $(OBJS)\n\n')

mkfile.write('rm_mods:\n')
mkfile.write('\trm -f $(MODS)\n\n')

mkfile.write('rm_app:\n')
mkfile.write('\trm -f $(NAME)\n\n')

mkfile.write('clean:\n')
mkfile.write('\t$(MAKE) rm_objs\n')
mkfile.write('\t$(MAKE) rm_mods\n\n')

mkfile.write('cleanall:\n')
mkfile.write('\t$(MAKE) clean\n')
mkfile.write('\t$(MAKE) rm_app\n\n')

mkfile.write('remake:\n')
mkfile.write('\t$(MAKE) cleanall\n')
mkfile.write('\t$(MAKE)\n\n')

mkfile.write('build:\n')
mkfile.write('\t$(MAKE) cleanall\n')
mkfile.write('\t$(MAKE)\n')
mkfile.write('\t$(MAKE) clean\n\n')

mkfile.close()

if options.make:
    os.system(call_makefile)
