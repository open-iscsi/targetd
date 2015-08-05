import json
from targetd.utils import TargetdError, invoke
import pytest
from targetd.iscsi_init import discovery_node_parser, discovery_summary_parser
from targetd.iscsi_init import node_summary_parser, session_parser
from targetd.iscsi_init import validate_string, delete_discovery
from targetd.iscsi_init import display_discovery, discover_portal
from targetd.iscsi_init import login_target, logout_target, delete_node
from test_iscsi_init_attributes import DISCOVERY_OUTPUT
from test_iscsi_init_attributes import DISCOVERY_PARSED
from test_iscsi_init_attributes import NODE_OUTPUT
from test_iscsi_init_attributes import NODE_PARSED
from test_iscsi_init_attributes import DISCOVERY_SUMMARY_OUTPUT
from test_iscsi_init_attributes import DISCOVERY_SUMMARY_PARSED
from test_iscsi_init_attributes import NODE_SUMMARY_OUTPUT
from test_iscsi_init_attributes import NODE_SUMMARY_PARSED
from test_iscsi_init_attributes import SESSION_OUTPUT
from test_iscsi_init_attributes import SESSION_PARSED
# to run tests : sudo py.test -q test_discovery_iscsi_init.py

return_code, output_success, output_fail = invoke(["which", "iscsiadm"], False)


class TestDiscoveryNodeParser:
    def test_discovery_parser(self):
        d = discovery_node_parser(DISCOVERY_OUTPUT, "discovery")
        assert d == DISCOVERY_PARSED

    def test_node_parser(self):
        d = discovery_node_parser(NODE_OUTPUT, "node")
        assert d == NODE_PARSED


def test_discovery_summary_parser():
    d = discovery_summary_parser(DISCOVERY_SUMMARY_OUTPUT)
    assert d == DISCOVERY_SUMMARY_PARSED


def test_node_summary_parser():
    d = node_summary_parser(NODE_SUMMARY_OUTPUT)
    assert d == NODE_SUMMARY_PARSED


def test_session_parser():
    d = session_parser(SESSION_OUTPUT)
    assert d == SESSION_PARSED


class TestValidateString:
    def test_empty_string(self):
        with pytest.raises(TargetdError) as td:
            validate_string("")
        assert str(td.value) == 'Unauthorised empty string'

    def test_string_too_long(self):
        with pytest.raises(TargetdError) as td:
            validate_string("1"*256)
        assert str(td.value) == 'String too long'

    def test_not_ascii_encoded(self):
        with pytest.raises(TargetdError) as td:
            validate_string("\xea\x80\x80abcd\xde\xb4")
        assert str(td.value) == 'Not a ascii-encoded unicode string'


class TestDeleteDiscovery:
    if output_success:
        def test_record_not_found(self):
            with pytest.raises(TargetdError) as td:
                delete_discovery(None, "essai")
            assert str(td.value) == 'Discovery record [essai,3260] not found.'

        def test_discovery_method_error(self):
            with pytest.raises(TargetdError) as td:
                delete_discovery(None, "192.168.122.237", "test")
            assert str(td.value) == ('Invalid value. Possible values'
                                     ' are : sendtargets, isns')

    def test_validate_string_one(self):
        with pytest.raises(TargetdError) as td:
            delete_discovery(None, "")
        assert str(td.value) == 'Unauthorised empty string'

    def test_validate_string_two(self):
        with pytest.raises(TargetdError) as td:
            delete_discovery(None, "1"*256)
        assert str(td.value) == 'String too long'

    def test_validate_string_three(self):
        with pytest.raises(TargetdError) as td:
            delete_discovery(None, "\xea\x80\x80abcd\xde\xb4")
        assert str(td.value) == 'Not a ascii-encoded unicode string'


class TestDisplayDiscovery:
    if output_success:
        def test_record_not_found(self):
            with pytest.raises(TargetdError) as td:
                display_discovery(None, "test")
            assert str(td.value) == 'Discovery record [test,3260] not found.'

        def test_discovery_method_error(self):
            with pytest.raises(TargetdError) as td:
                display_discovery(None, "192.168.122.237", "test")
            assert str(td.value) == ('Invalid value. Possible values'
                                     ' are : sendtargets, isns')

    def test_validate_string_one(self):
        with pytest.raises(TargetdError) as td:
            display_discovery(None, "")
        assert str(td.value) == 'Unauthorised empty string'

    def test_validate_string_two(self):
        with pytest.raises(TargetdError) as td:
            display_discovery(None, "1"*256)
        assert str(td.value) == 'String too long'

    def test_validate_string_three(self):
        with pytest.raises(TargetdError) as td:
            display_discovery(None, "\xea\x80\x80abcd\xde\xb4")
        assert str(td.value) == 'Not a ascii-encoded unicode string'


class TestDiscoverPortal:
    if output_success:
        def test_no_connection(self):
            with pytest.raises(TargetdError) as td:
                discover_portal(None, "192.168.122.237")
            delete_discovery(None, "192.168.122.237")
            assert str(td.value) == ('cannot make connection to '
                                     '192.168.122.237: No route to host')

        def test_discovery_method_error(self):
            with pytest.raises(TargetdError) as td:
                discover_portal(None, "192.168.122.237", "test")
            assert str(td.value) == ('Invalid value. Possible values'
                                     ' are : sendtargets, isns')

        def test_auth_method_error(self):
            with pytest.raises(TargetdError) as td:
                discover_portal(None, "192.168.122.237", "sendtargets", "test")
            assert str(td.value) == ('Invalid value. Possible values are'
                                     ' : chap, mutual_chap')

    def test_validate_string_one(self):
        with pytest.raises(TargetdError) as td:
            discover_portal(None, "")
        assert str(td.value) == 'Unauthorised empty string'

    def test_validate_string_two(self):
        with pytest.raises(TargetdError) as td:
            discover_portal(None, "1"*256)
        assert str(td.value) == 'String too long'

    def test_validate_string_three(self):
        with pytest.raises(TargetdError) as td:
            discover_portal(None, "\xea\x80\x80abcd\xde\xb4")
        assert str(td.value) == 'Not a ascii-encoded unicode string'


class TestLoginTarget:
    if output_success:
        def test_no_records_found(self):
            with pytest.raises(TargetdError) as td:
                login_target(None, "iqn")
            assert str(td.value) == ('No records found')

        def test_auth_method_error(self):
            with pytest.raises(TargetdError) as td:
                login_target(None, "iqn", None, "test")
            assert str(td.value) == ('Invalid value. Possible values are'
                                     ' : chap, mutual_chap')

    def test_validate_string_one(self):
        with pytest.raises(TargetdError) as td:
            login_target(None, "")
        assert str(td.value) == 'Unauthorised empty string'

    def test_validate_string_two(self):
        with pytest.raises(TargetdError) as td:
            login_target(None, "1"*256)
        assert str(td.value) == 'String too long'

    def test_validate_string_three(self):
        with pytest.raises(TargetdError) as td:
            login_target(None, "\xea\x80\x80abcd\xde\xb4")
        assert str(td.value) == 'Not a ascii-encoded unicode string'


class TestLogoutTarget:
    if output_success:
        def test_no_sessions_found(self):
            with pytest.raises(TargetdError) as td:
                logout_target(None, "iqn")
            assert str(td.value) == ('No matching sessions found')

    def test_validate_string_one(self):
        with pytest.raises(TargetdError) as td:
            logout_target(None, "")
        assert str(td.value) == 'Unauthorised empty string'

    def test_validate_string_two(self):
        with pytest.raises(TargetdError) as td:
            logout_target(None, "1"*256)
        assert str(td.value) == 'String too long'

    def test_validate_string_three(self):
        with pytest.raises(TargetdError) as td:
            logout_target(None, "\xea\x80\x80abcd\xde\xb4")
        assert str(td.value) == 'Not a ascii-encoded unicode string'


class TestDeleteNode:
    if output_success:
        def test_no_records_found(self):
            with pytest.raises(TargetdError) as td:
                delete_node(None, "iqn")
            assert str(td.value) == ('No records found')

    def test_validate_string_one(self):
        with pytest.raises(TargetdError) as td:
            delete_node(None, "")
        assert str(td.value) == 'Unauthorised empty string'

    def test_validate_string_two(self):
        with pytest.raises(TargetdError) as td:
            delete_node(None, "1"*256)
        assert str(td.value) == 'String too long'

    def test_validate_string_three(self):
        with pytest.raises(TargetdError) as td:
            delete_node(None, "\xea\x80\x80abcd\xde\xb4")
        assert str(td.value) == 'Not a ascii-encoded unicode string'
