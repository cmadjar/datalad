# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test classes SSHConnection and SSHManager

"""

import os
from os.path import exists, join as opj

from nose.tools import ok_, assert_is_instance

from datalad.support.sshconnector import SSHConnection, SSHManager
from datalad.tests.utils import assert_raises
from datalad.tests.utils import skip_ssh


@skip_ssh
def test_ssh_get_connection():

    manager = SSHManager()
    c1 = manager.get_connection('ssh://localhost')
    assert_is_instance(c1, SSHConnection)

    # subsequent call returns the very same instance:
    ok_(manager.get_connection('ssh://localhost') is c1)

    # fail on malformed URls (meaning: urlparse can't correctly deal with them):
    assert_raises(ValueError, manager.get_connection, 'localhost')
    assert_raises(ValueError, manager.get_connection, 'someone@localhost')
    assert_raises(ValueError, manager.get_connection, 'ssh:/localhost')


@skip_ssh
def test_ssh_open_close():

    manager = SSHManager()
    c1 = manager.get_connection('ssh://localhost')
    path = opj(manager.socket_dir, 'localhost')
    c1.open()
    # control master exists:
    ok_(exists(path))

    # TODO: how to test, we can actually use it? => SSHConnection callable.
    # But what command call would be possible to prove the point?

    c1.close()
    # control master doesn't exist anymore:
    ok_(not exists(path))


