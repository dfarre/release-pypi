import configparser
import os
import subprocess
import unittest
import unittest.mock as mock

from release_pypi import topypi


class VersionFileTests(unittest.TestCase):
    path = 'fake_version.ini'

    @classmethod
    def tearDownClass(cls):
        os.remove(cls.path)

    def new(self, text):
        with open(self.path, 'w') as wfile:
            wfile.write(f'[version]\nname=foo\nvalue={text}')

        return topypi.VersionFile(self.path)

    def test_up_minor_shift(self):
        vfile = self.new('0.1.2.pre1.dev4')
        vfile.up(3)

        assert str(vfile.v) == '0.1.5'

    def test_up_major_shift(self):
        vfile = self.new('0.1.2')
        vfile.up(1, 2, 3)

        assert str(vfile.v) == '1.3.5'

    def test_up_enlarge(self):
        vfile = self.new('0.1.2.post0')
        vfile.up(0, 0, 1, 1)

        assert str(vfile.v) == '0.1.3.1'

    def test_qualify__dev0(self):
        vfile = self.new('0.1.2.pre0')
        vfile.qualify(pre=2, dev=1)

        assert str(vfile.v) == '0.1.2rc2.dev0'

    def test_qualify__dev2(self):
        vfile = self.new('0.1.2.dev0')
        vfile.qualify(pre=2, dev=2)

        assert repr(vfile) == '<VersionFile: foo-0.1.2rc1.dev2>'


class ToPyPiTests(unittest.TestCase):
    version_path = 'version.ini'
    secrets_path = '.secrets.ini'
    pypi_secrets = {'user': 'Alice', 'test_password': 'T', 'password': 'P'}
    sdist_call = mock.call('python', '-m', 'build')
    twine_call = mock.call('twine', 'fake')
    git_status_call = mock.call(('git', 'status', '--porcelain'))

    def setUp(self):
        self.version_ini = configparser.ConfigParser()
        self.version_ini.read(self.version_path)

        self.secrets_ini = configparser.ConfigParser()
        self.write_secrets(self.pypi_secrets)

        os.makedirs('dist', exist_ok=True)

    def tearDown(self):
        with open(self.version_path, 'w') as wfile:
            self.version_ini.write(wfile)

        os.remove(self.secrets_path)

    def write_secrets(self, secrets):
        self.secrets_ini['pypi'] = secrets

        with open(self.secrets_path, 'w') as wfile:
            self.secrets_ini.write(wfile)

    @staticmethod
    def git_push_calls(version):
        return [mock.call(*tup) for tup in [
            ('git', 'add', 'version.ini'),
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
        assert topypi.release_pypi.call(1, 1, pre=1, dev=1, test_pypi=True) == 0
        assert list(map(str, upload_cmd_mock.call_args_list)) == [
            'call(<Section: pypi>, True)']
        assert check_output_mock.call_args_list == [self.sdist_call, self.twine_call]

    @mock.patch('builtins.input', return_value='Yes')
    @mock.patch('release_pypi.topypi.upload_cmd', return_value=['twine', 'fake'])
    @mock.patch('subprocess.check_output', return_value=b'M version.ini')
    @mock.patch('release_pypi.topypi.check_output', return_value=b'Foo')
    def test_yes(self, custom_check_output_mock, check_output_mock, upload_cmd_mock,
                 input_mock):
        assert topypi.release_pypi.call(1, dev=1, test_pypi=False) == 0
        version_file = topypi.VersionFile()
        input_mock.assert_called_once_with(
            f'Upload {version_file} to PyPI, and git-push tag and version.ini'
            ' to origin HEAD (Yes/No)? ')
        assert list(map(str, upload_cmd_mock.call_args_list)) == [
            'call(<Section: pypi>, False)']
        assert check_output_mock.call_args_list == [self.git_status_call]
        assert custom_check_output_mock.call_args_list == [
            self.sdist_call, self.twine_call] + self.git_push_calls(version_file.v)

    @mock.patch('subprocess.check_output', return_value=b'M version.ini')
    @mock.patch('builtins.input', return_value='No')
    @mock.patch('sys.stdout.write')
    def test_aborted(self, stdout_mock, input_mock, check_output_mock):
        assert topypi.release_pypi.call(test_pypi=False) == 0
        version_file = topypi.VersionFile()
        input_mock.assert_called_once_with(
            f'Upload {version_file} to PyPI, and git-push tag and version.ini'
            ' to origin HEAD (Yes/No)? ')
        assert len(stdout_mock.call_args_list) == 1
        assert stdout_mock.call_args == mock.call('Aborted\n')
        assert check_output_mock.call_args_list == [self.git_status_call]

    @mock.patch('subprocess.check_output', return_value=b'M fake_file.py')
    @mock.patch('builtins.input')
    @mock.patch('sys.stdout.write')
    def test_wrong_git_status(self, stdout_mock, input_mock, check_output_mock):
        assert topypi.release_pypi.call(test_pypi=False) == 6
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
        assert topypi.release_pypi.call(test_pypi=test_pypi) == 5
        input_mock.assert_not_called()
