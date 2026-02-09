"""File-based fabric manager with thread safety."""
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import json
import threading


class FabricManager:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.base_dir / "index.json"
        self._lock = threading.RLock()
        with self._lock:
            if not self.index_file.exists():
                self._write_index({})

    def _read_text_safe(self, path: Path) -> str:
        for encoding in ("utf-8", "cp1252", "latin-1"):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        raise UnicodeDecodeError("utf-8", b"", 0, 1, "Unable to decode file")

    def _read_index(self) -> Dict[str, Any]:
        with self._lock:
            if not self.index_file.exists():
                return {}
            content = self._read_text_safe(self.index_file)
            return json.loads(content)

    def _write_index(self, index: Dict[str, Any]) -> None:
        with self._lock:
            tmp = self.index_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(index, indent=2), encoding="utf-8")
            tmp.replace(self.index_file)

    def list_fabrics(self) -> List[Dict[str, Any]]:
        index = self._read_index()
        fabrics = []
        for name, data in index.items():
            fabrics.append({
                "name": name,
                "created": data.get("created", ""),
                "modified": data.get("modified", ""),
                "dataset_count": len(data.get("datasets", [])),
                "description": data.get("description", "")
            })
        return sorted(fabrics, key=lambda x: x["modified"], reverse=True)

    def create_fabric(self, name: str, description: str = "") -> None:
        index = self._read_index()
        if name in index:
            raise ValueError(f"Fabric '{name}' already exists")
        now = datetime.now().isoformat()
        index[name] = {
            "created": now,
            "modified": now,
            "datasets": [],
            "description": description or ""
        }
        self._write_index(index)

    def delete_fabric(self, name: str) -> None:
        index = self._read_index()
        if name not in index:
            raise ValueError(f"Fabric '{name}' not found")
        fabric_dir = self.base_dir / name
        if fabric_dir.exists():
            import shutil
            shutil.rmtree(fabric_dir)
        del index[name]
        self._write_index(index)

    def get_fabric_data(self, name: str) -> Dict[str, Any]:
        index = self._read_index()
        if name not in index:
            return {"datasets": []}
        return index[name]

    def update_description(self, name: str, description: str) -> None:
        index = self._read_index()
        if name not in index:
            raise ValueError(f"Fabric '{name}' not found")
        index[name]["description"] = description or ""
        index[name]["modified"] = datetime.now().isoformat()
        self._write_index(index)

    def add_dataset(self, fabric_name: str, dataset: Dict[str, Any]) -> None:
        index = self._read_index()
        if fabric_name not in index:
            raise ValueError(f"Fabric '{fabric_name}' not found")
        index[fabric_name]["datasets"].append(dataset)
        index[fabric_name]["modified"] = datetime.now().isoformat()
        self._write_index(index)

    def save_fabric_metadata(self, fabric_name: str, data: Dict[str, Any]) -> None:
        index = self._read_index()
        if fabric_name not in index:
            raise ValueError(f"Fabric '{fabric_name}' not found")
        data["modified"] = datetime.now().isoformat()
        index[fabric_name] = data
        self._write_index(index)
