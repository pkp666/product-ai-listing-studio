# 通用 Coze 工作流驱动：按配置上传素材、触发工作流并保存返回结果。
"""
扣子工作流调用模块
────────────────────────────────────────────────────────────
函数模式（被 app.py 调用）：
    from coze_workflow import run_workflow
    paths = run_workflow("zhutu", img_bytes, filename, product_name, save_dir)

    # 视频工作流（返回本地视频路径）：
    result = run_workflow("shipintu", img_bytes, filename, product_name, save_dir,
                          extra_params={"maidian": "产品卖点", "name": "慧慧"})

脚本模式（本地测试）：
    python coze_workflow.py zhutu
    python coze_workflow.py xiangxitu
    python coze_workflow.py xiangxitu2
    python coze_workflow.py shipintu
"""

import sys
import json
import os
import re
import requests
from pathlib import Path
from datetime import datetime

# ══════════════════════════════════════════════
# 配置（全部硬编码）
# ══════════════════════════════════════════════

COZE_TOKEN       = os.getenv("COZE_TOKEN", "")
IMAGE_RELAY_URL  = os.getenv("PT_IMAGE_RELAY_URL", "")
LOCAL_IMAGE_PATH = r"D:\download\DOWN\微信图片_20260427221917_947_63.jpg"
DEFAULT_SAVE_DIR = "./output/images"
DEFAULT_VIDEO_DIR = "./output/videos"   # 视频保存根目录

# 工作流定义
WORKFLOWS = {
    "zhutu": {
        "workflow_id": os.getenv("COZE_WORKFLOW_ZHUTU_ID", ""),
        "fixed_params": {
            "chajian":  "即梦",
            "mihe_key": os.getenv("COZE_MIHE_KEY", ""),
        },
        "desc":   "主图工作流",
        "output": "image",   # 输出类型
    },
    "xiangxitu": {
        "workflow_id": os.getenv("COZE_WORKFLOW_XIANGXITU_ID", ""),
        "fixed_params": {
            "mihe_key": os.getenv("COZE_MIHE_KEY", ""),
        },
        "desc":   "详情图工作流",
        "output": "image",
    },
    "xiangxitu2": {
        "workflow_id": os.getenv("COZE_WORKFLOW_XIANGXITU2_ID", ""),
        "fixed_params": {},          # ratio 由调用方传入
        "desc":   "详情图工作流2",
        "output": "image",
    },
    # ── 新增：视频工作流 ──────────────────────────
    "shipintu": {
        "workflow_id": os.getenv("COZE_WORKFLOW_VIDEO_ID", ""),
        "fixed_params": {
            "key":  os.getenv("COZE_MIHE_KEY", ""),
            "name": "慧慧",         # 默认主播名，可被 extra_params 覆盖
        },
        "desc":   "视频工作流",
        "output": "video",          # 输出类型：视频
    },
}

WORKFLOW_LABELS = {
    "zhutu":      "主图（即梦）",
    "xiangxitu":  "详情图",
    "xiangxitu2": "详情图2（带比例）",
    "shipintu":   "视频图",
}


# ══════════════════════════════════════════════
# 内部工具
# ══════════════════════════════════════════════

def _upload_to_relay(image_bytes: bytes, filename: str = "image.png") -> str:
    """上传图片到中转服务器，返回 URL。"""
    ext  = Path(filename).suffix.lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(ext, "image/png")
    resp = requests.post(
        IMAGE_RELAY_URL,
        files={"image": (filename, image_bytes, mime)},
        headers={"ngrok-skip-browser-warning": "true"},
        timeout=60,
    )
    data = resp.json()
    url  = data.get("url") or data["data"]["url"]
    if not url.startswith("http"):
        url = "http://" + url
    return url


def _extract_urls(content: str, output_type: str = "image") -> list[str]:
    """
    从工作流返回内容中提取所有媒体 URL。
    output_type: "image" 只提取图片，"video" 提取视频（mp4/mov 等）。
    """
    IMAGE_EXTS = r'png|jpg|jpeg|webp|gif'
    VIDEO_EXTS = r'mp4|mov|avi|mkv|webm|flv'

    # 先尝试 JSON 解析
    try:
        obj = json.loads(content)
        urls = []
        def collect(v):
            if isinstance(v, str) and v.startswith("http"):
                urls.append(v)
            elif isinstance(v, list):
                for item in v: collect(item)
            elif isinstance(v, dict):
                for val in v.values(): collect(val)
        collect(obj)
        if urls:
            if output_type == "video":
                # 优先返回视频链接；若没有则返回全部（部分工作流URL无扩展名）
                video_urls = [u for u in urls if re.search(rf'\.({VIDEO_EXTS})', u, re.I)]
                return video_urls if video_urls else urls
            return urls
    except (json.JSONDecodeError, TypeError):
        pass

    # 正则兜底
    if output_type == "video":
        exts = VIDEO_EXTS
    else:
        exts = IMAGE_EXTS
    urls = re.findall(
        rf'https?://[^\s"\'>,]+\.(?:{exts})(?:[?#][^\s"\'>,]*)?',
        content, re.IGNORECASE
    )
    if not urls:
        # 最宽泛兜底：捕获所有 http URL（视频URL可能无扩展名）
        urls = re.findall(r'https?://[^\s"\'>,]+', content)
    return urls


def _download_file(url: str, save_path: Path) -> str:
    """下载单个文件到 save_path，返回本地绝对路径字符串。"""
    r = requests.get(url, stream=True, timeout=300)
    r.raise_for_status()
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    return str(save_path.resolve())


def _stream_workflow(workflow_id: str, parameters: dict) -> list[str]:
    """
    调用扣子流式工作流，返回所有媒体 URL 列表（原始内容字符串列表）。
    失败时 raise Exception。
    """
    headers = {
        "Authorization": f"Bearer {COZE_TOKEN}",
        "Content-Type":  "application/json",
    }
    payload = {"workflow_id": workflow_id, "parameters": parameters}

    resp = requests.post(
        "https://api.coze.cn/v1/workflow/stream_run",
        headers=headers,
        json=payload,
        stream=True,
        timeout=300,
    )
    if resp.status_code != 200:
        raise Exception(f"HTTP {resp.status_code}: {resp.text[:300]}")

    current_event = None
    current_data  = None
    raw_contents: list[str] = []   # 收集所有 node_is_finish 的 content

    for raw_line in resp.iter_lines():
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line

        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            current_data = line[len("data:"):].strip()
        elif line == "":
            if not current_event or not current_data:
                current_event = current_data = None
                continue

            event_type, data_str = current_event, current_data
            current_event = current_data = None

            if data_str == "{}":
                continue

            try:
                obj = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            if event_type == "Message":
                content        = obj.get("content", "")
                node_is_finish = obj.get("node_is_finish", False)
                if node_is_finish and content:
                    raw_contents.append(content)

            elif event_type == "Error":
                raise Exception(f"工作流错误: {obj.get('error_message')}")

    return raw_contents


# ══════════════════════════════════════════════
# 公开接口（被 app.py 调用）
# ══════════════════════════════════════════════

def run_workflow(
    workflow_name: str,
    image_bytes:   bytes,
    filename:      str   = "image.png",
    product_name:  str   = "",
    save_dir:      str   = DEFAULT_SAVE_DIR,
    extra_params:  dict  = None,
    video_dir:     str   = DEFAULT_VIDEO_DIR,
) -> dict:
    """
    上传图片 → 调用扣子工作流 → 下载结果文件到本地。

    图片工作流返回：
    {
        "workflow":    "zhutu",
        "output_type": "image",
        "image_urls":  ["http://...", ...],
        "image_paths": ["/abs/path/...", ...],
    }

    视频工作流返回：
    {
        "workflow":    "shipintu",
        "output_type": "video",
        "video_urls":  ["http://...", ...],
        "video_paths": ["/abs/path/...", ...],
    }

    失败时 raise Exception。
    """
    if workflow_name not in WORKFLOWS:
        raise ValueError(f"未知工作流: {workflow_name}，可选: {list(WORKFLOWS.keys())}")

    config      = WORKFLOWS[workflow_name]
    output_type = config.get("output", "image")

    # 1. 上传图片到中转
    img_url = _upload_to_relay(image_bytes, filename)

    # 2. 组装参数
    params = dict(config["fixed_params"])
    params["img"]   = img_url
    params["image"] = img_url
    if product_name:
        params["chanpinming"] = product_name
    if extra_params:
        params.update(extra_params)

    # 3. 调用工作流，拿到所有原始 content
    raw_contents = _stream_workflow(config["workflow_id"], params)
    if not raw_contents:
        raise Exception("工作流未返回任何内容")

    # 4. 从所有 content 中提取 URL
    all_urls: list[str] = []
    for content in raw_contents:
        urls = _extract_urls(content, output_type)
        all_urls.extend(urls)

    if not all_urls:
        raise Exception(f"工作流未返回任何{'视频' if output_type == 'video' else '图片'} URL")

    # 5. 下载到本地
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if output_type == "video":
        save_root = Path(video_dir) / workflow_name / timestamp
        file_paths = []
        for i, url in enumerate(all_urls):
            # 尽量保留原始扩展名，默认 .mp4
            clean_url = url.split("?")[0].split("#")[0]
            ext = Path(clean_url).suffix or ".mp4"
            if ext.lower() not in (".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"):
                ext = ".mp4"
            path = save_root / f"{workflow_name}_{i+1:02d}{ext}"
            local_path = _download_file(url, path)
            file_paths.append(local_path)
        return {
            "workflow":    workflow_name,
            "output_type": "video",
            "video_urls":  all_urls,
            "video_paths": file_paths,
        }

    else:
        save_root  = Path(save_dir) / workflow_name / timestamp
        file_paths = []
        for i, url in enumerate(all_urls):
            clean_url = url.split("?")[0].split("#")[0]
            ext = Path(clean_url).suffix or ".png"
            path = save_root / f"{workflow_name}_{i+1:02d}{ext}"
            local_path = _download_file(url, path)
            file_paths.append(local_path)
        return {
            "workflow":    workflow_name,
            "output_type": "image",
            "image_urls":  all_urls,
            "image_paths": file_paths,
        }


# ══════════════════════════════════════════════
# 脚本模式（本地测试）
# ══════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in WORKFLOWS:
        available = " / ".join(WORKFLOWS.keys())
        print(f"用法: python coze_workflow.py [{available}]")
        sys.exit(1)

    wf_name = sys.argv[1]
    print(f"🔹 工作流: {WORKFLOWS[wf_name]['desc']}")
    print("🔹 读取本地图片...")

    with open(LOCAL_IMAGE_PATH, "rb") as f:
        img_bytes = f.read()

    # 各工作流的测试额外参数
    extra_map = {
        "xiangxitu2": {"ratio": "3:4"},
        "shipintu":   {"maidian": "牛仔布拼接PU皮革设计，细腻牛仔纹理叠加光滑哑光皮质，兼具少女感与通勤质感。",
                       "name":    "慧慧"},
    }

    print("🔹 运行中...")
    try:
        result = run_workflow(
            workflow_name = wf_name,
            image_bytes   = img_bytes,
            filename      = Path(LOCAL_IMAGE_PATH).name,
            product_name  = "测试产品",
            save_dir      = "./output/images",
            video_dir     = "./output/videos",
            extra_params  = extra_map.get(wf_name),
        )
        output_type = result["output_type"]
        if output_type == "video":
            paths = result["video_paths"]
            print(f"\n✅ 完成！共 {len(paths)} 个视频")
            for p in paths:
                print(f"  🎬 {p}")
        else:
            paths = result["image_paths"]
            print(f"\n✅ 完成！共 {len(paths)} 张图片")
            for p in paths:
                print(f"  📄 {p}")
    except Exception as e:
        print(f"❌ 失败: {e}")
