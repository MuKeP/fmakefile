#!/usr/bin/python3
import os
import re
import sys
import optparse
import platform


class FortranCodeError(Exception):
    pass


class ArgumentError(Exception):
    pass


quotes_set = "'" + '"'
name_pattern = 'a-zA-Z0-9_'
available_modules = ['ifport', 'ifposix', 'ifcore', 'ifqwin', 'iflogm', 'ifcom', 'ifauto',
                     'dfport', 'dflib', 'dfwin', 'dflogm', 'dfauto']
ignore_warnings = '7000,7954,8290,8291'


if platform.system() == 'Windows':
    null_device = 'nul'
elif platform.system() == 'Linux':
    null_device = '/dev/null'


def isNotQuoted(line, position):  # assuming that everything is fine with quotes
    if not any([(quote in line) for quote in quotes_set]):
        return True

    quote_status = -1
    for pos, symbol in enumerate(line):
        if pos == position:
            return False if quote_status != -1 else True

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


parser = optparse.OptionParser()
parser.add_option('--config',
                  dest='configuration',
                  action='store',
                  default='release',
                  help='select required configuration [debug,release]')

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
                  help='ignore path (seperate by ;)')

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
                  help='specify dependence')

parser.add_option('--extension',
                  dest='extension',
                  action='store',
                  default='.f90',
                  help='specify source files extension')

(options, args) = parser.parse_args()

# ()()()()()()()()()()()()()()()()()() PROCEED ARGUMENTS ()()()()()()()()()()()()()()()()()() #

if options.configuration not in ['debug', 'release']:
	raise ArgumentError('Invalid "--config" value. Should be in ["debug", "release"].')

if options.dependency not in ['object files', 'modules']:
    raise ArgumentError('Invalid "--dependence" value. Should be in ["object files", "modules"].')

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
            options.compiler_pparams = '/O1 /C /traceback /Qdiag-disable:' + ignore_warnings + ' /nologo'
        elif platform.system() == 'Linux':
            options.compiler_pparams = '-O1 -C -traceback -diag-disable ' + ignore_warnings + ' -nologo'

    if options.configuration == 'release':
        if platform.system() == 'Windows':
            options.compiler_pparams = '/O3 /Qdiag-disable:' + ignore_warnings + ' /nologo'
        elif platform.system() == 'Linux':
            options.compiler_pparams = '-O3 -diag-disable ' + ignore_warnings + ' -nologo'

if not options.compiler_sparams:
    if platform.system() == 'Windows':
        options.compiler_sparams = '/Qopenmp'
    elif platform.system() == 'Linux':
        options.compiler_sparams = '-openmp'

ignore_path_set = []
if options.ignore:
    ignore_path_set = options.ignore.split(';')

fileset = []
for (dirpath, dirnames, filenames) in os.walk('.'):  # collect all source files recursively
    fileset.extend([os.path.join(dirpath, file)
                    for file in filenames if file.endswith(options.extension)])

if ignore_path_set:
    ignore_path_set = ['.' + os.path.sep + ignored for ignored in ignore_path_set]
    for file in fileset[::-1]:
        for ignored in ignore_path_set:
            if file.startswith(ignored):
                fileset.remove(file)

contains = {}; program = {}; non_interfaced = True; module_location={}
for file in fileset:  # location of program units
    filecontains = {'modules': [], 'subroutines': [], 'functions': [], 'dependencies': []}
    for line in open(file, 'r'):  # assume that key statements are written without ;&!

        if '!' in line and isNotQuoted(line, line.index('!')):
            line = line[:line.index('!')]  # remove comment

        uline = line.lower().strip()
        statement, *other = uline.split(' ')

        if statement == 'interface':
            if isNotQuoted(statement, statement.index('interface')):
                non_interfaced = False
                continue

        if uline.startswith('end interface') or uline.startswith('endinterface'):
            non_interfaced = True
            continue

        if statement == 'module' and other[0] != 'procedure':
            if isNotQuoted(statement, statement.index('module')):
                module_name = other[0].strip()
                filecontains['modules'].append(module_name)
                module_location[module_name] = file
                continue

        if statement == 'subroutine' and non_interfaced:
            if isNotQuoted(statement, statement.index('subroutine')):
                filecontains['subroutines'].append(other[0][:get_name_len(other[0])])
                continue

        if statement == 'program':
            if isNotQuoted(statement, statement.index('program')):
                if program:
                    raise FortranCodeError('Found more than one program statement.')
                program = {'name': other[0], 'location': file}
                continue

        if statement == 'use':
            if isNotQuoted(statement, statement.index('use')):
                if other[0][:get_name_len(other[0])] not in available_modules:
                    filecontains['dependencies'].append(other[0][:get_name_len(other[0])])
                    continue

        if 'function' in uline and not uline.startswith('end') and non_interfaced:
            if isNotQuoted(uline, uline.index('function')):
                words = uline.split(' ')
                position = words.index('function')
                filecontains['functions'].append(words[position+1][:get_name_len(words[position+1])])
                continue

    contains[file] = dict(filecontains)

for file in fileset:
    contains[file]['dependencies'] = list(set(contains[file]['dependencies']))
    for module in contains[file]['modules']:
        if module in contains[file]['dependencies']:  # remove self-dependencies
            contains[file]['dependencies'].remove(module)

obj_order = []; modules_proc = []; files_unproc = fileset[:]
while files_unproc:
    for file in files_unproc:
        if all([(module in modules_proc) if contains[file]['dependencies'] else True
                for module in contains[file]['dependencies']]):
            modules_proc.extend(contains[file]['modules'])
            obj_order.append(file)
            files_unproc.remove(file)
            break
    else:
        raise FortranCodeError('Cannot resolve dependencies. Probably cross-dependence.')

#prepare_objs =
obj_string = get_file_list('OBJS',
                           [obj.replace(options.extension, options.obj_extension) for obj in obj_order])

mod_string = get_file_list('MODS', [module + '.mod' for module in modules_proc])

mkfile = open(options.mfname, 'w')

mkfile.write('# generated automatically with command line:\n')
mkfile.write('# {} {} \n'.format(os.path.split(sys.argv[0])[1], ' '.join(sys.argv[1:])))
mkfile.write('# paltform: {}\n\n'.format(platform.system()))

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
        deps = [module_location[dep].replace(options.extension, options.obj_extension)
                for dep in contains[obj]['dependencies']]
    else:
        deps = [dep + '.mod' for dep in contains[obj]['dependencies']]

    deps.append(obj)
    mkfile.write(obj.replace(options.extension, options.obj_extension) + ': ' + ' '.join(deps) + '\n')
    mkfile.write('\t$(COM) -c $(PFLAGS) $(SFLAGS) {} -o {}\n'.format(
                 obj, obj.replace(options.extension, options.obj_extension)))

rm_recursive_obj = ('\tfind | grep -E "*\\' +
                    options.obj_extension + '" | xargs rm 2>' + null_device + '\n')

rm_recursive_mod = ('\tfind | grep -E "*\\' +
                    '.mod" | xargs rm 2>' + null_device + '\n')

if platform.system() == 'Windows':
    call_makefile = 'nmake -f ' + options.mfname
elif platform.system() == 'Linux':
    call_makefile = 'make -f ' + options.mfname

mkfile.write('\nrm_objs:\n')
#mkfile.write(rm_recursive_obj + '\n')
mkfile.write('\trm $(OBJS)\n\n')

mkfile.write('rm_mods:\n')
#mkfile.write(rm_recursive_mod + '\n')
mkfile.write('\trm $(MODS)\n\n')

mkfile.write('clean:\n')
mkfile.write('\t$(MAKE) rm_objs\n')
mkfile.write('\t$(MAKE) rm_mods\n\n')

mkfile.write('cleanall:\n')
mkfile.write('\t$(MAKE) clean\n')
mkfile.write('\trm $(NAME)\n\n')

mkfile.write('remake:\n')
mkfile.write('\t$(MAKE) cleanall\n')
mkfile.write('\t$(MAKE)\n\n')

mkfile.write('build:\n')
mkfile.write('\t$(MAKE) cleanall\n')
mkfile.write('\t$(MAKE)\n')
mkfile.write('\t$(MAKE) clean\n\n')

'''
mkfile.write('set_env:\n')
mkfile.write('\t' +
    r'C:\"Program Files (x86)"\Intel\ComposerXE-2011\bin\compilervars_arch.bat intel64' +
    '\n\n')
'''

mkfile.close()

if options.make:
    os.system(call_makefile)

'''
print ('Obj files order:',obj_order,end='\n\n')
print ('Program',program['name'],'enter is located in',program['location'])
print ('*'*78)
for file in fileset:
    print ('File:',file)
    print ('Modules:',contains[file]['modules'])
    print ('Dependencies:',contains[file]['dependencies'])
    print ('Subroutines:',contains[file]['subroutines'])
    print ('Functions:',contains[file]['functions'])
    print ('*'*78)
'''
