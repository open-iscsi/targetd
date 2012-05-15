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

import symmetricjsonrpc
import sys
import setproctitle
import rtslib
import lvm

setproctitle.setproctitle("targetd")

# TODO: read config file

root = rtslib.RTSRoot()

vg_name = "test"

lvm_handle = lvm.Liblvm()

vg = lvm_handle.vgOpen(vg_name, "w")

def volumes():
    output = []
    for lv in vg.listLVs():
        output.append(dict(name=lv.getName(), size=lv.getSize(),
                           uuid=lv.getUuid()))
    return output

def create(name, size):
    lv = vg.createLvLinear(name, int(size))
    print "LV %s created, size %s" % (name, lv.getSize())

def destroy(name):
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

class TargetRPCServer(symmetricjsonrpc.RPCServer):
    class InboundConnection(symmetricjsonrpc.RPCServer.InboundConnection):
        class Thread(symmetricjsonrpc.RPCServer.InboundConnection.Thread):
            class Request(symmetricjsonrpc.RPCServer.InboundConnection.Thread.Request):
                def dispatch_notification(self, subject):
                    print "dispatch_notification(%s)" % (repr(subject),)
                    assert subject['method'] == "shutdown"
                    # Shutdown the server. Note: We must use a
                    # notification, not a method for this - when the
                    # server's dead, there's no way to inform the
                    # client that it is...
                    self.parent.parent.parent.shutdown()

                def dispatch_request(self, subject):
                    print "dispatch_request(%s)" % (repr(subject),)
                    if subject['method'] not in mapping:
                        raise Exception("method not found")
                    params = subject['params']
                    print "params", params
                    if not params:
                        return mapping[subject['method']]()
                    else:
                        return mapping[subject['method']](**params)
                    

if '--help' in sys.argv:
    print """client.py
    --ssl
        Encrypt communication with SSL using M2Crypto. Requires a
        server.pem and server.key in the current directory.
"""
    sys.exit(0)

if '--ssl' in sys.argv:
    # Set up a SSL socket
    import M2Crypto
    ctx = M2Crypto.SSL.Context()
    ctx.load_cert('server.pem', 'server.key')
    s = M2Crypto.SSL.Connection(ctx)
else:
    # Set up a TCP socket
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

#  Start listening on the socket for connections
s.bind(('', 4712))
s.listen(1)

# Create a server thread handling incoming connections
server = TargetRPCServer(s, name="targetd")

# Wait for the server to stop serving clients
server.join()

