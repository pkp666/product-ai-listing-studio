# 云雾视频生成界面：调用 yunwu.ai 的视频接口并展示任务进度。
import streamlit as st
import os
import requests
import base64

API_KEY = os.getenv("YUNWU_API_KEY", "")

st.title("Image 生成 & 编辑")

model = st.selectbox("模型", ["grok-3-image", "gpt-image-2", "gpt-image-2-all"], label_visibility="visible")
image_files = st.file_uploader("上传参考图（可选，最多16张，有图则编辑，无图则生成）", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True, label_visibility="visible")
prompt = st.text_area("提示词", label_visibility="visible")

if image_files and len(image_files) > 16:
    st.warning("最多上传16张图片")

if st.button("生成"):
    if not prompt:
        st.warning("请填写提示词")
    elif image_files and len(image_files) > 16:
        st.warning("最多上传16张图片")
    else:
        with st.spinner("处理中..."):
            if image_files:
                files = [("image[]", (f.name, f.getvalue(), f.type)) for f in image_files]
                resp = requests.post(
                    "https://yunwu.ai/v1/images/edits",
                    headers={"Authorization": f"Bearer {API_KEY}"},
                    data={"model": model, "prompt": prompt},
                    files=files,
                )
            else:
                resp = requests.post(
                    "https://yunwu.ai/v1/images/generations",
                    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                    json={"model": model, "prompt": prompt, "size": "1024x1024"},
                )
            data = resp.json()
            if "data" in data:
                url = data["data"][0].get("url")
                b64 = data["data"][0].get("b64_json")
                if url:
                    st.image(url)
                elif b64:
                    st.image(base64.b64decode(b64))
            else:
                st.error(str(data))
# 云雾视频生成界面：调用 yunwu.ai 的视频接口并展示任务进度。
