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
