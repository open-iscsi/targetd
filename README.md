targetd
=======

Remote configuration of a LIO-based storage appliance
-----------------------------------------------------
targetd turns Linux into a remotely-configurable storage appliance. It
supports an HTTP/jsonrpc-2.0 interface to let a remote administrator
allocate volumes from an LVM volume group, and export those volumes
over iSCSI.

Current Status
--------------
targetd is pre-alpha, and contributions are welcome! It is licensed
under the GPLv3. Please use target-devel@vger.kernel.org for
discussion. Source repo and bug tracking is at
https://github.com/agrover/targetd.

**NOTE: targetd is PRE-ALPHA, STORAGE-RELATED software. Do NOT use
  around valuable data!**

Getting Started
---------------
targetd has these Python library dependencies:
* [python-rtslib](https://github.com/agrover/rtslib-fb) 2.1.fb14+  (must be fb*)
* [python-lvm](https://github.com/agrover/python-lvm) 1.2.2+
* [python-setproctitle](https://github.com/dvarrazzo/py-setproctitle)

All of these are available in Fedora Rawhide.

### Configuring targetd

targetd defaults to using the "test" volume group, and username 'foo'
password 'bar' for the HTTP jsonrpc interface. Overrides to these
defaults may be placed in `/etc/target/targetd.json`:

    {
        # this is a comment. comments must be on their own line.
        "pool_name" : "test",
        "user" : "foo",
        "password" : "bar",
        "ssl" : false,
        "target_name" : "iqn.2003-01.org.example.mach1:1234"
    }

Then, run `sudo ./targetd.py`.

