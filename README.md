# ACI Capacity Atlas

Commercial-grade ACI capacity analytics platform for multi-fabric environments.  
Provides offline data ingestion, scalability limits, utilization insights, and executive reporting.

## Highlights
- Multi-fabric management with cached summaries and differential updates.
- Offline collector with APIC fallback and dataset completeness validation.
- Rich per-fabric drill-down: headroom, utilization, tenants, capacity, insights.
- Executive PDF report and Excel export.
- Cisco scalability limits (APIC 5.2(4) 4-node cluster) with headroom mapping.

## Quick Start
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5001`.

## Upload / Import
- Upload ACI datasets or ZIP bundles via **Upload Data** page.
- Import ZIPs into existing or new fabrics.
- The app builds a cache to speed analysis and supports differential updates.

## Executive Report
Open `http://localhost:5001/report/<fabric>` and print/save to PDF.

## Environment Variables
- `UPLINKS_PER_LEAF_DEFAULT`: default uplinks per leaf (default: 2)
- `ACICAP_PROFILE`: enable profiling (1/true/yes)
- `SECRET_KEY`: Flask session secret

## Notes
- Large data sets benefit from cached analysis and incremental updates.
- Some pages use Bootstrap 5 for commercial-grade UI components.

## Repo
`https://github.com/sartios-source/acicap`

## Architecture (High Level)
- **Flask app** (`app.py`) serves UI + APIs for analysis, exports, and reporting.
- **Fabric manager** (`analysis/fabric_manager.py`) stores fabric metadata and datasets.
- **Analyzer** (`analysis/engine.py`) parses ACI data, applies Cisco limits, and generates insights.
- **Offline collector** (`offline_collector.py`) pulls APIC data and generates upload-ready bundles.
- **Cache** (`data/<fabric>/aci_objects_cache.json`) accelerates analysis with differential updates.

## Data Schema (Key Objects)
The analyzer expects ACI objects in `imdata` format. Key classes include:
- Required: `fabricNode`, `eqptFex`, `fvTenant`, `fvCtx`, `fvBD`, `fvAEPg`, `fvRsPathAtt`, `fvSubnet`, `ethpmPhysIf`, `physDomP`
- Optional: `vzBrCP`, `vpcDom`, `pcAggrIf`, `l3ext*`, `bgpPeerP`, `fvns*`, `vmmDomP` and others

Completeness is calculated from required + optional class coverage and surfaced in UI.

## Offline Collector Usage
1) Run collector to export data from APIC:
```bash
python offline_collector.py --apic 10.10.10.10 --user admin --password MyPass --out ./output
```

2) Upload the generated ZIP to the app or import via the Upload page.

The collector includes fallback APIC host logic and gathers datasets aligned with the analyzer.
