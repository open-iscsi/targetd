Remote configuration of a "Konnector" storage appliance
=======================================================

"Konnector" storage nodes "import" storage from a fabric (iSCSI, iSER, SAS or FC) and use that storage to create MD RAID and LVM Volumes.

This project is a fork of Andy Grover's targetd and adds iscsi initiator management functionality.

Getting Started
---------------
-----
The following dependencies are required : 
- [rtslib-fb](https://github.com/agrover/rtslib-fb)
- [py-setproctitle](https://github.com/dvarrazzo/py-setproctitle)
- [PyYAML](http://pyyaml.org/)
- [lvm2](https://sourceware.org/lvm2/)

## Installing dependencies

#### rtslib-fb
```py
$ pip-3.2 install rtslib-fb
```

#### py-setproctitle
```py
$ pip install setproctitle
```

#### PyYAML
```py
$ pip install PyYAML
```

#### lvm2
To install lvm2, preferably use your distribution package manager to install lvm2-python-libs. Several distributions do not have the package (e.g. Ubuntu), so you can install it manually as follow.
```py
$ git clone git://git.fedorahosted.org/git/lvm2.git
$ cd lvm2

/lvm2$ apt-get install thin-provisioning-tools
/lvm2$ apt-get install python-dev
/lvm2$ ./configure --enable-python_bindings --enable-applib

/lvm2$ make
/lvm2$ make install
/lvm2$ cd /usr/lib/python2.7/site-packages/
/usr/lib/python2.7/site-packages$ mv lvm.so ../dist-packages 
/usr/lib/python2.7/site-packages$ cd
```

How to install Konnector
------------------------

```py
$ git clone https://github.com/MPSTOR/targetd.git
$ cd targetd
/targetd$ python setup.py install
```

A configuration file may be placed at `/etc/target/targetd.yaml`, and is in YAML format. Here's an example:

    user: "foo" # strings quoted, or not
    password: bar
    ssl: false
    target_name: iqn.2003-01.org.example.mach1:1234

    block_pools: []
    fs_pools: []
targetd defaults to using the username 'admin'. The admin password does not have a default -- each installation must set it.

Use the following instructions to move and edit your configuration file:
```py
/targetd$ mv targetd.yaml /etc/target
/targetd$ vi /etc/target/targetd.yaml
```

Setting "fs_pool" in the config to one or more paths require them to match formatted btrfs mount point, else Konnector will not start and throw an error.

```py
$ cd
```

**Run Konnector**
```py
$ targetd
```

**To run unit tests**
```py
$ py.test -q tests/test_iscsi_init.py -vv
```
