import os
import re
import sys
import optparse


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

parser.add_option('--ignore-path',
                  dest='ignore',
                  action='store',
                  default=None,
                  help='ignore path (seperate by ;)')

(options, args) = parser.parse_args()

if not options.appname.endswith('.exe'):
    options.appname += '.exe'

if not options.compiler_pparams:
    if options.configuration == 'debug':
        options.compiler_pparams = '/O1 /C /traceback /Qdiag-disable:8291,7954 /nologo'

    if options.configuration == 'release':
        options.compiler_pparams = '/O3 /Qdiag-disable:8291,7954 /nologo'

if options.ignore:
    ignore_path_set = options.ignore.split(';')

fileset = []
for (dirpath, dirnames, filenames) in os.walk('.'):  # collect all source files recursively
    fileset.extend([os.path.join(dirpath, file) for file in filenames if file.endswith('.f90')])

ignore_path_set = ['.\\' + ignored for ignored in ignore_path_set]

for file in fileset[::-1]:
    for ignored in ignore_path_set:
        if file.startswith(ignored):
            fileset.remove(file)

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
            filecontains['functions'].append(words[position+1][:get_name_len(words[position+1])])

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

prepare_objs = [obj.replace('.f90', '.obj') for obj in obj_order]

line_width = 80
obj_string = 'OBJS= \\\n'
while prepare_objs:
    count = 0
    while True:
        count += 1

        width = sum([len(obj) for obj in prepare_objs[:count]]) + (count-1) + 2
        if width > line_width:
            obj_string += ' '.join(prepare_objs[:count-1]) + ' \\\n'
            prepare_objs = prepare_objs[count-1:]
            break

        if count == len(prepare_objs):
            obj_string += ' '.join(prepare_objs[:count]) + '\n'
            prepare_objs = []
            break

mkfile = open('Makefile', 'w')

mkfile.write('# generated automatically with command line:\n')
mkfile.write('# {} {} \n\n'.format(os.path.split(sys.argv[0])[1], ' '.join(sys.argv[1:])))

mkfile.write('NAME={}\n'.format(options.appname))
mkfile.write('COM={}\n'.format(options.compiler))
mkfile.write('PFLAGS={}\n'.format(options.compiler_pparams))
mkfile.write('SFLAGS={}\n'.format(options.compiler_sparams))

mkfile.write(obj_string + '\n\n')
mkfile.write('$(NAME): $(OBJS)\n')
mkfile.write('\t$(COM) $(OBJS) $(SFLAGS) -o $(NAME)\n\n')

for obj in obj_order:
    deps = [module_location[dep].replace('.f90', '.obj') for dep in contains[obj]['dependencies']]
    deps.append(obj)
    mkfile.write(obj.replace('.f90', '.obj') + ': ' + ' '.join(deps) + '\n')
    mkfile.write('\t$(COM) -c $(PFLAGS) $(SFLAGS) {} -o {}\n'.format(
                 obj, obj.replace('.f90', '.obj')))

rm_recursive_obj = '\tfind | grep -E "*\.obj" | xargs rm 2>nul\n'
rm_recursive_mod = '\tfind | grep -E "*\.mod" | xargs rm 2>nul\n'

mkfile.write('\n')
mkfile.write('clean:\n')
mkfile.write(rm_recursive_obj)
mkfile.write(rm_recursive_mod + '\n')

mkfile.write('cleanall:\n')
mkfile.write(rm_recursive_obj)
mkfile.write(rm_recursive_mod)
mkfile.write('\trm $(NAME)\n\n')

mkfile.write('remake:\n')
mkfile.write(rm_recursive_obj)
mkfile.write(rm_recursive_mod)
mkfile.write('\trm $(NAME)\n')
mkfile.write('\tnmake -f Makefile\n\n')

mkfile.write('build:\n')
mkfile.write(rm_recursive_obj)
mkfile.write(rm_recursive_mod)
mkfile.write('\trm $(NAME)\n')
mkfile.write('\tnmake -f Makefile\n')
mkfile.write(rm_recursive_obj)
mkfile.write(rm_recursive_mod + '\n')

mkfile.write('rm_objs:\n')
mkfile.write(rm_recursive_obj + '\n')

mkfile.write('rm_mods:\n')
mkfile.write(rm_recursive_mod + '\n')

'''
mkfile.write('set_env:\n')
mkfile.write('\t' +
    r'C:\"Program Files (x86)"\Intel\ComposerXE-2011\bin\compilervars_arch.bat intel64' +
    '\n\n')
'''

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
