#!/bin/bash

mkdir -p /etc/target || exit 1
cp test/targetd.yaml /etc/target/ || exit 1

# Needed for NFS functionality
mkdir -p /etc/exports.d || exit 1

# We don't place the password into the example yaml to prevent
# people from using it and having it contain a bad password by default
echo "password: targetd" >> /etc/target/targetd.yaml

# Create the needed block devices for lvm, btrfs, and zfs for testing
truncate -s 1T /tmp/block1.img || exit 1
truncate -s 1T /tmp/block2.img || exit 1
truncate -s 1T /tmp/block3.img || exit 1

loop1=$(losetup -f --show /tmp/block1.img)
loop2=$(losetup -f --show /tmp/block2.img)
loop3=$(losetup -f --show /tmp/block3.img)

# Create lvm needed parts
vgcreate vg-targetd $loop1 || exit 1
lvcreate -L 500G -T vg-targetd/thin_pool || exit 1

# Create btrfs
mkfs.btrfs $loop2 || exit 1
mkdir -p /mnt/btrfs || exit 1
mount $loop2 /mnt/btrfs || exit 1

# Create needed zfs
zpool create zfs_targetd $loop3 || exit 1
zfs create zfs_targetd/block_pool || exit 1
zfs create zfs_targetd/fs_pool || exit 1

export PYTHONPATH=$(pwd)
python3 scripts/targetd > /tmp/targetd.log 2>&1 &

sleep 5 || exit 1
echo "Dumping targetd output ..."
cat /tmp/targetd.log

# get/buid/run libstoragemgmt tests
./test/lsm_test.sh
rc=$?
if [ $rc -ne 0 ]; then
  echo "Dumping targetd output on libstoragemgmt error ..."
  cat /tmp/targetd.log
  exit $rc
fi

# Run the actual tests, these need work ...
echo "Running client test ..."
python3 client
rc=$?
if [ $rc -ne 0 ]; then
    echo "Dumping targetd output on client error ..."
    cat /tmp/targetd.log
    exit $rc
fi

exit 0
