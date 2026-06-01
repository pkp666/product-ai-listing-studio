# 拼多多平台专用提示词模板：生成平台文案、属性和标题等字段。
"""
拼多多平台适配 Prompt
────────────────────────────────────────────────────────────
平台规则要点：
  标题  ≤60字，关键词密度高，禁极限词（最/第一/唯一）禁特殊符号
  风格  口语化、性价比导向，避免过度轻奢表达
  属性  风格/闭合方式/适用场景/流行元素/内里材质 需单独填写
  关键词 以买家搜索习惯为准，长尾词优先
"""

# ── 平台专属属性选项（渲染 selectbox 用）──
PDD_ATTR_OPTIONS = {
    "风格":     ["简约", "韩版", "欧美", "复古", "英伦", "日系", "民族风", "潮流", "淑女", "通勤"],
    "闭合方式": ["拉链", "磁扣", "搭扣", "按扣", "无扣", "抽绳"],
    "适用场景": ["通勤", "休闲", "旅行", "购物", "宴会", "运动", "上学", "约会"],
    "流行元素": ["纯色", "印花", "撞色", "刺绣", "铆钉", "流苏", "格纹", "拼接"],
    "内里材质": ["涤纶", "棉布", "绒面", "PU", "尼龙", "无内里"],
}

# ── 拼多多平台禁用词（prompt 里提示模型规避）──
_PDD_FORBIDDEN = "最、第一、唯一、极致、顶级、国家级、世界级、%、&、*、#、@"


def build_pdd_prompt(s1: dict, s2: dict) -> str:
    """
    输入 stage1 基础字段 + stage2 通用字段，
    输出针对拼多多改写的平台专属内容。
    """

    # ── 从 stage1 提取关键信息 ──
    colors = [r["color"] for r in s1.get("sku_rows", []) if r.get("color")]
    prices = [r["price"] for r in s1.get("sku_rows", []) if r.get("price")]

    base_lines = []
    if s1.get("category"):   base_lines.append(f"- 类目：{s1['category']}")
    if s1.get("name_zh"):    base_lines.append(f"- 产品名称：{s1['name_zh']}")
    if s1.get("material"):   base_lines.append(f"- 材质：{s1['material']}")
    if colors:               base_lines.append(f"- 颜色款式：{'、'.join(colors)}")
    if prices:               base_lines.append(f"- 价格区间：¥{min(prices, key=lambda x: float(x) if x else 0)}")
    size_parts = [s1.get("size_l",""), s1.get("size_w",""), s1.get("size_h","")]
    if any(size_parts):
        base_lines.append(f"- 尺寸：{'×'.join(p or '?' for p in size_parts)} cm")
    if s1.get("weight_g"):   base_lines.append(f"- 重量：{s1['weight_g']} g")

    # ── 从 stage2 提取通用内容 ──
    s2_lines = []
    if s2.get("title_core"):
        s2_lines.append(f"- 通用标题：{s2['title_core']}")
    if s2.get("selling_points"):
        pts = "\n".join(f"  {i+1}. {p}" for i, p in enumerate(s2["selling_points"]))
        s2_lines.append(f"- 通用卖点：\n{pts}")
    if s2.get("description"):
        s2_lines.append(f"- 通用描述：{s2['description'][:300]}...")
    if s2.get("keywords_core"):
        s2_lines.append(f"- 核心关键词：{'、'.join(s2['keywords_core'])}")
    if s2.get("differentiation"):
        s2_lines.append(f"- 差异化优势：{s2['differentiation']}")

    base_block = "\n".join(base_lines) if base_lines else "（无基础信息）"
    s2_block   = "\n".join(s2_lines)   if s2_lines   else "（无通用字段）"

    # ── 属性选项提示 ──
    attr_hint = "\n".join(
        f"  {k}：从以下选一个 → {' / '.join(v)}"
        for k, v in PDD_ATTR_OPTIONS.items()
    )

    output_schema = """{
  "title": "拼多多标题，≤60字，关键词密度高，格式参考：[人群词]+[产品词]+[卖点]+[场景词]，禁止极限词和特殊符号",
  "selling_points": [
    "卖点1，口语化、具体、突出性价比或实用性，≤30字",
    "卖点2",
    "卖点3",
    "卖点4",
    "卖点5"
  ],
  "description": "详情页文字，200-400字，口语化，强调实用/性价比/品质，适合拼多多用户审美，避免过度轻奢表述",
  "keywords": ["搜索词1", "搜索词2", "搜索词3", "搜索词4", "搜索词5", "搜索词6", "搜索词7", "搜索词8"],
  "attrs": {
    "风格":     "从选项中选一个",
    "闭合方式": "从选项中选一个",
    "适用场景": "从选项中选一个",
    "流行元素": "从选项中选一个",
    "内里材质": "从选项中选一个"
  }
}"""

    return f"""你是拼多多资深运营专家，请将以下商品信息改写为适合拼多多平台的内容。

【商品基础信息】
{base_block}

【阶段二通用内容（参考改写，不要直接复制）】
{s2_block}

【拼多多平台规则】
1. 标题关键词密度要高，买家最常搜的词要靠前
2. 文案口语化，强调性价比、实用性、送礼自用
3. 禁止极限词：{_PDD_FORBIDDEN}
4. 禁止夸大宣传，卖点要具体可信
5. 避免过度轻奢/高端表述，换成"大牌同款""品质好货"等

【属性字段选项】（attrs 字段必须从以下选项中选择）
{attr_hint}

【输出要求】
严格按照以下 JSON 格式输出，不要有任何多余文字：

{output_schema}"""


# ══════════════════════════════════════════════
# 图片生成提示词（主图 + 详情图）
# ══════════════════════════════════════════════

# 主图生图引擎提示词系统角色
ZHUTU_SYSTEM_PROMPT = """你是亚马逊/拼多多电商视觉营销专家，擅长为商品生成高转化率的主图提示词。
分析用户提供的产品信息，生成5条用于AI绘图的英文提示词。
直接输出包含5个字符串的JSON数组，不要任何解释。"""


def _extract_base(s1: dict, s2: dict, imp: dict) -> dict:
    """从 s1/s2/impression 提取常用字段，供提示词构建复用。"""
    colors = [r["color"] for r in s1.get("sku_rows", []) if r.get("color")]
    prices = [r["price"] for r in s1.get("sku_rows", []) if r.get("price")]
    size_parts = [s1.get("size_l",""), s1.get("size_w",""), s1.get("size_h","")]
    size_str = "×".join(p for p in size_parts if p) if any(size_parts) else ""

    return {
        "name_zh":       s1.get("name_zh", ""),
        "name_en":       s1.get("name_en", ""),
        "category":      s1.get("category", ""),
        "material":      s1.get("material", ""),
        "colors":        colors,
        "price":         prices[0] if prices else "",
        "size":          size_str,
        "weight":        s1.get("weight_g", ""),
        "title":         s2.get("title_core", ""),
        "points":        s2.get("selling_points", []),
        "scenes":        s2.get("use_scenes", []),
        "diff":          s2.get("differentiation", ""),
        "style_tags":    imp.get("style_tags", []),
        "texture":       imp.get("texture_detail", ""),
        "hardware":      imp.get("hardware_detail", ""),
        "structure":     imp.get("structure_detail", ""),
    }


def build_zhutu_prompts_llm(s1: dict, s2: dict, impression: dict = None, wenan: str = "") -> str:
    """
    构建【主图】提示词生成的 LLM user prompt。
    由 call_llm_json 调用，返回5条英文生图提示词列表。
    wenan: 用户指定的海报文案关键词（留空则模型自动发挥）
    """
    imp = impression or {}
    b   = _extract_base(s1, s2, imp)

    wenan_hint = f"海报文案关键词（必须用）：{wenan}" if wenan else "海报文案关键词：留空，请根据产品自动选择最强卖点英文词"

    return f"""请根据以下产品信息，生成5条用于AI绘图的中文提示词。

【产品信息】
- 产品名（中文）：{b['name_zh']}
- 产品名（英文）：{b['name_en'] or '请自动翻译'}
- 类目：{b['category']}
- 材质：{b['material']}
- 颜色：{'、'.join(b['colors']) or '未指定'}
- 尺寸：{b['size']} cm
- 核心卖点：{'；'.join(b['points'][:3]) or '未提供'}
- 差异化优势：{b['diff'] or '未提供'}
- 材质质感：{b['texture'] or '未提供'}
- 风格标签：{'、'.join(b['style_tags']) or '未提供'}
- {wenan_hint}

【5张图要求】
第1张：纯白背景主图，产品居中85%，无阴影无杂物，8K超清
第2张：使用场景图，欧美现代家居或户外，真实人物互动，景深
第3张：氛围展示图，光影质感，产品摆拍，电影级打光，浅景深
第4张：带文字促销海报，大号3D粗体字，高对比度，活力配色
第5张：带文字功能展示图，科技感版式，描述质量的中文词醒目居中

【输出格式】
直接输出JSON数组，5个中文字符串，不要任何解释：
["prompt1", "prompt2", "prompt3", "prompt4", "prompt5"]"""


def build_xiangxitu_prompts(s1: dict, s2: dict, impression: dict = None) -> list[str]:
    """
    直接构建【详情图】12条中文生图提示词列表。
    不走 LLM，直接用字段拼接，速度快且字段对应准确。
    """
    imp = impression or {}
    b   = _extract_base(s1, s2, imp)

    name    = b["name_zh"] or "产品"
    mat     = b["material"] or "优质材料"
    colors  = "、".join(b["colors"]) if b["colors"] else "多色可选"
    size    = b["size"] or "标准尺寸"
    weight  = f"{b['weight']}g" if b["weight"] else ""
    texture = b["texture"] or f"{mat}，质感细腻"
    hw      = b["hardware"] or "精致五金件"
    struct  = b["structure"] or "多层收纳设计"
    scenes  = b["scenes"] if b["scenes"] else ["日常通勤", "休闲出行"]
    points  = b["points"] if b["points"] else ["品质优良", "设计精美", "实用耐用", "性价比高", "多场景适用"]

    # 补齐 points 到至少5条
    while len(points) < 5:
        points.append("品质保障")
    # 补齐 scenes 到至少2条
    while len(scenes) < 2:
        scenes.append("多场景适用")

    # 公共后缀：电商详情图风格
    suffix = "电商详情图风格，真实场景，高清质感，光线明亮，专业摄影"

    prompts = [
        # 1. 整体形象
        f"{name}整体形象展示，{colors}多色展示，简洁大气背景，产品主视觉突出，品牌感强，{suffix}",

        # 2. 材质细节
        f"{name}材质特写，{texture}，{mat}细节放大，纹理清晰可见，高端质感，微距摄影，{suffix}",

        # 3. 内部结构
        f"{name}内部结构展示，{struct}，各功能区域标注，收纳空间直观呈现，{suffix}",

        # 4. 尺寸对比
        f"{name}尺寸对比图，{size} cm{'，'+weight if weight else ''}，与A4纸/手机等参照物对比，尺寸标注清晰，{suffix}",

        # 5-9. 卖点（逐条）
        f"{name}核心卖点展示：{points[0]}，产品细节特写，文案标注醒目，{suffix}",
        f"{name}卖点展示：{points[1]}，使用细节，场景化呈现，{suffix}",
        f"{name}卖点展示：{points[2]}，功能演示，直观对比，{suffix}",
        f"{name}卖点展示：{points[3]}，{hw}五金件特写，工艺精细，{suffix}",
        f"{name}卖点展示：{points[4]}，品质细节，做工展示，{suffix}",

        # 10-11. 使用场景
        f"{name}使用场景：{scenes[0]}，真实人物使用，欧美风格环境，生活化氛围，{suffix}",
        f"{name}使用场景：{scenes[1]}，搭配穿搭展示，时尚感强，自然光线，{suffix}",

        # 12. 规格参数
        f"{name}规格参数展示，材质{mat}，尺寸{size} cm{'，重量'+weight if weight else ''}，颜色{colors}，数据可视化排版，科技感，{suffix}",
    ]

    return prompts


# ══════════════════════════════════════════════
# 表单1:1填写 Prompt（阶段三核心）
# ══════════════════════════════════════════════

FORM_FILL_SYSTEM_PROMPT = """你是拼多多资深上架专家，熟悉拼多多各类目的表单规范和审核要求。
根据商品信息，按照平台表单字段定义，输出完整的上架表单数据。
严格按照JSON格式输出，select类型字段只能填写给定选项中的值，不得自创。
不输出任何多余文字和解释。"""


def build_pdd_form_prompt(s1: dict, s2: dict, pdd: dict, field_map: dict) -> str:
    """
    构建表单1:1填写提示词。
    遍历 field_map 里所有非 upload/sku_axis 字段，
    告诉模型字段名、类型、可选项（select）、字数限制，
    让模型逐一填写，输出完整表单 JSON。
    """

    # ── 商品信息块 ──
    colors = [r["color"] for r in s1.get("sku_rows", []) if r.get("color")]
    prices = [r["price"] for r in s1.get("sku_rows", []) if r.get("price")]
    size_parts = [s1.get("size_l",""), s1.get("size_w",""), s1.get("size_h","")]

    info_lines = []
    if s1.get("category"):      info_lines.append(f"- 类目：{s1['category']}")
    if s1.get("name_zh"):       info_lines.append(f"- 产品名（中文）：{s1['name_zh']}")
    if s1.get("name_en"):       info_lines.append(f"- 产品名（英文）：{s1['name_en']}")
    if s1.get("brand"):         info_lines.append(f"- 品牌：{s1['brand']}")
    if s1.get("material"):      info_lines.append(f"- 材质：{s1['material']}")
    if any(size_parts):         info_lines.append(f"- 尺寸：{'×'.join(p or '?' for p in size_parts)} cm")
    if s1.get("weight_g"):      info_lines.append(f"- 重量：{s1['weight_g']} g")
    if s1.get("ship_from"):     info_lines.append(f"- 发货地：{s1['ship_from']}")
    if s1.get("ship_time"):     info_lines.append(f"- 发货时效：{s1['ship_time']}")
    if s1.get("return_policy"): info_lines.append(f"- 退货政策：{s1['return_policy']}")
    if s1.get("packaging"):     info_lines.append(f"- 包装方式：{s1['packaging']}")
    if colors:                  info_lines.append(f"- 颜色款式：{'、'.join(colors)}")
    if prices:                  info_lines.append(f"- 参考价格：¥{prices[0]}")

    if s2.get("title_core"):    info_lines.append(f"- 通用标题：{s2['title_core']}")
    if s2.get("description"):   info_lines.append(f"- 通用描述：{s2['description'][:400]}")
    if s2.get("selling_points"):
        pts = "；".join(s2["selling_points"][:5])
        info_lines.append(f"- 卖点：{pts}")
    if s2.get("keywords_core"): info_lines.append(f"- 核心关键词：{'、'.join(s2['keywords_core'])}")
    if s2.get("differentiation"): info_lines.append(f"- 差异化优势：{s2['differentiation']}")

    # pdd 已有的文案
    if pdd.get("title"):        info_lines.append(f"- 拼多多标题（参考）：{pdd['title']}")
    if pdd.get("description"):  info_lines.append(f"- 拼多多描述（参考）：{pdd['description'][:300]}")
    if pdd.get("keywords"):     info_lines.append(f"- 拼多多关键词（参考）：{'、'.join(pdd['keywords'])}")

    info_block = "\n".join(info_lines)

    # ── 字段定义块 ──
    field_lines = []
    output_schema = {}

    for section in field_map.get("sections", []):
        for field in section.get("fields", []):
            ftype    = field.get("type", "text")
            fname    = field["name"]
            required = field.get("required", False)
            options  = field.get("options", [])
            max_len  = field.get("max_length")
            note     = field.get("note", "")

            # 跳过不需要AI填的字段类型
            if ftype in ("upload", "sku_axis"):
                continue

            # 构建字段说明行
            req_mark = "【必填】" if required else "【选填】"
            line = f"- {fname} {req_mark} 类型:{ftype}"
            if options:
                line += f" 可选值:[{'|'.join(options)}]"
            if max_len:
                line += f" 最多{max_len}字"
            if note:
                line += f" 说明:{note}"
            field_lines.append(line)
            output_schema[fname] = f"根据类型和选项填写"

    field_block  = "\n".join(field_lines)
    schema_str   = "{\n" + "\n".join(f'  "{k}": ""' for k in output_schema) + "\n}"

    return f"""请根据以下商品信息，填写拼多多【{field_map.get('category','')}】类目的上架表单。

【商品信息】
{info_block}

【平台规则】
1. 标题≤60字，关键词密度高，禁止：最、第一、唯一、极致、顶级及特殊符号
2. select类型字段只能从给定选项中选择，不得自创
3. 文案口语化，贴近拼多多用户审美，强调性价比和实用性
4. 产地填发货地的省市，如"广东"

【需要填写的字段】
{field_block}

【输出格式】
严格按以下JSON结构输出所有字段，不要任何多余文字：
{schema_str}"""
# 拼多多平台专用 Prompt 模板：生成平台文案、属性和标题等字段。