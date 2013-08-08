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
# Copyright 2012, Andy Grover <agrover@redhat.com>
# Copyright 2013, Tony Asleson <tasleson@redhat.com>
#
# fs support using btrfs.

import os
import time
from subprocess import Popen, PIPE
from main import TargetdError
from nfs import Nfs, Export


# Notes:
#
# User can configure block pools (lvm volume groups) 1 to many or 0-many file
# system mount points to be used as pools.  At this time you have to specify
# a block pool for block operations and file system mount point pool for FS
# operations.  We could use files on a file system for block too and create
# file systems on top of lvm too, but that is TBD.
#
# We are using btrfs to provide all the cool fast FS features.  User supplies a
# btrfs mount point and we create a targetd_fs and targetd_ss subvolumes.  Each
# time the user creates a file system we are creating a subvolume under fs.
# Each time a FS clone is made we create the clone under fs.  For each snapshot
# (RO clone) we are creating a read only snapshot in
# <mount>/targetd_ss/<fsname>/<snapshot name>
#
# There may be better ways of utilizing btrfs.

import logging as log

fs_path = "targetd_fs"
ss_path = "targetd_ss"
fs_cmd = 'btrfs'


pools = []

def initialize(config_dict):

    global pools
    pools = config_dict['fs_pools']

    for pool in pools:
        # Make sure we have the appropriate subvolumes available
        try:
            create_sub_volume(os.path.join(pool, fs_path))
            create_sub_volume(os.path.join(pool, ss_path))
        except TargetdError, e:
            log.error('Unable to create required subvolumes')
            log.error(e.msg)
            raise

    return dict(
        fs_list=fs,
        fs_destroy=fs_destroy,
        fs_create=fs_create,
        fs_clone=fs_clone,
        ss_list=ss,
        fs_snapshot=fs_snapshot,
        fs_snapshot_delete=fs_snapshot_delete,
        nfs_export_auth_list=nfs_export_auth_list,
        nfs_export_list=nfs_export_list,
        nfs_export_add=nfs_export_add,
        nfs_export_remove=nfs_export_remove,
        )


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

    return c.returncode, out[0], out[1]


def create_sub_volume(p):
    if not os.path.exists(p):
        invoke([fs_cmd, 'subvolume', 'create', p])


def split_stdout(out):
    """
    Split the text out as an array of text arrays.
    """
    rc = []
    for line in out.split('\n'):
        elem = line.split(' ')
        if len(elem) > 1:
            rc.append(elem)
    return rc


def fs_space_values(mount_point):
    """
    Return a tuple (total, free) from the specified path
    """
    st = os.statvfs(mount_point)
    free = (st.f_bavail * st.f_frsize)
    total = (st.f_blocks * st.f_frsize)
    return total, free


def pool_check(pool_name):
    """
    pool_name *cannot* be trusted, funcs taking a pool param must call
    this or to ensure passed-in pool name is one targetd has
    been configured to use.
    """
    if pool_name not in pools:
        raise TargetdError(-110, "Invalid filesystem pool")


def fs_create(req, pool_name, name, size_bytes):
    pool_check(pool_name)

    full_path = os.path.join(pool_name, fs_path, name)

    if not os.path.exists(full_path):
        invoke([fs_cmd, 'subvolume', 'create', full_path])
    else:
        raise TargetdError(-53, 'FS already exists')


def fs_snapshot(req, fs_uuid, dest_ss_name):
    fs = _get_fs_by_uuid(req, fs_uuid)

    if fs:
        source_path = os.path.join(fs['pool'], fs_path, fs['name'])
        dest_base = os.path.join(fs['pool'], ss_path, fs['name'])
        dest_path = os.path.join(dest_base, dest_ss_name)

        create_sub_volume(dest_base)

        if os.path.exists(dest_path):
            raise TargetdError(-53, "Snapshot already exists with that name")

        invoke([fs_cmd, 'subvolume', 'snapshot', '-r', source_path, dest_path])


def fs_snapshot_delete(req, fs_uuid, ss_uuid):
    fs_hash = _get_fs_by_uuid(req, fs_uuid)
    snapshot = _get_ss_by_uuid(req, fs_uuid, ss_uuid, fs_hash)
    path = os.path.join(fs_hash['pool'], ss_path, fs_hash['name'],
                        snapshot['name'])
    fs_subvolume_delete(path)


def fs_subvolume_delete(path):
    invoke([fs_cmd, 'subvolume', 'delete', path])


def fs_destroy(req, uuid):
    # Check to see if this file system has any read-only snapshots, if yes then
    # delete.  The API requires a FS to list its RO copies, we may want to
    # reconsider this decision.

    fs = _get_fs_by_uuid(req, uuid)

    base_snapshot_dir = os.path.join(fs['pool'], ss_path, fs['name'])

    snapshots = ss(req, uuid)
    for s in snapshots:
        fs_subvolume_delete(os.path.join(base_snapshot_dir, s['name']))

    if os.path.exists(base_snapshot_dir):
        fs_subvolume_delete(base_snapshot_dir)

    fs_subvolume_delete(os.path.join(fs['pool'], fs_path, fs['name']))


def fs_pools(req):
    results = []

    for pool in pools:
        total, free = fs_space_values(pool)
        results.append(dict(name=pool, size=total, free_size=free, type='fs'))

    return results


def _fs_hash():
    fs_list = {}

    for pool in pools:
        full_path = os.path.join(pool, fs_path)

        # TODO take out this loop, used to handle bug in btrfs
        # ERROR: Failed to lookup path for root 0 - No such file or directory
        while True:
            result, out, err = invoke([fs_cmd, 'subvolume', 'list', '-u',
                                       full_path], False)
            if result == 0:
                data = split_stdout(out)
                if len(data):
                    (total, free) = fs_space_values(full_path)
                    for e in data:
                        sub_vol = e[10]
                        key = full_path + '/' + sub_vol
                        fs_list[key] = dict(name=sub_vol, uuid=e[8],
                                            total_space=total, free_space=free,
                                            pool=pool, full_path=key)
                break
            elif result == 19:
                time.sleep(1)
                continue
            else:
                raise TargetdError(-303, "Unexpected exit code %d" % result)

    return fs_list


def fs(req):
    return _fs_hash().values()


def ss(req, fs_uuid, fs_cache=None):
    snapshots = []

    if fs_cache is None:
        fs_cache = _get_fs_by_uuid(req, fs_uuid)

    full_path = os.path.join(fs_cache['pool'], ss_path, fs_cache['name'])

    # TODO take out this loop, used to handle bug in btrfs
    # ERROR: Failed to lookup path for root 0 - No such file or directory

    if os.path.exists(full_path):
        while True:
            result, out, err = invoke([fs_cmd, 'subvolume', 'list', '-s',
                                       full_path], False)
            if result == 0:
                data = split_stdout(out)
                if len(data):
                    for e in data:
                        ts = "%s %s" % (e[10], e[11])
                        time_epoch = int(time.mktime(
                            time.strptime(ts, '%Y-%m-%d %H:%M:%S')))
                        st = dict(name=e[-1], uuid=e[-3], timestamp=time_epoch)
                        snapshots.append(st)
                break
            elif result == 19:
                time.sleep(1)
                continue
            else:
                raise TargetdError(-303, "Unexpected exit code %d" % result)

    return snapshots


def _get_fs_by_uuid(req, fs_uuid):
    for f in fs(req):
        if f['uuid'] == fs_uuid:
            return f


def _get_ss_by_uuid(req, fs_uuid, ss_uuid, fs=None):
    if fs is None:
        fs = _get_fs_by_uuid(req, fs_uuid)

    for s in ss(req, fs_uuid, fs):
        if s['uuid'] == ss_uuid:
            return s


def fs_clone(req, fs_uuid, dest_fs_name, snapshot_id):
    fs = _get_fs_by_uuid(req, fs_uuid)

    if not fs:
        raise TargetdError(-104, "fs_uuid not found")

    if snapshot_id:
        snapshot = _get_ss_by_uuid(req, fs_uuid, snapshot_id)
        if not snapshot:
            raise TargetdError(-112, "snapshot not found")

        source = os.path.join(fs['pool'], ss_path, fs['name'], snapshot['name'])
        dest = os.path.join(fs['pool'], fs_path, dest_fs_name)
    else:
        source = os.path.join(fs['pool'], fs_path, fs['name'])
        dest = os.path.join(fs['pool'], fs_path, dest_fs_name)

    if os.path.exists(dest):
        raise TargetdError(-51, "Filesystem with that name exists")

    invoke([fs_cmd, 'subvolume', 'snapshot', source, dest])


def nfs_export_auth_list(req):
    return Nfs.security_options()


def nfs_export_list(req):
    rc = []
    exports = Nfs.exports()
    for e in exports:
        rc.append(dict(host=e.host, path=e.path, options=e.options_list()))
    return rc


def nfs_export_add(req, host, path, export_path, options):

    if export_path is not None:
        raise TargetdError(-401, "separate export path not supported at "
                                 "this time")
    bit_opt = 0
    key_opt = {}

    for o in options:
        if '=' in o:
            k, v = o.split('=')
            key_opt[k] = v
        else:
            bit_opt |= Export.bool_option[o]

    Nfs.export_add(host, path, bit_opt, key_opt)


def nfs_export_remove(req, host, path):
    found = False

    for e in Nfs.exports():
        if e.host == host and e.path == path:
            Nfs.export_remove(e)
            found = True

    if not found:
        raise TargetdError(-400, "NFS export to remove not found %s:%s",
                       (host, path))
