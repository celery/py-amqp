#!/usr/bin/env python

import re
import sys
from os import environ
from pathlib import Path

import setuptools
import setuptools.command.test

NAME = 'amqp'

# -*- Classifiers -*-

classes = """
    Development Status :: 5 - Production/Stable
    Programming Language :: Python
    Programming Language :: Python :: 3 :: Only
    Programming Language :: Python :: 3
    Programming Language :: Python :: 3.6
    Programming Language :: Python :: 3.7
    Programming Language :: Python :: 3.8
    Programming Language :: Python :: Implementation :: CPython
    Programming Language :: Python :: Implementation :: PyPy
    License :: OSI Approved :: BSD License
    Intended Audience :: Developers
    Operating System :: OS Independent
"""
classifiers = [s.strip() for s in classes.split('\n') if s]

# -*- Distribution Meta -*-

re_meta = re.compile(r'__(\w+?)__\s*=\s*(.*)')
re_doc = re.compile(r'^"""(.+?)"""')


def add_default(m):
    attr_name, attr_value = m.groups()
    return (attr_name, attr_value.strip("\"'")),


def add_doc(m):
    return ('doc', m.groups()[0]),


pats = {re_meta: add_default,
        re_doc: add_doc}
here = Path(__file__).parent
meta = {}
for line in (here / 'amqp/__init__.py').read_text().splitlines():
    if line.strip() == '# -eof meta-':
        break
    for pattern, handler in pats.items():
        m = pattern.match(line.strip())
        if m:
            meta.update(handler(m))

# -*- Installation Requires -*-

py_version = sys.version_info
is_jython = sys.platform.startswith('java')
is_pypy = hasattr(sys, 'pypy_version_info')


def strip_comments(l):
    return l.split('#', 1)[0].strip()


def reqs(f):
    lines = (here / 'requirements' / f).read_text().splitlines()
    reqs = [strip_comments(l) for l in lines]
    return list(filter(None, reqs))


# -*- %%% -*-


class pytest(setuptools.command.test.test):
    user_options = [('pytest-args=', 'a', 'Arguments to pass to py.test')]

    def initialize_options(self):
        setuptools.command.test.test.initialize_options(self)
        self.pytest_args = ''

    def run_tests(self):
        import pytest
        pytest_args = self.pytest_args.split(' ')
        sys.exit(pytest.main(pytest_args))


if environ.get("CELERY_ENABLE_SPEEDUPS"):
    setup_requires = ['Cython']
    ext_modules = [
        setuptools.Extension(
            'amqp.serialization',
            ["amqp/serialization.py"],
        ),
        setuptools.Extension(
            'amqp.basic_message',
            ["amqp/basic_message.py"],
        ),
        setuptools.Extension(
            'amqp.method_framing',
            ["amqp/method_framing.py"],
        ),
        setuptools.Extension(
            'amqp.abstract_channel',
            ["amqp/abstract_channel.py"],
        ),
        setuptools.Extension(
            'amqp.utils',
            ["amqp/utils.py"],
        ),
    ]
else:
    setup_requires = []
    ext_modules = []

setuptools.setup(
    name=NAME,
    packages=setuptools.find_packages(exclude=['ez_setup', 't', 't.*']),
    version=meta['version'],
    description=meta['doc'],
    long_description=(here / 'README.rst').read_text(),
    keywords='amqp rabbitmq cloudamqp messaging',
    author=meta['author'],
    author_email=meta['contact'],
    maintainer=meta['maintainer'],
    url=meta['homepage'],
    platforms=['any'],
    license='BSD',
    classifiers=classifiers,
    python_requires=">=3.6",
    install_requires=reqs('default.txt'),
    setup_requires=setup_requires,
    tests_require=reqs('test.txt'),
    cmdclass={'test': pytest},
    zip_safe=False,
    ext_modules=ext_modules,
)
