import sys

from sphinx_celery import conf

globals().update(conf.build_config(
    'amqp', __file__,
    project='py-amqp',
    description='Python Promises',
    version_dev='5.3',
    version_stable='5.3',
    canonical_url='https://amqp.readthedocs.io',
    webdomain='celeryproject.org',
    github_project='celery/py-amqp',
    author='Ask Solem & contributors',
    author_name='Ask Solem',
    copyright='2016',
    publisher='Celery Project',
    html_logo='images/celery_128.png',
    html_favicon='images/favicon.ico',
    html_prepend_sidebars=['sidebardonations.html'],
    extra_extensions=[],
    include_intersphinx={'python', 'sphinx'},
    apicheck_package='amqp',
    apicheck_ignore_modules=['amqp'],
))

# apicheck is only required for the apicheck builder.
if not any(arg == 'apicheck' for arg in sys.argv):
    extensions.remove('sphinx_celery.apicheck')

# GSSAPI may be backed by a local fallback class when gssapi is unavailable.
nitpick_ignore = [
    ('py:class', 'amqp.sasl._get_gssapi_mechanism.<locals>.FakeGSSAPI'),
]
