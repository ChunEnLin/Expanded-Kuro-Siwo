# Expanded Kuro Siwo — A STAC-Compliant Multi-Source Flood Dataset

> Final project for *Practical Applications of Environmental Big Data*  
> National Taiwan University, Spring 2026

---

## Overview

This project extends the [Kuro Siwo](https://doi.org/10.52202/079017-1204) dataset — a NeurIPS 2024 benchmark covering 33 billion m² of globally distributed flood events — by integrating complementary geospatial data sources and restructuring the entire corpus into a **STAC (SpatioTemporal Asset Catalog)**-compliant format.

---



**Source paper:**  
Bountos, N. I., Sdraka, M., Zavras, A., et al. "Kuro Siwo: 33 Billion m² under the Water. A Global Multi-Temporal Satellite Dataset for Rapid Flood Mapping." *Advances in Neural Information Processing Systems* 37 (2024), pp. 38105–38121. https://doi.org/10.52202/079017-1204

---

## Dataset Coverage

| Attribute | Value |
| :--- | :--- |
| Number of flood events | 43 |
| Event time range | 2015 – 2022 |
| Geographic coverage | Africa, Asia, Europe, North America, Oceania, South America |
| Event source | Copernicus EMS activations (EMSR codes) + field-labeled events |
| STAC layers per event | 7 |

---

## Data Layers

| Layer | Instrument / Source | Spatial Resolution | Temporal Resolution | Selected Variables | Preprocessing |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Sentinel-1** | Sentinel-1 SAR GRD (Kuro Siwo) | 10 m | 6 days | VV, VH | Tile-level files merged into single event-level GeoTIFF |
| **Sentinel-2** | Sentinel-2 MSI L2A (GEE) | 10 m | 5 days | B2, B3, B4, B8 | ±3-day mosaic composited around the reference date |
| **Precipitation** | NASA GPM IMERG Final Run L3 (GEE) | ~11 km | 30 min | Accumulated precipitation | 7-day accumulation up to event date |
| **LULC** | Dynamic World V1 (GEE) | 10 m | 5 days | 9-class label map + per-class probability maps | Year-scale composite; both categorical and probabilistic products generated |
| **DEM** | SRTM 1 Arc-Second Global (Kuro Siwo) | 10 m | Static | Elevation | Tile-level files merged into single event-level GeoTIFF |
| **MLU** | Manual Labeled Update (Kuro Siwo) | 10 m | Per-event | 0 (permanent water)<br>1 (no water)<br>2 (water)<br>3 (flood) | Tile-level files merged into single event-level GeoTIFF |
| **Flood Event Label** | Copernicus EMS delineation (Kuro Siwo) | Vector (.shp) | Per-event | Flooded area polygons | Passed through as-is |

---

## STAC Catalog Structure

```
catalog.json                          ← Root catalog
└── {EVENT_ID} collection.json/       ← One Collection per flood
    ├── Sentinel-1/
    │   └── Sentinel-1.tif
    ├── Sentinel-2/
    │   └── Sentinel-2.tif
    ├── Precipitation/
    │   └── IMERG_acc.tif
    ├── LULC/
    │   └── Dynamic_World.tif
    ├── DEM/
    │   └── SRTM.tif
    ├── Manual_Labeled_Data/
    │   └── MLU.tif
    └── Flood_Event_Labeled_Data/
        └── event_label.shp
```

Each Item carries:
- **EO Extension** — band definitions (name, common_name)
- **Projection Extension** — EPSG, shape, and affine transform extracted at build time
- **Scientific Extension** — DOI and citation for the originating dataset
- **Classification Extension** — class definitions for categorical layers (LULC, MLU)

---

## Workflow

```
Raw Kuro Siwo tiles   GEE (S2, IMERG, DW)   Copernicus EMS metadata
        │                     │                        │
        ▼                     ▼                        ▼
┌─────────────────────────────────────────────────────────────┐
│  1. Event-based Filtering & Web crawlers & Basic Data CSV   │
│     kurosiwo_data.ipynb                                     │
│     · Download Kuro Siwo dataset                            │
│     · Parse filenames for timestamps                        │
│     · Extract AOI bounding boxes via geopandas              │
│     · Web-scrape EMSR portal for event name & country       │
│     · Output as csv file                                    │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Data Download and Preprocessing                         │
│     S2_data.ipynb · IMERG_catch.ipynb · Dynamic_World.ipynb │
│     · Download target spatial range and target time data    |
|       from GEE                                              │
│     · Perform accumulation and synthesis operations         │
│     · Utilize the existing lazy evaluation, parallel        |
|       computation, and chunking mechanisms of the GEE       |
|       platform to output the data                           │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Extract Kuro Siwo files                                 │
│     extract_kurosiwo.ipynb                                  │
│     · Merge fragmented S1, DEM, MLU tiles per event         │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Data Engineering – COG strategy                         │
│     strategy.ipynb                                          │
│     · Convert GeoTIFFs to Cloud-Optimized GeoTIFF (COG)     │
│     · Benchmark tile sizes (256 / 512) with Dask            │
│     · Select optimal tiling strategy from I/O profiling     │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  5. STAC Catalog Construction                               │
│     Final_Stac.py · convert_to_cog.py ·                     |
|     rewrite_stac_to_cog.py                                  │
│     · Build Catalog → Collections → Items → Assets          │
│     · Attach EO, Projection, Scientific, Classification     │
│       metadata extracted dynamically from each file         │
│     · Validate all JSON against the STAC specification      │
|     · Convert GeoTIFFs to COG                               |
|     · Rewrite STAC asset hrefs to COG paths                 |
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  6. WebGIS Visualization                                    │
|     aoi_analysis_api.py                                     |
│     · Load STAC catalog via Leaflet front-end               │
│     · Spatial search, layer toggling, event browsing        │
└─────────────────────────────────────────────────────────────┘
```



---

## Getting Started

### Requirements

- Python ≥ 3.12
- [uv](https://docs.astral.sh/uv/) for dependency management
- GDAL command-line tools (`gdal_translate`) — required for the COG pipeline only

### Installation

```bash
git clone <repository-url>
cd expanded_kuro_siwo

uv add \
  cartopy \
  cmocean \
  dask \
  earthengine-api \
  fastapi \
  geemap \
  geopandas \
  hvplot \
  matplotlib \
  numpy \
  pandas \
  pyproj \
  pystac \
  rasterio \
  rich \
  rio-cogeo \
  rioxarray \
  shapely \
  stac-validator \
  "titiler[application]" \
  tqdm \
  "uvicorn[standard]" \
  xarray \
  zarr
```

### Building the STAC Catalog

Update the path constants at the top of [src/stac_build/Final_Stac.py](src/stac_build/Final_Stac.py) to match your local data layout, then run:

```bash
uv run python src/stac_build/Final_Stac.py
```

The script will build the catalog under `KuroSiwo_STAC_V8/` and print a STAC validation report to the terminal. The `KuroSiwo_STAC_V8/` directory in this repository serves as a pre-built sample output; asset `href` fields point to the original GeoTIFF files on the NAS.

> To obtain a catalog whose assets point to Cloud-Optimized GeoTIFFs instead, follow the COG Pipeline below to produce `KuroSiwo_STAC_V8_COG/`.

### COG Pipeline → `KuroSiwo_STAC_V8_COG`

The COG pipeline (under [src/cog_pipeline/](src/cog_pipeline/)) converts all source GeoTIFFs to Cloud-Optimized GeoTIFF format and rewrites the STAC asset `href` fields accordingly. All commands should be run from `src/cog_pipeline/`.

Each GeoTIFF is converted via `gdal_translate -of COG` with DEFLATE compression and 256 px tiles. Resampling is set automatically per layer type: `NEAREST` for categorical layers (LULC, flood labels), `BILINEAR` for continuous layers (S1, S2, DEM, Precipitation).

```bash
cd src/cog_pipeline
```

**Step 1 — Generate a small test input list (optional)**

```bash
bash gen_test_inputs.sh
# Outputs: test_inputs.txt  (one representative file per layer type)
```

**Step 2 — Dry-run to verify the plan**

```bash
python3 convert_to_cog.py --list test_inputs.txt --manifest manifest_test.csv --dry-run
```

**Step 3 — Small-batch test**

```bash
python3 convert_to_cog.py --list test_inputs.txt --manifest manifest_test.csv
```

**Step 4 — Full batch conversion, one run per data source**

```bash
python3 convert_to_cog.py \
    --dir /path/to/kurosiwo_S1_DEM   --manifest manifest_s1dem.csv

python3 convert_to_cog.py \
    --dir /path/to/DW                --manifest manifest_lulc.csv

python3 convert_to_cog.py \
    --dir /path/to/S2_aoi_modify     --manifest manifest_s2.csv

python3 convert_to_cog.py \
    --dir /path/to/Imerg/7days_sum   --manifest manifest_prec.csv
```

**Step 5 — Merge per-layer manifests into a single `manifest_full.csv`**

```bash
python3 - <<'EOF'
import csv, glob
fields = None
rows = []
for f in sorted(glob.glob("manifest_*.csv")):
    if f in ("manifest_test.csv", "manifest_full.csv"):
        continue
    with open(f) as fh:
        reader = csv.DictReader(fh)
        if fields is None:
            fields = reader.fieldnames
        rows.extend(reader)
with open("manifest_full.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
print(f"Merged: {len(rows)} entries")
EOF
```

**Step 6 — Rewrite STAC asset hrefs to COG paths**

```bash
python3 rewrite_stac_to_cog.py \
    --manifest manifest_full.csv \
    --src-stac /path/to/KuroSiwo_STAC_V8 \
    --dst-stac KuroSiwo_STAC_V8_COG
```

This copies the entire STAC directory structure to `KuroSiwo_STAC_V8_COG/` and rewrites every asset `href` that has a matching entry in `manifest_full.csv` to point to the new COG file. Any unmatched hrefs are logged to `KuroSiwo_STAC_V8_COG/_unmatched_hrefs.txt`.

```
KuroSiwo_STAC_V8/         ← original STAC (hrefs → source GeoTIFFs)
KuroSiwo_STAC_V8_COG/     ← COG STAC (hrefs → COG files, identical STAC structure)
```

### Launching the WebGIS

The WebGIS runs three services. In our lab these run on a GPU server (`up3090`) managed with `tmux`, and the browser connects via SSH port forwarding. Adjust hostnames and paths to match your own environment.

**Services overview**

| tmux session | Service | Bind port | Role |
| :--- | :--- | :--- | :--- |
| `webv7_8002` | Static HTTP server | 8002 | Serves `index.html` and static assets |
| `titiler8003` | TiTiler | 8003 | On-the-fly COG tile rendering |
| `aoiapi` | AOI Analysis API | 8004 | Raster statistics masked to event AOI |

**Step 1 — Deploy WebGIS files to the server**

Copy `src/webgis/` to the deployment directory on the server (e.g. `/home/gisele/webgis_v7_app`), then update `APP_ROOT` in [src/webgis/aoi_analysis_api.py](src/webgis/aoi_analysis_api.py) to match:

```python
# aoi_analysis_api.py  (top of file)
APP_ROOT = Path("/home/gisele/webgis_v7_app")
AOI_DIR  = APP_ROOT / "aoi_geojson"
```

**Step 2 — Start all three services on the server**

```bash
# Kill any previous sessions first
tmux kill-session -t webv7_8002  2>/dev/null
tmux kill-session -t titiler8003 2>/dev/null
tmux kill-session -t aoiapi      2>/dev/null

# Static frontend
tmux new-session -d -s webv7_8002 \
    'python3 -m http.server 8002 --bind 127.0.0.1 --directory /home/gisele/webgis_v7_app'

# TiTiler (COG tile server)
tmux new-session -d -s titiler8003 \
    'conda run -n cogenv uvicorn titiler.application.main:app --host 127.0.0.1 --port 8003'

# AOI Analysis API
tmux new-session -d -s aoiapi \
    'cd /home/gisele/webgis_v7_app && conda run -n cogenv uvicorn aoi_analysis_api:app --host 127.0.0.1 --port 8004'

# Verify all three are up
sleep 3
ss -ltnp | grep -E '8002|8003|8004'
curl http://127.0.0.1:8004/health
# Expected: {"status":"ok"}
```

**Step 3 — Open an SSH tunnel on your local machine**

```bash
# Close any existing tunnels on these ports
for p in 8080 8081 8082; do
  pid=$(lsof -ti tcp:$p) && kill $pid 2>/dev/null
done

# Forward local ports to the server (keep this terminal open)
ssh -N \
    -L 8080:127.0.0.1:8002 \
    -L 8081:127.0.0.1:8003 \
    -L 8082:127.0.0.1:8004 \
    gisele@up3090
```

| Local port | Forwarded to | Service |
| :--- | :--- | :--- |
| 8080 | server:8002 | WebGIS frontend |
| 8081 | server:8003 | TiTiler |
| 8082 | server:8004 | AOI Analysis API |

**Step 4 — Open the browser**

```
http://127.0.0.1:8080/index.html
```

The map loads all 43 flood event AOIs. Click any event to browse data layers and trigger on-the-fly analysis.

**AOI Analysis API endpoints**

| Endpoint | Description |
| :--- | :--- |
| `GET /analyze/precip?event_id=&raster_path=` | Precipitation statistics (mean, min, max, std) masked to AOI |
| `GET /analyze/lulc?event_id=&raster_path=` | LULC class composition (%) masked to AOI |
| `GET /analyze/raster_basic?event_id=&raster_path=` | Per-band statistics for any raster |
| `GET /analyze/s2rgb?event_id=&raster_path=` | Sentinel-2 RGB band statistics |

---

## Environment

The following hardware specifications are those used in our laboratory for data processing. You are not required to meet these standards.

| Component | Specification |
| :--- | :--- |
| CPU | AMD Ryzen 9 5950X (16 cores / 32 threads) |
| RAM | 78 GB |
| Storage | NAS — 84 TB |
| OS | Ubuntu (Linux) |
| Dependency manager | uv |

---

## Citation

If you use this dataset, please also cite the original Kuro Siwo paper:

```bibtex
@inproceedings{NEURIPS2024_43612b06,
  author    = {Bountos, Nikolaos Ioannis and Sdraka, Maria and Zavras, Angelos and
               Karavias, Andreas and Karasante, Ilektra and Herekakis, Themistocles and
               Thanasou, Angeliki and Michail, Dimitrios and Papoutsis, Ioannis},
  booktitle = {Advances in Neural Information Processing Systems},
  title     = {Kuro Siwo: 33 billion $m^2$ under the water. A global multi-temporal
               satellite dataset for rapid flood mapping},
  volume    = {37},
  pages     = {38105--38121},
  year      = {2024},
  url       = {https://proceedings.neurips.cc/paper_files/paper/2024/file/43612b0662cb6a4986edf859fd6ebafe-Paper-Datasets_and_Benchmarks_Track.pdf}
}
```

Additional dataset citations are embedded in the Scientific STAC extension of each item (see `src/stac_build/Final_Stac.py`).

---

## Acknowledgements

- Copernicus Emergency Management Service (EMSR activations)
- NASA GPM / IMERG
- ESA Copernicus Sentinel-1 & Sentinel-2
- Google Earth Engine — Dynamic World V1, SRTM
- Course: *Practical Applications of Environmental Big Data*, National Taiwan University
