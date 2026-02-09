#!/usr/bin/env python3
"""ACI APIC Data Collector - REST, icurl, moquery fallbacks."""

import argparse
import getpass
import json
import logging
import os
import re
import ssl
import zipfile
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import http.cookiejar
import urllib.request

DATA_COMPLETENESS_CLASSES = [
    'fvAEPg',
    'fabricNode',
    'fvRsPathAtt',
    'fvBD',
    'fvCtx',
    'fvTenant',
    'fvSubnet',
    'ethpmPhysIf',
    'physDomP',
    'eqptFex',
    'vzBrCP',
    'vzSubj',
    'vzFilter',
    'vzEntry',
    'vzRsSubjFiltAtt',
    'fvRsCons',
    'fvRsProv',
    'vpcDom',
    'pcAggrIf',
    'lacpEntity',
    'vpcIf',
    'l3extOut',
    'l3extInstP',
    'l3extLNodeP',
    'l3extLIfP',
    'l3extRsNodeL3OutAtt',
    'l3extSubnet',
    'l3extRsEctx',
    'bgpPeerP',
    'ospfIfP',
    'ipRouteP',
    'fvnsVlanInstP',
    'fvnsEncapBlk',
    'vmmDomP',
    'l3extDomP',
    'infraRsVlanNs',
    'vmmRsVlanNs',
    'l3extRsVlanNs',
    'infraAccPortGrp',
    'infraAccBndlGrp',
    'infraAccPortP',
    'infraHPortS',
    'infraRsDomP',
    'infraAttEntityP',
    'lldpAdjEp',
    'cdpAdjEp'
]

REQUIRED_ACI_CLASSES = [
    'fabricNode',
    'eqptFex',
    'fvAEPg',
    'fvRsPathAtt',
    'fvBD',
    'fvCtx',
    'fvTenant',
    'fvSubnet',
    'ethpmPhysIf',
    'physDomP'
]

DEFAULT_ACI_CLASSES = DATA_COMPLETENESS_CLASSES + ['fvRsBd', 'fvRsCtx']

ORDER_BY_ATTR = {
    'fabricNode': 'id',
    'eqptFex': 'id',
    'fvAEPg': 'name',
    'fvBD': 'name',
    'fvCtx': 'name',
    'fvTenant': 'name'
}

LARGE_QUERY_CLASSES = {
    'fvRsPathAtt',
    'ethpmPhysIf',
    'lldpAdjEp',
    'cdpAdjEp'
}

ALIAS_ACCEPT_CLASSES = {
    'eqptFex': ['eqptFex', 'eqptExtCh', 'eqptCh']
}

try:
    import requests
except Exception:
    requests = None
    InsecureRequestWarning = None

try:
    import urllib3
except Exception:
    urllib3 = None


class APICCollector:
    def __init__(self, apic_host, username, password, output_dir, log_level="INFO"):
        self.apic_host = apic_host
        self.username = username
        self.password = password
        self.output_dir = output_dir
        self.ssl_context = ssl._create_unverified_context()

        os.makedirs(self.output_dir, exist_ok=True)
        self._setup_logging(log_level)

        self.rest_session = None
        self.icurl_token = None
        self.discovered_pods = set()
        self.discovered_nodes = {}

        self.summary = {
            'hostname': apic_host,
            'timestamp': datetime.now().isoformat(),
            'classes_requested': [],
            'classes_collected': [],
            'class_errors': [],
            'class_details': {},
            'class_files': {},
            'missing_required': [],
            'missing_optional': [],
            'methods_used': [],
            'imdata_count': 0,
            'collection_status': 'failed',
            'output_file': ''
        }

    def _setup_logging(self, log_level):
        logging.basicConfig(
            level=getattr(logging, log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(message)s"
        )
        self.logger = logging.getLogger("apic_collector")

    def _escape_single_quotes(self, value):
        return value.replace("'", "'\"'\"'")

    def _clean_apic_json_output(self, text):
        if not text:
            return ""

        lines = text.splitlines()
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("Warning: Permanently added"):
                continue
            if stripped.startswith("Last login"):
                continue
            if stripped.startswith("Connection to") and stripped.endswith("closed."):
                continue
            cleaned_lines.append(line)

        cleaned = "\n".join(cleaned_lines).strip()
        start_idx = -1
        for idx, ch in enumerate(cleaned):
            if ch in "{[":
                start_idx = idx
                break
        if start_idx == -1:
            return cleaned
        end_idx = max(cleaned.rfind("}"), cleaned.rfind("]"))
        if end_idx > start_idx:
            cleaned = cleaned[start_idx:end_idx + 1]
        else:
            cleaned = cleaned[start_idx:]
        return cleaned.strip()

    def _rest_login(self):
        apic_url = f"https://{self.apic_host}"
        payload = {
            "aaaUser": {
                "attributes": {
                    "name": self.username,
                    "pwd": self.password
                }
            }
        }

        if requests:
            if urllib3:
                try:
                    urllib3.disable_warnings()
                except Exception:
                    pass
            session = requests.Session()
            session.verify = False
            resp = session.post(f"{apic_url}/api/aaaLogin.json", json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            token = data.get("imdata", [{}])[0].get("aaaLogin", {}).get("attributes", {}).get("token")
            if not token:
                raise ValueError("APIC REST login returned no token")
            self.rest_session = ("requests", session)
            return

        cookie_jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{apic_url}/api/aaaLogin.json",
            data=body,
            headers={"Content-Type": "application/json"}
        )
        with opener.open(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        token = data.get("imdata", [{}])[0].get("aaaLogin", {}).get("attributes", {}).get("token")
        if not token:
            raise ValueError("APIC REST login returned no token")
        self.rest_session = ("urllib", opener)

    def _rest_get_class(self, class_name):
        if not self.rest_session:
            return None
        mode, session = self.rest_session
        url = f"https://{self.apic_host}/api/node/class/{class_name}.json"
        if mode == "requests":
            resp = session.get(url, timeout=60)
            resp.raise_for_status()
            return resp.text
        with session.open(url, timeout=60) as resp:
            return resp.read().decode("utf-8")

    def _rest_get_url(self, path):
        if not self.rest_session:
            return None
        mode, session = self.rest_session
        url = f"https://{self.apic_host}{path}"
        if mode == "requests":
            resp = session.get(url, timeout=60)
            resp.raise_for_status()
            return resp.text
        with session.open(url, timeout=60) as resp:
            return resp.read().decode("utf-8")

    def _fetch_paged_class(self, class_name, fetch_fn, allowed_types=None, page_size=50000, max_pages=50):
        """Fetch class data across pages until empty."""
        imdata_all = []
        attempts = []
        seen_dns = set()
        for page in range(max_pages):
            path = f"/api/node/class/{class_name}.json?page={page}&page-size={page_size}"
            try:
                output = fetch_fn(path)
                class_imdata = self._parse_imdata(output, class_name, allowed_types=allowed_types) or []
                attempts.append({'path': path, 'count': len(class_imdata), 'status': 'success' if class_imdata else 'empty'})
                if not class_imdata:
                    break
                # De-dupe by dn if possible
                for item in class_imdata:
                    if not isinstance(item, dict):
                        continue
                    attrs = item.get(class_name, {}).get('attributes', {})
                    dn = attrs.get('dn')
                    if dn:
                        if dn in seen_dns:
                            continue
                        seen_dns.add(dn)
                    imdata_all.append(item)
                if len(class_imdata) < page_size:
                    break
            except Exception as exc:
                attempts.append({'path': path, 'count': 0, 'status': f'error: {exc}'})
                break
        return imdata_all, attempts

    def _ssh_command(self, command, timeout=120):
        ssh_cmd = [
            'ssh',
            '-o', 'ConnectTimeout=10',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            '-o', 'LogLevel=ERROR',
            f'{self.username}@{self.apic_host}',
            'bash', '-lc', command
        ]
        env = os.environ.copy()
        if self.password:
            ssh_cmd = ['sshpass', '-p', self.password] + ssh_cmd
        result = subprocess.run(
            ssh_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=timeout
        )
        if result.returncode == 0:
            return result.stdout
        raise RuntimeError(result.stderr.strip() or "SSH command failed")

    def _icurl_login(self):
        safe_user = self._escape_single_quotes(self.username)
        safe_pass = self._escape_single_quotes(self.password)
        payload = f'{{"aaaUser":{{"attributes":{{"name":"{safe_user}","pwd":"{safe_pass}"}}}}}}'
        cmd = f"icurl -k -s -X POST https://127.0.0.1/api/aaaLogin.json -d '{payload}'"
        output = self._ssh_command(cmd, timeout=60)
        data = json.loads(self._clean_apic_json_output(output))
        token = data.get("imdata", [{}])[0].get("aaaLogin", {}).get("attributes", {}).get("token")
        if not token:
            raise ValueError("APIC icurl login returned no token")
        self.icurl_token = token

    def _icurl_get_class(self, class_name):
        if not self.icurl_token:
            return None
        cmd = (
            "icurl -k -s "
            f"-H \"Cookie: APIC-cookie={self.icurl_token}\" "
            f"https://127.0.0.1/api/node/class/{class_name}.json"
        )
        return self._ssh_command(cmd, timeout=60)

    def _icurl_get_url(self, path):
        if not self.icurl_token:
            return None
        cmd = (
            "icurl -k -s "
            f"-H \"Cookie: APIC-cookie={self.icurl_token}\" "
            f"https://127.0.0.1{path}"
        )
        return self._ssh_command(cmd, timeout=60)

    def _moquery_get_class(self, class_name):
        cmd = f"moquery -c {class_name} -o json"
        return self._ssh_command(cmd, timeout=120)

    def _extract_imdata_type(self, item):
        if not isinstance(item, dict):
            return None
        if len(item) == 1:
            return next(iter(item.keys()))
        return item.get("type")

    def _collect_children_types(self, item, allowed_types):
        found = []
        if not isinstance(item, dict):
            return found
        for key, value in item.items():
            if not isinstance(value, dict):
                continue
            children = value.get('children', [])
            for child in children:
                child_type = self._extract_imdata_type(child)
                if child_type in allowed_types:
                    found.append(child)
                found.extend(self._collect_children_types(child, allowed_types))
        return found

    def _parse_imdata(self, output, target_class=None, allowed_types=None):
        if not output:
            return []
        cleaned = self._clean_apic_json_output(output)
        data = json.loads(cleaned)
        imdata = data.get('imdata', [])
        if imdata and (target_class or allowed_types):
            if allowed_types is None:
                allowed_types = [target_class]
            filtered = [
                item for item in imdata
                if self._extract_imdata_type(item) in allowed_types
            ]
            if filtered:
                imdata = filtered
            else:
                child_matches = []
                for item in imdata:
                    child_matches.extend(self._collect_children_types(item, allowed_types))
                imdata = child_matches
        return imdata

    def _update_discovered_nodes(self, imdata):
        for item in imdata:
            if not isinstance(item, dict) or 'fabricNode' not in item:
                continue
            attributes = item.get('fabricNode', {}).get('attributes', {})
            node_id = attributes.get('id')
            pod_id = attributes.get('podId')
            dn = attributes.get('dn', '')
            if not pod_id and dn:
                match = re.search(r'topology/pod-(\d+)/node-(\d+)', dn)
                if match:
                    pod_id = match.group(1)
                    if not node_id:
                        node_id = match.group(2)
            if node_id:
                node_id = str(node_id)
                if pod_id is not None:
                    pod_id = str(pod_id)
                    self.discovered_pods.add(pod_id)
                    self.discovered_nodes[node_id] = pod_id

    def _build_query_candidates(self, class_name, aggressive=False):
        queries = []

        def add(path):
            if path not in queries:
                queries.append(path)

        if class_name in LARGE_QUERY_CLASSES:
            add(f"/api/node/class/{class_name}.json?page=0&page-size=50000")
            add(f"/api/node/class/{class_name}.json?page=1&page-size=50000")

        add(f"/api/node/class/{class_name}.json")
        add(f"/api/class/{class_name}.json")

        order_attr = ORDER_BY_ATTR.get(class_name)
        if order_attr:
            add(f"/api/node/class/{class_name}.json?order-by={class_name}.{order_attr}")

        add(f"/api/node/class/{class_name}.json?query-target=self")
        add(f"/api/node/class/{class_name}.json?rsp-subtree=full")
        add(f"/api/node/class/{class_name}.json?page=0&page-size=50000")
        add(f"/api/node/class/{class_name}.json?page=1&page-size=50000")
        add(f"/api/node/class/{class_name}.json?page=2&page-size=50000")

        add(f"/api/node/mo/topology.json?query-target=subtree&target-subtree-class={class_name}")
        for pod_id in sorted(self.discovered_pods):
            add(f"/api/node/mo/topology/pod-{pod_id}.json?query-target=subtree&target-subtree-class={class_name}")
        for node_id, pod_id in sorted(self.discovered_nodes.items()):
            add(f"/api/node/mo/topology/pod-{pod_id}/node-{node_id}.json?query-target=subtree&target-subtree-class={class_name}")

        if class_name == 'eqptFex':
            add("/api/node/mo/sys.json?query-target=subtree&target-subtree-class=eqptFex")
            add("/api/node/mo/sys/extch.json?query-target=subtree&target-subtree-class=eqptFex")
            add("/api/node/class/eqptFex.json?query-target-filter=eq(eqptFex.operSt,\"online\")")
            add("/api/node/class/eqptExtCh.json")
            add("/api/node/class/eqptCh.json?query-target=subtree&target-subtree-class=eqptFex")
            for fex_id in range(101, 106):
                add(f"/api/node/mo/sys/extch/fex-{fex_id}.json")

        if class_name == 'fvRsPathAtt':
            add("/api/node/class/fvRsPathAtt.json?query-target-filter=wcArd(fvRsPathAtt.tDn,\"extch\")")
            add("/api/node/class/fvRsPathAtt.json?query-target-filter=wcArd(fvRsPathAtt.dn,\"extch\")")
            add("/api/node/class/fvRsPathAtt.json?query-target-filter=wcArd(fvRsPathAtt.tDn,\"paths-\")")
            add("/api/node/class/fvRsPathAtt.json?query-target-filter=wcArd(fvRsPathAtt.tDn,\"protpaths-\")")
            add("/api/node/class/fvRsPathAtt.json?query-target-filter=wcArd(fvRsPathAtt.dn,\"extpaths-\")")
            add("/api/node/class/fvAEPg.json?rsp-subtree=children&rsp-subtree-class=fvRsPathAtt")

        if not self.discovered_pods:
            add(f"/api/node/mo/topology/pod-1.json?query-target=subtree&target-subtree-class={class_name}")
            add(f"/api/node/mo/topology/pod-2.json?query-target=subtree&target-subtree-class={class_name}")
            for node_id in range(101, 105):
                add(f"/api/node/mo/topology/pod-1/node-{node_id}.json?query-target=subtree&target-subtree-class={class_name}")

        if aggressive:
            tenant_scoped = (
                class_name.startswith('fv')
                or class_name.startswith('vz')
                or class_name.startswith('l3ext')
                or class_name.startswith('vmm')
                or class_name.startswith('infra')
                or class_name.startswith('fvns')
            )
            if tenant_scoped:
                add(f"/api/node/mo/uni.json?query-target=subtree&target-subtree-class={class_name}")
            add(f"/api/node/mo/sys.json?query-target=subtree&target-subtree-class={class_name}")
            add(f"/api/node/mo/sys/extch.json?query-target=subtree&target-subtree-class={class_name}")

        return queries

    def _fetch_with_fallbacks(self, class_name, aggressive=False):
        queries = self._build_query_candidates(class_name, aggressive=aggressive)
        last_error = None
        attempts = []
        allowed_types = ALIAS_ACCEPT_CLASSES.get(class_name, [class_name])

        if self.rest_session:
            if class_name in LARGE_QUERY_CLASSES:
                paged, page_attempts = self._fetch_paged_class(class_name, self._rest_get_url, allowed_types=allowed_types)
                for item in page_attempts:
                    attempts.append({'method': 'rest', **item})
                if paged:
                    return paged, "rest", attempts
            for idx, path in enumerate(queries, start=1):
                percent = int(round((idx / float(len(queries))) * 100))
                self.logger.info(
                    "Trying %s (rest) %s/%s (%s%%): %s",
                    class_name,
                    idx,
                    len(queries),
                    percent,
                    path
                )
                try:
                    output = self._rest_get_url(path)
                    class_imdata = self._parse_imdata(output, class_name, allowed_types=allowed_types)
                    if class_imdata:
                        attempts.append({'method': 'rest', 'path': path, 'count': len(class_imdata), 'status': 'success'})
                        return class_imdata, "rest", attempts
                    attempts.append({'method': 'rest', 'path': path, 'count': 0, 'status': 'empty'})
                except Exception as exc:
                    last_error = f"REST {path}: {exc}"
                    attempts.append({'method': 'rest', 'path': path, 'count': 0, 'status': f'error: {exc}'})

        if self.icurl_token:
            if class_name in LARGE_QUERY_CLASSES:
                paged, page_attempts = self._fetch_paged_class(class_name, self._icurl_get_url, allowed_types=allowed_types)
                for item in page_attempts:
                    attempts.append({'method': 'icurl', **item})
                if paged:
                    return paged, "icurl", attempts
            for idx, path in enumerate(queries, start=1):
                percent = int(round((idx / float(len(queries))) * 100))
                self.logger.info(
                    "Trying %s (icurl) %s/%s (%s%%): %s",
                    class_name,
                    idx,
                    len(queries),
                    percent,
                    path
                )
                try:
                    output = self._icurl_get_url(path)
                    class_imdata = self._parse_imdata(output, class_name, allowed_types=allowed_types)
                    if class_imdata:
                        attempts.append({'method': 'icurl', 'path': path, 'count': len(class_imdata), 'status': 'success'})
                        return class_imdata, "icurl", attempts
                    attempts.append({'method': 'icurl', 'path': path, 'count': 0, 'status': 'empty'})
                except Exception as exc:
                    last_error = f"icurl {path}: {exc}"
                    attempts.append({'method': 'icurl', 'path': path, 'count': 0, 'status': f'error: {exc}'})

        try:
            output = self._moquery_get_class(class_name)
            class_imdata = self._parse_imdata(output, class_name)
            if class_imdata:
                attempts.append({'method': 'moquery', 'path': None, 'count': len(class_imdata), 'status': 'success'})
                return class_imdata, "moquery", attempts
            attempts.append({'method': 'moquery', 'path': None, 'count': 0, 'status': 'empty'})
        except Exception as exc:
            last_error = f"moquery: {exc}"
            attempts.append({'method': 'moquery', 'path': None, 'count': 0, 'status': f'error: {exc}'})

        return None, last_error or "no data returned", attempts

    def _has_fex_indicators_in_imdata(self, imdata):
        for item in imdata:
            if not isinstance(item, dict) or 'fvRsPathAtt' not in item:
                continue
            attributes = item.get('fvRsPathAtt', {}).get('attributes', {})
            tdn = attributes.get('tDn', '')
            dn = attributes.get('dn', '')
            if 'extch' in tdn or 'extpaths' in tdn or 'extch' in dn:
                return True
        return False

    def _retry_missing_classes(self, missing_classes):
        recovered = {}
        for class_name in missing_classes:
            class_imdata, method_or_error, attempts = self._fetch_with_fallbacks(class_name, aggressive=True)
            if class_imdata:
                recovered[class_name] = (class_imdata, method_or_error, attempts)
            else:
                self.summary['class_details'][class_name] = attempts
        return recovered

    def collect(self, classes):
        self.summary['classes_requested'] = classes

        # REST login
        try:
            self._rest_login()
            self.logger.info("REST login successful")
        except Exception as exc:
            self.logger.warning("REST login failed: %s", exc)

        # icurl login
        try:
            self._icurl_login()
            self.logger.info("icurl login successful")
        except Exception as exc:
            self.logger.warning("icurl login failed: %s", exc)

        imdata = []
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        for class_name in classes:
            self.logger.info("Collecting %s", class_name)
            class_imdata, method_or_error, attempts = self._fetch_with_fallbacks(class_name)
            self.summary['class_details'][class_name] = attempts
            if not class_imdata:
                self.summary['class_errors'].append(f"{class_name}: {method_or_error}")
                continue
            imdata.extend(class_imdata)
            self.summary['classes_collected'].append(class_name)
            if class_name == 'fabricNode':
                self._update_discovered_nodes(class_imdata)
            if method_or_error and method_or_error not in self.summary['methods_used']:
                self.summary['methods_used'].append(method_or_error)
            class_output_path = os.path.join(
                self.output_dir,
                f"apic_{self.apic_host}_{timestamp}_{class_name}.json"
            )
            with open(class_output_path, 'w', encoding='utf-8') as handle:
                json.dump({"imdata": class_imdata}, handle, indent=2)
            self.summary['class_files'][class_name] = class_output_path

        completeness_missing = [
            class_name for class_name in DATA_COMPLETENESS_CLASSES
            if class_name not in self.summary['classes_collected']
        ]
        if completeness_missing:
            recovered = self._retry_missing_classes(completeness_missing)
            for class_name, (class_imdata, method_or_error, attempts) in recovered.items():
                imdata.extend(class_imdata)
                self.summary['classes_collected'].append(class_name)
                self.summary['class_details'][class_name] = attempts
                if class_name == 'fabricNode':
                    self._update_discovered_nodes(class_imdata)
                if method_or_error and method_or_error not in self.summary['methods_used']:
                    self.summary['methods_used'].append(method_or_error)
                class_output_path = os.path.join(
                    self.output_dir,
                    f"apic_{self.apic_host}_{timestamp}_{class_name}.json"
                )
                with open(class_output_path, 'w', encoding='utf-8') as handle:
                    json.dump({"imdata": class_imdata}, handle, indent=2)
                self.summary['class_files'][class_name] = class_output_path

        collected_set = set(self.summary['classes_collected'])
        self.summary['missing_required'] = [
            class_name for class_name in REQUIRED_ACI_CLASSES
            if class_name not in collected_set
        ]
        self.summary['missing_optional'] = [
            class_name for class_name in DATA_COMPLETENESS_CLASSES
            if class_name not in collected_set and class_name not in REQUIRED_ACI_CLASSES
        ]
        if 'eqptFex' not in collected_set:
            if 'eqptFex' not in self.summary['missing_required']:
                self.summary['missing_required'].append('eqptFex')
            self.summary['missing_optional'] = [
                class_name for class_name in self.summary['missing_optional']
                if class_name != 'eqptFex'
            ]
        if self.summary['missing_required']:
            self.logger.warning("Missing required classes: %s", ", ".join(self.summary['missing_required']))
        if self.summary['missing_optional']:
            self.logger.warning("Missing optional classes: %s", ", ".join(self.summary['missing_optional']))

        if imdata:
            output_path = os.path.join(self.output_dir, f"apic_{self.apic_host}_{timestamp}.json")
            with open(output_path, 'w', encoding='utf-8') as handle:
                json.dump({"imdata": imdata}, handle, indent=2)
            self.summary['imdata_count'] = len(imdata)
            self.summary['output_file'] = output_path
            if self.summary['missing_required'] or self.summary['missing_optional']:
                self.summary['collection_status'] = 'partial'
            else:
                self.summary['collection_status'] = 'success'
        else:
            self.summary['collection_status'] = 'failed'

        summary_path = os.path.join(self.output_dir, f"apic_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(summary_path, 'w', encoding='utf-8') as handle:
            json.dump(self.summary, handle, indent=2)

        return self.summary


def parse_args():
    parser = argparse.ArgumentParser(description="ACI-only APIC data collector")
    parser.add_argument("--apic-host", help="APIC hostname or IP (prompted if not set)")
    parser.add_argument("--host-file", help="File with APIC hostnames (one per line)")
    parser.add_argument("--apic-username", help="APIC username (prompted if not set)")
    parser.add_argument("--output-dir", default="network_data", help="Output directory")
    parser.add_argument("--log-level", default="INFO", help="Log level")
    parser.add_argument("--aci-classes", help="Comma-separated ACI classes to collect (defaults to full set)")
    return parser.parse_args()


def main():
    args = parse_args()
    apic_hosts = []
    host_file = args.host_file
    if not host_file:
        choice = input("Use a host file with APIC hostnames? [y/N]: ").strip().lower()
        if choice in {"y", "yes"}:
            host_file = input("Host file path: ").strip()
    if host_file:
        try:
            with open(host_file, 'r', encoding='utf-8') as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    apic_hosts.append(line)
        except Exception as exc:
            print(f"Failed to read host file: {exc}")
            return 1
    else:
        apic_host = args.apic_host or input("APIC hostname or IP: ").strip()
        if not apic_host:
            print("No APIC hostname provided.")
            return 1
        apic_hosts = [apic_host]
    apic_username = args.apic_username or input("APIC username: ").strip()
    if not apic_username:
        print("No APIC username provided.")
        return 1
    apic_password = getpass.getpass("APIC password: ")

    if args.aci_classes:
        classes = [c.strip() for c in args.aci_classes.split(',') if c.strip()]
    else:
        classes = DEFAULT_ACI_CLASSES

    def collect_for_host(apic_host):
        host_output = os.path.join(args.output_dir, apic_host)
        collector = APICCollector(
            apic_host=apic_host,
            username=apic_username,
            password=apic_password,
            output_dir=host_output,
            log_level=args.log_level
        )
        summary = collector.collect(classes)
        summary['fabric_name'] = apic_host
        summary['description'] = ''
        summary_path = os.path.join(host_output, 'collector_manifest.json')
        try:
            with open(summary_path, 'w', encoding='utf-8') as handle:
                json.dump(summary, handle, indent=2)
        except Exception:
            pass
        return apic_host, summary

    final_status = 0
    max_threads = 1
    if len(apic_hosts) > 1:
        try:
            thread_input = input(f"Parallel threads (1-{len(apic_hosts)}, default 4): ").strip()
            if thread_input:
                max_threads = max(1, min(int(thread_input), len(apic_hosts)))
            else:
                max_threads = min(4, len(apic_hosts))
        except Exception:
            max_threads = min(4, len(apic_hosts))

    if max_threads > 1:
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            future_map = {executor.submit(collect_for_host, host): host for host in apic_hosts}
            for future in as_completed(future_map):
                apic_host, summary = future.result()
                status = summary.get('collection_status', 'failed')
                print(f"[{apic_host}] APIC collection status: {status}")
                print(f"[{apic_host}] Classes collected: {len(summary.get('classes_collected', []))}/{len(classes)}")
                print(f"[{apic_host}] Output: {summary.get('output_file', '')}")
                if summary.get('missing_required'):
                    print(f"[{apic_host}] Missing required classes: {', '.join(summary.get('missing_required', []))}")
                if status != 'success':
                    final_status = 1
    else:
        for apic_host in apic_hosts:
            apic_host, summary = collect_for_host(apic_host)
            status = summary.get('collection_status', 'failed')
            print(f"[{apic_host}] APIC collection status: {status}")
            print(f"[{apic_host}] Classes collected: {len(summary.get('classes_collected', []))}/{len(classes)}")
            print(f"[{apic_host}] Output: {summary.get('output_file', '')}")
            if summary.get('missing_required'):
                print(f"[{apic_host}] Missing required classes: {', '.join(summary.get('missing_required', []))}")
            if status != 'success':
                final_status = 1
    zip_answer = input("Create a ZIP archive of the output? [Y/n]: ").strip().lower()
    if zip_answer in {"", "y", "yes"}:
        zip_name = input(f"ZIP filename (default: {args.output_dir}.zip): ").strip()
        if not zip_name:
            zip_name = f"{args.output_dir}.zip"
        try:
            with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(args.output_dir):
                    for file_name in files:
                        file_path = os.path.join(root, file_name)
                        rel_path = os.path.relpath(file_path, args.output_dir)
                        zf.write(file_path, rel_path)
            print(f"Created ZIP: {zip_name}")
        except Exception as exc:
            print(f"Failed to create ZIP: {exc}")
            final_status = 1
    return final_status


if __name__ == "__main__":
    raise SystemExit(main())
