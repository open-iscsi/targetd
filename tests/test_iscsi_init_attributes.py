DISCOVERY_OUTPUT = """
# BEGIN RECORD 2.0-873
discovery.startup = manual
discovery.type = sendtargets
discovery.sendtargets.address = 192.168.122.239
discovery.sendtargets.port = 3260
discovery.sendtargets.auth.authmethod = None
discovery.sendtargets.auth.username = <empty>
discovery.sendtargets.auth.password = <empty>
discovery.sendtargets.auth.username_in = <empty>
discovery.sendtargets.auth.password_in = <empty>
discovery.sendtargets.timeo.login_timeout = 15
discovery.sendtargets.use_discoveryd = No
discovery.sendtargets.discoveryd_poll_inval = 30
discovery.sendtargets.reopen_max = 5
discovery.sendtargets.timeo.auth_timeout = 44
discovery.sendtargets.timeo.active_timeout = 30
discovery.sendtargets.iscsi.MaxRecvDataSegmentLength = 32768
# END RECORD
"""

DISCOVERY_PARSED = {"type": "sendtargets", "startup": "manual",
                    "sendtargets": {"use_discoveryd": "No",
                                    "reopen_max": "5",
                                    "auth": {"username": "",
                                             "username_in": "",
                                             "password": "",
                                             "authmethod": "None",
                                             "password_in": ""},
                                    "discoveryd_poll_inval": "30",
                                    "timeo": {"active_timeout": "30",
                                              "auth_timeout": "44",
                                              "login_timeout": "15"},
                                    "address": "192.168.122.239",
                                    "port": "3260",
                                    "iscsi": {"MaxRecvData"
                                              "SegmentLength": "32768"}}}

NODE_OUTPUT = """
# BEGIN RECORD 2.0-873
node.name = iqn.2003-01.org.linux-iscsi.vb.x8664:sn.a5cb3c86aadd
node.tpgt = 1
node.startup = automatic
node.leading_login = No
iface.hwaddress = <empty>
iface.ipaddress = <empty>
iface.iscsi_ifacename = default
iface.net_ifacename = <empty>
iface.transport_name = tcp
iface.initiatorname = <empty>
iface.bootproto = <empty>
iface.subnet_mask = <empty>
iface.gateway = <empty>
iface.ipv6_autocfg = <empty>
iface.linklocal_autocfg = <empty>
iface.router_autocfg = <empty>
iface.ipv6_linklocal = <empty>
iface.ipv6_router = <empty>
iface.state = <empty>
iface.vlan_id = 0
iface.vlan_priority = 0
iface.vlan_state = <empty>
iface.iface_num = 0
iface.mtu = 0
iface.port = 0
node.discovery_address = 192.168.122.239
node.discovery_port = 3260
node.discovery_type = send_targets
node.session.initial_cmdsn = 0
node.session.initial_login_retry_max = 8
node.session.xmit_thread_priority = -20
node.session.cmds_max = 128
node.session.queue_depth = 32
node.session.nr_sessions = 1
node.session.auth.authmethod = None
node.session.auth.username = <empty>
node.session.auth.password = <empty>
node.session.auth.username_in = <empty>
node.session.auth.password_in = <empty>
node.session.timeo.replacement_timeout = 120
node.session.err_timeo.abort_timeout = 15
node.session.err_timeo.lu_reset_timeout = 30
node.session.err_timeo.tgt_reset_timeout = 30
node.session.err_timeo.host_reset_timeout = 60
node.session.iscsi.FastAbort = Yes
node.session.iscsi.InitialR2T = No
node.session.iscsi.ImmediateData = Yes
node.session.iscsi.FirstBurstLength = 262144
node.session.iscsi.MaxBurstLength = 16776192
node.session.iscsi.DefaultTime2Retain = 0
node.session.iscsi.DefaultTime2Wait = 2
node.session.iscsi.MaxConnections = 1
node.session.iscsi.MaxOutstandingR2T = 1
node.session.iscsi.ERL = 0
node.conn[0].address = 192.168.122.239
node.conn[0].port = 3260
node.conn[0].startup = manual
node.conn[0].tcp.window_size = 524288
node.conn[0].tcp.type_of_service = 0
node.conn[0].timeo.logout_timeout = 15
node.conn[0].timeo.login_timeout = 15
node.conn[0].timeo.auth_timeout = 45
node.conn[0].timeo.noop_out_interval = 5
node.conn[0].timeo.noop_out_timeout = 5
node.conn[0].iscsi.MaxXmitDataSegmentLength = 0
node.conn[0].iscsi.MaxRecvDataSegmentLength = 262144
node.conn[0].iscsi.HeaderDigest = None
node.conn[0].iscsi.DataDigest = None
node.conn[0].iscsi.IFMarker = No
node.conn[0].iscsi.OFMarker = No
# END RECORD
"""

NODE_PARSED = {"name": "iqn.2003-01.org.linux-iscsi.vb.x8664:sn.a5cb3c86aadd",
               "discovery_address": "192.168.122.239",
               "discovery_type": "send_targets",
               "startup": "automatic", "discovery_port": "3260",
               "leading_login": "No",
               "session": {"initial_cmdsn": "0",
                           "queue_depth": "32",
                           "iscsi": {"ImmediateData": "Yes",
                                     "MaxOutstandingR2T": "1",
                                     "InitialR2T": "No",
                                     "DefaultTime2Retain": "0",
                                     "FirstBurstLength": "262144",
                                     "FastAbort": "Yes",
                                     "DefaultTime2Wait": "2",
                                     "MaxConnections": "1", "ERL": "0",
                                     "MaxBurstLength": "16776192"},
                           "auth": {"username": "", "username_in": "",
                                    "password": "", "authmethod": "None",
                                    "password_in": ""},
                           "nr_sessions": "1", "initial_login_retry_max": "8",
                           "timeo": {"replacement_timeout": "120"},
                           "xmit_thread_priority": "-20",
                           "err_timeo": {"tgt_reset_timeout": "30",
                                         "host_reset_timeout": "60",
                                         "abort_timeout": "15",
                                         "lu_reset_timeout": "30"},
                           "cmds_max": "128"},
               "conn[0]": {"iscsi": {"OFMarker": "No", "DataDigest": "None",
                                     "IFMarker": "No",
                                     "MaxRecvDataSegmentLength": "262144",
                                     "HeaderDigest": "None",
                                     "MaxXmitDataSegmentLength": "0"},
                           "startup": "manual",
                           "tcp": {"type_of_service": "0",
                                   "window_size": "524288"},
                           "timeo": {"noop_out_timeout": "5",
                                     "noop_out_interval": "5",
                                     "logout_timeout": "15",
                                     "auth_timeout": "45",
                                     "login_timeout": "15"},
                           "address": "192.168.122.239", "port": "3260"},
               "tpgt": "1"}

DISCOVERY_SUMMARY_OUTPUT = """
192.168.122.23:3260 via sendtargets
test:3260 via sendtargets
192.168.122.239:3260 via sendtargets
192.168.122.255:3205 via isns
"""

DISCOVERY_SUMMARY_PARSED = {'192.168.122.255': (3205, 'isns'),
                            '192.168.122.23': (3260, 'sendtargets'),
                            '192.168.122.239': (3260, 'sendtargets'),
                            'test': (3260, 'sendtargets')}

NODE_SUMMARY_OUTPUT = """
Target: iqn.2003-01.org.linux-iscsi.vb.x8664:sn.a5cb3c86aadd
    Portal: 192.168.122.239:3260,1
        Iface Name: default
Target: iqn.2003-01.org.linux-iscsi.vb.x8664:sn.36311f944591
    Portal: 192.168.122.239:3260,1
        Iface Name: default
    Portal: 192.168.122.240:3260,1
        Iface Name: default
Target: iqn.2003-01.org.linux-iscsi.vb.x8664:sn.e824acd0142c
    Portal: 192.168.122.239:3260,1
        Iface Name: default
"""

NODE_SUMMARY_PARSED = {'iqn.2003-01.org.linux-iscsi.vb.x8664:sn.36311f94459'
                       '1': {'192.168.122.239': {'interface': 'default',
                                                 'portal': ('192.168.122.239',
                                                            3260, 1)},
                             '192.168.122.240': {'interface': 'default',
                                                 'portal': ('192.168.122.240',
                                                            3260, 1)}},
                       'iqn.2003-01.org.linux-iscsi.vb.x8664:sn.a5cb3c86aad'
                       'd': {'192.168.122.239': {'interface': 'default',
                                                 'portal': ('192.168.122.239',
                                                            3260, 1)}},
                       'iqn.2003-01.org.linux-iscsi.vb.x8664:sn.e824acd0142'
                       'c': {'192.168.122.239': {'interface': 'default',
                                                 'portal': ('192.168.122.239',
                                                            3260, 1)}}}

SESSION_OUTPUT = """
Target: iqn.2003-01.org.linux-iscsi.vb.x8664:sn.36311f944591
    Current Portal: 192.168.122.239:3260,1
    Persistent Portal: 192.168.122.239:3260,1
        **********
        Interface:
        **********
        Iface Name: default
        Iface Transport: tcp
        Iface Initiatorname: iqn.1991-05.com.microsoft:ibm-t410s
        Iface IPaddress: 192.168.122.1
        Iface HWaddress: <empty>
        Iface Netdev: <empty>
        SID: 13
        iSCSI Connection State: LOGGED IN
        iSCSI Session State: LOGGED_IN
        Internal iscsid Session State: NO CHANGE
Target: iqn.2003-01.org.linux-iscsi.vb.x8664:sn.a5cb3c86aadd
    Current Portal: 192.168.122.239:3260,1
    Persistent Portal: 192.168.122.239:3260,1
        **********
        Interface:
        **********
        Iface Name: default
        Iface Transport: tcp
        Iface Initiatorname: iqn.1991-05.com.microsoft:ibm-t410s
        Iface IPaddress: 192.168.122.1
        Iface HWaddress: <empty>
        Iface Netdev: <empty>
        SID: 15
        iSCSI Connection State: LOGGED IN
        iSCSI Session State: LOGGED_IN
        Internal iscsid Session State: NO CHANGE
"""

SESSION_PARSED = {"iqn.2003-01.org.linux-iscsi.vb.x8664:sn.36311f94459"
                  "1": {"192.168."
                        "122.239": {"connection_state": "LOGGED IN",
                                    "session_state": "LOGGED_IN",
                                    "initiator_name": "iqn.1991-05.com."
                                    "microsoft:ibm-t410s",
                                    "session_id": "13",
                                    "portal": ("192.168.122.239", 3260, 1),
                                    "iscsid_session_state": "NO CHANGE",
                                    "ip_address": "192.168.122.1",
                                    "transport": "tcp"}},
                  "iqn.2003-01.org.linux-iscsi.vb.x8664:sn.a5cb3c86aad"
                  "d": {"192.168."
                        "122.239": {"connection_state": "LOGGED IN",
                                    "session_state": "LOGGED_IN",
                                    "initiator_name": "iqn.1991-05.com."
                                    "microsoft:ibm-t410s",
                                    "session_id": "15",
                                    "portal": ("192.168.122.239", 3260, 1),
                                    "iscsid_session_state": "NO CHANGE",
                                    "ip_address": "192.168.122.1",
                                    "transport": "tcp"}}}
