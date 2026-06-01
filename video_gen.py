# 视频生成接口封装：提交任务、查询状态并下载最终视频文件。
import base64
import os
import time
import requests
from pathlib import Path
from datetime import datetime

API_KEY = os.getenv("YUNWU_API_KEY", "")
API_BASE = os.getenv("YUNWU_BASE_URL", "https://yunwu.ai")
MODEL = os.getenv("YUNWU_VIDEO_MODEL", "grok-video-3-10s")
ASPECT_RATIO = "9:16"
SIZE         = "720P"
POLL_INTERVAL = 5
POLL_TIMEOUT  = 120   # 次，共 10 分钟
SAVE_DIR      = "./output/videos"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type":  "application/json",
    "Accept":        "application/json",
}

FINAL_STATUSES = {
    "completed", "failed", "error",
    "video_generation_failed", "video_upsampling_failed",
}


def _to_base64(image_bytes: bytes, filename: str) -> str:
    ext  = filename.rsplit(".", 1)[-1].lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
    return f"data:{mime};base64," + base64.b64encode(image_bytes).decode()


def create_video(prompt: str, image_bytes: bytes, filename: str = "image.png") -> str:
    """提交视频生成任务，返回 task_id。"""
    payload = {
        "model":        MODEL,
        "prompt":       prompt,
        "aspect_ratio": ASPECT_RATIO,
        "size":         SIZE,
        "images":       [_to_base64(image_bytes, filename)],
    }
    resp = requests.post(f"{API_BASE}/v1/video/create", headers=HEADERS, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    task_id = data.get("id")
    if not task_id:
        raise Exception(f"提交失败：{data}")
    return task_id


def query_task(task_id: str) -> dict:
    """查询任务状态，返回原始 dict。"""
    resp = requests.get(f"{API_BASE}/v1/video/query",
                        params={"id": task_id}, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def poll_until_done(task_id: str, callback=None) -> str:
    """
    轮询直到完成，返回 video_url。
    callback(status: str, progress: int) 供调用方更新进度。
    失败时 raise Exception。
    """
    progress_map = {
        "pending": 10, "image_downloading": 20, "video_generating": 50,
        "video_generation_completed": 70, "video_upsampling": 85,
        "video_upsampling_completed": 95, "completed": 100,
    }
    for _ in range(POLL_TIMEOUT):
        time.sleep(POLL_INTERVAL)
        data   = query_task(task_id)
        status = data.get("status", "unknown")
        prog   = progress_map.get(status, 5)
        if callback:
            callback(status, prog)
        if status == "completed":
            url = data.get("video_url")
            if not url:
                raise Exception("完成但无 video_url")
            return url
        if status in FINAL_STATUSES:
            raise Exception(f"生成失败，状态: {status}")
    raise Exception("轮询超时（10分钟）")


def download_video(url: str, save_dir: str = SAVE_DIR) -> str:
    """下载视频到本地，返回本地路径。"""
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(save_dir) / f"video_{ts}.mp4"
    resp = requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()
    with open(path, "wb") as f:
        for chunk in resp.iter_content(8192):
            f.write(chunk)
    return str(path.resolve())


def generate_video(
    prompt: str,
    image_bytes: bytes,
    filename: str = "image.png",
    save_dir: str = SAVE_DIR,
    callback=None,
) -> dict:
    """
    完整流程：提交 → 轮询 → 下载。
    返回 {"task_id", "video_url", "local_path"}
    """
    task_id   = create_video(prompt, image_bytes, filename)
    video_url = poll_until_done(task_id, callback)
    local     = download_video(video_url, save_dir)
    return {"task_id": task_id, "video_url": video_url, "local_path": local}
# 视频生成 API 封装：提交任务、查询状态并下载最终视频文件。
