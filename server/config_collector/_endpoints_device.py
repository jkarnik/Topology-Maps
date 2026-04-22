"""Device-level endpoint definitions (Plan 1.04)."""
from __future__ import annotations

from server.config_collector.endpoints_catalog import EndpointSpec

DEVICE_ENDPOINTS: tuple[EndpointSpec, ...] = (
    # All products
    EndpointSpec("device_metadata",                "device", "/devices/{serial}",                         (), 1, False),
    EndpointSpec("device_management_interface",    "device", "/devices/{serial}/managementInterface",     (), 1, False),
    # MS
    EndpointSpec("switch_device_ports",            "device", "/devices/{serial}/switch/ports",             ("switch",),    1, False),
    EndpointSpec("switch_device_routing_interfaces","device","/devices/{serial}/switch/routing/interfaces",("switch",),    2, False),
    EndpointSpec("switch_device_routing_static_routes","device","/devices/{serial}/switch/routing/staticRoutes",("switch",),2, False),
    EndpointSpec("switch_device_warm_spare",       "device", "/devices/{serial}/switch/warmSpare",          ("switch",),    2, False),
    # MR
    EndpointSpec("wireless_device_radio_settings", "device", "/devices/{serial}/wireless/radio/settings",   ("wireless",),  1, False),
    EndpointSpec("wireless_device_bluetooth",      "device", "/devices/{serial}/wireless/bluetooth/settings",("wireless",), 2, False),
    # MX
    EndpointSpec("appliance_device_uplinks",       "device", "/devices/{serial}/appliance/uplinks/settings",("appliance",), 1, False),
    # MV
    EndpointSpec("camera_device_quality_retention","device", "/devices/{serial}/camera/qualityAndRetention",("camera",),    2, False),
    EndpointSpec("camera_device_video_settings",   "device", "/devices/{serial}/camera/videoSettings",      ("camera",),    2, False),
    EndpointSpec("camera_device_sense",            "device", "/devices/{serial}/camera/sense",              ("camera",),    2, False),
)
