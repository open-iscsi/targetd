#!/bin/bash

clean_up ()
{
    # Try to clean everything up so we can re-run the test during
    # development
    pkill --signal SIGINT targetd || echo "Warning: Unable to end targetd process"
    # Give targetd a moment to stop ...
    sleep 1

    pkill lsmd || echo "Warning: Unable to end lsmd process"

    $COV_CMD report || echo "Warning: Unable to generate report"

    if [ $FEDORA -eq 0 ]; then
        zpool destroy zfs_targetd || echo "Warning: unable to destroy zpool zfs_targetd"
    fi

    umount /mnt/btrfs || echo "Warning: , unable to unmount /mnt/btrfs"
    vgremove -f vg-targetd || echo "Warning: unable to remove VG vg-targetd"
    losetup -D || echo "Warning: Unable to remove all loopback devices"
    rm -f /tmp/block*.img || echo "Warning: error while removing sparse files"
    rm -rf /tmp/libstoragemgmt || echo "Warning: Unable to remove /tmp/libstoragemgmt"

    exit $1
}

# We don't have ZFS in fedora for default repos.
FEDORA=0
if [ -f "/etc/redhat-release" ]; then
    FEDORA=1
fi

if [ $FEDORA -eq 0 ]; then
    pip3 install black || exit 10
    COV_CMD=python3-coverage
else
    COV_CMD=coverage3
fi

# Handle a couple options to allow developers to be more productive in
# their test environment.
SETUP=0
TEARDOWN=0
UNIT_ONLY=0
if [ $# -eq 1 ]; then
    if [ $1 = "setup" ]; then
        SETUP=1
    elif [ $1 = "teardown" ]; then
        TEARDOWN=1
    elif [ $1 = "unit_only" ]; then
        UNIT_ONLY=1
    else
        echo "test.sh [setup|teardown|unit_only] or no args to run tests"
        exit 1
    fi
fi

# Used during development to clean up
if [  $TEARDOWN -eq 1 ]; then
    clean_up 0
fi

# Will use to see how well the test coverage is ...
if [ $FEDORA -eq 0 ]; then
    apt-get install python3-coverage || clean_up 1
else
    # Travis yml file handles dependencies, we will do that
    # here for other.
    dnf install `cat test/fedora_pkgs.txt` -y -q || clean_up 1
fi

mkdir -p /etc/target || clean_up 1
cp test/targetd.yaml /etc/target/ || clean_up 1

# Remove zfs references from config file
if [ $FEDORA -eq 1 ]; then
    sed -e '/zfs_block_pools/ s/^#*/#/' -i /etc/target/targetd.yaml
    sed -e '/fs_pools/ s/^#*/#/' -i /etc/target/targetd.yaml
    echo "fs_pools: [/mnt/btrfs]" >> /etc/target/targetd.yaml
fi

# Needed for NFS functionality
mkdir -p /etc/exports.d || clean_up 1

# We don't place the password into the example yaml to prevent
# people from using it and having it contain a bad password by default
echo "password: targetd" >> /etc/target/targetd.yaml

# We are going to utilize SSL for all tests as users should be using
# it, so make a self signed cert for testing
./test/make_test_cert.sh || clean_up 1

# Create the needed block devices for lvm, btrfs, and zfs for testing
truncate -s 1T /tmp/block1.img || clean_up 1
truncate -s 1T /tmp/block2.img || clean_up 1
truncate -s 1T /tmp/block3.img || clean_up 1

loop1=$(losetup -f --show /tmp/block1.img)
loop2=$(losetup -f --show /tmp/block2.img)
loop3=$(losetup -f --show /tmp/block3.img)

# Create lvm needed parts
vgcreate vg-targetd $loop1 || clean_up 1
lvcreate -L 500G -T vg-targetd/thin_pool || clean_up 1

# Create btrfs
mkfs.btrfs $loop2 || clean_up 1
mkdir -p /mnt/btrfs || clean_up 1
mount $loop2 /mnt/btrfs || clean_up 1

# Create needed zfs
if [ $FEDORA -eq 0 ]; then
    zpool create zfs_targetd $loop3 || clean_up 1
    zfs create zfs_targetd/block_pool || clean_up 1
    zfs create zfs_targetd/fs_pool || clean_up 1
fi

# setup a sample nfs export file for parsing
cp test/targetd_test_parse /tmp/. || clean_up 1
export BASE_NFS_MOUNT="/mnt/nfs_mounts"

if [ $SETUP -eq 1  ]; then
    exit 0
fi

export PYTHONPATH=$(pwd)
export TARGETD_NFS_EXPORT="/tmp/targetd_test_parse"
$COV_CMD run --omit=/usr/lib/python3/* scripts/targetd > /tmp/targetd.log 2>&1 &

sleep 5 || clean_up 1
echo "Dumping targetd output ..."
cat /tmp/targetd.log

echo "Running unit test ..."
test/targetd_test.py -v
rc=$?
if [ $rc -ne 0 ]; then
    echo "Dumping targetd output on unit test error ..."
    cat /tmp/targetd.log
    clean_up $rc
fi

# For local unit test development
if [ $UNIT_ONLY -eq 1 ]; then
    cat /tmp/targetd.log
    clean_up 0
fi


# get/build/run or install libstoragemgmt tests
# Need to update lsm for latest ubuntu
./test/lsm_test.sh

rc=$?
if [ $rc -ne 0 ]; then
    echo "Dumping targetd output on libstoragemgmt error ..."
    cat /tmp/targetd.log
    clean_up $rc
fi

# Run the actual legacy tests which only work with ZFS enabled
if [ $FEDORA -eq 0 ]; then
    echo "Running legacy client test ..."
    python3 client
    rc=$?
    if [ $rc -ne 0 ]; then
        echo "Dumping targetd output on client error ..."
        cat /tmp/targetd.log
        clean_up $rc
    fi
fi

# Make sure we are formatted correctly
echo "Checking code formatting ..."
black -t py36 --check --diff .
rc=$?
if [ $rc -ne 0 ]; then
    echo "Code formatting incorrect, please do $ black -t py36 ."
    chean_up $rc
fi

clean_up 0
