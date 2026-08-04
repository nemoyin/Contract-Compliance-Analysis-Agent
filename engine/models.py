"""数据模型定义"""
from dataclasses import dataclass, field
from typing import Optional, Literal


@dataclass
class StandardItem:
    """成都市住宅物业服务等级规范中的单条明细"""
    id: str              # "L3-C2-045"（等级-大类-序号）
    level: int           # 1~5
    category: str        # 综合管理/共用部位维护/共用设施设备维护/公共秩序维护/保洁服务/绿化养护/其他
    requirement: str     # 具体内容和要求
    is_new_vs_prev: bool # 是否同比上一级新增


@dataclass
class ServiceClause:
    """合同中提取的单条服务条款"""
    content: str         # 条款原文
    category: str        # 归属大类
    page: int            # 来源页码


@dataclass
class Contract:
    """物业合同完整数据（元数据+PDF提取合并）"""
    id: str
    property_name: str
    location: str
    building_area: float
    property_type: str
    party_a: str
    party_b: str
    residential_fee: float    # 元/月·㎡
    commercial_fee: float
    parking_fee: float        # 元/月·个
    service_level_declared: Optional[str] = None
    service_clauses: list[ServiceClause] = field(default_factory=list)
    source_pdf: str = ""


@dataclass
class MatchResult:
    """单条规范 vs 单合同的匹配判定"""
    contract_id: str
    standard_item_id: str
    verdict: Literal["满足", "部分满足", "不满足", "不确定"]
    evidence: str            # 合同原文片段
    confidence: float        # 0~1
    method: Literal["rule", "llm"]
    matched_level: int       # 该条款实际达到的等级


@dataclass
class ComplianceReport:
    """满足率计算结果"""
    contract_id: str
    total_rate: float                        # 总满足率
    level_rates: dict[int, float]            # {1: 0.92, 2: 0.78, ...}
    category_rates: dict[str, float]         # {"综合管理": 0.72, ...}
    matched_count: int
    total_count: int
    details: list[MatchResult] = field(default_factory=list)


@dataclass
class ComparisonResult:
    """同价不同质：两个合同的对比结果"""
    contract_a: Contract
    contract_b: Contract
    fee_type: str           # "residential" | "commercial" | "parking"
    a_report: ComplianceReport
    b_report: ComplianceReport
    a_only_items: list[MatchResult]     # A满足但B不满足的条款
    b_only_items: list[MatchResult]     # B满足但A不满足的条款
    both_missing: list[MatchResult]     # 双方都不满足的条款
    summary: str                         # LLM生成的自然语言总结


@dataclass
class ClusterResult:
    """同质不同价：聚类+异常检测结果"""
    fee_type: str
    groups: list['QualityGroup']
    outliers: list['PriceOutlier']


@dataclass
class QualityGroup:
    """同质组"""
    group_id: int
    contract_ids: list[str]
    avg_satisfaction: float
    avg_price: float
    price_std: float


@dataclass
class PriceOutlier:
    """价格异常点"""
    contract_id: str
    property_name: str
    fee: float
    group_id: int
    group_avg_fee: float
    deviation_pct: float     # 偏离百分比
