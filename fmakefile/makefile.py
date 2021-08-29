
import os
import sys
import re
import platform
import subprocess
import logging
import datetime

####################################################################################################

logger = logging.getLogger(__name__)

####################################################################################################

platform_ = platform.system()

PRESETS = {
           'ifort': {
                     'Windows': {
                                 'pparams':    '/O3 /fpp /Qdiag-disable:7000,7734,7954,8290,8291 /nologo',
                                 'sparams':    '/Qopenmp',
                                 'stdmodules': [
                                                'ifport', 'ifposix', 'ifcore', 'ifqwin',
                                                'iflogm', 'ifcom', 'ifauto', 'omp_lib',
                                                'dfport','dflib', 'dfwin', 'dflogm', 'dfauto'
                                               ],
                                 'stdincludes': ['omp_lib.h']
                                },
                     'Linux': {
                               'pparams':     '-O3 -fpp -diag-disable 7000,7734,7954,8290,8291',
                               'sparams':     '-qopenmp',
                               'stdmodules':  [
                                               'ifport', 'ifposix', 'ifcore', 'ifqwin',
                                               'iflogm', 'ifcom', 'ifauto', 'omp_lib',
                                               'dfport','dflib', 'dfwin', 'dflogm', 'dfauto'
                                              ],
                               'stdincludes': ['omp_lib.h']
                              }
                    },

           'gfortran': {
                        'Windows': {
                                    'pparams':     '-O3 -fsyntax-only',
                                    'sparams':     '-fopenmp',
                                    'stdmodules':  [],
                                    'stdincludes': []
                                   },
                        'Linux': {
                                 'pparams':     '-O3 -fsyntax-only',
                                 'sparams':     '-fopenmp',
                                 'stdmodules':  [],
                                 'stdincludes': []
                                 }
                       }
          }

####################################################################################################

class FortranCodeError(Exception):
    '''
    Raised when Fortran syntax is violated.
    '''
    pass

####################################################################################################

def remove_extenstions(string, suffix):
    '''
    Remove substring(s) from the end of the string.

    Arguments:
        string - target string [string]
        suffix - suffix(es) to be removed [string or list/tuple/set of strings]
    '''
    if isinstance(suffix, (tuple, set, list)):
        for sub in suffix:
            if string.endswith(sub):
                string = string[:-len(sub)]
    elif isinstance(suffix, str):
        if string.endswith(suffix):
            string = string[:-len(suffix)]
    else:
        raise TypeError('Expected str or list of str, while got %s' % type(suffix))

    return string

####################################################################################################

def is_quoted(line, position):
    '''
    Check whether selected <position> is quoted.

    Arguments:
        line     - line for search  [string or list of chars]
        position - position to be tested [int]

    Return:
        boolean
    '''
    quotes = chr(34)+chr(39)

    if not any([(quote in line) for quote in quotes]):
        return False

    if position > len(line) or position < 0:
        raise IndexError('Inquired position is beyond the string.')

    status = None
    for pos, symbol in enumerate(line):
        if pos == position:
            return bool(status)

        if symbol in quotes:
            current_quote = symbol

            if status is None:
                status = current_quote
            elif status == current_quote:
                status = None

    raise FortranCodeError('Probably quotes are not balanced: (%s)' % line)

####################################################################################################

def dequote(line):
    '''
    Gentle quotes stripping.
    '''
    while True:
        if line.startswith('"') or line.startswith("'"):
            line = line[1:]
        else:
            break

    while True:
        if line.endswith('"') or line.endswith("'"):
            line = line[:-1]
        else:
            break
    return line

####################################################################################################

def is_keyword(line, keyword, before=False):
    '''
    Check whether <line> contains <keyword>.

    Arguments:
        line    - line for search
        keyword - keyword that is being looked for
        before  - set True if need guarantee previous symbol to be non-alphabetic

    Returns:
        boolean
    '''
    try:
        ln, pos = len(keyword), line.index(keyword)
    except ValueError:  # keyword is not found in the line
        return False

    # keyword len is equal to line len
    if ln+pos >= len(line):
        return True

    extra = True
    if before:
        if pos != 0:
            if line[pos-1].isalpha():  # previous symbol is letter
                extra = False

    return not is_quoted(line, pos) and not line[ln+pos].isalpha() and extra

####################################################################################################

def extract_element_name(string):
    '''
    Get the name given to element.
        e.g. subroutine hello(world) returns hello
    '''

    # find first symbol that is not allowed to use in names.
    result = re.search('[^a-zA-Z0-9_]', string)
    return string[:result.start()] if result else string

####################################################################################################

def replace_extension(filename, extensions, object_extension):
    '''
    Convert source file name into object file name.

    Arguments:
        filename         - the name of source file
        extensions       - extension list undergo changes
        object_extension - desired extension

    Returns:
        <filename> with replaced extension if found in <extensions>, else return <filename>
    '''
    for e in extensions:
        if filename.endswith(e):
            return filename.replace(e, object_extension)
    else:
        return '%s.%s' % (filename, object_extension)

####################################################################################################

def get_wrapped_line(objects, prefix='', postfix='', sep=' ', width=80, end='\\', adjust=True):
    '''
    Generate multiline block for the list.

    Arguments:
        objects - list of objects to be put in the block
        prefix  - prefix for the first line of the block
        postfix - postfix for the last line of the block
        sep     - separator
        width   - line width to cut the block
        end     - ending for every line
        adjust  - if True, indent every line to be at the same level with the prefix

    Return:
        multiline block
    '''
    indent = ''
    if adjust:
        indent = ' '*len(prefix)

    raw, result, line = objects[:], '', prefix
    while raw:
        if len(line+sep+raw[0])+len(end)+1 > width:
            free_space = ' '*(width-len(line)-len(end))

            result += line + free_space + end + '\n'
            if adjust:
                line = indent
            continue
        line += raw.pop(0)+sep
    result += line.rstrip(sep)

    return result + postfix

####################################################################################################

def has_extension(file, extensions):
    '''
    Check whether <file> contains one of <extensions>.

    Arguments:
        file       - filename
        extensions - the list of extenstions to be tested for

    Returns:
        boolean
    '''
    return any([file.endswith(e) for e in extensions])

####################################################################################################

def draw_directory_tree(fileset, indent_size=3):
    '''
    Output directory tree.

    Arguments:
        fileset     - set of files (with pathes)
        indent_size - size of indention (spaces)
    '''
    indent = ' '*indent_size

    def update_tree(root, branch):
        current = root
        for node in branch:
            if node not in current:
                current[node] = {}
            current = current[node]

    def unfold(tree, level=0):
        if tree:
            for node in tree:
                prefix = '\n' if tree[node] else ''
                print('%s%s%s %s' % (prefix, indent*level, '--', node))
                unfold(tree[node], level+1)

    tree = {}
    for file in fileset:
        update_tree(tree, expand_path(file)[1:])

    print('Project:')
    unfold(tree, 1)

####################################################################################################

def expand_path(path):
    '''
    Split path into parts.
    '''
    parts = []
    while True:
        path, folder = os.path.split(path)

        if folder:
            parts.insert(0, folder)
        else:
            if path:
                parts.insert(0, path)
            break
    return parts

####################################################################################################

def collect_files(directory, ignore_paths, extensions):
        '''
        Collect files for the project stored in <directory>.

        Arguments:
            directory    - directory to proceed
            ignore_paths - subdirectories to be excluded
            extensions   - the set of extensions
        '''

        # add project prefix for ignored directories
        ignored_paths = [os.path.join(directory, path) for path in ignore_paths]

        fileset = []
        for (dirpath, _, files) in os.walk(directory):
            for file in files:

                # it fits one of extensions
                if has_extension(file, extensions):
                    path = os.path.join(dirpath, file)

                    for ignored in ignored_paths:
                        if path.startswith(ignored):
                            break
                    else:
                        fileset.append(path)

        return fileset

####################################################################################################

def purify_path(path):
    '''
    Remove .. and . from the path.
    '''
    tree = expand_path(path)
    purified = []
    for k, part in enumerate(tree):
        if k == 0 and part == '.':
            purified.append('.')
            continue
        if part == '..':
            purified.pop()
            continue
        if part == '.':
            continue
        purified.append(part)
    return os.path.join(*purified)

####################################################################################################

def purify_include(path):
    '''
    Extract name from 'include' statement.
    '''
    return dequote(path.strip().split(' ', 1)[1].strip())

####################################################################################################

def read_with_encoding_guess(file, *, debug=False, encoding=None, **kwargs):
    '''
    Try to guess encoding of the file. Function is called to solve the problem
    with cyrillic comments.

    Arguments:
        file     - filename
        debug    - show debug information
        encoding - force to use encoding, if is given will skip guess procedure
        kwargs   - keyword arguments of the open function
    '''
    guesses = ['utf-8', 'windows-1251', 'cp866', 'ascii', 'windows-1252']

    # in case of incorrect encoding will raise UnicodeDecodeError
    if encoding and encoding not in guesses:
        return open(file, encoding=encoding, **kwargs).readlines()

    if debug:
        print('Reading file %s.' % file)

    notutf = False
    for encoding_ in guesses:
        try:
            result = open(file, encoding=encoding_, **kwargs).readlines()
            if notutf and debug:
                print('Success in reading with %s encoding.' % encoding_)
            return result

        except UnicodeDecodeError:
            notutf = True
            pass

    raise UnicodeDecodeError('Unable to guess encoding. None of %s.' % guesses)

####################################################################################################

class ProjectParser:
    '''
    Class for Fortran project analysis.
    '''
    DEFAULTS = {
                'drop_execute_flag': True,
                'verbose':           True,
                'debug':             False,
                'encoding':          'utf-8',
                'extensions':        ['.f90', '.F90', '.f', '.F', '.for', '.FOR'],
                'compiler':          'ifort',
                'appname':           'appname',
                'object_extension':  '.obj',
                'dependency':        'object files',
                'makefile_name':     'Makefile',
                'pcompiler_params':  PRESETS['ifort'][platform_]['pparams'],
                'scompiler_params':  PRESETS['ifort'][platform_]['sparams'],
                'ignore_paths':      [],
                'ignore_modules':    PRESETS['ifort'][platform_]['stdmodules'],
                'ignore_includes':   PRESETS['ifort'][platform_]['stdincludes'],
               }

    def __init__(self, **kwargs):
        '''
        Arguments:
            drop_execute_flag - make all source files not executable
            verbose           - verbose process
            debug             - print debug information
            encoding          - encoding of source files
            extensions        - the set of extensions
            compiler          - compiler
            appname           - application name
            object_extension  - object files extension
            dependency        - dependence mode (object files, modules)
            makefile_name     - the name of makefile
            pcompiler_params  - primary compiler parameters
            scompiler_params  - secondary compiler parameters
            ignore_paths      - the set of paths to be ignored
            ignore_modules    - the set of available modules
            ignore_includes   - the set of available include files
        '''
        check_arguments = set(kwargs) - set(ProjectParser.DEFAULTS)
        if check_arguments:
            raise KeyError('Unexpected argument(s): %s' % list(check_arguments))

        for key in ProjectParser.DEFAULTS:
            if key in ('ignore_modules', 'ignore_includes'):
                if key in kwargs:
                    setattr(self, key, ProjectParser.DEFAULTS[key].extend(kwargs[key]))
                    continue

            setattr(self, key, kwargs.get(key, ProjectParser.DEFAULTS[key]))

        self.includes = []

        appname = remove_extenstions(self.appname, ('.x', '.exe'))
        if platform_ == 'Linux':
            self.appname = appname + '.x'
        elif platform_ == 'Windows':
            self.appname = appname + '.exe'

    def _parse_source_file(self, file):

        filecontains = {'modules': [], 'subroutines': [], 'functions': [],
                        'dependencies': [], 'includes': [], 'entry_point': False}

        non_interfaced = True

        # assume that key statements are written without ;&!
        for line in read_with_encoding_guess(file, debug=self.debug, encoding=self.encoding):

            # cut comment if exist
            if '!' in line and not is_quoted(line, line.index('!')):
                line = line[:line.index('!')]

            uline = line.lower().strip()
            statement, *other = uline.split(' ')

            if not other:
                continue

            if is_keyword(statement, 'interface'):
                non_interfaced = False
                continue

            if uline.startswith('end interface') or uline.startswith('endinterface'):
                non_interfaced = True
                continue

            if is_keyword(statement, 'module') and other[0] != 'procedure':
                module_name = other[0].strip()
                if module_name not in filecontains['modules']:
                    filecontains['modules'].append(module_name)
                self.modules[module_name] = file
                continue

            if is_keyword(statement, 'include'):

                # initial case (not lowered) is required due to UNIX case sensitivity
                include_source = purify_include(line)
                if include_source in self.ignore_includes:
                    continue

                include_file = purify_path(os.path.join(os.path.dirname(file), include_source))

                self.includes.append(include_file)

                filecontains['includes'].append(include_file)
                result = self._parse_source_file(include_file)

                for key in result:
                    if key != 'entry_point':
                        for val in result[key]:
                            if val not in filecontains[key]:
                                filecontains[key].append(val)
                continue

            if is_keyword(statement, 'subroutine') and non_interfaced:
                subroutine_name = extract_element_name(other[0])
                if subroutine_name not in filecontains['subroutines']:
                    filecontains['subroutines'].append(subroutine_name)
                self.subroutines[subroutine_name] = file
                continue

            if is_keyword(statement, 'program'):
                if self.entry_point:
                    print('>>', self.entry_point['name'], 'in', self.entry_point['location'])
                    print('>>', other[0], 'in', file)
                    print()
                    raise FortranCodeError('Found more than one entry point.')

                self.entry_point = {'name': other[0], 'location': file}
                filecontains['entry_point'] = True
                continue

            if is_keyword(statement, 'use', True):
                module = extract_element_name(other[0])
                if module not in self.ignore_modules:
                    if module not in filecontains['dependencies']:
                        filecontains['dependencies'].append(module)
                continue

            if ('function' in uline and is_keyword(uline, 'function') and
                not uline.startswith('end') and non_interfaced):
                words = uline.split(' ')
                position = words.index('function')+1

                function_name = extract_element_name(words[position])
                filecontains['functions'].append(function_name)
                self.functions[function_name] = file
                continue

        return filecontains

    def _parse_project(self):
        self.entry_point = None
        self.empty_files = []

        if self.debug:
            print('========== PROJECT INFORMATION ==========\n')

        self.structure, self.modules, self.functions, self.subroutines = {}, {}, {}, {}
        for file in self.fileset:

            contains = self._parse_source_file(file)

            is_empty = not any([bool(item) for item in contains.items()])
            if is_empty:
                self.empty_files.append(file)

            if self.debug:
                width = max([len(key) for key in contains.keys()])
                print('*** File [%s]' % file, end=' ')
                if not is_empty:
                    print('info:')
                    for key in contains:
                        if key in ('entry_point', 'functions'):
                            continue
                        if contains[key]:
                            elems  = list(set(contains[key]))
                            prefix = '>>> %s%s: [' % (key, ' '*(width-len(key)))
                            block = get_wrapped_line(elems, prefix, postfix=']', sep=', ', end='')
                            print(block)
                else:
                    print('is empty.')

                if contains['entry_point']:
                    print('!!! contains program entry.')
                print()

            self.structure[file] = contains

        if self.empty_files:
            if self.debug:
                print()
                print('Empty stream(s):')
                for i, file in enumerate(self.empty_files):
                    print('%2d) %s' % (i+1, file))
                print('Rename file(s) (name -> name~) to exclude them from the list.')
                print()
            raise FortranCodeError('Empty stream(s) found.')

    def _resolve_dependencies(self):

        # remove self-dependencies
        for file in self.fileset:
            for module in self.structure[file]['modules']:
                if module in self.structure[file]['dependencies']:
                    self.structure[file]['dependencies'].remove(module)

        objects, modules, unproc = [], [], self.fileset[:]
        while True:
            removed = 0
            for file in unproc:
                if all([(module in modules) if self.structure[file]['dependencies'] else True
                        for module in self.structure[file]['dependencies']]):
                    modules.extend(self.structure[file]['modules'])
                    objects.append(file)
                    unproc.remove(file)
                    removed += 1

            if not unproc:
                break

            if not removed:
                print('\nFiles with unresolved dependencies:')
                for file in unproc:
                    print('Name', file)
                    print('Dependencies:')
                    k = 0
                    for dep in self.structure[file]['dependencies']:
                        if dep not in modules:
                            k += 1
                            print('  %2d) %s' % (k, dep))
                print()
                msg = 'Cannot resolve dependencies. Probably cross-dependence or missing modules.'
                raise FortranCodeError(msg)

        return objects, modules

####################################################################################################

    def analize_project(self, directory):
        # TODO
        pass

####################################################################################################

    def create_makefile(self, directory):
        '''
        Generate makefile for project at <directory> path.
        '''
        self.generated = datetime.datetime.now()

        self.fileset = collect_files(directory, self.ignore_paths, self.extensions)
        self._parse_project()

        if self.verbose:
            draw_directory_tree(self.fileset+self.includes)
            print()
            print('appname:             ', self.appname)
            print('compiler:            ', self.compiler)
            print('primary parameters:  ', self.pcompiler_params)
            print('secondary parameters:', self.scompiler_params)
            print('available recipes:   ', 'rm_objs rm_mods rm_app clean cleanall remake build')

        if self.drop_execute_flag:
            if platform_ == 'Linux':
                subprocess.call(['chmod', 'a-x'] + self.fileset)

        objects, modules = self._resolve_dependencies()

        objs = [replace_extension(obj, self.extensions, self.object_extension) for obj in objects]
        mods = [module + '.mod' for module in modules]

        obj_string = get_wrapped_line(objs, prefix='OBJS = ')
        mod_string = get_wrapped_line(mods, prefix='MODS = ')

        mkfile = open(self.makefile_name, 'w')

        mkfile.write('\n# %s #\n' % ('()'*25))
        mkfile.write('# %s\n' % (self.generated.strftime("%Y-%m-%d %H:%M")))
        mkfile.write('# generated automatically with command line:\n')
        mkfile.write('# {} {} \n'.format(os.path.split(sys.argv[0])[1], ' '.join(sys.argv[1:])))
        mkfile.write('# paltform: {}\n'.format(platform_))
        mkfile.write('# %s #\n\n' % ('()'*25))

        mkfile.write('NAME={}\n'.format(self.appname))
        mkfile.write('COM={}\n'.format(self.compiler))
        mkfile.write('PFLAGS={}\n'.format(self.pcompiler_params))
        mkfile.write('SFLAGS={}\n\n'.format(self.scompiler_params))

        mkfile.write(obj_string + '\n\n')
        mkfile.write(mod_string + '\n\n')
        mkfile.write('$(NAME): $(OBJS)\n')
        mkfile.write('\t$(COM) $(OBJS) $(SFLAGS) -o $(NAME)\n\n')

        for obj in objects:

            if self.dependency == 'object files':
                deps = [replace_extension(self.modules[dep], self.extensions, self.object_extension)
                        for dep in self.structure[obj]['dependencies']]
            else:
                deps = [dep + '.mod' for dep in self.structure[obj]['dependencies']]

            deps += self.structure[obj]['includes']

            deps.append(obj)
            dstring = ' '.join(deps)
            ostring = replace_extension(obj, self.extensions, self.object_extension)

            mkfile.write('%s: %s\n' % (ostring, dstring))
            mkfile.write('\t$(COM) -c $(PFLAGS) $(SFLAGS) {} -o {}\n'.format(
                         obj, replace_extension(obj, self.extensions, self.object_extension)))

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

        if self.verbose:
            print('created:             ', self.makefile_name)
