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
