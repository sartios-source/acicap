#!/usr/bin/env python3
"""ACI Capacity Offline Collector - APIC REST export into JSON bundles."""
import argparse
import getpass
import json
import os
import ssl
import zipfile
from datetime import datetime
from urllib.request import build_opener, HTTPCookieProcessor, Request
import http.cookiejar

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

DEFAULT_CLASSES = REQUIRED_CLASSES + OPTIONAL_CLASSES


class APICCollector:
    def __init__(self, apic_host, username, password, output_dir):
        self.apic_host = apic_host
        self.username = username
        self.password = password
        self.output_dir = output_dir
        self.ssl_context = ssl._create_unverified_context()
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookie_jar))
        os.makedirs(self.output_dir, exist_ok=True)

        self.summary = {
            "hostname": apic_host,
            "timestamp": datetime.now().isoformat(),
            "classes_requested": [],
            "classes_collected": [],
            "missing_required": [],
            "missing_optional": [],
            "output_file": "",
            "collection_status": "failed"
        }

    def _rest_login(self):
        payload = json.dumps({
            "aaaUser": {"attributes": {"name": self.username, "pwd": self.password}}
        }).encode("utf-8")
        req = Request(
            f"https://{self.apic_host}/api/aaaLogin.json",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        self.opener.open(req, context=self.ssl_context, timeout=30)

    def _get_class(self, class_name):
        req = Request(f"https://{self.apic_host}/api/node/class/{class_name}.json")
        with self.opener.open(req, context=self.ssl_context, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def collect(self, classes):
        self.summary["classes_requested"] = classes
        self._rest_login()
        imdata_all = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for cls in classes:
            data = self._get_class(cls)
            imdata = data.get("imdata", [])
            if imdata:
                imdata_all.extend(imdata)
                self.summary["classes_collected"].append(cls)
                class_path = os.path.join(self.output_dir, f"apic_{self.apic_host}_{timestamp}_{cls}.json")
                with open(class_path, "w", encoding="utf-8") as handle:
                    json.dump({"imdata": imdata}, handle, indent=2)

        collected = set(self.summary["classes_collected"])
        self.summary["missing_required"] = [c for c in REQUIRED_CLASSES if c not in collected]
        self.summary["missing_optional"] = [c for c in OPTIONAL_CLASSES if c not in collected]

        if imdata_all:
            output_path = os.path.join(self.output_dir, f"apic_{self.apic_host}_{timestamp}.json")
            with open(output_path, "w", encoding="utf-8") as handle:
                json.dump({"imdata": imdata_all}, handle, indent=2)
            self.summary["output_file"] = output_path
            self.summary["collection_status"] = "partial" if self.summary["missing_required"] else "success"
        else:
            self.summary["collection_status"] = "failed"

        manifest_path = os.path.join(self.output_dir, "collector_manifest.json")
        self.summary["fabric_name"] = self.apic_host
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(self.summary, handle, indent=2)

        return self.summary


def parse_args():
    parser = argparse.ArgumentParser(description="ACI Capacity Offline Collector")
    parser.add_argument("--apic-host", help="APIC hostname or IP")
    parser.add_argument("--host-file", help="File with APIC hostnames (one per line)")
    parser.add_argument("--apic-username", help="APIC username")
    parser.add_argument("--output-dir", default="network_data", help="Output directory")
    parser.add_argument("--aci-classes", help="Comma-separated ACI classes to collect")
    return parser.parse_args()


def main():
    args = parse_args()
    apic_hosts = []
    if args.host_file:
        with open(args.host_file, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line and not line.startswith("#"):
                    apic_hosts.append(line)
    elif args.apic_host:
        apic_hosts = [args.apic_host]
    else:
        apic_hosts = [input("APIC hostname or IP: ").strip()]

    apic_username = args.apic_username or input("APIC username: ").strip()
    apic_password = getpass.getpass("APIC password: ")

    classes = [c.strip() for c in (args.aci_classes or "").split(",") if c.strip()] or DEFAULT_CLASSES

    for host in apic_hosts:
        host_dir = os.path.join(args.output_dir, host)
        collector = APICCollector(host, apic_username, apic_password, host_dir)
        summary = collector.collect(classes)
        print(f"[{host}] status={summary['collection_status']} classes={len(summary['classes_collected'])}/{len(classes)}")

    zip_answer = input("Create a ZIP archive of the output? [Y/n]: ").strip().lower()
    if zip_answer in {"", "y", "yes"}:
        zip_name = input(f"ZIP filename (default: {args.output_dir}.zip): ").strip() or f"{args.output_dir}.zip"
        with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(args.output_dir):
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    rel_path = os.path.relpath(file_path, args.output_dir)
                    zf.write(file_path, rel_path)
        print(f"Created ZIP: {zip_name}")


if __name__ == "__main__":
    main()
