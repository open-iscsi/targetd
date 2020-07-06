#!/bin/bash

# Not finding libStorageMgmt packages, so let download and build.  We should
# try and fix that.

cd /tmp || exit 1

git clone http://github.com/libstorage/libstoragemgmt || exit 1

cd /tmp/libstoragemgmt || exit 1

export DEBIAN_FRONTEND="noninteractive"
apt-get update
apt-get install -y tzdata
ln -fs /usr/share/zoneinfo/GMT /etc/localtime
dpkg-reconfigure --frontend noninteractive tzdata

# Get all the needed files
apt-get install $(cat ./deb_dependency) -y -q || exit 1

./autogen.sh || exit 1

# Not all the libraries for py3 exist
./configure --with-python2 || exit 1

V=1 make || exit 1

# Setup some  symlinks
ln -s `pwd`/plugin `pwd`/python_binding/lsm/plugin  || exit 1
ln -s `pwd`/tools/lsmcli `pwd`/python_binding/lsm || exit 1
ln -s `pwd`/python_binding/lsm/.libs/*.so `pwd`/python_binding/lsm/. || exit 1
ln -s `pwd`/plugin/nfs/.libs/*.so `pwd`/plugin/nfs/. || exit 1

# Make the IPC directory
mkdir -p /var/run/lsm/ipc || exit 1

PYENV=`pwd`/python_binding
LSMDLOG=/tmp/lsmd.log

# Start up the daemon
PYTHONPATH=$PYENV daemon/lsmd -v -d --plugindir `pwd`/plugin > $LSMDLOG 2>&1 &

# Run the client test
PYTHONPATH=$PYENV test/plugin_test.py -v --uri targetd://admin@localhost --password targetd

rc=$?
if [ $rc -ne 0 ]; then
    echo "Dumping lsmd output on unit test error ..."
    cat $LSMDLOG
    exit $rc
fi

# Exit success
exit 0

