import configparser
import os
import shutil
import subprocess
import sys
import tomllib

from packaging.version import Version

from simple_cmd import decorators

from release_pypi.exceptions import SecretsNotFound, WrongGitStatus

SECRETS_PATH = '.secrets.ini'
DEFAULT_VERSION_FILE = 'pyproject.toml'


class VersionFile:
    qualifiers = ('pre', 'post', 'dev')

    def __init__(self, path=DEFAULT_VERSION_FILE):
        with open(path, 'rb') as pyproject_file:
            self.toml = tomllib.load(pyproject_file)

        self.path = path

    def __str__(self):
        return f'{self.name}=={self.version}'

    @property
    def version(self):
        return Version(self.toml['project']['version'])

    @property
    def name(self):
        return self.toml['project']['name']

    @property
    def git_push_tag_cmds(self):
        return [['git', 'add', self.path],
                ['git', 'commit', '-m', f'Bump version to {self.version}'],
                ['git', 'tag', str(self.version)],
                ['git', 'push', '--tags', 'origin', 'HEAD']]

    def check_git_status(self):
        git_status = subprocess.check_output(('git', 'status', '--porcelain')).decode().strip()

        if git_status != f'M {self.path}':
            raise WrongGitStatus(
                f'Clean the git status to push a commit with the new {self.path} only.')


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


@decorators.ErrorsCommand(
    FileNotFoundError, subprocess.CalledProcessError, SecretsNotFound, WrongGitStatus)
def release_pypi(test_pypi: 'Just push to test.pypi.org' = False,
                 version_toml: str = DEFAULT_VERSION_FILE):
    version_file = VersionFile(version_toml)

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
        go = input(f'Upload {version_file} to PyPI, and git-push the version tag and '
                   f'the {version_file.path} file to origin HEAD ({"/".join(choices)})? ')

    if choices[go] is False:
        sys.stdout.write('Aborted\n')
        return 0

    check_output(*upload_cmd(secrets['pypi'], test_pypi))

    for cmd in version_file.git_push_tag_cmds:
        check_output(*cmd)

    return 0
