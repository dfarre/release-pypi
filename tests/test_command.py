import configparser
import os
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
    git_push_calls = [mock.call(tup) for tup in [
        ('git', 'add', 'version.ini'),
        ('git', 'commit', '-m', 'Release'),
        ('git', 'tag', '1.1.dev0'),
        ('git', 'push', '--tags', 'origin', 'HEAD')]]

    def setUp(self):
        self.version_ini = configparser.ConfigParser()
        self.version_ini.read(self.version_path)

        self.secrets_ini = configparser.ConfigParser()
        self.secrets_ini['pypi'] = self.pypi_secrets

        with open(self.secrets_path, 'w') as wfile:
            self.secrets_ini.write(wfile)

    def tearDown(self):
        with open(self.version_path, 'w') as wfile:
            self.version_ini.write(wfile)

        os.remove(self.secrets_path)

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
    @mock.patch('subprocess.check_output', return_value=b'foo')
    def test_check_output(self, check_output_mock, stdout_mock):
        topypi.check_output('fake', 'cl')

        check_output_mock.assert_called_once_with(('fake', 'cl'))
        stdout_mock.assert_called_once_with('foo')

    @mock.patch('release_pypi.topypi.upload_cmd', return_value=['twine', 'fake'])
    @mock.patch('subprocess.check_output', return_value=b'Foo')
    def test_test_pypi(self, check_output_mock, upload_cmd_mock):
        assert topypi.release_pypi.call(1, 1, pre=1, dev=1, test_pypi=True) == 0
        assert list(map(str, upload_cmd_mock.call_args_list)) == [
            'call(<Section: pypi>, True)']
        assert check_output_mock.call_args_list == [self.sdist_call, self.twine_call]

    @mock.patch('builtins.input', return_value='Yes')
    @mock.patch('release_pypi.topypi.upload_cmd', return_value=['twine', 'fake'])
    @mock.patch('subprocess.check_output', return_value=b'M version.ini')
    def test_yes(self, check_output_mock, upload_cmd_mock, input_mock):
        assert topypi.release_pypi.call(1, dev=1, test_pypi=False) == 0
        input_mock.assert_called_once_with(
            'Upload release-pypi-1.1.dev0 to PyPI, and git-push tag and version.ini'
            ' to origin HEAD (Yes/No)? ')
        assert list(map(str, upload_cmd_mock.call_args_list)) == [
            'call(<Section: pypi>, False)']
        assert check_output_mock.call_args_list == [
            self.sdist_call, self.git_status_call, self.twine_call] + self.git_push_calls

    @mock.patch('subprocess.check_output', return_value=b'M version.ini')
    @mock.patch('builtins.input', return_value='No')
    @mock.patch('sys.stdout.write')
    def test_aborted(self, stdout_mock, input_mock, check_output_mock):
        assert topypi.release_pypi.call(test_pypi=False) == 0
        input_mock.assert_called_once_with(
            'Upload release-pypi-1.0rc1 to PyPI, and git-push tag and version.ini'
            ' to origin HEAD (Yes/No)? ')
        assert len(stdout_mock.call_args_list) == 2
        assert stdout_mock.call_args == mock.call('Aborted\n')
        assert check_output_mock.call_args_list == [self.sdist_call, self.git_status_call]
