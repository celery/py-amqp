#!/usr/bin/env python
"""
Python Distutils setup for for amqp.  Build and install with

    python setup.py install

2007-11-10 Barry Pederson <bp@barryp.org>

"""

import sys

try:
    from setuptools import setup
except:
    from distutils.core import setup


try:
    from distutils.command.build_py import build_py_2to3 as build_py
except ImportError:
    # 2.x
    from distutils.command.build_py import build_py

setup(name = "amqplib",
      description = "AMQP Client Library",
      version = "0.6.2-devel",
      classifiers=[
          'Programming Language :: Python',
          'Programming Language :: Python :: 3',
          ],
      license = "LGPL",
      author = "Barry Pederson",
      author_email = "bp@barryp.org",
      url = "http://code.google.com/p/py-amqplib/",
      packages = ['amqplib', 'amqplib.client_0_8'],
      cmdclass = {'build_py':build_py},
     )
