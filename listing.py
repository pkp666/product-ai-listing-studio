# 商品与上架数据持久化：负责保存、读取和导出本地商品与平台表单。
"""
listing.py — 商品存档 + 平台上架数据管理

商品存档：output/products/product_{name}_{ts}.json  （stage1+stage2）
上架存档：output/listings/{platform}_{category}_{ts}.json （stage3数据）
"""
import json
from pathlib import Path
from datetime import datetime

PRODUCTS_DIR = Path("./output/products")
LISTINGS_DIR = Path("./output/listings")
PRODUCTS_DIR.mkdir(parents=True, exist_ok=True)
LISTINGS_DIR.mkdir(parents=True, exist_ok=True)


# ── 商品存档 ──────────────────────────────────────────────────

def save_product(product: dict) -> str:
    """保存 stage1+stage2 为商品存档，返回文件路径。"""
    from ziduan import export_sku_rows
    name = product["stage1"].get("name_zh", "未命名").replace("/", "_")
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = PRODUCTS_DIR / f"product_{name}_{ts}.json"
    data = {
        "saved_at": str(datetime.now()),
        "stage1":   {**product["stage1"],
                     "sku_rows": export_sku_rows(product["stage1"]["sku_rows"])},
        "stage2":   {k: v for k, v in product["stage2"].items()
                     if k != "image_impression"},
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def list_products() -> list[dict]:
    """列出所有商品存档，返回 [{name, path, saved_at}]。"""
    result = []
    for f in sorted(PRODUCTS_DIR.glob("product_*.json"), reverse=True):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            result.append({
                "name":     d.get("stage1", {}).get("name_zh", f.stem),
                "path":     str(f),
                "saved_at": d.get("saved_at", ""),
            })
        except Exception:
            pass
    return result


def load_product_base(path: str) -> dict:
    """加载商品存档，返回含 stage1+stage2 的 dict。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    # 补齐 images/composite 字段（导出时丢失，重置为空）
    for row in data.get("stage1", {}).get("sku_rows", []):
        row["images"]    = []
        row["sku_image"] = None
        row.pop("_image_count", None)
    data["stage2"]["image_impression"] = {}
    return data


# ── 平台上架存档 ──────────────────────────────────────────────

def save_listing(product: dict, s3: dict) -> str:
    """保存平台上架数据，返回文件路径。"""
    from ziduan import export_sku_rows, build_sku_matrix
    platform = s3.get("platform", "unknown")
    category = s3.get("pdd_category", "未知类目").replace("/", "_").replace(" > ", "_").replace(" ", "")
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LISTINGS_DIR / f"{platform}_{category}_{ts}.json"
    data = {
        "saved_at":    str(datetime.now()),
        "product_name": product["stage1"].get("name_zh", ""),
        "platform":    platform,
        "category":    s3.get("pdd_category", ""),
        "filled_form": s3.get("pdd", {}).get("filled_form", {}),
        "sku_matrix":  s3.get("pdd", {}).get("filled_form", {}).get("sku_matrix", []),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def list_listings(platform: str = "") -> list[dict]:
    """列出上架存档，可按平台筛选。"""
    result = []
    pattern = f"{platform}_*.json" if platform else "*.json"
    for f in sorted(LISTINGS_DIR.glob(pattern), reverse=True):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            result.append({
                "name":     d.get("product_name", ""),
                "platform": d.get("platform", ""),
                "category": d.get("category", ""),
                "path":     str(f),
                "saved_at": d.get("saved_at", ""),
            })
        except Exception:
            pass
    return result


def load_listing(path: str) -> dict:
    """加载上架存档。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))