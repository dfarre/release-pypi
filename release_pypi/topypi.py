import configparser
import os
import shutil
import subprocess
import sys

from packaging import version

from simple_cmd import commands


class VersionFile:
    qualifiers = ('pre', 'post', 'dev')

    def __init__(self, path='version.ini'):
        self.ini = configparser.ConfigParser()
        self.ini.read(path)
        self.path = path

    def __repr__(self):
        return f'<{self.__class__.__name__}: {self}>'

    def __str__(self):
        return f'{self.name}-{self.v}'

    @property
    def v(self):
        return version.Version(self.ini['version']['value'])

    @property
    def name(self):
        return self.ini['version']['name']

    def put(self, text, key='value'):
        self.ini['version'][key] = text

        with open(self.path, 'w') as wfile:
            self.ini.write(wfile)

    def up(self, *inc):
        """Shifts version and prunes qualifiers"""
        release, inc = self.v.release, list(map(int, inc))
        head, tail = inc[:len(release)], inc[len(release):]

        if not tail and len(release) > len(head):
            head = [0]*(len(release) - len(head)) + head

        self.put('.'.join(map(str, list(map(sum, zip(release, head))) + tail)))

    def qualify(self, **incs):
        current = dict(map(
            lambda it: (it[0], it[1][1] if isinstance(it[1], tuple) else it[1]),
            filter(lambda it: it[1] is not None, (
                (key, getattr(self.v, key)) for key in self.qualifiers))))
        quals = '.'.join([
            f'{key}{current.get(key, -1) + incs.get(key, 0)}'
            for key in self.qualifiers if key in set(current) | set(incs)])
        self.put(f'{self.v.base_version}.{quals}')


class ToPyPI(commands.ErrorsCommand):
    arguments = (
        (('inc',), dict(nargs='*', type=int, help='Version number increments (0s left)')),
        (('--test-pypi',), dict(action='store_true', help='Use test.pypi.org')), *(
            ((f'--{qal}',), dict(type=int, help='Qualifier increment'))
            for qal in VersionFile.qualifiers))
    exceptions = (FileNotFoundError, subprocess.CalledProcessError)

    @staticmethod
    def check_output(*cmd):
        sys.stdout.write(subprocess.check_output(cmd).decode())

    @staticmethod
    def upload_cmd(config, test_pypi):
        return ['twine', 'upload', '-u', config['user'], '-p',
                config['test_password'] if test_pypi else config['password']
                ] + (['--repository-url', 'https://test.pypi.org/legacy/']
                     if test_pypi else []) + ['dist/*']

    def try_call(self, **kwargs):
        version_file, inc = VersionFile(), kwargs.pop('inc')
        test_pypi = kwargs.pop('test_pypi')

        if inc:
            version_file.up(*inc)

        if kwargs:
            version_file.qualify(**kwargs)

        if os.path.isdir('dist'):
            shutil.rmtree('dist')

        self.check_output('python', 'setup.py', 'sdist', 'bdist_wheel')
        secrets = configparser.ConfigParser()
        secrets.read('.secrets.ini')

        if test_pypi:
            self.check_output(*self.upload_cmd(secrets['pypi'], test_pypi))
        else:
            go, choices = '', {'Yes': True, 'No': False}

            while not (go in choices):
                go = input(f'Upload {version_file} to PyPI ({"/".join(choices)})? ')

            if choices[go]:
                self.check_output(*self.upload_cmd(secrets['pypi'], test_pypi))
            else:
                sys.stdout.write('Aborted\n')


release_pypi = ToPyPI()
