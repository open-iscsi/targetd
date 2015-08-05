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
ISCSI_ERR_TRANS_TIMEOUT = 8
ISCSI_ERR_NO_OBJS_FOUND = 21
ISCSI_ERR_SESS_EXISTS = 15
ISCSI_ERR_ISNS_QUERY = 25

STRING_TOO_LONG = -20
EMPTY_STRING = -21
NO_ASCSII_STRING = -22
DISCOVERY_RECORD_NOT_FOUND = -23
INVALID_VALUE_DISCOVERY = -24
INVALID_VALUE_AUTH = -25
NO_ROUTE_TO_HOST = -26
LOGIN_FAILED = -27
SERVER_FAILURE = -28
NO_RECORDS_FOUND = -29
SESSION_LOGGED_IN = -30
NO_SESSION_INFO = -31
QUERY_FAILURE = -32


def initialize(config_dict):
    return dict(
        delete_discovery=delete_discovery,
        display_discovery=display_discovery,
        display_discovery_summary=display_discovery_summary,
        discover_portal=discover_portal,
        login_target=login_target,
        logout_target=logout_target,
        logout_all_targets=logout_all_targets,
        display_node=display_node,
        display_node_summary=display_node_summary,
        delete_node=delete_node,
        delete_all_nodes=delete_all_nodes,
        display_session=display_session,
        purge=purge)


def nested_set(dic, keys, value):
    for key in keys[:-1]:
        dic = dic.setdefault(key, {})
    dic[keys[-1]] = value


def discovery_node_parser(msg, mode):
    """
    Takes a string as parameter and returns a dictionary
    corresponding to a node or discovery record.
    """
    d = defaultdict(dict)

    for line in msg.splitlines():
        if line.startswith(mode):
            attribute, value = line.split("=")
            attrs = attribute.split(".")

            value = value.strip()
            if value == "<empty>":
                value = ""
            for i in range(len(attrs)):
                attrs[i] = attrs[i].strip()

            nested_set(d, attrs, value)

    return d[mode]


def discovery_summary_parser(msg):
    """
    Takes a string as parameter and returns a dictionary
    corresponding to all discovery records
    """
    d = defaultdict(dict)
    for line in msg.splitlines():
        try:
            key, method = [s.strip() for s in line.split(" via ")]
        except ValueError:
            continue
        try:
            hostname, port = key.split(":")
            port = int(port)
            d[hostname] = (port, method)
        except KeyError:
            pass

    return d


def node_summary_parser(msg):
    """
    Takes a string as parameter and returns a dictionary
    corresponding to all node records
    """
    d = defaultdict(dict)

    KEYWORD_MAP = {"Portal": "portal", "Iface Name": "interface"}
    for line in msg.splitlines():
        try:
            key, value = [s.strip() for s in line.split(": ")]
        except ValueError:
            continue
        try:
            if key == "Target":
                target = value
            elif key == "Portal":
                host, tpg = value.split(",")
                hostname, port = host.split(":")
                host_tuple = (hostname, int(port), int(tpg))
                d[target][hostname] = {KEYWORD_MAP[key]: host_tuple}
            else:
                d[target][hostname][KEYWORD_MAP[key]] = value
        except KeyError:
            pass

    return d


def session_parser(msg):
    """
    Takes a string as parameter and returns a dictionary
    corresponding to a session
    """
    d = defaultdict(dict)

    KEYWORD_MAP = {"Current Portal": "portal", "Iface Transport": "transport",
                   "Iface Initiatorname": "initiator_name",
                   "Iface IPaddress": "ip_address", "SID": "session_id",
                   "iSCSI Connection State": "connection_state",
                   "iSCSI Session State": "session_state",
                   "Internal iscsid Session State": "iscsid_session_state"}
    for line in msg.splitlines():
        try:
            key, value = [s.strip() for s in line.split(": ")]
        except ValueError:
            continue
        try:
            if key == "Target":
                target = value
            elif key == "Current Portal":
                host, tpg = value.split(",")
                hostname, port = host.split(":")
                host_tuple = (hostname, int(port), int(tpg))
                d[target][hostname] = {KEYWORD_MAP[key]: host_tuple}
            else:
                d[target][hostname][KEYWORD_MAP[key]] = value
        except KeyError:
            pass

    return d


def validate_string(msg):
    """
    Raise an error if the specified string is empty,
    longer than 255 chars or not ASCII encoded
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
    to the error code of iscsi specification
    """
    dict_error = {ISCSI_ERR_LOGIN_AUTH_FAILED: LOGIN_FAILED,
                  ISCSI_ERR_TRANS: NO_ROUTE_TO_HOST,
                  ISCSI_ERR_IDBM: DISCOVERY_RECORD_NOT_FOUND,
                  ISCSI_ERR_TRANS_TIMEOUT: SERVER_FAILURE,
                  ISCSI_ERR_NO_OBJS_FOUND: NO_RECORDS_FOUND,
                  ISCSI_ERR_SESS_EXISTS: SESSION_LOGGED_IN,
                  ISCSI_ERR_ISNS_QUERY: QUERY_FAILURE}
    if iscsi_error_code not in dict_error:
        return -1
    else:
        return dict_error[iscsi_error_code]


def discovery_wrapper(hostname=None, discovery_method=None, operation=None,
                      op_params=(), discover=False):
    """
    Returns the iscsiadm command, with discovery mode,
    corresponding to different specified arguments
    """
    cmd = [ISCSIADM_BINARY, "-m", "discoverydb"]
    if hostname:
        cmd.extend(["-p", hostname])
    if discovery_method:
        cmd.extend(["-t", discovery_method])
    if operation:
        cmd.extend(["-o", operation])
        if op_params:
            cmd.extend(["-n", "discovery.sendtargets.auth.%s" % op_params[0]])
            cmd.extend(["-v", op_params[1]])
    elif discover:
        cmd.extend(["-D", "-P", "1"])
    return_code, output_success, output_failure = invoke(cmd, False)
    if return_code:
        try:
            error_string = output_failure.splitlines()[0].split(" ", 1)[-1]
            error_string = error_string.strip()
            # error_string extracts the text after "iscsiadm: " of the
            # first line of e.output
            error_code = get_error_code(return_code)
            raise TargetdError(error_code, error_string)
        except IndexError:
            raise TargetdError(DISCOVERY_RECORD_NOT_FOUND,
                               "No discovery records found")
    return output_success


def node_wrapper(targetname=None, hostname=None, operation="",
                 op_params=(), login_out=None):
    """
    Returns the iscsiadm command, with node mode,
    corresponding to different specified arguments
    """
    cmd = [ISCSIADM_BINARY, "-m", "node", "-P", "1"]
    if targetname:
        cmd.extend(["-T", targetname])
    if hostname:
        cmd.extend(["-p", hostname])
    if operation:
        cmd.extend(["-o", operation])
        if op_params:
            cmd.extend(["-n", "node.session.auth.%s" % op_params[0]])
            cmd.extend(["-v", op_params[1]])
    elif login_out:
        if login_out == "login":
            cmd.append("--login")
        if login_out == "logout":
            cmd.append("--logout")
    error_code, output_success, output_failure = utils.invoke(cmd, False)
    if error_code != 0:
        error_string = output_failure.splitlines()[0].split(" ", 1)[-1].strip()
        # error_string extracts the text after "iscsiadm: " of the
        # first line of e.output
        error_code = get_error_code(error_code)
        raise TargetdError(error_code, error_string)
    return output_success


def session_wrapper(session_id=None):
    """
    Returns the iscsiadm command, with session mode,
    corresponding to different specified arguments
    """
    cmd = [ISCSIADM_BINARY, "-m", "session", "-P", "1"]
    if session_id:
        cmd.extend(["-r", session_id])
    error_code, output_success, output_failure = utils.invoke(cmd, False)
    if error_code != 0:
        error_string = output_failure.splitlines()[0].split(" ", 1)[-1].strip()
        # error_string extracts the text after "iscsiadm: " of the
        # first line of e.output
        error_code = get_error_code(error_code)
        raise TargetdError(error_code, error_string)
    return output_success


def discover_portal(req, hostname, discovery_method="sendtargets",
                    auth_method=None, username=None, password=None,
                    username_in=None, password_in=None):
    """
    Discover all targets for a given discovery portal
    using specified informations
    """
    validate_string(hostname)
    if discovery_method not in DISCOVERY_METHODS:
        raise TargetdError(INVALID_VALUE_DISCOVERY, "Invalid value."
                           " Possible values are : %s" %
                           ", ".join(DISCOVERY_METHODS))

    if auth_method in AUTH_METHODS:
        validate_string(username)
        validate_string(password)
        discovery_wrapper(hostname, discovery_method, "new")
        discovery_wrapper(hostname, discovery_method, "update",
                          ("authmethod", "CHAP"))
        discovery_wrapper(hostname, discovery_method, "update",
                          ("username", username))
        discovery_wrapper(hostname, discovery_method, "update",
                          ("password", password))
        if auth_method == "mutual_chap":
            validate_string(username_in)
            validate_string(password_in)
            discovery_wrapper(hostname, discovery_method, "update",
                              ("username_in", username_in))
            discovery_wrapper(hostname, discovery_method, "update",
                              ("password_in", password_in))
    elif auth_method:
        raise TargetdError(INVALID_VALUE_AUTH, "Invalid value."
                           " Possible values are : %s" %
                           ", ".join(AUTH_METHODS))

    output = discovery_wrapper(hostname, discovery_method,
                               discover=True)

    return node_summary_parser(output)


def display_discovery(req, hostname, discovery_method="sendtargets"):
    """
    Returns a dictionary of all data for the
    discovery portal at the specified hostname
    """
    validate_string(hostname)
    if discovery_method not in DISCOVERY_METHODS:
        raise TargetdError(INVALID_VALUE_DISCOVERY, "Invalid value."
                           " Possible values are : %s" %
                           ", ".join(DISCOVERY_METHODS))

    output = discovery_wrapper(hostname, discovery_method)
    return discovery_node_parser(output, "discovery")


def display_discovery_summary(req):
    """
    Returns a dictionary of all data for
    all discovery records
    """
    output = discovery_wrapper()
    return discovery_summary_parser(output)


def delete_discovery(req, hostname, discovery_method="sendtargets"):
    """
    Delete discovery of targets at the specified hostname
    with the right discovery method
    """
    validate_string(hostname)
    if discovery_method not in DISCOVERY_METHODS:
        raise TargetdError(INVALID_VALUE_DISCOVERY, "Invalid value."
                           " Possible values are : %s" %
                           ", ".join(DISCOVERY_METHODS))

    output = discovery_wrapper(hostname, discovery_method, "delete")


def delete_all_discoveries():
    """
    Delete all discovery records
    """
    d = display_discovery_summary(None)
    for t in d:
        delete_discovery(None, t, d[t][-1])


def login_target(req, targetname, hostname=None, auth_method=None,
                 username=None, password=None, username_in=None,
                 password_in=None):
    """
    Login to a given target using specified informations
    """
    validate_string(targetname)
    if hostname:
        validate_string(hostname)
    if auth_method in AUTH_METHODS:
        validate_string(username)
        validate_string(password)
        node_wrapper(targetname, hostname, "update", ("authmethod", "CHAP"))
        node_wrapper(targetname, hostname, "update", ("username", username))
        node_wrapper(targetname, hostname, "update", ("password", password))
        if auth_method == "mutual_chap":
            validate_string(username_in)
            validate_string(password_in)
            node_wrapper(targetname, hostname, "update",
                         ("username_in", username_in))
            node_wrapper(targetname, hostname, "update",
                         ("password_in", password_in))
    elif auth_method:
        raise TargetdError(INVALID_VALUE_AUTH, "Invalid value."
                           " Possible values are : %s" %
                           ", ".join(AUTH_METHODS))
    output = node_wrapper(targetname, hostname, login_out="login")


def logout_target(req, targetname, hostname=None):
    """
    Logout for a given target using specified informations
    """
    validate_string(targetname)
    if hostname:
        validate_string(hostname)
    output = node_wrapper(targetname, hostname, login_out="logout")


def logout_all_targets(req):
    """
    Logout for all targets
    """
    output = node_wrapper(login_out="logout")


def display_node(req, targetname, hostname=None):
    """
    Returns a dictionary of all data for the
    discovery portal at the specified hostname
    """
    validate_string(targetname)
    if hostname:
        validate_string(hostname)
    output = node_wrapper(targetname, hostname)
    return discovery_node_parser(output, "node")


def display_node_summary(req):
    """
    Returns a dictionary of all data for
    all node records
    """
    output = node_wrapper()
    return node_summary_parser(output)


def delete_node(req, targetname, hostname=None):
    """
    Delete a given node record
    using specified informations
    """
    validate_string(targetname)
    if hostname:
        validate_string(hostname)
    output = node_wrapper(targetname, hostname, "delete")


def delete_all_nodes(req):
    """
    Delete all node records
    """
    output = node_wrapper(operation="delete")


def display_session(req, targetname=None, hostname=None):
    """
    Returns a dictionary of all data for all active sessions
    If a session is specified, returns a dictionary of all data
    for the given session using specified informations
    """
    output = session_wrapper()
    d = session_parser(output)
    if targetname and hostname:
        validate_string(targetname)
        validate_string(hostname)
        try:
            return {targetname: {hostname: d[targetname][hostname]}}
        except KeyError:
            raise TargetdError(NO_SESSION_INFO, "Could not get session info")
    elif targetname:
        validate_string(targetname)
        try:
            return {targetname: d[targetname]}
        except KeyError:
            raise TargetdError(NO_SESSION_INFO, "Could not get session info")
    else:
        return d


def purge(req):
    try:
        logout_all_targets(None)
    except TargetdError:
        pass
    try:
        delete_all_discoveries()
    except TargetdError:
        pass
    try:
        delete_all_nodes(None)
    except TargetdError:
        pass
