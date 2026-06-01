# 表单截图识别工具：从平台页面截图中提取字段定义并落盘。
"""
platform_maps/capture.py
────────────────────────────────────────────────────────────
识图提取平台表单字段，保存为 platform_maps/{platform}/{category}.json

用法：
    from platform_maps.capture import capture_fields_from_image
    result = capture_fields_from_image(img_bytes, "pdd", "女包")
"""

import json
from pathlib import Path

# 字段定义存储根目录
MAPS_DIR = Path(__file__).parent


CAPTURE_SYSTEM_PROMPT = """你是电商平台表单分析专家。
分析用户上传的电商平台发布商品表单截图，提取所有可见字段。
严格按照指定JSON格式输出，不输出任何多余文字。"""


def build_capture_prompt(platform: str, category: str) -> str:
    return f"""请分析这张【{platform}】平台发布【{category}】商品的表单截图。

提取所有可见的表单字段，输出以下JSON格式：

{{
  "platform": "{platform}",
  "category": "{category}",
  "sections": [
    {{
      "name": "区域名称（如：基本信息/规格与库存/服务与承诺）",
      "fields": [
        {{
          "name": "字段名称",
          "type": "text/select/upload/richtext/number/radio/checkbox/sku_axis",
          "required": true或false,
          "max_length": null或数字,
          "note": "字段说明或填写要求（从页面提示文字提取）",
          "options": [],
          "source": "",
          "ai_fill": false
        }}
      ]
    }}
  ]
}}

字段类型说明：
- text: 文本输入框
- select: 下拉选择
- upload: 图片/视频上传
- richtext: 富文本编辑器
- number: 数字输入
- radio: 单选
- checkbox: 多选
- sku_axis: 规格轴（颜色/尺寸等）

注意：
- required为true的用橙色或红色*标注的字段
- source和ai_fill字段留空，后续系统自动填充
- 只提取字段信息，不描述页面布局"""


def capture_fields_from_image(
    img_bytes: bytes,
    platform: str,
    category: str,
    filename: str = "screenshot.png",
) -> dict:
    """
    识图提取平台表单字段。
    返回提取的字段定义dict，同时保存到本地JSON文件。
    失败时 raise Exception。
    """
    from llm import call_llm_vision_json

    prompt = build_capture_prompt(platform, category)
    data = call_llm_vision_json(
        user_prompt=prompt,
        images=[img_bytes],
        system_prompt=CAPTURE_SYSTEM_PROMPT,
        filenames=[filename],
    )

    # 自动补 captured_at
    from datetime import date
    data["captured_at"] = str(date.today())

    # 保存到本地
    save_path = MAPS_DIR / platform / f"{_category_to_filename(category)}.json"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return data


def _category_to_filename(category: str) -> str:
    """类目全路径 → 安全文件名，如：箱包皮具/女包/男包 > 女包 > 手提包 → 箱包皮具_女包_男包__女包__手提包"""
    return category.replace("/", "_").replace(" > ", "__").replace(" ", "")


def load_field_map(platform: str, category: str) -> dict | None:
    """
    读取已保存的字段定义。
    不存在返回 None。
    """
    path = MAPS_DIR / platform / f"{_category_to_filename(category)}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_available_maps() -> dict:
    """
    列出所有已录入的平台×类目组合。
    返回 {"pdd": ["箱包皮具/女包/男包 > 女包 > 手提包", ...]}
    读取JSON内的 category 字段作为显示名。
    """
    result = {}
    for platform_dir in MAPS_DIR.iterdir():
        if not platform_dir.is_dir() or platform_dir.name.startswith("_"):
            continue
        categories = []
        for f in platform_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                categories.append(data.get("category", f.stem))
            except Exception:
                categories.append(f.stem)
        if categories:
            result[platform_dir.name] = categories
    return result
# 表单截图识别工具：从平台页面截图中提取字段定义并落盘。