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
# Routines to export block devices over iscsi.

import contextlib
from rtslib import (Target, TPG, NodeACL, FabricModule, BlockStorageObject, RTSRoot,
                    NetworkPortal, LUN, MappedLUN, RTSLibError, RTSLibNotInCFS)
import lvm
from main import TargetdError
from utils import ignored


def get_vg_lv(pool_name):
    """
    Checks for the existence of a '/' in the pool name.  We are using this
    as an indicator that the vg & lv refer to a thin pool.
    """
    if '/' in pool_name:
        return pool_name.split('/')
    else:
        return pool_name, None


def pool_check(pool_name):
    """
    pool_name *cannot* be trusted, funcs taking a pool param must call
    this or vgopen() to ensure passed-in pool name is one targetd has
    been configured to use.
    """
    pool_to_check = get_vg_lv(pool_name)[0]

    if pool_to_check not in [get_vg_lv(x)[0] for x in pools]:
        raise TargetdError(-110, "Invalid pool")


@contextlib.contextmanager
def vgopen(pool_name):
    """
    Helper function to check/close vg for us.
    """
    global lib_calls
    pool_check(pool_name)
    with contextlib.closing(lvm.vgOpen(pool_name, "w")) as vg:
        yield vg

    # Clean library periodically
    lib_calls += 1
    if lib_calls > 50:
        try:
            # May not be present if using older library
            lvm.gc()
        except AttributeError:
            pass
        lib_calls = 0

pools = []
target_name = None
lib_calls = 0


#
# config_dict must include block_pools and target_name or we blow up
#
def initialize(config_dict):

    global pools
    pools = config_dict['block_pools']

    global target_name
    target_name = config_dict['target_name']

    # fail early if can't access any vg
    for pool in pools:
        test_vg = lvm.vgOpen(get_vg_lv(pool)[0])
        test_vg.close()

    return dict(
        vol_list=volumes,
        vol_create=create,
        vol_destroy=destroy,
        vol_copy=copy,
        export_list=export_list,
        export_create=export_create,
        export_destroy=export_destroy,
        initiator_set_auth=initiator_set_auth,
    )


def volumes(req, pool):
    output = []
    vg_name, lv_pool = get_vg_lv(pool)
    with vgopen(vg_name) as vg:
        for lv in vg.listLVs():
            attrib = lv.getAttr()
            if attrib[0] == 'V' or attrib[0] == '-':
                output.append(dict(name=lv.getName(), size=lv.getSize(),
                                   uuid=lv.getUuid()))
    return output


def create(req, pool, name, size):
    vg_name, lv_pool = get_vg_lv(pool)
    with vgopen(vg_name) as vg:
        if lv_pool:
            # Fall back to non-thinp if needed
            try:
                vg.createLvThin(lv_pool, name, int(size))
            except AttributeError:
                vg.createLvLinear(name, int(size))
        else:
            vg.createLvLinear(name, int(size))


def destroy(req, pool, name):
    with ignored(RTSLibNotInCFS):
        fm = FabricModule('iscsi')
        t = Target(fm, target_name, mode='lookup')
        tpg = TPG(t, 1, mode='lookup')

        so_name = "%s:%s" % (pool, name)
        if so_name in (lun.storage_object.name for lun in tpg.luns):
            raise TargetdError(-303, "Volume '%s' cannot be "
                                     "removed while exported" % name)

    with vgopen(get_vg_lv(pool)[0]) as vg:
        vg.lvFromName(name).remove()


def copy(req, pool, vol_orig, vol_new, timeout=10):
    """
    Create a new volume that is a copy of an existing one.
    Since 0.6, requires thinp support.
    """
    vg_name, thin_pool = get_vg_lv(pool)

    with vgopen(vg_name) as vg:
        if not thin_pool:
            raise RuntimeError("copy requires thin-provisioned volumes")

        try:
            vg.lvFromName(vol_orig).snapshot(vol_new)
        except AttributeError:
            raise NotImplementedError("liblvm lacks thin snap support")


def export_list(req):
    try:
        fm = FabricModule('iscsi')
        t = Target(fm, target_name, mode='lookup')
        tpg = TPG(t, 1, mode='lookup')
    except RTSLibNotInCFS:
        return []

    exports = []
    for na in tpg.node_acls:
        for mlun in na.mapped_luns:
            mlun_vg, mlun_name = \
                mlun.tpg_lun.storage_object.udev_path.split("/")[2:]
            with vgopen(get_vg_lv(mlun_vg)[0]) as vg:
                lv = vg.lvFromName(mlun_name)
                exports.append(
                    dict(initiator_wwn=na.node_wwn, lun=mlun.mapped_lun,
                         vol_name=mlun_name, pool=mlun_vg,
                         vol_uuid=lv.getUuid(), vol_size=lv.getSize()))
    return exports


def export_create(req, pool, vol, initiator_wwn, lun):
    # get wwn of volume so LIO can export as vpd83 info
    vg_name, thin_pool = get_vg_lv(pool)

    with vgopen(vg_name) as vg:
        vol_serial = vg.lvFromName(vol).getUuid()

    # only add new SO if it doesn't exist
    # so.name concats pool & vol names separated by ':'
    so_name = "%s:%s" % (vg_name, vol)
    try:
        so = BlockStorageObject(so_name)
    except RTSLibError:
        so = BlockStorageObject(so_name, dev="/dev/%s/%s" % (vg_name, vol))
        so.wwn = vol_serial

    # export useful scsi model if kernel > 3.8
    with ignored(RTSLibError):
        so.set_attribute("emulate_model_alias", '1')

    fm = FabricModule('iscsi')
    t = Target(fm, target_name)
    tpg = TPG(t, 1)
    tpg.enable = True
    tpg.set_attribute("authentication", '0')
    NetworkPortal(tpg, "0.0.0.0")
    na = NodeACL(tpg, initiator_wwn)

    # only add tpg lun if it doesn't exist
    for tmp_lun in tpg.luns:
        if tmp_lun.storage_object.name == so.name \
                and tmp_lun.storage_object.plugin == 'block':
            tpg_lun = tmp_lun
            break
    else:
        tpg_lun = LUN(tpg, storage_object=so)

    # only add mapped lun if it doesn't exist
    for tmp_mlun in tpg_lun.mapped_luns:
        if tmp_mlun.mapped_lun == lun:
            break
    else:
        MappedLUN(na, lun, tpg_lun)

    RTSRoot().save_to_file()


def export_destroy(req, pool, vol, initiator_wwn):
    pool_check(pool)
    fm = FabricModule('iscsi')
    t = Target(fm, target_name)
    tpg = TPG(t, 1)
    na = NodeACL(tpg, initiator_wwn)

    vg_name, thin_pool = get_vg_lv(pool)

    for mlun in na.mapped_luns:
        # all SOs are Block so we can access udev_path safely
        mlun_vg, mlun_name = \
            mlun.tpg_lun.storage_object.udev_path.split("/")[2:]

        if mlun_vg == vg_name and mlun_name == vol:
            tpg_lun = mlun.tpg_lun
            mlun.delete()
            # be tidy and delete unused tpg lun mappings?
            if not len(list(tpg_lun.mapped_luns)):
                so = tpg_lun.storage_object
                tpg_lun.delete()
                so.delete()
            break
    else:
        raise TargetdError(-151, "Volume '%s' not found in %s exports" %
                                 (vol, initiator_wwn))

    # Clean up tree if branch has no leaf
    if not len(list(na.mapped_luns)):
        na.delete()
        if not len(list(tpg.node_acls)):
            tpg.delete()
            if not len(list(t.tpgs)):
                t.delete()

    RTSRoot().save_to_file()


def initiator_set_auth(req, initiator_wwn, in_user, in_pass, out_user,
                       out_pass):
    fm = FabricModule('iscsi')
    t = Target(fm, target_name)
    tpg = TPG(t, 1)
    na = NodeACL(tpg, initiator_wwn)

    if not in_user or not in_pass:
        # rtslib treats '' as its NULL value for these
        in_user = in_pass = ''

    if not out_user or not out_pass:
        out_user = out_pass = ''

    na.chap_userid = in_user
    na.chap_password = in_pass

    na.chap_mutual_userid = out_user
    na.chap_mutual_password = out_pass

    RTSRoot().save_to_file()


def block_pools(req):
    results = []

    for pool in pools:
            with vgopen(get_vg_lv(pool)[0]) as vg:
                results.append(dict(name=pool, size=vg.getSize(),
                                    free_size=vg.getFreeSize(), type='block',
                                    uuid=vg.getUuid()))

    return results
