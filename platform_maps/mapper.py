# 平台映射器：把商品数据按字段映射为上架表单结构，并生成补全提示。
"""
platform_maps/mapper.py
────────────────────────────────────────────────────────────
把 product dict 按字段定义 mapping 成平台上架数据。

用法：
    from platform_maps.mapper import build_platform_output, get_missing_fields
    output = build_platform_output(product, "pdd", "女包")
    missing = get_missing_fields(output, "pdd", "女包")
"""

import json
from pathlib import Path
from platform_maps.capture import load_field_map
from ziduan import DEFAULT_STOCK


# ── 从 product 里按 source 路径取值 ──────────────────────────

def _resolve(product: dict, source: str):
    """
    按 source 路径从 product 取值。
    支持：
      stage1.brand
      stage1.sku_rows[0].sku_code   → 取第一行
      stage1.sku_rows[].color       → 取所有行的该字段，返回列表
      stage3.pdd.title
      stage3.pdd.attrs.风格
    """
    if not source:
        return None

    parts = source.split(".")
    cur   = product

    for part in parts:
        if cur is None:
            return None

        # sku_rows[0] → 取指定index
        if "[0]" in part:
            key = part.replace("[0]", "")
            arr = cur.get(key, [])
            cur = arr[0] if arr else None

        # sku_rows[] → 取所有，返回列表（后续字段继续在每项里取）
        elif "[]" in part:
            key = part.replace("[]", "")
            cur = cur.get(key, [])
            # 标记为列表模式，后续parts在每项里取
            # 直接返回，由调用方处理剩余路径
            return cur  # 此处简化：直接返回列表，mapper里特殊处理

        elif isinstance(cur, dict):
            cur = cur.get(part)

        else:
            return None

    return cur


def _resolve_sku_field(product: dict, source: str) -> list:
    """
    专门处理 sku_rows[].xxx 路径，返回每个SKU行的该字段值列表。
    """
    if "sku_rows[]" not in source:
        return []

    field = source.split("sku_rows[].")[1]  # 如 "color"
    rows  = product["stage1"].get("sku_rows", [])

    result = []
    for row in rows:
        # 支持嵌套，如 price_single（不存在则fallback到price）
        val = row.get(field)
        if val is None and field == "price_single":
            val = row.get("price")
        if val is None and field == "stock":
            val = DEFAULT_STOCK
        result.append({
            "color":    row.get("color", ""),
            "sku_code": row.get("sku_code", ""),
            "value":    val,
        })
    return result


# ── 主 mapping 函数 ───────────────────────────────────────────

def build_platform_output(product: dict, platform: str, category: str) -> dict:
    """
    把 product 数据按字段定义 mapping 成平台上架dict。
    返回：
    {
        "platform":  "pdd",
        "category":  "女包",
        "fields":    {"商品标题": "...", "品牌": "...", ...},
        "sku_matrix": [{"color": "黑色", "库存": 100, "拼单价": 89, ...}],
        "missing":   ["面料材质", "闭合方式"],   # 必填但为空的字段
        "ai_fill_needed": ["颜地", "适用年龄"],  # 标记了ai_fill=true的字段
    }
    """
    field_map = load_field_map(platform, category)
    if not field_map:
        raise FileNotFoundError(f"未找到 {platform}/{category} 的字段定义，请先录入表单截图")

    output = {
        "platform":       platform,
        "category":       category,
        "fields":         {},
        "sku_matrix":     [],
        "missing":        [],
        "ai_fill_needed": [],
    }

    for section in field_map.get("sections", []):
        for field in section.get("fields", []):
            name     = field["name"]
            source   = field.get("source", "")
            required = field.get("required", False)
            ai_fill  = field.get("ai_fill", False)
            ftype    = field.get("type", "text")

            # SKU轴字段单独处理，不放进 fields
            if ftype == "sku_axis":
                continue

            # sku_rows[] 字段 → 放进 sku_matrix
            if "sku_rows[]" in source:
                _merge_sku_matrix(output["sku_matrix"], product, name, source)
                continue

            # 普通字段
            val = _resolve(product, source)

            # 特殊处理：ship_time 映射到拼多多选项
            if name == "手调发货时间":
                val = _map_ship_time(val)

            # 特殊处理：return_policy
            if name == "退货":
                val = "7天无理由退换" in str(val)

            output["fields"][name] = val

            # 记录缺失/需AI填
            if not val:
                if required:
                    output["missing"].append(name)
                if ai_fill:
                    output["ai_fill_needed"].append(name)

    return output


def _merge_sku_matrix(matrix: list, product: dict, field_name: str, source: str):
    """把 sku_rows[].xxx 的值合并进 sku_matrix 列表。"""
    rows    = product["stage1"].get("sku_rows", [])
    if not matrix:
        # 初始化
        for row in rows:
            matrix.append({
                "color":    row.get("color", ""),
                "sku_code": row.get("sku_code", ""),
            })

    field_key = source.split("sku_rows[].")[1]
    for i, row in enumerate(rows):
        if i >= len(matrix):
            break
        val = row.get(field_key)
        if val is None and field_key == "price_single":
            val = row.get("price")
        if val is None and field_key == "stock":
            val = str(DEFAULT_STOCK)
        matrix[i][field_name] = val


def _map_ship_time(val: str) -> str:
    """把我们的发货时效值映射到拼多多选项。"""
    mapping = {
        "当日发": "当日发货及晚点",
        "24h":   "24小时发货及晚点",
        "48h":   "48小时发货及晚点",
        "72h":   "48小时发货及晚点",  # 降级
    }
    return mapping.get(val, val or "48小时发货及晚点")


# ── 辅助：AI补填缺失字段 ──────────────────────────────────────

def build_ai_fill_prompt(product: dict, output: dict) -> str:
    """
    构建AI补填缺失字段的提示词。
    针对 missing + ai_fill_needed 字段。
    """
    need_fill = list(set(output["missing"] + output["ai_fill_needed"]))
    if not need_fill:
        return ""

    s1 = product["stage1"]
    s2 = product["stage2"]

    return f"""根据以下商品信息，补填拼多多上架表单中缺失的字段。

【商品信息】
- 类目：{s1.get('category','')}
- 产品名：{s1.get('name_zh','')}
- 材质：{s1.get('material','')}
- 发货地：{s1.get('ship_from','')}
- 卖点：{'；'.join(s2.get('selling_points',[])[:3])}

【需要补填的字段】
{chr(10).join(f'- {f}' for f in need_fill)}

【输出要求】
严格按以下JSON输出，字段值简短精确，符合平台规范：
{{{', '.join(f'"{f}": "填写值"' for f in need_fill)}}}"""


def ai_fill_missing(product: dict, output: dict) -> dict:
    """
    调用LLM补填缺失字段，直接更新 output["fields"]。
    返回更新后的 output。
    """
    from llm import call_llm_json
    from prompt import SYSTEM_PROMPT

    prompt = build_ai_fill_prompt(product, output)
    if not prompt:
        return output

    try:
        filled = call_llm_json(prompt, SYSTEM_PROMPT)
        for k, v in filled.items():
            if v:
                output["fields"][k] = v
                # 从 missing 和 ai_fill_needed 中移除
                output["missing"]        = [f for f in output["missing"]        if f != k]
                output["ai_fill_needed"] = [f for f in output["ai_fill_needed"] if f != k]
    except Exception as e:
        print(f"[mapper] AI补填失败: {e}")

    return output


def get_missing_fields(output: dict) -> list:
    """返回仍然缺失的必填字段列表。"""
    return output.get("missing", [])
# 平台映射器：把商品数据按字段映射为上架表单结构，并生成补全提示。