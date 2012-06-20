#!/usr/bin/env python

# based on code from git://github.com/openstack/nova.git
# nova/volume/nexenta/jsonrpc.py
#
# Copyright 2011 Nexenta Systems, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0

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
# Test client to exercise targetd.
#


import sys
import urllib2
import json
import time

user = "foo"
password = "bar"
url = "http://localhost:18700/targetrpc"
host = 'localhost'
port = 18700
path = '/targetrpc'
id = 1

def jsonrequest(method, params=None, ssl=False):
    global id
    data = json.dumps(dict(id=id, method=method, params=params, jsonrpc="2.0"))
    id += 1
    auth = ('%s:%s' % (user, password)).encode('base64')[:-1]
    headers = {'Content-Type': 'application/json',
               'Authorization': 'Basic %s' % (auth,)}
    #print('Sending JSON data: %s' % data)
    if ssl:
        scheme = 'https'
    else:
        scheme = 'http'
    url = "%s://%s:%s%s" % (scheme, host, port, path)
    request = urllib2.Request(url, data, headers)
    response_obj = urllib2.urlopen(request)
    response_data = response_obj.read()
    #print('Got response: %s' % response_data)
    response = json.loads(response_data)
    if response.get('error') is not None:
        if response['error']['code'] <= 0:
            raise Exception(response['error'].get('message', ''))
        else: # +code is async execution id
            print "Async completion, polling for results"
            async_code = response['error']['code']
            while True:
                time.sleep(1)
                results = jsonrequest('async_list')
                status = results.get(str(async_code), None)
                if status:
                    if status[0]:
                        print "%d has error %d" % (async_code, status[0])
                        break
                    else:
                        print "%d still going, %d%% complete" % \
                            (async_code, status[1])
                else:
                    print "%s done" % async_code
                    break
    else:
        return response.get('result')


results = jsonrequest("vol_list")
for result in results:
    print result['name'], result['size']

#print "+"*20
#jsonrequest('vol_create', dict(name="test2", size=400000000))

#print "+"*20
#jsonrequest("vol_destroy", dict(name="test2-copy"))

print "+"*20
jsonrequest("vol_copy", dict(vol_orig="test2", vol_new="test2-copy"))

print "+"*20
jsonrequest("vol_destroy", dict(name="test2-copy"))


#jsonrequest("export_destroy", dict(vol_name="test5", initiator_wwn="iqn.2006-03.com.wtf.ohyeah:666"))

#jsonrequest("export_create", dict(vol_name="test5", lun=5, initiator_wwn="iqn.2006-03.com.wtf.ohyeah:666"))

#jsonrequest("create", dict(name="test6", size=20000000))
#jsonrequest("destroy", dict(name="test6"))

