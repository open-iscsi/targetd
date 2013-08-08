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
# A server that exposes a network API for configuring
# sharable resources on the local machine, such as the LIO
# kernel target.

import os
import setproctitle
import json
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from threading import Lock
import yaml
import itertools
import socket
import ssl
import traceback
import logging as log
import sys

default_config_path = "/etc/target/targetd.yaml"

default_config = dict(
    block_pools=['vg-targetd'],
    fs_pools=[],
    user="admin",
    log_level='info',
    # security: no default password
    target_name="iqn.2003-01.org.linux-iscsi.%s:targetd" %
                socket.gethostname(),
    ssl=False,
    ssl_cert="/etc/target/targetd_cert.pem",
    ssl_key="/etc/target/targetd_key.pem",
)

config = {}


class TargetdError(Exception):
    def __init__(self, error_code, message, *args, **kwargs):
        Exception.__init__(self, *args, **kwargs)
        self.error = error_code
        self.msg = message

# Will be added to by fs/block.initialize()
mapping = dict()

class TargetHandler(BaseHTTPRequestHandler):

    def log_request(self, code='-', size='-'):
        # override base class - don't log good requests
        pass

    def do_POST(self):

        rpcdata = ""
        error = None

        # get basic auth string, strip "Basic "
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
            self.id = None
            try:
                content_len = int(self.headers.getheader('content-length'))
                req = json.loads(self.rfile.read(content_len))
            except ValueError:
                # see http://www.jsonrpc.org/specification for errcodes
                error = (-32700, "parse error")
                raise

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()

            try:
                version = req['jsonrpc']
                if version != "2.0":
                    raise ValueError
                method = req['method']
                self.id = int(req['id'])
                params = req.get('params', None)
            except (KeyError, ValueError):
                error = (-32600, "not a valid jsonrpc-2.0 request")
                raise

            try:
                if params:
                    result = mapping[method](self, **params)
                else:
                    result = mapping[method](self)
            except KeyError:
                error = (-32601, "method %s not found" % method)
                log.debug(traceback.format_exc())
                raise
            except TypeError:
                error = (-32602, "invalid method parameter(s)")
                log.debug(traceback.format_exc())
                raise
            except TargetdError, td:
                error = (td.error, td.msg)
                raise
            except Exception, e:
                error = (-1, "%s: %s" % (type(e).__name__, e))
                log.debug(traceback.format_exc())
                raise

            rpcdata = json.dumps(dict(result=result, id=self.id))

        except:
            log.debug('Error=%s, msg=%s' % error)
            rpcdata = json.dumps(
                dict(error=dict(code=error[0], message=error[1]), id=self.id))
        finally:
            self.wfile.write(rpcdata)


class HTTPService(HTTPServer, object):
    """
    Handle requests one at a time

    Note: The liblvm library we use is not thread safe, thus we need to
    serialize access to it.  It has locking for concurrent process usage, but
    we will keep things simple by serializing calls to it.
    """


class TLSHTTPService(HTTPService):
    """Also use TLS to encrypt the connection"""

    def finish_request(self, sock, addr):
        sockssl = ssl.wrap_socket(
            sock, server_side=True,
            keyfile=config["ssl_key"],
            certfile=config["ssl_cert"],
            ciphers="HIGH:-aNULL:-eNULL:-PSK",
            suppress_ragged_eofs=True)
        return self.RequestHandlerClass(sockssl, addr, self)


def load_config(config_path):
    global config

    if os.path.isfile(config_path):
        config = yaml.safe_load(open(config_path).read())
        if config is None:
            config = {}

    for key, value in default_config.iteritems():
        if key not in config:
            config[key] = value

    # compat: handle old single-pool config option
    if 'pool_name' in config:
        config['block_pools'].append(config['pool_name'])
        del config['pool_name']

    # uniquify pool lists
    config['block_pools'] = set(config['block_pools'])
    config['fs_pools'] = set(config['fs_pools'])

    if not config.get('password', None):
        log.critical("password not set in %s" % config_path)
        raise AttributeError

    # convert log level to int
    config['log_level'] = getattr(log, config['log_level'].upper(), log.INFO)
    log.basicConfig(level=config['log_level'])
    

def update_mapping():
    # wait until now so submodules can import 'main' safely
    import block
    import fs

    mapping.update(block.initialize(config))
    mapping.update(fs.initialize(config))

    # one method requires output from both modules
    def pool_list(req):
        return list(itertools.chain(block.block_pools(req), fs.fs_pools(req)))

    mapping['pool_list'] = pool_list


def main():
    server = None

    try:
        load_config(default_config_path)
    except AttributeError:
        return -1

    setproctitle.setproctitle("targetd")

    update_mapping()

    if config['ssl']:
        server_class = TLSHTTPService
        note = "(TLS yes)"
    else:
        server_class = HTTPService
        note = "(TLS no)"

    try:
        server = server_class(('', 18700), TargetHandler)
        log.info("started server %s", note)
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("SIGINT received, shutting down")
        if server is not None:
            server.socket.close()
        return -1

    return 0
