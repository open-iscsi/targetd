#!/usr/bin/env python

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Copyright 2012, Andy Grover <agrover@redhat.com>
#
# A server that exposes a network interface for the LIO
# kernel target.

import os
import contextlib
import setproctitle
from rtslib import (Target, TPG, NodeACL, FabricModule, BlockStorageObject,
                    NetworkPortal, LUN, MappedLUN, RTSLibError)
import lvm
import json
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from SocketServer import ThreadingMixIn
import socket

setproctitle.setproctitle("targetd")

config_path = "/etc/target/targetd.json"

default_config = dict(
    pool_name = "test",
    user = "foo",
    password = "bar",
    ssl = False,
    target_name = "iqn.2003-01.org.linux-iscsi.%s:targetd" % socket.gethostname()
)

config = {}
if os.path.isfile(config_path):
    jsontxt=""
    for f in open(config_path):
        if not f.lstrip().startswith("#"):
            jsontxt += f
    config = json.loads(jsontxt)

for key, value in default_config.iteritems():
    if key not in config:
        config[key] = value


# fail early if can't access vg
lvm_handle = lvm.Liblvm()
test_vg = lvm_handle.vgOpen(config['pool_name'], "w")
test_vg.close()
lvm_handle.close()

#
# We can't keep lvm/vg handles open continually since liblvm does weird
# things with signals. Instead, define this context manager that eases
# getting vg in each method and calls close() on vg and lvm objs.
#
@contextlib.contextmanager
def vgopen():
    with contextlib.closing(lvm.Liblvm()) as lvm_handle:
        with contextlib.closing(lvm_handle.vgOpen(config['pool_name'], "w")) as vg:
            yield vg

def volumes():
    output = []
    with vgopen() as vg:
        for lv in vg.listLVs():
            output.append(dict(name=lv.getName(), size=lv.getSize(),
                               uuid=lv.getUuid()))
    return output

def create(name, size):
    with vgopen() as vg:
        lv = vg.createLvLinear(name, int(size))
        print "LV %s created, size %s" % (name, lv.getSize())

def destroy(name):
    fm = FabricModule('iscsi')
    t = Target(fm, config['target_name'])
    tpg = TPG(t, 1)

    if name in (lun.storage_object.name for lun in tpg.luns):
        raise ValueError("Volume '%s' cannot be removed while exported")

    with vgopen() as vg:
        lvs = [lv for lv in vg.listLVs() if lv.getName() == name]
        if not len(lvs) == 1:
            raise LookupError("lv not found")
        lvs[0].remove()
        print "LV %s removed" % name

def export_list():
    fm = FabricModule('iscsi')
    t = Target(fm, config['target_name'])
    tpg = TPG(t, 1)

    exports = []
    for na in tpg.node_acls:
        for mlun in na.mapped_luns:
            exports.append(dict(initiator_wwn=na.node_wwn, lun=mlun.mapped_lun,
                                vol=mlun.tpg_lun.storage_object.name))
    return exports

def export_to_initiator(vol_name, initiator_wwn, lun):
    # only add new SO if it doesn't exist
    try:
        so = BlockStorageObject(vol_name)
    except RTSLibError:
        so = BlockStorageObject(vol_name, dev="/dev/%s/%s" %
                                (config['pool_name'], vol_name))

    so = BlockStorageObject(vol_name)
    fm = FabricModule('iscsi')
    t = Target(fm, config['target_name'])
    tpg = TPG(t, 1)
    tpg.enable = True
    tpg.set_attribute("authentication", 0)
    np = NetworkPortal(tpg, "0.0.0.0")
    na = NodeACL(tpg, initiator_wwn)

    # only add tpg lun if it doesn't exist
    for tmp_lun in tpg.luns:
        if tmp_lun.storage_object.name == so.name \
                and tmp_lun.storage_object.plugin == 'block':
            tpg_lun = tmp_lun
            break
    else:
        tpg_lun = LUN(tpg, storage_object=so)

    # only add mapped lun if it doesn't exist
    for tmp_mlun in tpg_lun.mapped_luns:
        if tmp_mlun.mapped_lun == lun:
            mapped_lun = tmp_mlun
            break
    else:
        mapped_lun = MappedLUN(na, lun, tpg_lun)

def remove_export(vol_name, initiator_wwn):
    fm = FabricModule('iscsi')
    t = Target(fm, config['target_name'])
    tpg = TPG(t, 1)
    na = NodeACL(tpg, initiator_wwn)

    for mlun in na.mapped_luns:
        if mlun.tpg_lun.storage_object.name == vol_name:
            tpg_lun = mlun.tpg_lun
            mlun.delete()
            # be tidy and delete unused tpg lun mappings?
            if not len(list(tpg_lun.mapped_luns)):
                tpg_lun.delete()
            break
    else:
        raise LookupError("Volume '%s' not found in %s exports" %
                          (vol_name, initiator_wwn))

    # TODO: clean up NodeACLs w/o any exports as well?

def pools():
    with vgopen() as vg:
        # only support 1 vg for now
        return [dict(name=vg.getName(), size=vg.getSize(), free_size=vg.getFreeSize())]


mapping = dict(
    vol_list=volumes,
    vol_create=create,
    vol_destroy=destroy,
    export_list=export_list,
    export_create=export_to_initiator,
    export_destroy=remove_export,
    pool_list=pools,
    )

class TargetHandler(BaseHTTPRequestHandler):

    def do_POST(self):

        # get basic auth string, strip "Basic "
        # TODO: add SSL/TLS, or this is not secure
        try:
            auth64 = self.headers.getheader("Authorization")[6:]
            in_user, in_pass = auth64.decode('base64').split(":")
        except:
            self.send_error(400)
            return

        if in_user != config['user'] or in_pass != config['password']:
            self.send_error(401)
            return

        if not self.path == "/targetrpc":
            self.send_error(404)
            return

        try:
            error = (-1, "jsonrpc error")
            id = None
            try:
                content_len = int(self.headers.getheader('content-length'))
                req = json.loads(self.rfile.read(content_len))
            except ValueError:
                # see http://www.jsonrpc.org/specification for errcodes
                errcode = (-32700, "parse error")
                raise

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()

            try:
                version = req['jsonrpc']
                if version != "2.0":
                    raise ValueError
                method = req['method']
                id = req['id']
                params = req.get('params', None)
            except (KeyError, ValueError):
                error = (-32600, "not a valid jsonrpc-2.0 request")
                raise

            try:
                if params:
                    result = mapping[method](**params)
                else:
                    result = mapping[method]()
            except KeyError:
                error = (-32601, "method %s not found" % method)
                raise
            except TypeError:
                error = (-32602, "invalid method parameter(s)")
                raise
            except Exception, e:
                error = (-1, "%s: %s" % (type(e).__name__, e))
                raise

            rpcdata = json.dumps(dict(result=result, id=id))

        except Exception, e:
            rpcdata = json.dumps(dict(error=dict(code=error[0], message=error[1]), id=id))
        finally:
            self.wfile.write(rpcdata)
            self.wfile.close()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""

try:
    server = ThreadedHTTPServer(('', 18700), TargetHandler)
    print "started server"
    server.serve_forever()
except KeyboardInterrupt:
    print "SIGINT received, shutting down"
    server.socket.close()
