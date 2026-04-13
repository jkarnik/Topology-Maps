# Fortinet SD-Branch Design: High-Density Retail (40k sqft)

## 1. Store Profile
* **Size:** 40,000 sqft (4 Floors x 10,000 sqft)
* **Peak Load:** 10,000 concurrent guests + 90 employees
* **Focus:** Security-first retail (PCI-DSS), high-density Wi-Fi 7, and unified SNMP/API monitoring.

---

## 2. Infrastructure Bill of Materials (BOM)

| Component | Model | Quantity | Role | New Relic Integration Hook |
| :--- | :--- | :---: | :--- | :--- |
| **SD-WAN / Firewall** | **FortiGate 200G** | 2 | Secure Edge & Controller (HA Pair). | FortiOS API / SNMP (All OIDs). |
| **Core Switch** | **FortiSwitch 1024E** | 1 | 10G SFP+ Aggregation. | Interface stats & SFP diagnostics. |
| **Floor Switches** | **FortiSwitch 448E-FPOE** | 4 | 48-port Full PoE (802.3at/bt). | PoE Power draw & VLAN tagging. |
| **Access Points** | **FortiAP 431K** | 56 | Wi-Fi 7 (Tri-Radio) High-Density. | Client Dwell Time & RSSI via API. |

---

## 3. Retail Endpoints & IoT Peripherals

To fully map the store's ecosystem in New Relic, we must classify the edge devices. The FortiGate acts as the gateway, identifying and segmenting these devices automatically using **Device Fingerprinting**.

| Category | Typical Devices (Examples) | Estimated Quantity | Network Connection | New Relic NPM Monitoring Focus |
| :--- | :--- | :---: | :--- | :--- |
| **Payment (PCI)** | POS Terminals (Verifone/Ingenico), Mobile POS (Square/Adyen), Receipt Printers | 30–50 | Wired (VLAN 10) & Secured Wi-Fi | End-to-end latency to payment gateways; TCP retransmission rates. |
| **Operations** | Inventory PCs, Back-office workstations, Network Printers (HP/Zebra) | 10–15 | Wired (VLAN 20) | Bandwidth utilization; DNS resolution times for internal apps. |
| **Employee Mobility** | Handheld Scanners (Zebra TC series), VoIP Badges (Vocera) | 90 | Corporate Wi-Fi (802.1x) | Wi-Fi Roaming health across floors; Client RSSI (Signal Strength). |
| **Security & Safety** | IP Cameras (Axis/Verkada), NVRs, Access Control Systems | 40–60 | PoE Wired (VLAN 40) | Port-level PoE power draw monitoring; constant high-bandwidth baseline anomalies. |
| **Retail IoT** | Digital Signage, Smart HVAC/BMS, Environmental Sensors (Temp/Humidity), ESL (Electronic Shelf Labels) | 100+ | Wired/Wi-Fi (VLAN 50) | Status checks via Webhooks; MAC address tracking; low-bandwidth keepalives. |
| **Guest Network** | Customer Mobiles, Tablets, Wearables | ~10,000 (Peak) | Guest Wi-Fi (Captive Portal) | DHCP pool exhaustion alerts; AP load balancing; total Guest bandwidth tracking. |

---

## 4. Deployment Architecture

### A. The "FortiLink" Advantage & Device Fingerprinting
All FortiSwitches and FortiAPs are managed via **FortiLink**. 
* **Dynamic Port Policies:** When a Verifone POS is plugged into a floor switch, Fortinet identifies the MAC/OS and automatically assigns it to the isolated PCI VLAN.
* **Unified Monitoring:** Instead of polling endpoints directly, New Relic queries the **FortiGate 200G** to receive the health, IP assignment, and device type of every peripheral connected.

### B. High-Density Capacity Management
* **Wi-Fi 7 (431K):** Selected to handle the 10,000 peak footfall alongside 90 employee handhelds.
* **QoS (Quality of Service):** Employee scanners and POS systems are prioritized over customer iPhones streaming video on the Guest Wi-Fi to ensure no operations drop during Black Friday rushes.

---

## 5. Monitoring Strategy (New Relic NPM Refresh)

Integrating the peripheral layer provides the ultimate "Full Stack" view for store managers.

### 1. Unified SNMP & API Aggregation
* **PoE Budgeting:** IP Cameras, Smart Displays, and APs draw significant power. New Relic can poll the FortiSwitches via SNMP to alert when a switch is nearing its maximum PoE budget limit, preventing a camera reboot.
* **Application Signatures:** Using Fortinet's Layer 7 visibility, New Relic can ingest APIs that track exactly what applications the endpoints are using (e.g., "Guest Wi-Fi is consuming 80% bandwidth via TikTok").

### 2. Peripheral-Specific Webhooks
* **Zebra / Handheld Integrations:** Many modern handhelds support direct Webhooks to NPM platforms regarding battery health and dropped packets.
* **Environmental Alerts:** Smart sensors can push instant Webhooks to New Relic if server room temperatures spike or if a freezer in the back-office fails.

---

## 6. Security & Compliance (Retail Focus)
> **Zero Trust Network Access (ZTNA):** By profiling every peripheral, the network ensures an Environmental Sensor cannot "talk" to a POS Terminal. If an IP Camera is compromised by malware, Fortinet instantly quarantines the port and pushes an alert to your New Relic dashboard, ensuring PCI-DSS isolation remains intact during a 10,000-guest peak.