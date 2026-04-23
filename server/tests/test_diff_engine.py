import pytest
from server.config_collector.diff_engine import compute_diff, DiffResult, FieldChanged, FieldAdded, FieldRemoved, SecretChanged, RowAdded, RowRemoved, RowChanged

def test_object_mode_field_changed():
    a = {"name": "HQ", "vlan": 10}
    b = {"name": "HQ", "vlan": 20}
    result = compute_diff(a, b)
    assert result.shape == "object"
    assert len(result.changes) == 1
    assert isinstance(result.changes[0], FieldChanged)
    assert result.changes[0].key == "vlan"
    assert result.changes[0].before == 10
    assert result.changes[0].after == 20
    assert result.unchanged_count == 1

def test_object_mode_field_added():
    a = {"name": "HQ"}
    b = {"name": "HQ", "vlan": 20}
    result = compute_diff(a, b)
    assert len(result.changes) == 1
    assert isinstance(result.changes[0], FieldAdded)
    assert result.changes[0].key == "vlan"
    assert result.changes[0].value == 20

def test_object_mode_field_removed():
    a = {"name": "HQ", "vlan": 10}
    b = {"name": "HQ"}
    result = compute_diff(a, b)
    assert len(result.changes) == 1
    assert isinstance(result.changes[0], FieldRemoved)
    assert result.changes[0].key == "vlan"
    assert result.changes[0].value == 10

def test_object_mode_no_changes():
    a = {"name": "HQ", "vlan": 10}
    result = compute_diff(a, a)
    assert result.changes == []
    assert result.unchanged_count == 2

def test_object_mode_secret_field():
    a = {"psk_hash": "abc123"}
    b = {"psk_hash": "def456"}
    result = compute_diff(a, b)
    assert len(result.changes) == 1
    assert isinstance(result.changes[0], SecretChanged)
    assert result.changes[0].key == "psk_hash"

def test_object_mode_secret_unchanged_not_emitted():
    a = {"psk_hash": "abc123"}
    result = compute_diff(a, a)
    assert result.changes == []
    assert result.unchanged_count == 1

def test_object_mode_nested_dict():
    a = {"vpn": {"enabled": True, "mode": "hub"}}
    b = {"vpn": {"enabled": True, "mode": "spoke"}}
    result = compute_diff(a, b)
    assert result.shape == "object"
    assert len(result.changes) == 1
    assert isinstance(result.changes[0], FieldChanged)
    assert result.changes[0].key == "vpn.mode"
    assert result.changes[0].before == "hub"
    assert result.changes[0].after == "spoke"

def test_array_mode_row_added():
    a = {"vlans": [{"id": 1, "name": "Default"}]}
    b = {"vlans": [{"id": 1, "name": "Default"}, {"id": 40, "name": "Guest"}]}
    result = compute_diff(a, b)
    assert result.shape == "array"
    assert len(result.changes) == 1
    assert isinstance(result.changes[0], RowAdded)
    assert result.changes[0].identity == 40
    assert result.unchanged_count == 1

def test_array_mode_row_removed():
    a = {"vlans": [{"id": 1, "name": "Default"}, {"id": 40, "name": "Guest"}]}
    b = {"vlans": [{"id": 1, "name": "Default"}]}
    result = compute_diff(a, b)
    assert len(result.changes) == 1
    assert isinstance(result.changes[0], RowRemoved)
    assert result.changes[0].identity == 40

def test_array_mode_row_changed():
    a = {"vlans": [{"id": 1, "name": "Default", "subnet": "10.0.0.0/24"}]}
    b = {"vlans": [{"id": 1, "name": "Default", "subnet": "10.1.0.0/24"}]}
    result = compute_diff(a, b)
    assert len(result.changes) == 1
    assert isinstance(result.changes[0], RowChanged)
    assert result.changes[0].identity == 1
    fc = result.changes[0].field_changes
    assert len(fc) == 1
    assert isinstance(fc[0], FieldChanged)
    assert fc[0].key == "subnet"

def test_array_mode_ssid_uses_number_key():
    a = {"ssids": [{"number": 0, "name": "Corp"}, {"number": 1, "name": "Guest"}]}
    b = {"ssids": [{"number": 0, "name": "Corp-Updated"}, {"number": 1, "name": "Guest"}]}
    result = compute_diff(a, b)
    assert len(result.changes) == 1
    assert result.changes[0].identity == 0

def test_array_mode_firewall_uses_position():
    a = {"appliance_firewall_l3": [{"comment": "rule1"}, {"comment": "rule2"}]}
    b = {"appliance_firewall_l3": [{"comment": "rule1"}, {"comment": "rule2-changed"}]}
    result = compute_diff(a, b)
    assert len(result.changes) == 1
    assert result.changes[0].identity == 1  # position index

def test_array_mode_unchanged_rows_counted():
    a = {"vlans": [{"id": 1}, {"id": 2}, {"id": 3}]}
    result = compute_diff(a, a)
    assert result.changes == []
    assert result.unchanged_count == 3

def test_array_mode_switch_ports_uses_portId():
    a = {"switch_device_ports": [{"portId": "1", "vlan": 10}]}
    b = {"switch_device_ports": [{"portId": "1", "vlan": 20}]}
    result = compute_diff(a, b)
    assert len(result.changes) == 1
    assert result.changes[0].identity == "1"
