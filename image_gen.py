# 图像生成与编辑工具：封装上传、轮询和批量调用图像接口的能力。
import os
import time
import threading
import queue
import requests
from pathlib import Path
import uuid

API_KEY = os.getenv("GRSAI_API_KEY", "")
BASE_URL = os.getenv("GRSAI_BASE_URL", "https://grsaiapi.com")
HEADERS  = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
IMG_DIR  = "images"

YUNWU_API_KEY = os.getenv("YUNWU_API_KEY", "")

os.makedirs(IMG_DIR, exist_ok=True)

GPTIMAGE2_MODELS = ["gpt-image-2", "gpt-image-2-vip"]
BANANA_MODELS = [
    "nano-banana-fast", "nano-banana", "nano-banana-pro",
    "nano-banana-pro-vt", "nano-banana-2", "nano-banana-2-cl",
]


# ── 图片上传中转 ──────────────────────────────────────────────

def _upload_image(image_path: str, server_url: str) -> str | None:
    if not image_path or not os.path.exists(image_path):
        return None
    try:
        upload_url = f"{server_url.rstrip('/')}/upload/image"
        with open(image_path, "rb") as f:
            files = {"image": (Path(image_path).name, f, "image/png")}
            r = requests.post(
                upload_url, files=files,
                headers={"ngrok-skip-browser-warning": "true"}, timeout=60
            )
        if r.status_code == 200:
            result = r.json()
            url = result.get("url") or (result.get("data") or {}).get("url")
            if url and not url.startswith("http"):
                url = "http://" + url
            return url
        return None
    except Exception as e:
        print(f"[image_gen] 上传失败 {image_path}: {e}")
        return None


def _upload_refs(ref_paths: list[str], server_url: str) -> list[str]:
    if not server_url:
        return []
    urls = [None] * len(ref_paths)
    lock = threading.Lock()

    def worker(i, path):
        url = _upload_image(path, server_url)
        with lock:
            urls[i] = url

    threads = [
        threading.Thread(target=worker, args=(i, p), daemon=True)
        for i, p in enumerate(ref_paths) if p and os.path.exists(p)
    ]
    for t in threads: t.start()
    for t in threads: t.join()
    return [u for u in urls if u]


# ── 轮询 & 下载 ──────────────────────────────────────────────

def _poll(task_id: str, timeout: int = 300) -> str | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        r = requests.post(
            f"{BASE_URL}/v1/draw/result", headers=HEADERS,
            json={"id": task_id}, timeout=15
        )
        res    = (r.json().get("data") or {})
        status = res.get("status")
        if status == "succeeded":
            results = res.get("results", [])
            return results[0]["url"] if results else None
        elif status == "failed":
            print(f"[image_gen] 生图失败: {res.get('failure_reason')} {res.get('error')}")
            return None
    return None


def _download(url: str, index: int) -> str | None:
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        filename = f"{IMG_DIR}/{int(time.time())}_{index}_{uuid.uuid4().hex[:8]}.png"
        with open(filename, "wb") as f:
            f.write(r.content)
        return filename
    except Exception:
        return None


# ── 云雾调用（单次，指定model）────────────────────────────────

def _call_yunwu(prompt: str, model: str,
                ref_urls: list[str] | None = None) -> str | None:
    try:
        headers = {"Authorization": f"Bearer {YUNWU_API_KEY}"}
        if ref_urls:
            # 下载参考图再以 multipart 上传
            files = []
            for i, u in enumerate(ref_urls):
                try:
                    content = requests.get(u, timeout=30).content
                    files.append(("image[]", (f"ref_{i}.jpg", content, "image/jpeg")))
                except Exception as e:
                    print(f"[image_gen] 云雾下载参考图失败 {u}: {e}")
            resp = requests.post(
                "https://yunwu.ai/v1/images/edits",
                headers=headers,
                data={"model": model, "prompt": prompt},
                files=files,
                timeout=120,
            )
        else:
            resp = requests.post(
                "https://yunwu.ai/v1/images/generations",
                headers={**headers, "Content-Type": "application/json"},
                json={"model": model, "prompt": prompt, "size": "1024x1024"},
                timeout=120,
            )
        data = resp.json()
        if "data" in data:
            return data["data"][0].get("url") or data["data"][0].get("b64_json")
        print(f"[image_gen] 云雾({model})返回异常: {data}")
        return None
    except Exception as e:
        print(f"[image_gen] 云雾({model})调用失败: {e}")
        return None


# ── 提交 gptimage2（grsai）────────────────────────────────────

def _submit_gptimage2(prompt: str, model: str, size: str,
                      ref_urls: list[str] | None = None) -> str:
    print(f"[image_gen] 提交生图 model={model} size={size}")
    payload = {
        "model": model,
        "prompt": prompt,
        "aspectRatio": size,
        "shutProgress": True,
        "webHook": "-1",
    }
    if ref_urls:
        payload["urls"] = ref_urls
    r   = requests.post(f"{BASE_URL}/v1/draw/completions", headers=HEADERS, json=payload, timeout=30)
    raw = r.json()
    if raw.get("code") != 0:
        raise ValueError(f"提交失败: {raw.get('msg')}")
    task_id = (raw.get("data") or {}).get("id")
    if not task_id:
        raise ValueError(f"未获取到 task_id: {raw}")
    return task_id


def _submit_banana(prompt: str, model: str, size: str,
                   ref_urls: list[str] | None = None,
                   image_size: str = "4K") -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "aspectRatio": size,
        "imageSize": image_size,
        "shutProgress": True,
        "webHook": "-1",
    }
    if ref_urls:
        payload["urls"] = ref_urls
    r   = requests.post(f"{BASE_URL}/v1/draw/nano-banana", headers=HEADERS, json=payload, timeout=30)
    raw = r.json()
    if raw.get("code") != 0:
        raise ValueError(f"提交失败: {raw.get('msg')}")
    task_id = (raw.get("data") or {}).get("id")
    if not task_id:
        raise ValueError(f"未获取到 task_id: {raw}")
    return task_id


# ── worker ───────────────────────────────────────────────────

def _worker(index: int, prompt: str, model: str, size: str,
            q: queue.Queue, ref_urls: list[str] | None = None,
            backend: str = "gptimage2"):
    try:
        url = None

        if backend == "banana":
            for image_size in ["2K", "2K"]:
                try:
                    task_id = _submit_banana(prompt, model, size, ref_urls, image_size)
                    url     = _poll(task_id)
                    if url:
                        print(f"[image_gen] banana {image_size} 成功 index={index}")
                        break
                    print(f"[image_gen] banana {image_size} 返回空，尝试降级")
                except Exception as e:
                    print(f"[image_gen] banana {image_size} 失败 index={index}: {e}")

        else:
            # 三级降级：云雾 gpt-image-2-all → 云雾 gpt-image-2 → grsai gpt-image-2
            print(f"[image_gen] 尝试云雾 gpt-image-2-all index={index}")
            url = _call_yunwu(prompt, "gpt-image-2-all", ref_urls)

            if not url:
                print(f"[image_gen] 云雾 gpt-image-2-all 失败，降级云雾 gpt-image-2 index={index}")
                url = _call_yunwu(prompt, "gpt-image-2", ref_urls)

            if not url:
                print(f"[image_gen] 云雾 gpt-image-2 失败，降级 grsai index={index}")
                task_id = _submit_gptimage2(prompt, "gpt-image-2", size, ref_urls)
                url     = _poll(task_id)

        if url:
            local_path = _download(url, index)
            q.put({"index": index, "url": local_path or url})
        else:
            q.put({"index": index, "url": None})

    except Exception as e:
        print(f"[image_gen] worker error index={index}: {e}")
        q.put({"index": index, "url": None, "error": str(e)})


# ── 对外接口 ─────────────────────────────────────────────────

def generate_images(
    prompts: list[str],
    backend: str = "gptimage2",
    model: str = "gpt-image-2",
    size: str = "1:1",
) -> list[str | None]:
    total   = len(prompts)
    results = [None] * total
    q       = queue.Queue()

    threads = [
        threading.Thread(
            target=_worker,
            args=(i, p, model, size, q, None, backend),
            daemon=True
        )
        for i, p in enumerate(prompts)
    ]
    for t in threads: t.start()
    for _ in range(total):
        item = q.get()
        results[item["index"]] = item.get("url")
    for t in threads: t.join()
    return results


def generate_shot_images(
    prompts: list[str],
    ref_chars: list[str],
    ref_scene: str | None,
    upload_server: str = "",
    backend: str = "gptimage2",
    model: str = "gpt-image-2",
    size: str = "1:1",
) -> list[str | None]:
    ref_paths = [p for p in ref_chars if p and os.path.exists(p)]
    if ref_scene and os.path.exists(ref_scene):
        ref_paths.append(ref_scene)

    if not ref_paths:
        print("[image_gen] 无参考图，使用普通生图")
        return generate_images(prompts, backend, model, size)

    if not upload_server:
        print("[image_gen] 未配置上传服务器，使用普通生图")
        return generate_images(prompts, backend, model, size)

    print(f"[image_gen] 上传 {len(ref_paths)} 张参考图...")
    ref_urls = _upload_refs(ref_paths, upload_server)

    if not ref_urls:
        print("[image_gen] 参考图上传全部失败，退回普通生图")
        return generate_images(prompts, backend, model, size)

    print(f"[image_gen] 上传成功 {len(ref_urls)} 张，开始生图（含参考图）")
    print(f"[image_gen] 参考图URL: {ref_urls}")
    total   = len(prompts)
    results = [None] * total
    q       = queue.Queue()

    threads = [
        threading.Thread(
            target=_worker,
            args=(i, p, model, size, q, ref_urls, backend),
            daemon=True
        )
        for i, p in enumerate(prompts)
    ]
    for t in threads: t.start()
    for _ in range(total):
        item = q.get()
        results[item["index"]] = item.get("url")
    for t in threads: t.join()
    return results
