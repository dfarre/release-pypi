import configparser
import os
import subprocess
import unittest
import unittest.mock as mock

from release_pypi import topypi


class ToPyPiTests(unittest.TestCase):
    version_path = 'test_pyproject.toml'
    secrets_path = '.secrets.ini'
    pypi_secrets = {'user': 'Alice', 'test_password': 'T', 'password': 'P'}
    sdist_call = mock.call('python', '-m', 'build')
    twine_call = mock.call('twine', 'fake')
    git_status_call = mock.call(('git', 'status', '--porcelain'))

    def setUp(self):
        with open(self.version_path, 'w') as wfile:
            wfile.write('[project]\nname = "foo"\nversion = "0.3rc0"')

        self.version_ini = configparser.ConfigParser()
        self.version_ini.read(self.version_path)

        self.secrets_ini = configparser.ConfigParser()
        self.write_secrets(self.pypi_secrets)

        os.makedirs('dist', exist_ok=True)

    def tearDown(self):
        os.remove(self.version_path)
        os.remove(self.secrets_path)

    def write_secrets(self, secrets):
        self.secrets_ini['pypi'] = secrets

        with open(self.secrets_path, 'w') as wfile:
            self.secrets_ini.write(wfile)

    def git_push_calls(self, version):
        return [mock.call(*tup) for tup in [
            ('git', 'add', self.version_path),
            ('git', 'commit', '-m', f'Bump version to {version}'),
            ('git', 'tag', str(version)),
            ('git', 'push', '--tags', 'origin', 'HEAD')]]

    @staticmethod
    def assert_upload_cmd(cmd, test):
        assert len(cmd) == 9 if test else 7
        assert cmd[:6] == ['twine', 'upload', '-u', 'Alice', '-p', 'T' if test else 'P']
        assert cmd[-1] == 'dist/*'

        if test:
            assert cmd[6:8] == ['--repository-url', 'https://test.pypi.org/legacy/']

    def test_upload_cmd(self):
        self.assert_upload_cmd(topypi.upload_cmd(self.pypi_secrets, False), False)

    def test_upload_cmd__test(self):
        self.assert_upload_cmd(topypi.upload_cmd(self.pypi_secrets, True), True)

    @mock.patch('sys.stdout.write')
    def test_check_output(self, stdout_mock):
        self.assertRaises(subprocess.CalledProcessError, topypi.check_output, 'ls', '--fake=3')

    @mock.patch('release_pypi.topypi.upload_cmd', return_value=['twine', 'fake'])
    @mock.patch('release_pypi.topypi.check_output', return_value=b'Foo')
    def test_test_pypi(self, check_output_mock, upload_cmd_mock):
        assert topypi.release_pypi.call(version_toml=self.version_path, test_pypi=True) == 0
        assert list(map(str, upload_cmd_mock.call_args_list)) == [
            'call(<Section: pypi>, True)']
        assert check_output_mock.call_args_list == [self.sdist_call, self.twine_call]

    @mock.patch('builtins.input', return_value='Yes')
    @mock.patch('release_pypi.topypi.upload_cmd', return_value=['twine', 'fake'])
    @mock.patch('subprocess.check_output', return_value=b'M test_pyproject.toml')
    @mock.patch('release_pypi.topypi.check_output', return_value=b'Foo')
    def test_yes(self, custom_check_output_mock, check_output_mock, upload_cmd_mock,
                 input_mock):
        assert topypi.release_pypi.call(version_toml=self.version_path, test_pypi=False) == 0
        input_mock.assert_called_once_with(
            'Upload foo==0.3rc0 to PyPI, and git-push the version tag and the '
            'test_pyproject.toml file to origin HEAD (Yes/No)? ')
        assert list(map(str, upload_cmd_mock.call_args_list)) == [
            'call(<Section: pypi>, False)']
        assert check_output_mock.call_args_list == [self.git_status_call]
        assert custom_check_output_mock.call_args_list == [
            self.sdist_call, self.twine_call] + self.git_push_calls('0.3rc0')

    @mock.patch('subprocess.check_output', return_value=b'M test_pyproject.toml')
    @mock.patch('builtins.input', return_value='No')
    @mock.patch('sys.stdout.write')
    def test_aborted(self, stdout_mock, input_mock, check_output_mock):
        assert topypi.release_pypi.call(version_toml=self.version_path, test_pypi=False) == 0
        input_mock.assert_called_once_with(
            'Upload foo==0.3rc0 to PyPI, and git-push the version tag and the '
            'test_pyproject.toml file to origin HEAD (Yes/No)? ')
        assert len(stdout_mock.call_args_list) == 1
        assert stdout_mock.call_args == mock.call('Aborted\n')
        assert check_output_mock.call_args_list == [self.git_status_call]

    @mock.patch('subprocess.check_output', return_value=b'M fake_file.py')
    @mock.patch('builtins.input')
    @mock.patch('sys.stdout.write')
    def test_wrong_git_status(self, stdout_mock, input_mock, check_output_mock):
        assert topypi.release_pypi.call(version_toml=self.version_path, test_pypi=False) == 6
        input_mock.assert_not_called()
        assert len(stdout_mock.call_args_list) == 0
        assert check_output_mock.call_args_list == [self.git_status_call]

    @mock.patch('subprocess.check_output', return_value=b'Fake output')
    @mock.patch('builtins.input')
    @mock.patch('sys.stdout.write')
    def test_secrets_not_found(self, stdout_mock, input_mock, check_output_mock):
        self.write_secrets({})
        self.assert_secrets_not_found(input_mock)

        self.write_secrets({'user': 'D', 'password': 'P'})
        self.assert_secrets_not_found(input_mock)

        self.write_secrets({'user': 'D', 'test_password': 'P'})
        self.assert_secrets_not_found(input_mock, test_pypi=False)

    def assert_secrets_not_found(self, input_mock, test_pypi=True):
        assert topypi.release_pypi.call(
            version_toml=self.version_path, test_pypi=test_pypi) == 5
        input_mock.assert_not_called()
