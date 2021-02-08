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

from rtslib_fb import (Target, TPG, NodeACL, FabricModule, BlockStorageObject,
                       RTSRoot, NetworkPortal, LUN, MappedLUN, RTSLibError,
                       RTSLibNotInCFS, NodeACLGroup)

from targetd.backends import lvm, zfs
from targetd.main import TargetdError
from targetd.utils import ignored, name_check

# Handle changes in rtslib_fb for the constant expressing maximum LUN number
# https://github.com/open-iscsi/rtslib-fb/commit/20a50d9967464add8d33f723f6849a197dbe0c52
try:
    MAX_LUN = LUN.MAX_LUN
except AttributeError:
    # Library no longer exposes iSCSI limitation which we're limited too.
    MAX_LUN = 256


def set_portal_addresses(tpg):
    for a in addresses:
        NetworkPortal(tpg, a)


pools = {
    "zfs": [],
    "lvm": []
}
pool_modules = {
    "zfs": zfs,
    "lvm": lvm
}
target_name = ""
addresses = []


def pool_module(pool_name):
    for modname, mod in pool_modules.items():
        if mod.has_pool(pool_name):
            return mod
    raise TargetdError(TargetdError.INVALID_POOL,
                       "Invalid pool (%s)" % pool_name)


def udev_path_module(udev_path):
    for modname, mod in pool_modules.items():
        if mod.has_udev_path(udev_path):
            return mod
    raise TargetdError(TargetdError.INVALID_POOL,
                       "Pool not found by udev path (%s)" % udev_path)


def so_name_module(so_name):
    for modname, mod in pool_modules.items():
        if mod.has_so_name(so_name):
            return mod
    raise TargetdError(TargetdError.INVALID_POOL,
                       "Pool not found by storage object (%s)" % so_name)


#
# config_dict must include block_pools and target_name or we blow up
#
def initialize(config_dict):
    global pools
    pools["lvm"] = list(config_dict['block_pools'])
    pools["zfs"] = list(config_dict['zfs_block_pools'])

    global target_name
    target_name = config_dict['target_name']

    global addresses
    addresses = config_dict['portal_addresses']

    if any(i in pools['zfs'] for i in pools['lvm']):
        raise TargetdError(TargetdError.INVALID,
                           "Conflicting names in zfs_block_pools and block_pools in config.")

    # initialize and check both pools
    for modname, mod in pool_modules.items():
        mod.initialize(config_dict, pools[modname])

    return dict(
        vol_list=volumes,
        vol_create=create,
        vol_destroy=destroy,
        vol_copy=copy,
        vol_resize=resize,
        export_list=export_list,
        export_create=export_create,
        export_destroy=export_destroy,
        initiator_set_auth=initiator_set_auth,
        initiator_list=initiator_list,
        access_group_list=access_group_list,
        access_group_create=access_group_create,
        access_group_destroy=access_group_destroy,
        access_group_init_add=access_group_init_add,
        access_group_init_del=access_group_init_del,
        access_group_map_list=access_group_map_list,
        access_group_map_create=access_group_map_create,
        access_group_map_destroy=access_group_map_destroy,
    )


def volumes(req, pool):
    return pool_module(pool).volumes(req, pool)


def check_vol_exists(req, pool, name):
    mod = pool_module(pool)
    if any(v['name'] == name for v in mod.volumes(req, pool)):
        return True
    return False


def create(req, pool, name, size):
    mod = pool_module(pool)
    # Check to ensure that we don't have a volume with this name already,
    # lvm/zfs will fail if we try to create a LV/dataset with a duplicate name
    if check_vol_exists(req, pool, name):
        raise TargetdError(TargetdError.NAME_CONFLICT,
                           "Volume with that name exists")
    mod.create(req, pool, name, size)


def get_so_name(pool, volname):
    return pool_module(pool).get_so_name(pool, volname)


def destroy(req, pool, name):
    mod = pool_module(pool)
    if not check_vol_exists(req, pool, name):
        raise TargetdError(TargetdError.NOT_FOUND_VOLUME,
                           "Volume %s not found in pool %s" % (name, pool))

    with ignored(RTSLibNotInCFS):
        fm = FabricModule('iscsi')
        t = Target(fm, target_name, mode='lookup')
        tpg = TPG(t, 1, mode='lookup')

        so_name = get_so_name(pool, name)

        if so_name in (lun.storage_object.name for lun in tpg.luns):
            raise TargetdError(TargetdError.VOLUME_MASKED,
                               "Volume '%s' cannot be "
                               "removed while exported" % name)

    mod.destroy(req, pool, name)


def copy(req, pool, vol_orig, vol_new, size=None, timeout=10):
    mod = pool_module(pool)
    if not check_vol_exists(req, pool, vol_orig):
        raise TargetdError(TargetdError.NOT_FOUND_VOLUME,
                           "Volume %s not found in pool %s" % (vol_orig, pool))

    if size is not None:
        for v in mod.volumes(req, pool):
            if v['name'] == vol_orig and v['size'] >= size:
                raise TargetdError(TargetdError.INVALID,
                                   "Size %d need a larger than size in original volume %s in pool %s" % (size,
                                                                                                         vol_orig,
                                                                                                         pool))

    mod.copy(req, pool, vol_orig, vol_new, size, timeout)


def resize(req, pool, name, size):
    mod = pool_module(pool)
    if not check_vol_exists(req, pool, name):
        raise TargetdError(TargetdError.NOT_FOUND_VOLUME,
                           "Volume %s not found in pool %s" % (name, pool))

    for v in mod.volumes(req, pool):
        if v['name'] == name and v['size'] >= size:
            raise TargetdError(TargetdError.INVALID_ARGUMENT,
                               "Size %d need a larger than size in original volume %s in pool %s" % (size,
                                                                                                     name,
                                                                                                     pool))

    mod.resize(req, pool, name, size)


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
            mod = udev_path_module(mlun.tpg_lun.storage_object.udev_path)
            mlun_pool, mlun_name = \
                mod.split_udev_path(mlun.tpg_lun.storage_object.udev_path)
            vinfo = mod.vol_info(mod.dev2pool_name(mlun_pool), mlun_name)
            exports.append(
                dict(
                    initiator_wwn=na.node_wwn,
                    lun=mlun.mapped_lun,
                    vol_name=mlun_name,
                    pool=mod.dev2pool_name(mlun_pool),
                    vol_uuid=vinfo.uuid,
                    vol_size=vinfo.size))
    return exports


def export_create(req, pool, vol, initiator_wwn, lun):
    fm = FabricModule('iscsi')
    t = Target(fm, target_name)
    tpg = TPG(t, 1)
    tpg.enable = True
    tpg.set_attribute("authentication", '0')

    set_portal_addresses(tpg)

    na = NodeACL(tpg, initiator_wwn)

    tpg_lun = _tpg_lun_of(tpg, pool, vol)

    # only add mapped lun if it doesn't exist
    for tmp_mlun in tpg_lun.mapped_luns:
        if tmp_mlun.mapped_lun == lun and tmp_mlun.parent_nodeacl == na:
            break
    else:
        MappedLUN(na, lun, tpg_lun)

    RTSRoot().save_to_file()


def export_destroy(req, pool, vol, initiator_wwn):
    mod = pool_module(pool)
    fm = FabricModule('iscsi')
    t = Target(fm, target_name)
    tpg = TPG(t, 1)
    na = NodeACL(tpg, initiator_wwn)

    pool_dev_name = mod.pool2dev_name(pool)

    for mlun in na.mapped_luns:
        # all SOs are Block so we can access udev_path safely
        if mod.has_udev_path(mlun.tpg_lun.storage_object.udev_path):
            mlun_vg, mlun_name = \
                mod.split_udev_path(mlun.tpg_lun.storage_object.udev_path)

            if mlun_vg == pool_dev_name and mlun_name == vol:
                tpg_lun = mlun.tpg_lun
                mlun.delete()
                # be tidy and delete unused tpg lun mappings?
                if not any(tpg_lun.mapped_luns):
                    so = tpg_lun.storage_object
                    tpg_lun.delete()
                    so.delete()
                break
    else:
        raise TargetdError(TargetdError.NOT_FOUND_VOLUME_EXPORT,
                           "Volume '%s' not found in %s exports" %
                           (vol, initiator_wwn))

    # Clean up tree if branch has no leaf
    if not any(na.mapped_luns):
        na.delete()
        if not any(tpg.node_acls):
            tpg.delete()
            if not any(t.tpgs):
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

    for modname, mod in pool_modules.items():
        results += mod.block_pools(req)

    return results


def _get_iscsi_tpg():
    fabric_module = FabricModule('iscsi')
    target = Target(fabric_module, target_name)
    return TPG(target, 1)


def initiator_list(req, standalone_only=False):
    """Return a list of initiator

    Iterate all iSCSI rtslib-fb.NodeACL via rtslib-fb.TPG.node_acls().
    Args:
        req (TargetHandler):  Reserved for future use.
        standalone_only (bool):
            When standalone_only is True, only return initiator which is not
            in any NodeACLGroup (NodeACL.tag is None).
    Returns:
        [
            {
                'init_id':  NodeACL.node_wwn,
                'init_type': 'iscsi',
            },
        ]

        Currently, targetd only support iscsi which means 'init_type' is
        always 'iscsi'.
    Raises:
        N/A
    """

    def _condition(node_acl, _standalone_only):
        if _standalone_only and node_acl.tag is not None:
            return False
        else:
            return True

    return list({
                    'init_id': node_acl.node_wwn,
                    'init_type': 'iscsi'
                } for node_acl in _get_iscsi_tpg().node_acls
                if _condition(node_acl, standalone_only))


def access_group_list(req):
    """Return a list of access group

    Iterate all iSCSI rtslib-fb.NodeACLGroup via rtslib-fb.TPG.node_acls().
    Args:
        req (TargetHandler):  Reserved for future use.
    Returns:
        [
            {
                'name':     str,
                'init_ids':  list(str),
                'init_type': 'iscsi',
            },
        ]
        Currently, targetd only support iscsi which means init_type is always
        'iscsi'.
    Raises:
        N/A
    """
    return list({
                    'name': node_acl_group.name,
                    'init_ids': list(node_acl_group.wwns),
                    'init_type': 'iscsi',
                } for node_acl_group in _get_iscsi_tpg().node_acl_groups)


def access_group_create(req, ag_name, init_id, init_type):
    if init_type != 'iscsi':
        raise TargetdError(TargetdError.NO_SUPPORT, "Only support iscsi")

    name_check(ag_name)

    tpg = _get_iscsi_tpg()

    # Pre-check:
    #   1. Name conflict: requested name is in use
    #   2. Initiator conflict:  request initiator is in use

    for node_acl_group in tpg.node_acl_groups:
        if node_acl_group.name == ag_name:
            raise TargetdError(TargetdError.NAME_CONFLICT,
                               "Requested access group name is in use")

    if init_id in list(i.node_wwn for i in tpg.node_acls):
        raise TargetdError(TargetdError.EXISTS_INITIATOR,
                           "Requested init_id is in use")

    node_acl_group = NodeACLGroup(tpg, ag_name)
    node_acl_group.add_acl(init_id)
    RTSRoot().save_to_file()


def access_group_destroy(req, ag_name):
    NodeACLGroup(_get_iscsi_tpg(), ag_name).delete()
    RTSRoot().save_to_file()


def access_group_init_add(req, ag_name, init_id, init_type):
    if init_type != 'iscsi':
        raise TargetdError(TargetdError.NO_SUPPORT, "Only support iscsi")

    tpg = _get_iscsi_tpg()
    # Pre-check:
    #   1. Already in requested access group, return silently.
    #   2. Initiator does not exist.
    #   3. Initiator not used by other access group.

    if init_id in list(NodeACLGroup(tpg, ag_name).wwns):
        return

    for node_acl_group in tpg.node_acl_groups:
        if init_id in list(node_acl_group.wwns):
            raise TargetdError(
                TargetdError.EXISTS_INITIATOR,
                "Requested init_id is used by other access group")
    for node_acl in tpg.node_acls:
        if init_id == node_acl.node_wwn:
            raise TargetdError(TargetdError.EXISTS_INITIATOR,
                               "Requested init_id is in use")

    NodeACLGroup(tpg, ag_name).add_acl(init_id)
    RTSRoot().save_to_file()


def access_group_init_del(req, ag_name, init_id, init_type):
    if init_type != 'iscsi':
        raise TargetdError(TargetdError.NO_SUPPORT, "Only support iscsi")

    tpg = _get_iscsi_tpg()

    # Pre-check:
    #   1. Initiator is not in requested access group, return silently.
    if init_id not in list(NodeACLGroup(tpg, ag_name).wwns):
        return

    NodeACLGroup(tpg, ag_name).remove_acl(init_id)
    RTSRoot().save_to_file()


def access_group_map_list(req):
    """
    Return a list of dictionaries in this format:
        {
            'ag_name': ag_name,
            'h_lun_id': h_lun_id,   # host side LUN ID
            'pool_name': pool_name,
            'vol_name': vol_name,
        }
    """
    results = []
    tpg = _get_iscsi_tpg()

    for node_acl_group in tpg.node_acl_groups:
        for mapped_lun_group in node_acl_group.mapped_lun_groups:
            tpg_lun = mapped_lun_group.tpg_lun
            so_name = tpg_lun.storage_object.name
            mod = so_name_module(so_name)
            pool_name, vol_name = mod.so_name2pool_volume(so_name)

            # When user delete old volume and the created new one with
            # idential name. The mapping status will be kept.
            # Hence we don't expose volume UUID here.
            results.append({
                'ag_name': node_acl_group.name,
                'h_lun_id': mapped_lun_group.mapped_lun,
                'pool_name': pool_name,
                'vol_name': vol_name,
            })

    return results


def _tpg_lun_of(tpg, pool_name, vol_name):
    """
    Return a object of LUN for given pool and volume.
    If not exist, create one.
    """
    mod = pool_module(pool_name)
    # get wwn of volume so LIO can export as vpd83 info
    vol_serial = mod.vol_info(pool_name, vol_name).uuid

    # only add new SO if it doesn't exist
    # so.name concats pool & vol names separated by ':'
    so_name = mod.get_so_name(pool_name, vol_name)
    try:
        so = BlockStorageObject(so_name)
    except RTSLibError:
        so = BlockStorageObject(
            so_name, dev=mod.get_dev_path(pool_name, vol_name))
        so.wwn = vol_serial

    # export useful scsi model if kernel > 3.8
    with ignored(RTSLibError):
        so.set_attribute("emulate_model_alias", '1')

    # only add tpg lun if it doesn't exist
    for tmp_lun in tpg.luns:
        if tmp_lun.storage_object.name == so.name and \
                tmp_lun.storage_object.plugin == 'block':
            return tmp_lun
    else:
        return LUN(tpg, storage_object=so)


def access_group_map_create(req, pool_name, vol_name, ag_name, h_lun_id=None):
    tpg = _get_iscsi_tpg()
    tpg.enable = True
    tpg.set_attribute("authentication", '0')

    set_portal_addresses(tpg)

    tpg_lun = _tpg_lun_of(tpg, pool_name, vol_name)

    # Pre-Check:
    #   1. Already mapped to requested access group, return None
    if any(tpg_lun.mapped_luns):
        tgt_map_list = access_group_map_list(req)
        for tgt_map in tgt_map_list:
            if tgt_map['ag_name'] == ag_name and \
                    tgt_map['pool_name'] == pool_name and \
                    tgt_map['vol_name'] == vol_name:
                # Already masked.
                return None

    node_acl_group = NodeACLGroup(tpg, ag_name)
    if not any(node_acl_group.wwns):
        # Non-existent access group means volume mapping status will not be
        # stored. This should be considered as an error instead of silently
        # returning.
        raise TargetdError(TargetdError.NOT_FOUND_ACCESS_GROUP,
                           "Access group not found")

    if h_lun_id is None:
        # Find out next available host LUN ID
        # Assuming max host LUN ID is MAX_LUN
        free_h_lun_ids = set(range(MAX_LUN + 1)) - \
                         set([int(x.mapped_lun) for x in tpg_lun.mapped_luns])
        if len(free_h_lun_ids) == 0:
            raise TargetdError(TargetdError.NO_FREE_HOST_LUN_ID,
                               "All host LUN ID 0 ~ %d is in use" % MAX_LUN)
        else:
            h_lun_id = free_h_lun_ids.pop()

    node_acl_group.mapped_lun_group(h_lun_id, tpg_lun)
    RTSRoot().save_to_file()


def access_group_map_destroy(req, pool_name, vol_name, ag_name):
    tpg = _get_iscsi_tpg()
    node_acl_group = NodeACLGroup(tpg, ag_name)
    tpg_lun = _tpg_lun_of(tpg, pool_name, vol_name)
    for map_group in node_acl_group.mapped_lun_groups:
        if map_group.tpg_lun == tpg_lun:
            map_group.delete()

    if not any(tpg_lun.mapped_luns):
        # If LUN is not masked to any access group or initiator
        # remove LUN instance.
        lun_so = tpg_lun.storage_object
        tpg_lun.delete()
        lun_so.delete()

    RTSRoot().save_to_file()
