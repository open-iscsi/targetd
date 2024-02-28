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

import json
import os
import signal

import setproctitle

try:
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
except ImportError:
    from http.server import BaseHTTPRequestHandler, HTTPServer
import yaml
import itertools
import socket
import base64
import ssl
from socketserver import ThreadingMixIn
import time
from threading import Lock
import traceback
import logging as log
from targetd.utils import TargetdError, Pit, Tar
import stat

default_config_path = "/etc/target/targetd.yaml"

default_config = dict(
    block_pools=["vg-targetd"],
    fs_pools=[],
    zfs_block_pools=[],
    zfs_enable_copy=False,
    user="admin",
    log_level="info",
    # security: no default password
    target_name="iqn.2003-01.org.linux-iscsi.%s:targetd" % socket.gethostname(),
    ssl=False,
    ssl_cert="/etc/target/targetd_cert.pem",
    ssl_key="/etc/target/targetd_key.pem",
    portal_addresses=["0.0.0.0"],
    allow_chown=False,
)

config = {}

# Will be added to by fs/block.initialize()
mapping = dict()

# Used to serialize the work we actually do
mutex = Lock()

# Tarpit
tar = Tar()


class TargetHandler(BaseHTTPRequestHandler):
    def log_request(self, code="-", size="-"):
        # override base class - don't log good requests
        pass

    def do_POST(self):

        rpcdata = ""
        error = None
        id_num = 0

        # get basic auth string, strip "Basic "
        try:
            auth_bytes = self.headers.get("Authorization")[6:].encode("utf-8")
            auth_str = base64.b64decode(auth_bytes).decode("utf-8")
            in_user, in_pass = auth_str.split(":")
        except Exception:
            log.error(traceback.format_exc())
            self.send_error(400)
            return

        if tar.is_stuck(self.client_address[0]):
            log.warning(
                "Concurrent authentication attempts from %s" % self.client_address[0]
            )
            # This client already has a failed authentication attempt,
            # immediately return error without trying new credentials.
            self.send_error(503)
            return

        if in_user != config["user"] or in_pass != config["password"]:
            # Tarpit the bad authentication for a bit
            with tar.pitted(self.client_address[0]):
                time.sleep(2)
                self.send_error(401)
            return

        if not self.path == "/targetrpc":
            log.error("Invalid URL %s" % self.path)
            self.send_error(404)
            return

        try:
            error = (-1, "jsonrpc error")
            try:
                content_len = int(self.headers.get("content-length"))

                # Make sure we aren't being asked to read too much data.
                # Since this happens after authentication this really should
                # never happen for normal operation.
                if content_len > (1024 * 128):
                    log.error(
                        "client %s, content-length = %d rejecting!"
                        % (self.client_address[0], content_len)
                    )
                    self.send_error(413)
                    return

                req = json.loads(self.rfile.read(content_len).decode("utf-8"))
            except ValueError:
                # see http://www.jsonrpc.org/specification for errcodes
                error = (-32700, "parse error")
                raise

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()

            try:
                version = req["jsonrpc"]
                if version != "2.0":
                    raise ValueError
                method = req["method"]
                id_num = int(req["id"])
                params = req.get("params", None)
            except (KeyError, ValueError):
                error = (-32600, "not a valid jsonrpc-2.0 request")
                raise

            # Serialize the actual work to be done.
            mutex.acquire()
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
                error = (TargetdError.INVALID_ARGUMENT, "invalid method arguments(s)")
                log.debug(traceback.format_exc())
                raise
            except TargetdError as td:
                error = (td.error, str(td))
                raise
            except Exception as e:
                error = (-1, "%s: %s" % (type(e).__name__, e))
                log.debug(traceback.format_exc())
                raise
            finally:
                mutex.release()

            rpcdata = json.dumps(dict(result=result, id=id_num, jsonrpc="2.0"))
        except:
            log.debug(traceback.format_exc())
            log.debug("Error=%s, msg=%s" % (error[0], error[1]))
            rpcdata = json.dumps(
                dict(
                    error=dict(code=error[0], message=error[1]),
                    id=id_num,
                    jsonrpc="2.0",
                )
            )
        finally:
            self.wfile.write(rpcdata.encode("utf-8"))


class HTTPService(ThreadingMixIn, HTTPServer, object):
    """
    Handle rpc requests concurrently, but process them sequentially by using a
    mutex.  We do this so we hopefully don't block valid API users when some
    one tries to brute force the password.

    Note: Many things we are calling into are not thread safe and/or cannot be
    done concurrently.  We will process things one at a time.
    """


class TLSHTTPService(HTTPService):
    """Also use TLS to encrypt the connection"""

    @staticmethod
    def _verify_ssl_file(f):
        rc = False
        # Check the SSL files
        if os.path.exists(f):
            ss = os.stat(f)
            if stat.S_ISREG(ss.st_mode):
                if ss.st_uid == 0:
                    if ss.st_mode & 0o077 == 0 and bool(ss.st_mode & stat.S_IRUSR):
                        rc = True
                    else:
                        log.error(
                            "SSL file: '%s' incorrect permissions (%s), "
                            "ensure file is _not_ readable or writeable "
                            "by anyone other than owner, and that owner "
                            "can read." % (f, oct(ss.st_mode & 0o777))
                        )
                else:
                    log.error("SSL file: '%s' not owned by root." % f)
            else:
                log.error("SSL file: '%s' is not a regular file." % f)
        else:
            log.error("SSL file: '%s' does not exist." % f)
        return rc

    @staticmethod
    def verify_certificates():
        return TLSHTTPService._verify_ssl_file(
            config["ssl_key"]
        ) and TLSHTTPService._verify_ssl_file(config["ssl_cert"])


def load_config(config_path):
    global config

    if os.path.isfile(config_path):
        config = yaml.safe_load(open(config_path).read())
        # If a user supplies a password as "password:whatever" we don't get
        # a parse failure, we simply get a string with the contents.
        # Maybe there is a better way to handle this issue where we don't
        # have a space between key and value?
        if config is None or type(config) is str:
            config = {}

    for key, value in iter(default_config.items()):
        if key not in config:
            config[key] = value

    # compatibility: handle old single-pool config option
    if "pool_name" in config:
        log.warning("Please update config file, " "'pool_name' should be 'block_pools'")
        config["block_pools"] = [config["pool_name"]]
        del config["pool_name"]

    # Make unique pool lists
    config["block_pools"] = set(config["block_pools"])
    config["fs_pools"] = set(config["fs_pools"])
    config["zfs_block_pools"] = set(config["zfs_block_pools"])

    passwd = config.get("password", None)
    if not passwd or type(passwd) is not str:
        log.critical(
            "password not set in %s in the form 'password: string_pw'" % config_path
        )
        raise AttributeError

    # convert log level to int
    config["log_level"] = getattr(log, config["log_level"].upper(), log.INFO)
    log.basicConfig(level=config["log_level"])


def update_mapping():
    # wait until now so submodules can import 'main' safely
    import targetd.block as block
    import targetd.fs as fs

    try:
        mapping.update(block.initialize(config))
    except Exception as e:
        log.error("Error initializing block module: %s" % e)
        raise

    try:
        mapping.update(fs.initialize(config))
    except Exception as e:
        log.error("Error initializing fs module: %s" % e)
        raise

    # one method requires output from both modules
    def pool_list(req):
        return list(itertools.chain(block.block_pools(req), fs.fs_pools(req)))

    mapping["pool_list"] = pool_list


RUN = True


def handler(signum, frame):
    global RUN
    if signum == signal.SIGINT:
        log.info("SIGINT received, shutting down ...")
        RUN = False


def wrap_socket(s):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.check_hostname = False
    context.load_cert_chain(config["ssl_cert"], config["ssl_key"])
    context.set_ciphers("HIGH:-aNULL:-eNULL:-PSK")
    wrapped = context.wrap_socket(s, server_side=True)
    return wrapped


def main():

    signal.signal(signal.SIGINT, handler)

    try:
        load_config(default_config_path)
    except AttributeError:
        return -1

    setproctitle.setproctitle("targetd")

    try:
        update_mapping()
    except Exception as e:
        log.error(repr(e))
        return -1

    if config["ssl"]:
        server_class = TLSHTTPService

        # Make sure certificates are good to go!
        if not TLSHTTPService.verify_certificates():
            return -1

        note = "(TLS yes)"
    else:
        server_class = HTTPService
        note = "(TLS no)"

    server = server_class(("", 18700), TargetHandler)
    server.socket = wrap_socket(server.socket)
    log.info("started server %s", note)

    server.timeout = 0.5
    while RUN:
        server.handle_request()

    server.socket.close()

    return 0
