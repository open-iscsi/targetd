
import requests
from requests.auth import HTTPBasicAuth

from os import getenv, path
import json
from targetd.utils import TargetdError

# based on code from git://github.com/openstack/nova.git
# nova/volume/nexenta/jsonrpc.py which is under Apache License, Version 2.0
# and copied from `../client` file in the targetd repo and modified for
# unit test.  TODO: Convert client over to using this too.

# Make most of these changeable
user = getenv("TARGETD_UT_USER", "admin")
password = getenv("TARGETD_UT_PASSWORD", "targetd")
host = getenv("TARGETD_UT_HOST", "localhost")
port = int(getenv("TARGETD_UT_PORT", 18700))
rpc_path = '/targetrpc'
cert_file = getenv("TARGETD_UT_CERTFILE",
                   path.dirname(path.realpath(__file__)) +
                   "/targetd_cert.pem")

id_num = 1


def _json_payload(payload):
    assert payload.get('jsonrpc') == "2.0"
    if 'error' in payload:
        error_code = int(payload['error']['code'])
        if error_code <= 0:
            raise TargetdError(error_code,
                               payload['error'].get('message', ''))
        else:
            raise Exception("Invalid error code %d, should be negative!" %
                            error_code)
    else:
        return payload['result']


def rpc(method, params=None, data=None):
    global id_num
    auth_info = HTTPBasicAuth(user, password)

    if not data:
        data = json.dumps(
            dict(id=id_num,
                 method=method,
                 params=params, jsonrpc="2.0")).encode('utf-8')

    id_num += 1
    url = "%s://%s:%s%s" % ('https', host, port, rpc_path)
    r = requests.post(url, data=data, auth=auth_info, verify=cert_file)
    if r.status_code == 200:
        # JSON RPC error
        return _json_payload(r.json())
    else:
        # Transport error
        raise TargetdError(r.status_code, str(r))

def test_bad_authenticate():
    auth_info = HTTPBasicAuth("bad_user", "bad_password")
    data = json.dumps(
        dict(id=10,
             method="pool_list",
             params=None, jsonrpc="2.0")).encode('utf-8')
    url = "%s://%s:%s%s" % ('https', host, port, rpc_path)

    result = None
    exception = None
    try:
        result = requests.post(url, data=data, auth=auth_info, verify=cert_file)
    except Exception as e:
        exception = e

    return exception, result


if __name__ == "__main__":
    try:
        print(rpc("pool_list"))
    except TargetdError as e:
        print("Got error %d %s" % (e.error, e))