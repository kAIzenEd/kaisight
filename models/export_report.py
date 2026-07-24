# -*- coding: utf-8 -*-
from odoo import api, models


def _export_pdf_font_size(column_count):
    """Pick a compact font so wide tables fit on landscape A3."""
    if column_count <= 8:
        return "9pt"
    if column_count <= 12:
        return "8pt"
    if column_count <= 16:
        return "7pt"
    if column_count <= 22:
        return "6pt"
    return "5pt"


class ReportKaisightExportTable(models.AbstractModel):
    _name = "report.kaisight.export_table"
    _description = "kaisight tabular export PDF"

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        headers = data.get("headers", [])
        column_count = data.get("column_count") or len(headers)
        return {
            "doc_ids": docids,
            "doc_model": "kai.view.report.builder",
            "docs": self.env["kai.view.report.builder"].browse(docids),
            "headers": headers,
            "rows": data.get("rows", []),
            "report_title": data.get("report_title", "Export"),
            "record_count": data.get("record_count", 0),
            "generated_on": data.get("generated_on", ""),
            "column_count": column_count,
            "font_size": data.get("font_size") or _export_pdf_font_size(column_count),
            "has_images": data.get("has_images", False),
        }
