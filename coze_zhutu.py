# 主图与详情图工作流测试脚本：上传图片后批量拉取并保存生成图。
"""
多工作流版本：
python coze_workflow.py zhutu      # 运行主图工作流
python coze_workflow.py xiangxitu  # 运行详情图工作流
"""
import sys
import json
import re
import os
import requests
from pathlib import Path
from datetime import datetime

# ===================== 配置 =====================
TOKEN = os.getenv("COZE_TOKEN", "")
IMAGE_RELAY_URL = os.getenv("PT_IMAGE_RELAY_URL", "")
LOCAL_IMAGE_PATH = r"D:\download\DOWN\微信图片_20260427221917_947_63.jpg"
SAVE_FOLDER = "./ima"
Path(SAVE_FOLDER).mkdir(exist_ok=True)

# ===================== 工作流配置 =====================
WORKFLOWS = {
    "zhutu": {
        "workflow_id": os.getenv("COZE_WORKFLOW_ZHUTU_ID", ""),
        "parameters": {
            "chajian": "即梦",
            "chanpinming": "慧慧包包",
            "mihe_key": os.getenv("COZE_MIHE_KEY", ""),
            "wenan":"PKP",
        },
        "desc": "主图工作流",
    },
    "xiangxitu": {
        "workflow_id": os.getenv("COZE_WORKFLOW_XIANGXITU_ID", ""),
        "parameters": {
            "mihe_key": os.getenv("COZE_MIHE_KEY", ""),
        },
        "desc": "详情图工作流",
    },
        "xiangxitu2": {
        "workflow_id": os.getenv("COZE_WORKFLOW_XIANGXITU2_ID", ""),
        "parameters": {
            "ratio": "2:3",  # ← 补上，常见值如 "1:1" "3:4" "16:9"，按你工作流实际需求填
        },
        "desc": "详情图工作流2",
    },
}


# ===================== 上传中转 =====================
def upload_to_relay(image_bytes: bytes, filename: str = "image.png") -> str:
    ext = Path(filename).suffix.lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".webp": "image/webp", ".gif": "image/gif"}
    mime = mime_map.get(ext, "image/png")
    resp = requests.post(
        IMAGE_RELAY_URL,
        files={"image": (filename, image_bytes, mime)},
        headers={"ngrok-skip-browser-warning": "true"},
        timeout=60,
    )
    data = resp.json()
    url = data.get("url") or data["data"]["url"]
    if not url.startswith("http"):
        url = "http://" + url
    return url


# ===================== 下载图片（时间戳命名）=====================
def download_image(url: str, workflow_name: str, index: int = 0):
    print(f"  ⬇ 下载中 [{index + 1}]: {url}")
    try:
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
        # 文件名格式：工作流名_时间戳_序号.png
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = Path(SAVE_FOLDER) / f"{workflow_name}_{timestamp}_{index + 1:02d}.png"
        with open(save_path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        print(f"  ✅ 保存: {save_path.resolve()}")
    except Exception as e:
        print(f"  ❌ 下载失败: {e}")


# ===================== 提取并下载所有 URL =====================
def extract_and_download_urls(content: str, workflow_name: str) -> bool:
    # 先尝试 JSON 解析，递归提取所有 URL
    try:
        obj = json.loads(content)
        urls = []

        def collect(v):
            if isinstance(v, str) and v.startswith("http"):
                urls.append(v)
            elif isinstance(v, list):
                for item in v:
                    collect(item)
            elif isinstance(v, dict):
                for val in v.values():
                    collect(val)

        collect(obj)
        if urls:
            print(f"\n📦 共提取到 {len(urls)} 张图片，开始下载...")
            for i, url in enumerate(urls):
                download_image(url, workflow_name, i)
            return True
    except (json.JSONDecodeError, TypeError):
        pass

    # 正则兜底
    urls = re.findall(r'https?://[^\s"\'>,]+\.(?:png|jpg|jpeg|webp|gif)', content, re.IGNORECASE)
    if urls:
        print(f"\n📦 正则提取到 {len(urls)} 张图片，开始下载...")
        for i, url in enumerate(urls):
            download_image(url, workflow_name, i)
        return True

    return False


# ===================== 运行工作流 =====================
def run_workflow(workflow_name: str, img_url: str):
    config = WORKFLOWS[workflow_name]
    workflow_id = config["workflow_id"]

    parameters = dict(config["parameters"])
    parameters["img"] = img_url      # 原有的
    parameters["image"] = img_url

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "workflow_id": workflow_id,
        "parameters": parameters,
    }

    print(f"🔹 工作流: {config['desc']} (id: {workflow_id})")

    resp = requests.post(
        "https://api.coze.cn/v1/workflow/stream_run",
        headers=headers,
        json=payload,
        stream=True,
        timeout=300,
    )

    if resp.status_code != 200:
        print(f"❌ HTTP 错误: {resp.status_code}\n{resp.text}")
        return

    current_event = None
    current_data = None
    downloaded = False

    for raw_line in resp.iter_lines():
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line

        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            current_data = line[len("data:"):].strip()
        elif line == "":
            if not current_event or not current_data:
                current_event = None
                current_data = None
                continue

            event_type = current_event
            data_str = current_data
            current_event = None
            current_data = None

            if data_str == "{}":
                if event_type == "Done":
                    print("✅ 工作流执行完成！")
                continue

            try:
                obj = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            if event_type == "Message":
                content = obj.get("content", "")
                node_title = obj.get("node_title", "")
                node_is_finish = obj.get("node_is_finish", False)

                if node_title and not downloaded:
                    print(content, end="", flush=True)
                    if node_is_finish:
                        print()

                if node_is_finish and not downloaded:
                    if extract_and_download_urls(content, workflow_name):
                        downloaded = True

            elif event_type == "Error":
                print(f"\n❌ 错误: code={obj.get('error_code')}, {obj.get('error_message')}")

            elif event_type == "Done":
                debug_url = obj.get("debug_url", "")
                if debug_url:
                    print(f"🔗 调试链接: {debug_url}")
                print("✅ 工作流执行完成！")


# ===================== 主程序 =====================
if __name__ == "__main__":
    # 解析命令行参数
    if len(sys.argv) < 2 or sys.argv[1] not in WORKFLOWS:
        available = " / ".join(WORKFLOWS.keys())
        print(f"用法: python coze_workflow.py [{available}]")
        print("示例: python coze_workflow.py zhutu")
        sys.exit(1)

    workflow_name = sys.argv[1]

    print("🔹 读取本地图片...")
    with open(LOCAL_IMAGE_PATH, "rb") as f:
        img_bytes = f.read()

    print("🔹 上传到中转服务器...")
    img_url = upload_to_relay(img_bytes, Path(LOCAL_IMAGE_PATH).name)
    print(f"✅ 图片URL: {img_url}\n")

    run_workflow(workflow_name, img_url)
