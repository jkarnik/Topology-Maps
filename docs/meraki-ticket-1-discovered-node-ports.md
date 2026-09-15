# Meraki support ticket 1 of 2 — `discovered` (non-Meraki) node ports

## Subject

`/networks/{id}/topology/linkLayer` reports incorrect, replicated, transposed or `null` port IDs
whenever the neighbour is a non-Meraki `discovered` node — verified against `/devices/{serial}/lldpCdp`

## Environment and reproduction

- **Organization ID:** 225248
- **API:** Dashboard API v1, `https://api.meraki.com/api/v1`
- **Captured:** 2026-09-10 / 2026-09-11 UTC. All calls returned HTTP 200.
- **Scope of comparison:** all 10 networks / 149 devices in the org. `linkLayer` returned 92 links;
  `lldpCdp` returned 400 port-neighbour records.

Two calls reproduce everything below:

```
GET /networks/{networkId}/topology/linkLayer     # 1 per network
GET /devices/{serial}/lldpCdp                    # 1 per device
```

Networks referenced in this ticket:

| Network | networkId |
|---|---|
| BCN211D | `N_652458996015301075` |
| PDX111F - Portland | `L_652458996015307801` |
| London - Strand House | `L_652458996015302502` |

Wherever the two endpoints disagree, `lldpCdp` matches the switch's own interface descriptions.
**Across the org, all 28 observations involving a non-Meraki neighbour disagreed with `lldpCdp`.**
Serials for every device named are tabulated at the end.

---

## Symptom 1 — One device's port number is replicated onto every link at the site

BCN211D: 9 × CW9176I / CW9172I APs (`wireless-32-2-4`) uplinked to a **Juniper EX4300-48P**
(JUNOS 20.4R3-S2.6), not Meraki-managed.

`linkLayer` returns the right number of links (9) and the right neighbour, but reports the **same
port, `866` / `BCN211D-22AP02`, on all 9 of them**. That is AP-02's genuine port, replicated to the
other eight. `lldpCdp` returns nine distinct, correct ports — and the switch's own interface
descriptions independently confirm each mapping:

| AP | linkLayer port | lldpCdp port | switch interface description |
|---|---|---|---|
| bcn211d-22ap-02 | 866 | 866 | BCN211D-22AP02 |
| bcn211d-22ap-03 | 866 | 836 | BCN211D-22AP03 |
| bcn211d-22ap-04 | 866 | 840 | BCN211D-22AP04 |
| bcn211d-22ap-05 | 866 | 845 | BCN211D-22AP05 |
| bcn211d-22ap-06 | 866 | 849 | BCN211D-22AP06 |
| bcn211d-22ap-07 | 866 | 852 | BCN211D-22AP07 |
| bcn211d-22ap-09 | 866 | 859 | BCN211D-22AP09 |
| bcn211d-22ap-08 | 866 | 954 | BCN211D-AP08_270 |
| bcn211d-22ap-mdf | 866 | 869 | ge-3/0/19 |

## Symptom 2 — The two ends of the link are transposed

In that same BCN211D response the values sit on the wrong ends: the **AP's** end carries `866`
(a Juniper port number, not an AP port), and the **Juniper's** end carries `Port 0` (the AP's own
uplink port name).

Where the neighbour *is* Meraki-managed the same endpoint gets this right — at LON138S the switch
end carries the switch port (19 / 20 / 22) and the AP end carries `Port 0` / `eth0`, all three
correct and distinct. So the convention appears to invert specifically for `discovered` nodes.

## Symptom 3 — Port is `null` on the Meraki end

PDX111F: 19 × CW9176I (`wireless-32-2-4`) behind two **Juniper EX4300-48P** switches. `linkLayer`
creates the Juniper `discovered` node correctly, but the AP end's port is `null` on 18 of 19 links.
`lldpCdp` returns a distinct correct port for every one:

| AP | linkLayer port | lldpCdp port | switch interface description |
|---|---|---|---|
| pdx111f-21ap01 | null | 863 | 2-41 |
| pdx111f-21ap02 | null | 967 | 3-39 |
| pdx111f-21ap03 | null | 850 | 3-11 |
| pdx111f-21ap06 | null | 692 | ge-4/0/20 |
| pdx111f-21ap13 | null | 513 | 1-2 |
| … | null | … | 18 of 19 affected |

---

## What we'd expect

1. Each end's `discovered.lldp` / `discovered.cdp` `portId` / `portDescription` should carry that
   end's own port for that specific link, matching what the device itself reports via
   `/devices/{serial}/lldpCdp`.
2. A port ID should never be replicated across sibling links — each AP's link should carry that AP's
   own switch port.
3. The two ends should not be transposed when the neighbour is a `discovered` node.

## Questions

- Is this a known issue? Specifically, is port attribution for `discovered` nodes expected to differ
  from `/devices/{serial}/lldpCdp` for the same link?
- Is there a fix or workaround available at network level? We are building a cross-vendor topology
  map and cannot fall back to one `/devices/{serial}/lldpCdp` call per device — at 149 devices and
  growing, against the documented 10 req/s per-organisation limit (we self-throttle below that), that
  does not scale for us.

## Device reference

| Device | Serial | Model | Firmware | Network |
|---|---|---|---|---|
| bcn211d-22ap-02 | Q5BK-MGPG-T7U3 | CW9176I | wireless-32-2-4 | BCN211D |
| bcn211d-22ap-03 | Q5BK-4F77-VZ2W | CW9176I | wireless-32-2-4 | BCN211D |
| bcn211d-22ap-04 | Q5BK-B3ZX-K6XR | CW9176I | wireless-32-2-4 | BCN211D |
| bcn211d-22ap-05 | Q5BK-TCQE-DLUT | CW9176I | wireless-32-2-4 | BCN211D |
| bcn211d-22ap-06 | Q5BK-2HX3-WYE2 | CW9176I | wireless-32-2-4 | BCN211D |
| bcn211d-22ap-07 | Q5BK-PG8V-LMGU | CW9176I | wireless-32-2-4 | BCN211D |
| bcn211d-22ap-08 | Q5BK-AXCJ-ENJ6 | CW9176I | wireless-32-2-4 | BCN211D |
| bcn211d-22ap-09 | Q5BK-UR74-GYUF | CW9176I | wireless-32-2-4 | BCN211D |
| bcn211d-22ap-mdf | Q5BE-CGNH-AP46 | CW9172I | wireless-32-2-4 | BCN211D |
| pdx111f-21ap01 | Q5BK-HCD2-L5SX | CW9176I | wireless-32-2-4 | PDX111F |
| pdx111f-21ap02 | Q5BK-PZLZ-84MB | CW9176I | wireless-32-2-4 | PDX111F |
| pdx111f-21ap03 | Q5BK-98GQ-DEE8 | CW9176I | wireless-32-2-4 | PDX111F |
| pdx111f-21ap06 | Q5BK-5MEC-PZLJ | CW9176I | wireless-32-2-4 | PDX111F |
| pdx111f-21ap13 | Q5BK-UA25-JNQA | CW9176I | wireless-32-2-4 | PDX111F |
| LON138S-SW01 (correct-behaviour contrast, Symptom 2) | Q2GW-NRVG-D6Q6 | MS225-24P | switch-17-2-2 | London - Strand House |

Non-Meraki devices referenced (discovered via LLDP, not in the Meraki inventory):

| Name | Chassis MAC | Description | Site |
|---|---|---|---|
| bcn211d-22dist | `00:31:46:49:4e:40` | Juniper EX4300-48P, JUNOS 20.4R3-S2.6 | BCN211D |
| pdx111f-21dist | `80:7f:f8:e0:e6:c0` | Juniper EX4300-48P, JUNOS 20.4R3-S2.6 | PDX111F |
| pdx111f-22dist | `c0:03:80:0b:68:80` | Juniper EX4300-48P, JUNOS 18.4R2-S8 | PDX111F |

Full raw JSON for every call above is available on request.
