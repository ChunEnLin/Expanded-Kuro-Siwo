#!/usr/bin/env bash
# gen_test_inputs.sh — 自動生成小批次測試清單 test_inputs.txt
# 從四類各抓一個代表性檔案
#
# 用法：bash gen_test_inputs.sh

OUTPUT="test_inputs.txt"

echo "# KuroSiwo 小批次測試輸入清單" > "$OUTPUT"
echo "# 產生時間：$(date -Iseconds)" >> "$OUTPUT"
echo "" >> "$OUTPUT"

# 安全的 find_first 函式：找第一個符合條件的 .tif 檔案
# 用 -print -quit 讓 find 找到第一個就停止，不產生 SIGPIPE
find_first() {
    local dir="$1"
    local pattern="$2"
    find "$dir" -type f -name "$pattern" -print -quit 2>/dev/null
}

# ── 1. Precipitation (IMERG) ─────────────────────────────────────────────────
echo "# --- precipitation ---" >> "$OUTPUT"
PREC=$(find_first "/home/NAS/homes/gisele-10036/02.Course/26S_BigData/Imerg/7days_sum" "*.tif")
if [ -n "$PREC" ]; then
    echo "$PREC" >> "$OUTPUT"
    echo "  [precipitation] $PREC"
else
    echo "  [WARN] 找不到 precipitation 檔案，請手動填入 test_inputs.txt"
fi

# ── 2. LULC (Dynamic World) — 優先抓 *_label_vis.tif ────────────────────────
echo "" >> "$OUTPUT"
echo "# --- lulc ---" >> "$OUTPUT"
LULC=$(find_first "/home/NAS/homes/chunen-10029/bigdata/final/DW" "*_label_vis.tif")
# 若無 _label_vis，退而求其次抓任何 tif
if [ -z "$LULC" ]; then
    LULC=$(find_first "/home/NAS/homes/chunen-10029/bigdata/final/DW" "*.tif")
fi
if [ -n "$LULC" ]; then
    echo "$LULC" >> "$OUTPUT"
    echo "  [lulc] $LULC"
else
    echo "  [WARN] 找不到 LULC 檔案，請手動填入 test_inputs.txt"
fi

# ── 3. Sentinel-2 ────────────────────────────────────────────────────────────
echo "" >> "$OUTPUT"
echo "# --- s2 ---" >> "$OUTPUT"
S2=$(find_first "/home/NAS/homes/chunen-10029/bigdata/final/S2_aoi_modify" "*.tif")
if [ -n "$S2" ]; then
    echo "$S2" >> "$OUTPUT"
    echo "  [s2] $S2"
else
    echo "  [WARN] 找不到 S2 檔案，請手動填入 test_inputs.txt"
fi

# ── 4. Sentinel-1 / DEM ───────────────────────────────────────────────────────
echo "" >> "$OUTPUT"
echo "# --- s1_dem ---" >> "$OUTPUT"
S1=$(find_first "/home/NAS/homes/chunen-10029/bigdata/final/kurosiwo_S1_DEM" "*.tif")
if [ -n "$S1" ]; then
    echo "$S1" >> "$OUTPUT"
    echo "  [s1_dem] $S1"
else
    echo "  [WARN] 找不到 S1/DEM 檔案，請手動填入 test_inputs.txt"
fi

echo ""
echo "✔ 已產生：$OUTPUT"
echo ""
cat "$OUTPUT"
