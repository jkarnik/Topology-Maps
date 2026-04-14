"""Shared constants for the network topology simulator."""

import os

# SNMP Configuration
SNMP_COMMUNITY = "public"
SNMP_VERSION = 1  # v2c (0-indexed in pysnmp)

# Device IP Assignments (simulated)
DEVICE_IPS = {
    "fg-primary": "10.0.0.1",
    "fg-standby": "10.0.0.2",
    "core-sw": "10.0.1.1",
    "floor-sw-1": "10.0.1.11",
    "floor-sw-2": "10.0.1.12",
    "floor-sw-3": "10.0.1.13",
    "floor-sw-4": "10.0.1.14",
}

# SNMP Agent UDP Ports (all on localhost)
SNMP_PORTS = {
    "fg-primary": 10161,
    "fg-standby": 10162,
    "core-sw": 10163,
    "floor-sw-1": 10164,
    "floor-sw-2": 10165,
    "floor-sw-3": 10166,
    "floor-sw-4": 10167,
}

# Device Models
DEVICE_MODELS = {
    "fg-primary": "FortiGate 200G",
    "fg-standby": "FortiGate 200G",
    "core-sw": "FortiSwitch 1024E",
    "floor-sw-1": "FortiSwitch 448E-FPOE",
    "floor-sw-2": "FortiSwitch 448E-FPOE",
    "floor-sw-3": "FortiSwitch 448E-FPOE",
    "floor-sw-4": "FortiSwitch 448E-FPOE",
}

# Device Types
DEVICE_TYPES = {
    "fg-primary": "firewall",
    "fg-standby": "firewall",
    "core-sw": "core_switch",
    "floor-sw-1": "floor_switch",
    "floor-sw-2": "floor_switch",
    "floor-sw-3": "floor_switch",
    "floor-sw-4": "floor_switch",
}

# Floor assignments
DEVICE_FLOORS = {
    "floor-sw-1": 1,
    "floor-sw-2": 2,
    "floor-sw-3": 3,
    "floor-sw-4": 4,
}

# APs: 14 per floor, 56 total
APS_PER_FLOOR = 14
TOTAL_FLOORS = 4
TOTAL_APS = APS_PER_FLOOR * TOTAL_FLOORS

# AP IP range: 10.0.1.101 - 10.0.1.156
AP_BASE_IP = "10.0.1"
AP_IP_START = 101

# VLAN Configuration
VLANS = {
    10: {"name": "PCI / Payment", "cidr": "10.10.10.0/24", "category": "payment"},
    20: {"name": "Operations", "cidr": "10.10.20.0/24", "category": "operations"},
    30: {"name": "Employee Wi-Fi", "cidr": "10.10.30.0/23", "category": "employee"},
    40: {"name": "Security & Safety", "cidr": "10.10.40.0/24", "category": "security"},
    50: {"name": "Retail IoT", "cidr": "10.10.50.0/23", "category": "iot"},
    60: {"name": "Guest Wi-Fi", "cidr": "172.16.0.0/20", "category": "guest"},
}

# Endpoint counts per VLAN (approximate targets)
ENDPOINT_COUNTS = {
    10: 40,   # POS / Payment
    20: 12,   # Operations PCs
    30: 90,   # Employee Handhelds (wireless)
    40: 50,   # IP Cameras / Security
    50: 110,  # IoT (signage, sensors, ESL)
    60: 850,  # Guest Wi-Fi (concurrent)
}

# Wired endpoint VLANs (connected to floor switches)
WIRED_VLANS = [10, 20, 40, 50]

# Wireless endpoint VLANs (connected via APs)
WIRELESS_VLANS = [30, 60]

# Service ports
SIMULATOR_REST_PORT = int(os.environ.get("SIMULATOR_REST_PORT", "8001"))
SERVER_HTTP_PORT = int(os.environ.get("SERVER_HTTP_PORT", "8000"))
UI_PORT = int(os.environ.get("UI_PORT", "5173"))

# Simulator host (for collector/server to reach simulator REST API)
SIMULATOR_HOST = os.environ.get("SIMULATOR_HOST", "localhost")
SERVER_HOST = os.environ.get("SERVER_HOST", "localhost")

# Collector polling interval (seconds)
POLL_INTERVAL = 5

# Roaming configuration
ROAMING_INTERVAL_MIN = 3  # seconds
ROAMING_INTERVAL_MAX = 5  # seconds
ROAMING_BATCH_MIN = 2     # clients per tick
ROAMING_BATCH_MAX = 5     # clients per tick

# Roaming probabilities by device type
ROAMING_SAME_FLOOR = {
    "employee": 0.70,
    "guest": 0.85,
}
ROAMING_CROSS_FLOOR = {
    "employee": 0.30,
    "guest": 0.15,
}

# Inter-VLAN routing policies
ROUTING_POLICIES = [
    {"from_vlan": 10, "to_vlan": 20, "policy": "allow"},
    {"from_vlan": 10, "to_vlan": 60, "policy": "deny"},
    {"from_vlan": 20, "to_vlan": 10, "policy": "allow"},
    {"from_vlan": 20, "to_vlan": 30, "policy": "allow"},
    {"from_vlan": 30, "to_vlan": 20, "policy": "allow"},
    {"from_vlan": 30, "to_vlan": 60, "policy": "deny"},
    {"from_vlan": 40, "to_vlan": 20, "policy": "allow"},
    {"from_vlan": 50, "to_vlan": 20, "policy": "allow"},
    {"from_vlan": 60, "to_vlan": "internet", "policy": "allow"},
]
