"""模型供应商配置页面"""
import os
import streamlit as st
from engine.config import ConfigManager
from engine.llm import create_provider

st.title("⚙️ 模型供应商配置")

data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
config_path = os.path.join(data_dir, "config.json")
cfg = ConfigManager(config_path)
config = cfg.load()

# LLM 配置
st.subheader("🔌 LLM 供应商")

provider = st.selectbox(
    "供应商类型",
    options=["deepseek", "claude", "openai", "custom"],
    index=["deepseek", "claude", "openai", "custom"].index(
        config["llm"].get("provider", "deepseek")),
    format_func=lambda x: {"deepseek": "DeepSeek", "claude": "Claude",
                           "openai": "OpenAI", "custom": "自定义"}[x],
)

api_key = st.text_input(
    "API Key",
    value=config["llm"].get("api_key", ""),
    type="password",
    placeholder="输入 API Key...",
)

base_url = st.text_input(
    "Base URL",
    value=config["llm"].get("base_url", "https://api.deepseek.com/v1"),
)

model = st.text_input(
    "Model",
    value=config["llm"].get("model", "deepseek-chat"),
)

temperature = st.slider(
    "Temperature",
    min_value=0.0, max_value=1.0,
    value=float(config["llm"].get("temperature", 0.3)),
    step=0.05,
)

col1, col2 = st.columns(2)
with col1:
    if st.button("🔍 测试连接", use_container_width=True):
        test_config = {
            "llm": {"api_key": api_key, "model": model,
                    "base_url": base_url, "temperature": temperature,
                    "provider": provider}
        }
        llm = create_provider(test_config)
        if llm and llm.test_connection():
            st.success("✅ 连接成功！")
        else:
            st.error("❌ 连接失败，请检查配置")

with col2:
    if st.button("💾 保存配置", type="primary", use_container_width=True):
        config["llm"].update({
            "provider": provider, "api_key": api_key,
            "model": model, "base_url": base_url,
            "temperature": temperature,
        })
        cfg.save(config)
        st.success("配置已保存！")

st.markdown("---")

# 匹配参数
st.subheader("🎯 匹配参数")

rule_threshold = st.slider(
    "规则置信度阈值",
    min_value=0.7, max_value=0.99,
    value=float(config["matching"].get("rule_confidence_threshold", 0.9)),
    step=0.01,
    help="规则匹配置信度 ≥ 此值直接判定，否则交给 LLM",
)

batch_size = st.number_input(
    "LLM 批量大小",
    min_value=5, max_value=50,
    value=int(config["matching"].get("llm_batch_size", 20)),
    step=5,
    help="单次 LLM 调用最多判定的条款数",
)

st.markdown("---")

# 分析阈值
st.subheader("📐 分析阈值")

similar_price = st.number_input(
    "同价判定范围 (±%)",
    min_value=1, max_value=30,
    value=int(config["thresholds"].get("similar_price_pct", 5)),
    help="价格差在此百分比内视为'同价'",
)

quality_sim = st.slider(
    "同质相似度阈值",
    min_value=0.80, max_value=1.00,
    value=float(config["thresholds"].get("quality_similarity", 0.95)),
    step=0.01,
    help="余弦相似度 ≥ 此值视为'同质组'",
)

price_outlier = st.number_input(
    "价格异常标准差倍数",
    min_value=0.5, max_value=5.0,
    value=float(config["thresholds"].get("price_outlier_std", 1.5)),
    step=0.1,
    help="价格偏离组均值 ≥ N 个标准差视为异常",
)

if st.button("💾 保存全部配置", type="primary", use_container_width=True):
    config["llm"].update({
        "provider": provider, "api_key": api_key,
        "model": model, "base_url": base_url,
        "temperature": temperature,
    })
    config["matching"].update({
        "rule_confidence_threshold": rule_threshold,
        "llm_batch_size": batch_size,
    })
    config["thresholds"].update({
        "similar_price_pct": similar_price,
        "quality_similarity": quality_sim,
        "price_outlier_std": price_outlier,
    })
    cfg.save(config)
    st.success("全部配置已保存！")
    st.rerun()
