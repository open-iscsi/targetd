#! /usr/bin/env python
# -*- coding: utf-8 -*-
# vim: set fileencoding=UTF-8 :

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
# Test client to exercise targetd.

import symmetricjsonrpc, sys

class PingRPCClient(symmetricjsonrpc.RPCClient):
    class Request(symmetricjsonrpc.RPCClient.Request):
        def dispatch_request(self, subject):
            # Handle callbacks from the server
            print "dispatch_request(%s)" % (repr(subject),)
            assert subject['method'] == "pingping"
            return "pingpong"

if '--help' in sys.argv:
    print """client.py
    --ssl
        Encrypt communication with SSL using M2Crypto. Requires a
        server.pem in the current directory.
"""
    sys.exit(0)

if '--ssl' in sys.argv:
    # Set up an SSL connection
    import M2Crypto
    ctx = M2Crypto.SSL.Context()
    ctx.set_verify(M2Crypto.SSL.verify_peer | M2Crypto.SSL.verify_fail_if_no_peer_cert, depth=9)
    if ctx.load_verify_locations('server.pem') != 1: raise Exception('No CA certs')
    s = M2Crypto.SSL.Connection(ctx)
else:
    # Set up a TCP socket
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

#  Connect to the server
s.connect(('localhost', 4712))

# Create a client thread handling for incoming requests
client = PingRPCClient(s)

# Call a method on the server
res = client.request("volumes", wait_for_response=True)
print "client.volumes => %s" % res

# Call a second method on the server
try:
    res = client.request("destroy", params=dict(name="test4"), wait_for_response=True)
    print "client.destroy => %s" % res
except Exception, e:
    print "Exception:", e

# Call a third method on the server
try:
    res = client.request("create", params=dict(name="test4", size=20000000), wait_for_response=True)
    print "client.create => %s" % res
except Exception, e:
    print "Exception:", e


# Notify server it can shut down
client.notify("shutdown")

client.shutdown()
