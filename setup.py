import os
import fnmatch
from setuptools import find_packages, setup

with open(os.path.join(os.path.dirname(__file__), 'README.md')) as readme:
    long_description = readme.read()

with open(os.path.join(os.path.dirname(__file__), 'requirements.txt')) as f:
    requirements = f.read().splitlines()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))


def package_version():
    from basiclive.version import get_version
    return get_version()


def package_files(directory, exclude=()):
    if os.path.exists(directory):
        return [
            os.path.join(path, filename)
            for (path, directories, filenames) in os.walk(directory)
            for filename in filenames
            if not any(fnmatch.fnmatch(filename, pattern) for pattern in exclude)
        ]
    return []


setup(
    name='basiclive',
    version=package_version(),
    packages=find_packages(),
    url='https://github.com/katyjg/basic-live',
    license='MIT',
    author='Kathryn Janzen, Michel Fodje',
    author_email='kathryn.janzen@lightsource.ca, michel.fodje@lightsource.ca',
    description='A Framework for creating beamline LIMS',
    long_description=long_description,
    long_description_content_type="text/markdown",
    install_requires=requirements,
    include_package_data=True,
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.7',
    ],
)
