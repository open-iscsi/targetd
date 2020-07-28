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
from targetd.utils import invoke, TargetdError

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


def fs_initialize(config_dict, init_pools):

    global pools
    pools = [fs['mount'] for fs in init_pools]

    for pool in pools:
        # Make sure we have the appropriate subvolumes available
        try:
            create_sub_volume(os.path.join(pool, fs_path))
            create_sub_volume(os.path.join(pool, ss_path))
        except TargetdError as e:
            log.error('Unable to create required subvolumes {0} (Btrfs)'.format(e))
            raise


def create_sub_volume(p):
    if not os.path.exists(p):
        invoke([fs_cmd, 'subvolume', 'create', p])


def split_stdout(out):
    """
    Split the text out as an array of text arrays.
    """
    strip_it = '<FS_TREE>/'

    rc = []
    for line in out.split('\n'):
        elem = line.split(' ')
        if len(elem) > 1:
            tmp = []
            for z in elem:
                if z.startswith(strip_it):
                    tmp.append(z[len(strip_it):])
                else:
                    tmp.append(z)
            rc.append(tmp)
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
        raise TargetdError(TargetdError.INVALID_POOL,
                           "Invalid filesystem pool (Btrfs)")


def has_fs_pool(pool_name):
    """
        This can be used to check if module owns given fs_pool without raising
        exception
    """
    return pool_name in pools


def fs_create(req, pool_name, name, size_bytes):
    pool_check(pool_name)

    full_path = os.path.join(pool_name, fs_path, name)

    if not os.path.exists(full_path):
        invoke([fs_cmd, 'subvolume', 'create', full_path])
    else:
        raise TargetdError(TargetdError.EXISTS_FS_NAME, 'FS already exists (Btrfs)')


def fs_snapshot(req, pool, name, dest_ss_name):
    source_path = os.path.join(pool, fs_path, name)
    dest_base = os.path.join(pool, ss_path, name)
    dest_path = os.path.join(dest_base, dest_ss_name)

    create_sub_volume(dest_base)

    if os.path.exists(dest_path):
        raise TargetdError(TargetdError.EXISTS_FS_NAME,
                           "Snapshot already exists with that name (Btrfs)")

    invoke([fs_cmd, 'subvolume', 'snapshot', '-r', source_path, dest_path])


def fs_snapshot_delete(req, pool, name, ss_name):
    path = os.path.join(pool, ss_path, name,
                        ss_name)
    fs_subvolume_delete(path)


def fs_subvolume_delete(path):
    invoke([fs_cmd, 'subvolume', 'delete', path])


def fs_destroy(req, pool, name):
    # Check to see if this file system has any read-only snapshots, if yes then
    # delete.  The API requires a FS to list its RO copies, we may want to
    # reconsider this decision.

    base_snapshot_dir = os.path.join(pool, ss_path, name)

    snapshots = ss(req, pool, name)
    for s in snapshots:
        fs_subvolume_delete(os.path.join(base_snapshot_dir, s['name']))

    if os.path.exists(base_snapshot_dir):
        fs_subvolume_delete(base_snapshot_dir)

    fs_subvolume_delete(os.path.join(pool, fs_path, name))


def fs_pools(req):
    results = []

    for pool in pools:
        total, free = fs_space_values(pool)
        results.append(dict(name=pool, size=total, free_size=free, type='fs'))

    return results


def _invoke_retries(command, throw_exception):
    # TODO take out this loop, used to handle bug in btrfs
    # ERROR: Failed to lookup path for root 0 - No such file or directory

    for i in range(0, 5):
        result, out, err = invoke(command, False)
        if result == 0:
            return result, out, err
        elif result == 19:
            time.sleep(1)
            continue
        else:
            raise TargetdError(TargetdError.UNEXPECTED_EXIT_CODE,
                               "Unexpected exit code %d (Btrfs)" % result)

    raise TargetdError(TargetdError.UNEXPECTED_EXIT_CODE,
                       "Unable to execute command after "
                       "multiple retries %s (Btrfs)" % (str(command)))


def fs_hash():
    fs_list = {}

    for pool in pools:
        full_path = os.path.join(pool, fs_path)

        result, out, err = _invoke_retries(
            [fs_cmd, 'subvolume', 'list', '-ua', pool], False)

        data = split_stdout(out)
        if len(data):
            (total, free) = fs_space_values(full_path)
            for e in data:
                sub_vol = e[10]

                prefix = fs_path + os.path.sep

                if sub_vol[:len(prefix)] == prefix:
                    key = os.path.join(pool, sub_vol)
                    fs_list[key] = dict(
                        name=sub_vol[len(prefix):],
                        uuid=e[8],
                        total_space=total,
                        free_space=free,
                        pool=pool,
                        full_path=key
                    )

    return fs_list


def ss(req, pool, name):
    '''
        Returns the snapshots belonging to this filesystem
    :param req:
    :param pool: pool of the filesystem
    :param name: name of the subvol of this filesystem
    :return: list of snapshots
    '''
    snapshots = []

    full_path = os.path.join(pool, ss_path, name)

    if os.path.exists(full_path):
        result, out, err = _invoke_retries(
            [fs_cmd, 'subvolume', 'list', '-s', full_path], False)

        data = split_stdout(out)
        if len(data):
            for e in data:
                ts = "%s %s" % (e[10], e[11])
                time_epoch = int(
                    time.mktime(time.strptime(ts, '%Y-%m-%d %H:%M:%S')))
                st = dict(name=e[-1], uuid=e[-3], timestamp=time_epoch)
                snapshots.append(st)

    return snapshots


def fs_clone(req, pool, name, dest_fs_name, snapshot_name=None):
    if snapshot_name is not None:
        source = os.path.join(pool, ss_path, name,
                              snapshot_name)
        dest = os.path.join(pool, fs_path, dest_fs_name)
    else:
        source = os.path.join(pool, fs_path, name)
        dest = os.path.join(pool, fs_path, dest_fs_name)

    if os.path.exists(dest):
        raise TargetdError(TargetdError.EXISTS_CLONE_NAME,
                           "Filesystem with that name exists (Btrfs)")

    invoke([fs_cmd, 'subvolume', 'snapshot', source, dest])