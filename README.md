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

The COG pipeline (under [src/cog_pipeline/](src/cog_pipeline/)) converts all source GeoTIFFs to Cloud-Optimized GeoTIFF format and rewrites the STAC asset `href` fields accordingly. It consists of three steps:

**Step 1 — (Optional) Generate a small test input list**

```bash
bash src/cog_pipeline/gen_test_inputs.sh
# Outputs: test_inputs.txt  (one representative file per layer type)
```

**Step 2 — Convert GeoTIFFs to COG**

```bash
# Small-batch test from the txt list:
uv run python src/cog_pipeline/convert_to_cog.py \
    --list test_inputs.txt \
    --manifest manifest_test.csv

# Full batch from a directory:
uv run python src/cog_pipeline/convert_to_cog.py \
    --dir /path/to/your/data \
    --manifest manifest_full.csv

# Dry-run (plan only, no conversion):
uv run python src/cog_pipeline/convert_to_cog.py \
    --list test_inputs.txt --dry-run
```

Each GeoTIFF is converted via `gdal_translate -of COG` with DEFLATE compression and 256 px tiles. Resampling is set automatically per layer type (nearest for categorical, bilinear for continuous). A `manifest.csv` is written recording the source path, destination COG path, layer type, and conversion status for every file.

**Step 3 — Rewrite STAC asset hrefs to COG paths**

```bash
uv run python src/cog_pipeline/rewrite_stac_to_cog.py \
    --manifest manifest_full.csv \
    --src-stac KuroSiwo_STAC_V8 \
    --dst-stac KuroSiwo_STAC_V8_COG
```

This copies `KuroSiwo_STAC_V8/` to `KuroSiwo_STAC_V8_COG/` and rewrites every asset `href` that has a corresponding entry in `manifest.csv` to point to the new COG file. Any unmatched hrefs are logged to `KuroSiwo_STAC_V8_COG/_unmatched_hrefs.txt` for inspection.

```
KuroSiwo_STAC_V8/         ← original STAC (hrefs → source GeoTIFFs)
KuroSiwo_STAC_V8_COG/     ← COG STAC (hrefs → COG files, STAC structure identical)
```

### Launching the WebGIS

The WebGIS consists of a **FastAPI backend** for on-the-fly raster analysis and a **Leaflet frontend** served as a static HTML file.

**Step 1 — Configure paths in the backend**

Open [src/webgis/aoi_analysis_api.py](src/webgis/aoi_analysis_api.py) and update `APP_ROOT` and `AOI_DIR` to match the actual location of the WebGIS directory on your machine:

```python
# src/webgis/aoi_analysis_api.py  (top of file)
APP_ROOT = Path("/path/to/expanded_kuro_siwo/src/webgis")
AOI_DIR  = APP_ROOT / "aoi_geojson"
```

**Step 2 — Start the backend API server**

```bash
uv run uvicorn src.webgis.aoi_analysis_api:app --host 0.0.0.0 --port 8000
```

Verify it is running:

```bash
curl http://localhost:8000/health
# Expected: {"status":"ok"}
```

Available analysis endpoints:

| Endpoint | Description |
| :--- | :--- |
| `GET /analyze/precip?event_id=&raster_path=` | Precipitation statistics (mean, min, max, std) masked to AOI |
| `GET /analyze/lulc?event_id=&raster_path=` | LULC class composition (%) masked to AOI |
| `GET /analyze/raster_basic?event_id=&raster_path=` | Per-band statistics for any raster |
| `GET /analyze/s2rgb?event_id=&raster_path=` | Sentinel-2 RGB band statistics |

**Step 3 — Open the frontend**

Serve `index.html` from a local HTTP server (required for browser security policies):

```bash
# From the webgis directory:
python3 -m http.server 5500 --directory src/webgis
```

Then open `http://localhost:5500` in your browser. The map will load all 43 flood event AOIs from the `aoi_geojson/` directory. Click any event to browse its data layers and trigger on-the-fly analysis via the backend API.

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
