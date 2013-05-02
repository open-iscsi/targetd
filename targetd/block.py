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
#
# Routines to export block devices over iscsi.

import contextlib
from rtslib import (Target, TPG, NodeACL, FabricModule, BlockStorageObject,
                    NetworkPortal, LUN, MappedLUN, RTSLibError, RTSLibNotInCFS)
import lvm
import socket
import time
from targetcli import UIRoot
from configshell import ConfigShell
from main import config, TargetdError
from utils import ignored


def pool_check(pool_name):
    """
    pool_name *cannot* be trusted, funcs taking a pool param must call
    this or vgopen() to ensure passed-in pool name is one targetd has
    been configured to use.
    """
    if pool_name not in pools:
        raise TargetdError(-110, "Invalid pool")


@contextlib.contextmanager
def vgopen(pool_name):
    """
    Helper function to check/close vg for us.
    """
    pool_check(pool_name)
    with contextlib.closing(lvm.vgOpen(pool_name, "w")) as vg:
        yield vg


pools = []
target_name = None

# Auth info for mutual auth
mutual_auth_user = ''
mutual_auth_password = ''

#
# config_dict must include block_pools and target_name or we blow up
#
def initialize(config_dict):

    global pools
    pools = config_dict['block_pools']

    global target_name
    target_name = config_dict['target_name']

    global mutual_auth_user
    mutual_auth_user = config_dict.get('mutual_auth_user', '')

    global mutual_auth_password
    mutual_auth_password = config_dict.get('mutual_auth_password', '')

    # fail early if can't access any vg
    for pool in pools:
        test_vg = lvm.vgOpen(pool)
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
    with vgopen(pool) as vg:
        for lv in vg.listLVs():
            output.append(dict(name=lv.getName(), size=lv.getSize(),
                               uuid=lv.getUuid()))
    return output


def create(req, pool, name, size):
    with vgopen(pool) as vg:
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

    with vgopen(pool) as vg:
        vg.lvFromName(name).remove()


def copy(req, pool, vol_orig, vol_new, timeout=10):
    """
    Create a new volume that is a copy of an existing one.
    If this operation takes longer than the timeout, it will return
    an async completion and report actual status later.
    """
    with vgopen(pool) as vg:
        copy_size = vg.lvFromName(vol_orig).getSize()

    create(req, pool, vol_new, copy_size)

    try:
        src_path = "/dev/%s/%s" % (pool, vol_orig)
        dst_path = "/dev/%s/%s" % (pool, vol_new)

        start_time = time.clock()
        with open(src_path, 'rb') as fsrc:
            with open(dst_path, 'wb') as fdst:
                copied = 0
                while copied != copy_size:
                    buf = fsrc.read(1024 * 1024)
                    if not buf:
                        break
                    fdst.write(buf)
                    copied += len(buf)
                    if time.clock() > (start_time + timeout):
                        req.mark_async()
                        req.async_status(0, int((float(copied) / copy_size) * 100))
        req.complete_maybe_async(0)

    except Exception, e:
        destroy(req, pool, vol_new)
        req.async_status(-303, int((float(copied) / copy_size) * 100))
        raise TargetdError(-303, "Unexpected exception: %s" % (str(e)))


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
            with vgopen(mlun_vg) as vg:
                lv = vg.lvFromName(mlun_name)
                exports.append(
                    dict(initiator_wwn=na.node_wwn, lun=mlun.mapped_lun,
                         vol_name=mlun_name, pool=mlun_vg,
                         vol_uuid=lv.getUuid(), vol_size=lv.getSize()))
    return exports


def _exports_save_config():
    """
    HACK: call targetcli saveconfig method to save state
    """
    root = UIRoot(ConfigShell(), as_root=True)
    root.ui_command_saveconfig()


def export_create(req, pool, vol, initiator_wwn, lun):
    # get wwn of volume so LIO can export as vpd83 info
    with vgopen(pool) as vg:
        vol_serial = vg.lvFromName(vol).getUuid()

    # only add new SO if it doesn't exist
    # so.name concats pool & vol names separated by ':'
    so_name = "%s:%s" % (pool, vol)
    try:
        so = BlockStorageObject(so_name)
    except RTSLibError:
        so = BlockStorageObject(so_name, dev="/dev/%s/%s" % (pool, vol))
        so.wwn = vol_serial

    # export useful scsi model if kernel > 3.8
    with ignored(RTSLibError):
        so.set_attribute("emulate_model_alias", '1')

    fm = FabricModule('iscsi')
    t = Target(fm, target_name)
    tpg = TPG(t, 1)
    tpg.enable = True
    tpg.set_attribute("authentication", '0')
    np = NetworkPortal(tpg, "0.0.0.0")
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
            mapped_lun = tmp_mlun
            break
    else:
        mapped_lun = MappedLUN(na, lun, tpg_lun)

    _exports_save_config()


def export_destroy(req, pool, vol, initiator_wwn):
    pool_check(pool)
    fm = FabricModule('iscsi')
    t = Target(fm, target_name)
    tpg = TPG(t, 1)
    na = NodeACL(tpg, initiator_wwn)

    for mlun in na.mapped_luns:
        # all SOs are Block so we can access udev_path safely
        mlun_vg, mlun_name = \
            mlun.tpg_lun.storage_object.udev_path.split("/")[2:]

        if mlun_vg == pool and mlun_name == vol:
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

    _exports_save_config()


def initiator_set_auth(req, initiator_wwn, username, password, mutual):
    fm = FabricModule('iscsi')
    t = Target(fm, target_name)
    tpg = TPG(t, 1)
    na = NodeACL(tpg, initiator_wwn)

    if not username or not password:
        # rtslib treats '' as its NULL value for these
        username = password = ''

    na.chap_userid = userid
    na.chap_password = password

    if mutual:
        na.chap_mutual_userid = target_auth_userid
        na.chap_mutual_password = target_auth_password
    else:
        na.chap_mutual_userid = ''
        na.chap_mutual_password = ''

    _exports_save_config()


def block_pools(req):
    results = []

    for pool in pools:
            with vgopen(pool) as vg:
                results.append(dict(name=vg.getName(), size=vg.getSize(),
                                    free_size=vg.getFreeSize(), type='block',
                                    uuid=vg.getUuid()))

    return results
