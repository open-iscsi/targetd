Remote configuration of a "Konnector" storage appliance.

"Konnector" storage nodes "import" storage from a fabric (iSCSI, iSER, SAS or FC) and use that storage to create MD RAID and LVM Volumes.

This project will use targetd as a template, as targetd already has components that can be reused for this Konnector project, namely the jsonrpc-2.0 API as well as the LVM management.

targetd's API will be extended to handle LVM PV/VG creation as well as for iSCSI storage to be connected.
