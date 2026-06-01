# nano-banana 生图测试界面：支持参考图上传、批量生成和结果展示。
"""
banana_test.py — nano-banana 系列生图测试工具
streamlit run banana_test.py
"""
import os
import time
import threading
import queue
import requests
import streamlit as st
from pathlib import Path
import uuid

# ── 配置 ──────────────────────────────────────────────────────
API_KEY = os.getenv("GRSAI_API_KEY", "")
BASE_URL = os.getenv("GRSAI_BASE_URL", "https://grsaiapi.com")
HEADERS      = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
RELAY_URL = os.getenv("PT_IMAGE_RELAY_BASE_URL", "")
IMG_DIR      = "banana_output"
os.makedirs(IMG_DIR, exist_ok=True)

BANANA_MODELS = [
    "nano-banana-fast",
    "nano-banana",
    "nano-banana-pro",
    "nano-banana-pro-vt",
    "nano-banana-2",
    "nano-banana-2-cl",
]
RATIO_OPTIONS   = ["1:1", "3:4", "4:3", "9:16", "16:9", "3:2", "2:3"]
SIZE_OPTIONS    = ["1K", "2K", "4K"]


# ── 上传中转 ──────────────────────────────────────────────────

def upload_to_relay(image_bytes: bytes, filename: str) -> str:
    ext  = Path(filename).suffix.lower()
    mime = {".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",
            ".webp":"image/webp"}.get(ext, "image/png")
    resp = requests.post(
        f"{RELAY_URL}/upload/image",
        files={"image": (filename, image_bytes, mime)},
        headers={"ngrok-skip-browser-warning": "true"},
        timeout=60,
    )
    data = resp.json()
    url  = data.get("url") or (data.get("data") or {}).get("url", "")
    if url and not url.startswith("http"):
        url = "http://" + url
    return url


# ── 提交 & 轮询 ───────────────────────────────────────────────

def submit_banana(prompt: str, model: str, ratio: str, image_size: str,
                  ref_urls: list[str] | None = None) -> str:
    payload = {
        "model":       model,
        "prompt":      prompt,
        "aspectRatio": ratio,
        "imageSize":   image_size,
        "shutProgress": True,
        "webHook":     "-1",
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


def poll_result(task_id: str, timeout: int = 300) -> str | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        r   = requests.post(f"{BASE_URL}/v1/draw/result", headers=HEADERS,
                            json={"id": task_id}, timeout=15)
        res = (r.json().get("data") or {})
        st  = res.get("status")
        if st == "succeeded":
            results = res.get("results", [])
            return results[0]["url"] if results else None
        elif st == "failed":
            raise ValueError(f"生图失败: {res.get('failure_reason')} {res.get('error')}")
    raise TimeoutError("轮询超时")


def download_image(url: str, prefix: str = "banana") -> str:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    path = f"{IMG_DIR}/{prefix}_{int(time.time())}_{uuid.uuid4().hex[:6]}.png"
    with open(path, "wb") as f:
        f.write(r.content)
    return path


# ── 并发生图 ──────────────────────────────────────────────────

def run_batch(prompt, model, ratio, image_size, count, ref_urls, progress_cb):
    q       = queue.Queue()
    results = [None] * count

    def worker(idx):
        try:
            task_id = submit_banana(prompt, model, ratio, image_size, ref_urls)
            url     = poll_result(task_id)
            if url:
                local = download_image(url, model.replace("-","_"))
                q.put({"idx": idx, "path": local, "url": url})
            else:
                q.put({"idx": idx, "path": None, "error": "空结果"})
        except Exception as e:
            q.put({"idx": idx, "path": None, "error": str(e)})

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(count)]
    for t in threads: t.start()

    done = 0
    while done < count:
        item = q.get()
        results[item["idx"]] = item
        done += 1
        progress_cb(done, count)

    for t in threads: t.join()
    return results


# ── UI ────────────────────────────────────────────────────────

st.set_page_config(page_title="Banana 生图测试", page_icon="🍌", layout="wide")
st.title("🍌 nano-banana 生图测试")

# ── 左栏：参数 ──
with st.sidebar:
    st.header("参数配置")
    model      = st.selectbox("模型", BANANA_MODELS, index=1)
    ratio      = st.selectbox("比例", RATIO_OPTIONS, index=0)
    image_size = st.selectbox("分辨率", SIZE_OPTIONS, index=0)
    count      = st.slider("生成数量", 1, 8, 1)

    st.divider()
    st.markdown("**参考图（选填）**")
    uploaded = st.file_uploader("上传参考图", type=["png","jpg","jpeg","webp"],
                                 accept_multiple_files=True, label_visibility="collapsed")

# ── 主区域 ──
prompt = st.text_area("提示词", placeholder="描述你想生成的图片...", height=120)

if st.button("🚀 开始生成", type="primary", use_container_width=True):
    if not prompt:
        st.error("请输入提示词")
        st.stop()

    # 上传参考图
    ref_urls = []
    if uploaded:
        with st.spinner(f"上传 {len(uploaded)} 张参考图..."):
            for f in uploaded:
                url = upload_to_relay(f.read(), f.name)
                if url:
                    ref_urls.append(url)
        st.caption(f"✅ 参考图已上传：{len(ref_urls)} 张")

    # 进度
    prog_text = st.empty()
    prog_bar  = st.progress(0)

    def update_progress(done, total):
        prog_bar.progress(done / total)
        prog_text.caption(f"完成 {done}/{total}")

    with st.spinner(f"生成中（{model} · {ratio} · {image_size} · {count}张）..."):
        try:
            results = run_batch(prompt, model, ratio, image_size, count, ref_urls, update_progress)
        except Exception as e:
            st.error(f"生成失败：{e}")
            st.stop()

    prog_bar.empty()
    prog_text.empty()

    # 展示结果
    st.divider()
    st.subheader(f"生成结果（{len([r for r in results if r and r.get('path')])} 张成功）")

    success = [r for r in results if r and r.get("path")]
    errors  = [r for r in results if r and r.get("error")]

    if success:
        cols = st.columns(min(len(success), 4))
        for i, item in enumerate(success):
            with cols[i % 4]:
                st.image(item["path"], use_column_width=True)
                st.caption(f"[下载]({item['url']})" if item.get("url") else item["path"])

    for item in errors:
        st.error(f"图 {item['idx']+1} 失败：{item['error']}")

# ── 已生成图片浏览 ──
st.divider()
with st.expander("📁 查看已生成图片"):
    imgs = sorted(Path(IMG_DIR).glob("*.png"), reverse=True)
    if imgs:
        cols = st.columns(5)
        for i, img in enumerate(imgs[:20]):
            with cols[i % 5]:
                st.image(str(img), caption=img.name[:20], use_column_width=True)
    else:
        st.caption("暂无图片")
# nano-banana 生图测试界面：支持参考图上传、批量生成和结果展示。
