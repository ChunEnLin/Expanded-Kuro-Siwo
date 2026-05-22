#!/usr/bin/env python3
"""
rewrite_stac_to_cog.py — 複製 STAC 並將 asset href 改為 COG 路徑
=================================================================

【流程】
  1. 讀取 manifest.csv（由 convert_to_cog.py 產出）
  2. 複製原始 STAC 到新目錄（不覆蓋原始）
  3. 逐一更新 JSON 中的 asset href（原始 GeoTIFF → COG 路徑）
  4. 輸出統計與 unmatched href 清單

【命令列用法】
  # 標準執行（讀預設路徑）：
  python3 rewrite_stac_to_cog.py --manifest manifest.csv

  # 指定所有路徑：
  python3 rewrite_stac_to_cog.py \
      --manifest /path/to/manifest.csv \
      --src-stac /home/NAS/homes/chunen-10029/bigdata/final/KuroSiwo_STAC_V8 \
      --dst-stac KuroSiwo_STAC_V8_COG

  # Dry-run（只列計劃）：
  python3 rewrite_stac_to_cog.py --manifest manifest.csv --dry-run

  # 強制重新複製整個 STAC（即使目標目錄已存在）：
  python3 rewrite_stac_to_cog.py --manifest manifest.csv --force-copy
"""

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

# ─── 預設路徑 ─────────────────────────────────────────────────────────────────

SRC_STAC_DEFAULT = "/home/NAS/homes/chunen-10029/bigdata/final/KuroSiwo_STAC_V8"
DST_STAC_DEFAULT = "KuroSiwo_STAC_V8_COG"

# NAS 路徑別名 → 實際路徑（與 convert_to_cog.py 一致）
PATH_ALIAS_MAP = [
    ("/home/chunen/nas",       "/home/NAS/homes/chunen-10029"),
    ("/home/gisele/nas",       "/home/NAS/homes/gisele-10036"),
    ("/home/chunen-10029/nas", "/home/NAS/homes/chunen-10029"),
]

# ─── 路徑工具 ─────────────────────────────────────────────────────────────────

def normalize_path(p: str) -> str:
    """將 STAC 別名路徑正規化為實際路徑"""
    for alias, real in PATH_ALIAS_MAP:
        if p.startswith(alias + "/") or p == alias:
            return real + p[len(alias):]
    return p


def all_variants(href: str) -> list[str]:
    """
    針對一個 href，產生所有可能的變體（原始、正規化、各別名），
    用於在 manifest 中查找對應。
    """
    variants = set()
    variants.add(href)
    normalized = normalize_path(href)
    variants.add(normalized)
    # 反向：若 href 是實際路徑，也產生別名
    for alias, real in PATH_ALIAS_MAP:
        if normalized.startswith(real + "/"):
            variants.add(alias + normalized[len(real):])
    return list(variants)

# ─── 讀取 Manifest ────────────────────────────────────────────────────────────

def load_manifest(manifest_path: Path) -> dict[str, str]:
    """
    讀取 manifest.csv，建立 href → dst_path 的查找表。
    key 包含 src_path 和 src_path_stac_compat 兩個欄位，
    以及各種正規化變體，確保最大相容性。
    回傳 {possible_href: dst_cog_path}
    """
    mapping: dict[str, str] = {}
    missing_dst: list[str]  = []

    with open(manifest_path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            status  = row.get("status", "")
            dst     = row.get("dst_path", "").strip()
            src     = row.get("src_path", "").strip()
            compat  = row.get("src_path_stac_compat", "").strip()

            # 接受 ok 或 skip（skip 代表 COG 已存在，也可用）
            if status not in ("ok", "skip"):
                continue
            if not dst:
                continue

            # 驗證 COG 目標是否存在
            if not Path(dst).exists():
                missing_dst.append(dst)
                continue

            # 建立所有可能的 href 變體 → dst 的對應
            for variant in all_variants(src):
                mapping[variant] = dst
            if compat:
                for variant in all_variants(compat):
                    mapping[variant] = dst

    if missing_dst:
        print(f"  [WARN] manifest 中有 {len(missing_dst)} 個 COG 目標不存在（已跳過）：")
        for p in missing_dst[:5]:
            print(f"         {p}")
        if len(missing_dst) > 5:
            print(f"         ... 共 {len(missing_dst)} 個")

    return mapping

# ─── 複製 STAC ────────────────────────────────────────────────────────────────

def copy_stac_dir(src_stac: Path, dst_stac: Path, force: bool = False):
    """
    複製整個 STAC 目錄到新目錄。
    若目標已存在且 --force-copy，先刪除再複製；否則跳過。
    """
    if dst_stac.exists():
        if force:
            print(f"  [INFO] 刪除已存在的目標目錄：{dst_stac}")
            shutil.rmtree(dst_stac)
        else:
            print(f"  [INFO] 目標目錄已存在，跳過複製（用 --force-copy 強制重複製）：{dst_stac}")
            return

    print(f"  [INFO] 複製 STAC：{src_stac} → {dst_stac}")
    shutil.copytree(src_stac, dst_stac)
    print(f"  [INFO] 複製完成")

# ─── 更新 JSON ────────────────────────────────────────────────────────────────

def rewrite_json_file(
    json_path: Path,
    mapping: dict[str, str],
    dry_run: bool = False,
) -> tuple[int, list[str]]:
    """
    更新單一 JSON 檔案中的 asset href。
    回傳 (changed_assets_count, unmatched_hrefs)
    只修改 assets[*].href，不改其他欄位。
    """
    try:
        with open(json_path, encoding="utf-8") as f:
            obj = json.load(f)
    except Exception as e:
        print(f"  [ERROR] 無法讀取 {json_path}: {e}")
        return 0, []

    assets = obj.get("assets", {})
    if not assets:
        return 0, []

    changed   = 0
    unmatched = []

    for key, asset in assets.items():
        href = asset.get("href", "")
        if not href:
            continue
        # 只處理 .tif / .tiff
        href_lower = href.lower()
        if not (href_lower.endswith(".tif") or href_lower.endswith(".tiff")):
            continue

        # 查找對應 COG 路徑
        new_href = None
        for variant in all_variants(href):
            if variant in mapping:
                new_href = mapping[variant]
                break

        if new_href is None:
            unmatched.append(href)
        else:
            if not dry_run:
                asset["href"] = new_href
            changed += 1

    if changed > 0 and not dry_run:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)

    return changed, unmatched

# ─── 主程式 ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="複製 STAC 並將 asset href 改為 COG 路徑",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--manifest",   required=True, metavar="CSV",
                        help="manifest.csv 路徑（由 convert_to_cog.py 產出）")
    parser.add_argument("--src-stac",   default=SRC_STAC_DEFAULT, metavar="DIR",
                        help=f"原始 STAC 目錄（預設：{SRC_STAC_DEFAULT}）")
    parser.add_argument("--dst-stac",   default=DST_STAC_DEFAULT, metavar="DIR",
                        help=f"新 STAC 輸出目錄（預設：{DST_STAC_DEFAULT}）")
    parser.add_argument("--dry-run",    action="store_true",
                        help="只列計劃，不修改任何 JSON")
    parser.add_argument("--force-copy", action="store_true",
                        help="若目標 STAC 目錄已存在，強制重新複製")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    src_stac      = Path(args.src_stac)
    dst_stac      = Path(args.dst_stac)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] rewrite_stac_to_cog.py 開始")
    print(f"  manifest : {manifest_path}")
    print(f"  src STAC : {src_stac}")
    print(f"  dst STAC : {dst_stac}")
    print(f"  dry-run  : {args.dry_run}")
    print()

    # 基本檢查
    if not manifest_path.exists():
        print(f"[ERROR] manifest 不存在：{manifest_path}")
        sys.exit(1)
    if not src_stac.exists():
        print(f"[ERROR] 原始 STAC 目錄不存在：{src_stac}")
        sys.exit(1)

    # 1. 讀取 manifest
    print("─" * 72)
    print("Step 1｜讀取 manifest...")
    mapping = load_manifest(manifest_path)
    print(f"  有效 COG 對應條目：{len(mapping)} 個 href 變體")

    if not mapping:
        print("[ERROR] manifest 中沒有有效的 ok 條目，請先完成 COG 轉換。")
        sys.exit(1)

    # 2. 複製 STAC 目錄
    print()
    print("─" * 72)
    print("Step 2｜複製 STAC 目錄...")
    if args.dry_run:
        print(f"  [DRY-RUN] 會複製 {src_stac} → {dst_stac}")
    else:
        copy_stac_dir(src_stac, dst_stac, force=args.force_copy)

    # 3. 遍歷新 STAC 的所有 JSON 並更新 href
    print()
    print("─" * 72)
    print("Step 3｜更新 asset href...")

    # dry-run 時掃描原始 STAC；否則掃描已複製的新 STAC
    scan_root = src_stac if args.dry_run else dst_stac

    json_files = sorted(scan_root.rglob("*.json"))
    print(f"  找到 {len(json_files)} 個 JSON 檔案")
    print()

    total_json_changed  = 0
    total_assets_changed = 0
    all_unmatched: list[str] = []

    for json_path in json_files:
        changed, unmatched = rewrite_json_file(json_path, mapping, dry_run=args.dry_run)
        if changed > 0:
            total_json_changed  += 1
            total_assets_changed += changed
            rel = json_path.relative_to(scan_root)
            action = "[DRY-RUN]" if args.dry_run else "已更新"
            print(f"  {action} {rel}  ({changed} 個 asset)")
        all_unmatched.extend(unmatched)

    # 去重 unmatched
    unmatched_unique = sorted(set(all_unmatched))

    # 4. 輸出統計
    print()
    print("─" * 72)
    print("Step 4｜統計結果")
    print(f"  更新的 JSON 數：{total_json_changed}")
    print(f"  更新的 asset 數：{total_assets_changed}")
    print(f"  未匹配的 href 數：{len(unmatched_unique)}")

    # 5. 輸出 unmatched 清單
    if unmatched_unique:
        unmatched_file = dst_stac / "_unmatched_hrefs.txt" if not args.dry_run else Path("_unmatched_hrefs_dryrun.txt")
        unmatched_file.parent.mkdir(parents=True, exist_ok=True)
        with open(unmatched_file, "w", encoding="utf-8") as f:
            f.write(f"# 未匹配的 href 清單\n")
            f.write(f"# 產生時間：{datetime.now().isoformat()}\n")
            f.write(f"# 這些 href 在 manifest 中找不到對應的 COG\n\n")
            for h in unmatched_unique:
                f.write(h + "\n")
        print(f"  未匹配清單已寫出：{unmatched_file}")
        print()
        print("  [未匹配 href 前 10 條]：")
        for h in unmatched_unique[:10]:
            print(f"    {h}")
        if len(unmatched_unique) > 10:
            print(f"    ... 共 {len(unmatched_unique)} 條，詳見 {unmatched_file}")

    print()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {'[DRY-RUN] ' if args.dry_run else ''}完成！")
    if not args.dry_run:
        print(f"  新 STAC 目錄：{dst_stac}")


if __name__ == "__main__":
    main()
