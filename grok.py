# 视频生成界面：调用 yunwu/grok 接口创建视频任务并展示状态。
import streamlit as st
import os
import requests
import base64
import time

# ── 配置 ─────────────────────────────────────────────────────
API_KEY = os.getenv("YUNWU_API_KEY", "")
API_BASE = os.getenv("YUNWU_BASE_URL", "https://yunwu.ai")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# ── 图片转 base64 ─────────────────────────────────────────────

def to_base64(file_bytes: bytes, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
    return f"data:{mime};base64," + base64.b64encode(file_bytes).decode()


# ── API 调用 ──────────────────────────────────────────────────

def create_video(model, prompt, aspect_ratio, size, images_b64: list[str]):
    if model == "grok-videos":
        data = {"model": model, "prompt": prompt, "size": aspect_ratio}
        if images_b64:
            data["input_reference"] = images_b64[0]
        r = requests.post(
            f"{API_BASE}/v1/videos",
            headers={"Authorization": f"Bearer {API_KEY}"},
            data=data,
        )
    else:
        payload = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "size": size,
            "images": images_b64,
        }
        r = requests.post(f"{API_BASE}/v1/video/create", headers=HEADERS, json=payload)
    return r.json()


def query_task(task_id):
    r = requests.get(
        f"{API_BASE}/v1/video/query",
        params={"id": task_id},
        headers=HEADERS,
    )
    return r.json()


# ── 状态 ─────────────────────────────────────────────────────

STATUS_LABELS = {
    "pending": "⏳ 等待中",
    "image_downloading": "📥 图片下载中",
    "video_generating": "🎬 视频生成中",
    "video_generation_completed": "✅ 生成完成，处理中",
    "video_upsampling": "🔍 超分处理中",
    "video_upsampling_completed": "✅ 超分完成",
    "completed": "✅ 完成",
    "failed": "❌ 失败",
    "error": "❌ 错误",
}
PROGRESS_MAP = {
    "pending": 10, "image_downloading": 20, "video_generating": 50,
    "video_generation_completed": 70, "video_upsampling": 85,
    "video_upsampling_completed": 95, "completed": 100,
}
FINAL = {"completed", "failed", "error", "video_generation_failed", "video_upsampling_failed"}

# ── UI ───────────────────────────────────────────────────────

st.set_page_config(page_title="视频生成", layout="centered")
st.title("🎬 视频生成")

model = st.selectbox("模型", ["grok-video-3", "grok-video-3-10s", "grok-videos"], key="model")
prompt_text = st.text_area("提示词", key="prompt", placeholder="描述视频内容...")

col1, col2 = st.columns(2)
with col1:
    aspect_ratio = st.selectbox("比例", ["3:2", "2:3", "1:1", "16:9", "9:16"], key="aspect_ratio")
with col2:
    size = st.selectbox("分辨率", ["720P", "1080P"], key="size")

st.markdown("**垫图（可选）**")
ref_mode = st.radio(
    "参考图模式",
    ["standard（普通参考）", "custom（严格跟随参考图）"],
    key="ref_mode", horizontal=True,
)

uploaded = st.file_uploader(
    "上传垫图", type=["png", "jpg", "jpeg", "webp"],
    key="img_upload", label_visibility="visible",
)

images_b64 = []
if uploaded:
    st.image(uploaded, width=200)
    cache_key = f"b64_{uploaded.name}_{uploaded.size}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = to_base64(uploaded.read(), uploaded.name)
    images_b64 = [st.session_state[cache_key]]
    st.caption("✅ 垫图已就绪（base64）")

# ── 提交 ─────────────────────────────────────────────────────

if st.button("🚀 生成视频", key="submit", use_container_width=True):
    if not prompt_text:
        st.error("请输入提示词")
        st.stop()

    final_prompt = prompt_text
    if images_b64 and "custom" in ref_mode:
        if "--mode=custom" not in final_prompt:
            final_prompt = final_prompt.rstrip() + "  --mode=custom"

    with st.spinner("提交任务中..."):
        try:
            result = create_video(model, final_prompt, aspect_ratio, size, images_b64)
        except Exception as e:
            st.error(f"请求失败: {e}")
            st.stop()

    task_id = result.get("id")
    if not task_id:
        st.error(f"创建失败: {result}")
        st.stop()

    st.success(f"任务 ID：`{task_id}`")

    status_box = st.empty()
    bar = st.progress(0)
    video_box = st.empty()

    for _ in range(120):
        time.sleep(5)
        try:
            data = query_task(task_id)
        except Exception as e:
            status_box.warning(f"查询异常: {e}")
            continue

        status = data.get("status", "unknown")
        status_box.info(STATUS_LABELS.get(status, status))
        bar.progress(PROGRESS_MAP.get(status, 5))

        if status == "completed":
            video_url = data.get("video_url")
            if video_url:
                video_box.video(video_url)
                st.markdown(f"[📥 下载视频]({video_url})")
            break
        elif status in FINAL:
            st.error(f"任务结束，状态: {status}")
            st.json(data)
            break
    else:
        st.warning("轮询超时，请手动查询")

# ── 手动查询 ──────────────────────────────────────────────────

st.divider()
st.subheader("🔍 手动查询任务")
manual_id = st.text_input("任务 ID", key="manual_id", placeholder="grok:xxxx-xxxx")
if st.button("查询", key="query_btn"):
    if not manual_id:
        st.error("请填写任务 ID")
    else:
        data = query_task(manual_id)
        st.json(data)
        if data.get("video_url"):
            st.video(data["video_url"])
# 视频生成界面：调用 yunwu/grok 接口创建视频任务并展示状态。
