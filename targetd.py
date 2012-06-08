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
# Based upon example code from python-symmetric-jsonrpc:
# Copyright (C) 2009 Egil Moeller <redhog@redhog.org>
# Copyright (C) 2009 Nicklas Lindgren <nili@gulmohar.se>
#
# Copyright 2012, Andy Grover <agrover@redhat.com>
#
# A server that exposes a network interface for the LIO
# kernel target.

import sys
import contextlib
import setproctitle
import signal
import rtslib
import lvm
import json
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

setproctitle.setproctitle("targetd")

# TODO: read config file

root = rtslib.RTSRoot()

vg_name = "test"

# fail early if can't access vg
lvm_handle = lvm.Liblvm()
test_vg = lvm_handle.vgOpen(vg_name, "w")
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
        with contextlib.closing(lvm_handle.vgOpen(vg_name, "w")) as vg:
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
    with vgopen() as vg:
        lvs = [lv for lv in vg.listLVs() if lv.getName() == name]
        if not len(lvs) == 1:
            raise LookupError("lv not found")
        lvs[0].remove()
        print "LV %s removed" % name

mapping = dict(
    volumes=volumes,
    create=create,
    destroy=destroy,
    )

class LIOHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        if self.path == "/liorpc":
            try:
                content_len = int(self.headers.getheader('content-length'))
                req = json.loads(self.rfile.read(content_len))

                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()

                if "params" in req and req['params']:
                    result = mapping[req['method']](**req['params'])
                else:
                    result = mapping[req['method']]()

                rpcdata = json.dumps(dict(result=result, id=req['id']))

            except Exception, e:
                rpcdata = json.dumps(dict(error=dict(code=-1, message=str(e)), id=req['id']))
            finally:
                self.wfile.write(rpcdata)
                self.wfile.close()
        else:
            self.send_error(404)


try:
    server = HTTPServer(('', 18700), LIOHandler)
    print "started server"
    server.serve_forever()
except KeyboardInterrupt:
    print "SIGINT received, shutting down"
    server.socket.close()
