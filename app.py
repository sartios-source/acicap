import json
import logging
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from flask import Flask, jsonify, render_template, request, session, redirect, url_for, send_file
from werkzeug.utils import secure_filename
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache

from config import get_config
from analysis import CapacityAnalyzer, FabricManager
from analysis.export import export_fabric_excel

app = Flask(__name__)
config_class = get_config(os.environ.get("FLASK_ENV", "development"))
app.config.from_object(config_class)
config_class.init_app(app)
app.secret_key = app.config["SECRET_KEY"]

csrf = CSRFProtect(app)
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=[app.config["API_RATE_LIMIT"]])
cache = Cache(app, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300})

BASE_DIR = app.config["BASE_DIR"]
FABRICS_DIR = app.config["FABRICS_DIR"]
OUTPUT_DIR = app.config["OUTPUT_DIR"]

fm = FabricManager(FABRICS_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("acicap")

ANALYZER_CACHE: Dict[str, Dict[str, Any]] = {}


def validate_fabric_name(name: str) -> str:
    import re
    if not name or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", name.strip()):
        raise ValueError("Invalid fabric name. Use alphanumeric, dot, underscore, hyphen (1-64).")
    return name.strip()


def _get_analyzer(fabric_name: str):
    fabric_data = fm.get_fabric_data(fabric_name)
    modified = fabric_data.get("modified", "")
    cached = ANALYZER_CACHE.get(fabric_name)
    if cached and cached.get("modified") == modified:
        return cached["analyzer"]
    analyzer = CapacityAnalyzer(fabric_data)
    ANALYZER_CACHE[fabric_name] = {"modified": modified, "analyzer": analyzer}
    return analyzer


def _get_cached_summary(fabric_name: str):
    cache_key = f"summary:{fabric_name}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    analyzer = _get_analyzer(fabric_name)
    summary = analyzer.summarize()
    cache.set(cache_key, summary, timeout=600)
    return summary


def _get_cached_analysis(fabric_name: str):
    cache_key = f"analysis:{fabric_name}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    analyzer = _get_analyzer(fabric_name)
    analysis = analyzer.analyze()
    cache.set(cache_key, analysis, timeout=600)
    return analysis


@app.context_processor
def inject_fabrics():
    return {"fabrics": fm.list_fabrics(), "current_fabric": session.get("current_fabric")}


@app.route("/")
def index():
    current_fabric = session.get("current_fabric")
    fabrics = fm.list_fabrics()
    totals = {
        "leafs": 0,
        "spines": 0,
        "fex": 0,
        "tenants": 0,
        "vrfs": 0,
        "bds": 0,
        "epgs": 0,
        "subnets": 0,
        "contracts": 0,
        "endpoints": 0,
        "ports": 0,
        "ports_with_epg": 0,
    }
    return render_template("index.html", current_fabric=current_fabric, fabrics=fabrics, totals=totals)


@app.route("/api/summary/<fabric_name>")
def api_summary(fabric_name):
    fabric_name = validate_fabric_name(fabric_name)
    return jsonify(_get_cached_summary(fabric_name))


@app.route("/upload_page")
def upload_page():
    current_fabric = session.get("current_fabric")
    datasets = []
    if current_fabric:
        datasets = fm.get_fabric_data(current_fabric).get("datasets", [])
    return render_template("upload.html", current_fabric=current_fabric, datasets=datasets)


@app.route("/fabrics", methods=["GET"])
def list_fabrics():
    return jsonify(fm.list_fabrics())


@app.route("/fabrics", methods=["POST"])
@csrf.exempt
def create_fabric():
    data = request.get_json(silent=True) or {}
    name = validate_fabric_name(data.get("name", ""))
    description = str(data.get("description", "")).strip()
    fm.create_fabric(name, description=description)
    session["current_fabric"] = name
    return jsonify({"success": True, "fabric": name})


@app.route("/fabrics/<fabric_name>", methods=["DELETE"])
@csrf.exempt
def delete_fabric(fabric_name):
    fabric_name = validate_fabric_name(fabric_name)
    fm.delete_fabric(fabric_name)
    ANALYZER_CACHE.pop(fabric_name, None)
    if session.get("current_fabric") == fabric_name:
        session.pop("current_fabric", None)
    return jsonify({"success": True})


@app.route("/fabrics/reset", methods=["POST"])
@csrf.exempt
def reset_fabrics():
    fabrics = [f["name"] for f in fm.list_fabrics()]
    for name in fabrics:
        try:
            fm.delete_fabric(name)
        except Exception:
            continue
        ANALYZER_CACHE.pop(name, None)
        cache.delete(f"summary:{name}")
        cache.delete(f"analysis:{name}")
    session.pop("current_fabric", None)
    return jsonify({"success": True, "deleted": len(fabrics)})


@app.route("/fabrics/<fabric_name>/meta", methods=["POST"])
@csrf.exempt
def update_fabric_meta(fabric_name):
    fabric_name = validate_fabric_name(fabric_name)
    data = request.get_json(silent=True) or {}
    fabric_data = fm.get_fabric_data(fabric_name)
    description = str(data.get("description", fabric_data.get("description", ""))).strip()
    uplinks_per_leaf = data.get("uplinks_per_leaf")
    uplink_speed = data.get("uplink_speed")
    scale_profile = data.get("scale_profile")
    endpoint_profile = data.get("endpoint_profile")
    fabric_data["description"] = description
    if uplinks_per_leaf is not None:
        try:
            if uplinks_per_leaf == "":
                fabric_data.pop("uplinks_per_leaf", None)
            else:
                fabric_data["uplinks_per_leaf"] = int(uplinks_per_leaf)
        except Exception:
            return jsonify({"error": "uplinks_per_leaf must be an integer"}), 400
    if scale_profile:
        fabric_data["scale_profile"] = str(scale_profile).upper()
    if endpoint_profile:
        fabric_data["endpoint_profile"] = str(endpoint_profile).lower()
    if uplink_speed:
        fabric_data["uplink_speed"] = str(uplink_speed).upper()
    fm.save_fabric_metadata(fabric_name, fabric_data)
    ANALYZER_CACHE.pop(fabric_name, None)
    return jsonify({"success": True})

@app.route("/fabrics/<fabric_name>/select", methods=["POST"])
@csrf.exempt
def select_fabric(fabric_name):
    fabric_name = validate_fabric_name(fabric_name)
    if fabric_name not in [f["name"] for f in fm.list_fabrics()]:
        return jsonify({"error": "Fabric not found"}), 404
    session["current_fabric"] = fabric_name
    return jsonify({"success": True, "fabric": fabric_name})


def _validate_file_upload(file) -> str:
    if not file or file.filename == "":
        raise ValueError("No file selected")
    filename = secure_filename(file.filename)
    if "." not in filename:
        raise ValueError("Invalid filename")
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in app.config["ALLOWED_EXTENSIONS"]:
        raise ValueError(f"File type .{ext} not allowed")
    return filename


@app.route("/upload", methods=["POST"])
@csrf.exempt
@limiter.exempt
def upload():
    current_fabric = session.get("current_fabric")
    if not current_fabric:
        return jsonify({"error": "No fabric selected"}), 400
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    try:
        filename = _validate_file_upload(file)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    fabric_dir = FABRICS_DIR / current_fabric
    fabric_dir.mkdir(parents=True, exist_ok=True)
    file_path = (fabric_dir / filename).resolve()
    file.save(str(file_path))

    ext = filename.rsplit(".", 1)[-1].lower()
    if ext != "json":
        return jsonify({"error": "Only JSON uploads are supported for ACI data."}), 400
    dataset = {
        "filename": filename,
        "type": "aci",
        "format": ext,
        "uploaded": datetime.now().isoformat(),
        "path": str(file_path),
        "size": file_path.stat().st_size
    }
    fm.add_dataset(current_fabric, dataset)
    ANALYZER_CACHE.pop(current_fabric, None)
    cache.delete(f"summary:{current_fabric}")
    cache.delete(f"analysis:{current_fabric}")
    return jsonify({"success": True, "filename": filename})


@app.route("/api/collector/import", methods=["POST"])
@csrf.exempt
def import_collector_zip():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    upload_file = request.files["file"]
    filename = secure_filename(upload_file.filename or "")
    if not filename.lower().endswith(".zip"):
        return jsonify({"error": "Only .zip files are supported"}), 400

    base_tmp = BASE_DIR / "tmp_import"
    base_tmp.mkdir(parents=True, exist_ok=True)
    temp_dir = base_tmp / f"acicap_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    zip_path = os.path.join(str(temp_dir), filename)
    upload_file.save(zip_path)
    imported = []
    results = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(str(temp_dir))
        for root, _, files in os.walk(str(temp_dir)):
            if "collector_manifest.json" not in files:
                continue
            manifest_path = os.path.join(root, "collector_manifest.json")
            try:
                manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            except Exception:
                manifest = {}
            fabric_name = validate_fabric_name(manifest.get("fabric_name") or os.path.basename(root))
            if fabric_name not in [f["name"] for f in fm.list_fabrics()]:
                fm.create_fabric(fabric_name, description=str(manifest.get("description") or ""))

            fabric_dir = FABRICS_DIR / fabric_name / "imports" / datetime.now().strftime("%Y%m%d_%H%M%S")
            fabric_dir.mkdir(parents=True, exist_ok=True)

            for file_name in files:
                if not file_name.endswith(".json") or file_name.startswith("apic_summary_"):
                    continue
                src = os.path.join(root, file_name)
                dest = fabric_dir / file_name
                shutil.copy2(src, dest)
                fm.add_dataset(fabric_name, {
                    "filename": file_name,
                    "type": "aci",
                    "format": "json",
                    "uploaded": datetime.now().isoformat(),
                    "path": str(dest),
                    "size": dest.stat().st_size
                })
            imported.append(fabric_name)
            ANALYZER_CACHE.pop(fabric_name, None)
            cache.delete(f"summary:{fabric_name}")
            cache.delete(f"analysis:{fabric_name}")
            try:
                analyzer = _get_analyzer(fabric_name)
                completeness = analyzer.get_data_completeness()
            except Exception as exc:
                completeness = {"error": str(exc)}
            results.append({
                "fabric": fabric_name,
                "completeness": completeness
            })
        return jsonify({"success": True, "fabrics": sorted(list(set(imported))), "results": results})
    finally:
        shutil.rmtree(str(temp_dir), ignore_errors=True)


@app.route("/download_offline_collector")
def download_offline_collector():
    collector_path = BASE_DIR / "offline_collector.py"
    return send_file(collector_path, as_attachment=True, download_name="offline_collector.py")


@app.route("/api/analysis/<fabric_name>")
def api_analysis(fabric_name):
    fabric_name = validate_fabric_name(fabric_name)
    return jsonify(_get_cached_analysis(fabric_name))


@app.route("/api/export/excel/<fabric_name>")
def export_excel(fabric_name):
    fabric_name = validate_fabric_name(fabric_name)
    analyzer = _get_analyzer(fabric_name)
    analysis = analyzer.analyze()
    wb = export_fabric_excel(fabric_name, analysis)
    output_path = OUTPUT_DIR / f"{fabric_name}_capacity.xlsx"
    wb.save(output_path)
    return send_file(output_path, as_attachment=True, download_name=output_path.name)


@app.route("/api/export/excel_multi", methods=["POST"])
@csrf.exempt
def export_excel_multi():
    data = request.get_json(silent=True) or {}
    fabrics = data.get("fabrics") or [f["name"] for f in fm.list_fabrics()]
    wb = None
    for fabric_name in fabrics:
        fabric_name = validate_fabric_name(fabric_name)
        analyzer = _get_analyzer(fabric_name)
        analysis = analyzer.analyze()
        fabric_wb = export_fabric_excel(fabric_name, analysis)
        if wb is None:
            wb = fabric_wb
            for sheet in wb.worksheets:
                sheet.title = f"{fabric_name} - {sheet.title}"
        else:
            for sheet in fabric_wb.worksheets:
                sheet.title = f"{fabric_name} - {sheet.title}"
                wb._add_sheet(sheet)
    output_path = OUTPUT_DIR / "multi_fabric_capacity.xlsx"
    wb.save(output_path)
    return send_file(output_path, as_attachment=True, download_name=output_path.name)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001, threaded=True, use_reloader=False)
