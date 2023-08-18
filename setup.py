import configparser
import setuptools


ini = configparser.ConfigParser()
ini.read('version.ini')

with open('README.md') as readme:
    long_description = readme.read()

tests_require = ['pytest-cov']

setuptools.setup(
    name=ini['version']['name'],
    version=ini['version']['value'],
    author='Daniel Farré Manzorro',
    author_email='d.farre.m@gmail.com',
    description='Simple PyPI uploader using twine',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://bitbucket.org/coleopter/release-pypi',
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Intended Audience :: Developers'],
    packages=setuptools.find_packages(),
    install_requires=['build', 'twine', 'packaging', 'simple-cmd', 'urllib3<2.0'],
    setup_requires=['setuptools', 'configparser'],
    tests_require=tests_require,
    extras_require={'dev': ['ipdb', 'ipython'], 'test': tests_require},
    entry_points={'console_scripts': [
        'release-pypi=release_pypi.topypi:release_pypi']},
)
