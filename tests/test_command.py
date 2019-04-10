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
    path = 'version.ini'
    command = topypi.ToPyPI(test_mode=True)
    pypi = {'pypi': {'user': 'Alice', 'test_password': 'T', 'password': 'P'}}
    sdist_call = mock.call('python', 'setup.py', 'sdist', 'bdist_wheel')

    def setUp(self):
        self.ini = configparser.ConfigParser()
        self.ini.read(self.path)

    def tearDown(self):
        with open(self.path, 'w') as wfile:
            self.ini.write(wfile)

    @staticmethod
    def assert_upload_cmd(cmd, test):
        assert len(cmd) == 9 if test else 7
        assert cmd[:6] == ['twine', 'upload', '-u', 'Alice', '-p', 'T' if test else 'P']
        assert cmd[-1] == 'dist/*'

        if test:
            assert cmd[6:8] == ['--repository-url', 'https://test.pypi.org/legacy/']

    def test_upload_cmd(self):
        self.assert_upload_cmd(self.command.upload_cmd(self.pypi['pypi'], False), False)

    def test_upload_cmd__test(self):
        self.assert_upload_cmd(self.command.upload_cmd(self.pypi['pypi'], True), True)

    @mock.patch('sys.stdout.write')
    @mock.patch('subprocess.check_output', return_value=b'foo')
    def test_check_output(self, check_output_mock, stdout_mock):
        self.command.check_output('fake', 'cl')

        check_output_mock.assert_called_once_with(('fake', 'cl'))
        stdout_mock.assert_called_once_with('foo')

    @mock.patch('release_pypi.topypi.ToPyPI.upload_cmd', return_value=['fake', 'line'])
    @mock.patch('release_pypi.topypi.ToPyPI.check_output')
    def test_test_pypi(self, check_output_mock, upload_cmd_mock):
        assert self.command(inc=[1, 1], pre=1, dev=1, test_pypi=True) == 0
        assert list(map(str, upload_cmd_mock.call_args_list)) == [
            'call(<Section: pypi>, True)']
        assert check_output_mock.call_args_list == [self.sdist_call, mock.call('fake', 'line')]

    @mock.patch('builtins.input', return_value='Yes')
    @mock.patch('release_pypi.topypi.ToPyPI.upload_cmd', return_value=['fake', 'cl'])
    @mock.patch('release_pypi.topypi.ToPyPI.check_output')
    def test_yes(self, check_output_mock, upload_cmd_mock, input_mock):
        assert self.command(inc=[1], dev=1, test_pypi=False) == 0
        input_mock.assert_called_once_with(
            'Upload release-pypi-1.1.dev0 to PyPI (Yes/No)? ')
        assert list(map(str, upload_cmd_mock.call_args_list)) == [
            'call(<Section: pypi>, False)']
        assert check_output_mock.call_args_list == [self.sdist_call, mock.call('fake', 'cl')]

    @mock.patch('builtins.input', return_value='No')
    @mock.patch('sys.stdout.write')
    def test_aborted(self, stdout_mock, input_mock):
        assert self.command(inc=[], test_pypi=False) == 0
        input_mock.assert_called_once_with('Upload release-pypi-1.0rc0 to PyPI (Yes/No)? ')
        assert len(stdout_mock.call_args_list) == 2
        assert stdout_mock.call_args == mock.call('Aborted\n')
