#!/usr/bin/env python3
"""
convert_to_cog.py — GeoTIFF → Cloud Optimized GeoTIFF 批次轉換
===============================================================

【命令列用法】
  # 從 txt 清單（小批次測試）：
  python3 convert_to_cog.py --list test_inputs.txt --manifest manifest_test.csv

  # 從 csv 清單（需有 src_path 欄位）：
  python3 convert_to_cog.py --list test_inputs.csv --manifest manifest_test.csv

  # 遞迴掃描資料夾（整批）：
  python3 convert_to_cog.py --dir /home/NAS/homes/chunen-10029/bigdata/final \
      --manifest manifest_full.csv

  # Dry-run（只列計劃）：
  python3 convert_to_cog.py --list test_inputs.txt --dry-run

  # 限制前 N 筆（小批次）：
  python3 convert_to_cog.py --dir /path/to/dir --limit 5 --manifest manifest_test.csv

  # 強制重新轉換（覆蓋已存在 COG）：
  python3 convert_to_cog.py --list test_inputs.txt --force
"""

import argparse
import csv
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ─── 路徑常數 ─────────────────────────────────────────────────────────────────

COG_ROOT = Path("KuroSiwo_COG_V8")

COG_BLOCKSIZE   = 256
COG_COMPRESS    = "DEFLATE"
COG_BIGTIFF     = "IF_SAFER"
COG_NUM_THREADS = "ALL_CPUS"

# STAC href 別名 → 實際可讀路徑
PATH_ALIAS_MAP = [
    ("/home/chunen/nas",       "/home/NAS/homes/chunen-10029"),
    ("/home/gisele/nas",       "/home/NAS/homes/gisele-10036"),
    ("/home/chunen-10029/nas", "/home/NAS/homes/chunen-10029"),
]

# ─── Layer type 規則 ──────────────────────────────────────────────────────────
# 類別型 → nearest；連續型 → bilinear

# 先比對目錄關鍵字
DIR_RULES = [
    ("kurosiwo_events", "flood_label",   "nearest"),
    ("kurosiwo_S1_DEM", "s1_dem",        "bilinear"),
    ("DW",              "lulc",          "nearest"),
    ("S2_aoi_modify",   "s2",            "bilinear"),
    ("Imerg",           "precipitation", "bilinear"),
    ("IMERG",           "precipitation", "bilinear"),
    ("imerg",           "precipitation", "bilinear"),
]

# 再比對檔名關鍵字（優先）
FNAME_RULES = [
    ("_label",    "flood_label",   "nearest"),
    ("_lulc",     "lulc",         "nearest"),
    ("_MLU",      "lulc",         "nearest"),
    ("_mlu",      "lulc",         "nearest"),
    ("_DEM",      "dem",          "bilinear"),
    ("_dem",      "dem",          "bilinear"),
    ("_VV",       "s1_sar",       "bilinear"),
    ("_VH",       "s1_sar",       "bilinear"),
]

# ─── 路徑工具 ─────────────────────────────────────────────────────────────────

def normalize_path(p: str) -> str:
    """將 STAC 別名路徑轉為實際可讀路徑"""
    for alias, real in PATH_ALIAS_MAP:
        if p.startswith(alias + "/") or p == alias:
            return real + p[len(alias):]
    return p


def to_stac_compat(real_path: str) -> str:
    """將實際路徑轉回 STAC 可能使用的別名（供 rewrite_stac_to_cog.py 對比）"""
    for alias, real in PATH_ALIAS_MAP:
        if real_path.startswith(real + "/") or real_path == real:
            return alias + real_path[len(real):]
    return real_path


def infer_layer_info(src: Path) -> tuple[str, str, str]:
    """
    依路徑與檔名推斷 (layer_type, resampling, event_id)。
    event_id 嘗試從路徑片段取出（EM_ 前綴、純數字等）。
    """
    path_str = str(src)
    stem     = src.stem

    # 先比對檔名
    layer_type, resampling = "unknown", "bilinear"
    for kw, lt, rs in FNAME_RULES:
        if kw in stem:
            layer_type, resampling = lt, rs
            break

    # 再比對目錄
    if layer_type == "unknown":
        for kw, lt, rs in DIR_RULES:
            if kw in path_str:
                layer_type, resampling = lt, rs
                break

    # 推斷 event_id
    event_id = "unknown_event"
    for part in src.parts:
        if (part.startswith("EM_") or
            part.startswith("event") or
            part.startswith("Event") or
            (part.isdigit() and 2 <= len(part) <= 6)):
            event_id = part
            break

    return layer_type, resampling, event_id

# ─── 輸入蒐集 ─────────────────────────────────────────────────────────────────

def collect_from_txt(f: Path) -> list[Path]:
    paths = []
    with open(f, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            p = Path(normalize_path(line))
            if p.suffix.lower() in (".tif", ".tiff"):
                paths.append(p)
    return paths


def collect_from_csv(f: Path) -> list[Path]:
    paths = []
    with open(f, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            src = row.get("src_path", "").strip()
            if not src:
                continue
            p = Path(normalize_path(src))
            if p.suffix.lower() in (".tif", ".tiff"):
                paths.append(p)
    return paths


def collect_from_dir(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in (".tif", ".tiff")
    )

# ─── COG 轉換 ─────────────────────────────────────────────────────────────────

def convert_to_cog(src: Path, dst: Path, resampling: str) -> dict:
    """gdal_translate -of COG 轉換，回傳 {status, message}"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "gdal_translate",
        "-of", "COG",
        "-co", f"BLOCKSIZE={COG_BLOCKSIZE}",
        "-co", f"COMPRESS={COG_COMPRESS}",
        "-co", f"BIGTIFF={COG_BIGTIFF}",
        "-co", f"NUM_THREADS={COG_NUM_THREADS}",
        "-co", f"RESAMPLING={resampling.upper()}",
        str(src), str(dst),
    ]
    try:
        r = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        return {"status": "ok", "message": "gdal_translate COG 成功"}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": f"gdal_translate 失敗: {e.stderr.strip()[:300]}"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "timeout >600s"}
    except FileNotFoundError:
        return {"status": "error", "message": "找不到 gdal_translate，請安裝 gdal-bin"}

# ─── Manifest ─────────────────────────────────────────────────────────────────

FIELDS = [
    "src_path", "src_path_stac_compat", "dst_path",
    "layer_type", "event_id", "resampling",
    "blocksize", "compress", "status", "message", "converted_at",
]


def write_manifest(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

# ─── 主程式 ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="GeoTIFF → COG 批次轉換，產出 manifest.csv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--list", metavar="FILE",
                     help=".txt（每行一路徑）或 .csv（含 src_path 欄位）")
    grp.add_argument("--dir",  metavar="DIR",
                     help="遞迴掃描資料夾下所有 .tif/.tiff")
    parser.add_argument("--manifest", metavar="CSV", default="manifest.csv",
                        help="manifest 輸出路徑（預設：manifest.csv）")
    parser.add_argument("--cog-root", metavar="DIR", default=str(COG_ROOT),
                        help=f"COG 根目錄（預設：{COG_ROOT}）")
    parser.add_argument("--dry-run",  action="store_true",
                        help="只列計劃，不轉換")
    parser.add_argument("--force",    action="store_true",
                        help="強制覆蓋已存在的 COG")
    parser.add_argument("--limit",    type=int, default=0,
                        help="只處理前 N 筆（0=全部）")
    args = parser.parse_args()

    cog_root = Path(args.cog_root)

    # 蒐集輸入
    if args.list:
        lf = Path(args.list)
        src_files = collect_from_csv(lf) if lf.suffix.lower() == ".csv" else collect_from_txt(lf)
    else:
        src_files = collect_from_dir(Path(args.dir))

    if not src_files:
        print("未找到任何 .tif/.tiff 檔案，結束。")
        sys.exit(0)

    if args.limit > 0:
        src_files = src_files[:args.limit]

    total = len(src_files)
    print(f"共 {total} 個檔案  COG設定：BLOCKSIZE={COG_BLOCKSIZE} COMPRESS={COG_COMPRESS}")
    print("─" * 72)

    rows: list[dict] = []
    ok = skip = err = 0

    for idx, src in enumerate(src_files, 1):
        tag = f"[{idx}/{total}]"
        layer_type, resampling, event_id = infer_layer_info(src)
        dst = cog_root / event_id / layer_type / f"{src.stem}_cog.tif"
        stac_compat = to_stac_compat(str(src))

        base = dict(
            src_path=str(src),
            src_path_stac_compat=stac_compat,
            dst_path=str(dst),
            layer_type=layer_type,
            event_id=event_id,
            resampling=resampling,
            blocksize=COG_BLOCKSIZE,
            compress=COG_COMPRESS,
        )

        if args.dry_run:
            print(f"{tag} {src.name}  layer={layer_type} resampling={resampling}")
            print(f"       → {dst}")
            rows.append({**base, "status": "dry_run", "message": "", "converted_at": ""})
            continue

        if not src.exists():
            msg = "來源檔案不存在"
            print(f"{tag} ✘  {src.name}  [{msg}]")
            rows.append({**base, "status": "missing", "message": msg,
                         "converted_at": datetime.now().isoformat()})
            err += 1
            continue

        if dst.exists() and not args.force:
            msg = "COG 已存在，略過"
            print(f"{tag} –  {src.name}  [略過]")
            rows.append({**base, "status": "skip", "message": msg, "converted_at": ""})
            skip += 1
            continue

        print(f"{tag} ⟳  {src.name}  (layer={layer_type}, resampling={resampling})")
        result = convert_to_cog(src, dst, resampling)

        if result["status"] == "ok":
            print(f"       ✔  → {dst}")
            ok += 1
        else:
            print(f"       ✘  {result['message']}")
            err += 1

        rows.append({**base, "status": result["status"],
                     "message": result["message"],
                     "converted_at": datetime.now().isoformat()})

    # 寫出 manifest
    manifest_path = Path(args.manifest)
    write_manifest(manifest_path, rows)
    print("─" * 72)
    if args.dry_run:
        print(f"[DRY-RUN] {total} 個檔案，未轉換。manifest → {manifest_path}")
    else:
        print(f"完成：✔ {ok}  – 略過 {skip}  ✘ 錯誤 {err}")
        print(f"manifest → {manifest_path}")


if __name__ == "__main__":
    main()
