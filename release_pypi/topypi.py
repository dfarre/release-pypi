import configparser
import os
from packaging import version
import shutil
import subprocess
import sys

from simple_cmd import decorators

from release_pypi.exceptions import SecretsNotFound, WrongGitStatus

SECRETS_PATH = '.secrets.ini'


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

    @property
    def git_push_tag_cmds(self):
        return [['git', 'add', self.path],
                ['git', 'commit', '-m', f'Bump version {self.v}'],
                ['git', 'tag', self.ini['version']['value']],
                ['git', 'push', '--tags', 'origin', 'HEAD']]

    def check_git_status(self):
        git_status = subprocess.check_output(('git', 'status', '--porcelain')).decode().strip()

        if git_status != f'M {self.path}':
            raise WrongGitStatus('Clean the git status to push a commit '
                                 f'with the new {self.path} only')

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


def check_output(*cmd):
    completed_process = subprocess.run(cmd, stdout=sys.stdout, stderr=sys.stderr)

    if completed_process.returncode:
        raise subprocess.CalledProcessError(completed_process.returncode, ' '.join(cmd))


def upload_cmd(config, test_pypi):
    return ['twine', 'upload', '-u', config['user'], '-p',
            config['test_password'] if test_pypi else config['password']
            ] + (['--repository-url', 'https://test.pypi.org/legacy/']
                 if test_pypi else []) + ['dist/*']


def check_secrets_present(secrets_ini, test_pypi):
    if not secrets_ini.has_option('pypi', 'user'):
        raise SecretsNotFound(
            f"{SECRETS_PATH} with 'pypi' section containing 'user' not found")

    if test_pypi and not secrets_ini.has_option('pypi', 'test_password'):
        raise SecretsNotFound(
            f"'test_password' not found in {SECRETS_PATH} 'pypi' section")

    if not test_pypi and not secrets_ini.has_option('pypi', 'password'):
        raise SecretsNotFound(
            f"'password' not found in {SECRETS_PATH} 'pypi' section")


@decorators.ErrorsCommand(FileNotFoundError, subprocess.CalledProcessError, WrongGitStatus,
                          SecretsNotFound, help={'inc': 'Version number increments (0s left)'})
def release_pypi(*inc: int, test_pypi: 'Just push to test.pypi.org' = False,
                 pre: 'Release Candidate qualifier increment' = 0,
                 post: 'Post-release qualifier increment' = 0,
                 dev: 'Development release qualifier increment' = 0):
    version_file = VersionFile()

    if inc:
        version_file.up(*inc)

    qualifier_incs = {k: v for k, v in [('pre', pre), ('post', post), ('dev', dev)] if v}

    if qualifier_incs:
        version_file.qualify(**qualifier_incs)

    if os.path.isdir('dist'):
        shutil.rmtree('dist')

    check_output('python', '-m', 'build')

    secrets = configparser.ConfigParser()
    secrets.read(SECRETS_PATH)
    check_secrets_present(secrets, test_pypi)

    if test_pypi:
        check_output(*upload_cmd(secrets['pypi'], test_pypi))
        return 0

    version_file.check_git_status()

    go, choices = '', {'Yes': True, 'No': False}

    while not (go in choices):
        go = input(f'Upload {version_file} to PyPI, and git-push tag and '
                   f'{version_file.path} to origin HEAD ({"/".join(choices)})? ')

    if choices[go] is False:
        sys.stdout.write('Aborted\n')
        return 0

    check_output(*upload_cmd(secrets['pypi'], test_pypi))

    for cmd in version_file.git_push_tag_cmds:
        check_output(*cmd)

    return 0
