"""报告生成与 Excel 导出"""
import io
import pandas as pd
from engine.models import ComplianceReport, ComparisonResult


def export_compliance_report(report: ComplianceReport, filepath: str) -> None:
    """导出满足率报告到 Excel"""
    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        # Sheet 1: 总览
        overview = pd.DataFrame([{
            "合同ID": report.contract_id,
            "总满足率": f"{report.total_rate * 100:.1f}%",
            "满足条款数": report.matched_count,
            "总条款数": report.total_count,
        }])
        overview.to_excel(writer, sheet_name="总览", index=False)

        # Sheet 2: 按等级
        level_data = [{"等级": f"{lv}级", "满足率": f"{rate * 100:.1f}%"}
                      for lv, rate in sorted(report.level_rates.items())]
        pd.DataFrame(level_data).to_excel(writer, sheet_name="按等级", index=False)

        # Sheet 3: 按大类
        cat_data = [{"大类": cat, "满足率": f"{rate * 100:.1f}%"}
                    for cat, rate in report.category_rates.items()]
        pd.DataFrame(cat_data).to_excel(writer, sheet_name="按大类", index=False)

        # Sheet 4: 明细
        if report.details:
            detail_data = [{
                "规范条款ID": d.standard_item_id,
                "判定结果": d.verdict,
                "证据": d.evidence[:200],
                "置信度": d.confidence,
                "方法": d.method,
            } for d in report.details]
            pd.DataFrame(detail_data).to_excel(writer, sheet_name="明细", index=False)


def export_comparison(result: ComparisonResult, filepath: str) -> None:
    """导出对比结果到 Excel"""
    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        # Sheet 1: 总对比
        overview = pd.DataFrame([
            {"指标": "合同名称", "合同A": result.contract_a.property_name,
             "合同B": result.contract_b.property_name},
            {"指标": "总满足率", "合同A": f"{result.a_report.total_rate * 100:.1f}%",
             "合同B": f"{result.b_report.total_rate * 100:.1f}%"},
            {"指标": "满足条款数", "合同A": result.a_report.matched_count,
             "合同B": result.b_report.matched_count},
        ])
        overview.to_excel(writer, sheet_name="对比总览", index=False)

        # Sheet 2: A独有
        if result.a_only_items:
            a_data = [{"规范条款ID": d.standard_item_id, "证据": d.evidence[:200]}
                      for d in result.a_only_items]
            pd.DataFrame(a_data).to_excel(writer, sheet_name="A独有满足", index=False)

        # Sheet 3: B独有
        if result.b_only_items:
            b_data = [{"规范条款ID": d.standard_item_id, "证据": d.evidence[:200]}
                      for d in result.b_only_items]
            pd.DataFrame(b_data).to_excel(writer, sheet_name="B独有满足", index=False)

        # Sheet 4: 总结
        pd.DataFrame([{"AI总结": result.summary}]).to_excel(
            writer, sheet_name="总结", index=False)


def dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Sheet1") -> bytes:
    """DataFrame 转为 Excel 字节流（供 Streamlit 下载按钮使用）"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()
