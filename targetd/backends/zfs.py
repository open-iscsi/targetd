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
# Copyright 2012-2013, Andy Grover <agrover@redhat.com>
#
# Routines specific to ZFS to export zvols over iscsi
import distutils.spawn
import logging
import re
import subprocess, os
from time import time, mktime, strptime

from targetd.main import TargetdError

pools = []
pools_fs = dict()
zfs_cmd = ""
zfs_enable_copy = False
ALLOWED_DATASET_NAMES = re.compile('^[A-Za-z0-9][A-Za-z0-9_.\-]*$')

class VolInfo(object):
    """
        Just to have attributes compatible with LVM info.
    """
    uuid = ''
    size = 0

    def __init__(self, uuid, size):
        self.uuid = uuid
        self.size = size


def pool_check(pool_name):
    """
        pool_name *cannot* be trusted, funcs taking a pool param must call
        this to ensure passed-in pool name is one targetd has
        been configured to use.
    """
    if not has_pool(pool_name):
        raise TargetdError(TargetdError.INVALID_POOL, "Invalid pool (ZFS)")


def has_pool(pool_name):
    """
        This can be used to check if module owns given pool without raising
        exception
    """
    return pool_name in pools


def has_fs_pool(pool_name):
    """
        This can be used to check if module owns given fs_pool without raising
        exception
    """
    return pool_name in pools_fs


def has_udev_path(udev_path):
    try:
        pool, dataset = split_udev_path(udev_path)
    except (IndexError, ValueError, TypeError):
        return False
    return True


def split_udev_path(udev_path):
    dataset = udev_path.split("/", 2)[2]
    for p in pools:
        if dataset.startswith(p + "/"):
            return p, dataset.replace(p + "/", "", 1)


def pool2dev_name(pool):
    """
        Pool name and dev name (equivalent of vg from LVM) are the same in ZFS
    """
    return pool


def dev2pool_name(dev):
    """
        Pool name and dev name (equivalent of vg from LVM) are the same in ZFS
    """
    return dev


def get_so_name(pool, volname):
    """
        Using % here, because it's not allowed in zfs dataset names and
        / is not allowed in target's storage object names
    """
    return "%s:%s" % (pool.replace('/', '%'), volname)


def so_name2pool_volume(so_name):
    pool_name, vol_name = so_name.split(":")
    pool_name = pool_name.replace('%', '/')
    return pool_name, vol_name


def has_so_name(so_name):
    pool_name, vol_name = so_name.split(":")
    pool_name = pool_name.replace('%', '/')
    return has_pool(pool_name)


def get_dev_path(pool_name, vol_name):
    return "/dev/%s/%s" % (pool2dev_name(pool_name), vol_name)


def initialize(config_dict, init_pools):
    global pools
    global zfs_enable_copy
    zfs_enable_copy = zfs_enable_copy or config_dict['zfs_enable_copy']
    check_pools_access(init_pools)
    pools = init_pools


def fs_initialize(config_dict, init_pools):
    global pools_fs
    global zfs_enable_copy
    zfs_enable_copy = zfs_enable_copy or config_dict['zfs_enable_copy']
    pools_fs = {fs['mount']: fs['device'] for fs in init_pools}
    check_pools_access(list(pools_fs.values()))


def _check_dataset_name(name):
    if not ALLOWED_DATASET_NAMES.match(name):
        raise TargetdError(
            TargetdError.INVALID_ARGUMENT,
            "Invalid dataset name, can only contain alphanumeric characters,"
            "underscores, dots and hyphens"
        )


def _zfs_find_cmd():
    cmd = distutils.spawn.find_executable('zfs') \
          or distutils.spawn.find_executable('zfs', '/sbin:/usr/sbin')
    if cmd is None or not cmd:
        raise TargetdError(
            TargetdError.INVALID,
            "zfs_block_pools is set but no zfs command was found")
    global zfs_cmd
    zfs_cmd = cmd


def _zfs_exec_command(args=None):
    if args is None:
        args = []
    proc = subprocess.Popen([zfs_cmd] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = proc.communicate()
    if proc.returncode != 0:
        logging.debug("zfs command returned non-zero status: %s, %s. Stderr: %s. Stdout: %s"
                      % (proc.returncode, args, out, err))
    return proc.returncode, out, err


def _zfs_get(datasets, properties, recursive=False, fstype="all"):
    result = {}
    flags = '-Hp'
    if recursive:
        flags = '-Hpr'
    code, out, err = _zfs_exec_command(['get',
                                        flags,
                                        "-t", fstype,
                                        ",".join(properties)
                                        ] + datasets)
    for line in out.strip().split(b"\n"):
        fields = str(line, encoding='utf-8').strip().split("\t")
        if len(fields) < 2:
            continue
        if fields[0] in result:
            result[fields[0]][fields[1]] = fields[2].strip()
        else:
            result[fields[0]] = {
                fields[1]: fields[2].strip()
            }
    return result


def check_pools_access(check_pools):
    if any([s.startswith(i + "/") for s in check_pools for i in check_pools]):
        raise TargetdError(
            TargetdError.INVALID,
            "ZFS pools cannot contain both parent and child datasets")

    if any(":" in p for p in check_pools):
        raise TargetdError(
            TargetdError.INVALID,
            "Colon in ZFS pools is not supported")

    if len(check_pools) == 0:
        logging.debug("No ZFS pool defined, skipping ZFS")
        return

    _zfs_find_cmd()

    props = _zfs_get(check_pools, ["type", "name"])

    for p in check_pools:
        if p not in props or "type" not in props[p]:
            raise TargetdError(
                TargetdError.INVALID,
                "ZFS dataset does not exist: %s" % (p,))
        if props[p]["type"] != "filesystem":
            raise TargetdError(
                TargetdError.INVALID,
                "ZFS dataset must be of 'filesystem' type. %s is %s" %
                (p, props[p]["type"])
            )


def block_pools(req):
    if not zfs_cmd:
        return []
    results = []
    props = _zfs_get(pools, ["available", "used", "guid"])
    for pool in pools:
        results.append(
            dict(
                name=pool,
                size=int(props[pool]["available"]) +
                     int(props[pool]["used"]),
                free_size=int(props[pool]["available"]),
                type='block',
                uuid=int(props[pool]["guid"])))
    return results


def volumes(req, pool):
    if not zfs_cmd:
        return []
    allprops = _zfs_get([pool], ["volsize", "guid"], True, "volume")
    results = []
    for fullname, props in allprops.items():
        results.append(
            dict(
                name=fullname.replace(pool + "/", "", 1),
                size=int(props["volsize"]),
                uuid=props["guid"]
            ))
    return results


def fs_hash():
    if not zfs_cmd:
        return {}

    fs_list = {}

    for pool, zfs_pool in pools_fs.items():
        allprops = _zfs_get([zfs_pool], ["name","mountpoint","guid","used","available"], True, "filesystem")

        for fullname, props in allprops.items():
            if fullname == zfs_pool:
                continue

            sub_vol = fullname.replace(zfs_pool + "/", "", 1)

            key = props["name"]
            fs_list[key] = dict(
                name=sub_vol,
                uuid=props["guid"],
                total_space=int(props["used"]) + int(props["available"]),
                free_space=int(props["available"]),
                pool=pool,
                full_path=props["mountpoint"]
            )

    return fs_list


def vol_info(pool, name):
    props = _zfs_get([pool + "/" + name], ["guid", "volsize"], fstype="volume")
    if (pool + "/" + name) in props:
        props = props[pool + "/" + name]
        return VolInfo(props["guid"], int(props["volsize"]))


def fs_info(pool, name):
    props = _zfs_get([pool + "/" + name], ["guid", "used", "available"], fstype="filesystem")
    if (pool + "/" + name) in props:
        props = props[pool + "/" + name]
        return VolInfo(props["guid"], int(props["available"])+int(props["used"]))


def snap_info(pool, name, snapshot):
    props = _zfs_get([pool + "/" + name + "@" + snapshot], ["guid"], fstype="snapshot")
    if (pool + "/" + name + "@" + snapshot) in props:
        props = props[pool + "/" + name + "@" + snapshot]
        return dict(name=pool + "/" + name + "@" + snapshot,
                    uuid=props["guid"])


def create(req, pool, name, size):
    _check_dataset_name(name)
    code, out, err = _zfs_exec_command(["create", "-V", str(size), pool + "/" + name])
    if code != 0:
        logging.error("Could not create volume %s on pool %s. Code: %s, stderr %s"
                      % (name, pool, code, err))
        raise TargetdError(TargetdError.UNEXPECTED_EXIT_CODE, "Could not create volume %s on pool %s" % (name, pool))


def fs_create(req, pool, name, size):
    _check_dataset_name(name)
    zfs_pool = pools_fs[pool]
    code, out, err = _zfs_exec_command(["create", zfs_pool + "/" + name])
    if code != 0:
        logging.error("Could not create volume %s on pool %s. Code: %s, stderr %s"
                      % (name, pool, code, err))
        raise TargetdError(TargetdError.UNEXPECTED_EXIT_CODE, "Could not create volume %s on pool %s" % (name, pool))


def destroy(req, pool, name):
    _check_dataset_name(name)
    # -r will destroy snapshots and children but not dependant clones
    code, out, err = _zfs_exec_command(["destroy", "-r", pool + "/" + name])
    if code != 0:
        if b'volume has dependent clones' in err:
            logging.error(
                "Volume %s on %s has dependent clones and cannot be destroyed. Stderr: %s" % (name, pool, err))
            raise TargetdError(TargetdError.INVALID_ARGUMENT,
                               "Volume %s on %s has dependent clones and cannot be destroyed." % (name, pool))
        else:
            logging.error("Could not destroy volume %s on pool %s. Code: %s, stderr %s"
                          % (name, pool, code, err))
        raise TargetdError(TargetdError.UNEXPECTED_EXIT_CODE, "Could not destroy volume %s on pool %s" % (name, pool))


def fs_destroy(req, pool, name):
    zfs_pool = pools_fs[pool]
    destroy(req, zfs_pool, name)


def copy(req, pool, vol_orig, vol_new, timeout=10):
    _copy(req, pool, vol_orig, vol_new, vol_info)


def _copy(req, pool, vol_orig, vol_new, info_fn, snap=None):
    if not zfs_enable_copy:
        raise TargetdError(TargetdError.NO_SUPPORT, "Copy on ZFS disabled. Consult manual before enabling it.")
    _check_dataset_name(vol_orig)
    _check_dataset_name(vol_new)
    if info_fn(pool, vol_orig) is None:
        raise TargetdError(TargetdError.INVALID_ARGUMENT,
                           "Source volume %s does not exist on pool %s" % (vol_orig, pool))
    if info_fn(pool, vol_new) is not None:
        raise TargetdError(TargetdError.NAME_CONFLICT,
                           "Destination volume %s already exists on pool %s" % (vol_new, pool))
    if snap is None:
        snap = vol_new + str(int(time()))
        code, out, err = _zfs_exec_command(["snapshot", "%s/%s@%s" % (pool, vol_orig, snap)])
        if code != 0:
            raise TargetdError(TargetdError.UNEXPECTED_EXIT_CODE,
                               "Could not create snapshot of %s on pool %s" % (vol_orig, pool))
    code, out, err = _zfs_exec_command(["clone",
                                        "%s/%s@%s" % (pool, vol_orig, snap),
                                        "%s/%s" % (pool, vol_new)
                                        ])
    if code != 0:
        # try cleaning up the snapshot if cloning goes wrong
        _zfs_exec_command(["destroy", "%s/%s@%s" % (pool, vol_orig, snap)])
        raise TargetdError(TargetdError.UNEXPECTED_EXIT_CODE,
                           "Could not create clone of %s@%s on pool %s" % (vol_orig, snap, pool))


def ss(req, pool, name):
    snapshots = []

    zfs_pool = pools_fs[pool]

    # NOTE: Recursive is set to True as the ZFS version on Ubuntu in Travis does not appreciate getting snapshots
    # by passing in a non-snapshot name. Somewhere between version 0.7.5 and 0.8.4 this got fixed
    allprops = _zfs_get([zfs_pool+"/"+name], ["name", "guid", "creation"], True, "snapshot")
    for fullname, props in allprops.items():
        # Filter out any subvolume snapshots (these should not generally exist though
        # and indicate an administration issue)
        if not fullname.startswith(zfs_pool+"/"+name+"@"):
            logging.warning("found additional subvolumes with snapshots while trying to list snapshots. Please do not"
                            " create subvolumes underneath targetd managed subvolumes")
            continue
        time_epoch = int(props['creation'])
        st = dict(name=props['name'].replace((zfs_pool + "/" + name + "@"), "", 1), uuid=props['guid'], timestamp=time_epoch)
        snapshots.append(st)

    return snapshots


def fs_snapshot(req, pool, name, dest_ss_name):
    _check_dataset_name(name)
    _check_dataset_name(dest_ss_name)

    zfs_pool = pools_fs[pool]

    info = snap_info(zfs_pool, name, dest_ss_name)
    if info is not None:
        raise TargetdError(TargetdError.NAME_CONFLICT,
                           "Snapshot {0} already exists on pool {1} for {2}".format(dest_ss_name, pool, name))

    code, out, err = _zfs_exec_command(["snapshot", "{0}/{1}@{2}".format(zfs_pool, name, dest_ss_name)])
    if code != 0:
        raise TargetdError(TargetdError.UNEXPECTED_EXIT_CODE,
                           "Could not create snapshot")


def fs_snapshot_delete(req, pool, name, ss_name):
    _check_dataset_name(name)
    _check_dataset_name(ss_name)

    zfs_pool = pools_fs[pool]

    info = snap_info(zfs_pool, name, ss_name)
    if info is None:
        return

    code, out, err = _zfs_exec_command(["destroy", "-r", "{0}/{1}@{2}".format(zfs_pool, name, ss_name)])
    if code != 0:
        raise TargetdError(TargetdError.UNEXPECTED_EXIT_CODE,
                           "Could not destroy snapshot")


def fs_clone(req, pool, name, dest_fs_name, snapshot_name=None):
    zfs_pool = pools_fs[pool]

    _copy(req, zfs_pool, name, dest_fs_name, fs_info, snapshot_name)


def fs_pools(req):
    results = []

    for pool, zfs_pool in pools_fs.items():
        allprops = _zfs_get([zfs_pool], ["name","used","available"], False, "filesystem")
        if zfs_pool in allprops:
            props = allprops[zfs_pool]
            results.append(dict(name=pool, size=(int(props["used"])+int(props["available"])), free_size=int(props["available"]), type='fs'))

    return results
