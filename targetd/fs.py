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

from targetd.backends import btrfs, zfs
from targetd.mount import Mount
from targetd.nfs import Nfs, Export
from targetd.utils import TargetdError

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

pool_modules = {"zfs": zfs, "btrfs": btrfs}
allow_chown = False


def pool_module(pool_name):
    """
    Determines the module responsible for the given pool
    :param pool_name: the pool to determine this for
    :return: the module responsible for it
    """
    for modname, mod in pool_modules.items():
        if mod.has_fs_pool(pool_name):
            return mod
    raise TargetdError(TargetdError.INVALID_POOL, "Invalid pool (%s)" % pool_name)


def initialize(config_dict):
    pools = {"zfs": [], "btrfs": []}
    global allow_chown

    allow_chown = config_dict["allow_chown"]

    all_fs_pools = list(config_dict["fs_pools"])

    for mount in all_fs_pools:
        if not os.path.exists(mount):
            raise TargetdError(
                TargetdError.NOT_FOUND_FS,
                "The fs_pool {0} does not exist".format(mount),
            )

    for info in Mount.mounted_filesystems():
        if info[Mount.MOUNT_POINT] in all_fs_pools:
            filesystem = info[Mount.FS_TYPE]
            if filesystem in pool_modules:
                # forward both mountpoint and device to the backend as ZFS prefers its own devices (pool/volume) and
                # btrfs prefers mount points (/mnt/btrfs). Otherwise ZFS or btrfs needs to ask mounted_filesystems again
                pools[filesystem].append(
                    {"mount": info[Mount.MOUNT_POINT], "device": info[Mount.DEVICE]}
                )
            else:
                raise TargetdError(
                    TargetdError.NO_SUPPORT,
                    "Unsupported filesystem {0} for pool {1}".format(info[2], info[1]),
                )

    for modname, mod in pool_modules.items():
        mod.fs_initialize(config_dict, pools[modname])

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


def fs_create(req, pool_name, name, size_bytes):
    """
    Create a filesystem inside a given pool with a given name
    :param req:
    :param pool_name: the pool where to create the filesystem
    :param name: name to use for the filesystem
    :param size_bytes: size limit of the filesystetm
    """
    pool_module(pool_name).fs_create(req, pool_name, name, size_bytes)


def fs_snapshot(req, fs_uuid, dest_ss_name):
    """
    Create a snapshot from the filesystem described by the given uuid
    :param req:
    :param fs_uuid: the uuid of the filesystem to snapshot
    :param dest_ss_name: name of the snapshot
    :return:
    """
    fs_ht = _get_fs_by_uuid(req, fs_uuid)
    pool_module(fs_ht["pool"]).fs_snapshot(
        req, fs_ht["pool"], fs_ht["name"], dest_ss_name
    )


def fs_snapshot_delete(req, fs_uuid, ss_uuid):
    fs_ht = _get_fs_by_uuid(req, fs_uuid)
    snapshot = _get_ss_by_uuid(req, fs_uuid, ss_uuid, fs_ht)
    pool_module(fs_ht["pool"]).fs_snapshot_delete(
        req, fs_ht["pool"], fs_ht["name"], snapshot["name"]
    )


def fs_destroy(req, uuid):
    # Check to see if this file system has any read-only snapshots, if yes then
    # delete.  The API requires a FS to list its RO copies, we may want to
    # reconsider this decision.
    fs_ht = _get_fs_by_uuid(req, uuid)
    pool_module(fs_ht["pool"]).fs_destroy(req, fs_ht["pool"], fs_ht["name"])


def fs_pools(req):
    results = []

    for mod in pool_modules.values():
        results.extend(mod.fs_pools(req))

    return results


def _fs_hash():
    fs_list = {}

    for mod in pool_modules.values():
        fs_list.update(mod.fs_hash())

    return fs_list


def fs(req):
    return list(_fs_hash().values())


def ss(req, fs_uuid, fs_cache=None):
    if fs_cache is None:
        fs_cache = _get_fs_by_uuid(req, fs_uuid)

    return pool_module(fs_cache["pool"]).ss(req, fs_cache["pool"], fs_cache["name"])


def _get_fs_by_uuid(req, fs_uuid):
    for f in fs(req):
        if f["uuid"] == fs_uuid:
            return f
    raise TargetdError(TargetdError.NOT_FOUND_FS, "fs_uuid not found")


def _get_ss_by_uuid(req, fs_uuid, ss_uuid, fs_ht=None):
    if fs_ht is None:
        fs_ht = _get_fs_by_uuid(req, fs_uuid)

    for s in ss(req, fs_uuid, fs_ht):
        if s["uuid"] == ss_uuid:
            return s
    raise TargetdError(TargetdError.NOT_FOUND_SS, "snapshot not found")


def fs_clone(req, fs_uuid, dest_fs_name, snapshot_id):
    fs_ht = _get_fs_by_uuid(req, fs_uuid)
    if snapshot_id:
        snapshot = _get_ss_by_uuid(req, fs_uuid, snapshot_id)
        source = snapshot["name"]
    else:
        source = None

    pool_module(fs_ht["pool"]).fs_clone(
        req, fs_ht["pool"], fs_ht["name"], dest_fs_name, source
    )


def nfs_export_auth_list(req):
    return Nfs.security_options()


def nfs_export_list(req):
    rc = []
    exports = Nfs.exports()
    for e in exports:
        rc.append(dict(host=e.host, path=e.path, options=e.options_list()))
    return rc


def nfs_export_add(req, host, path, options=None, chown=None, export_path=None):

    if not isinstance(options, list):
        if options is not None and len(options) > 0:
            options = [options]
        else:
            options = []

    if export_path is not None:
        raise TargetdError(
            TargetdError.NFS_NO_SUPPORT,
            "separate export path not supported at " "this time",
        )
    bit_opt = 0
    key_opt = {}

    for o in options:
        if "=" in o:
            k, v = o.split("=")
            key_opt[k] = v
        else:
            bit_opt |= Export.bool_option[o]

    if chown is not None:
        if not allow_chown:
            raise TargetdError(
                TargetdError.NO_SUPPORT,
                "Chown is disabled. Consult manual before enabling it.",
            )
        items = chown.split(":")
        try:
            uid = int(items[0])
            gid = -1
            if len(items) > 1:
                gid = int(items[1])
            os.chown(path, uid, gid)
        except ValueError as e:
            raise TargetdError(
                TargetdError.INVALID_ARGUMENT, "Wrong chown arguments: {}".format(e)
            )
    try:
        Nfs.export_add(host, path, bit_opt, key_opt)
    except ValueError as e:
        raise TargetdError(TargetdError.INVALID_ARGUMENT, "{}".format(e))
    return dict(host=host, path=path)


def nfs_export_remove(req, host, path):
    found = False

    for e in Nfs.exports():
        if e.host == host and e.path == path:
            Nfs.export_remove(e)
            found = True

    if not found:
        raise TargetdError(
            TargetdError.NOT_FOUND_NFS_EXPORT,
            "NFS export to remove not found %s:%s" % (host, path),
        )
