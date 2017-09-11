import os
import re
import sys
from sys import exit as stop

from optparse import OptionParser


class FortranCodeError(Exception):
    pass


quotes_set = "'" + '"'
name_pattern = 'a-zA-Z0-9_'
available_modules = ['ifport', 'ifposix', 'ifcore', 'ifqwin', 'iflogm', 'ifcom', 'ifauto',
                     'dfport', 'dflib', 'dfwin', 'dflogm', 'dfauto']


def isQuoted(line, position):  # assuming that everything is fine with quotes
    if not any([(quote in line) for quote in quotes_set]):
        return False

    quote_status = -1
    for pos, symbol in enumerate(line):
        if pos == position:
            return True if quote_status != -1 else False

        if symbol in quotes_set:
            current_quote = [quote == symbol for quote in quotes_set].index(True)

            if quote_status == -1:
                quote_status = current_quote
            elif quote_status == current_quote:
                quote_status = -1


def get_name_len(string):
    result = re.search('[^' + name_pattern + ']', string)
    return result.start() if result else None


mkfile = open('Makefile', 'w')

parser = OptionParser()
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
                  default='/O3 /Qdiag-disable:8291,7954 /nologo',
                  help='specify primary compiler parameters')

parser.add_option('--sparams',
                  dest='compiler_sparams',
                  action='store',
                  default='/Qopenmp',
                  help='specify secondary compiler parameters')

parser.add_option('--appname',
                  dest='appname',
                  action='store',
                  default='appname.exe',
                  help='specify application name')

parser.add_option('--make',
                  dest='make',
                  action='store_true',
                  default=False,
                  help='call make')

(options, args) = parser.parse_args()

pparams_set = '--pparams' in ' '.join(sys.argv[1:])

if not options.appname.endswith('.exe'):
    options.appname += '.exe'

if options.configuration == 'debug':
    if not pparams_set:
        options.compiler_pparams = '/O1 /C /traceback /Qdiag-disable:8291,7954 /nologo'

if options.configuration == 'release':
    if not pparams_set:
        options.compiler_pparams = '/O3 /Qdiag-disable:8291,7954 /nologo'

fileset = []
for (dirpath, dirnames, filenames) in os.walk('.'):  # collect all source files recursively
    fileset.extend([os.path.join(dirpath, file) for file in filenames if file.endswith('.f90')])

contains = {}; program = {}; non_interfaced = True; module_location={}
for file in fileset:  # location of program units
    filecontains = {'modules': [], 'subroutines': [], 'functions': [], 'dependencies': []}
    for line in open(file, 'r'):  # assume that key statements are written without ;&!

        if '!' in line:
            line = line[:line.index('!')]  # remove comment

        uline = line.lower().strip()
        statement, *other = uline.split(' ')

        if statement == 'interface':
            non_interfaced = False
            continue

        if uline.startswith('end interface') or uline.startswith('endinterface'):
            non_interfaced = True
            continue

        if statement == 'module' and other[0] != 'procedure':
            module_name = other[0].strip()
            filecontains['modules'].append(module_name)
            module_location[module_name] = file

        if statement == 'subroutine' and non_interfaced:
            filecontains['subroutines'].append(other[0][:get_name_len(other[0])])

        if statement == 'program':
            if program:
                raise FortranCodeError('Found more than one program statement.')
            program = {'name': other[0], 'location': file}

        if statement == 'use':
            if other[0][:get_name_len(other[0])] not in available_modules:
                filecontains['dependencies'].append(other[0][:get_name_len(other[0])])

        if 'function' in uline and not uline.startswith('end') and non_interfaced:
            words = uline.split(' ')
            position = words.index('function')
            filecontains['functions'].append(words[position + 1][:get_name_len(words[position + 1])])

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

#print(module_location); stop()

prepare_objs = [obj.replace('.f90', '.obj') for obj in obj_order]

line_width = 80
obj_string = 'OBJS= \\\n'
while prepare_objs:
    count = 0
    while True:
        count += 1

        width = sum([len(obj) for obj in prepare_objs[:count]]) + (count - 1) + 2
        if width > line_width:
            obj_string += ' '.join(prepare_objs[:count - 1]) + ' \\\n'
            prepare_objs = prepare_objs[count - 1:]
            break

        if count == len(prepare_objs):
            obj_string += ' '.join(prepare_objs[:count]) + '\n'
            prepare_objs = []
            break

mkfile.write('\n')
mkfile.write('NAME=' + options.appname + '\n')
mkfile.write('COM=' + options.compiler + '\n')
mkfile.write('PFLAGS=' + options.compiler_pparams + '\n')
mkfile.write('SFLAGS=' + options.compiler_sparams + '\n\n')

mkfile.write(obj_string + '\n\n')
mkfile.write('$(NAME): $(OBJS)' + '\n')
mkfile.write('\t' + '$(COM) $(OBJS) $(SFLAGS) -o $(NAME)' + '\n\n')

for obj in obj_order:
    deps = [module_location[dep].replace('.f90', '.obj') for dep in contains[obj]['dependencies']]
    deps.append(obj)
    mkfile.write(obj.replace('.f90', '.obj') + ': ' + ' '.join(deps) + '\n')
    mkfile.write('\t$(COM) -c $(PFLAGS) $(SFLAGS) ' + obj + '\n')

mkfile.write('\n')
mkfile.write('clean:\n')
mkfile.write('\terase *.obj\n')
mkfile.write('\terase *.mod\n\n')

mkfile.write('cleanall:\n')
mkfile.write('\terase *.obj\n')
mkfile.write('\terase *.mod\n')
mkfile.write('\terase $(NAME)\n\n')

mkfile.write('remake:\n')
mkfile.write('\terase *.obj\n')
mkfile.write('\terase *.mod\n')
mkfile.write('\terase $(NAME)\n')
mkfile.write('\tnmake -f Makefile\n\n')

mkfile.write('build:\n')
mkfile.write('\terase *.obj\n')
mkfile.write('\terase *.mod\n')
mkfile.write('\terase $(NAME)\n')
mkfile.write('\tnmake -f Makefile\n')
mkfile.write('\terase *.obj\n')
mkfile.write('\terase *.mod\n\n')

mkfile.write('set_env:\n')
mkfile.write('\t' +
    r'C:\"Program Files (x86)"\Intel\ComposerXE-2011\bin\compilervars_arch.bat intel64' +
    '\n\n')

mkfile.close()

if options.make:
    os.system('nmake -f Makefile')

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
