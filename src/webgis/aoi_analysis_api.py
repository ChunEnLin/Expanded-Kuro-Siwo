from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import json
import numpy as np
import rasterio
from rasterio.mask import mask

APP_ROOT = Path("/home/gisele/webgis_v7_app")
AOI_DIR = APP_ROOT / "aoi_geojson"

DW_CLASS_NAMES = {
    0: "Water",
    1: "Trees",
    2: "Grass",
    3: "Flooded vegetation",
    4: "Crops",
    5: "Shrub & Scrub",
    6: "Built Area",
    7: "Bare Ground",
    8: "Snow & Ice"
}

# ================= [MODIFIED] Dynamic World RGB display palette mapping =================
DW_RGB_TO_CLASS = {
    (65, 155, 223): (0, "Water"),
    (57, 125, 73): (1, "Trees"),
    (136, 176, 83): (2, "Grass"),
    (122, 135, 198): (3, "Flooded vegetation"),
    (228, 150, 53): (4, "Crops"),
    (223, 195, 90): (5, "Shrub & Scrub"),
    (196, 40, 27): (6, "Built Area"),
    (165, 155, 143): (7, "Bare Ground"),
    (179, 159, 225): (8, "Snow & Ice")
}

def analyze_lulc_vis_rgb(out_image, nodata):
    """
    For *_vis.tif RGB rasters, classify pixels by RGB triplets.
    """
    if out_image.shape[0] < 3:
        return None

    rgb = out_image[:3].astype("uint16")
    rgb = np.moveaxis(rgb, 0, -1)   # H, W, 3

    # valid pixels: not all zero
    valid_mask = np.any(rgb != 0, axis=2)
    pixels = rgb[valid_mask]

    if pixels.size == 0:
        return []

    counts = {}
    for px in pixels:
        key = (int(px[0]), int(px[1]), int(px[2]))
        if key in DW_RGB_TO_CLASS:
            class_value, class_name = DW_RGB_TO_CLASS[key]
        else:
            # unknown RGB, skip
            continue

        if class_value not in counts:
            counts[class_value] = {
                "class_value": class_value,
                "class_name": class_name,
                "pixel_count": 0
            }
        counts[class_value]["pixel_count"] += 1

    total = sum(v["pixel_count"] for v in counts.values())
    if total == 0:
        return []

    composition = []
    for class_value in sorted(counts.keys()):
        row = counts[class_value]
        composition.append({
            "class_value": row["class_value"],
            "class_name": row["class_name"],
            "pixel_count": row["pixel_count"],
            "ratio": row["pixel_count"] / total
        })

    composition = sorted(composition, key=lambda x: x["ratio"], reverse=True)
    return composition


app = FastAPI(title="AOI Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def load_aoi_geometry(event_id: str):
    geojson_path = AOI_DIR / f"{event_id}.geojson"
    if not geojson_path.exists():
        raise HTTPException(status_code=404, detail=f"AOI GeoJSON not found for {event_id}")

    with open(geojson_path, "r", encoding="utf-8") as f:
        geo = json.load(f)

    if geo["type"] == "FeatureCollection":
        geoms = [feat["geometry"] for feat in geo["features"] if feat.get("geometry")]
    elif geo["type"] == "Feature":
        geoms = [geo["geometry"]]
    else:
        geoms = [geo]

    if not geoms:
        raise HTTPException(status_code=400, detail=f"No valid AOI geometry for {event_id}")

    return geoms

def masked_array_from_aoi(raster_path: str, geoms):
    path = Path(raster_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Raster not found: {raster_path}")

    try:
        with rasterio.open(path) as src:
            out_image, out_transform = mask(src, geoms, crop=True, filled=True)
            nodata = src.nodata
            return out_image, nodata, src.count, src.dtypes, src.descriptions
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Mask failed: {e}")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/analyze/precip")
def analyze_precip(event_id: str, raster_path: str):
    geoms = load_aoi_geometry(event_id)
    out_image, nodata, count, dtypes, descriptions = masked_array_from_aoi(raster_path, geoms)

    arr = out_image[0].astype("float64")

    if nodata is not None:
        arr[arr == nodata] = np.nan

    # 避免完全空值
    valid = arr[~np.isnan(arr)]
    if valid.size == 0:
        return {
            "event_id": event_id,
            "raster_path": raster_path,
            "type": "precipitation",
            "count_valid": 0,
            "mean": None,
            "min": None,
            "max": None,
            "std": None
        }

    return {
        "event_id": event_id,
        "raster_path": raster_path,
        "type": "precipitation",
        "count_valid": int(valid.size),
        "mean": float(np.mean(valid)),
        "min": float(np.min(valid)),
        "max": float(np.max(valid)),
        "std": float(np.std(valid))
    }

@app.get("/analyze/lulc")
def analyze_lulc(event_id: str, raster_path: str):
    geoms = load_aoi_geometry(event_id)
    out_image, nodata, count, dtypes, descriptions = masked_array_from_aoi(raster_path, geoms)

    # ================= [MODIFIED] If RGB display raster, decode via RGB palette =================
    if out_image.shape[0] >= 3:
        composition = analyze_lulc_vis_rgb(out_image, nodata)
        return {
            "event_id": event_id,
            "raster_path": raster_path,
            "type": "lulc",
            "count_valid": int(sum(r["pixel_count"] for r in composition)),
            "composition": composition
        }

    # ================= [MODIFIED] Single-band class raster fallback =================
    arr = out_image[0].astype("float64")

    if nodata is not None:
        arr[arr == nodata] = np.nan

    valid = arr[~np.isnan(arr)]
    if valid.size == 0:
        return {
            "event_id": event_id,
            "raster_path": raster_path,
            "type": "lulc",
            "count_valid": 0,
            "composition": []
        }

    vals, counts = np.unique(valid.astype(int), return_counts=True)
    total = counts.sum()

    composition = []
    for v, c in zip(vals, counts):
        composition.append({
            "class_value": int(v),
            "class_name": DW_CLASS_NAMES.get(int(v), f"Class {int(v)}"),
            "pixel_count": int(c),
            "ratio": float(c / total)
        })

    composition = sorted(composition, key=lambda x: x["ratio"], reverse=True)

    return {
        "event_id": event_id,
        "raster_path": raster_path,
        "type": "lulc",
        "count_valid": int(total),
        "composition": composition
    }

@app.get("/analyze/raster_basic")
def analyze_raster_basic(event_id: str, raster_path: str):
    geoms = load_aoi_geometry(event_id)
    out_image, nodata, count, dtypes, descriptions = masked_array_from_aoi(raster_path, geoms)

    band_stats = []
    for i in range(out_image.shape[0]):
        arr = out_image[i].astype("float64")
        if nodata is not None:
            arr[arr == nodata] = np.nan

        valid = arr[~np.isnan(arr)]
        if valid.size == 0:
            band_stats.append({
                "band_index": i + 1,
                "count_valid": 0,
                "mean": None,
                "min": None,
                "max": None,
                "std": None
            })
        else:
            band_stats.append({
                "band_index": i + 1,
                "count_valid": int(valid.size),
                "mean": float(np.mean(valid)),
                "min": float(np.min(valid)),
                "max": float(np.max(valid)),
                "std": float(np.std(valid))
            })

    return {
        "event_id": event_id,
        "raster_path": raster_path,
        "type": "raster_basic",
        "bands": band_stats
    }


# === S2 RGB AOI API PATCH ===
from pathlib import Path as _Path
import json as _json
import numpy as _np
import rasterio as _rasterio
from rasterio.mask import mask as _rio_mask
from fastapi import HTTPException as _HTTPException

_AOI_DIR_PATCH = _Path("/home/gisele/webgis_v7_app/aoi_geojson")

def _load_aoi_shapes_patch(event_id: str):
    geojson_path = _AOI_DIR_PATCH / f"{event_id}.geojson"
    if not geojson_path.exists():
        raise _HTTPException(status_code=404, detail=f"AOI geojson not found for event_id={event_id}")

    data = _json.loads(geojson_path.read_text(encoding="utf-8"))

    if data.get("type") == "FeatureCollection":
        shapes = [f["geometry"] for f in data.get("features", []) if f.get("geometry")]
    elif data.get("type") in ("Polygon", "MultiPolygon"):
        shapes = [data]
    else:
        shapes = []

    if not shapes:
        raise _HTTPException(status_code=400, detail=f"No valid AOI geometry for event_id={event_id}")

    return shapes

@app.get("/analyze/s2rgb")
def analyze_s2rgb(event_id: str, raster_path: str):
    raster_file = _Path(raster_path)
    if not raster_file.exists():
      raise _HTTPException(status_code=404, detail=f"Raster not found: {raster_path}")

    shapes = _load_aoi_shapes_patch(event_id)

    try:
        with _rasterio.open(raster_path) as src:
            clipped, _ = _rio_mask(src, shapes, crop=True, filled=False)

            if clipped.ndim != 3 or clipped.shape[0] < 3:
                raise _HTTPException(status_code=400, detail="S2 raster must contain at least 3 bands")

            labels = ["Red (display)", "Green (display)", "Blue (display)", "Band 4"]
            band_stats = []
            means = []
            valid_count = None

            for i in range(min(clipped.shape[0], 4)):
                arr = clipped[i]

                if hasattr(arr, "compressed"):
                    vals = arr.compressed()
                else:
                    vals = arr[_np.isfinite(arr)]

                vals = _np.asarray(vals, dtype="float64")
                vals = vals[_np.isfinite(vals)]

                if vals.size == 0:
                    stats = {
                        "label": labels[i] if i < len(labels) else f"Band {i+1}",
                        "min": 0.0,
                        "max": 0.0,
                        "mean": 0.0,
                        "stddev": 0.0,
                        "count_valid": 0
                    }
                else:
                    stats = {
                        "label": labels[i] if i < len(labels) else f"Band {i+1}",
                        "min": float(vals.min()),
                        "max": float(vals.max()),
                        "mean": float(vals.mean()),
                        "stddev": float(vals.std()),
                        "count_valid": int(vals.size)
                    }

                if valid_count is None:
                    valid_count = stats["count_valid"]

                band_stats.append(stats)
                means.append(stats["mean"])

            mean_brightness = float(sum(means[:3]) / 3.0) if len(means) >= 3 else None

            return {
                "event_id": event_id,
                "raster_path": raster_path,
                "type": "s2rgb",
                "count_valid": valid_count if valid_count is not None else 0,
                "bands": band_stats,
                "mean_brightness": mean_brightness
            }

    except _HTTPException:
        raise
    except Exception as e:
        raise _HTTPException(status_code=500, detail=f"s2rgb analysis failed: {e}")
