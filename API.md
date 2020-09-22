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

For file system related operations, the pool refers to a btrfs or zfs mount point.
Each newly created file system is a subvolume on that mount point.

Conventions
-----------
* All sizes are in bytes, and are passed as numbers.
* All names must only contain characters in '[a-z][A-Z][0-9]_-'
* Uuid fields are represented as strings.
* If an error occurs, it will be indicated by returning a jsonrpc
error object with a negative error code. Non-negative error codes
(including 0) are not defined.
* Any call currently not returning anything may start to do so in the future in the
form of returning an object or list of objects.
* Any call that returns an object may extended this object in the future with
additional fields, clients should ignore any fields it does not know of.
* Fields will not be removed or renamed without changing the version.
* Any creating function will at least return the fields necessary for destruction
later on and use the same field names.



Pool operations
---------------
Pools are configured on the host, and are not remotely configurable
via this API.

### `pool_list()`
List all defined pools.

**Returns:**
```yaml
[
   {
      "name":       string,
      "size":       number,
      "free_size":  number,
      "uuid":       string,
      "type":      [block, fs],
   }
]
```
  The `name` specifies the name of the pool to be used during futher
  interaction with the pool. The `size` specifies the total size of
  the volume. `free_size` specifies the amount available. `type`
  specifies the type of pool: `block` pools can be given to `vol_`
  operations, `fs` pools can be given to `fs_` operations.

Volume operations
-----------------

### `vol_list(pool)`
Returns all volume objects contained in a pool.

**Parameters:**
- `pool`(**string**, *mandatory*):\
  The name of the pool to query
  
**Returns:**
```yaml
[
  {
    "name": string,
    "size": number,
    "uuid": string,
  }
]
```
`name` specifies the name of the volume. Volume names may be reused, such
as when a volume is created and then removed. `uuid` specifies the unique
id associated with the volume. When a volume is created with the same name,
the `uuid` would be a different, unique value.

### `vol_create(pool, name, size)`
Creates a new volume with the specified size and name inside the specified pool

**Parameters:**
- `pool`(**string**, *mandatory*):\
  The name of the pool the volume should belong to
- `name`(**string**, *mandatory*):\
  The name of the volume to create
- `size`(**number**, *mandatory*):\
  The size of the volume in bytes

### `vol_destroy(pool, name)`
Removes a volume from a pool. This destroys the backing
data, and the data in the volume is lost even if another volume with
the same name is created.

**Parameters:**
- `pool`(**string**, *mandatory*):\
  The name of the pool where the volume resides
- `name`(**string**, *mandatory*):\
  The name of the volume to delete

### `vol_copy(pool, vol_orig, vol_new)`

Creates a new volume based on an existing volume in a pool. It will
 have the same size and contents as the original but the UUID differs.
 
**Parameters:**
- `pool`(**string**, *mandatory*):\
  The name of the pool where the original volume resides and where
  the new volume will be created
- `vol_orig`(**string**, *mandatory*):\
  The name of the original volume
- `vol_new`(**string**, *mandatory*):\
  The name of the new volume

Export operations
-----------------
Exports make a volume accessible to a remote iSCSI initiator.

### `export_list()`
Returns all existing export objects.

**Returns:**
```yaml
[
  {
    "initiator_wwn": string,
    "lun":           number,
    "vol_name":      string,
    "vol_size":      string,
    "vol_uuid":      string,
    "pool":          string,
  }
]
```
`initiator_wwn` is the iSCSI name (`iqn.*`) of the initiator
with access to the export. `lun` is the SCSI logical unit number the
initiator will see for this export. `vol_name` is the name of the
backing volume. `vol_uuid` and `vol_size` return the unique identifier
and size of the volume. The `pool` attribute is the name of the pool
containing the backing volume.

### `export_create(pool, vol, initiator_wwn, lun)`
Creates an export of volume a volume to the given initiator and maps it to a
 specified logical unit number.
 
**Parameters:**
- `pool`(**string**, *mandatory*):\
  The pool where the volume resides in
- `vol`(**string**, *mandatory*):\
  The name of the volume to export
- `initiator_wwn`(**number**, *mandatory*):\
  The iSCSI name of the initiator
- `lun`(**string**, *mandatory*):\
  The logical unit number to map the volume to

### `export_destroy(pool, vol, initiator_wwn)`
Removes an export of a given volume.

**Parameters**
- `pool`(**string**, *mandatory*):\
  The pool where the volume to unexport resides in
- `vol`(**string**, *mandatory*):\
  The volume to unexport
- `initiator_wwn`(**string**, *mandatory*):\
  The initiator from which to unexport the volume

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

**Parameters:**
 - `standalone_only`(**bool**, *optional*)
 
   If `standalone_only` is True, only return initiator which is not in any
   NodeACLGroup.
   By default, all initiators will be included in result.

**Returns:**

  - ```yaml
    [
        {
            "init_id": string,
            "init_type": string,
        },
    ]
    ```
    The 'init_id' of result is the iSCSI IQN/NAA/EUI address of initiator.
    Example: 'iqn.2000-04.com.example:someone-01'
    The 'init_type' is reserved for future use, currently, it is 'iscsi'.

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
pool is a btrfs or zfs sub volume and new file systems are sub volumes within that
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

### nfs_export_add(host, path, options, chown)
Adds a NFS export given a `host`, export `path` to export, list of `options` and optionally a chown specification.
Options is a list of NFS export options.  Each option can be either a single value
eg. no_root_squash or can be a `key=value` like `sec=sys`. See `man 5 exports` for all available supported options and
the formats supported for `host`. `Chown` follows the chown format of `uid:gid` or simply `uid` in numerical form.

### nfs_export_remove(host, path)
Removes a NFS export given a `host` and an export `path`


