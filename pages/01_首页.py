"""首页 — 仪表盘"""
import os
import streamlit as st
from engine.config import ConfigManager
from engine.cache import CacheManager

st.title("🏠 物业合同分析智能体")
st.markdown("分析成都市天府新区物业合同，对比服务质量和价格")

# 数据状态
data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
cache_dir = os.path.join(data_dir, "cache")
standards_path = os.path.join(data_dir, "standards.xlsx")
meta_path = os.path.join(data_dir, "contracts_meta.xlsx")
contracts_dir = os.path.join(data_dir, "contracts")

config_path = os.path.join(data_dir, "config.json")
cache_mgr = CacheManager(cache_dir)
cfg = ConfigManager(config_path)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("📋 规范标准", "已就绪" if os.path.exists(standards_path) else "缺失")
with col2:
    pdf_count = len([f for f in os.listdir(contracts_dir) if f.endswith(".pdf")]) \
        if os.path.exists(contracts_dir) else 0
    st.metric("📄 合同PDF", f"{pdf_count} 份" if pdf_count else "缺失")
with col3:
    st.metric("📊 合同元数据", "已就绪" if os.path.exists(meta_path) else "缺失")
with col4:
    is_cached = cache_mgr.is_valid()
    st.metric("💾 缓存状态", "有效" if is_cached else "未初始化")

st.markdown("---")

# 快捷入口
st.subheader("快速开始")
qcol1, qcol2, qcol3 = st.columns(3)

with qcol1:
    st.page_link("pages/03_同价不同质.py", label="📊 同价不同质", icon="⚖️")
    st.caption("对比两个价格相近合同的物业服务差异")

with qcol2:
    st.page_link("pages/04_同质不同价.py", label="📊 同质不同价", icon="🔍")
    st.caption("批量分析找价格异常楼盘")

with qcol3:
    st.page_link("pages/05_满足率计算.py", label="📈 满足率计算", icon="📋")
    st.caption("计算合同对五级规范的满足率")

st.markdown("---")

# 数据初始化区域
st.subheader("⚡ 数据初始化")
st.info(
    "首次使用需初始化数据缓存。此操作将解析 PDF 合同、执行规则匹配和 LLM 判定，"
    "预计耗时 10-15 分钟，之后分析秒级响应。"
)

if st.button("🔄 初始化/刷新数据缓存", type="primary", use_container_width=True):
    config = cfg.load()

    if not config["llm"].get("api_key"):
        st.error("请先在「模型供应商配置」页面设置 API Key")
    else:
        with st.status("正在初始化...", expanded=True) as status:
            # 用于跟踪各步骤状态的容器
            step_containers = {}
            step_keys_order = ["step1", "step2", "step3", "step4"]

            # 初始化步骤显示
            progress_placeholder = st.empty()

            def on_progress(key: str, message: str):
                """接收 preprocess 的进度回调"""
                # 查找或创建该步骤的消息容器
                if key not in step_containers:
                    # 为新步骤创建区域
                    step_icons = {
                        "step1": "📋 步骤 1/4: 加载规范标准和合同元数据",
                        "step2": "📄 步骤 2/4: 解析 PDF 合同",
                        "step3": "⚙️ 步骤 3/4: 执行规则匹配",
                        "step4": "🤖 步骤 4/4: LLM 语义判定",
                    }
                    header = step_icons.get(key, key)
                    step_containers[key] = st.container()
                    with step_containers[key]:
                        st.markdown(f"**{header}**")
                        step_containers[f"{key}_log"] = st.empty()

                # 更新日志
                if f"{key}_log" in step_containers:
                    # 收集该步骤的所有消息
                    if f"{key}_messages" not in step_containers:
                        step_containers[f"{key}_messages"] = []
                    step_containers[f"{key}_messages"].append(message)
                    # 只显示最近5条
                    recent = step_containers[f"{key}_messages"][-5:]
                    step_containers[f"{key}_log"].markdown(
                        "\n".join(f"- {m}" for m in recent)
                    )

                # 整体进度条
                completed = sum(1 for k in step_keys_order
                               if k in step_containers and f"{k}_messages" in step_containers
                               and any("✅ 缓存写入完成" in m for m in step_containers.get(f"{k}_messages", [])))
                if completed < 1:
                    # 粗略进度
                    active_steps = len([k for k in step_keys_order if k in step_containers])
                    progress_pct = min(active_steps / len(step_keys_order), 0.99)
                    progress_placeholder.progress(progress_pct, f"已完成 {active_steps}/4 阶段")

            try:
                from engine.preprocess import run_preprocessing
                stats = run_preprocessing(data_dir, config, on_progress=on_progress)
                progress_placeholder.progress(1.0, "初始化完成！")
                status.update(label="初始化完成！", state="complete")
                st.success(
                    f"✅ {stats['contracts_loaded']} 份合同加载，"
                    f"{stats['pdfs_processed']} 份 PDF 处理，"
                    f"{stats['clauses_extracted']} 条服务条款提取，"
                    f"{stats['results_cached']} 份结果缓存"
                )
                st.rerun()
            except Exception as e:
                status.update(label="初始化失败", state="error")
                st.error(f"❌ 初始化失败: {e}")

# ── 数据概览（缓存有效时显示） ──
if cache_mgr.is_valid():
    st.markdown("---")
    st.subheader("📊 数据概览")

    contracts = cache_mgr.get_contracts()
    results = cache_mgr.load_results()
    from engine.loader import load_standards
    standards = load_standards(standards_path) if os.path.exists(standards_path) else []
    metadata = cache_mgr.get_metadata()

    # 总览指标
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("📋 规范条款", f"{len(standards)} 条")
    with m2:
        st.metric("📄 合同", f"{len(contracts)} 份")
    with m3:
        total_clauses = sum(len(c.service_clauses) for c in contracts)
        contracts_with_clauses = sum(1 for c in contracts if c.service_clauses)
        st.metric("📝 提取条款", f"{total_clauses} 条",
                  delta=f"{contracts_with_clauses}/{len(contracts)} 份PDF已解析" if contracts else None)
    with m4:
        last_cached = metadata.get("cached_at", "未知")
        st.metric("🕐 缓存时间", last_cached[:16] if last_cached else "未知")

    st.markdown("---")

    # 合同卡片
    st.subheader("📑 合同解析详情")
    for contract in contracts:
        with st.expander(f"🏢 {contract.property_name}", expanded=len(contracts) <= 2):
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"**甲方**: {contract.party_a or '—'}")
                st.markdown(f"**乙方**: {contract.party_b or '—'}")
                st.markdown(f"**位置**: {contract.location or '—'}")
                st.markdown(f"**类型**: {contract.property_type or '—'} | "
                           f"**面积**: {contract.building_area} ㎡")
            with col_b:
                st.markdown(f"**住宅物业费**: {contract.residential_fee} 元/月·㎡")
                st.markdown(f"**商业物业费**: {contract.commercial_fee} 元/月·㎡")
                st.markdown(f"**车位费**: {contract.parking_fee} 元/月·个")
                st.markdown(f"**声明等级**: {contract.service_level_declared or '未声明'}")
                st.markdown(f"**源文件**: {contract.source_pdf or '—'}")

            # 服务条款一览
            if contract.service_clauses:
                st.markdown(f"**📝 服务条款 ({len(contract.service_clauses)} 条)**:")
                # 按大类分组统计
                from collections import Counter
                cat_counts = Counter(cl.category for cl in contract.service_clauses)
                cat_tags = "  ".join(
                    f"`{cat}` ×{n}" for cat, n in cat_counts.most_common()
                )
                st.markdown(cat_tags)

                # 展示前10条条款内容
                st.caption("条款预览（前10条）：")
                clause_df_data = []
                for cl in contract.service_clauses[:10]:
                    clause_df_data.append({
                        "大类": cl.category,
                        "条款内容": cl.content[:100] + ("..." if len(cl.content) > 100 else ""),
                        "页码": cl.page,
                    })
                import pandas as pd
                st.dataframe(pd.DataFrame(clause_df_data), use_container_width=True, hide_index=True)
                if len(contract.service_clauses) > 10:
                    st.caption(f"... 还有 {len(contract.service_clauses) - 10} 条未显示")
            else:
                # 区分不同原因给出明确提示
                pdf_path = os.path.join(contracts_dir, contract.source_pdf) if contract.source_pdf else ""
                pdf_exists = os.path.exists(pdf_path)
                if not pdf_exists:
                    st.warning("⚠️ 未提取到服务条款 — PDF 文件不存在，无法解析")
                else:
                    # 检测是否为扫描件
                    from engine.pdf_parser import OCR_MIN_TEXT_LENGTH
                    try:
                        import pdfplumber, re
                        with pdfplumber.open(pdf_path) as pf:
                            sample = "".join((page.extract_text() or "") for page in pf.pages[:3])
                        is_scanned = len(re.sub(r"\s", "", sample)) < OCR_MIN_TEXT_LENGTH
                    except Exception:
                        is_scanned = False
                    if is_scanned:
                        st.warning("⚠️ 未提取到服务条款 — PDF 为扫描件，OCR 识别后 LLM 未能提取条款，请检查 LLM 配置")
                    else:
                        st.warning("⚠️ 未提取到服务条款 — 请检查 PDF 是否可读、LLM 是否正确配置")

            # 匹配结果概要
            if contract.id in results:
                c_results = results[contract.id]
                verdict_counts = Counter(r.verdict for r in c_results)
                v_tags = "  ".join(
                    f"`{v}` ×{n}" for v, n in verdict_counts.most_common()
                )
                st.markdown(f"**📊 匹配结果** ({len(c_results)} 条): {v_tags}")
