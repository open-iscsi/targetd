# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Copyright 2013, Andy Grover <agrover@redhat.com>
#
# Utility functions.

import re
from contextlib import contextmanager
from subprocess import Popen, PIPE
from threading import Lock


@contextmanager
def ignored(*exceptions):
    try:
        yield
    except exceptions:
        pass


_NAME_REGEX = '^[a-zA-Z0-9_-]+$'


def name_check(name):
    if not re.match(_NAME_REGEX, name):
        raise TargetdError(TargetdError.INVALID_ARGUMENT,
                           "Illegal name, should match: %s" % _NAME_REGEX)


class TargetdError(Exception):
    # Common
    INVALID = -1
    NAME_CONFLICT = -50
    NO_SUPPORT = -153
    UNEXPECTED_EXIT_CODE = -303
    INVALID_ARGUMENT = -32602

    # Specific to block
    EXISTS_INITIATOR = -52
    NOT_FOUND_VOLUME = -103
    NOT_FOUND_VOLUME_GROUP = -152
    NOT_FOUND_ACCESS_GROUP = -200
    VOLUME_MASKED = -303
    NO_FREE_HOST_LUN_ID = -1000

    # Specific to FS/NFS
    EXISTS_CLONE_NAME = -51
    EXISTS_FS_NAME = -53
    NOT_FOUND_FS = -104
    INVALID_POOL = -110
    NOT_FOUND_SS = -112
    NOT_FOUND_VOLUME_EXPORT = -151
    NOT_FOUND_NFS_EXPORT = -400
    NFS_NO_SUPPORT = -401

    def __init__(self, error_code, *args, **kwargs):
        Exception.__init__(self, *args, **kwargs)
        self.error = error_code


def invoke(cmd, raise_exception=True):
    """
    Exec a command returning a tuple (exit code, stdout, stderr) and optionally
    throwing an exception on non-zero exit code.
    """
    c = Popen(cmd, stdout=PIPE, stderr=PIPE)
    out = c.communicate()

    if raise_exception:
        if c.returncode != 0:
            cmd_str = str(cmd)
            raise TargetdError(TargetdError.UNEXPECTED_EXIT_CODE,
                               'Unexpected exit code "%s" %s, out= %s' %
                               (cmd_str, str(c.returncode),
                                str(out[0] + out[1])))

    return c.returncode, out[0].decode('utf-8'), out[1].decode('utf-8')


class Pit(object):

    def __init__(self, tar, client_id):
        self.tar = tar
        self.client_id = client_id

    def __enter__(self):
        self.tar.lock.acquire()
        try:
            self.tar.client[self.client_id] = True
        finally:
            self.tar.lock.release()

    def __exit__(self, e_type, e_value, e_traceback):
        self.tar.lock.acquire()
        try:
            del self.tar.client[self.client_id]
        finally:
            self.tar.lock.release()


class Tar(object):

    def __init__(self):
        self.lock = Lock()
        self.client = dict()

    def is_stuck(self, client_id):
        self.lock.acquire()
        try:
            if client_id in self.client:
                return True
        finally:
            self.lock.release()
        return False

    def pitted(self, client_id):
        return Pit(self, client_id)