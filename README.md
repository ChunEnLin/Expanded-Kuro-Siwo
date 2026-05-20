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

## End-to-End Workflow

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
│     S2_data.ipynb · IMERG_catch.ipynb                       │
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
│     Final_Stac.py                                           │
│     · Build Catalog → Collections → Items → Assets          │
│     · Attach EO, Projection, Scientific, Classification     │
│       metadata extracted dynamically from each file         │
│     · Validate all JSON against the STAC specification      │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  6. WebGIS Visualization                                    │
│     · Load STAC catalog via Leaflet front-end               │
│     · Spatial search, layer toggling, event browsing        │
└─────────────────────────────────────────────────────────────┘
```



---

## Getting Started

### Requirements

- Python ≥ 3.12
- [uv](https://docs.astral.sh/uv/) for dependency management

### Installation

```bash
git clone <repository-url>
cd expanded_kuro_siwo

uv add \
  cartopy \
  cmocean \
  dask \
  earthengine-api \
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
  xarray \
  zarr
```

### Building the STAC Catalog

Update the path constants at the top of [src/stac_build/Final_Stac.py](src/stac_build/Final_Stac.py) to match your local data layout, then run:

```bash
uv run python src/stac_build/Final_Stac.py
```

The script will build the catalog and print a STAC validation report to the terminal.

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
