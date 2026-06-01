# Streamlit 主应用：串起商品信息、AI 文案、平台适配和视频、图片生成流程。
"""
多平台跨境电商系统 — 阶段一 + 阶段二
Streamlit 1.37.1
"""
import json
import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from llm     import call_llm_json, call_llm_vision_json
from ziduan  import empty_product, make_sku_row, export_sku_rows, export_product, load_product, build_sku_matrix, OUTPUT_FIELDS, PDD_OUTPUT_FIELDS, CATEGORY_OPTIONS, DEFAULT_STOCK
from prompt  import SYSTEM_PROMPT, VISION_SYSTEM_PROMPT, build_stage2_prompt, build_image_analysis_prompt
from prompt_pdd import build_pdd_prompt, PDD_ATTR_OPTIONS
from coze_workflow import run_workflow, WORKFLOWS, WORKFLOW_LABELS
from prompt_video import (build_video_script_prompt, VIDEO_SCRIPT_SYSTEM_PROMPT,
                           parse_two_scripts, build_premium_script_prompt, VIDEO_PREMIUM_SYSTEM_PROMPT)
from listing      import save_product, list_products, load_product_base, save_listing, list_listings
from cozedaihuo   import run_video_workflow
from video_gen    import create_video, query_task, download_video, POLL_TIMEOUT, POLL_INTERVAL, FINAL_STATUSES, SAVE_DIR
from image_gen    import generate_shot_images, GPTIMAGE2_MODELS, BANANA_MODELS
from prompt_pdd   import (build_zhutu_prompts_llm, build_xiangxitu_prompts,
                          ZHUTU_SYSTEM_PROMPT)


# ══════════════════════════════════════════════
# Session State
# ══════════════════════════════════════════════

def init_state():
    if "product"      not in st.session_state:
        st.session_state.product      = empty_product()
    if "stage"        not in st.session_state:
        st.session_state.stage        = 1
    if "ai_generated" not in st.session_state:
        st.session_state.ai_generated = False
    if "ai_raw_error" not in st.session_state:
        st.session_state.ai_raw_error = ""


# ══════════════════════════════════════════════
# on_change 回调
# ══════════════════════════════════════════════

def _s1(field):
    st.session_state.product["stage1"][field] = st.session_state[f"s1_{field}"]

def _s2(field):
    st.session_state.product["stage2"][field] = st.session_state[f"s2_{field}"]

def _s2_list(field, widget_key):
    raw = st.session_state.get(widget_key, "")
    st.session_state.product["stage2"][field] = [
        x.strip() for x in raw.replace("，", ",").split(",") if x.strip()
    ]

def _selling_point(idx):
    pts = st.session_state.product["stage2"]["selling_points"]
    while len(pts) <= idx:
        pts.append("")
    pts[idx] = st.session_state.get(f"s2_sp_{idx}", "")


# ══════════════════════════════════════════════
# 阶段一：基础字段
# ══════════════════════════════════════════════

def render_stage1():
    s1 = st.session_state.product["stage1"]

    # ── 商品存档快速操作 ──
    products = list_products()
    pc1, pc2, pc3 = st.columns([4, 1, 1])
    with pc1:
        if products:
            opts = {f"{p['name']} ({p['saved_at'][:16]})": p["path"] for p in products}
            sel  = st.selectbox("选择已有商品", ["（新建）"] + list(opts.keys()),
                                key="s1_prod_sel", label_visibility="collapsed")
            if sel != "（新建）" and st.button("📂 加载", key="s1_load"):
                base = load_product_base(opts[sel])
                st.session_state.product["stage1"] = base["stage1"]
                st.session_state.product["stage2"] = base["stage2"]
                st.session_state.ai_generated = bool(base["stage2"].get("title_core"))
                st.success("已加载")
                st.rerun()
        else:
            st.caption("暂无存档")
    with pc2:
        if st.button("💾 保存", key="s1_save_top"):
            try:
                save_product(st.session_state.product)
                st.success("已保存")
            except Exception as e:
                st.error(str(e))
    with pc3:
        if st.button("🗑 新建", key="s1_new"):
            from ziduan import empty_product
            st.session_state.product = empty_product()
            st.session_state.ai_generated = False
            st.rerun()

    st.divider()

    # ── 类目 ──
    st.subheader("类目")
    cat_idx = CATEGORY_OPTIONS.index(s1["category"]) if s1["category"] in CATEGORY_OPTIONS else len(CATEGORY_OPTIONS) - 1
    st.selectbox("产品类目 *", CATEGORY_OPTIONS, index=cat_idx,
                 key="s1_category", on_change=_s1, args=("category",))
    if s1["category"] == "其他（自定义）":
        st.text_input("自定义类目名称", key="s1_category_custom",
                      on_change=lambda: st.session_state.product["stage1"].__setitem__(
                          "category", st.session_state.s1_category_custom))

    # ── 目标平台类目（与阶段三串联）──
    from pathlib import Path as _PL
    pdd_cats = []
    maps_dir = _PL(__file__).parent / "platform_maps" / "pdd"
    if maps_dir.exists():
        import json as _json
        for f in sorted(maps_dir.glob("*.json")):
            try:
                d = _json.loads(f.read_text(encoding="utf-8"))
                pdd_cats.append(d.get("category", f.stem))
            except Exception:
                pass

    if pdd_cats:
        cur_cat = s1.get("target_category", pdd_cats[0])
        idx = pdd_cats.index(cur_cat) if cur_cat in pdd_cats else 0
        s1["target_category"] = st.selectbox(
            "目标上架类目（用于阶段三自动填表）",
            pdd_cats, index=idx, key="s1_target_category",
        )
    else:
        st.caption("暂无已录入类目，请在阶段三录入")

    st.divider()

    # ── 产品基本信息 ──
    st.subheader("产品基本信息")
    c1, c2 = st.columns(2)
    with c1:
        st.text_input("产品名称（中文）*", value=s1["name_zh"],
                      key="s1_name_zh", on_change=_s1, args=("name_zh",))
        st.text_input("材质", value=s1["material"], placeholder="如：PU皮 / 真皮 / 帆布",
                      key="s1_material", on_change=_s1, args=("material",))
        st.text_input("货号前缀（选填）", value=s1["sku_prefix"],
                      placeholder="如：BAG，用于自动生成货号",
                      key="s1_sku_prefix", on_change=_s1, args=("sku_prefix",))
    with c2:
        st.text_input("产品名称（英文）", value=s1["name_en"],
                      key="s1_name_en", on_change=_s1, args=("name_en",))
        st.text_input("品牌（无则留空）", value=s1["brand"],
                      key="s1_brand", on_change=_s1, args=("brand",))
        st.selectbox("包装方式", ["单件", "套装", "礼盒", "袋装"],
                     index=["单件","套装","礼盒","袋装"].index(s1["packaging"])
                           if s1["packaging"] in ["单件","套装","礼盒","袋装"] else 0,
                     key="s1_packaging", on_change=_s1, args=("packaging",))

    st.markdown("**尺寸（cm）& 重量**")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.text_input("长", value=s1["size_l"], key="s1_size_l", on_change=_s1, args=("size_l",))
    with c2: st.text_input("宽", value=s1["size_w"], key="s1_size_w", on_change=_s1, args=("size_w",))
    with c3: st.text_input("高", value=s1["size_h"], key="s1_size_h", on_change=_s1, args=("size_h",))
    with c4: st.text_input("重量(g)", value=s1["weight_g"], key="s1_weight_g", on_change=_s1, args=("weight_g",))

    st.divider()

    # ── SKU 规格轴配置 ──
    st.subheader("SKU 规格设置")

    ca, cb, cc = st.columns([2, 2, 2])
    with ca:
        s1["sku_axis1_name"] = st.text_input(
            "第一规格轴名称", value=s1.get("sku_axis1_name","颜色"),
            key="s1_axis1_name", placeholder="如：颜色")
    with cb:
        s1["sku_axis2_name"] = st.text_input(
            "第二规格轴名称（留空=只有一轴）", value=s1.get("sku_axis2_name",""),
            key="s1_axis2_name", placeholder="如：尺寸/款式")
    with cc:
        s1["pin_price_diff"] = st.text_input(
            "拼单价 = 单买价 - N元", value=s1.get("pin_price_diff","1"),
            key="s1_pin_diff", placeholder="1")

    # 第二轴值（和第一轴一样，逐行填写）
    if s1.get("sku_axis2_name"):
        axis2_name = s1["sku_axis2_name"]
        axis2_vals = s1.get("sku_axis2_values", [])

        st.markdown(f"**{axis2_name}列表**")
        # 表头
        ah1, ah2 = st.columns([3, 1])
        ah1.markdown(f"**{axis2_name}**")
        ah2.markdown("**删除**")

        new_axis2 = []
        for j, val in enumerate(axis2_vals):
            ac1, ac2 = st.columns([3, 1])
            with ac1:
                new_val = st.text_input(
                    axis2_name, value=val, key=f"axis2_val_{j}",
                    label_visibility="collapsed", placeholder=f"如：S / M / L",
                )
                new_axis2.append(new_val)
            with ac2:
                if st.button("🗑", key=f"axis2_del_{j}"):
                    axis2_vals.pop(j)
                    st.rerun()

        if st.button(f"＋ 添加{axis2_name}", key="axis2_add"):
            axis2_vals.append("")
            st.rerun()

        s1["sku_axis2_values"] = new_axis2
    else:
        s1["sku_axis2_values"] = []

    st.divider()

    # ── 第一轴行表格 ──
    axis1_label = s1.get("sku_axis1_name","颜色")
    st.subheader(f"{axis1_label}款式（每行含图片和单买价）")
    st.caption(f"货号留空则不填，库存留空默认 {DEFAULT_STOCK}，拼单价自动 = 单买价 - {s1.get('pin_price_diff','1')}元")

    rows = s1["sku_rows"]

    # 表头
    h1, h2, h3, h4, h5, h6, h7 = st.columns([2, 1.5, 3, 2, 1.5, 1.5, 0.8])
    h1.markdown(f"**{axis1_label}**")
    h2.markdown("**SKU图**")
    h3.markdown("**参考图集 + 合成**")
    h4.markdown("**货号**")
    h5.markdown("**单买价(¥)**")
    h6.markdown(f"**库存**（空={DEFAULT_STOCK}）")
    h7.markdown("**删除**")

    for i, row in enumerate(rows):
        # 确保新字段存在（兼容旧数据）
        row.setdefault("sku_image", None)
        row.setdefault("composite", "")

        c1, c2, c3, c4, c5, c6, c7 = st.columns([2, 1.5, 3, 2, 1.5, 1.5, 0.8])

        with c1:
            new_val = st.text_input(
                axis1_label, value=row["color"], key=f"sku_color_{i}",
                label_visibility="collapsed", placeholder="如：黑色",
            )
            if new_val != row["color"]:
                row["color"] = new_val
                prefix = s1.get("sku_prefix","")
                if prefix and (not row["sku_code"] or row["sku_code"].startswith(prefix)):
                    from ziduan import COLOR_MAP
                    c_code = COLOR_MAP.get(new_val, new_val[:3].upper() if new_val else "")
                    row["sku_code"] = f"{prefix}-{c_code}" if c_code else ""

        with c2:
            # SKU预览图（单张，平台上架用）
            sku_up = st.file_uploader(
                "SKU图", type=["png","jpg","jpeg","webp"],
                key=f"sku_single_{i}", label_visibility="collapsed",
            )
            if sku_up:
                row["sku_image"] = sku_up.read()
            if row["sku_image"]:
                st.image(row["sku_image"], width=50)

        with c3:
            # 参考图集（多张，AI生成用）
            refs_up = st.file_uploader(
                "参考图集", type=["png","jpg","jpeg","webp"],
                accept_multiple_files=True,
                key=f"sku_img_{i}", label_visibility="collapsed",
            )
            if refs_up:
                row["images"] = [f.read() for f in refs_up]
            if row["images"]:
                st.caption(f"📷 {len(row['images'])} 张参考图")
                # 生成合成参考图按钮
                if st.button("🔍 生成合成图", key=f"sku_composite_{i}"):
                    with st.spinner("生成中..."):
                        try:
                            import tempfile, os
                            from image_gen import generate_shot_images
                            # 把 bytes 写到临时文件
                            tmp_paths = []
                            for j, b in enumerate(row["images"]):
                                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                                tmp.write(b); tmp.close()
                                tmp_paths.append(tmp.name)
                            prompt = (f"{row['color']}款{s1.get('name_zh','')}，"
                                      "多视角细节合成，展示正面侧面背面及细节特写，"
                                      "白色背景，电商产品摄影，高清真实质感")
                            paths = generate_shot_images(
                                prompts=[prompt],
                                ref_chars=tmp_paths,
                                ref_scene=None,
                                upload_server=os.getenv("PT_IMAGE_RELAY_BASE_URL", ""),
                                backend="banana",
                                model="nano-banana-pro",
                                size="1:1",
                            )
                            for p in tmp_paths:
                                try: os.unlink(p)
                                except: pass
                            if paths and paths[0]:
                                row["composite"] = paths[0]
                                st.rerun()
                            else:
                                st.error("生成失败，请重试")
                        except Exception as e:
                            st.error(f"生成失败：{e}")
            # 上传或显示合成图
            comp_up = st.file_uploader(
                "上传合成图", type=["png","jpg","jpeg","webp"],
                key=f"sku_comp_up_{i}", label_visibility="collapsed",
            )
            if comp_up:
                import tempfile
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                tmp.write(comp_up.read()); tmp.close()
                row["composite"] = tmp.name
            if row["composite"]:
                try:
                    st.image(row["composite"], caption="合成参考图", width=80)
                except Exception:
                    st.caption(f"✅ {row['composite']}")

        with c4:
            row["sku_code"] = st.text_input(
                "货号", value=row["sku_code"], key=f"sku_code_{i}",
                label_visibility="collapsed", placeholder="留空则不填",
            )

        with c5:
            row["price"] = st.text_input(
                "单买价", value=row["price"], key=f"sku_price_{i}",
                label_visibility="collapsed", placeholder="如：89.00",
            )
            if row["price"]:
                try:
                    diff = float(s1.get("pin_price_diff","1"))
                    pin  = round(max(float(row["price"]) - diff, 0), 2)
                    st.caption(f"拼单价：¥{pin}")
                except Exception:
                    pass

        with c6:
            row["stock"] = st.text_input(
                "库存", value=row["stock"], key=f"sku_stock_{i}",
                label_visibility="collapsed", placeholder=str(DEFAULT_STOCK),
            )

        with c7:
            if st.button("🗑", key=f"sku_del_{i}", help="删除此行"):
                rows.pop(i)
                st.rerun()

    if st.button(f"＋ 添加{axis1_label}"):
        rows.append(make_sku_row("", s1.get("sku_prefix","")))
        st.rerun()

    # SKU 矩阵预览（有第二轴时展示）
    if s1.get("sku_axis2_name") and s1.get("sku_axis2_values") and rows:
        with st.expander(f"SKU 矩阵预览（{axis1_label}×{s1['sku_axis2_name']}）"):
            matrix = build_sku_matrix(s1)
            st.dataframe(
                [{
                    s1["sku_axis1_name"]: m["axis1"],
                    s1["sku_axis2_name"]: m["axis2"],
                    "单买价(¥)": m["price"],
                    "拼单价(¥)": m["pin_price"],
                    "库存":      m["stock"],
                } for m in matrix],
                use_container_width=True, hide_index=True,
            )

    st.divider()

    # ── 供应链 ──
    st.subheader("供应链 & 服务")
    c1, c2 = st.columns(2)
    with c1:
        st.text_input("发货地（省市）*", value=s1["ship_from"], placeholder="如：广东省广州市",
                      key="s1_ship_from", on_change=_s1, args=("ship_from",))
        st.selectbox("发货时效", ["当日发", "24h", "48h", "72h"],
                     index=["当日发","24h","48h","72h"].index(s1["ship_time"])
                           if s1["ship_time"] in ["当日发","24h","48h","72h"] else 1,
                     key="s1_ship_time", on_change=_s1, args=("ship_time",))
        st.text_input("公司 / 卖家名", value=s1["company"],
                      key="s1_company", on_change=_s1, args=("company",))
    with c2:
        st.selectbox("退货政策", ["7天无理由退换", "运费险", "不支持退换"],
                     index=["7天无理由退换","运费险","不支持退换"].index(s1["return_policy"])
                           if s1["return_policy"] in ["7天无理由退换","运费险","不支持退换"] else 0,
                     key="s1_return_policy", on_change=_s1, args=("return_policy",))
        st.text_input("认证 / 合规（选填）", value=s1["certification"],
                      placeholder="CE / FCC / RoHS",
                      key="s1_certification", on_change=_s1, args=("certification",))
        st.selectbox("运费模板", ["默认包邮", "偏远加收", "自定义"],
                     key="s1_freight_template", on_change=_s1, args=("freight_template",))

    st.divider()

    # ── 下一步校验 ──
    c_save, c_next = st.columns([1, 3])
    with c_save:
        if st.button("💾 保存商品"):
            try:
                p = save_product(st.session_state.product)
                st.success(f"已保存")
            except Exception as e:
                st.error(str(e))
    with c_next:
        pass
    if st.button("下一步：AI 生成详细字段 →", type="primary", use_container_width=True):
        missing = []
        if not s1["category"]:           missing.append("产品类目")
        if not s1["name_zh"]:            missing.append("产品名称（中文）")
        if not s1["ship_from"]:          missing.append("发货地")
        if not s1["sku_rows"]:           missing.append("至少添加一个颜色款式")
        has_price = any(r["price"] for r in s1["sku_rows"])
        if not has_price:                missing.append("至少填写一个 SKU 价格")
        if missing:
            st.error(f"请填写：{'、'.join(missing)}")
        else:
            st.session_state.stage = 2
            st.session_state.ai_generated = False
            st.rerun()


# ══════════════════════════════════════════════
# 阶段二：AI 生成详细字段
# ══════════════════════════════════════════════

def render_stage2():
    s1 = st.session_state.product["stage1"]
    s2 = st.session_state.product["stage2"]

    # ── 识图区（有图才显示，优先合成图，其次参考图集）──
    import os as _os2
    all_images = []
    all_filenames = []
    for row in s1["sku_rows"]:
        if row.get("composite") and _os2.path.exists(row["composite"]):
            all_images.append(open(row["composite"], "rb").read())
            all_filenames.append(f"{row['color']}_composite.jpg")
        else:
            for j, img_bytes in enumerate(row.get("images", [])):
                all_images.append(img_bytes)
                all_filenames.append(f"{row['color']}_{j}.png")

    if all_images and not s2.get("image_impression"):
        st.info(f"检测到 {len(all_images)} 张实拍图，可先让 AI 分析图片提升文案质量。")
        if st.button("🔍 AI 分析实拍图", use_container_width=True):
            with st.spinner("识图分析中..."):
                try:
                    impression = call_llm_vision_json(
                        user_prompt=build_image_analysis_prompt(),
                        images=all_images,
                        system_prompt=VISION_SYSTEM_PROMPT,
                        filenames=all_filenames,
                    )
                    s2["image_impression"] = impression
                    st.rerun()
                except ValueError as e:
                    st.error("识图结果解析失败")
                    with st.expander("查看原始输出"):
                        st.text(str(e))
                except Exception as e:
                    st.error(f"识图失败：{e}")

    # 显示识图结果摘要
    if s2.get("image_impression"):
        imp = s2["image_impression"]
        with st.expander("📷 图片分析结果（点击展开/收起）", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                if imp.get("colors_detected"):
                    st.write(f"**识别颜色**：{'、'.join(imp['colors_detected'])}")
                if imp.get("material_guess"):
                    st.write(f"**材质判断**：{imp['material_guess']}")
                if imp.get("style_tags"):
                    st.write(f"**风格标签**：{'、'.join(imp['style_tags'])}")
            with c2:
                if imp.get("texture_detail"):
                    st.write(f"**质感细节**：{imp['texture_detail']}")
                if imp.get("hardware_detail"):
                    st.write(f"**五金细节**：{imp['hardware_detail']}")
                if imp.get("structure_detail"):
                    st.write(f"**结构细节**：{imp['structure_detail']}")
            if st.button("🔄 重新识图"):
                s2["image_impression"] = {}
                st.rerun()

    st.divider()

    # ── AI 文案生成区 ──
    if not st.session_state.ai_generated:
        impression = s2.get("image_impression") or None
        has_imp = bool(impression)
        st.info(
            f"将根据「{s1['category']} · {s1['name_zh']}」"
            f"{'+ 实拍图分析 ' if has_imp else ''}"
            f"生成详细字段。"
        )
        if st.button("🤖 一键 AI 生成", type="primary", use_container_width=True):
            with st.spinner("AI 生成中，约 30-60 秒..."):
                try:
                    data = call_llm_json(
                        build_stage2_prompt(s1, impression),
                        SYSTEM_PROMPT,
                    )
                    for field in OUTPUT_FIELDS["str"]:
                        if field in data:
                            s2[field] = str(data[field])
                    for field in OUTPUT_FIELDS["list"]:
                        if field in data and isinstance(data[field], list):
                            s2[field] = data[field]
                    st.session_state.ai_generated = True
                    st.session_state.ai_raw_error = ""
                    st.rerun()
                except ValueError as e:
                    st.session_state.ai_raw_error = str(e)
                    st.error("AI 返回内容无法解析为 JSON")
                    with st.expander("查看原始输出"):
                        st.text(st.session_state.ai_raw_error)
                except Exception as e:
                    st.error(f"网络或接口错误：{e}")
        return

    if st.session_state.ai_raw_error:
        with st.expander("上次生成有解析错误"):
            st.text(st.session_state.ai_raw_error)

    # ── SKU 汇总（只读展示）──
    st.subheader("SKU 汇总")
    sku_display = []
    for row in s1["sku_rows"]:
        sku_display.append({
            "颜色":   row["color"],
            "货号":   row["sku_code"] or "—",
            "价格(¥)": row["price"],
            "库存":   row["stock"] or str(DEFAULT_STOCK),
            "图片数": len(row.get("images", [])),
        })
    st.dataframe(sku_display, use_container_width=True, hide_index=True)

    st.divider()

    # ── 文案 ──
    st.subheader("文案")
    st.text_input("核心标题（60字内）", value=s2["title_core"],
                  key="s2_title_core", on_change=_s2, args=("title_core",))

    st.markdown("**产品卖点（5条）**")
    pts = s2["selling_points"]
    while len(pts) < 5: pts.append("")
    for i in range(5):
        st.text_input(f"卖点 {i+1}", value=pts[i], key=f"s2_sp_{i}",
                      on_change=_selling_point, args=(i,), label_visibility="visible")

    st.text_area("详细描述（300-500字）", value=s2["description"], height=160,
                 key="s2_description", on_change=_s2, args=("description",))

    c1, c2 = st.columns(2)
    with c1:
        st.text_input("使用场景（逗号分隔）", value="，".join(s2["use_scenes"]),
                      key="s2_use_scenes",
                      on_change=_s2_list, args=("use_scenes", "s2_use_scenes"))
        st.text_area("差异化优势", value=s2["differentiation"], height=100,
                     key="s2_differentiation", on_change=_s2, args=("differentiation",))
    with c2:
        st.text_area("详情页结构规划", value=s2["detail_page_structure"], height=100,
                     key="s2_detail_page_structure", on_change=_s2, args=("detail_page_structure",))
        st.text_area("注意事项 / 售后说明", value=s2["after_sale_notes"], height=100,
                     key="s2_after_sale_notes", on_change=_s2, args=("after_sale_notes",))

    st.divider()

    # ── SEO ──
    st.subheader("SEO / 搜索索引")
    c1, c2 = st.columns(2)
    with c1:
        st.text_input("核心关键词（逗号分隔，5-10个）", value="，".join(s2["keywords_core"]),
                      key="s2_keywords_core",
                      on_change=_s2_list, args=("keywords_core", "s2_keywords_core"))
        st.text_input("长尾关键词（逗号分隔，10-20个）", value="，".join(s2["keywords_longtail"]),
                      key="s2_keywords_longtail",
                      on_change=_s2_list, args=("keywords_longtail", "s2_keywords_longtail"))
    with c2:
        st.text_area("后台搜索词（不展示给买家）", value=s2["keywords_backend"], height=80,
                     key="s2_keywords_backend", on_change=_s2, args=("keywords_backend",))
        st.text_input("适用人群标签（逗号分隔）", value="，".join(s2["target_audience"]),
                      key="s2_target_audience",
                      on_change=_s2_list, args=("target_audience", "s2_target_audience"))

    st.divider()

    # ── 底部操作 ──
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("← 返回基础字段"):
            st.session_state.stage = 1
            st.rerun()
    with c2:
        if st.button("🔄 重新 AI 生成"):
            st.session_state.ai_generated = False
            st.rerun()
    with c3:
        if st.button("📥 导出 JSON"):
            st.session_state.show_export = not st.session_state.get("show_export", False)
    with c4:
        if st.button("下一步：平台适配 →", type="primary"):
            st.session_state.stage = 3
            st.rerun()

    if st.session_state.get("show_export"):
        # 导出时 sku_rows 去掉 images（bytes不可序列化），stock补默认值
        export_data = {
            "stage1": {**st.session_state.product["stage1"],
                       "sku_rows": export_sku_rows(s1["sku_rows"])},
            "stage2": {k: v for k, v in s2.items() if k != "image_impression"},
        }
        payload = json.dumps(export_data, ensure_ascii=False, indent=2)
        st.code(payload, language="json")
        st.download_button("⬇ 下载 product_data.json", data=payload,
                           file_name="product_data.json", mime="application/json")


# ══════════════════════════════════════════════
# 阶段三：平台适配
# ══════════════════════════════════════════════

PLATFORM_OPTIONS = {"拼多多": "pdd"}


def _get_available_categories(platform_key: str) -> list[str]:
    """从 platform_maps/{platform}/ 目录读取已录入的类目列表。"""
    import json
    from pathlib import Path
    maps_dir = Path(__file__).parent / "platform_maps" / platform_key
    if not maps_dir.exists():
        return []
    categories = []
    for f in sorted(maps_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            categories.append(data.get("category", f.stem))
        except Exception:
            pass
    return categories


def _load_field_map_by_category(platform_key: str, category: str) -> dict | None:
    """根据类目全名读取字段定义。"""
    from platform_maps.capture import load_field_map
    return load_field_map(platform_key, category)


def render_stage3():
    s1 = st.session_state.product["stage1"]
    s2 = st.session_state.product["stage2"]
    s3 = st.session_state.product["stage3"]

    # ── 平台选择 ──
    st.subheader("平台 & 类目")
    platform_labels = list(PLATFORM_OPTIONS.keys())
    cur_label = next((k for k, v in PLATFORM_OPTIONS.items() if v == s3["platform"]), platform_labels[0])
    chosen_label = st.radio("平台", platform_labels, index=platform_labels.index(cur_label),
                            horizontal=True, label_visibility="collapsed")
    chosen_key = PLATFORM_OPTIONS[chosen_label]
    if chosen_key != s3["platform"]:
        s3["platform"]                = chosen_key
        s3["pdd"]["generated"]        = False
        s3["pdd"]["form_generated"]   = False
        s3["pdd"]["filled_form"]      = {}

    # ── 类目选择（优先读阶段一的 target_category，可手动覆盖）──
    available_cats = _get_available_categories(chosen_key)

    if not available_cats:
        st.warning("暂无已录入的类目，请上传平台表单截图录入新类目。")
        _render_capture_new(chosen_key)
        return

    cat_options = available_cats + ["➕ 录入新类目（上传截图）"]

    # 优先用阶段一设置的目标类目
    s1_target = s1.get("target_category", "")
    cur_cat   = s3.get("pdd_category") or (s1_target if s1_target in available_cats else available_cats[0])

    chosen_cat = st.selectbox(
        "选择类目", cat_options,
        index=cat_options.index(cur_cat) if cur_cat in cat_options else 0,
        key="s3_category_select",
    )

    if chosen_cat == "➕ 录入新类目（上传截图）":
        _render_capture_new(chosen_key)
        return

    if chosen_cat != s3.get("pdd_category"):
        s3["pdd_category"]          = chosen_cat
        s3["pdd"]["generated"]      = False
        s3["pdd"]["form_generated"] = False
        s3["pdd"]["filled_form"]    = {}
        s3["pdd"]["field_values"]   = {}

    st.caption(f"当前类目：`{chosen_cat}`")
    col_new, _ = st.columns([1, 3])
    with col_new:
        if st.button("➕ 录入新类目", key="s3_new_cat_btn"):
            st.session_state.show_capture = not st.session_state.get("show_capture", False)
    if st.session_state.get("show_capture"):
        _render_capture_new(chosen_key)
    st.divider()

    # ── 加载字段定义 ──
    field_map = _load_field_map_by_category(chosen_key, chosen_cat)
    if not field_map:
        st.error(f"字段定义文件读取失败，请重新录入类目。")
        return

    if chosen_key == "pdd":
        _render_pdd(s1, s2, s3, field_map)


def _render_capture_new(platform_key: str):
    """录入新类目：上传截图 → 识图提取字段 → 保存。"""
    st.subheader("录入新类目")
    st.caption("上传平台发布商品的表单截图，AI 自动提取字段定义并保存。")

    new_cat = st.text_input("类目全名（如：箱包皮具/女包/男包 > 女包 > 单肩包）",
                             key="new_cat_name")
    uploaded = st.file_uploader("上传表单截图", type=["png","jpg","jpeg"],
                                 key="new_cat_img")

    if uploaded and new_cat:
        if st.button("🔍 识图提取字段", type="primary"):
            with st.spinner("识图中..."):
                try:
                    from platform_maps.capture import capture_fields_from_image
                    img_bytes = uploaded.read()
                    result = capture_fields_from_image(img_bytes, platform_key, new_cat, uploaded.name)
                    field_count = sum(len(s.get("fields",[])) for s in result.get("sections",[]))
                    st.success(f"✅ 提取成功！共 {field_count} 个字段，已保存为「{new_cat}」")
                    st.rerun()
                except Exception as e:
                    st.error(f"识图失败：{e}")
    elif uploaded and not new_cat:
        st.warning("请先填写类目全名")


def _render_pdd(s1, s2, s3, field_map: dict):
    from prompt_pdd import build_pdd_form_prompt, FORM_FILL_SYSTEM_PROMPT
    pdd = s3["pdd"]

    # ── 强制初始化新字段，清除旧版干扰 ──
    if "form_generated" not in pdd:
        pdd["form_generated"] = False
    if "filled_form" not in pdd:
        pdd["filled_form"] = {}
    # generated 是旧字段，不再使用，强制忽略
    # 只看 form_generated

    # ══ 第一步：AI 一键填写表单 ══
    if not pdd["form_generated"]:
        st.info(f"AI 将根据阶段一、二的内容，按照「{field_map.get('category','')}」类目表单1:1填写所有字段。")
        if st.button("🤖 AI 一键填写表单", type="primary", use_container_width=True):
            with st.spinner("AI 填写中，约 20-40 秒..."):
                try:
                    prompt = build_pdd_form_prompt(s1, s2, pdd, field_map)
                    data   = call_llm_json(prompt, FORM_FILL_SYSTEM_PROMPT)
                    pdd["filled_form"]    = data
                    pdd["form_generated"] = True
                    st.rerun()
                except ValueError as e:
                    st.error("AI 返回内容解析失败")
                    with st.expander("查看原始输出"):
                        st.text(str(e))
                except Exception as e:
                    st.error(f"接口错误：{e}")
        return

    # ══ 第二步：展示并允许用户修改 ══
    filled = pdd["filled_form"]

    for section in field_map.get("sections", []):
        sec_name = section["name"]
        fields   = [f for f in section.get("fields", [])
                    if f.get("type") not in ("upload",)]

        if not fields:
            continue

        st.subheader(sec_name)

        if sec_name == "规格与库存":
            # SKU 表格
            _render_pdd_sku(s1, pdd)
            st.divider()
            continue

        if sec_name == "服务与承诺":
            # 服务字段（radio/checkbox）
            for field in fields:
                if field["type"] == "sku_axis":
                    continue
                fname    = field["name"]
                ftype    = field["type"]
                required = field.get("required", False)
                label    = fname + (" *" if required else "")
                cur_val  = filled.get(fname, "")

                if ftype == "radio":
                    options = field.get("options", [])
                    # 没有值时用 default
                    if not cur_val:
                        cur_val = field.get("default", options[0] if options else "")
                    idx = options.index(cur_val) if cur_val in options else 0
                    filled[fname] = st.radio(label, options, index=idx,
                                             horizontal=True, key=f"pdd_f_{fname}")
                elif ftype == "checkbox":
                    default_val = field.get("default", False)
                    filled[fname] = st.checkbox(label,
                                                value=bool(cur_val) if cur_val != "" else default_val,
                                                key=f"pdd_f_{fname}")
                else:
                    filled[fname] = st.text_input(label, value=str(cur_val),
                                                   key=f"pdd_f_{fname}")
            st.divider()
            continue

        # 基本信息：分四类渲染
        # 1. select → 三列下拉
        # 2. 普通text（非全宽）→ 两列输入
        # 3. 全宽text（搜索关键词等长字段）→ 全宽
        # 4. richtext → 全宽文本框
        FULLWIDTH_TEXT = {"搜索关键词", "商品货号", "品牌"}  # 这些全宽展示

        select_fields   = [f for f in fields if f["type"] == "select"]
        fullwidth_text  = [f for f in fields if f["type"] == "text" and f["name"] in FULLWIDTH_TEXT]
        normal_text     = [f for f in fields if f["type"] in ("text","number") and f["name"] not in FULLWIDTH_TEXT]
        rich_fields     = [f for f in fields if f["type"] == "richtext"]

        # select 三列
        if select_fields:
            cols = st.columns(3)
            for idx, field in enumerate(select_fields):
                fname    = field["name"]
                options  = ["（请选择）"] + field.get("options", [])
                required = field.get("required", False)
                label    = fname + (" *" if required else "")
                cur_val  = filled.get(fname, "")
                cur_idx  = options.index(cur_val) if cur_val in options else 0
                with cols[idx % 3]:
                    sel = st.selectbox(label, options, index=cur_idx, key=f"pdd_f_{fname}")
                    filled[fname] = "" if sel == "（请选择）" else sel

        # 普通text 两列
        if normal_text:
            left_col, right_col = st.columns(2)
            for idx, field in enumerate(normal_text):
                fname    = field["name"]
                required = field.get("required", False)
                max_len  = field.get("max_length")
                cur_val  = filled.get(fname, "")
                if isinstance(cur_val, list):
                    cur_val = "，".join(cur_val)
                cur_val = str(cur_val)
                label = fname + (" *" if required else "")
                if max_len:
                    label += f"（{len(cur_val)}/{max_len}字）"
                col = left_col if idx % 2 == 0 else right_col
                with col:
                    val = st.text_input(label, value=cur_val, key=f"pdd_f_{fname}")
                    filled[fname] = val
                    if max_len and len(val) > max_len:
                        st.warning(f"{fname} 超出 {max_len} 字限制")

        # 全宽text（搜索关键词等）
        for field in fullwidth_text:
            fname    = field["name"]
            required = field.get("required", False)
            max_len  = field.get("max_length")
            cur_val  = filled.get(fname, "")
            if isinstance(cur_val, list):
                cur_val = "，".join(cur_val)
            cur_val = str(cur_val)
            label = fname + (" *" if required else "")
            if max_len:
                label += f"（{len(cur_val)}/{max_len}字）"
            val = st.text_input(label, value=cur_val, key=f"pdd_f_{fname}")
            filled[fname] = val

        # richtext 全宽
        for field in rich_fields:
            fname    = field["name"]
            required = field.get("required", False)
            cur_val  = str(filled.get(fname, ""))
            label    = fname + (" *" if required else "")
            filled[fname] = st.text_area(label, value=cur_val, height=200,
                                          key=f"pdd_f_{fname}")

        st.divider()

    # ── 缺失必填字段提示 ──
    missing = []
    for section in field_map.get("sections", []):
        for field in section.get("fields", []):
            if field.get("required") and field["type"] not in ("upload","sku_axis"):
                fname = field["name"]
                if not filled.get(fname):
                    missing.append(fname)
    if missing:
        st.warning(f"以下必填字段未填写：{'、'.join(missing)}")

    # ── 底部操作 ──
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("← 返回详细字段"):
            st.session_state.stage = 2
            st.rerun()
    with c2:
        if st.button("🔄 重新 AI 填写"):
            pdd["form_generated"] = False
            pdd["filled_form"]    = {}
            st.rerun()
    with c3:
        if st.button("💾 保存上架数据"):
            try:
                p = save_listing(st.session_state.product, s3)
                st.success(f"已保存")
            except Exception as e:
                st.error(str(e))
    with c4:
        if st.button("下一步：图片生成 →", type="primary"):
            st.session_state.stage = 4
            st.rerun()

    if st.session_state.get("show_s3_export"):
        export_data = {
            "stage1": {**s1, "sku_rows": export_sku_rows(s1["sku_rows"])},
            "stage2": {k: v for k, v in st.session_state.product["stage2"].items()
                       if k != "image_impression"},
            "stage3": s3,
        }
        payload = json.dumps(export_data, ensure_ascii=False, indent=2)
        st.code(payload, language="json")
        st.download_button("⬇ 下载 product_data.json", data=payload,
                           file_name="product_data.json", mime="application/json")


def _render_pdd_sku(s1: dict, pdd: dict):
    """渲染 SKU 规格与库存表格，使用 build_sku_matrix 生成。"""
    filled   = pdd["filled_form"]
    matrix   = build_sku_matrix(s1)
    axis1    = s1.get("sku_axis1_name","颜色")
    axis2    = s1.get("sku_axis2_name","")
    has_ax2  = bool(axis2 and s1.get("sku_axis2_values"))

    # 初始化或重建（行数变化时重建）
    if "sku_matrix" not in filled or len(filled["sku_matrix"]) != len(matrix):
        filled["sku_matrix"] = [
            {
                axis1:    m["axis1"],
                axis2:    m["axis2"],
                "规格编码": m["sku_code"],
                "单买价":  m["price"],
                "拼单价":  m["pin_price"],
                "库存":    m["stock"],
            }
            for m in matrix
        ]

    st.caption(f"拼单价 = 单买价 - {s1.get('pin_price_diff','1')}元（可单独修改）")

    # 表头
    col_widths = [2, 2, 2, 1.5, 1.5, 1.5, 1] if has_ax2 else [2, 2, 1.5, 1.5, 1.5, 1]
    headers    = ([axis1, axis2] if has_ax2 else [axis1]) + ["规格编码","单买价(¥)","拼单价(¥)","库存","状态"]
    h_cols = st.columns(col_widths)
    for col, label in zip(h_cols, headers):
        col.markdown(f"**{label}**")

    for i, sku in enumerate(filled["sku_matrix"]):
        cols = st.columns(col_widths)
        ci = 0
        with cols[ci]: st.text_input(axis1, value=sku[axis1], disabled=True,
                                      key=f"s3_sk_a1_{i}", label_visibility="collapsed")
        ci += 1
        if has_ax2:
            with cols[ci]: st.text_input(axis2, value=sku.get(axis2,""), disabled=True,
                                          key=f"s3_sk_a2_{i}", label_visibility="collapsed")
            ci += 1
        with cols[ci]: sku["规格编码"] = st.text_input("规格编码", value=sku["规格编码"],
                                                         key=f"s3_sk_code_{i}", label_visibility="collapsed")
        ci += 1
        with cols[ci]: sku["单买价"] = st.text_input("单买价", value=sku["单买价"],
                                                        key=f"s3_sk_single_{i}", label_visibility="collapsed")
        ci += 1
        with cols[ci]: sku["拼单价"] = st.text_input("拼单价", value=sku["拼单价"],
                                                        key=f"s3_sk_pin_{i}", label_visibility="collapsed")
        ci += 1
        with cols[ci]: sku["库存"]   = st.text_input("库存", value=str(sku["库存"]),
                                                        key=f"s3_sk_stock_{i}", label_visibility="collapsed")
        ci += 1
        with cols[ci]: st.markdown("✅")


def _render_capture_new(platform_key: str):
    """录入新类目：上传截图 → 识图提取字段 → 保存。"""
    st.subheader("录入新类目")
    st.caption("上传平台发布商品的表单截图，AI 自动提取字段定义并保存。")

    new_cat = st.text_input("类目全名（如：箱包皮具/女包/男包 > 女包 > 单肩包）",
                             key="new_cat_name")
    uploaded = st.file_uploader("上传表单截图", type=["png","jpg","jpeg"],
                                 key="new_cat_img")

    if uploaded and new_cat:
        if st.button("🔍 识图提取字段", type="primary"):
            with st.spinner("识图中..."):
                try:
                    from platform_maps.capture import capture_fields_from_image
                    img_bytes = uploaded.read()
                    result = capture_fields_from_image(img_bytes, platform_key, new_cat, uploaded.name)
                    field_count = sum(len(s.get("fields",[])) for s in result.get("sections",[]))
                    st.success(f"✅ 提取成功！共 {field_count} 个字段，已保存为「{new_cat}」")
                    st.rerun()
                except Exception as e:
                    st.error(f"识图失败：{e}")
    elif uploaded and not new_cat:
        st.warning("请先填写类目全名")



# ══════════════════════════════════════════════
# 阶段四：图片生成
# ══════════════════════════════════════════════

RATIO_OPTIONS  = ["1:1", "3:4", "4:3", "9:16", "16:9"]
ENGINE_OPTIONS = ["sora", "banana"]
UPLOAD_SERVER  = os.getenv("PT_IMAGE_RELAY_BASE_URL", "")


def _init_stage4_sku(s1: dict, s4: dict):
    existing = {item["color"]: item for item in s4["sku_main_images"]}
    new_list = []
    for row in s1["sku_rows"]:
        color = row["color"]
        if color in existing:
            new_list.append(existing[color])
        else:
            new_list.append({
                "color":       color,
                "engine":      "sora",
                "status":      "idle",
                "image_paths": [],
                "image_urls":  [],
            })
    s4["sku_main_images"] = new_list


def _save_ref_images(sku_row: dict) -> list[str]:
    """
    返回参考图路径列表。
    优先用 composite（合成参考图），没有则把 images bytes 写临时文件。
    """
    import tempfile, os
    # 优先用合成参考图
    if sku_row.get("composite") and os.path.exists(sku_row["composite"]):
        return [sku_row["composite"]]
    # fallback：把 images bytes 写临时文件
    paths = []
    for img_bytes in sku_row.get("images", []):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.write(img_bytes); tmp.close()
        paths.append(tmp.name)
    return paths


def render_stage4():
    s1 = st.session_state.product["stage1"]
    s2 = st.session_state.product["stage2"]
    s4 = st.session_state.product["stage4"]
    imp = s2.get("image_impression") or {}

    _init_stage4_sku(s1, s4)
    product_name = s1.get("name_zh", "")

    # ── 全局设置 ──
    st.subheader("图片生成设置")
    c1, c2, c3 = st.columns(3)
    with c1:
        ratio_idx  = RATIO_OPTIONS.index(s4["ratio"]) if s4["ratio"] in RATIO_OPTIONS else 1
        s4["ratio"] = st.selectbox("详情图比例", RATIO_OPTIONS, index=ratio_idx, key="s4_ratio")
    with c2:
        engine_idx = ENGINE_OPTIONS.index(s4.get("engine","sora")) if s4.get("engine","sora") in ENGINE_OPTIONS else 0
        s4["engine"] = st.selectbox("生图引擎", ENGINE_OPTIONS, index=engine_idx, key="s4_engine",
                                    help="sora=即梦  banana=纳米香蕉")
    with c3:
        wenan = st.text_input("主图海报文案（选填，如：HOT SALE）",
                              value=s4.get("wenan",""), key="s4_wenan",
                              placeholder="留空则自动发挥")
        s4["wenan"] = wenan

    st.divider()

    # ══ 主图 ══
    st.subheader("主图生成（按颜色，每色5张）")

    for i, item in enumerate(s4["sku_main_images"]):
        color = item["color"]
        sku_row = next((r for r in s1["sku_rows"] if r["color"] == color), {})
        import os as _os3
        has_images = (bool(sku_row.get("images")) or
                      bool(sku_row.get("composite") and _os3.path.exists(sku_row.get("composite",""))))

        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 2, 4])

            with c1:
                st.markdown(f"**{color}**")
                if sku_row.get("composite") and _os3.path.exists(sku_row.get("composite","")):
                    st.caption("✅ 合成参考图")
                elif sku_row.get("images"):
                    st.caption(f"📷 {len(sku_row['images'])} 张实拍图")
                else:
                    st.caption("❌ 无图片")

            with c2:
                if has_images:
                    btn_label = "▶ 生成主图" if item["status"] != "running" else "⏳ 生成中..."
                    if st.button(btn_label, key=f"s4_main_{i}",
                                 disabled=(item["status"] == "running"), type="primary"):
                        item["status"] = "running"
                        st.rerun()

                    if item["status"] == "running":
                        with st.spinner(f"正在生成 {color} 主图（共5张）..."):
                            try:
                                # 1. LLM 生成5条提示词
                                from llm import call_llm_json
                                prompt_user = build_zhutu_prompts_llm(s1, s2, imp, s4.get("wenan",""))
                                prompts = call_llm_json(prompt_user, ZHUTU_SYSTEM_PROMPT)
                                if isinstance(prompts, dict):
                                    # 有时模型返回 {"prompts": [...]}
                                    prompts = next(iter(prompts.values()))
                                prompts = [str(p) for p in prompts if p]

                                # 2. 把实拍图写到本地作参考
                                ref_paths = _save_ref_images(sku_row)

                                # 3. 生图
                                paths = generate_shot_images(
                                    prompts       = prompts,
                                    ref_chars     = ref_paths,
                                    ref_scene     = None,
                                    upload_server = UPLOAD_SERVER,
                                    backend       = s4["engine"],
                                    model         = "gpt-image-2" if s4["engine"]=="sora" else "nano-banana",
                                    size          = "1:1",
                                )
                                item["image_paths"] = [p for p in paths if p]
                                item["status"]      = "done"
                                st.rerun()
                            except Exception as e:
                                item["status"] = "error"
                                item["error"]  = str(e)
                                st.rerun()
                else:
                    st.caption("请先上传实拍图")

            with c3:
                if item["status"] == "done" and item["image_paths"]:
                    st.caption(f"✅ {len(item['image_paths'])} 张")
                    cols = st.columns(min(len(item["image_paths"]), 5))
                    for j, path in enumerate(item["image_paths"][:5]):
                        with cols[j]:
                            try:    st.image(path, use_column_width=True)
                            except: st.caption(f"图{j+1}")
                elif item["status"] == "error":
                    st.error(item.get("error","生成失败")[:200])
                    if st.button("重试", key=f"s4_main_retry_{i}"):
                        item["status"] = "idle"
                        st.rerun()

    st.divider()

    # ══ 详情图 ══
    st.subheader(f"详情图生成（12张，比例 {s4['ratio']}）")

    detail = s4["detail_images"]
    import os as _os4
    first_row = next(
        (r for r in s1["sku_rows"]
         if (r.get("composite") and _os4.path.exists(r["composite"])) or r.get("images")),
        None
    )

    c1, c2 = st.columns([3, 5])
    with c1:
        if first_row:
            btn_label = "▶ 生成详情图" if detail["status"] != "running" else "⏳ 生成中..."
            if st.button(btn_label, key="s4_detail_run",
                         disabled=(detail["status"] == "running"), type="primary"):
                detail["status"] = "running"
                st.rerun()

            if detail["status"] == "running":
                with st.spinner("正在生成12张详情图..."):
                    try:
                        # 1. 直接拼接12条提示词
                        prompts = build_xiangxitu_prompts(s1, s2, imp)

                        # 2. 参考图（用第一个有图的颜色）
                        ref_paths = _save_ref_images(first_row)

                        # 3. 生图
                        paths = generate_shot_images(
                            prompts       = prompts,
                            ref_chars     = ref_paths,
                            ref_scene     = None,
                            upload_server = UPLOAD_SERVER,
                            backend       = s4["engine"],
                            model         = "gpt-image-2" if s4["engine"]=="sora" else "nano-banana",
                            size          = s4["ratio"],
                        )
                        detail["image_paths"] = [p for p in paths if p]
                        detail["status"]      = "done"
                        st.rerun()
                    except Exception as e:
                        detail["status"] = "error"
                        detail["error"]  = str(e)
                        st.rerun()
        else:
            st.caption("请先在阶段一上传任意颜色的实拍图")

        if detail["status"] == "error":
            st.error(detail.get("error","生成失败")[:200])
            if st.button("重试详情图"):
                detail["status"] = "idle"
                st.rerun()

    with c2:
        if detail["status"] == "done" and detail["image_paths"]:
            st.caption(f"✅ {len(detail['image_paths'])} 张")
            cols_per_row = 4
            paths = detail["image_paths"]
            for row_start in range(0, len(paths), cols_per_row):
                thumb_cols = st.columns(cols_per_row)
                for j, path in enumerate(paths[row_start:row_start+cols_per_row]):
                    with thumb_cols[j]:
                        try:    st.image(path, use_column_width=True)
                        except: st.caption(f"图{row_start+j+1}")

    st.divider()

    # ── 底部操作 ──
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("← 返回平台适配"):
            st.session_state.stage = 3
            st.rerun()
    with c2:
        if st.button("下一步：带货视频 →", type="primary"):
            st.session_state.stage = 5
            st.rerun()
    with c3:
        if st.button("📥 导出完整 JSON", key="s4_export_btn"):
            st.session_state.show_s4_export = not st.session_state.get("show_s4_export", False)

    if st.session_state.get("show_s4_export"):
        s4_export = {
            "ratio":           s4["ratio"],
            "engine":          s4["engine"],
            "sku_main_images": [
                {k: v for k, v in item.items() if k != "error"}
                for item in s4["sku_main_images"]
            ],
            "detail_images": {k: v for k, v in detail.items() if k != "error"},
        }
        export_data = {
            "stage1": {**s1, "sku_rows": export_sku_rows(s1["sku_rows"])},
            "stage2": {k: v for k, v in s2.items() if k != "image_impression"},
            "stage3": st.session_state.product["stage3"],
            "stage4": s4_export,
        }
        payload = json.dumps(export_data, ensure_ascii=False, indent=2)
        st.code(payload, language="json")
        st.download_button("⬇ 下载 product_data.json", data=payload,
                           file_name="product_data.json", mime="application/json")



# ══════════════════════════════════════════════
# 阶段五：带货视频
# ══════════════════════════════════════════════

def render_stage5():
    s1 = st.session_state.product["stage1"]
    s2 = st.session_state.product["stage2"]
    s5 = st.session_state.product["stage5"]

    tab1, tab2 = st.tabs(["🎬 普通带货（2×10秒）", "✨ 精品带货（15秒）"])
    with tab2:
        _render_premium_video(s1, s2)
    with tab1:
        _render_normal_video(s1, s2, s5)


def _render_premium_video(s1, s2):
    from llm import call_llm
    import os as _osp
    s5 = st.session_state.product["stage5"]
    s5.setdefault("premium_video_status", "idle")
    s5.setdefault("premium_video_urls",   [])
    s5.setdefault("premium_video_paths",  [])

    # ── 上半：15秒口播文案 ──
    st.subheader("精品带货文案（15秒）")
    if "premium_script" not in st.session_state:
        st.session_state.premium_script = ""
    if st.button("🤖 生成15秒精品文案", type="primary"):
        with st.spinner("生成中..."):
            try:
                st.session_state.premium_script = call_llm(
                    build_premium_script_prompt(s1, s2), VIDEO_PREMIUM_SYSTEM_PROMPT)
                st.rerun()
            except Exception as e:
                st.error(f"生成失败：{e}")
    if st.session_state.premium_script:
        st.session_state.premium_script = st.text_area(
            "精品带货文案（可编辑）",
            value=st.session_state.premium_script, height=200, key="premium_script_area")

    st.divider()

    # ── 下半：精致带货视频（coze工作流）──
    st.subheader("精致带货视频")
    st.caption("使用合成图 + 卖点 + 产品名，调用 AI 工作流生成")

    # 找合成图
    composite_bytes = None
    composite_color = ""
    for row in s1["sku_rows"]:
        if row.get("composite") and _osp.path.exists(row["composite"]):
            composite_bytes = open(row["composite"], "rb").read()
            composite_color = row["color"]
            break

    if not composite_bytes:
        st.warning("请先在阶段一生成合成图")
    else:
        st.caption(f"参考图：{composite_color}（合成图）")
        maidian = "；".join(s2.get("selling_points", [])[:3])
        name    = s1.get("name_zh", "")
        st.caption(f"卖点：{maidian}")
        st.caption(f"产品名：{name}")

        if s5["premium_video_status"] == "idle":
            if st.button("🎬 生成精致带货视频", type="primary", use_container_width=True):
                s5["premium_video_status"] = "running"
                st.rerun()

        if s5["premium_video_status"] == "running":
            with st.spinner("精致视频生成中，约需 2-5 分钟..."):
                try:
                    result = run_video_workflow(
                        image_bytes = composite_bytes,
                        maidian     = maidian,
                        filename    = f"{composite_color}_composite.jpg",
                        name        = name,
                    )
                    s5["premium_video_urls"]  = result["video_urls"]
                    s5["premium_video_paths"] = result["video_paths"]
                    s5["premium_video_status"] = "done"
                    st.rerun()
                except Exception as e:
                    s5["premium_video_status"] = "error"
                    st.error(f"生成失败：{e}")

        if s5["premium_video_status"] == "done":
            st.success(f"✅ 生成 {len(s5['premium_video_paths'])} 个视频")
            for path in s5["premium_video_paths"]:
                try:    st.video(path)
                except: st.caption(path)
            if st.button("🔄 重新生成精致视频", key="premium_retry"):
                s5["premium_video_status"] = "idle"
                s5["premium_video_urls"]   = []
                s5["premium_video_paths"]  = []
                st.rerun()

        if s5["premium_video_status"] == "error":
            if st.button("🔄 重试", key="premium_retry_err"):
                s5["premium_video_status"] = "idle"
                st.rerun()


def _render_normal_video(s1, s2, s5):
    import time, subprocess, os as _os
    from llm import call_llm

    # ── 选图 ──
    st.subheader("选择参考图")
    all_imgs = []
    for row in s1["sku_rows"]:
        if row.get("composite") and _os.path.exists(row["composite"]):
            all_imgs.append({"color": row["color"], "label": f"{row['color']}（合成图）",
                              "bytes": open(row["composite"], "rb").read()})
        elif row.get("images"):
            for j, b in enumerate(row["images"]):
                all_imgs.append({"color": row["color"], "label": f"{row['color']} 参考图{j+1}",
                                  "img_idx": j, "bytes": b})

    if not all_imgs:
        st.warning("请先在阶段一上传实拍图或生成合成图")
        return

    selected_keys = {i.get("label","") for i in s5["selected_images"]}
    cols = st.columns(min(len(all_imgs), 5))
    new_selected = []
    for i, img in enumerate(all_imgs):
        with cols[i % 5]:
            st.image(img["bytes"], caption=img["label"], use_column_width=True)
            if st.checkbox("选", key=f"s5_sel_{i}", value=(img["label"] in selected_keys)):
                new_selected.append(img)
    s5["selected_images"] = new_selected

    st.divider()

    # ── 生成脚本 ──
    st.subheader("口播文案")
    if st.button("🤖 生成两段口播文案", type="primary"):
        with st.spinner("生成中..."):
            try:
                raw = call_llm(build_video_script_prompt(s1, s2), VIDEO_SCRIPT_SYSTEM_PROMPT)
                s5["script1"], s5["script2"] = parse_two_scripts(raw)
                s5["script_status"] = "done"
                st.rerun()
            except Exception as e:
                st.error(f"生成失败：{e}")

    if s5.get("script1"):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**视频1：外观/材质/颜值**")
            s5["script1"] = st.text_area("视频1脚本", value=s5["script1"], height=180,
                                          key="s5_sc1", label_visibility="collapsed")
        with c2:
            st.markdown("**视频2：场景/功能/痛点**")
            s5["script2"] = st.text_area("视频2脚本", value=s5["script2"], height=180,
                                          key="s5_sc2", label_visibility="collapsed")

    st.divider()

    # ── 生成视频 ──
    st.subheader("生成带货视频")
    if not s5.get("script1"):
        st.info("请先生成口播文案")
    elif not new_selected:
        st.info("请先选择参考图")
    else:
        img_bytes = new_selected[0].get("bytes")
        img_name  = new_selected[0].get("label", "ref").replace(" ", "_") + ".jpg"

        if s5["video_status"] == "idle":
            if st.button("🎬 生成两段视频", type="primary", use_container_width=True):
                if not img_bytes:
                    st.error("图片数据丢失")
                else:
                    with st.spinner("提交任务..."):
                        try:
                            s5["task_id1"] = create_video(s5["script1"], img_bytes, img_name)
                            s5["task_id2"] = create_video(s5["script2"], img_bytes, img_name)
                            s5["video_status"] = "running"
                            st.rerun()
                        except Exception as e:
                            st.error(f"提交失败：{e}")

        if s5["video_status"] == "running":
            st.info(f"任务1：`{s5['task_id1']}`  任务2：`{s5['task_id2']}`")
            prog_map = {"pending":10,"image_downloading":20,"video_generating":50,
                        "video_generation_completed":70,"video_upsampling":85,
                        "video_upsampling_completed":95,"completed":100}
            bar1, bar2 = st.empty(), st.empty()
            with st.spinner("视频生成中..."):
                done1 = done2 = False
                for _ in range(POLL_TIMEOUT):
                    time.sleep(POLL_INTERVAL)
                    try:
                        if not done1:
                            d1 = query_task(s5["task_id1"])
                            st1 = d1.get("status","")
                            bar1.progress(prog_map.get(st1,5), text=f"视频1：{st1}")
                            if st1 == "completed":
                                s5["path1"] = download_video(d1["video_url"]); done1 = True
                            elif st1 in FINAL_STATUSES:
                                done1 = True
                        if not done2:
                            d2 = query_task(s5["task_id2"])
                            st2 = d2.get("status","")
                            bar2.progress(prog_map.get(st2,5), text=f"视频2：{st2}")
                            if st2 == "completed":
                                s5["path2"] = download_video(d2["video_url"]); done2 = True
                            elif st2 in FINAL_STATUSES:
                                done2 = True
                    except Exception as e:
                        st.warning(f"查询异常：{e}")
                    if done1 and done2:
                        if s5["path1"] and s5["path2"]:
                            from pathlib import Path as _Path
                            merged   = str(_Path(SAVE_DIR) / "merged_video.mp4")
                            listfile = str(_Path(SAVE_DIR) / "concat_list.txt")
                            try:
                                p1, p2 = s5["path1"], s5["path2"]
                                lines = ["file '" + p1 + "'", "file '" + p2 + "'"]
                                with open(listfile, "w") as lf:
                                    lf.write("".join(lines))

                                subprocess.run([
                                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                                    "-i", listfile,
                                    "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                                    "-c:v", "libx264", "-preset", "fast",
                                    "-c:a", "aac", "-ar", "44100", merged
                                ], check=True, capture_output=True)
                                s5["merged_path"] = merged
                            except Exception as e:
                                st.warning(f"拼接失败：{e}")
                        s5["video_status"] = "done"
                        st.rerun()
                        break
                else:
                    st.warning("轮询超时")

        if s5["video_status"] == "done":
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**视频1**")
                if s5.get("path1"):
                    try: st.video(s5["path1"])
                    except: st.caption(s5["path1"])
            with c2:
                st.markdown("**视频2**")
                if s5.get("path2"):
                    try: st.video(s5["path2"])
                    except: st.caption(s5["path2"])
            if s5.get("merged_path"):
                st.markdown("**合并视频（20秒）**")
                try: st.video(s5["merged_path"])
                except: st.caption(s5["merged_path"])
            if st.button("🔄 重新生成"):
                for k in ("task_id1","task_id2","path1","path2","merged_path"):
                    s5[k] = ""
                s5["video_status"] = "idle"
                st.rerun()

    st.divider()
    with st.expander("🔍 手动查询任务"):
        mid = st.text_input("任务ID", key="s5_mid")
        if st.button("查询", key="s5_q"):
            if mid:
                data = query_task(mid)
                st.json(data)
                if data.get("video_url"):
                    st.video(data["video_url"])

    if st.button("← 返回图片生成"):
        st.session_state.stage = 4
        st.rerun()


# ══════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════

def main():
    st.set_page_config(page_title="跨境电商系统", page_icon="🛍️", layout="wide")
    init_state()

    st.title("🛍️ 多平台跨境电商 · 商品录入")

    # ── 存档加载区 ──
    with st.expander("📂 商品存档 / 上架数据", expanded=False):
        tab_prod, tab_listing, tab_export = st.tabs(["📦 商品存档", "📋 上架存档", "💾 导出"])

        with tab_prod:
            # 保存当前商品
            if st.button("💾 保存当前商品", type="primary"):
                try:
                    p = save_product(st.session_state.product)
                    st.success(f"已保存：{p}")
                except Exception as e:
                    st.error(f"保存失败：{e}")
            st.divider()
            # 加载已有商品
            products = list_products()
            if products:
                opts = {f"{p['name']} ({p['saved_at'][:16]})": p["path"] for p in products}
                sel  = st.selectbox("加载商品存档", list(opts.keys()), key="prod_select")
                if st.button("✅ 加载商品"):
                    try:
                        base = load_product_base(opts[sel])
                        # 合并到当前 product（保留 stage3-5）
                        st.session_state.product["stage1"] = base["stage1"]
                        st.session_state.product["stage2"] = base["stage2"]
                        st.session_state.ai_generated = bool(base["stage2"].get("title_core"))
                        st.success("商品已加载，实拍图需重新上传")
                        st.rerun()
                    except Exception as e:
                        st.error(f"加载失败：{e}")
            else:
                st.caption("暂无商品存档")

        with tab_listing:
            listings = list_listings()
            if listings:
                opts2 = {f"{l['product_name']} · {l['platform']} · {l['category']} ({l['saved_at'][:16]})": l["path"]
                         for l in listings}
                sel2  = st.selectbox("上架存档", list(opts2.keys()), key="listing_select")
                if st.button("✅ 查看上架数据"):
                    from listing import load_listing
                    data = load_listing(opts2[sel2])
                    st.json(data)
            else:
                st.caption("暂无上架存档，在阶段三生成后可保存")

        with tab_export:
            # 旧版完整导出（JSON文件）
            uploaded_json = st.file_uploader("上传 product_data.json 恢复", type="json",
                                              key="json_uploader", label_visibility="collapsed")
            if uploaded_json and st.button("✅ 确认恢复"):
                try:
                    product = load_product(uploaded_json.read().decode("utf-8"))
                    st.session_state.product      = product
                    st.session_state.ai_generated = bool(product["stage2"].get("title_core"))
                    st.success("已恢复！")
                    st.rerun()
                except ValueError as e:
                    st.error(f"失败：{e}")
            if st.button("📥 导出完整 JSON", key="s5_export_btn"):
                payload = export_product(st.session_state.product)
                st.download_button("⬇ 下载", data=payload,
                                   file_name="product_data.json", mime="application/json",
                                   key="top_export_btn")

    # ── 一键生成区 ──
    with st.expander("🚀 一键生成全流程", expanded=False):
        s1 = st.session_state.product["stage1"]
        s2 = st.session_state.product["stage2"]
        import os as _osq

        # 前置检查
        checks = []
        checks.append(("产品名", bool(s1.get("name_zh"))))
        checks.append(("目标类目", bool(s1.get("target_category"))))
        has_composite = any(
            r.get("composite") and _osq.path.exists(r["composite"])
            for r in s1.get("sku_rows", [])
        )
        has_img = has_composite or any(r.get("images") for r in s1.get("sku_rows", []))
        checks.append(("合成图或参考图", has_img))

        cc = st.columns(len(checks))
        all_ok = True
        for i, (label, ok) in enumerate(checks):
            with cc[i]:
                st.markdown(f"{'✅' if ok else '⚠️'} {label}")
            if not ok:
                all_ok = False

        if not all_ok:
            st.warning("请先完成阶段一：填写产品名、选择目标类目、上传参考图")
        else:
            gen_video = st.checkbox("同时生成带货视频", value=True, key="onestep_video")
            if st.button("🚀 开始一键生成", type="primary", use_container_width=True):
                import threading
                from llm import call_llm_json, call_llm_vision_json, call_llm

                prog   = st.progress(0)
                status = st.empty()
                errors = []

                # ── 工具函数 ──────────────────────────────────────
                def get_ref_img():
                    """取第一张合成图或参考图，返回 (bytes, filename)"""
                    for row in s1["sku_rows"]:
                        if row.get("composite") and _osq.path.exists(row["composite"]):
                            return open(row["composite"],"rb").read(), f"{row['color']}.jpg"
                        elif row.get("images"):
                            return row["images"][0], f"{row['color']}.jpg"
                    return None, None

                # ── ① 识图（带30秒超时，失败跳过）────────────────
                status.info("① 识图分析（最多30秒，超时跳过）...")
                if not s2.get("image_impression"):
                    imgs, fnames = [], []
                    for row in s1["sku_rows"]:
                        if row.get("composite") and _osq.path.exists(row["composite"]):
                            imgs.append(open(row["composite"],"rb").read())
                            fnames.append(f"{row['color']}_composite.jpg")
                        else:
                            for j, b in enumerate(row.get("images",[])):
                                imgs.append(b); fnames.append(f"{row['color']}_{j}.png")
                    if imgs:
                        imp_result = {}
                        def _do_vision():
                            try:
                                imp_result["data"] = call_llm_vision_json(
                                    build_image_analysis_prompt(), imgs,
                                    VISION_SYSTEM_PROMPT, fnames)
                            except Exception as e:
                                imp_result["error"] = str(e)
                        t = threading.Thread(target=_do_vision, daemon=True)
                        t.start(); t.join(timeout=30)
                        if "data" in imp_result:
                            s2["image_impression"] = imp_result["data"]
                prog.progress(12)

                # ── ② 生成 stage2 ────────────────────────────────
                status.info("② 生成产品详细字段...")
                try:
                    data = call_llm_json(build_stage2_prompt(s1, s2.get("image_impression")), SYSTEM_PROMPT)
                    for f in OUTPUT_FIELDS["str"]:
                        if f in data: s2[f] = str(data[f])
                    for f in OUTPUT_FIELDS["list"]:
                        if f in data and isinstance(data[f], list): s2[f] = data[f]
                    st.session_state.ai_generated = True
                except Exception as e:
                    errors.append(f"stage2: {e}")
                prog.progress(25)

                # ── ③ 平台表单 ───────────────────────────────────
                status.info("③ AI 填写平台表单...")
                s3  = st.session_state.product["stage3"]
                cat = s1.get("target_category","")
                if cat:
                    try:
                        field_map = _load_field_map_by_category("pdd", cat)
                        if field_map:
                            from prompt_pdd import build_pdd_form_prompt, FORM_FILL_SYSTEM_PROMPT
                            pdd = s3["pdd"]
                            pdd["filled_form"]    = call_llm_json(
                                build_pdd_form_prompt(s1, s2, pdd, field_map), FORM_FILL_SYSTEM_PROMPT)
                            pdd["form_generated"] = True
                            s3["platform"]        = "pdd"
                            s3["pdd_category"]    = cat
                    except Exception as e:
                        errors.append(f"表单: {e}")
                prog.progress(38)

                # ── ④⑤ 主图 + 详情图并发 ────────────────────────
                status.info("④⑤ 并发生成主图 + 详情图...")
                s4  = st.session_state.product["stage4"]
                _init_stage4_sku(s1, s4)
                imp = s2.get("image_impression") or {}
                from prompt_pdd import build_zhutu_prompts_llm, ZHUTU_SYSTEM_PROMPT, build_xiangxitu_prompts
                engine    = s4.get("engine","gptimage2")
                model_str = "gpt-image-2" if engine == "gptimage2" else "nano-banana"

                def _gen_main():
                    for item in s4["sku_main_images"]:
                        sku_row = next((r for r in s1["sku_rows"] if r["color"]==item["color"]),{})
                        ref_paths = _save_ref_images(sku_row)
                        if not ref_paths: continue
                        try:
                            prompts = call_llm_json(
                                build_zhutu_prompts_llm(s1, s2, imp, s4.get("wenan","")), ZHUTU_SYSTEM_PROMPT)
                            if isinstance(prompts, dict): prompts = next(iter(prompts.values()))
                            prompts = [str(p) for p in prompts if p]
                            paths = generate_shot_images(
                                prompts=prompts, ref_chars=ref_paths, ref_scene=None,
                                upload_server=UPLOAD_SERVER, backend=engine,
                                model=model_str, size="1:1")
                            item["image_paths"] = [p for p in paths if p]
                            item["status"]      = "done"
                        except Exception as e:
                            item["status"] = "error"; item["error"] = str(e)

                first_row = next((r for r in s1["sku_rows"]
                                  if (r.get("composite") and _osq.path.exists(r.get("composite","")))
                                  or r.get("images")), None)
                def _gen_detail():
                    if not first_row: return
                    try:
                        prompts   = build_xiangxitu_prompts(s1, s2, imp)
                        ref_paths = _save_ref_images(first_row)
                        paths = generate_shot_images(
                            prompts=prompts, ref_chars=ref_paths, ref_scene=None,
                            upload_server=UPLOAD_SERVER, backend=engine,
                            model=model_str, size=s4.get("ratio","3:4"))
                        s4["detail_images"]["image_paths"] = [p for p in paths if p]
                        s4["detail_images"]["status"]      = "done"
                    except Exception as e:
                        s4["detail_images"]["status"] = "error"
                        errors.append(f"详情图: {e}")

                # 主图+详情图串行（内部已并发，避免API限流）
                status.info("④ 生成主图...")
                _gen_main()
                prog.progress(58)
                status.info("⑤ 生成详情图...")
                _gen_detail()
                prog.progress(70)

                # ── ⑥⑦ 两种视频并发 ─────────────────────────────
                if gen_video:
                    status.info("⑥⑦ 并发提交普通带货视频 + 精致带货视频...")
                    s5 = st.session_state.product["stage5"]
                    ref_bytes, ref_name = get_ref_img()

                    def _gen_normal():
                        if not ref_bytes: return
                        try:
                            raw = call_llm(build_video_script_prompt(s1, s2), VIDEO_SCRIPT_SYSTEM_PROMPT)
                            s5["script1"], s5["script2"] = parse_two_scripts(raw)
                            s5["task_id1"]     = create_video(s5["script1"], ref_bytes, ref_name)
                            s5["task_id2"]     = create_video(s5["script2"], ref_bytes, ref_name)
                            s5["video_status"] = "running"
                        except Exception as e:
                            errors.append(f"普通视频: {e}")

                    def _gen_premium():
                        if not ref_bytes: return
                        try:
                            result = run_video_workflow(
                                image_bytes = ref_bytes,
                                maidian     = "；".join(s2.get("selling_points",[])[:3]),
                                filename    = ref_name,
                                name        = s1.get("name_zh",""),
                            )
                            s5["premium_video_urls"]   = result["video_urls"]
                            s5["premium_video_paths"]  = result["video_paths"]
                            s5["premium_video_status"] = "done"
                        except Exception as e:
                            errors.append(f"精致视频: {e}")

                    t_normal  = threading.Thread(target=_gen_normal,  daemon=True)
                    t_premium = threading.Thread(target=_gen_premium, daemon=True)
                    t_normal.start();  t_premium.start()
                    t_normal.join();   t_premium.join()
                prog.progress(100)

                save_product(st.session_state.product)
                if errors:
                    status.warning(f"完成（部分失败）：{'；'.join(errors)}")
                else:
                    status.success("✅ 全流程完成！点击导航栏查看各阶段结果")

    STAGES = ["阶段一：基础字段", "阶段二：AI 详细字段", "阶段三：平台适配", "阶段四：图片生成", "阶段五：带货视频"]
    cur = st.session_state.stage
    cols = st.columns(len(STAGES))
    for i, (col, label) in enumerate(zip(cols, STAGES)):
        n = i + 1
        if n == cur:
            col.button(f"▶ {label}", key=f"nav_{n}", disabled=True,
                       use_container_width=True, type="primary")
        else:
            if col.button(label, key=f"nav_{n}", use_container_width=True):
                st.session_state.stage = n
                st.rerun()

    st.progress(cur / len(STAGES))
    st.divider()

    if cur == 1:
        render_stage1()
    elif cur == 2:
        render_stage2()
    elif cur == 3:
        render_stage3()
    elif cur == 4:
        render_stage4()
    elif cur == 5:
        render_stage5()


if __name__ == "__main__":
    main()
