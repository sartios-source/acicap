import json
from typing import Dict, Any, List


def parse_aci_json(content: str) -> Dict[str, Any]:
    data = json.loads(content)
    imdata = data.get("imdata", data if isinstance(data, list) else [])
    objects = []
    for item in imdata:
        if isinstance(item, dict):
            if "type" in item and "attributes" in item:
                objects.append({"type": item["type"], "attributes": item.get("attributes", {})})
                continue
            if len(item) == 1:
                obj_type = next(iter(item.keys()))
                attrs = item[obj_type].get("attributes", {}) if isinstance(item[obj_type], dict) else {}
                objects.append({"type": obj_type, "attributes": attrs})
                continue
    return {"objects": objects}


def parse_aci(content: str, fmt: str) -> Dict[str, Any]:
    if fmt.lower() == "json":
        return parse_aci_json(content)
    raise ValueError(f"Unsupported ACI format: {fmt}")


def parse_cmdb_csv(_content: str) -> List[Dict[str, Any]]:
    # Placeholder for future CMDB support in capacity-only app.
    return []
