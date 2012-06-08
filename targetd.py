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

user = "foo"
password = "bar"

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

        # get basic auth string, strip "Basic "
        # TODO: add SSL/TLS, or this is not secure
        try:
            auth64 = self.headers.getheader("Authorization")[6:]
            in_user, in_pass = auth64.decode('base64').split(":")
        except:
            self.send_error(400)
            return

        if in_user != user or in_pass != password:
            self.send_error(401)
            return

        if not self.path == "/liorpc":
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

            rpcdata = json.dumps(dict(result=result, id=id))

        except Exception, e:
            rpcdata = json.dumps(dict(error=dict(code=error[0], message=error[1]), id=id))
        finally:
            self.wfile.write(rpcdata)
            self.wfile.close()


try:
    server = HTTPServer(('', 18700), LIOHandler)
    print "started server"
    server.serve_forever()
except KeyboardInterrupt:
    print "SIGINT received, shutting down"
    server.socket.close()
