"""Excel 数据加载模块"""
from pathlib import Path
from typing import Optional
import pandas as pd
from engine.models import StandardItem, Contract

# 列名映射：可能的 Excel 列名 → 模型字段
_STANDARDS_COLUMN_MAP = {
    "等级": "level",
    "大类": "category",
    "内容和要求": "requirement",
    "是否新增": "is_new",
    "是否同比上一级新增": "is_new",
    "备注": "is_new",
}

_CONTRACTS_COLUMN_MAP = {
    "物业名称": "property_name",
    "位置": "location",
    "建筑面积": "building_area",
    "物业类型": "property_type",
    "甲方": "party_a",
    "乙方": "party_b",
    "住宅物业费": "residential_fee",
    "住宅物业服务费用": "residential_fee",
    "商业物业费": "commercial_fee",
    "商业物业服务费用": "commercial_fee",
    "车位费": "parking_fee",
    "车位费用": "parking_fee",
}


def load_standards(filepath: str, sheet_name: str | int = 0) -> list[StandardItem]:
    """加载成都市住宅物业服务等级规范 Excel"""
    df = pd.read_excel(filepath, sheet_name=sheet_name)
    df = _normalize_standards_columns(df)
    items = []
    for idx, row in df.iterrows():
        level = int(row["level"])
        cat = str(row["category"]).strip()
        item_id = f"L{level}-{_category_abbr(cat)}-{idx + 1:03d}"
        is_new = _parse_is_new(row.get("is_new", "否"))
        items.append(StandardItem(
            id=item_id,
            level=level,
            category=cat,
            requirement=str(row["requirement"]).strip(),
            is_new_vs_prev=is_new,
        ))
    return items


def load_contracts_meta(filepath: str, sheet_name: str | int = 0) -> list[Contract]:
    """加载合同元数据 Excel（不含服务条款，需后续从 PDF 补充）"""
    df = pd.read_excel(filepath, sheet_name=sheet_name)
    df = _normalize_contracts_columns(df)
    contracts = []
    for idx, row in df.iterrows():
        contracts.append(Contract(
            id=f"C{idx + 1:03d}",
            property_name=str(row["property_name"]).strip(),
            location=str(row.get("location", "")).strip(),
            building_area=_safe_float(row.get("building_area", 0)),
            property_type=str(row.get("property_type", "住宅")).strip(),
            party_a=str(row.get("party_a", "")).strip(),
            party_b=str(row.get("party_b", "")).strip(),
            residential_fee=_safe_float(row.get("residential_fee", 0)),
            commercial_fee=_safe_float(row.get("commercial_fee", 0)),
            parking_fee=_safe_float(row.get("parking_fee", 0)),
        ))
    return contracts


def _normalize_standards_columns(df: pd.DataFrame) -> pd.DataFrame:
    """将可能的列名标准化为内部字段名"""
    rename = {}
    for col in df.columns:
        col_str = str(col).strip()
        if col_str in _STANDARDS_COLUMN_MAP:
            rename[col] = _STANDARDS_COLUMN_MAP[col_str]
    return df.rename(columns=rename)


def _normalize_contracts_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for col in df.columns:
        col_str = str(col).strip()
        if col_str in _CONTRACTS_COLUMN_MAP:
            rename[col] = _CONTRACTS_COLUMN_MAP[col_str]
    return df.rename(columns=rename)


def _parse_is_new(val) -> bool:
    """解析'是否同比上一级新增'标记"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    s = str(val).strip()
    return s in ("是", "新增", "True", "true", "1", "yes")


def _category_abbr(category: str) -> str:
    """大类名称 → 缩写代码"""
    abbr_map = {
        "综合管理": "ZH", "共用部位维护": "BW", "共用部位": "BW",
        "共用设施设备维护": "SS", "共用设施设备": "SS", "设施设备": "SS",
        "公共秩序维护": "ZX", "公共秩序": "ZX",
        "保洁服务": "BJ", "保洁": "BJ",
        "绿化养护": "LH", "绿化": "LH",
        "其他": "QT",
    }
    return abbr_map.get(category, category[:2].upper())


def _safe_float(val) -> float:
    """安全转换为 float"""
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0
