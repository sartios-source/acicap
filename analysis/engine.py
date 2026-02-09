from typing import Dict, Any, List, Tuple
from collections import defaultdict, Counter
import re
from pathlib import Path


REQUIRED_CLASSES = [
    "fabricNode",
    "eqptFex",
    "fvTenant",
    "fvCtx",
    "fvBD",
    "fvAEPg",
    "fvRsPathAtt",
    "fvSubnet",
    "ethpmPhysIf",
    "physDomP"
]

OPTIONAL_CLASSES = [
    "vzBrCP",
    "vpcDom",
    "pcAggrIf",
    "lacpEntity",
    "vpcIf",
    "l3extOut",
    "l3extInstP",
    "l3extLNodeP",
    "l3extLIfP",
    "l3extRsNodeL3OutAtt",
    "l3extSubnet",
    "l3extRsEctx",
    "bgpPeerP",
    "ospfIfP",
    "ipRouteP",
    "fvnsVlanInstP",
    "fvnsEncapBlk",
    "vmmDomP",
    "l3extDomP",
    "infraRsVlanNs",
    "vmmRsVlanNs",
    "l3extRsVlanNs"
]


def _extract_tenant_from_dn(dn: str) -> str:
    match = re.search(r"uni/tn-([^/]+)", dn or "")
    return match.group(1) if match else ""


def _extract_nodes_from_tdn(tdn: str) -> List[str]:
    nodes = set()
    for match in re.finditer(r"node-(\d+)", tdn or ""):
        nodes.add(match.group(1))
    return sorted(nodes)


def _extract_interface_id_from_dn(dn: str) -> str:
    if not dn:
        return ""
    match = re.search(r"\[(.+?)\]$", dn)
    if match:
        return match.group(1)
    match = re.search(r"pathep-\[(.+?)\]", dn)
    return match.group(1) if match else ""


def _parse_vlan_encap(encap: str) -> str:
    match = re.search(r"vlan-(\d+)", encap or "")
    return match.group(1) if match else ""


def _parse_vlan_block(encap: str) -> Tuple[int, int]:
    # Format: vlan-100-200 or vlan-100
    match = re.search(r"vlan-(\d+)(?:-(\d+))?", encap or "")
    if not match:
        return (0, 0)
    start = int(match.group(1))
    end = int(match.group(2) or match.group(1))
    return (start, end)


class CapacityAnalyzer:
    def __init__(self, fabric_data: Dict[str, Any]):
        self.fabric_data = fabric_data
        self.datasets = fabric_data.get("datasets", [])
        self._aci_objects: List[Dict[str, Any]] = []
        self._class_counts: Counter = Counter()

        self._by_type = defaultdict(list)

    def _load_data(self) -> None:
        if self._aci_objects:
            return
        from . import parsers
        for dataset in self.datasets:
            if dataset.get("type") != "aci":
                continue
            path_value = dataset.get("path")
            if not path_value:
                continue
            path = Path(path_value)
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            fmt = dataset.get("format") or "json"
            parsed = parsers.parse_aci(content, fmt)
            for obj in parsed.get("objects", []):
                self._aci_objects.append(obj)
        for obj in self._aci_objects:
            obj_type = obj.get("type")
            if obj_type:
                self._class_counts[obj_type] += 1
                self._by_type[obj_type].append(obj.get("attributes", {}))

    def get_data_completeness(self) -> Dict[str, Any]:
        self._load_data()
        missing_required = [c for c in REQUIRED_CLASSES if self._class_counts.get(c, 0) == 0]
        missing_optional = [c for c in OPTIONAL_CLASSES if self._class_counts.get(c, 0) == 0]
        required_score = (len(REQUIRED_CLASSES) - len(missing_required)) / len(REQUIRED_CLASSES) * 70
        optional_score = (len(OPTIONAL_CLASSES) - len(missing_optional)) / len(OPTIONAL_CLASSES) * 30
        completeness_score = round(required_score + optional_score)
        return {
            "completeness_score": completeness_score,
            "missing_required": missing_required,
            "missing_optional": missing_optional,
            "class_counts": dict(self._class_counts)
        }

    def _get_fabric_nodes(self) -> Dict[str, List[Dict[str, Any]]]:
        nodes = self._by_type.get("fabricNode", [])
        by_role = defaultdict(list)
        for node in nodes:
            by_role[node.get("role", "unknown")].append(node)
        return by_role

    def _get_border_leaf_ids(self) -> List[str]:
        node_ids = set()
        for item in self._by_type.get("l3extRsNodeL3OutAtt", []):
            tdn = item.get("tDn", "")
            nodes = _extract_nodes_from_tdn(tdn)
            node_ids.update(nodes)
        for item in self._by_type.get("l3extLNodeP", []):
            dn = item.get("dn", "")
            nodes = _extract_nodes_from_tdn(dn)
            node_ids.update(nodes)
        return sorted(node_ids)

    def _get_port_stats(self) -> Dict[str, Any]:
        ports = self._by_type.get("ethpmPhysIf", [])
        total = len(ports)
        up = sum(1 for p in ports if (p.get("operSt") or "").lower() == "up")
        down = sum(1 for p in ports if (p.get("operSt") or "").lower() == "down")
        unknown = max(total - up - down, 0)

        path_attachments = self._by_type.get("fvRsPathAtt", [])
        port_paths = defaultdict(int)
        for path in path_attachments:
            tdn = path.get("tDn", "")
            iface = _extract_interface_id_from_dn(tdn)
            nodes = _extract_nodes_from_tdn(tdn)
            key = f"{nodes[0] if nodes else ''}:{iface}"
            if iface:
                port_paths[key] += 1
        used_ports = len(port_paths)
        return {
            "total": total,
            "up": up,
            "down": down,
            "unknown": unknown,
            "ports_with_epg": used_ports
        }

    def _get_tenant_rollups(self) -> Dict[str, Any]:
        tenants = defaultdict(lambda: defaultdict(int))
        for epg in self._by_type.get("fvAEPg", []):
            tenant = _extract_tenant_from_dn(epg.get("dn", ""))
            tenants[tenant]["epgs"] += 1
        for bd in self._by_type.get("fvBD", []):
            tenant = _extract_tenant_from_dn(bd.get("dn", ""))
            tenants[tenant]["bds"] += 1
        for vrf in self._by_type.get("fvCtx", []):
            tenant = _extract_tenant_from_dn(vrf.get("dn", ""))
            tenants[tenant]["vrfs"] += 1
        for subnet in self._by_type.get("fvSubnet", []):
            tenant = _extract_tenant_from_dn(subnet.get("dn", ""))
            tenants[tenant]["subnets"] += 1
        for contract in self._by_type.get("vzBrCP", []):
            tenant = _extract_tenant_from_dn(contract.get("dn", ""))
            tenants[tenant]["contracts"] += 1

        rollups = []
        for tenant, counts in tenants.items():
            rollups.append({
                "tenant": tenant or "common",
                "vrfs": counts.get("vrfs", 0),
                "bds": counts.get("bds", 0),
                "epgs": counts.get("epgs", 0),
                "subnets": counts.get("subnets", 0),
                "contracts": counts.get("contracts", 0)
            })
        rollups = sorted(rollups, key=lambda x: x["epgs"], reverse=True)
        return {"rows": rollups}

    def _get_epg_spread(self) -> Dict[str, Any]:
        epg_paths = defaultdict(list)
        for path in self._by_type.get("fvRsPathAtt", []):
            dn = path.get("dn", "")
            tenant = _extract_tenant_from_dn(dn)
            epg = dn.split("/epg-")[-1] if "/epg-" in dn else dn
            tdn = path.get("tDn", "")
            nodes = _extract_nodes_from_tdn(tdn)
            epg_paths[(tenant, epg)].append(nodes)

        rows = []
        for (tenant, epg), node_lists in epg_paths.items():
            node_set = set(n for nodes in node_lists for n in nodes)
            rows.append({
                "tenant": tenant or "common",
                "epg": epg,
                "path_count": len(node_lists),
                "node_count": len(node_set)
            })
        rows = sorted(rows, key=lambda x: (x["node_count"], x["path_count"]), reverse=True)
        return {"rows": rows[:1000]}

    def _get_vlan_overlap(self) -> Dict[str, Any]:
        vlan_to_tenants = defaultdict(set)
        for path in self._by_type.get("fvRsPathAtt", []):
            vlan = _parse_vlan_encap(path.get("encap", ""))
            if not vlan:
                continue
            tenant = _extract_tenant_from_dn(path.get("dn", ""))
            vlan_to_tenants[vlan].add(tenant or "common")
        overlaps = [
            {"vlan": vlan, "tenant_count": len(tenants), "tenants": sorted(list(tenants))}
            for vlan, tenants in vlan_to_tenants.items() if len(tenants) > 1
        ]
        overlaps = sorted(overlaps, key=lambda x: x["tenant_count"], reverse=True)
        return {"total_vlans": len(vlan_to_tenants), "overlaps": overlaps}

    def _get_vlan_pools(self) -> Dict[str, Any]:
        pools = self._by_type.get("fvnsVlanInstP", [])
        blocks = self._by_type.get("fvnsEncapBlk", [])
        total_pool_vlans = 0
        for blk in blocks:
            start, end = _parse_vlan_block(blk.get("encap", ""))
            if start and end:
                total_pool_vlans += (end - start + 1)
        used_vlans = set()
        for path in self._by_type.get("fvRsPathAtt", []):
            vlan = _parse_vlan_encap(path.get("encap", ""))
            if vlan:
                used_vlans.add(int(vlan))
        return {
            "pool_count": len(pools),
            "pool_vlan_capacity": total_pool_vlans,
            "used_vlan_count": len(used_vlans)
        }

    def _get_vpc_scale(self) -> Dict[str, Any]:
        return {
            "vpc_domains": len(self._by_type.get("vpcDom", [])),
            "port_channels": len(self._by_type.get("pcAggrIf", [])),
            "lacp_entities": len(self._by_type.get("lacpEntity", [])),
            "vpc_interfaces": len(self._by_type.get("vpcIf", []))
        }

    def _get_l3out_scale(self) -> Dict[str, Any]:
        border_leafs = self._get_border_leaf_ids()
        return {
            "l3outs": len(self._by_type.get("l3extOut", [])),
            "external_epgs": len(self._by_type.get("l3extInstP", [])),
            "bgp_peers": len(self._by_type.get("bgpPeerP", [])),
            "ospf_interfaces": len(self._by_type.get("ospfIfP", [])),
            "border_leaf_count": len(border_leafs),
            "border_leafs": border_leafs
        }

    def analyze(self) -> Dict[str, Any]:
        self._load_data()

        by_role = self._get_fabric_nodes()
        leafs = by_role.get("leaf", [])
        spines = by_role.get("spine", [])
        fex = self._by_type.get("eqptFex", [])

        summary = {
            "leafs": len(leafs),
            "spines": len(spines),
            "fex": len(fex),
            "tenants": len(self._by_type.get("fvTenant", [])),
            "vrfs": len(self._by_type.get("fvCtx", [])),
            "bds": len(self._by_type.get("fvBD", [])),
            "epgs": len(self._by_type.get("fvAEPg", [])),
            "subnets": len(self._by_type.get("fvSubnet", [])),
            "contracts": len(self._by_type.get("vzBrCP", []))
        }

        return {
            "summary": summary,
            "completeness": self.get_data_completeness(),
            "ports": self._get_port_stats(),
            "tenants": self._get_tenant_rollups(),
            "epg_spread": self._get_epg_spread(),
            "vlan_overlap": self._get_vlan_overlap(),
            "vlan_pools": self._get_vlan_pools(),
            "vpc": self._get_vpc_scale(),
            "l3out": self._get_l3out_scale()
        }
