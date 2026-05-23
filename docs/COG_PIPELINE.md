# KuroSiwo COG Pipeline

GeoTIFF → Cloud Optimized GeoTIFF (COG) → STAC Rewrite 自動化流程  
**執行環境：** Linux、Python 3、GDAL (`gdal_translate`)  

---

## 目錄結構

```
<LOCAL_DATA_ROOT>/
│
├── cog_pipeline/                         ← 本腳本目錄
│   ├── convert_to_cog.py                 ← A. GeoTIFF → COG 批次轉換
│   ├── rewrite_stac_to_cog.py            ← B. 複製 STAC 並更新 asset href
│   ├── gen_test_inputs.sh                ← 自動產生小批次測試清單
│   ├── manifest_lulc.csv                 ← LULC 轉換記錄
│   ├── manifest_s2.csv                   ← Sentinel-2 轉換記錄
│   ├── manifest_prec.csv                 ← Precipitation 轉換記錄
│   ├── manifest_s1dem.csv                ← S1/DEM 轉換記錄
│   └── manifest_full.csv                 ← 合併後完整記錄（1142 筆）
│
├── KuroSiwo_COG_V8/                      ← COG 輸出根目錄
│   └── <event_id>/<layer_type>/<file>_cog.tif
│
└── KuroSiwo_STAC_V8_COG/                 ← 新版 STAC（指向 COG）
    ├── catalog.json
    ├── _unmatched_hrefs.txt              ← 未匹配的 href 清單
    └── <event>/<layer>/<item>.json
```

**原始資料路徑（未異動）：**

| 類型 | 路徑 |
|------|------|
| Precipitation | `/home/NAS/homes/gisele-10036/02.Course/26S_BigData/Imerg/7days_sum` |
| LULC (DW) | `/home/NAS/homes/chunen-10029/bigdata/final/DW` |
| Sentinel-2 | `/home/NAS/homes/chunen-10029/bigdata/final/S2_aoi_modify` |
| S1 / DEM | `/home/NAS/homes/chunen-10029/bigdata/final/kurosiwo_S1_DEM` |
| 原始 STAC | `/home/NAS/homes/chunen-10029/bigdata/final/KuroSiwo_STAC_V8` |

---

## 環境需求

```bash
# GDAL（必須）
gdal_translate --version   # 需要 >= 3.1（支援 -of COG）

# Python 套件（標準庫，不需額外安裝）
python3 --version   # >= 3.8
```

---

## A. convert_to_cog.py

將 GeoTIFF 批次轉換成 COG，產出 `manifest.csv` 追蹤每筆狀態。

### COG 固定設定

| 參數 | 值 |
|------|----|
| Format | COG |
| BLOCKSIZE | 256 |
| COMPRESS | DEFLATE |
| BIGTIFF | IF_SAFER |
| NUM_THREADS | ALL_CPUS |

### Resampling 規則

| Layer 類型 | Resampling | 原因 |
|-----------|-----------|------|
| LULC、flood_label | `NEAREST` | 類別型，不可插值 |
| S2、S1、DEM、Precipitation | `BILINEAR` | 連續型 |

### 用法

```bash
cd src/cog_pipeline

# 從 txt 清單（小批次測試）
python3 convert_to_cog.py \
    --list test_inputs.txt \
    --manifest manifest_test.csv

# 遞迴掃描整個資料夾
python3 convert_to_cog.py \
    --dir /home/NAS/homes/chunen-10029/bigdata/final/S2_aoi_modify \
    --manifest manifest_s2.csv

# Dry-run（只列計劃，不轉換）
python3 convert_to_cog.py --list test_inputs.txt --dry-run

# 強制覆蓋已存在的 COG
python3 convert_to_cog.py --list test_inputs.txt --force

# 限制前 N 筆（小批次測試）
python3 convert_to_cog.py --dir /path/to/dir --limit 5 --manifest manifest_test.csv
```

### manifest.csv 欄位說明

| 欄位 | 說明 |
|------|------|
| `src_path` | 原始 GeoTIFF 實際路徑 |
| `src_path_stac_compat` | STAC href 使用的別名路徑 |
| `dst_path` | COG 輸出路徑 |
| `layer_type` | 推斷的 layer 類型 |
| `event_id` | 推斷的 event ID |
| `resampling` | nearest 或 bilinear |
| `status` | ok / skip / missing / error |
| `message` | 成功/失敗原因 |

---

## B. rewrite_stac_to_cog.py

讀 `manifest_full.csv`，複製原始 STAC 到新目錄，並更新 asset href 為 COG 路徑。

### 用法

```bash
# Dry-run（確認計劃）
python3 rewrite_stac_to_cog.py \
    --manifest manifest_full.csv \
    --dry-run

# 正式執行
python3 rewrite_stac_to_cog.py \
    --manifest manifest_full.csv

# 指定路徑（可選）
python3 rewrite_stac_to_cog.py \
    --manifest manifest_full.csv \
    --src-stac /home/NAS/homes/chunen-10029/bigdata/final/KuroSiwo_STAC_V8 \
    --dst-stac KuroSiwo_STAC_V8_COG
```

---

## 完整執行流程（從頭開始）

```bash
cd src/cog_pipeline

# Step 1：生成測試清單
bash gen_test_inputs.sh

# Step 2：Dry-run 確認
python3 convert_to_cog.py --list test_inputs.txt --manifest manifest_test.csv --dry-run

# Step 3：小批次測試
python3 convert_to_cog.py --list test_inputs.txt --manifest manifest_test.csv

# Step 4：整批轉換（各類分開）
python3 convert_to_cog.py --dir /home/NAS/homes/chunen-10029/bigdata/final/kurosiwo_S1_DEM --manifest manifest_s1dem.csv
python3 convert_to_cog.py --dir /home/NAS/homes/chunen-10029/bigdata/final/DW              --manifest manifest_lulc.csv
python3 convert_to_cog.py --dir /home/NAS/homes/chunen-10029/bigdata/final/S2_aoi_modify   --manifest manifest_s2.csv
python3 convert_to_cog.py --dir /home/NAS/homes/gisele-10036/02.Course/26S_BigData/Imerg/7days_sum --manifest manifest_prec.csv

# Step 5：合併 manifest
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
print(f"合併完成：{len(rows)} 筆")
EOF

# Step 6：STAC rewrite
python3 rewrite_stac_to_cog.py --manifest manifest_full.csv

# Step 7：切換 WebGIS symlink
rm /home/gisele/webgis_v7_app/data
ln -s KuroSiwo_STAC_V8_COG \
      /home/gisele/webgis_v7_app/data
```

---

## WebGIS 啟動流程

### Server 端（up3090 上執行）

```bash
tmux kill-session -t webv7_8002 2>/dev/null
tmux kill-session -t titiler8003 2>/dev/null
tmux kill-session -t aoiapi 2>/dev/null

tmux new-session -d -s webv7_8002  'python3 -m http.server 8002 --bind 127.0.0.1 --directory /home/gisele/webgis_v7_app'
tmux new-session -d -s titiler8003 'conda run -n cogenv uvicorn titiler.application.main:app --host 127.0.0.1 --port 8003'
tmux new-session -d -s aoiapi      'cd /home/gisele/webgis_v7_app && conda run -n cogenv uvicorn aoi_analysis_api:app --host 127.0.0.1 --port 8004'

sleep 3
ss -ltnp | egrep '8002|8003|8004'
curl http://127.0.0.1:8004/health
```

### 本機端（開新終端機執行，保持開著）

```bash
# 關閉舊 tunnel
for p in 8080 8081 8082; do
  pid=$(lsof -ti tcp:$p)
  if [ -n "$pid" ]; then kill $pid; fi
done

# 開新 tunnel
ssh -N \
    -L 8080:127.0.0.1:8002 \
    -L 8081:127.0.0.1:8003 \
    -L 8082:127.0.0.1:8004 \
    gisele@up3090
```

### 打開瀏覽器

```
http://127.0.0.1:8080/index.html
```

| Port | 服務 |
|------|------|
| 8080 (→ 8002) | WebGIS 前端 |
| 8081 (→ 8003) | TiTiler |
| 8082 (→ 8004) | AOI Analysis API |

---

## 執行成果摘要（2026-05-21）

| 項目 | 數量 |
|------|------|
| 轉換成功的 COG | 1134 個 |
| 略過（已存在）| 8 個 |
| 更新的 STAC JSON | 252 個 |
| 更新的 asset href | 1007 個 |
| 未匹配的 href | 4 個（event 1111009 S1/DEM，詳見 `_unmatched_hrefs.txt`）|

---

## 已知問題

### 1. Event 1111009 的 4 個 S1/DEM 檔案未轉換

這 4 個檔案在新 STAC 中仍指向原始 GeoTIFF（仍可讀取，只是非 COG 格式）：

```
/home/chunen/nas/bigdata/final/S2_aoi_modify/1111009/1111009_1_20220607T061118-0000000000-0000000000.tif
/home/chunen/nas/bigdata/final/kurosiwo_S1_DEM/1111009/1111009_01_MS1_IVH_20220911.tif
/home/chunen/nas/bigdata/final/kurosiwo_S1_DEM/1111009/1111009_01_MS1_IVV_20220911.tif
/home/chunen/nas/bigdata/final/kurosiwo_S1_DEM/1111009/1111009_01_SL2_IVH_20220607.tif
```

補轉方式：

```bash
# 建立補轉清單
cat > fix_1111009.txt << 'EOF'
/home/NAS/homes/chunen-10029/bigdata/final/S2_aoi_modify/1111009/1111009_1_20220607T061118-0000000000-0000000000.tif
/home/NAS/homes/chunen-10029/bigdata/final/kurosiwo_S1_DEM/1111009/1111009_01_MS1_IVH_20220911.tif
/home/NAS/homes/chunen-10029/bigdata/final/kurosiwo_S1_DEM/1111009/1111009_01_MS1_IVV_20220911.tif
/home/NAS/homes/chunen-10029/bigdata/final/kurosiwo_S1_DEM/1111009/1111009_01_SL2_IVH_20220607.tif
EOF

python3 convert_to_cog.py --list fix_1111009.txt --manifest manifest_fix_1111009.csv
```

### 2. DW `_label.tif` 被分類為 `flood_label`

DW 目錄下的 `_label.tif` 因檔名含 `_label` 被分類為 `flood_label`，但 resampling 仍為 `nearest`（正確），不影響資料品質，只是輸出子目錄名稱為 `flood_label/` 而非 `lulc/`。

---

## 路徑別名對應

STAC 裡的 href 使用別名路徑，本腳本自動轉換：

| STAC href 前綴 | 實際路徑 |
|----------------|---------|
| `/home/chunen/nas` | `/home/NAS/homes/chunen-10029` |
| `/home/gisele/nas` | `/home/NAS/homes/gisele-10036` |
