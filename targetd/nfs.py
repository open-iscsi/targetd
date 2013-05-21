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

from subprocess import Popen, PIPE
import re


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
            raise RuntimeError('Unexpected exit code "%s" %s, out= %s' %
                               (cmd_str, str(c.returncode),
                                str(out[0] + out[1])))

    return c.returncode, out[0], out[1]


def make_line_array(out):
    """
    Split the text out as an array of text strings
    """
    rc = []
    for line in out.split('\n'):
        if len(line) > 1:
            rc.append(line)
    return rc


class Export(object):

    SECURE = 0x00000001
    RW = 0x00000002
    RO = 0x00000004
    SYNC = 0x00000008
    ASYNC = 0x00000010
    NO_WDELAY = 0x00000020
    NOHIDE = 0x00000040
    CROSS_MNT = 0x00000080
    NO_SUBTREE_CHECK = 0x00000100
    INSECURE_LOCKS = 0x00000200
    ROOT_SQUASH = 0x00000400
    NO_ROOT_SQUASH = 0x00000800
    ALL_SQUASH = 0x00001000
    WDELAY = 0x00002000
    HIDE = 0x00004000
    INSECURE = 0x00008000

    bool_option = dict(secure=SECURE, rw=RW, ro=RO, sync=SYNC, async=ASYNC,
                       no_wdelay=NO_WDELAY, nohide=NOHIDE,
                       cross_mnt=CROSS_MNT, no_subtree_check=NO_SUBTREE_CHECK,
                       insecure_locks=INSECURE_LOCKS, root_squash=ROOT_SQUASH,
                       all_squash=ALL_SQUASH, wdelay=WDELAY, hide=HIDE,
                       insecure=INSECURE, no_root_squash=NO_ROOT_SQUASH)

    key_pair = dict(mountpoint=str, mp=str, fsid=None, refer=str, replicas=str,
                    anonuid=int, anongid=int)

    export_regex = '([\/a-zA-Z0-9\.-_]+)[\s]+(.+)\((.+)\)'

    @staticmethod
    def _bitCount(int_type):
        count = 0
        while int_type:
            int_type &= int_type - 1
            count += 1
        return count

    @staticmethod
    def _validate_options(options):

        if Export._bitCount(((Export.RW | Export.RO) & options)) == 2:
            raise ValueError("Both RO & RW set")

        if Export._bitCount(((Export.INSECURE | Export.SECURE) & options)) == 2:
            raise ValueError("Both INSECURE & SECURE set")

        if Export._bitCount(((Export.SYNC | Export.ASYNC) & options)) == 2:
            raise ValueError("Both SYNC & ASYNC set")

        if Export._bitCount(((Export.HIDE | Export.NOHIDE) & options)) == 2:
            raise ValueError("Both HIDE & NOHIDE set")

        if Export._bitCount(((Export.WDELAY | Export.NO_WDELAY) & options)) \
                == 2:
            raise ValueError("Both WDELAY & NO_WDELAY set")

        if Export._bitCount(((Export.ROOT_SQUASH | Export.NO_ROOT_SQUASH)
                            & options)) > 1:
            raise ValueError("Only one option of ROOT_SQUASH, NO_ROOT_SQUASH, "
                             "can be specified")

        return options

    @staticmethod
    def _validate_key_pairs(kp):
        if kp:
            if isinstance(kp, dict):
                for k, v in kp.items():
                    if k not in Export.key_pair:
                        raise ValueError('option %s not valid' % k)

                return kp
            else:
                raise ValueError('key_value_options domain is None or dict')
        else:
            return {}

    def __init__(self, host, path, bit_wise_options=0, key_value_options=None):

        if host == '<world>':
            self.host = '*'
        else:
            self.host = host
        self.path = path
        self.options = Export._validate_options(bit_wise_options)
        self.key_value_options = Export._validate_key_pairs(key_value_options)

    @staticmethod
    def parse_opt(options_string):
        bits = 0
        pairs = {}

        options = options_string.split(',')
        for o in options:
            if '=' in o:
                #We have a key=value
                key, value = o.split('=')
                pairs[key] = value
            else:
                bits |= Export.bool_option[o]

        return bits, pairs

    @staticmethod
    def parse(export_text):
        rc = []
        pattern = re.compile(Export.export_regex)

        for m in re.finditer(pattern, export_text):
            rc.append(Export(m.group(2), m.group(1),
                             *Export.parse_opt(m.group(3))))
        return rc

    @staticmethod
    def _append(s, a):
        if len(s):
            s = s + "," + a
        else:
            s = a
        return s

    def options_list(self):
        rc = []
        for k, v in self.bool_option.items():
            if self.options & v:
                rc.append(k)

        for k, v in self.key_value_options.items():
            rc.append('%s=%s' % (k, v))

        return rc

    def options_string(self):
        return ','.join(self.options_list())

    def __repr__(self):
        return "%s%s(%s)" % (self.path.ljust(50), self.host,
                             self.options_string())


class Nfs(object):
    """
    Python module for configuring NFS exports
    """
    cmd = 'exportfs'

    def __init__(self):
        pass

    @staticmethod
    def security_options():
        return "sys", "krb5", "krb5i", "krb5p"

    @staticmethod
    def exports():
        """
        Return list of exports
        """
        rc = []
        ec, out, error = invoke([Nfs.cmd,  '-v'])
        rc = Export.parse(out)
        return rc

    @staticmethod
    def export_add(host, path, bit_wise_options, key_value_options):
        """
        Adds a path as an NFS export
        """
        export = Export(host, path, bit_wise_options, key_value_options)
        options = export.options_string()

        cmd = [Nfs.cmd]

        if len(options):
            cmd.extend(['-o', options])

        cmd.extend(['%s:%s' % (host, path)])

        ec, out, err = invoke(cmd, False)
        if ec == 0:
            return None
        elif ec == 22:
            raise ValueError("Invalid option: %s" % err)
        else:
            raise RuntimeError('Unexpected exit code "%s" %s, out= %s' %
                               (str(cmd), str(ec),
                                str(out + ":" + err)))

    @staticmethod
    def export_remove(export):
        ec, out, err = invoke([Nfs.cmd, '-u', '%s:%s' %
                                              (export.host, export.path)])
