# 大模型调用封装：负责文本、视觉请求、重试和图片中转上传。
import time
import os
import json
import requests
from pathlib import Path

# ── 配置常量 ──
API_KEY = os.getenv("YUNWU_API_KEY", "")
BASE_URL = os.getenv("YUNWU_CHAT_BASE_URL", "https://yunwu.ai/v1/chat/completions")
MODEL_ID = os.getenv("YUNWU_TEXT_MODEL", "gpt-5.1")
IMAGE_RELAY_URL = os.getenv("PT_IMAGE_RELAY_URL", "")
TIMEOUT          = (40, 300)
VISION_TIMEOUT   = (40, 300)  # 识图专用，与普通调用相同
IMG_UPLOAD_TIMEOUT = 60              # 上传中转服务器超时
MAX_RETRIES      = 4
RETRY_DELAY      = 2


# ══════════════════════════════════════════════
# 内部工具：上传图片到中转服务器，返回 URL
# ══════════════════════════════════════════════

def _compress_image(image_bytes: bytes, max_mb: float = 2.0) -> bytes:
    """压缩图片到指定大小以内，返回压缩后的 bytes。"""
    max_bytes = int(max_mb * 1024 * 1024)
    if len(image_bytes) <= max_bytes:
        return image_bytes
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        for quality in [85, 75, 65, 55, 45]:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            if buf.tell() <= max_bytes:
                print(f"[llm] 图片压缩: {len(image_bytes)//1024}KB → {buf.tell()//1024}KB (quality={quality})")
                return buf.getvalue()
        # 还是太大：缩小尺寸
        w, h = img.size
        while True:
            w, h = int(w * 0.8), int(h * 0.8)
            img = img.resize((w, h), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75)
            if buf.tell() <= max_bytes or w < 400:
                print(f"[llm] 图片缩尺寸压缩: {w}x{h}")
                return buf.getvalue()
    except Exception as e:
        print(f"[llm] 压缩失败，使用原图: {e}")
    return image_bytes


def _upload_to_relay(image_bytes: bytes, filename: str = "image.png") -> str:
    """
    上传图片 bytes 到中转服务器，返回可公开访问的 URL。
    失败直接 raise Exception。
    """
    image_bytes = _compress_image(image_bytes)  # 上传前压缩
    print(f"[llm] 上传图片到中转 {filename} ({len(image_bytes)//1024}KB)...")
    ext = Path(filename).suffix.lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
    mime = mime_map.get(ext, "image/png")

    resp = requests.post(
        IMAGE_RELAY_URL,
        files={"image": (filename, image_bytes, mime)},
        headers={"ngrok-skip-browser-warning": "true"},
        timeout=IMG_UPLOAD_TIMEOUT,
    )
    if resp.status_code != 200:
        raise Exception(f"图片上传失败: HTTP {resp.status_code} — {resp.text[:200]}")

    data = resp.json()
    url = data.get("url") or data.get("data", {}).get("url")
    if not url:
        raise Exception(f"中转服务器未返回 URL，原始响应: {data}")
    if not url.startswith("http"):
        url = "http://" + url
    return url


# ══════════════════════════════════════════════
# 内部工具：构建 user content（纯文本 or 图文混合）
# ══════════════════════════════════════════════

def _build_user_content(user_prompt: str, image_urls: list[str] | None):
    """
    image_urls=None  → 返回纯字符串（现有行为，不变）
    image_urls=[...] → 返回 list，text + 每张图的 image_url block
    """
    if not image_urls:
        return user_prompt

    content = [{"type": "text", "text": user_prompt}]
    for url in image_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})
    return content


# ══════════════════════════════════════════════
# 核心：_call（所有调用的底层，带重试）
# ══════════════════════════════════════════════

def _call(user_content, system_prompt: str, model: str, timeout=None) -> str:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ],
        "stream": False,
    }
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            _to = timeout or TIMEOUT
            resp = requests.post(BASE_URL, json=payload, headers=headers, timeout=_to)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except (requests.exceptions.SSLError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            last_error = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * (2 ** attempt))
            else:
                raise
        except Exception:
            raise
    raise last_error


# ══════════════════════════════════════════════
# 公开接口
# ══════════════════════════════════════════════

def call_llm(user_prompt: str, system_prompt: str = "你是一个专业助手") -> str:
    """纯文本调用，行为与之前完全一致。"""
    return _call(user_prompt, system_prompt, MODEL_ID)


def call_llm_json(user_prompt: str, system_prompt: str = "你是一个专业助手") -> dict:
    """
    调用 LLM 并解析 JSON。
    成功       → 返回 dict
    解析失败   → raise ValueError（含原始输出，供调用方展示调试）
    网络失败   → 直接 raise
    """
    raw = call_llm(user_prompt, system_prompt)
    text = raw.strip()
    if text.startswith("```"):
        lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON解析失败: {e}\n\n原始输出：\n{raw}")


def call_llm_vision(
    user_prompt: str,
    images: list,                        # 每项可以是 bytes 或 URL字符串
    system_prompt: str = "你是一个专业助手",
    filenames: list[str] | None = None,  # 与 images 对应的文件名（用于 MIME 判断）
) -> str:
    """
    识图调用。
    - images 里每项是 bytes（Streamlit 上传文件的 .read()）或已有的 URL 字符串。
    - bytes 会先上传到中转服务器换取 URL，再发给 LLM。
    - 返回字符串，失败直接 raise。
    """
    image_urls = []
    for i, img in enumerate(images):
        if isinstance(img, str):
            # 已经是 URL，直接用
            image_urls.append(img)
        elif isinstance(img, bytes):
            fname = (filenames[i] if filenames and i < len(filenames) else f"image_{i}.png")
            url = _upload_to_relay(img, fname)
            image_urls.append(url)
        else:
            raise TypeError(f"images[{i}] 类型不支持：{type(img)}，需要 bytes 或 str(URL)")

    user_content = _build_user_content(user_prompt, image_urls)
    # 识图不重试，超时直接抛出
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL_ID,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ],
        "stream": False,
    }
    resp = requests.post(BASE_URL, json=payload, headers=headers, timeout=VISION_TIMEOUT)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def call_llm_vision_json(
    user_prompt: str,
    images: list,
    system_prompt: str = "你是一个专业助手",
    filenames: list[str] | None = None,
) -> dict:
    """
    识图 + 解析 JSON。
    失败处理同 call_llm_json。
    """
    raw = call_llm_vision(user_prompt, images, system_prompt, filenames)
    text = raw.strip()
    if text.startswith("```"):
        lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON解析失败: {e}\n\n原始输出：\n{raw}")


# ══════════════════════════════════════════════
# main：本地测试识图
# ══════════════════════════════════════════════

if __name__ == "__main__":
    TEST_IMAGE = r"D:\download\DOWN\image__00002_.png"

    print("=" * 60)
    with open(TEST_IMAGE, "rb") as f:
        image_bytes = f.read()
    print(f"图片大小：{len(image_bytes) / 1024:.1f} KB")
    print("调用识图中...")

    result = call_llm_vision(
        user_prompt="请详细描述这张图片里有什么，包括主体、颜色、材质、场景等细节。",
        images=[image_bytes],
        filenames=[Path(TEST_IMAGE).name],
    )
    print("\n识图结果：")
    print(result)
    print("=" * 60)
