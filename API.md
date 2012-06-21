targetd API, version 0.2
========================

Summary
-------
targetd exposes a remote API for configuring a Linux host to perform a
block-based storage array role. API calls use the jsonrpc-2.0 format
over HTTP. The API optionally also uses SSL for connection encryption,
but does authentication via HTTP Basic auth.

Entities
--------
Raw storage space on the host is a `pool`. From a pool, a volume
`vol` is allocated. A volume is shared with remote hosts via an
`export`. Finally, long-running API calls may return before processing
is complete, and if so will supply an `async` id, which the caller may
use to check the status of the operation.

Conventions
-----------
* All sizes are in bytes, and are passed as numbers.
* Only methods documented as async may return an async id. Async-capable
methods may also complete normally.
* All names must only contain characters in '[a-z][A-Z][0-9]_-'
* If an error occurs, it will be indicated by returning a jsonrpc
error object with a negative error code. Positive error codes indicate
the operation is being completed asynchronously (see below). An error
code of 0 is not defined.


Pool operations
---------------
Pools are configured on the host, and are not remotely configurable
via this API.

### pool_list()
Returns an array of pool objects. Each pool object contains `name`,
`size`, and `free_size` fields.

Volume operations
-----------------

### vol_list(pool)
Returns an array of volume objects in `pool`. Each volume object
contains `name`, `size`, and `UUID` fields.

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
_ASYNC_

Creates a new volume named `vol_new` in `pool` the same size as
`vol_orig` in `pool`, and copies the contents from `vol_orig` into
`vol_new`. `vol_orig` and `vol_new` will have differing UUIDs.

Export operations
-----------------
Exports make a volume accessible to a remote iSCSI initiator.

### export_list()
Returns an array of export objects. Each export object contains
`initiator_wwn`, `lun`, `vol`, and `pool`. `initiator_wwn` is the
iSCSI name (iqn.*) of the initiator with access to the export. `lun`
is the SCSI logical unit number the initiator will see for this
export. `vol` is the name of the backing volume, and `pool` is the
name of the pool containing the backing volume.

### export_create(pool, vol, initiator_wwn, lun)
Creates an export of volume `vol` in pool `pool` to the given
initiator, and maps it to logical unit number `lun`.

### export_destroy(pool, vol, initiator_wwn)
Removes an export of `vol` in `pool` to `initiator_wwn`.

Async method calls
------------------
Operations defined as async that are deemed by targetd to be
long-running may complete the request before processing is
finished. In this case, it will return a jsonrpc error with a positive
nonzero error code. This is the `async_id` for that method's
completion status.

### async_list()
Returns an object mapping currently running `async_id`s to a 2-element
array containing a jsonrpc status code and a percentage complete. The
status code will either be 0 for no error, or a negative number
indicating the error. Percentage complete is an integer from 0 to 100.

If processing for an async operation completes successfully, it will
no longer be listed in the results of async_list.

If processing completes unsuccessfully, the error will be listed in the
results of `async_list` once, and then no longer listed.
