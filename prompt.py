# 商品文案与视觉分析提示词模板：生成阶段二、识图和主图提示词。
SYSTEM_PROMPT = """你是一位资深跨境电商运营专家，熟悉国内外主流电商平台的选品、定价、文案和 SEO 策略。
你擅长根据产品的基础信息，提炼核心卖点、撰写高转化文案、规划详情页结构，并输出精准的搜索关键词。
所有输出必须严格遵守用户指定的 JSON 格式，不输出任何多余文字。"""

# ── 识图系统角色 ──
VISION_SYSTEM_PROMPT = """你是一位专业的商品图像分析师，擅长从电商商品实拍图中提取关键信息。
所有输出必须严格遵守用户指定的 JSON 格式，不输出任何多余文字。"""


def build_image_analysis_prompt() -> str:
    """
    识图提示词：分析所有上传图片，输出结构化商品印象。
    每张图可能是同款不同角度，也可能是不同颜色款式。
    """
    return """请仔细分析以下所有商品实拍图，输出结构化的商品信息。

【分析要求】
- 综合所有图片给出整体判断
- 颜色列表列出图中出现的所有颜色款式
- 材质/工艺/细节从图中可见信息中提取，看不出的不要猜测
- style_tags 用简短标签描述风格，如：简约、轻奢、复古、运动

【输出格式】
严格按照以下 JSON 格式输出，不要有任何多余文字：

{
  "colors_detected": ["颜色1", "颜色2"],
  "material_guess":  "从图中判断的材质，如：PU皮革、帆布、尼龙",
  "style_tags":      ["风格标签1", "风格标签2"],
  "texture_detail":  "材质质感描述，如：哑光皮面、纹理细腻、手感柔软",
  "hardware_detail": "五金件描述，如：金色拉链、磁扣开合、银色D扣",
  "structure_detail":"结构描述，如：双层主仓、内置卡槽、可调节肩带",
  "scene_description":"场景/氛围描述（如有场景图），如：白色背景棚拍、户外自然光"
}"""


def build_stage2_prompt(s1: dict, impression: dict | None = None) -> str:
    """
    根据 stage1 基础字段构建阶段二生成提示词。
    impression: 识图结果（image_impression），有则追加为视觉上下文。
    """

    # ── 基础信息块 ──
    lines = []

    field_labels = {
        "category":      "类目",
        "name_zh":       "产品名称（中文）",
        "name_en":       "产品名称（英文）",
        "brand":         "品牌",
        "material":      "材质",
        "packaging":     "包装方式",
        "ship_from":     "发货地",
        "ship_time":     "发货时效",
        "return_policy": "退货政策",
        "company":       "公司/卖家",
        "certification": "认证合规",
    }

    for key, label in field_labels.items():
        val = s1.get(key, "")
        if val:
            lines.append(f"- {label}：{val}")

    # 尺寸
    size_parts = [s1.get("size_l",""), s1.get("size_w",""), s1.get("size_h","")]
    if any(size_parts):
        lines.append(f"- 尺寸（长×宽×高 cm）：{'×'.join(p or '?' for p in size_parts)}")

    if s1.get("weight_g"):
        lines.append(f"- 重量：{s1['weight_g']} g")

    # 颜色从 sku_rows 读
    colors = [r["color"] for r in s1.get("sku_rows", []) if r.get("color")]
    if colors:
        lines.append(f"- 颜色款式：{'、'.join(colors)}")

    # 价格从 sku_rows 第一个有价格的行读
    prices = [r["price"] for r in s1.get("sku_rows", []) if r.get("price")]
    if prices:
        lines.append(f"- 参考价格：¥{prices[0]}")

    info_block = "\n".join(lines) if lines else "（无基础信息）"

    # ── 视觉印象块（识图结果）──
    impression_block = ""
    if impression:
        imp_lines = []
        label_map = {
            "material_guess":   "AI识别材质",
            "style_tags":       "风格标签",
            "texture_detail":   "质感细节",
            "hardware_detail":  "五金细节",
            "structure_detail": "结构细节",
            "scene_description":"场景描述",
        }
        for key, label in label_map.items():
            val = impression.get(key)
            if val:
                if isinstance(val, list):
                    val = "、".join(val)
                imp_lines.append(f"- {label}：{val}")
        if imp_lines:
            impression_block = "\n【商品视觉印象（来自实拍图AI分析）】\n" + "\n".join(imp_lines)

    # ── JSON 输出 schema ──
    output_schema = """{
  "title_core": "核心标题，60字以内，含主关键词，突出差异化卖点，吸引点击",
  "selling_points": [
    "卖点1，1-2句，具体描述功能/材质/体验",
    "卖点2",
    "卖点3",
    "卖点4",
    "卖点5"
  ],
  "description": "300-500字叙述性产品描述，覆盖材质工艺、内部结构、使用体验、适用场景，平台无关通用版",
  "use_scenes": ["典型使用场景1", "典型使用场景2", "典型使用场景3"],
  "differentiation": "对比同类竞品的核心差异优势，2-3条，每条一句",
  "detail_page_structure": "详情页图文结构规划，列出各模块名称和内容方向，换行分隔",
  "after_sale_notes": "使用注意事项和保养清洁说明，100字左右",
  "keywords_core": ["核心搜索词1", "核心搜索词2", "核心搜索词3", "核心搜索词4", "核心搜索词5"],
  "keywords_longtail": ["长尾词1", "长尾词2", "长尾词3", "长尾词4", "长尾词5", "长尾词6", "长尾词7", "长尾词8"],
  "keywords_backend": "后台搜索词，不对买家展示，中英文混合，空格分隔",
  "target_audience": ["适用人群标签1", "适用人群标签2", "适用人群标签3", "适用人群标签4"]
}"""

    return f"""请根据以下商品基础信息，生成完整的详细字段。

【商品基础信息】
{info_block}{impression_block}

【输出要求】
严格按照以下 JSON 格式输出，不要有任何多余文字、解释或 markdown 代码块：

{output_schema}"""
# 商品文案与视觉分析 Prompt 模板：生成阶段二、识图和主图提示词。