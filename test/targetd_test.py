#!/usr/bin/python3

import unittest
import json
import random
import time
import string
from targetd.utils import TargetdError
from os import getenv
from requests.exceptions import ConnectionError
from test import testlib
from targetd import nfs
from multiprocessing.pool import ThreadPool


def jsonrequest(method, params=None, data=None):
    return testlib.rpc(method, params, data)


def _rs(length):
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(length))


def r_iqn():
    return 'iqn.1994-05.com.domain:01.' + _rs(6)


def rs(prefix="td", length=4):
    """
    Generate a random string with optional prefix
    """
    rp = _rs(length)

    if prefix is not None:
        return '%s_%s' % (prefix, rp)
    return rp


class TargetdObj(object):

    @staticmethod
    def build(objhash):
        o = TargetdObj()
        o.rpc = objhash
        return o

    def __getattr__(self, k):
        if k in self.rpc:
            if k in ['size', 'free_size']:
                return int(self.rpc[k])
            return self.rpc[k]
        # Not present for FS pools
        if k == "uuid":
            return None
        else:
            raise AttributeError(
                "'TargetdObj' object %s has no attribute '%s'" %
                (str(self), k))

    def __str__(self):
        s = ""
        for k, v in self.rpc.items():
            s += "%s: %s " % (k, v)
        return s


class NoDaemon(unittest.TestCase):

    def test_gp_nfs_export_parse(self):
        # sample taken from "man 5 exports"
        sample = "# sample /etc/exports file\n" \
               "/           master(rw) trusty(rw,no_root_squash)\n" \
               "/projects   proj*.local.domain(rw)\n" \
               "/usr        *.local.domain(ro) @trusted(rw)\n" \
               "/home/joe   pc001(rw,all_squash,anonuid=150,anongid=100)\n" \
               "/pub        *(ro,insecure,all_squash)\n" \
               "/srv/www    -sync,rw server @trusted @external(ro)\n" \
               "/foo        2001:db8:9:e54::/64(rw) 192.0.2.0/24(rw)\n" \
               "/build      buildhost[0-9].local.domain(rw)\n"

        with open("/tmp/sample", "w") as f:
            f.write(sample)

        result = nfs.Export.parse_exports_file("/tmp/sample")
        self.assertGreater(len(result), 1)

    def test_ep_export(self):
        self.assertRaises(ValueError, nfs.Export,
                          "localhost", "/mnt/foo",
                          nfs.Export.RW | nfs.Export.RO)
        self.assertRaises(ValueError, nfs.Export,
                          "localhost", "/mnt/foo",
                          nfs.Export.INSECURE | nfs.Export.SECURE)
        self.assertRaises(ValueError, nfs.Export,
                          "localhost", "/mnt/foo",
                          nfs.Export.SYNC | nfs.Export.ASYNC)
        self.assertRaises(ValueError, nfs.Export,
                          "localhost", "/mnt/foo",
                          nfs.Export.HIDE | nfs.Export.NOHIDE)

    def test_gp_export_compare(self):
        i1 = nfs.Export("localhost", "/mnt/foo", nfs.Export.RW)
        i2 = nfs.Export("localhost", "/mnt/foo", nfs.Export.RO)
        self.assertTrue(i1 == i2)

        i3 = nfs.Export("127.0.0.1", "/mnt/foo", nfs.Export.RO)
        self.assertTrue(i2 != i3)


class TestConnect(unittest.TestCase):

    def _test_ep_bad_auth(self, username=True):

        existing_user = testlib.user
        existing_pw = testlib.password

        if username:
            testlib.user = rs(length=10)
        else:
            testlib.password = rs(length=10)

        error_code = 0
        start = time.time()
        try:
            jsonrequest("pool_list")
        except TargetdError as e:
            error_code = e.error
        finally:
            end = time.time()
            testlib.user = existing_user
            testlib.password = existing_pw

        self.assertEqual(error_code, 401, "testing bad auth.")
        self.assertGreaterEqual(end-start, 1, "Expecting delayed response")

    def test_ep_bad_auth(self):
        self._test_ep_bad_auth()
        self._test_ep_bad_auth(False)

    def test_ep_concurrent_authentication(self):
        pool = ThreadPool(processes=4)

        results = []

        for _ in range(4):
            results.append(pool.apply_async(testlib.test_bad_authenticate))

        start = time.time()
        for r in results:
            exception, result = r.get()
            if exception:
                pass
            else:
                self.assertTrue((result.status_code == 401 or
                                 result.status_code == 503))
        end = time.time()
        diff = end - start
        self.assertTrue((diff > 1 or diff < 3), "Not expected %s" % (str(diff)))

        pool.close()

    def test_ep_bad_path(self):

        existing = testlib.rpc_path
        bad_path = "/" + _rs(10)
        testlib.rpc_path = bad_path

        error_code = 0
        try:
            jsonrequest("pool_list")
        except TargetdError as e:
            error_code = e.error
        except ConnectionError:
            # Not sure why the service is responding with a RST when using
            # ssl, works fine without ssl
            error_code = 404
        finally:
            testlib.rpc_path = existing

        self.assertEqual(error_code, 404, "testing bad path %s" % bad_path)

    def test_ep_method_not_found(self):
        error_code = 0
        try:
            jsonrequest("pool_listing")
        except TargetdError as e:
            error_code = e.error

        self.assertEqual(error_code, -32601, "testing method")

    def test_ep_invalid_arg(self):
        error_code = 0
        try:
            jsonrequest("pool_list", dict(foo="bar"))
        except TargetdError as e:
            error_code = e.error

        self.assertEqual(error_code, TargetdError.INVALID_ARGUMENT)

    def test_ep_invalid_json_version(self):
        method = "pool_list"
        params = None

        data = json.dumps(
            dict(id=100,
                 method=method,
                 params=params, jsonrpc="not_a_version")).encode('utf-8')

        error_code = 0
        try:
            jsonrequest(method, params=None, data=data)
        except TargetdError as e:
            error_code = e.error

        self.assertEqual(error_code, -32600)

    def test_ep_invalid_json(self):
        method = "pool_list"
        params = None

        data = json.dumps(
            dict(id=100,
                 method=method,
                 params=params, jsonrpc="2.0")).encode('utf-8')

        self.assertRaises(ConnectionError,
                          jsonrequest,
                          method, params=None, data=data[0:len(data) - 10])

    def test_gp_simple(self):
        # Basic good path
        jsonrequest("pool_list")

    def test_ep_request_too_big(self):
        request = rs(None, 1) * (1024 * 128)
        error_code = 0
        try:
            jsonrequest(request)
        except TargetdError as e:
            error_code = e.error
        except ConnectionError:
            # Not sure why the service is responding with a RST when using
            # ssl, works fine without ssl
            error_code = 413

        self.assertEqual(error_code, 413)


class TestTargetd(unittest.TestCase):

    @staticmethod
    def _pools():
        return [TargetdObj.build(x) for x in jsonrequest("pool_list")]

    @staticmethod
    def _block_pools():
        return [TargetdObj.build(x)
                for x in jsonrequest("pool_list")
                if x['type'] == 'block']

    @staticmethod
    def _vol_create(pool, name, size=1024 * 1024 * 100):
        jsonrequest("vol_create", dict(pool=pool.name, name=name, size=size))
        # just created, get it and return
        return TestTargetd._vol_list(pool, name)[0]

    def _vol_destroy(self, pool, vol):
        jsonrequest("vol_destroy", dict(pool=pool.name, name=vol.name))
        missing_volume = TestTargetd._vol_list(pool, vol.name)
        self.assertEqual(len(missing_volume), 0,
                         "Expected destroyed volume to not be in vol_list")

    @staticmethod
    def _vol_copy(pool, vol_orig, vol_new_name, size=None):
        jsonrequest("vol_copy",
                    dict(
                        pool=pool.name,
                        vol_orig=vol_orig.name,
                        vol_new=vol_new_name,
                        size=size))
        return TestTargetd._vol_list(pool, vol_new_name)[0]

    @staticmethod
    def _fs_create(pool, name, size=1024 * 1024 * 100):
        jsonrequest("fs_create",
                    dict(pool_name=pool.name, name=name, size_bytes=size))
        # just created, get it and return
        return TestTargetd._fs_list(name)[0]

    @staticmethod
    def _fs_clone(fs, dest_fs_name, snapshot_id=""):
        args = dict(fs_uuid=fs.uuid, dest_fs_name=dest_fs_name,
                    snapshot_id=snapshot_id)
        jsonrequest("fs_clone", args)
        return TestTargetd._fs_list(dest_fs_name)[0]

    def _fs_snapshot(self, fs, dest_ss_name):
        args = dict(fs_uuid=fs.uuid, dest_ss_name=dest_ss_name)

        # Make sure time stamp makes sense and is reasonably close,
        # we don't want false positives because clocks are slightly off if
        # test and service are on different systems

        delta = int(getenv("TARGETD_UT_CLOCK_DRIFT", 300))
        start = time.time() - delta
        jsonrequest("fs_snapshot", args)
        end = time.time() + delta
        search = TestTargetd._ss_list(fs, dest_ss_name)
        self.assertEqual(len(search), 1,
                         "expecting to find newly created snapshot %s" % fs)
        found = search[0]
        ts = int(found.timestamp)
        self.assertTrue(
            (start <= ts <= end),
            "Snapshot timestamp is out of range? (%d .. %d .. %d)" %
            (start, ts, end))
        return found

    def _fs_destroy(self, fs):
        jsonrequest("fs_destroy", dict(uuid=fs.uuid))
        fs_list = TestTargetd._fs_list()
        matched = [x for x in fs_list if x.uuid == fs.uuid]
        self.assertEqual(len(matched), 0,
                         "Expected destroyed fs to not be in fs_list")

    def _fs_snapshot_delete(self, fs, ss):
        jsonrequest(
            "fs_snapshot_delete", dict(fs_uuid=fs.uuid, ss_uuid=ss.uuid))

        search = TestTargetd._ss_list(fs, ss.name)
        self.assertEqual(len(search), 0,
                         "Expected deleted ss to not be in ss_list %s" % ss)

    @staticmethod
    def _vol_list(pool, name=None):

        vols = [TargetdObj.build(x)
                for x in jsonrequest("vol_list", dict(pool=pool.name))]

        if name:
            return [x for x in vols if x.name == name]
        return vols

    @staticmethod
    def _fs_list(name=None):

        fs = [TargetdObj.build(x)
              for x in jsonrequest("fs_list", dict())]

        if name:
            return [x for x in fs if x.name == name]
        return fs

    @staticmethod
    def _ss_list(fs, name=None):
        ss = [TargetdObj.build(x)
              for x in jsonrequest("ss_list", dict(fs_uuid=fs.uuid))]
        if name:
            return [x for x in ss if x.name == name]
        return ss

    @staticmethod
    def _fs_pools():
        return [TargetdObj.build(x)
                for x in jsonrequest("pool_list")
                if x['type'] == 'fs']

    @staticmethod
    def _initiator_list(standalone=False, wwid=None):
        initiators = [TargetdObj.build(x)
                      for x in jsonrequest("initiator_list",
                                           dict(standalone_only=str(standalone)))]
        if wwid:
            return [x for x in initiators if x.init_id == wwid]
        return initiators

    @staticmethod
    def _export_list(st=None):
        """
        Retrieve export list or constrain to single item.
        :param st: search_tuple (pool_name, vol_name, initiator_wwn, lun)
        :return: list of exports
        """
        exports = [TargetdObj.build(x)
                   for x in jsonrequest("export_list")]

        if st is None:
            return exports
        return [x for x in exports
                if (st[0] == x.pool and st[1] == x.vol_name and
                    st[2] == x.initiator_wwn and st[3] == x.lun)]

    def _export_create(self, pool, vol, initiator_wwn=None, lun=0):

        if initiator_wwn is None:
            initiator_wwn = r_iqn()

        jsonrequest(
            "export_create",
            dict(
                pool=pool.name, vol=vol.name, initiator_wwn=initiator_wwn,
                lun=lun))

        result = TestTargetd._export_list(
            (pool.name, vol.name, initiator_wwn, lun))

        self.assertEqual(len(result), 1,
                         "Expected 1 found export that we just created!")

        initiator = TestTargetd._initiator_list(wwid=initiator_wwn)
        self.assertEqual(len(initiator), 1,
                         "Expected 1 found for initiator list")

        return result[0]

    def _export_destroy(self, export):
        jsonrequest("export_destroy",
                    dict(pool=export.pool,
                         vol=export.vol_name,
                         initiator_wwn=export.initiator_wwn))

        expect_not_found = TestTargetd._export_list(
            (export.pool, export.vol_name, export.initiator_wwn, export.lun))
        self.assertEqual(len(expect_not_found), 0, "expect export gone!")
        initiator = TestTargetd._initiator_list(wwid=export.initiator_wwn)
        self.assertEqual(len(initiator), 0,
                         "Expected 1 found for initiator list")

    @staticmethod
    def _nfs_export_list(st=None):
        """
        Retrieve NFS export list or constrain to single item.
        :param st: search_tuple (host, path, options)
        :return: list of nfs exports
        """
        exports = [TargetdObj.build(x)
                   for x in jsonrequest("nfs_export_list")]

        if st is None:
            return exports
        return [x for x in exports
                if (st[0] == x.host and st[1] == x.path)]

    def _nfs_export_add(self, host, path, options, chown=None):

        answer = TargetdObj.build(jsonrequest(
            "nfs_export_add",
            dict(
                host=host, path=path, options=options, chown=chown)))

        self.assertEqual(answer.host, host)
        self.assertEqual(answer.path, path)

        result = TestTargetd._nfs_export_list(
            (host, path))

        self.assertEqual(len(result), 1,
                         "Expected 1 found export that we just created!")

        return answer

    def _nfs_export_remove(self, host, path):
        """
        Remove a NFS export
        :param host: the host associated with the export
        :param path: the path associated with the export
        :return: None
        """
        jsonrequest("nfs_export_remove",
                    dict(host=host,
                         path=path))

        expect_not_found = TestTargetd._nfs_export_list(
            (host, path))
        self.assertEqual(len(expect_not_found), 0, "expect export gone!")

    def test_gp_pool_list(self):
        p = TestTargetd._pools()

        self.assertGreater(len(p), 0, "Expecting at least 1 pool!")
        for i in p:
            self.assertGreater(len(i.name), 0, "Name should not be empty")
            self.assertGreater(i.size, 0, "Pool size should not be 0")
            self.assertTrue(i.type == 'fs' or i.type == 'block')
            self.assertTrue(i.free_size <= i.size)
            if i.type == 'fs':
                self.assertIsNone(i.uuid,
                                  "file pool have no uuid %s" % i)

    def test_gp_vol_create_copy_destroy_operations(self):
        for block_pool in self._block_pools():
            vol_name = rs(length=6)
            vol_copy_name = vol_name + "_copy"

            # Create a volume, copy it, destroy the copy, destroy original
            vol = TestTargetd._vol_create(block_pool, vol_name)
            vol_copy = TestTargetd._vol_copy(block_pool, vol, vol_copy_name)
            self._vol_destroy(block_pool, vol_copy)
            self._vol_destroy(block_pool, vol)

    def test_ep_copy_missing_volume(self):
        for block_pool in self._block_pools():
            vol_name = rs(length=6)
            vol_copy_name = vol_name + "_copy"

            # Create a volume, copy it, destroy the copy, destroy original
            vol = TestTargetd._vol_create(block_pool, vol_name)

            # Change name
            vol.name = vol.name + "_missing"

            error_code = 0
            try:
                TestTargetd._vol_copy(block_pool, vol, vol_copy_name)
            except TargetdError as e:
                error_code = e.error
            self.assertEqual(error_code, TargetdError.NOT_FOUND_VOLUME)

            # Correct name for deletion
            vol.name = vol_name
            self._vol_destroy(block_pool, vol)

    def test_ep_copy_expand_volume(self):
        for block_pool in self._block_pools():
            vol_name = rs(length=6)
            vol_copy_name = vol_name + "_copy"

            vol = TestTargetd._vol_create(block_pool, vol_name)

            expanded_size = vol.size + 200 * 1024 * 1024
            TestTargetd._vol_copy(block_pool, vol, vol_copy_name, expanded_size)

            vol_copy = TestTargetd._vol_list(block_pool, vol_copy_name)[0]
            self.assertEqual(expanded_size, vol_copy.size)

            vol_copy.name = vol_copy_name
            self._vol_destroy(block_pool, vol_copy)
            vol.name = vol_name
            self._vol_destroy(block_pool, vol)

    def test_gp_export_operations(self):
        exports = TestTargetd._export_list()

        for e in exports:
            # Check search for specific is working
            export = TestTargetd._export_list(
                (e.pool, e.vol_name, e.initiator_wwn, e.lun))
            self.assertEqual(len(export), 1, "expect to find existing export")

        if len(exports) == 0:
            for block_pool in self._block_pools():
                # Create a volume, then export it
                vol = TestTargetd._vol_create(block_pool, rs(length=6))
                export = self._export_create(block_pool, vol)
                self._export_destroy(export)
                self._vol_destroy(block_pool, vol)

    def test_ep_vol_name_collision(self):
        for block_pool in self._block_pools():
            vol_name = "some_block_vol"
            # Make sure we get the expected error for duplicate name during
            # volume creation and volume copy
            vol = TestTargetd._vol_create(block_pool, vol_name)

            error_code = 1
            try:
                TestTargetd._vol_create(block_pool, vol_name)
            except TargetdError as e:
                error_code = e.error
            self.assertTrue(error_code == TargetdError.NAME_CONFLICT,
                            block_pool)

            error_code = 1
            try:
                TestTargetd._vol_copy(block_pool, vol, vol_name)
            except TargetdError as e:
                error_code = e.error

            self.assertTrue(error_code == TargetdError.NAME_CONFLICT,
                            block_pool)

            self._vol_destroy(block_pool, vol)

    def test_ep_non_existent_vol_destroy(self):
        vol = TargetdObj.build(dict(name='no_such_volume_'))
        for block_pool in self._block_pools():
            error_code = 1
            try:
                self._vol_destroy(block_pool, vol)
            except TargetdError as e:
                error_code = e.error
            self.assertEqual(error_code,
                             TargetdError.NOT_FOUND_VOLUME, block_pool)

    def test_ep_non_existent_pool(self):
        pool = TargetdObj.build(dict(name='no_such_pool_'))
        vol = TargetdObj.build(dict(name='no_such_volume_'))
        error_code = 1
        try:
            self._vol_destroy(pool, vol)
        except TargetdError as e:
            error_code = e.error

        self.assertEqual(error_code, TargetdError.INVALID_POOL, pool)

    def test_gp_fs_create_destroy(self):
        for fs_pool in TestTargetd._fs_pools():
            fs = TestTargetd._fs_create(fs_pool, rs(length=10))
            self._fs_destroy(fs)

    def test_ep_fs_destroy(self):
        for fs_pool in TestTargetd._fs_pools():
            fs = TargetdObj.build(dict(uuid="123"))
            error_code = 0
            try:
                self._fs_destroy(fs)
            except TargetdError as e:
                error_code = e.error

            self.assertEqual(error_code, TargetdError.NOT_FOUND_FS, fs_pool)

    def test_ep_fs_dupe(self):
        for fs_pool in TestTargetd._fs_pools():
            name = rs(length=10)
            fs = TestTargetd._fs_create(fs_pool, name)

            error_code = 0
            try:
                self._fs_create(fs_pool, name)
            except TargetdError as e:
                error_code = e.error

            self.assertEqual(error_code, TargetdError.EXISTS_FS_NAME, fs_pool)
            self._fs_destroy(fs)

    def test_gp_fs_clone(self):
        for fs_pool in TestTargetd._fs_pools():
            fs = TestTargetd._fs_create(fs_pool, rs(length=10))
            clone = TestTargetd._fs_clone(fs, rs(length=10) + "_clone")
            self._fs_destroy(clone)
            self._fs_destroy(fs)

    def test_ep_fs_dupe_clone_name(self):
        for fs_pool in TestTargetd._fs_pools():
            fs = TestTargetd._fs_create(fs_pool, rs(length=10))
            name = rs(length=10) + "_clone"
            clone = TestTargetd._fs_clone(fs, name)

            error_code = 0
            try:
                self._fs_clone(fs, name)
            except TargetdError as e:
                error_code = e.error

            self.assertEqual(error_code,
                             TargetdError.EXISTS_CLONE_NAME,
                             fs_pool)

            self._fs_destroy(clone)
            self._fs_destroy(fs)

    def test_ep_fs_clone_bad_source(self):
        for fs_pool in TestTargetd._fs_pools():
            fs = TestTargetd._fs_create(fs_pool, rs(length=10))

            uuid = fs.uuid
            fs.uuid = rs(length=8)

            error_code = 0
            try:
                self._fs_clone(fs, rs(length=8))
            except TargetdError as e:
                error_code = e.error
            finally:
                fs.uuid = uuid

            self.assertEqual(error_code,
                             TargetdError.NOT_FOUND_FS,
                             fs_pool)
            self._fs_destroy(fs)

    def test_gp_fs_snapshot(self):
        for fs_pool in TestTargetd._fs_pools():
            fs = TestTargetd._fs_create(fs_pool, rs(length=10))
            ss = self._fs_snapshot(fs, rs(length=10) + "_ss")
            self._fs_snapshot_delete(fs, ss)
            self._fs_destroy(fs)

    def test_ep_fs_snapshot_not_exist(self):
        for fs_pool in TestTargetd._fs_pools():
            fs = TestTargetd._fs_create(fs_pool, rs(length=10))
            ss = self._fs_snapshot(fs, rs(length=10) + "_ss")

            error_code = 0
            uuid = ss.uuid
            ss.uuid = rs(length=5)
            try:
                self._fs_snapshot_delete(fs, ss)
            except TargetdError as e:
                error_code = e.error
            finally:
                ss.uuid = uuid

            self.assertEqual(error_code, TargetdError.NOT_FOUND_SS)
            self._fs_snapshot_delete(fs, ss)
            self._fs_destroy(fs)

    def test_ep_fs_snapshot_dupe_name(self):
        for fs_pool in TestTargetd._fs_pools():
            fs = TestTargetd._fs_create(fs_pool, rs(length=10))
            ss_name = rs(length=10) + "_ss"
            ss = self._fs_snapshot(fs, ss_name)

            error_code = 0
            try:
                self._fs_snapshot(fs, ss_name)
            except TargetdError as e:
                error_code = e.error

            self.assertEqual(error_code, TargetdError.EXISTS_FS_NAME)

            self._fs_snapshot_delete(fs, ss)
            self._fs_destroy(fs)

    def test_ep_no_such_pool(self):
        error_code = 0
        try:
            jsonrequest(
                "vol_create",
                dict(pool=rs(length=20), name="wont_create",
                     size=1024 * 1024 * 100))
        except TargetdError as e:
            error_code = e.error

        self.assertEqual(error_code, TargetdError.INVALID_POOL)

    def test_ep_no_such_fs_pool(self):
        error_code = 0
        try:
            jsonrequest(
                "fs_create",
                dict(pool_name=rs(length=10), name="whatever",
                     size_bytes=1024 * 1024 * 100))
        except TargetdError as e:
            error_code = e.error

        self.assertEqual(error_code, TargetdError.INVALID_POOL)

    def test_ep_no_such_snapshot(self):
        for fs_pool in TestTargetd._fs_pools():
            fs = TestTargetd._fs_create(fs_pool, rs(length=10))
            ss = self._fs_snapshot(fs, rs(length=10) + "_ss")

            uuid = ss.uuid
            ss.uuid = "NO_SUCH_UUID"

            error_code = 0
            try:
                self._fs_snapshot_delete(fs, ss)
            except TargetdError as e:
                error_code = e.error

            self.assertEqual(
                error_code, TargetdError.NOT_FOUND_SS,
                " fs_snapshot_delete expecting NOT_FOUND_SS when trying to"
                " delete the snapshot with incorrect uuid")

            ss.uuid = uuid
            self._fs_snapshot_delete(fs, ss)
            self._fs_destroy(fs)

    def test_ep_fs_snapshot(self):
        """
        Create a snapshot from a FS and then try to delete the snapshot using
        FS delete instead of SS delete expecting a NOT_FOUND_FS error
        :return: None
        """
        for fs_pool in TestTargetd._fs_pools():
            fs = TestTargetd._fs_create(fs_pool, rs(length=10))
            ss = self._fs_snapshot(fs, rs(length=10) + "_ss")
            # Try to use fs_destroy on a snapshot should fail
            error_code = 0
            try:
                self._fs_destroy(ss)
            except TargetdError as e:
                error_code = e.error
            self.assertEqual(
                error_code, TargetdError.NOT_FOUND_FS,
                "fs_destroy expecting NOT_FOUND_FS when trying to use ss"
                " uuid, fs_pool = %s" % fs_pool.name)

            self._fs_destroy(fs)

    def test_gp_fs_clone_from_snapshot(self):
        for fs_pool in TestTargetd._fs_pools():
            fs = TestTargetd._fs_create(fs_pool, rs(length=10))
            ss = self._fs_snapshot(fs, rs(length=10) + "_ss")
            clone = TestTargetd._fs_clone(fs, rs(length=10) + "_clone", ss.uuid)
            self._fs_destroy(clone)
            self._fs_snapshot_delete(fs, ss)
            self._fs_destroy(fs)

    def test_gp_nfs_export_add(self):
        for fs_pool in TestTargetd._fs_pools():
            fs = TestTargetd._fs_create(fs_pool, rs(length=10))
            export = self._nfs_export_add("0.0.0.0/0", fs.full_path, "insecure")
            self._nfs_export_remove(export.host, export.path)
            self._fs_destroy(fs)

    def test_gp_nfs_export_add_chown_uid(self):
        for fs_pool in TestTargetd._fs_pools():
            fs = TestTargetd._fs_create(fs_pool, rs(length=10))
            export = self._nfs_export_add("0.0.0.0/0", fs.full_path,
                                          ["insecure", "ro"], "1000")
            self._nfs_export_remove(export.host, export.path)
            self._fs_destroy(fs)

    def test_ep_nfs_export_invalid_options(self):
        for fs_pool in TestTargetd._fs_pools():
            fs = TestTargetd._fs_create(fs_pool, rs(length=10))

            error_code = 0
            try:
                self._nfs_export_add("0.0.0.0/0", fs.full_path,
                                     ["insecure", "secure"], "1000")
            except TargetdError as e:
                error_code = e.error

            self.assertEqual(
                error_code, TargetdError.INVALID_ARGUMENT,
                "Expecting error on conflicting options")
            self._fs_destroy(fs)

    def test_gp_nfs_export_add_chown_uid_gid(self):
        for fs_pool in TestTargetd._fs_pools():
            fs = TestTargetd._fs_create(fs_pool, rs(length=10))
            export = self._nfs_export_add("0.0.0.0/0", fs.full_path, "insecure", "1000:1000")
            self._nfs_export_remove(export.host, export.path)
            self._fs_destroy(fs)

    def test_ep_nfs_export_add_chown_invalid_uid(self):
        for fs_pool in TestTargetd._fs_pools():
            fs = TestTargetd._fs_create(fs_pool, rs(length=10))
            error_code = 0
            try:
                self._nfs_export_add("0.0.0.0/0", fs.full_path, "insecure", "testuser")
            except TargetdError as e:
                error_code = e.error
            self.assertEqual(
                error_code, TargetdError.INVALID_ARGUMENT,
                "nfs_export_add expecting INVALID_ARGUMENT when trying to use uid"
                " as non numerical")
            self._fs_destroy(fs)

    def tearDown(self):
        for e in TestTargetd._export_list():
            self._export_destroy(e)

        # As we can have dependencies we will loop trying to delete each one
        # until they are all gone
        while True:
            keep_going = False
            for pool in TestTargetd._block_pools():
                for vol in TestTargetd._vol_list(pool):
                    try:
                        self._vol_destroy(pool, vol)
                    except TargetdError:
                        keep_going = True
            if not keep_going:
                break

        while True:
            keep_going = False
            for fs in TestTargetd._fs_list():
                try:
                    self._fs_destroy(fs)
                except TargetdError:
                    keep_going = True
            if not keep_going:
                break


if __name__ == '__main__':
    unittest.main()
