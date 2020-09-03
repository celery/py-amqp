#!/usr/bin/env python

import codecs
import os
import re
import sys

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
here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'amqp/__init__.py')) as meta_fh:
    meta = {}
    for line in meta_fh:
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
    with open(os.path.join(os.getcwd(), 'requirements', f)) as fp:
        req = filter(None, [strip_comments(l) for l in fp.readlines()])
    # filter returns filter object(iterator) in Python 3,
    # but a list in Python 2.7, so make sure it returns a list.
    return list(req)


# -*- Long Description -*-

def long_description():
    try:
        return codecs.open('README.rst', 'r', 'utf-8').read()
    except OSError:
        return 'Long description error: Missing README.rst file'


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


if os.environ.get("CELERY_ENABLE_SPEEDUPS"):
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
