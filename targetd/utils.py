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

from subprocess import Popen, PIPE
from contextlib import contextmanager
import re


@contextmanager
def ignored(*exceptions):
    try:
        yield
    except exceptions:
        pass


_NAME_REGEX = '^[a-zA-Z0-9_-]+$'


def name_check(name):
    if not re.match(_NAME_REGEX, name):
        raise TargetdError(
            TargetdError.INVALID_ARGUMENT,
            "Illegal name, should match: %s" % _NAME_REGEX)


class TargetdError(Exception):
    INVALID_ARGUMENT = -32602
    NO_SUPPORT = -153
    NAME_CONFLICT = -50
    EXISTS_INITIATOR = -52
    NO_FREE_HOST_LUN_ID = -1000
    NOT_FOUND_ACCESS_GROUP = -200
    VOLUME_MASKED = -303

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
            raise TargetdError(-303, 'Unexpected exit code "%s" %s, out= %s' %
                                     (cmd_str, str(c.returncode),
                                      str(out[0] + out[1])))

    return c.returncode, out[0].decode('utf-8'), out[1].decode('utf-8')
