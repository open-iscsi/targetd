#!/bin/bash

# Not finding libStorageMgmt packages, so let download and build.  We should
# try and fix that.

cd /tmp || exit 1

git clone http://github.com/libstorage/libstoragemgmt || exit 1

cd /tmp/libstoragemgmt || exit 1


FEDORA=0
if [ -f "/etc/redhat-release" ]; then
    FEDORA=1
fi


CONNECT="${TARGETD_UT_PROTO:-https}"
echo "CONNECT = $CONNECT"

if [ $FEDORA -eq 0 ]; then

    export DEBIAN_FRONTEND="noninteractive"
    apt-get update
    apt-get install -y tzdata
    ln -fs /usr/share/zoneinfo/GMT /etc/localtime
    dpkg-reconfigure --frontend noninteractive tzdata

    # Get all the needed files
    apt-get install $(cat ./deb_dependency) -y -q || exit 1

    ./autogen.sh || exit 1

    ./configure --without-smispy || exit 1

    V=1 make || exit 1

    # Setup some  symlinks
    # We don't have pywbem available, remove plugin so we don't fail when we test for available plugins
    # Note: we should likely just leverage the make install to custom location to avoid all this.
    rm -rf `pwd`/plugin/smispy_plugin || exit 1
    ln -s `pwd`/plugin `pwd`/python_binding/lsm/plugin  || exit 1
    ln -s `pwd`/tools/lsmcli `pwd`/python_binding/lsm || exit 1
    ln -s `pwd`/python_binding/lsm/.libs/*.so `pwd`/python_binding/lsm/. || exit 1
    ln -s `pwd`/plugin/nfs_plugin/.libs/*.so `pwd`/plugin/nfs_plugin/. || exit 1

    # Make the IPC directory
    mkdir -p /var/run/lsm/ipc || exit 1
    PYENV=`pwd`/python_binding:`pwd`/plugin
    LSMDLOG=/tmp/lsmd.log

    # Start up the daemon
    PYTHONPATH=$PYENV daemon/lsmd -v -d --plugindir `pwd`/plugin > $LSMDLOG 2>&1 &


    # We also may want to test without SSL support
    if [[ "$CONNECT" = "http" ]]; then
        echo "Using NON-ssl URI!"
        PYTHONPATH=$PYENV test/plugin_test.py -v --uri targetd://admin@localhost --password targetd
    else
        PYTHONPATH=$PYENV test/plugin_test.py -v --uri targetd+ssl://admin@localhost?ca_cert_file=/tmp/targetd_cert.pem --password targetd
    fi

else
    systemctl start libstoragemgmt.service

    if [[ "$CONNECT" = "http" ]]; then
        echo "Using NON-ssl URI!"
        python3 test/plugin_test.py.in -v --uri targetd://admin@localhost --password targetd
    else
        python3 test/plugin_test.py.in -v --uri targetd+ssl://admin@localhost?ca_cert_file=/tmp/targetd_cert.pem --password targetd
    fi
fi

rc=$?
if [ $rc -ne 0 ]; then
    echo "Dumping lsmd output on unit test error ..."
    if [ $FEDORA -eq 0 ]; then
        cat $LSMDLOG
    else
        journalctl -b --unit libstoragemgmt.service
    fi
    exit $rc
fi

# Exit success
exit 0

