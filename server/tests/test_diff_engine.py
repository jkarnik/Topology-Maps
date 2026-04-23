import pytest
from server.config_collector.diff_engine import compute_diff, DiffResult, FieldChanged, FieldAdded, FieldRemoved, SecretChanged

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
