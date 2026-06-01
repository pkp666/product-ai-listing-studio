# 带货视频工作流封装：上传图片、触发工作流并下载生成结果。
"""
视频工作流调用模块 - shipintu
"""

import json
import os
import re
import requests
from pathlib import Path
from datetime import datetime

COZE_TOKEN       = os.getenv("COZE_TOKEN", "")
IMAGE_RELAY_URL  = os.getenv("PT_IMAGE_RELAY_URL", "")
WORKFLOW_ID      = os.getenv("COZE_WORKFLOW_VIDEO_ID", "")
DEFAULT_VIDEO_DIR = "./output/videos"


def _upload_image(image_bytes: bytes, filename: str = "image.png") -> str:
    ext  = Path(filename).suffix.lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(ext, "image/png")
    resp = requests.post(
        IMAGE_RELAY_URL,
        files={"image": (filename, image_bytes, mime)},
        headers={"ngrok-skip-browser-warning": "true"},
        timeout=600,
    )
    data = resp.json()
    url  = data.get("url") or data["data"]["url"]
    return url if url.startswith("http") else "http://" + url


def _extract_video_urls(content: str) -> list[str]:
    try:
        obj  = json.loads(content)
        urls = []
        def collect(v):
            if isinstance(v, str) and v.startswith("http"):
                urls.append(v)
            elif isinstance(v, list):
                for i in v: collect(i)
            elif isinstance(v, dict):
                for i in v.values(): collect(i)
        collect(obj)
        if urls:
            video = [u for u in urls if re.search(r'\.(mp4|mov|avi|webm)', u, re.I)]
            return video if video else urls
    except Exception:
        pass
    return re.findall(r'https?://[^\s"\'>,]+', content)


def _download(url: str, save_path: Path) -> str:
    r = requests.get(url, stream=True, timeout=3000)
    r.raise_for_status()
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    return str(save_path.resolve())


def run_video_workflow(
    image_bytes: bytes,
    maidian:     str,
    filename:    str = "image.png",
    name:        str = "慧慧",
    video_dir:   str = DEFAULT_VIDEO_DIR,
) -> dict:
    """
    返回：
    {
        "video_urls":  ["http://..."],
        "video_paths": ["/abs/path/xxx.mp4"],
    }
    """
    img_url = _upload_image(image_bytes, filename)

    params  = {
        "img":     img_url,
            "key":     os.getenv("COZE_MIHE_KEY", ""),
        "maidian": maidian,
        "name":    name,
    }

    # ==============================================
    # 🔥 这里加了 save_log=true 开启保存历史
    # ==============================================
    resp = requests.post(
        "https://api.coze.cn/v1/workflow/stream_run",
        headers={"Authorization": f"Bearer {COZE_TOKEN}", "Content-Type": "application/json"},
        json={
            "workflow_id": WORKFLOW_ID,
            "parameters": params,
            "is_async": False,     # 必须加
            "save_log": True       # ✅ 保存历史（核心）
        },
        stream=True,
        timeout=3000,
    )
    if resp.status_code != 200:
        raise Exception(f"HTTP {resp.status_code}: {resp.text[:300]}")

    all_urls      = []
    current_event = current_data = None

    for raw in resp.iter_lines():
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if line.startswith("event:"):
            current_event = line[6:].strip()
        elif line.startswith("data:"):
            current_data = line[5:].strip()
        elif line == "":
            if current_event and current_data and current_data != "{}":
                try:
                    obj = json.loads(current_data)
                except Exception:
                    current_event = current_data = None
                    continue
                if current_event == "Error":
                    raise Exception(f"工作流错误: {obj.get('error_message')}")
                if current_event == "Message" and obj.get("node_is_finish") and obj.get("content"):
                    all_urls.extend(_extract_video_urls(obj["content"]))
            current_event = current_data = None

    if not all_urls:
        raise Exception("工作流未返回任何视频 URL")

    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_root  = Path(video_dir) / timestamp
    video_paths = []
    for i, url in enumerate(all_urls):
        ext  = Path(url.split("?")[0]).suffix
        ext  = ext if ext.lower() in (".mp4", ".mov", ".avi", ".webm") else ".mp4"
        path = _download(url, save_root / f"video_{i+1:02d}{ext}")
        video_paths.append(path)

    return {"video_urls": all_urls, "video_paths": video_paths}


# ── 脚本测试 ──────────────────────────────────
if __name__ == "__main__":
    TEST_IMAGE = r"D:\download\DOWN\微信图片_20260427221917_947_63.jpg"
    with open(TEST_IMAGE, "rb") as f:
        img = f.read()

    result = run_video_workflow(
        image_bytes = img,
        filename    = Path(TEST_IMAGE).name,
        maidian     = "牛仔布拼接PU皮革，兼具少女感与通勤质感。",
        name        = "慧慧",
    )
    print(f"✅ 共 {len(result['video_paths'])} 个视频")
    for p in result['video_paths']:
        print(f"  🎬 {p}")
