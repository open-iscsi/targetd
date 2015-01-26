targetd API, version 0.6
========================

Summary
-------
targetd exposes a remote API for configuring a Linux host to perform a
block-based storage array role and a file system storage role. API calls use the
jsonrpc-2.0 format over HTTP, on TCP port 18700. The API optionally uses
TLS for connection encryption, but does authentication via HTTP Basic auth for
both encrypted and non-encrypted connections.

Entities
--------
Raw storage space on the host is a `pool`. From a pool, a volume
`vol` is allocated. A volume is shared with remote hosts via an
`export`.

For file system related operations, the pool refers to a btrfs mount point.
Each newly created file system is a subvolume on that mount point.

Conventions
-----------
* All sizes are in bytes, and are passed as numbers.
* All names must only contain characters in '[a-z][A-Z][0-9]_-'
* Uuid fields are represented as strings.
* If an error occurs, it will be indicated by returning a jsonrpc
error object with a negative error code. Non-negative error codes
(including 0) are not defined.


Pool operations
---------------
Pools are configured on the host, and are not remotely configurable
via this API.

### pool_list()
Returns an array of pool objects. Each pool object contains `name`,
`size`, `free_size`, and `type` fields, and may also contain a 'uuid'
field. The domain of the type field is [block|fs].

Volume operations
-----------------

### vol_list(pool)
Returns an array of volume objects in `pool`. Each volume object
contains `name`, `size`, and `uuid` fields.

Volume names may be reused, such as when a volume is created and then
removed. Another volume could then be created with the same name, but
the new volume's UUID would be a different, unique value.

### vol_create(pool, name, size)
Creates a volume named `name` with size `size` in the pool `pool`.

### vol_destroy(pool, name)
Removes `name` volume from pool `pool`. This destroys the backing
data, and the data in the volume is lost even if another volume with
the same name is created.

### vol_copy(pool, vol_orig, vol_new)

Creates a new volume named `vol_new` in `pool` the same size as
`vol_orig` in `pool`, and copies the contents from `vol_orig` into
`vol_new`. `vol_orig` and `vol_new` will have differing UUIDs.

Export operations
-----------------
Exports make a volume accessible to a remote iSCSI initiator.

### export_list()
Returns an array of export objects. Each export object contains
`initiator_wwn`, `lun`, `vol_name`, `vol_size`, `vol_uuid`, and
`pool`. `initiator_wwn` is the iSCSI name (iqn.*) of the initiator
with access to the export. `lun` is the SCSI logical unit number the
initiator will see for this export. `vol_name` is the name of the
backing volume. `vol_uuid` and `vol_size` return the unique identifier
and size of the volume. The `pool` attribute is the name of the pool
containing the backing volume.

### export_create(pool, vol, initiator_wwn, lun)
Creates an export of volume `vol` in pool `pool` to the given
initiator, and maps it to logical unit number `lun`.

### export_destroy(pool, vol, initiator_wwn)
Removes an export of `vol` in `pool` to `initiator_wwn`.

Initiator operations
--------------------
### initiator_set_auth(initiator_wwn, in_user, in_pass, out_user, out_pass)
Sets the inbound and outbound login credentials for the given
initiator. 'in_user' and 'in_pass' are credentials that the initiator
will use to login to the target and access luns exported by
'export_create'. 'out_user' and 'out_pass' are the credentials the
target will use to authenticate itself back to the initiator.

'initiator_wwn' must be set, but 'in_user', 'in_pass', 'out_user' and
'out_pass' may be 'null'. If either or both of each directions'
parameters are 'null', then authentication is disabled for that
direction.

Calling this method is not required for exports to work. If it is not
called, exports require no authentication.

### initiator_list(standalone_only=False)
List all initiators.
Parameters:
    standalone_only(bool, optional):
    If 'standalone_only' is True, only return initiator which is not in any
    NodeACLGroup.
    By default, all initiators will be included in result.
Returns:
    [
        {
            'init_id': str,
            'init_type': str,
        },
    ]
    The 'init_id' of result is the iSCSI IQN/NAA/EUI address of initiator.
    Example: 'iqn.2000-04.com.example:someone-01'
    The 'init_type' is reserved for future use, currently, it is 'iscsi'.

Errors:
    N/A

Access Group operations
-----------------------
Access Group is a group of initiators which sharing the same volume mapping
status.

### access_group_list()
List all access groups.

Parameters:
    N/A
Returns:
    [
        {
            'name': str
            'init_ids': list(str),
            'init_type': str,
        },
    ]
    The 'name' is the name of acccess group.
    The 'init_ids' of result is the iSCSI IQN/NAA/EUI address of initiators
    which belong to current access group.
    Example: ['iqn.2000-04.com.example:someone-01']
    The 'init_type' is reserved for future use, currently, it is 'iscsi'.

Errors:
    N/A

### access_group_create(ag_name, init_id, init_type)
Create new access group.

Parameters:
    ag_name (str): Access group name
    init_id (str): iSCSI initiator address
    init_type (str): Reserved for future use. Should be set as 'iscsi'
Returns:
    N/A
Errors:
    -32602: Invalid parameter. Provided 'ag_name' is illegal. Check
            'Conventions' for detail.
    -153:   No support. The 'init_type' is not 'iscsi'
    -50:    Name conflict. Requested 'ag_name' is in use
    -52:    Exists initiator. Requested 'init_id' is in use

### access_group_destroy(ag_name)
Delete a access group including it's initiator and volume masking status.
No error will be raised even provided access group name does not exist.
Parameters:
    ag_name (str): Access group name
Returns:
    N/A
Errors:
    N/A

### access_group_init_add(ag_name, init_id, init_type)
Add a new initiator into a access group.
If defined access group does not exist, create one with requested initiator.
Parameters:
    ag_name (str): Access group name
    init_id (str): iSCSI initiator address
    init_type (str): Reserved for future use. Should be set as 'iscsi'
Returns:
    N/A
Errors:
    -52:    Exists initiator. Requested 'init_id' is in use

### access_group_init_del(ag_name, init_id, init_type)
Remove a initiator from an access group.
If requested initiator not in defined access group, return silently.
If defined access group does not exist, return silently.
Parameters:
    ag_name (str): Access group name
    init_id (str): iSCSI initiator address
    init_type (str): Reserved for future use. Should be set as 'iscsi'
Returns:
    N/A
Errors:
    N/A

### access_group_map_list()
Query volume mapping status of all access groups.
Parameters:
    N/A
Returns:
    [
        {
            'ag_name': str,
            'h_lun_id': int,
            'pool_name': str,
            'vol_name': str,
        }
    ]
    The 'ag_name' is the name of access group.
    The 'h_lun_id' is the SCSI LUN ID seen by iSCSI initiator.
    The 'pool_name' is the name of pool which volume is belonging to.
    The 'vol_name' is the name of volume.
Errors:
    N/A

### access_group_map_create(pool_name, vol_name, ag_name, h_lun_id=None)
Grant certain access group the rw access to defined volume.
Parameters:
    pool_name (str): The name of pool which defined volume belongs to.
    vol_name (str): The name of volume.
    ag_name (str): Access group name
    h_lun_id (int, optional):
        Host LUN ID (the SCSI LUN ID seen by iSCSI initiator).
        Range is 0 to 255.
        If not defined, targetd will try to find the next available one.
Returns:
    N/A
Errors:
    -1000:  No free host_lun_id. LUN ID between 0 ~ 255 is in use.
    -200:   Access group not found.

### access_group_map_destroy(pool_name, vol_name, ag_name)
Revoke the rw access of certain access group to defined volume.
Parameters:
    pool_name (str): The name of pool which defined volume belongs to.
    vol_name (str): The name of volume.
    ag_name (str): Access group name
Returns:
    N/A
Errors:
    N/A

File system operations
----------------------
Ability to create different file systems and perform operation on them.  The
pool is a btrfs sub volume and new file systems are sub volumes within that
sub volume.

### fs_list()
Returns an array of file system objects.  Each file system object contains:
`name`, `uuid`, `total_space`, `free_space` and `pool` they were created from.

### fs_destroy(uuid)
Destroys the sub volume identified by file system `uuid` and any snapshots
created from it.

### fs_create(pool_name, name, size_bytes)
Create a new sub volume within the specified `pool_name` with the new `name`.
The parameter `size_bytes` is currently ignored, but will eventually be used
to set the quota for the sub volume.

### fs_clone(fs_uuid, dest_fs_name, snapshot_id)
Create a read/write-able copy of the file system with uuid `fs_uuid` to the new
name of `dest_fs_name`.  If `snapshot_id` is specified the new file system
contents will be created from the snapshot copy.

### ss_list(fs_uuid)
Returns an array of read only snapshot objects for the file system specified in
`fs_uuid`.  The returned objects contain: `name`, `uuid`, `timestamp`.  Time
stamp is when the snapshot was taken and it is represented as seconds from epoch.

### fs_snapshot(fs_uuid, dest_ss_name)
Creates a read only copy of the file system specified by `fs_uuid`.  The new
file system has the name represented by `dest_ss_name`.

### fs_snapshot_delete(fs_uuid, ss_uuid)
Deletes the read only snapshot specified by `fs_uuid` and `ss_uuid`.

NFS Export operations
----------------------
### nfs_export_auth_list()
Returns an array of supported NFS client authentication mechanisms.

### nfs_export_list()
Returns an array of export objects.  Each export object contains: `host`, `path`, `options`.

### nfs_export_add(host, path, options)
Adds a NFS export given a `host`, and an export `path` to export and a list of `options`
Options is a list of NFS export options.  Each option can be either a single value
eg. no_root_squash or can be a `key=value` like `sec=sys`.  See `man 5 exports` for all available
supported options and the formats supported for `host`.

### nfs_export_remove(host, path)
Removes a NFS export given a `host` and an export `path`


Async method calls
------------------
Obsolete, no longer defined.
