# 🏢 物业合同合规审查智能体

基于 LLM 的物业合同分析工具，用于审查成都市住宅物业服务合同与《成都市住宅物业服务等级规范》的合规性，识别"同价不同质"和"同质不同价"的异常楼盘。

## 功能模块

| 模块 | 说明 |
|------|------|
| **首页/仪表盘** | 数据概览、缓存状态、预处理控制 |
| **同价不同质** | 价格相近的两份合同 → 逐项对比服务条款满足度差异 |
| **同质不同价** | 按满足度聚类 → 标记同类服务中价格异常的楼盘 |
| **满足率计算** | 单/多合同对五级规范的满足率 + Excel 报告导出 |
| **模型配置** | LLM 供应商切换（DeepSeek/Claude/OpenAI/自定义）、API Key 管理、阈值调节 |

## 技术架构

```
┌──────────────────────────────────────────────────────────────┐
│                    一次性预处理（初始化）                      │
│                                                              │
│  PDF ─→ pdfplumber 文本提取 ─→ OCR 回退(Tesseract+PyMuPDF)   │
│              ↓                                               │
│  LLM 定位服务章节 → LLM 提取服务条款(7大类归类)                 │
│              ↓                                               │
│  五级规范Excel ─→ 规则匹配(关键词/排除/数值) → LLM语义判定     │
│              ↓                                               │
│        data/cache/merged_results.json (持久化缓存)             │
└──────────────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────────┐
│                    日常分析（秒级读取缓存）                     │
│                                                              │
│  用户操作 ─→ 读缓存 ─→ 对比/聚类/计算 ─→ 可视化输出           │
└──────────────────────────────────────────────────────────────┘
```

### 匹配引擎：规则粗筛 + LLM 语义判定（混合模式）

```
合同条款 → [阶段1: 规则粗筛] → 确定 → 直接打标 (method="rule")
                    ↓ 不确定
              [阶段2: LLM语义判定] → 满足/部分满足/不满足 (method="llm")
```

阶段1 规则类型：关键词命中、反向排除、数值范围比较、等级推断
阶段2 LLM 批量判定：20条/批，置信度 < 0.9 的项进入

## 项目结构

```
├── app.py                     # Streamlit 入口
├── pages/                     # 5个功能页面
│   ├── 01_首页.py
│   ├── 02_模型配置.py
│   ├── 03_同价不同质.py
│   ├── 04_同质不同价.py
│   └── 05_满足率计算.py
├── engine/                    # 核心分析引擎
│   ├── models.py              # 数据模型 (dataclass)
│   ├── config.py              # 配置管理 (JSON持久化)
│   ├── loader.py              # Excel 数据加载
│   ├── pdf_parser.py          # PDF文本提取+文档树 (pdfplumber + OCR)
│   ├── pdf_extractor.py       # LLM 条款提取 (章节定位+结构化)
│   ├── matcher.py             # 混合匹配引擎 (规则+LLM)
│   ├── llm.py                 # LLM 抽象层 (多供应商)
│   ├── cache.py               # 缓存管理
│   ├── comparator.py          # 对比分析逻辑
│   ├── preprocess.py          # 预处理流水线
│   └── report.py              # Excel 报告导出
├── data/
│   ├── standards.xlsx         # 成都市五级规范（198条）
│   ├── contracts_meta.xlsx    # 合同元数据（名称/价格等）
│   ├── contracts/             # PDF 合同文件
│   ├── cache/                 # 匹配结果缓存
│   └── config.json            # 运行时配置（含API Key，不提交Git）
└── tests/                     # 单元测试
```

## 数据流

```
standards.xlsx  ──→ StandardItem[] (198条, 5级7大类)
contracts_meta.xlsx ──→ Contract[] (元数据: 名称/价格等)
contracts/*.pdf ──→ 文本提取 → LLM提取 → ServiceClause[]
                            ↓
                   Contract.service_clauses 合并
                            ↓
           规则匹配(rule_match) + LLM判定(llm_match_batch)
                            ↓
                  MatchResult[] → 缓存 → 分析模块
```

## 快速开始

### 环境要求

- Python 3.11+
- Tesseract OCR（扫描件PDF识别，可选）
  - Windows: [下载安装](https://github.com/UB-Mannheim/tesseract/wiki)，勾选中文语言包
  - Linux: `sudo apt install tesseract-ocr tesseract-ocr-chi-sim`

### 安装

```bash
git clone https://github.com/nemoyin/Contract-Compliance-Analysis-Agent.git
cd Contract-Compliance-Analysis-Agent
pip install -r requirements.txt
```

### 配置

1. 启动 Streamlit 后在 **模型配置** 页面设置 LLM API Key
2. 或者手动编辑 `data/config.json`（不提交到 Git）：

```json
{
  "llm": {
    "provider": "deepseek",
    "api_key": "your-api-key",
    "model": "deepseek-v4-pro",
    "base_url": "https://api.deepseek.com/v1",
    "temperature": 0.3
  },
  "matching": {
    "rule_confidence_threshold": 0.9,
    "llm_batch_size": 20
  },
  "thresholds": {
    "similar_price_pct": 5,
    "quality_similarity": 0.95,
    "price_outlier_std": 1.5
  }
}
```

### 启动

```bash
streamlit run app.py
```

浏览器打开 `http://localhost:8501`，首页点击 **初始化数据缓存**。

### 初始化流程

1. 加载规范标准（198条）+ 合同元数据
2. 解析 PDF：文本型用 pdfplumber，扫描件自动 OCR 回退
3. LLM 提取服务条款（7大类归类）
4. 规则匹配 + LLM 语义判定
5. 结果写入 `data/cache/`

### 运行测试

```bash
python -m pytest tests/ -v
```

## 核心依赖

| 包 | 用途 |
|----|------|
| `streamlit` | Web 应用框架 |
| `pdfplumber` | PDF 文本提取 |
| `pytesseract` + `PyMuPDF` | OCR 扫描件识别 |
| `openai` | LLM API 客户端（兼容多供应商） |
| `pandas` + `openpyxl` | Excel 读写 |
| `plotly` | 交互式图表 |
| `scikit-learn` | 余弦相似度聚类 |

## 匹配判定

| 判定 | 含义 |
|------|------|
| **满足** | 合同明确覆盖了规范要求的服务内容和频率 |
| **部分满足** | 覆盖了服务内容但频率/范围不足 |
| **不满足** | 合同未涉及或明确排除 |
| **不确定** | LLM 不可用时降级标记 |

## License

MIT
