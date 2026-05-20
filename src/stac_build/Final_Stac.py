#!/usr/bin/env python
# coding: utf-8

# In[1]:


import os
import re
import glob
import shutil
import pandas as pd
import pystac
from pystac.extensions.eo import EOExtension
from pystac.extensions.projection import ProjectionExtension
from pystac.extensions.scientific import ScientificExtension
from pystac.extensions.scientific import Publication
from pystac.extensions.classification import ClassificationExtension
from pystac.extensions.eo import Band
import rioxarray
from datetime import timezone
from shapely.geometry import box
from rasterio.enums import Resampling
import geopandas as gpd

from pathlib import Path
from stac_validator import stac_validator
from rich import print as rprint
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree


# In[2]:



# In[3]:


# ================= 1. 路徑設定 =================
CSV_PATH = '/home/chunen/nas/bigdata/final/kurosiwo/kurosiwo_final_plus.csv'
IMERG_SRC = '/home/NAS/homes/gisele-10036/02.Course/26S_BigData/Imerg/7days_sum'
DW_SRC = '/home/chunen/nas/bigdata/final/DW'
S2_SRC = '/home/chunen/nas/bigdata/final/S2_aoi_modify'
S1_SRC = '/home/chunen/nas/bigdata/final/kurosiwo_S1_DEM'
SRTM_SRC = '/home/chunen/nas/bigdata/final/kurosiwo_S1_DEM'
MLU_SRC = '/home/chunen/nas/bigdata/final/kurosiwo_S1_DEM'
LABEL_SRC = '/home/chunen/nas/bigdata/final/kurosiwo_events'
OUTPUT_DIR = '/home/chunen/nas/bigdata/final/KuroSiwo_STAC_V8'

DW_CLASSES = [
    {"value": 0, "name": "water", "color_hint": "419BDF"},
    {"value": 1, "name": "trees", "color_hint": "397D49"},
    {"value": 2, "name": "grass", "color_hint": "88B053"},
    {"value": 3, "name": "flooded_vegetation", "color_hint": "7A87C6"},
    {"value": 4, "name": "crops", "color_hint": "E49635"},
    {"value": 5, "name": "shrub_and_scrub", "color_hint": "DFC35A"},
    {"value": 6, "name": "built", "color_hint": "C4281B"},
    {"value": 7, "name": "bare", "color_hint": "A59B8F"},
    {"value": 8, "name": "snow_and_ice", "color_hint": "B39FE1"}
]

MLU_CLASSES = [
    {"value": 0, "name": "permanent water", "color_hint": "#00FFFF"},
    {"value": 1, "name": "no water", "color_hint": "#000000"},
    {"value": 2, "name": "water", "color_hint": "#005757"},
    {"value": 3, "name": "flood", "color_hint": "#F00078"}
]

S2_BANDS = [
    Band.create(name="B4", description="Red", common_name="red"),
    Band.create(name="B3", description="Green", common_name="green"),
    Band.create(name="B2", description="Blue", common_name="blue"),
    Band.create(name="B8", description="NIR", common_name="nir")
]

# 如果 df 還沒讀，就取消下面註解
df = pd.read_csv(CSV_PATH)
# df.head()


# In[4]:


# ================= 2. 工具函數 =================
def normalize_text(text):
    """把字串整理成適合當 id / 檔名 / 資料夾名稱的格式 (空白和符號等轉換成底線)"""
    text = str(text).strip()
    text = re.sub(r'[^A-Za-z0-9]+', '_', text)
    text = re.sub(r'_+', '_', text)
    return text.strip('_')

def isoformat_z(dt):
    """轉成 STAC 常見的 UTC ISO 字串 (例如2023-01-01T12:00:00Z)"""
    if pd.isna(dt):
        return None
    return dt.isoformat().replace("+00:00", "Z")

def to_utc_timestamp(value):
    """把時間安全轉成 UTC timestamp (Pandas Timestamp 物件)"""
    dt = pd.to_datetime(value, errors='coerce')
    if pd.isna(dt):
        dt = pd.Timestamp.now(tz='UTC')
    elif dt.tzinfo is None:
        dt = dt.tz_localize(timezone.utc)
    else:
        dt = dt.tz_convert(timezone.utc)
    return dt

def union_bbox(b1, b2):
    """計算兩個 bbox 的聯集，bbox 格式為 [minx, miny, maxx, maxy]"""
    return [
        min(b1[0], b2[0]),
        min(b1[1], b2[1]),
        max(b1[2], b2[2]),
        max(b1[3], b2[3]),
    ]

def bbox_to_geometry(bbox):
    """
    利用 shapely 套件，將 bbox 的陣列格式，轉換成 STAC/GeoJSON 標準要求的 geometry dict
    例如 bbox = [0, 0, 10, 10] 會轉成：
    {'type': 'Polygon', 'coordinates': (((10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0), (10.0, 0.0)),)}
    """
    return box(bbox[0], bbox[1], bbox[2], bbox[3]).__geo_interface__

def get_num_id(row):
    """
    從 emsr_id 或 stac_item_id 中提取純數字
    例如 EMSR174 -> 174
    """
    emsr_raw = str(row.get('emsr_id', '')).strip()
    if emsr_raw and emsr_raw.lower() != 'nan':
        match = re.search(r'(\d+)', emsr_raw)
        if match:
            return match.group(1)

    stac_item_raw = str(row.get('stac_item_id', '')).strip()
    match = re.search(r'(\d+)', stac_item_raw)
    return match.group(1) if match else ""

def get_collection_prefix(row):
    """
    Collection 前綴規則：
    1. 有 EMSR 編號 -> 用 EMSR174
    2. 沒有 EMSR 編號 -> 用 stac_item_id 那串開頭
    """
    emsr_raw = str(row.get('emsr_id', '')).strip()

    if emsr_raw and emsr_raw.lower() != 'nan':
        match = re.search(r'EMSR\s*(\d+)', emsr_raw, flags=re.IGNORECASE)
        if match:
            return f"EMSR{match.group(1)}"

    stac_item_raw = str(row.get('stac_item_id', '')).strip()
    stac_item_clean = normalize_text(stac_item_raw)

    if stac_item_clean:
        return stac_item_clean

    return "UNKNOWN_EVENT"

def build_collection_id(row):
    """
    Collection 名稱：
    EMSR174_Flood_in_Skopje
    若沒 EMSR，就用 stac_item_id 開頭
    """
    prefix = get_collection_prefix(row)
    event_name = normalize_text(row.get('event', 'NoEvent'))

    if event_name:
        return f"{prefix}_{event_name}"
    return prefix

def make_row_suffix(row, index):
    """
    row-level 唯一識別，只拿來當 asset 檔名與 key，不再拿來命名 Item
    """
    stac_item_id = normalize_text(row.get('stac_item_id', ''))
    if not stac_item_id:
        stac_item_id = f"row_{index}"
    return f"{stac_item_id}_{index}"

def find_imerg_smart(row):
    """根據 stac_item_id 和 event 名稱，嘗試多種組合在 IMERG_SRC 找檔案"""
    item_id = str(row.get('stac_item_id', ''))
    event_raw = str(row.get('event', ''))
    event_query = re.sub(r'[^a-zA-Z0-9]', '*', event_raw).strip('*')

    candidates = [
        os.path.join(IMERG_SRC, f"Acc_{item_id}*.tif"),
        os.path.join(IMERG_SRC, f"Acc_*{item_id}*.tif"),
        os.path.join(IMERG_SRC, f"Acc_{event_query}*.tif"),
        os.path.join(IMERG_SRC, f"Acc_*{event_query}*.tif")
    ]

    for pattern in candidates:
        found = glob.glob(pattern)
        if found:
            return found[0]
    return None

def update_collection_extent(collection, bbox, dt):
    """
    Collection:
    - spatial extent = 所有 item 的 bbox 聯集
    - temporal extent = 最早時間 ~ 最晚時間
    """
    old_bbox = collection.extent.spatial.bboxes[0]
    new_bbox = union_bbox(old_bbox, bbox)
    collection.extent.spatial.bboxes = [new_bbox]

    old_start, old_end = collection.extent.temporal.intervals[0]

    if old_start is None or dt < old_start:
        old_start = dt
    if old_end is None or dt > old_end:
        old_end = dt

    collection.extent.temporal.intervals = [[old_start, old_end]]

def create_category_item(collection_id, category, output_dir, dt, bbox):
    """
    每個 Collection 底下建立固定的 category item：
    S1 / S2 / Precipitation / LULC ...
    """
    item = pystac.Item(
        id=category,
        geometry=bbox_to_geometry(bbox),
        bbox=bbox,
        datetime=dt,
        properties={
            "start_datetime": isoformat_z(dt),
            "end_datetime": isoformat_z(dt),
            "category": category
        }
    )

    ProjectionExtension.add_to(item)
    EOExtension.add_to(item)
    ScientificExtension.add_to(item)
    ClassificationExtension.add_to(item)

    item.set_self_href(
        os.path.join(output_dir, collection_id, category, f"{category}.json")
    )
    return item

def update_item_extent_and_time(item, bbox, dt):
    """
    跟 update_collection_extent 的概念很像，
    若同一個 category item 累積到多筆 row：
    - bbox 更新成聯集
    - geometry 更新成聯集後 bbox
    - datetime 取最早時間
    - properties 補 start/end
    """
    old_bbox = item.bbox
    new_bbox = union_bbox(old_bbox, bbox)
    item.bbox = new_bbox
    item.geometry = bbox_to_geometry(new_bbox)

    old_dt = item.datetime
    if old_dt is None or dt < old_dt:
        item.datetime = dt

    old_start = pd.to_datetime(item.properties.get("start_datetime"), utc=True, errors='coerce')
    old_end = pd.to_datetime(item.properties.get("end_datetime"), utc=True, errors='coerce')

    if pd.isna(old_start) or dt < old_start:
        old_start = dt
    if pd.isna(old_end) or dt > old_end:
        old_end = dt

    item.properties["start_datetime"] = isoformat_z(old_start)
    item.properties["end_datetime"] = isoformat_z(old_end)

def get_or_create_category_item(state, collection_id, category, dt, bbox):
    """
    從 state 取出既有 category item；若沒有就建立
    """
    if category not in state["items"]:
        item = create_category_item(collection_id, category, OUTPUT_DIR, dt, bbox)
        state["collection"].add_item(item)
        state["items"][category] = item
        state["seen_assets"][category] = set()
    else:
        item = state["items"][category]
        update_item_extent_and_time(item, bbox, dt)

    return state["items"][category]

# ================= 3. 清空輸出目錄 =================
if os.path.exists(OUTPUT_DIR):
    for item in os.listdir(OUTPUT_DIR):
        item_path = os.path.join(OUTPUT_DIR, item)
        if item not in [".git", ".ipynb_checkpoints"]:
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
            else:
                os.remove(item_path)
os.makedirs(OUTPUT_DIR, exist_ok=True)

CATALOG_DESCRIPTION = """

A comprehensive, STAC-compliant, multi-temporal dataset curated for global rapid flood mapping. 
This catalog expands upon the original Kuro Siwo dataset by structuring diverse spatiotemporal data sources around individual flood events (Collections).

# Available Asset Types
Each event collection integrates multiple distinct items aligned precisely to the event's geographical and temporal footprint:
- **Sentinel-1 (S1)**: Synthetic Aperture Radar (SAR) imagery with dual-polarization (VV/VH).
- **Sentinel-2 (S2)**: High-resolution multispectral optical imagery with B2, B3, B4, B8 bands.
- **Precipitation**: Accumulated rainfall metrics retrieved from NASA GPM IMERG Final Run L3.
- **LULC (Dynamic World)**: Near real-time 10m Land Use / Land Cover label map and 9 classes probability map.
- **DEM (SRTM)**: Downscaling using Shuttle Radar Topography Mission 1-arc second Global data.
- **MLU**: Maual labeled updated data of flood, water body, permanent water body and no water area of Kuro Siwo dataset.
- **Flood Event Labels**: Delineated ground truth annotations of flooded surface areas of Kuro Siwo dataset.

# Specifications
This dataset ensures robust standardization by incorporating multiple [STAC Extensions](https://stac-extensions.github.io/):
- **Projection**: Real-time EPSG, Shape, and Transform metrics extracted dynamically.
- **Electro-Optical (EO)**: Band mappings for optical imagery.
- **Classification**: Standardized Dynamic World terrestrial properties mapping.
- **Scientific**: Citations and DOI links to primary research literature.
"""

# ================= 4. 初始化 Catalog =================
catalog = pystac.Catalog(
    id='Expanded-KuroSiwo',
    description=CATALOG_DESCRIPTION.strip()
)
catalog.set_self_href(os.path.join(OUTPUT_DIR, "catalog.json"))

# 結構：
# collections_map[collection_id] = {
#     "collection": pystac.Collection,
#     "items": { "S1": Item, "S2": Item, ... },
#     "seen_assets": { "S1": set(), "S2": set(), ... }
# }
collections_map = {}


# In[5]:


# ================= 5. 執行迴圈 =================
for index, row in df.iterrows():
    collection_id = build_collection_id(row)
    num_id = get_num_id(row)
    dt = to_utc_timestamp(row['reference_date'])
    bbox = [row['west'], row['south'], row['east'], row['north']]
    row_suffix = make_row_suffix(row, index)

    continent = str(row.get('continent', '')).strip()

    # ---------- A. 建立 / 取用事件 Collection ----------
    if collection_id not in collections_map:
        keywords = [continent] if continent and continent.lower() != 'nan' else []
        
        event_collection = pystac.Collection(
            id=collection_id,
            title=collection_id,
            description=f"Flood event {collection_id}",
            keywords=keywords,
            extent=pystac.Extent(
                spatial=pystac.SpatialExtent(bboxes=[bbox]),
                temporal=pystac.TemporalExtent(intervals=[[dt, dt]])
            )
        )
        event_collection.set_self_href(
            os.path.join(OUTPUT_DIR, collection_id, "collection.json")
        )
        catalog.add_child(event_collection)

        collections_map[collection_id] = {
            "collection": event_collection,
            "items": {},
            "seen_assets": {}
        }
    else:
        update_collection_extent(collections_map[collection_id]["collection"], bbox, dt)

    state = collections_map[collection_id]

    # ---------- 1. Precipitation ----------
    src_imerg = find_imerg_smart(row)
    if src_imerg:
        precip_item = get_or_create_category_item(state, collection_id, "Precipitation", dt, bbox)

        # ScientificExtension
        sci_precip = ScientificExtension.ext(precip_item) 
        sci_precip.doi = "10.5067/GPM/IMERG/3B-HH/07"
        years = "2014-2022"
        sci_precip.citation = (
            f"Huffman, G.J., et al. (2023). GPM IMERG Final Run L3 Hourly 0.1 degree x 0.1 degree V07. "
            f"NASA GES DISC. Data ({years}) retrieved from Google Earth Engine (NASA/GPM_L3/IMERG_V07)."
        )

        src_key = os.path.abspath(src_imerg)

        # ProjectionExtension
        try:
            with rioxarray.open_rasterio(src_key) as rds:
                epsg = rds.rio.crs.to_epsg() if rds.rio.crs else None
                shape = list(rds.shape[-2:])
                transform = list(rds.rio.transform())[:6]

            proj = ProjectionExtension.ext(precip_item, add_if_missing=True)
            if epsg:
                proj.epsg = epsg
            proj.shape = shape
            proj.transform = transform
        except Exception as e:
            print(f"[Warning] Failed to read Projection from Precipitation {src_key}: {e}")

        # EOExtension
        eo = EOExtension.ext(precip_item, add_if_missing=True)
        eo.bands = [Band.create(name="precipitation", description="Accumulated Precipitation", common_name="precipitation")]

        if src_key not in state["seen_assets"]["Precipitation"]:
            asset_key = f"imerg_acc_{row_suffix}"
            precip_item.add_asset(
                key=asset_key,
                asset=pystac.Asset(
                    href=src_key,
                    media_type=pystac.MediaType.GEOTIFF
                )
            )
            state["seen_assets"]["Precipitation"].add(src_key)

    # ---------- 2. LULC ----------
    clean_num = str(num_id)
    # 同時搜尋 label 與 probs 檔案
    dw_candidates = glob.glob(os.path.join(DW_SRC, f"dw_kurosiwo_{clean_num}_*.tif"))
    # 過濾出我們想要的 (label 或 probs)
    found_dw = [f for f in dw_candidates if "_label" in f or "_probs" in f]

    if found_dw:
        lulc_item = get_or_create_category_item(state, collection_id, "LULC", dt, bbox)

        # ScientificExtension
        sci_lulc = ScientificExtension.ext(lulc_item) 
        sci_lulc.doi = "10.1038/s41597-022-01307-4"
        sci_lulc.citation = (
            "Brown, C.F., et al. (2022). Dynamic World, Near real-time global 10 m land use land cover mapping. "
            "Scientific Data. Data (2021-2023) retrieved from Google Earth Engine."
        )

        # 拿第一個檔案來當投影參考
        ref_src = os.path.abspath(found_dw[0])

        # ProjectionExtension
        try:
            with rioxarray.open_rasterio(ref_src) as rds:
                epsg = rds.rio.crs.to_epsg() if rds.rio.crs else None
                shape = list(rds.shape[-2:])
                transform = list(rds.rio.transform())[:6]

            proj = ProjectionExtension.ext(lulc_item, add_if_missing=True)
            if epsg:
                proj.epsg = epsg
            proj.shape = shape
            proj.transform = transform
        except Exception as e:
            print(f"[Warning] Failed to read Projection from LULC {ref_src}: {e}")

        # EOExtension & Classification
        eo = EOExtension.ext(lulc_item, add_if_missing=True)
        # 這裡定義的是 label 的波段資訊
        eo.bands = [Band.create(name="LULC", description="Dynamic World Land Use / Land Cover class", common_name="class")]
        lulc_item.properties["classification:classes"] = DW_CLASSES

        # 遍歷所有找到的檔案並加入為 Assets
        for src_dw in found_dw:
            src_key = os.path.abspath(src_dw)
            if src_key not in state["seen_assets"]["LULC"]:
                fname = os.path.basename(src_dw)
                
                # 嘗試從檔名提取日期範圍 (例如 20181126-20191125)
                date_match = re.search(r'(\d{8}-\d{8})', fname)
                date_info = f"_{date_match.group(1)}" if date_match else ""
                
                # 根據檔名決定類型
                is_probs = "_probs" in fname
                suffix = "probs" if is_probs else "label"
                
                # 產出 Asset Key (例如 dw_label_411_20181126-20191125)
                asset_key = f"dw_{suffix}_{num_id}{date_info}"
                
                asset_description = None
                if is_probs:
                    # 為機率圖提供波段說明
                    class_names = [c["name"] for c in DW_CLASSES]
                    asset_description = f"9-band probability map. Bands correspond to: {', '.join(class_names)}"

                lulc_item.add_asset(
                    key=asset_key,
                    asset=pystac.Asset(
                        href=src_key,
                        media_type=pystac.MediaType.GEOTIFF,
                        title=f"Dynamic World {suffix.capitalize()} ({num_id}{date_info})",
                        description=asset_description
                    )
                )
                state["seen_assets"]["LULC"].add(src_key)

    # ---------- 3. Sentinel-2 ----------
    s2_pattern = os.path.join(S2_SRC, "**", f"{num_id}_*.tif")
    s2_candidates = glob.glob(s2_pattern, recursive=True)

    if s2_candidates:
        s2_item = get_or_create_category_item(state, collection_id, "Sentinel-2", dt, bbox)

        # ScientificExtension
        sci_s2 = ScientificExtension.ext(s2_item) 
        sci_s2.doi = "10.5270/S2_-26n7jr4"
        sci_s2.citation = (
            "Copernicus Sentinel data (2015-2022) processed by ESA. "
            "Retrieved from Google Earth Engine (COPERNICUS/S2_SR_HARMONIZED)."
        )
        sci_s2.publications = [Publication(
            doi="10.1016/j.rse.2018.04.031",
            citation="Claverie, M., et al. (2018). The Harmonized Landsat and Sentinel-2 (HLS) product: Algorithms and methods. Remote Sensing of Environment."
        )]

        for src_s2 in s2_candidates:
            src_key = os.path.abspath(src_s2)

            # ProjectionExtension & EOExtension
            if not ProjectionExtension.ext(s2_item).shape:
                try:
                    with rioxarray.open_rasterio(src_key) as rds:
                        epsg = rds.rio.crs.to_epsg() if rds.rio.crs else None
                        shape = list(rds.shape[-2:])
                        transform = list(rds.rio.transform())[:6]

                    proj = ProjectionExtension.ext(s2_item, add_if_missing=True)
                    if epsg:
                        proj.epsg = epsg
                    proj.shape = shape
                    proj.transform = transform

                    eo = EOExtension.ext(s2_item, add_if_missing=True)
                    eo.bands = S2_BANDS
                except Exception as e:
                    print(f"[Warning] Failed to read Projection from S2 {src_key}: {e}")

            if src_key in state["seen_assets"]["Sentinel-2"]:
                continue

            original_name = os.path.basename(src_s2)
            asset_key = f"s2_{normalize_text(os.path.splitext(original_name)[0])}"
            s2_item.add_asset(
                key=asset_key,
                asset=pystac.Asset(
                    href=src_key,
                    media_type=pystac.MediaType.GEOTIFF
                )
            )
            state["seen_assets"]["Sentinel-2"].add(src_key)

    # ---------- 4. Sentinel-1 ----------
    s1_folder = os.path.join(S1_SRC, str(num_id))
    if os.path.exists(s1_folder):
        s1_candidates = [
            f for f in glob.glob(os.path.join(s1_folder, "**", "*.*"), recursive=True)
            if 'SL' in os.path.basename(f) or 'MS' in os.path.basename(f)
        ]

        if s1_candidates:
            s1_item = get_or_create_category_item(state, collection_id, "Sentinel-1", dt, bbox)

            # ScientificExtension
            sci_s1 = ScientificExtension.ext(s1_item)
            sci_s1.doi = "10.5270/S1-d363604"
            sci_s1.citation = (
                "Copernicus Sentinel-1 data processed by ESA."
                "Merged from Kuro Siwo dataset."
            )

            for src_s1 in s1_candidates:
                src_key = os.path.abspath(src_s1)

                # ProjectionExtension & EOExtension
                if not ProjectionExtension.ext(s1_item).shape:
                    try:
                        with rioxarray.open_rasterio(src_key) as rds:
                            epsg = rds.rio.crs.to_epsg() if rds.rio.crs else None
                            shape = list(rds.shape[-2:])
                            transform = list(rds.rio.transform())[:6]

                        proj = ProjectionExtension.ext(s1_item, add_if_missing=True)
                        if epsg:
                            proj.epsg = epsg
                        proj.shape = shape
                        proj.transform = transform

                        eo = EOExtension.ext(s1_item, add_if_missing=True)
                        eo.bands = [
                            Band.create(name="VV", description="Vertical Transmit, Vertical Receive", common_name="vv"),
                            Band.create(name="VH", description="Vertical Transmit, Horizontal Receive", common_name="vh")
                        ]
                    except Exception as e:
                        print(f"[Warning] Failed to read Projection from S1 {src_key}: {e}")

                if src_key in state["seen_assets"]["Sentinel-1"]:
                    continue

                original_name = os.path.basename(src_s1)
                asset_key = f"s1_{normalize_text(os.path.splitext(original_name)[0])}"
                s1_item.add_asset(
                    key=asset_key,
                    asset=pystac.Asset(
                        href=src_key,
                        media_type=pystac.MediaType.GEOTIFF if src_key.lower().endswith('.tif') else None
                    )
                )
                state["seen_assets"]["Sentinel-1"].add(src_key)

    # ---------- 5. SRTM ----------
    srtm_folder = os.path.join(SRTM_SRC, str(num_id))
    if os.path.exists(srtm_folder):
        srtm_candidates = [
            f for f in glob.glob(os.path.join(srtm_folder, "**", "*.*"), recursive=True)
            if 'DEM' in os.path.basename(f)
        ]

        if srtm_candidates:
            srtm_item = get_or_create_category_item(state, collection_id, "SRTM", dt, bbox)

            # ScientificExtension
            sci_srtm = ScientificExtension.ext(srtm_item)
            sci_srtm.doi = "10.5067/MEaSUREs/SRTM/SRTMGL1.003"
            sci_srtm.citation = (
                "Farr, T. G., et al. (2007). The Shuttle Radar Topography Mission. "
            )
            sci_srtm.publications = [Publication(
                doi="10.1029/2005RG000183",
                citation="Farr, T. G., et al. (2007), The Shuttle Radar Topography Mission, Rev. Geophys., 45, RG2004, doi:10.1029/2005RG000183."
            )]

            for src_srtm in srtm_candidates:
                src_key = os.path.abspath(src_srtm)

                # ProjectionExtension
                if not ProjectionExtension.ext(srtm_item).shape:
                    try:
                        with rioxarray.open_rasterio(src_key) as rds:
                            epsg = rds.rio.crs.to_epsg() if rds.rio.crs else None
                            shape = list(rds.shape[-2:])
                            transform = list(rds.rio.transform())[:6]

                        proj = ProjectionExtension.ext(srtm_item, add_if_missing=True)
                        if epsg:
                            proj.epsg = epsg
                        proj.shape = shape
                        proj.transform = transform
                        
                        eo = EOExtension.ext(srtm_item, add_if_missing=True)
                        eo.bands = [Band.create(name="elevation", description="Digital Elevation Model", common_name="elevation")]
                    except Exception as e:
                        print(f"[Warning] Failed to read Projection from SRTM {src_key}: {e}")

                if src_key in state["seen_assets"]["SRTM"]:
                    continue

                original_name = os.path.basename(src_srtm)
                asset_key = f"srtm_{normalize_text(os.path.splitext(original_name)[0])}"
                srtm_item.add_asset(
                    key=asset_key,
                    asset=pystac.Asset(
                        href=src_key,
                        media_type=pystac.MediaType.GEOTIFF if src_key.lower().endswith('.tif') else None
                    )
                )
                state["seen_assets"]["SRTM"].add(src_key)

    # ---------- 6. MLU ----------
    mlu_folder = os.path.join(MLU_SRC, str(num_id))
    if os.path.exists(mlu_folder):
        mlu_candidates = [
            f for f in glob.glob(os.path.join(mlu_folder, "**", "*.*"), recursive=True)
            if 'MLU' in os.path.basename(f)
        ]

        if mlu_candidates:
            mlu_item = get_or_create_category_item(state, collection_id, "MLU", dt, bbox)

            # ScientificExtension
            sci_mlu = ScientificExtension.ext(mlu_item) 
            sci_mlu.doi = "10.52202/079017-1204"
            sci_mlu.citation = (
                "@inproceedings{NEURIPS2024_43612b06,"
                "author = {Bountos, Nikolaos Ioannis and Sdraka, Maria and Zavras, Angelos and Karavias, Andreas and Karasante, Ilektra and Herekakis, Themistocles and Thanasou, Angeliki and Michail, Dimitrios and Papoutsis, Ioannis},"
                "booktitle = {Advances in Neural Information Processing Systems},"
                "editor = {A. Globerson and L. Mackey and D. Belgrave and A. Fan and U. Paquet and J. Tomczak and C. Zhang},"
                "pages = {38105--38121},"
                "publisher = {Curran Associates, Inc.},"
                "title = {Kuro Siwo: 33 billion m\^{}2 under the water. A global multi-temporal satellite dataset for rapid flood mapping},"
                "url = {https://proceedings.neurips.cc/paper_files/paper/2024/file/43612b0662cb6a4986edf859fd6ebafe-Paper-Datasets_and_Benchmarks_Track.pdf},"
                "volume = {37},"
                "year = {2024}"
                "}"
            )

            # ClassificationExtension
            mlu_item.properties["classification:classes"] = MLU_CLASSES

            for src_mlu in mlu_candidates:
                src_key = os.path.abspath(src_mlu)

                # ProjectionExtension
                if not ProjectionExtension.ext(mlu_item).shape:
                    try:
                        with rioxarray.open_rasterio(src_key) as rds:
                            epsg = rds.rio.crs.to_epsg() if rds.rio.crs else None
                            shape = list(rds.shape[-2:])
                            transform = list(rds.rio.transform())[:6]

                        proj = ProjectionExtension.ext(mlu_item, add_if_missing=True)
                        if epsg:
                            proj.epsg = epsg
                        proj.shape = shape
                        proj.transform = transform
                        
                        eo = EOExtension.ext(mlu_item, add_if_missing=True)
                        eo.bands = [Band.create(name="label", description="Manual Labeling Update", common_name="class")]
                    except Exception as e:
                        print(f"[Warning] Failed to read Projection from MLU {src_key}: {e}")

                if src_key in state["seen_assets"]["MLU"]:
                    continue

                original_name = os.path.basename(src_mlu)
                asset_key = f"mlu_{normalize_text(os.path.splitext(original_name)[0])}"
                mlu_item.add_asset(
                    key=asset_key,
                    asset=pystac.Asset(
                        href=src_key,
                        media_type=pystac.MediaType.GEOTIFF if src_key.lower().endswith('.tif') else None
                    )
                )
                state["seen_assets"]["MLU"].add(src_key)

    # ---------- 7. flood_event_label ----------
    label_pattern = os.path.join(LABEL_SRC, str(num_id), "*", "aoi", "aoi.*")
    label_candidates = glob.glob(label_pattern)

    if label_candidates:
        label_item = get_or_create_category_item(state, collection_id, "flood_event_label", dt, bbox)

        # ScientificExtension
        sci_label = ScientificExtension.ext(label_item) 
        sci_label.doi = "10.52202/079017-1204"
        sci_label.citation = (
            "@inproceedings{NEURIPS2024_43612b06,"
            "author = {Bountos, Nikolaos Ioannis and Sdraka, Maria and Zavras, Angelos and Karavias, Andreas and Karasante, Ilektra and Herekakis, Themistocles and Thanasou, Angeliki and Michail, Dimitrios and Papoutsis, Ioannis},"
            "booktitle = {Advances in Neural Information Processing Systems},"
            "editor = {A. Globerson and L. Mackey and D. Belgrave and A. Fan and U. Paquet and J. Tomczak and C. Zhang},"
            "pages = {38105--38121},"
            "publisher = {Curran Associates, Inc.},"
            "title = {Kuro Siwo: 33 billion m\^{}2 under the water. A global multi-temporal satellite dataset for rapid flood mapping},"
            "url = {https://proceedings.neurips.cc/paper_files/paper/2024/file/43612b0662cb6a4986edf859fd6ebafe-Paper-Datasets_and_Benchmarks_Track.pdf},"
            "volume = {37},"
            "year = {2024}"
            "}"
        )

        for src_label in label_candidates:
            src_key = os.path.abspath(src_label)
            if src_key in state["seen_assets"]["flood_event_label"]:
                continue

            # 從路徑 /.../1111002/01/aoi/aoi.shp 中抓出 '01' 作為 sub_dir
            sub_dir = os.path.basename(os.path.dirname(os.path.dirname(src_key)))
            ext = os.path.splitext(src_key)[1].strip('.')
            asset_key = f"aoi_{sub_dir}_{ext}"

            # ProjectionExtension (針對 Vector layer 提取 EPSG)
            if ext.lower() == 'shp' and not ProjectionExtension.ext(label_item).epsg:
                try:
                    gdf = gpd.read_file(src_key)
                    if gdf.crs:
                        epsg = gdf.crs.to_epsg()
                        if epsg:
                            proj = ProjectionExtension.ext(label_item, add_if_missing=True)
                            proj.epsg = epsg
                except Exception:
                    pass

            # 簡單給定常見附檔名的 media_type
            media_type = None
            if ext.lower() == 'shp':
                media_type = "application/x-shapefile"
            elif ext.lower() == 'dbf':
                media_type = "application/vnd.dbf"
            elif ext.lower() == 'prj':
                media_type = "text/plain"

            label_item.add_asset(
                key=asset_key,
                asset=pystac.Asset(
                    href=src_key,
                    media_type=media_type
                )
            )
            state["seen_assets"]["flood_event_label"].add(src_key)

# ================= 6. 儲存 =================
catalog.save(catalog_type=pystac.CatalogType.SELF_CONTAINED)

print(f" STAC 結構已順利產出至: {OUTPUT_DIR}")

# ================= 7. 驗證 =================
### 使用stac_validator來驗證剛剛生成的STAC JSON文件，這個工具會檢查文件是否符合STAC規範，並返回一個包含驗證結果的字典
def validate_stac_file(json_path: Path) -> dict:
    stac = stac_validator.StacValidate(str(json_path))
    stac.run()
    return stac.message[0] if stac.message else {}

targets = [Path(OUTPUT_DIR) / "catalog.json"] + sorted(Path(OUTPUT_DIR).rglob("collection.json"))

val_table = Table(title="STAC Validation Results")
val_table.add_column("File", style="cyan")
val_table.add_column("Valid", justify="center")
val_table.add_column("STAC Version", style="dim")
val_table.add_column("Error", style="red")

all_valid = True
for target in targets:
    result = validate_stac_file(target)
    valid  = result.get("valid_stac", False)
    all_valid = all_valid and valid
    val_table.add_row(
        str(target.relative_to(Path(OUTPUT_DIR))),
        "[green]YES[/green]" if valid else "[red]NO[/red]",
        result.get("version", "?"),
        result.get("error_message", "") or "",
    )

rprint(val_table)
rprint(Panel(
    "[bold green]All files valid![/bold green]" if all_valid
    else "[bold red]Validation errors — check error_message column[/bold red]",
    expand=False,
))