# Meraki support ticket 2 of 2 — port IDs on `stack` nodes

## Subject

`/networks/{id}/topology/linkLayer` reports the wrong port, `null`, or omits links entirely wherever
one end of the link is a `stack` node — verified from both ends via `/devices/{serial}/lldpCdp`

## Environment and reproduction

- **Organization ID:** 225248
- **API:** Dashboard API v1, `https://api.meraki.com/api/v1`
- **Captured:** 2026-09-10 / 2026-09-11 UTC. All calls returned HTTP 200.
- **Scope of comparison:** all 10 networks / 149 devices in the org. `linkLayer` returned 92 links,
  62 of them between two Meraki-managed devices; `lldpCdp` returned 400 port-neighbour records.

```
GET /networks/{networkId}/topology/linkLayer     # 1 per network
GET /devices/{serial}/lldpCdp                    # 1 per device
```

Networks referenced in this ticket:

| Network | networkId |
|---|---|
| London - Strand House | `L_652458996015302502` |
| HYD9T - Hyderabad India | `L_652458996015307212` |
| BLR15C - Bangalore India | `L_652458996015307187` |
| ATL1100P | `L_652458996015306596` |

Every device named below is Meraki-managed, so the correct value is confirmed independently from
**both** ends. In every case the two `lldpCdp` responses agree with each other while `linkLayer`
disagrees with both.

---

## What we see

The port reported for a link is frequently not the port of that link.

Wherever one end of a link is a `stack` node, the port returned for that end is often a port belonging
to a different link — another cable to the same peer, a cable to an entirely different device, or a port
on a different member of the same stack. Ethernet links are point-to-point, so each end of each link has
exactly one correct port, and `/devices/{serial}/lldpCdp` returns that port consistently from both
sides.

Three symptoms, which is why they are in one ticket:

| | Symptom | Section |
|---|---|---|
| i | The reported port belongs to a different link of the same node | A, B |
| ii | No port is reported at all (`null`) | C |
| iii | The node's other links are omitted from the response entirely | D |

## Observation — every failure involves a `stack` node

Every incorrect link we found across the org, classified by the `node.type` of its two ends:

| `node.type` of the two ends | incorrect links | of which the port is `null` |
|---|---|---|
| `device` / `stack` | 5 | 1 |
| `stack` / `stack` | **3 — every link of this kind in the org** | 3 |

**All 8 incorrect links have at least one `stack` end, and in every one of them the wrong or missing
value sits on the stack end.**

The non-stack end is not automatically safe, however. Of the 5 affected `device`/`stack` links, the
`device` end reports its own port correctly on 3, and on the other 2 it reports the port of its WAN
cable in place of the LAN cable the link describes (section B). So the stack end is wrong in every
failure, and the device end goes wrong only where two cables have been merged into one link.

Which wrong answer comes back varies with the stack's peer: where the peer is cabled to more than one
place, a port from one of its other cables is returned; where both ends are stacks, `null` is returned.

## Our hypothesis

Every stack node in our org is a genuine multi-member stack — two C9300X-24Y cores, and three or four
MS225/MS350 switches per distribution stack — so a port such as `Twe1/0/3` always has to be attributed
to a specific member and a specific cable. Our reading is that the port is being resolved against the
node's whole adjacency set rather than against the individual cable, and the member it belongs to is
lost on the way.

Section B is hard to explain any other way: a port from Core02 can only surface on the Core01 link
through the node those two switches share. We cannot narrow it down further from our own data, since we
have no link where a multi-cabled device faces a non-stack peer — so this is offered as a hypothesis,
and the sections below are simply what the two APIs returned.

---

## A. A port ID from a different peer's link (London - Strand House)

`LHR138S-mx01` (MX84, `wired-18-1-07`) has two neighbours on two physical ports:

| MX84 local port | Neighbour | Neighbour portId | portDescription |
|---|---|---|---|
| `port10` | Meraki MS225-24P - LON138S-SW01 (stack member) | **24** | Port 24 |
| `wan0` | NEWR1-M1790 (non-Meraki, WAN side) | **ether1-Data** | – |

The switch confirms the LAN link independently — `LON138S-SW01` port **24** →
`Meraki MX84 - LHR138S-mx01`, "lan port 0".

`linkLayer` returns:

| end | node type | device | direction | lldp.portId | lldp.portDescription |
|---|---|---|---|---|---|
| A | device | LHR138S-mx01 | downstream | 0 | lan port 0 |
| B | **stack** | LON138S-SW01 | upstream | **ether1-Data** | null |

`ether1-Data` is not an MS225 port name. It is the port of the MX's **WAN-side neighbour — a
different device on a different link**. Correct value, agreed by both ends: `24`.

## B. A port belonging to Core02 reported on the Core01 link (HYD9T)

Core01 and Core02 are the two members of one `Core Stack` node.

`lldpCdp` ground truth:

| device | local port | neighbour | nbr portId | nbr portDescription |
|---|---|---|---|---|
| HYD9T-15-MX02 | `port25` | HYD9T-15-**Core01** | **Twe2/0/24** | Port 24 |
| HYD9T-15-MX02 | `port26` | HYD9T-15-Core02 | Twe1/0/24 | Port 24 |
| HYD9T-15-MX02 | `wan1` | HYD9T-15-**Core02** | **Twe1/0/3** | Port 3 |
| HYD9T-15-Core01 | **24** | Meraki MX250 - HYD9T-15-MX02 | **23** | lan port 23 |
| HYD9T-15-Core02 | 3 | Meraki MX250 - HYD9T-15-MX02 | 1 | internet port 1 |

`linkLayer` returns:

| end | node type | device | direction | lldp.portId | lldp.portDescription |
|---|---|---|---|---|---|
| A | **stack** | HYD9T-15-**Core01** | downstream | **Twe1/0/3** | Port 3 |
| B | device | HYD9T-15-MX02 | upstream | 23 | lan port 23 |

The MX end (`23` / lan port 23) belongs to the Core01 link; the core end (`Twe1/0/3`) is **Core02's**
port from the `wan1` link. Two physical links to two different members of the same stack, merged into
one. Correct core end: `Twe2/0/24`.

The same shape occurs at `BLR15C-2-Core01 ↔ BLR15C-2-MX01` (core end `Twe2/0/24`, which faces MX01's
*lan port 22*, paired with MX end `internet port 0`, which faces `Twe2/0/2`) and at
`HYD9T-15-Core01 ↔ HYD9T-15-MX01`.

## C. Null port IDs

| Link | node types | lldpCdp, confirmed both ends | linkLayer |
|---|---|---|---|
| atl1100p-mx01 (MX85) ↔ atl1100p-20dist:02 (MS225-48FP) | device / stack | mx01 `port12` → dist02 **52**; dist02 `52` → mx01 "lan port 7" | mx01 end `7` (correct); **dist end `null`** |
| BLR15C-2-Core01 (C9300X-24Y) ↔ BLR15C-2-Dist01 (MS350-48FP) | stack / stack | Core01 `19` → Dist01 **52**; Dist01 `52` → Core01 **Twe2/0/19** | **`null` both ends**, `direction: None` |
| HYD9T-15-Core01 ↔ HYD9T-15I-Dist01 | stack / stack | Core01 `20` → I-Dist01 **52** | **`null` both ends**, `direction: None` |
| HYD9T-15-Core01 ↔ HYD9T-15M-Dist01 | stack / stack | Core01 `19` → M-Dist01 **52** | **`null` both ends**, `direction: None` |

Every link in our org where **both** ends are `stack` nodes returns `null` on both ends *and*
`direction: None` — the three core↔distribution links above, 3 of 3. This is the most direct
reproducer in this ticket.

## D. Parallel links into a stack are dropped entirely

Where a device is cabled to more than one member of the same stack, only one link is returned, with
nothing in the response indicating others were discarded.

**ATL1100P** — MX85 dual-homed to two members of the `atl1100p-20dist` stack, each confirming from its
own side:

| MX85 local port | Neighbour (stack member) | Neighbour port | Reciprocal confirmation |
|---|---|---|---|
| `port11` | atl1100p-20dist:01 | 52 | dist:01 port 52 → MX85 "lan port 6" |
| `port12` | atl1100p-20dist:02 | 52 | dist:02 port 52 → MX85 "lan port 7" |

`linkLayer` returns **one** link for the whole network: `atl1100p-mx01 (7) ↔ atl1100p-20dist:02
(null)`. The `dist:01` link is absent.

**BLR15C / HYD9T** — three cables per MX into a two-member `Core Stack`, one link returned:

| Device | cables reported by `lldpCdp` | linkLayer |
|---|---|---|
| BLR15C-2-MX01 | Core01 `Twe2/0/24` (port23), Core02 `Twe1/0/24` (port25), Core01 `Twe2/0/2` (wan0) | 1 of 3 |
| BLR15C-2-MX02 | Core01 `Twe2/0/23` (port23), Core02 `Twe1/0/23` (port25), Core02 `Twe1/0/3` (wan1) | 1 of 3 |
| HYD9T-15-MX01 | Core01 `Twe2/0/23` (port25), Core02 `Twe1/0/23` (port26), Core01 `Twe2/0/2` (wan0) | 1 of 3 |
| HYD9T-15-MX02 | Core01 `Twe2/0/24` (port25), Core02 `Twe1/0/24` (port26), Core02 `Twe1/0/3` (wan1) | 1 of 3 |

In every case the discarded links are the redundant paths, so the API's view of these sites shows no
redundancy where redundancy exists. This is consistent with the hypothesis above: if at most one link is
emitted per *node* pair, then cables to different members of one stack are contending for a single slot.

---

## What we'd expect

1. Each end's `discovered.lldp` / `discovered.cdp` `portId` / `portDescription` should carry that
   end's own port for that specific link, matching what the device itself reports via
   `/devices/{serial}/lldpCdp` — including when the end is a stack member.
2. A port ID should never appear on a link other than the one the device reported it on, and never a
   port belonging to a different member of the same stack.
3. `stack` / `stack` links should carry ports and a `direction`, not `null`.
4. Where a device is cabled to several members of one stack, all of those links should appear.

## Questions

- Is this a known issue with port attribution inside stack nodes?
- Is returning a single link per node pair intentional (e.g. a spanning-tree-style reduction for
  display)? If so, is there a supported way to retrieve the full adjacency set — without falling back
  to one `/devices/{serial}/lldpCdp` call per device? We are building a cross-vendor topology map; at
  149 devices and growing, against the documented 10 req/s per-organisation limit (we self-throttle
  below that), the per-device endpoint does not scale for us.
- Is there a way to have stacks returned as their individual member devices instead, if member-level
  port attribution is not supported?

## Device reference

| Device | Serial | Model | Firmware | Network |
|---|---|---|---|---|
| LHR138S-mx01 | Q2PN-XXDW-YU46 | MX84 | wired-18-1-07 | London - Strand House |
| LON138S-SW01 | Q2GW-NRVG-D6Q6 | MS225-24P | switch-17-2-2 | London - Strand House |
| LON138S-SW02 | Q2KW-N7BJ-5NX6 | MS225-48FP | switch-17-2-2 | London - Strand House |
| HYD9T-15-MX01 | Q2SW-Z772-QVEV | MX250 | wired-26-1-5 | HYD9T |
| HYD9T-15-MX02 | Q2SW-7V5N-A2EN | MX250 | wired-26-1-5 | HYD9T |
| HYD9T-15-Core01 | Q5JD-UZUQ-TQ3T | C9300X-24Y | cs-iosxe-17-15-5 | HYD9T |
| HYD9T-15-Core02 | Q5JD-LGVQ-EUVS | C9300X-24Y | cs-iosxe-17-15-5 | HYD9T |
| HYD9T-15I-Dist01 | Q2ZP-BU9T-TD7H | MS350-48FP | switch-18-1-7 | HYD9T |
| HYD9T-15M-Dist01 | Q2ZP-BU8U-8DN8 | MS350-48FP | switch-18-1-7 | HYD9T |
| BLR15C-2-MX01 | Q2SW-BKXV-NJUN | MX250 | wired-26-1-5 | BLR15C |
| BLR15C-2-MX02 | Q2SW-WB5N-N7MY | MX250 | wired-26-1-5 | BLR15C |
| BLR15C-2-Core01 | Q5JD-ZB5D-5NFW | C9300X-24Y | cs-iosxe-17-15-5 | BLR15C |
| BLR15C-2-Core02 | Q5JD-XLCV-HS23 | C9300X-24Y | cs-iosxe-17-15-5 | BLR15C |
| BLR15C-2-Dist01 | Q2ZP-BSQG-53SK | MS350-48FP | switch-17-2-2 | BLR15C |
| atl1100p-mx01 | Q2YN-ZMQA-B3U2 | MX85 | wired-26-1-5 | ATL1100P |
| atl1100p-20dist:01 | Q2KW-DGGQ-R2EW | MS225-48FP | switch-17-2-1 | ATL1100P |
| atl1100p-20dist:02 | Q2KW-BP5P-QFGR | MS225-48FP | switch-17-2-1 | ATL1100P |

Non-Meraki device referenced in section A (discovered via LLDP, not in the Meraki inventory):

| Name | Chassis MAC | Description | Site |
|---|---|---|---|
| NEWR1-M1790 | `cc:2d:e0:b9:b8:17` | WAN-side device on LHR138S-mx01 `wan0` | London - Strand House |

Full raw JSON for every call above is available on request.
