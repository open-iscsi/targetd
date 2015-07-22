import subprocess
import StringIO
import json
import logging as log
from collections import defaultdict
import utils
from utils import TargetdError, invoke
DISCOVERY_METHODS = ["sendtargets", "isns"]
AUTH_METHODS = ["chap", "mutual_chap"]
ISCSIADM_BINARY = "/usr/bin/iscsiadm"

ISCSI_ERR_LOGIN_AUTH_FAILED = 24
ISCSI_ERR_TRANS = 4
ISCSI_ERR_IDBM = 6

STRING_TOO_LONG = -20
EMPTY_STRING = -21
NO_ASCSII_STRING = -22
DISCOVERY_RECORD_NOT_FOUND = -23
INVALIDE_VALUE_DISCOVERY = -24
INVALIDE_VALUE_AUTH = -25
NO_ROUTE_TO_HOST = -26
LOGIN_FAILED = -27


def nested_set(dic, keys, value):
    for key in keys[:-1]:
        dic = dic.setdefault(key, {})
    dic[keys[-1]] = value


def discovery_parser(msg):
    """
    Takes a string as parameter and returns a dictionary
    """
    d = defaultdict(dict)

    for line in msg.splitlines():
        if line.startswith("discovery"):
            attribute, value = line.split("=")
            attrs = attribute.split(".")

            value = value.strip()
            if value == "<empty>":
                value = ""
            for i in range(len(attrs)):
                attrs[i] = attrs[i].strip()

            nested_set(d, attrs, value)

    return d["discovery"]


def validate_string(msg):
    """
    Raise an error if the specified string is empty,
    longer than 255 chars or not ASCII encoded.
    """
    try:
        if len(msg) > 255:
            raise TargetdError(STRING_TOO_LONG, "String too long")
        elif msg == "":
            raise TargetdError(EMPTY_STRING, "Unauthorised empty string")
        msg.decode('ascii')
    except UnicodeDecodeError:
        raise TargetdError(NO_ASCSII_STRING,
                           "Not a ascii-encoded unicode string")


def get_error_code(iscsi_error_code):
    """
    Returns the error code of our specification corresponding
    to the error code of iscsi specification.
    """
    error_code = -1
    if iscsi_error_code == ISCSI_ERR_LOGIN_AUTH_FAILED:
        error_code = LOGIN_FAILED
    elif iscsi_error_code == ISCSI_ERR_TRANS:
        error_code = NO_ROUTE_TO_HOST
    elif iscsi_error_code == ISCSI_ERR_IDBM:
        error_code = DISCOVERY_RECORD_NOT_FOUND
    return error_code


def discovery_wrapper(hostname, operation="", discovery_method="st",
                      op_params=(), discover=False):
    """
    Returns the iscsiadm command, with discovery mode,
    corresponding to different specified arguments.
    """
    cmd = [ISCSIADM_BINARY, "-m", "discoverydb", "-p",
           hostname, "-t", discovery_method]
    if operation:
        cmd.extend(["-o", operation])
        if op_params:
            cmd.extend(["-n", "discovery.sendtargets.auth.%s" % op_params[0]])
            cmd.extend(["-v", op_params[1]])
    elif discover:
        cmd.append("-D")
    return_code, output_success, output_failure = invoke(cmd, False)
    if return_code:
        error_string = output_failure.splitlines()[0].split(" ", 1)[-1].strip()
        # error_string extracts the text after "iscsiadm: " of the
        # first line of e.output
        error_code = get_error_code(return_code)
        raise TargetdError(error_code, error_string)
    return output_success


def node_wrapper(targetname, hostname=None, operation="",
                 op_params=(), login=False):
    """
    """
    cmd = [ISCSIADM_BINARY, "-m", "node", "-T",
           targetname, "-t", discovery_method]
    if operation:
        cmd.extend(["-o", operation])
        if op_params:
            cmd.extend(["-n", "node.session.auth.%s" % op_params[0]])
            cmd.extend(["-v", op_params[1]])
    elif discover:
        cmd.append("--login")
    error_code, output_success, output_failure = utils.invoke(cmd, False)
    if error_code != 0:
        error_string = output_failure.splitlines()[0].split(" ", 1)[-1].strip()
        # error_string extracts the text after "iscsiadm: " of the
        # first line of e.output
        error_code = get_error_code(error_code)
        raise TargetdError(error_code, error_string)
    return output_success


def delete_discovery(hostname):
    """
    Delete discovery of targets at the specified hostname.
    """
    validate_string(hostname)
    output = discovery_wrapper(hostname, "delete")


def display_discovery(hostname):
    """
    Returns a dictionary of all data for the
    discovery node at the specified hostname.
    """
    validate_string(hostname)
    output = discovery_wrapper(hostname)
    d = discovery_parser(output)
    return d


def discovery_portal(hostname, discovery_method="sendtargets",
                     auth_method=None, username=None, password=None,
                     username_in=None, password_in=None):
    """
    Discover all targets for a given discovery portal
    using specified informations.
    """
    validate_string(hostname)
    if discovery_method == "sendtargets":
        discovery_method = "st"
    elif discovery_method not in DISCOVERY_METHODS:
        raise TargetdError(INVALIDE_VALUE_DISCOVERY, "Invalid value."
                           " Possible values are : %s" %
                           ", ".join(DISCOVERY_METHODS))

    if auth_method in AUTH_METHODS:
        validate_string(username)
        validate_string(password)
        discovery_wrapper(hostname, "new", discovery_method)
        discovery_wrapper(hostname, "update", discovery_method,
                          ("authmethod", "CHAP"))
        discovery_wrapper(hostname, "update", discovery_method,
                          ("username", username))
        discovery_wrapper(hostname, "update", discovery_method,
                          ("password", password))
        if auth_method == "mutual_chap":
            validate_string(username_in)
            validate_string(password_in)
            discovery_wrapper(hostname, "update", discovery_method,
                              ("username_in", username_in))
            discovery_wrapper(hostname, "update", discovery_method,
                              ("password_in", password_in))
    elif auth_method:
        raise TargetdError(INVALIDE_VALUE_AUTH, "Invalid value."
                           " Possible values are : %s" %
                           ", ".join(AUTH_METHODS))

    discovery_wrapper(hostname, discovery_method=discovery_method,
                      discover=True)

# ************main****************
# delete_discovery("192.168.122.239")
print json.dumps(display_discovery("192.168.122.2"))
# discovery_portal("192.168.122.239")
# discovery_portal("192.168.122.239","sendtargets","mutual_chap","mytargetuid",
# "mytargetsecret","mymutualuid","mymutualsecret")
# help(delete_discovery)
# discovery_wrapper("192.168.122.239","st")
