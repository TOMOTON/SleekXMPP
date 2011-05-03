#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2008 Nathanael C. Fritz
# All Rights Reserved
#
# This software is licensed as described in the README file,
# which you should have received as part of this distribution.
#

# from ez_setup import use_setuptools
from distutils.core import setup
import sys

# the 'import sleekxmpp' command is pulling in too many modules
# making it fail in the OpenWRT cross-compilation environment
#
# HACK: we are avoiding the issue by making python believe it already
# imported the modules
#
# this works as the only thing used from the import is __version__
sys.modules["threading"] = {}
sys.modules["ssl"] = {}

import sleekxmpp

# if 'cygwin' in sys.platform.lower():
#     min_version = '0.6c6'
# else:
#     min_version = '0.6a9'
#
# try:
#     use_setuptools(min_version=min_version)
# except TypeError:
#     # locally installed ez_setup won't have min_version
#     use_setuptools()
#
# from setuptools import setup, find_packages, Extension, Feature

VERSION          = sleekxmpp.__version__
DESCRIPTION      = 'SleekXMPP is an elegant Python library for XMPP (aka Jabber, Google Talk, etc).'
LONG_DESCRIPTION = """
SleekXMPP is an elegant Python library for XMPP (aka Jabber, Google Talk, etc).
"""

CLASSIFIERS      = [ 'Intended Audience :: Developers',
                     'License :: OSI Approved :: MIT',
                     'Programming Language :: Python',
                     'Topic :: Software Development :: Libraries :: Python Modules',
                   ]

packages     = [ 'sleekxmpp',
                 'sleekxmpp/stanza',
                 'sleekxmpp/test',
                 'sleekxmpp/xmlstream',
                 'sleekxmpp/xmlstream/matcher',
                 'sleekxmpp/xmlstream/handler',
                 'sleekxmpp/thirdparty',
                 'sleekxmpp/plugins',
                 'sleekxmpp/plugins/xep_0009',
                 'sleekxmpp/plugins/xep_0009/stanza',
                 'sleekxmpp/plugins/xep_0030',
                 'sleekxmpp/plugins/xep_0030/stanza',
                 'sleekxmpp/plugins/xep_0050',
                 'sleekxmpp/plugins/xep_0059',
                 'sleekxmpp/plugins/xep_0085',
                 'sleekxmpp/plugins/xep_0086',
                 'sleekxmpp/plugins/xep_0092',
                 'sleekxmpp/plugins/xep_0128',
                 'sleekxmpp/plugins/xep_0199',
                 ]

if sys.version_info < (3, 0):
    py_modules = ['sleekxmpp.xmlstream.tostring.tostring26']
else:
    py_modules = ['sleekxmpp.xmlstream.tostring.tostring']

setup(
    name             = "sleekxmpp",
    version          = VERSION,
    description      = DESCRIPTION,
    long_description = LONG_DESCRIPTION,
    author       = 'Nathanael Fritz',
    author_email = 'fritzy [at] netflint.net',
    url          = 'http://code.google.com/p/sleekxmpp',
    license      = 'MIT',
    platforms    = [ 'any' ],
    packages     = packages,
    py_modules   = py_modules,
    requires     = [ 'tlslite', 'pythondns' ],
    )

