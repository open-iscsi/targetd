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
# Routines to specific to LVM export block devices over iscsi.

import gi

gi.require_version("GLib", "2.0")
gi.require_version("BlockDev", "2.0")

from gi.repository import GLib
from gi.repository import BlockDev as bd
from targetd.main import TargetdError

REQUESTED_PLUGIN_NAMES = {"lvm"}

requested_plugins = bd.plugin_specs_from_names(REQUESTED_PLUGIN_NAMES)

bd.switch_init_checks(False)

pools = []
vg_name_2_pool_name_dict = {}

try:
    succ_ = bd.init(requested_plugins)
except GLib.GError as err:
    raise RuntimeError("Failed to initialize libbd and its plugins (%s)" %
                       REQUESTED_PLUGIN_NAMES)


def get_vg_lv(pool_name):
    """
    Checks for the existence of a '/' in the pool name.  We are using this
    as an indicator that the vg & lv refer to a thin pool.
    """
    if '/' in pool_name:
        return pool_name.split('/')
    else:
        return pool_name, None


def has_pool(pool_name):
    """
        This can be used to check if module owns given pool without raising
        exception
    """
    pool_to_check = get_vg_lv(pool_name)[0]
    return pool_to_check in [get_vg_lv(x)[0] for x in pools]


def has_udev_path(udev_path):
    try:
        mlun_vg, mlun_name = split_udev_path(udev_path)
    except (IndexError, ValueError, TypeError):
        return False
    return has_pool(mlun_vg)


def split_udev_path(udev_path):
    return udev_path.split("/")[2:]


def pool2dev_name(pool):
    """
        When using LVM we need to convert pool name to vg_name and vice-versa.
        That's because with thin pool it's not the same thing.
    """
    vg_name, thin_pool = get_vg_lv(pool)
    return vg_name


def dev2pool_name(dev):
    """
        When using LVM we need to convert vg_name to pool name and vice-versa.
        That's because with thin pool it's not the same thing.
    """
    return vg_name_2_pool_name_dict[dev]


def get_so_name(pool, volname):
    """
        Storage object names in LVM are just plain vg_name:volname
    """
    vg_name, lv_pool = get_vg_lv(pool)
    return "%s:%s" % (vg_name, volname)


def so_name2pool_volume(so_name):
    vg_name, vol_name = so_name.split(":")
    return dev2pool_name(vg_name), vol_name


def has_so_name(so_name):
    pool_name, vol_name = so_name.split(":")
    return has_pool(pool_name)


def get_dev_path(pool_name, vol_name):
    return "/dev/%s/%s" % (pool2dev_name(pool_name), vol_name)


def initialize(config_dict, init_pools):
    global pools
    check_pools_access(init_pools)
    pools = init_pools
    for pool_name in pools:
        vg_name = get_vg_lv(pool_name)[0]
        vg_name_2_pool_name_dict[vg_name] = pool_name


def check_pools_access(check_pools):
    for pool in check_pools:
        thinp = None
        error = ""
        vg_name, thin_pool = get_vg_lv(pool)

        if vg_name and thin_pool:
            # We have VG name and LV name, check for it!
            try:
                thinp = bd.lvm.lvinfo(vg_name, thin_pool)
            except bd.LVMError as lve:
                error = str(lve).strip()

            if thinp is None:
                raise TargetdError(TargetdError.NOT_FOUND_VOLUME_GROUP,
                                   "VG with thin LV {} not found, "
                                   "nested error: {}".format(pool, error))
        else:
            try:
                bd.lvm.vginfo(vg_name)
            except bd.LVMError as vge:
                error = str(vge).strip()
                raise TargetdError(TargetdError.NOT_FOUND_VOLUME_GROUP,
                                   "VG pool {} not found, "
                                   "nested error: {}".format(vg_name, error))

        # Allowed multi-pool configs:
        # two thinpools from a single vg: ok
        # two vgs: ok
        # vg and a thinpool from that vg: BAD
        #
        if thin_pool and vg_name in check_pools:
            raise TargetdError(
                TargetdError.INVALID,
                "VG pool and thin pool from same VG not supported")

    return


def volumes(req, pool):
    output = []
    vg_name, lv_pool = get_vg_lv(pool)
    for lv in bd.lvm.lvs(vg_name):
        attrib = lv.attr
        if not lv_pool:
            if attrib[0] == '-':
                output.append(
                    dict(name=lv.lv_name, size=lv.size, uuid=lv.uuid))
        else:
            if attrib[0] == 'V' and lv.pool_lv == lv_pool:
                output.append(
                    dict(name=lv.lv_name, size=lv.size, uuid=lv.uuid))

    return output


def create(req, pool, name, size):
    # Check to ensure that we don't have a volume with this name already,
    # lvm will fail if we try to create a LV with a duplicate name
    if any(v['name'] == name for v in volumes(req, pool)):
        raise TargetdError(TargetdError.NAME_CONFLICT,
                           "Volume with that name exists")

    vg_name, lv_pool = get_vg_lv(pool)
    if lv_pool:
        # Fall back to non-thinp if needed
        try:
            bd.lvm.thlvcreate(vg_name, lv_pool, name, int(size))
        except bd.LVMError:
            bd.lvm.lvcreate(vg_name, name, int(size), 'linear')
    else:
        bd.lvm.lvcreate(vg_name, name, int(size), 'linear')


def destroy(req, pool, name):
    vg_name, lv_pool = get_vg_lv(pool)
    bd.lvm.lvremove(vg_name, name)


def copy(req, pool, vol_orig, vol_new, size, timeout=10):
    """
    Create a new volume that is a copy of an existing one.
    Since 0.6, requires thinp support.
    """
    if any(v['name'] == vol_new for v in volumes(req, pool)):
        raise TargetdError(TargetdError.NAME_CONFLICT,
                           "Volume with that name exists")

    vg_name, thin_pool = get_vg_lv(pool)

    if not thin_pool:
        raise RuntimeError("copy requires thin-provisioned volumes")

    try:
        bd.lvm.thsnapshotcreate(vg_name, vol_orig, vol_new, thin_pool)
    except bd.LVMError as err:
        raise TargetdError(TargetdError.UNEXPECTED_EXIT_CODE,
                           "Failed to copy volume, "
                           "nested error: {}".format(str(err).strip()))

    if size is not None:
        try:
            bd.lvm.lvresize(vg_name, vol_new, size)
        except bd.LVMError as err:
            raise TargetdError(TargetdError.UNEXPECTED_EXIT_CODE,
                               "Failed to resize volume, "
                               "nested error: {}".format(str(err).strip()))


def vol_info(pool, name):
    return bd.lvm.lvinfo(pool2dev_name(pool), name)


def block_pools(req):
    results = []

    def thinp_get_free_bytes(thinp_lib_obj):
        # we can only get used percent, so calculate an approx. free bytes
        # These return an integer in of millionths of a percent, so
        # add them and get a decimalization by dividing by another 100
        #
        # Note: It is possible for percentages to return a (-1) which depending
        # on lvm2app library version can be returned as -1 or 2**64-1

        unsigned_val = (2 ** 64 - 1)
        free_bytes = thinp_lib_obj.size
        dp = thinp_lib_obj.data_percent
        mp = thinp_lib_obj.metadata_percent

        if dp != -1 and dp != unsigned_val and mp != -1 and mp != unsigned_val:
            used_pct = float(dp + mp) / 100000000
            fs = int(free_bytes * (1 - used_pct))

            # Sanity checking, domain of free bytes should be [0..total size]
            if 0 <= fs < free_bytes:
                free_bytes = fs

        return free_bytes

    for pool in pools:
        vg_name, tp_name = get_vg_lv(pool)
        if not tp_name:
            vg = bd.lvm.vginfo(vg_name)
            results.append(
                dict(
                    name=pool,
                    size=vg.size,
                    free_size=vg.free,
                    type='block',
                    uuid=vg.uuid))
        else:
            thinp = bd.lvm.lvinfo(vg_name, tp_name)
            results.append(
                dict(
                    name=pool,
                    size=thinp.size,
                    free_size=thinp_get_free_bytes(thinp),
                    type='block',
                    uuid=thinp.uuid))

    return results
