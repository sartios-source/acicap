from typing import Dict, Any, List, Tuple
from collections import defaultdict, Counter
import re
from pathlib import Path
import json
import os
from functools import lru_cache


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


def _extract_node_id_from_dn(dn: str) -> str:
    match = re.search(r"node-(\d+)", dn or "")
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
        self._aci_object_index = set()

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
                obj_type = obj.get("type")
                attrs = obj.get("attributes", {})
                dn = attrs.get("dn", "")
                key = (obj_type, dn) if dn else (obj_type, json.dumps(attrs, sort_keys=True))
                if key in self._aci_object_index:
                    continue
                self._aci_object_index.add(key)
                if obj_type in {"eqptExtCh", "eqptCh"}:
                    if obj_type == "eqptExtCh" or ("extch" in dn or "fex-" in dn):
                        obj_type = "eqptFex"
                        obj["type"] = obj_type
                if obj_type == "eqptFex":
                    if not attrs.get("id"):
                        match = re.search(r"extch-(\d+)", dn)
                        if match:
                            attrs["id"] = match.group(1)
                        else:
                            match = re.search(r"fex-(\d+)", dn)
                            if match:
                                attrs["id"] = match.group(1)
                            else:
                                node_match = re.search(r"node-(\d+)", dn)
                                if node_match and int(node_match.group(1)) <= 200:
                                    attrs["id"] = node_match.group(1)
                    obj["attributes"] = attrs
                self._aci_objects.append(obj)
        for obj in self._aci_objects:
            obj_type = obj.get("type")
            if obj_type:
                self._class_counts[obj_type] += 1
                self._by_type[obj_type].append(obj.get("attributes", {}))

    def _unique_count(self, obj_type: str) -> int:
        seen = set()
        for attrs in self._by_type.get(obj_type, []):
            dn = attrs.get("dn")
            if dn:
                seen.add(dn)
        return len(seen)

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

    def _detect_apic_release(self) -> str:
        candidates = []
        for attrs in self._by_type.get("topSystem", []):
            version = attrs.get("version")
            if version:
                candidates.append(version)
        for attrs in self._by_type.get("firmwareCtrlrRunning", []):
            version = attrs.get("version")
            if version:
                candidates.append(version)
        for value in candidates:
            match = re.search(r"(\\d+\\.\\d+\\(\\d+\\))", value)
            if match:
                return match.group(1)
            match = re.search(r"(\\d+\\.\\d+\\.\\d+)", value)
            if match:
                return match.group(1)
        return self.fabric_data.get("apic_release") or "5.2(4)"

    def _detect_apic_cluster_size(self) -> int:
        controllers = [
            n for n in self._by_type.get("fabricNode", [])
            if (n.get("role") or "").lower() == "controller"
        ]
        return len(controllers) if controllers else 4

    @lru_cache(maxsize=4)
    def _load_scalability_limits(self) -> Dict[str, Any]:
        limits_path = Path(__file__).parent.parent / "data" / "scalability_limits.json"
        if not limits_path.exists():
            return {}
        return json.loads(limits_path.read_text(encoding="utf-8"))

    @lru_cache(maxsize=4)
    def _load_hardware_limits(self) -> Dict[str, Any]:
        limits_path = Path(__file__).parent.parent / "data" / "hardware_limits_9500.json"
        if not limits_path.exists():
            return {}
        return json.loads(limits_path.read_text(encoding="utf-8"))

    def _get_cisco_limits(self) -> Dict[str, Any]:
        release = self._detect_apic_release()
        cluster_size = self._detect_apic_cluster_size()
        limits = self._load_scalability_limits()
        release_key = release if release in limits else "5.2(4)"
        cluster_key = str(cluster_size)
        release_limits = limits.get(release_key, {})
        per_cluster = release_limits.get("cluster_size", {}).get(cluster_key, {})
        per_fabric = release_limits.get("per_fabric", {})
        return {
            "release": release_key,
            "cluster_size": cluster_size,
            "per_cluster": per_cluster,
            "per_fabric": per_fabric,
        }

    def _compute_headroom(self, current: int, maximum: int) -> Dict[str, Any]:
        if not maximum:
            return {"current": current, "maximum": None, "remaining": None, "pct": None}
        remaining = max(maximum - current, 0)
        pct = round((current / maximum) * 100, 1) if maximum else None
        return {"current": current, "maximum": maximum, "remaining": remaining, "pct": pct}

    def _get_spine_port_capacity(self) -> Dict[str, Any]:
        limits = self._load_hardware_limits()
        linecards = limits.get("linecards", {})
        spine_ids = {
            str(n.get("id")) for n in self._by_type.get("fabricNode", [])
            if (n.get("role") or "").lower() == "spine"
        }
        per_spine_ports = defaultdict(int)
        per_spine_cards = defaultdict(list)
        for lc in self._by_type.get("eqptLC", []):
            model = lc.get("model") or lc.get("name") or ""
            dn = lc.get("dn", "")
            node_match = re.search(r"node-(\\d+)", dn)
            node_id = node_match.group(1) if node_match else lc.get("id")
            if not node_id or str(node_id) not in spine_ids:
                continue
            normalized = model.strip().upper()
            if normalized in linecards:
                if not linecards[normalized].get("aci_spine_supported", True):
                    continue
                ports = int(linecards[normalized].get("spine_ports", 0))
                per_spine_ports[str(node_id)] += ports
                per_spine_cards[str(node_id)].append(normalized)
        if not per_spine_ports:
            per_spine_ports = defaultdict(int)
            per_spine_cards = defaultdict(list)
            for iface in self._by_type.get("ethpmPhysIf", []):
                dn = iface.get("dn", "")
                node_id = _extract_node_id_from_dn(dn)
                if node_id and node_id in spine_ids:
                    iface_id = _extract_interface_id_from_dn(dn) or iface.get("id", "")
                    if iface_id:
                        per_spine_ports[node_id] += 1
        total_ports = sum(per_spine_ports.values())
        return {
            "total_spine_ports": total_ports,
            "per_spine_ports": dict(per_spine_ports),
            "per_spine_cards": dict(per_spine_cards),
        }

    def _infer_uplinks_per_leaf(self, default_value: int) -> int:
        spine_names = {
            (n.get("name") or "").lower()
            for n in self._by_type.get("fabricNode", [])
            if (n.get("role") or "").lower() == "spine"
        }
        leaf_ids = {
            str(n.get("id")) for n in self._by_type.get("fabricNode", [])
            if (n.get("role") or "").lower() == "leaf"
        }

        def is_spine_neighbor(attrs: dict) -> bool:
            sys_name = (attrs.get("sysName") or "").lower()
            chassis = (attrs.get("chassisIdV") or "").lower()
            return any(name and name in sys_name for name in spine_names) or "spine" in sys_name or "spine" in chassis

        leaf_ports = defaultdict(set)
        for adj in self._by_type.get("lldpAdjEp", []) + self._by_type.get("cdpAdjEp", []):
            dn = adj.get("dn", "")
            node_id = _extract_node_id_from_dn(dn)
            if not node_id or node_id not in leaf_ids:
                continue
            if not is_spine_neighbor(adj):
                continue
            iface_id = _extract_interface_id_from_dn(dn)
            if iface_id:
                leaf_ports[node_id].add(iface_id)

        if not leaf_ports:
            return default_value

        counts = sorted(len(v) for v in leaf_ports.values() if v)
        if not counts:
            return default_value
        mid = len(counts) // 2
        return counts[mid] if len(counts) % 2 == 1 else max(1, int(round((counts[mid - 1] + counts[mid]) / 2)))

    def _get_port_utilization_breakdown(self) -> Dict[str, Any]:
        leaf_ids = {
            str(n.get("id")) for n in self._by_type.get("fabricNode", [])
            if (n.get("role") or "").lower() == "leaf"
        }
        spine_ids = {
            str(n.get("id")) for n in self._by_type.get("fabricNode", [])
            if (n.get("role") or "").lower() == "spine"
        }

        def add_stat(bucket, node_id, oper_st):
            bucket.setdefault(node_id, {"total": 0, "up": 0, "down": 0, "unknown": 0})
            bucket[node_id]["total"] += 1
            if oper_st == "up":
                bucket[node_id]["up"] += 1
            elif oper_st == "down":
                bucket[node_id]["down"] += 1
            else:
                bucket[node_id]["unknown"] += 1

        leaf_stats = {}
        spine_stats = {}
        for iface in self._by_type.get("ethpmPhysIf", []):
            dn = iface.get("dn", "")
            node_id = _extract_node_id_from_dn(dn)
            if not node_id:
                continue
            oper = (iface.get("operSt") or "").lower()
            if node_id in leaf_ids:
                add_stat(leaf_stats, node_id, oper)
            elif node_id in spine_ids:
                add_stat(spine_stats, node_id, oper)

        fex_stats = {}
        for fex in self._by_type.get("eqptFex", []):
            fex_id = fex.get("id")
            if not fex_id:
                dn = fex.get("dn", "")
                match = re.search(r"extch-(\d+)", dn)
                fex_id = match.group(1) if match else None
            if not fex_id:
                continue
            fex_stats[str(fex_id)] = {"total": 0, "up": 0, "down": 0, "unknown": 0}

        for iface in self._by_type.get("ethpmPhysIf", []):
            iface_id = iface.get("id", "") or _extract_interface_id_from_dn(iface.get("dn", ""))
            match = re.match(r"^eth(\d+)/", iface_id)
            if not match:
                continue
            fex_id = match.group(1)
            if fex_id not in fex_stats:
                continue
            oper = (iface.get("operSt") or "").lower()
            fex_stats[fex_id]["total"] += 1
            if oper == "up":
                fex_stats[fex_id]["up"] += 1
            elif oper == "down":
                fex_stats[fex_id]["down"] += 1
            else:
                fex_stats[fex_id]["unknown"] += 1

        def to_rows(stats):
            rows = []
            for node_id, data in stats.items():
                rows.append({"node": node_id, **data})
            return sorted(rows, key=lambda x: x["node"])

        return {
            "leafs": to_rows(leaf_stats),
            "spines": to_rows(spine_stats),
            "fex": [
                {"fex": fex_id, **data}
                for fex_id, data in sorted(fex_stats.items(), key=lambda x: x[0])
            ],
        }

    def analyze(self) -> Dict[str, Any]:
        self._load_data()

        by_role = self._get_fabric_nodes()
        leafs = by_role.get("leaf", [])
        spines = by_role.get("spine", [])
        fex = self._by_type.get("eqptFex", [])

        tenant_rollups = self._get_tenant_rollups()
        endpoints = self._unique_count("fvCEp")
        summary = {
            "leafs": len(leafs),
            "spines": len(spines),
            "fex": len(fex),
            "tenants": self._unique_count("fvTenant"),
            "vrfs": self._unique_count("fvCtx"),
            "bds": self._unique_count("fvBD"),
            "epgs": self._unique_count("fvAEPg"),
            "subnets": self._unique_count("fvSubnet"),
            "contracts": self._unique_count("vzBrCP"),
            "endpoints": endpoints,
        }
        ports = self._get_port_stats()
        spine_capacity = self._get_spine_port_capacity()
        limits = self._get_cisco_limits()
        per_cluster = limits.get("per_cluster", {})
        per_fabric = limits.get("per_fabric", {})
        per_tenant_epg_limit = per_fabric.get("epgs_per_tenant_multi") if summary["tenants"] > 1 else per_fabric.get("epgs_per_tenant_single")
        max_epg_per_tenant = max((row.get("epgs", 0) for row in tenant_rollups.get("rows", [])), default=0)
        default_uplinks = int(os.environ.get("UPLINKS_PER_LEAF_DEFAULT", "2"))
        uplinks_per_leaf = int(self.fabric_data.get("uplinks_per_leaf") or 0) or self._infer_uplinks_per_leaf(default_uplinks)
        leafs_supported_by_spines = (spine_capacity["total_spine_ports"] // uplinks_per_leaf) if uplinks_per_leaf else 0
        spine_leaf_headroom = max(leafs_supported_by_spines - summary["leafs"], 0)
        scale_profile = (self.fabric_data.get("scale_profile") or "LSE2").upper()
        l3outs_limit = per_fabric.get("l3outs_per_fabric_lse") if scale_profile != "ALE" else per_fabric.get("l3outs_per_fabric_ale")
        external_epgs_limit = per_fabric.get("external_epgs_per_fabric_lse") if scale_profile != "ALE" else per_fabric.get("external_epgs_per_fabric_ale")
        endpoint_profile = (self.fabric_data.get("endpoint_profile") or "default").lower()
        endpoint_limit_map = {
            "default": per_fabric.get("endpoints_per_leaf_default"),
            "high_dual_stack": per_fabric.get("endpoints_per_leaf_high_dual_stack"),
            "high_lpm": per_fabric.get("endpoints_per_leaf_high_lpm"),
            "high_policy": per_fabric.get("endpoints_per_leaf_high_policy_lse2"),
        }
        endpoints_per_leaf_limit = endpoint_limit_map.get(endpoint_profile, per_fabric.get("endpoints_per_leaf_default"))
        headroom = {
            "leafs": self._compute_headroom(summary["leafs"], per_cluster.get("leaf_switches")),
            "leafs_per_pod": self._compute_headroom(summary["leafs"], per_cluster.get("leaf_switches_per_pod")),
            "spines": self._compute_headroom(summary["spines"], per_fabric.get("spine_switches_total")),
            "tenants": self._compute_headroom(summary["tenants"], per_cluster.get("tenants")),
            "vrfs": self._compute_headroom(summary["vrfs"], per_cluster.get("vrfs")),
            "bds": self._compute_headroom(summary["bds"], per_fabric.get("bds")),
            "bds_per_leaf": self._compute_headroom(summary["bds"], per_fabric.get("bds_per_leaf")),
            "epgs": self._compute_headroom(summary["epgs"], per_fabric.get("epgs")),
            "epgs_per_bd_per_leaf": self._compute_headroom(summary["epgs"], per_fabric.get("epgs_per_bd_per_leaf")),
            "contracts": self._compute_headroom(summary["contracts"], per_fabric.get("contracts")),
            "fex": self._compute_headroom(summary["fex"], per_fabric.get("fexs")),
            "ports": self._compute_headroom(ports.get("total", 0), per_fabric.get("physical_ports")),
            "epgs_per_tenant": self._compute_headroom(max_epg_per_tenant, per_tenant_epg_limit),
            "leafs_by_spine_ports": self._compute_headroom(summary["leafs"], leafs_supported_by_spines),
            "l3outs": self._compute_headroom(self._unique_count("l3extOut"), l3outs_limit),
            "external_epgs": self._compute_headroom(self._unique_count("l3extInstP"), external_epgs_limit),
            "pc_vpc_per_leaf": self._compute_headroom(self._unique_count("pcAggrIf"), per_fabric.get("pc_vpc_per_leaf")),
            "ports_x_vlans": self._compute_headroom(len(self._by_type.get("fvRsPathAtt", [])), per_fabric.get("ports_x_vlans")),
            "endpoints_per_leaf": self._compute_headroom(endpoints, endpoints_per_leaf_limit),
        }

        return {
            "summary": summary,
            "completeness": self.get_data_completeness(),
            "ports": ports,
            "tenants": tenant_rollups,
            "epg_spread": self._get_epg_spread(),
            "vlan_overlap": self._get_vlan_overlap(),
            "vlan_pools": self._get_vlan_pools(),
            "vpc": self._get_vpc_scale(),
            "l3out": self._get_l3out_scale(),
            "cisco_limits": limits,
            "headroom": headroom,
            "scale_profile": scale_profile,
            "endpoint_profile": endpoint_profile,
            "port_utilization": self._get_port_utilization_breakdown(),
            "spine_capacity": {
                **spine_capacity,
                "uplinks_per_leaf": uplinks_per_leaf,
                "leafs_supported_by_spines": leafs_supported_by_spines,
                "remaining_leafs_before_linecards": spine_leaf_headroom
            }
        }
