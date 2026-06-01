# 商品字段与 SKU 工具：定义数据结构、默认值和导出、矩阵逻辑。
import copy

# ── 颜色 → 英文 code（自动生成货号用）──
COLOR_MAP = {
    "黑色": "BLK", "白色": "WHT", "米白": "WHT", "棕色": "BRN",
    "深蓝": "NVY", "酒红": "WIN", "灰色": "GRY", "红色": "RED",
    "粉色": "PNK", "绿色": "GRN", "橙色": "ORG", "紫色": "PUR",
    "默认": "DEF",
}

# ── 类目选项 ──
CATEGORY_OPTIONS = [
    "女包", "男包", "钱包 / 卡包",
    "女装", "男装", "童装",
    "运动鞋", "休闲鞋", "高跟鞋",
    "手机配件", "电脑配件", "智能设备",
    "家居装饰", "厨房用品", "床上用品",
    "美妆护肤", "个人护理",
    "玩具", "母婴用品",
    "户外运动",
    "其他（自定义）",
]

# ── 默认库存 ──
DEFAULT_STOCK = 9999

# ── 完整数据结构 ──
EMPTY_PRODUCT = {
    # 阶段一：用户手动填写，平台无关
    "stage1": {
        "category":         "",   # 类目
        "name_zh":          "",   # 产品名称（中文）
        "name_en":          "",   # 产品名称（英文）
        "brand":            "",   # 品牌
        "material":         "",   # 材质
        "size_l":           "",   # 长(cm)
        "size_w":           "",   # 宽(cm)
        "size_h":           "",   # 高(cm)
        "weight_g":         "",   # 重量(g)
        "sku_prefix":       "",   # 货号前缀（选填，用于自动生成货号）
        "packaging":        "",   # 包装方式
        "ship_from":        "",   # 发货地
        "ship_time":        "",   # 发货时效
        "return_policy":    "",   # 退货政策
        "company":          "",   # 公司/卖家名
        "certification":    "",   # 认证合规
        "freight_template": "",   # 运费模板

        # 目标平台类目（与阶段三串联）
        "target_platform": "pdd",   # 目标平台 key
        "target_category": "",      # 目标类目全名

        # SKU 规格轴配置（最多两个轴）
        "sku_axis1_name": "颜色",   # 第一轴名称（用户可改）
        "sku_axis2_name": "",       # 第二轴名称（空=只有一轴）
        "sku_axis2_values": [],     # 第二轴的值列表，如["S","M","L"]

        # 拼单价差值设置（单买价 - 差值 = 拼单价）
        "pin_price_diff": "1",      # 默认差1元

        # SKU 行（第一轴每个值一行）
        "sku_rows": [
            # {
            #   "color":     "黑色",
            #   "sku_image": None,   # bytes，单张SKU预览图（平台上架用）
            #   "images":    [],     # list[bytes]，参考图集（多视角，AI生成用）
            #   "composite": "",     # 合成参考图本地路径
            #   "sku_code":  "",
            #   "price":     "",
            #   "stock":     "",
            # }
        ],
    },

    # 阶段二：AI 生成 + 人工校对，平台无关
    "stage2": {
        "image_impression":       {},   # 识图结果（build_stage2_prompt 追加上下文用）
        "title_core":             "",
        "selling_points":         [],
        "description":            "",
        "use_scenes":             [],
        "differentiation":        "",
        "detail_page_structure":  "",
        "after_sale_notes":       "",
        "keywords_core":          [],
        "keywords_longtail":      [],
        "keywords_backend":       "",
        "target_audience":        [],
    },

    # 阶段三：平台适配
    "stage3": {
        "platform":     "",
        "pdd_category": "",   # 选中的完整类目路径
        "pdd": {
            "generated":      False,   # 旧文案生成标记（保留兼容）
            "form_generated": False,   # 表单AI填写标记
            "filled_form":    {},      # AI填写的表单结果（1:1对应平台字段）
            "title":         "",
            "selling_points":[],
            "description":   "",
            "keywords":      [],
            "attrs": {
                "风格":     "",
                "闭合方式": "",
                "适用场景": "",
                "流行元素": "",
                "内里材质": "",
            },
            "field_values": {},
        },
    },

    # 阶段五：带货视频
    "stage5": {
        "script1":         "",
        "script2":         "",
        "script_status":   "idle",
        "selected_images": [],
        "task_id1":        "",
        "task_id2":        "",
        "video_status":    "idle",
        "path1":           "",
        "path2":           "",
        "merged_path":     "",
        # 精致带货视频（coze工作流）
        "premium_video_status": "idle",
        "premium_video_urls":   [],
        "premium_video_paths":  [],
    },

    # 阶段四：图片生成
    "stage4": {
        "ratio": "3:4",          # 图片比例，xiangxitu2 用
        # 主图：按颜色存，与 stage1.sku_rows 一一对应
        # sku_main_images[i] = {
        #   "color":        "黑色",
        #   "workflow":     "zhutu",        # 跑的是哪个工作流
        #   "status":       "idle",         # idle/running/done/error
        #   "image_paths":  [],             # 本地路径列表
        #   "image_urls":   [],             # 工作流返回的原始URL
        # }
        "sku_main_images": [],
        # 详情图：颜色无关，只跑一次
        "detail_images": {
            "workflow":    "",              # xiangxitu / xiangxitu2
            "status":      "idle",
            "image_paths": [],
            "image_urls":  [],
        },
    },
}

# ── stage2 AI字段类型声明（加减字段只改这里）──
OUTPUT_FIELDS = {
    "str": [
        "title_core",
        "description",
        "differentiation",
        "detail_page_structure",
        "after_sale_notes",
        "keywords_backend",
    ],
    "list": [
        "selling_points",
        "use_scenes",
        "keywords_core",
        "keywords_longtail",
        "target_audience",
    ],
}


def make_sku_row(axis1_val: str = "", sku_prefix: str = "") -> dict:
    """新建一个空 SKU 行。"""
    c_code   = COLOR_MAP.get(axis1_val, axis1_val[:3].upper() if axis1_val else "")
    sku_code = f"{sku_prefix}-{c_code}" if sku_prefix and c_code else ""
    return {
        "color":     axis1_val,
        "sku_image": None,   # 单张SKU预览图 bytes
        "images":    [],     # 参考图集 bytes列表
        "composite": "",     # 合成参考图本地路径
        "sku_code":  sku_code,
        "price":     "",
        "stock":     "",
    }


def build_sku_matrix(s1: dict) -> list[dict]:
    """
    根据 sku_rows（第一轴）× sku_axis2_values（第二轴）生成完整SKU矩阵。
    每项：{axis1, axis2, sku_code, price, pin_price, stock}
    """
    rows       = s1.get("sku_rows", [])
    axis2_vals = s1.get("sku_axis2_values", [])
    diff_str   = s1.get("pin_price_diff", "1")
    try:
        diff = float(diff_str)
    except Exception:
        diff = 1.0

    matrix = []
    if not axis2_vals:
        # 只有一个轴
        for row in rows:
            price_str = row.get("price", "")
            try:
                price     = float(price_str)
                pin_price = str(round(max(price - diff, 0), 2))
            except Exception:
                pin_price = price_str
            matrix.append({
                "axis1":     row.get("color", ""),
                "axis2":     "",
                "sku_code":  row.get("sku_code", ""),
                "price":     price_str,        # 单买价
                "pin_price": pin_price,        # 拼单价
                "stock":     row.get("stock", "") or str(DEFAULT_STOCK),
            })
    else:
        # 两个轴，笛卡尔积
        for row in rows:
            price_str = row.get("price", "")
            try:
                price     = float(price_str)
                pin_price = str(round(max(price - diff, 0), 2))
            except Exception:
                pin_price = price_str
            for a2 in axis2_vals:
                matrix.append({
                    "axis1":     row.get("color", ""),
                    "axis2":     a2,
                    "sku_code":  row.get("sku_code", ""),
                    "price":     price_str,
                    "pin_price": pin_price,
                    "stock":     row.get("stock", "") or str(DEFAULT_STOCK),
                })
    return matrix


def export_sku_rows(sku_rows: list) -> list:
    """导出时处理 SKU 行：去掉 images，stock 补默认值。"""
    result = []
    for row in sku_rows:
        result.append({
            "color":     row["color"],
            "sku_code":  row["sku_code"],
            "price":     row["price"],
            "stock":     int(row["stock"]) if row["stock"] else DEFAULT_STOCK,
            "composite": row.get("composite", ""),  # 保留合成图路径
        })
    return result


def empty_product() -> dict:
    """返回 EMPTY_PRODUCT 的深拷贝。"""
    return copy.deepcopy(EMPTY_PRODUCT)

# ── stage3 拼多多字段类型声明 ──
PDD_OUTPUT_FIELDS = {
    "str":  ["title", "description"],
    "list": ["selling_points", "keywords"],
}


def export_product(product: dict) -> str:
    """
    完整序列化 product 为 JSON 字符串。
    处理不可序列化字段：
    - stage1.sku_rows[].images（bytes）→ 记录张数，不存内容
    - stage4.sku_main_images[].status=running → 重置为 idle
    """
    import json

    p = copy.deepcopy(product)

    # stage1: sku_rows 去掉 images bytes，保留张数
    for row in p["stage1"]["sku_rows"]:
        image_count = len(row.get("images", []))
        row["images"] = []               # bytes 不序列化
        row["_image_count"] = image_count  # 记录张数，加载时提示用户重传

    # stage2: 去掉 image_impression（识图结果，重新上图会重新识）
    p["stage2"].pop("image_impression", None)

    # stage4: running 状态重置，error 信息保留
    for item in p["stage4"].get("sku_main_images", []):
        if item.get("status") == "running":
            item["status"] = "idle"
    detail = p["stage4"].get("detail_images", {})
    if detail.get("status") == "running":
        detail["status"] = "idle"

    return json.dumps(p, ensure_ascii=False, indent=2)


def load_product(json_str: str) -> dict:
    """
    从 JSON 字符串恢复 product。
    - 用 EMPTY_PRODUCT 作为基础，递归合并加载数据（缺字段自动补默认值）
    - sku_rows 恢复 images=[]（需用户重新上传）
    - stage4 image_paths 校验本地文件是否存在，不存在则重置 status
    返回合并后的 product dict，失败时 raise ValueError。
    """
    import json
    from pathlib import Path

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 格式错误: {e}")

    # 以 EMPTY_PRODUCT 为基础深拷贝，再逐层覆盖
    product = copy.deepcopy(EMPTY_PRODUCT)

    def merge(base: dict, loaded: dict):
        """loaded 里有的字段覆盖 base，base 有但 loaded 没有的保留默认值。"""
        for k, v in loaded.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                merge(base[k], v)
            else:
                base[k] = v

    merge(product, data)

    # ── stage1: sku_rows 补 images 字段 ──
    for row in product["stage1"]["sku_rows"]:
        row["images"] = []   # bytes 无法从 JSON 恢复，重置为空
        row.pop("_image_count", None)   # 清掉记录字段

    # ── stage2: 补 image_impression（加载后为空，需重新识图）──
    product["stage2"]["image_impression"] = {}

    # ── stage4: 校验 image_paths 本地文件是否存在 ──
    for item in product["stage4"].get("sku_main_images", []):
        if item.get("image_paths"):
            all_exist = all(Path(p).exists() for p in item["image_paths"])
            if not all_exist:
                item["status"]      = "idle"
                item["image_paths"] = []
                item["image_urls"]  = []

    detail = product["stage4"].get("detail_images", {})
    if detail.get("image_paths"):
        all_exist = all(Path(p).exists() for p in detail["image_paths"])
        if not all_exist:
            detail["status"]      = "idle"
            detail["image_paths"] = []
            detail["image_urls"]  = []

    return product
# 商品字段与 SKU 工具：定义数据结构、默认值和导出/矩阵逻辑。