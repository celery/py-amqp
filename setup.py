#!/usr/bin/env python
"""
Python Distutils setup for for amqp.  Build and install with

    python setup.py install

2007-11-10 Barry Pederson <bp@barryp.org>

"""

import sys
from distutils.core import setup

setup(name = "amqplib",
      description = "AMQP Client Library",
      version = "0.4.1",
      license = "LGPL",
      author = "Barry Pederson",
      author_email = "bp@barryp.org",
      url = "http://barryp.org/software/py-amqplib/",
      packages = ['amqplib']
     )
