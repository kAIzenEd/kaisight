# -*- coding: utf-8 -*-
import base64
import csv
import io
import json
from datetime import date, datetime

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .report import _IMAGE_FIELD_TOKENS, _LIST_SKIP_TYPES, _is_image_field_name

_FIELD_CATEGORY_ORDER = [
    ("identity", _("Names & IDs")),
    ("contact", _("Contact")),
    ("dates", _("Dates")),
    ("status", _("Status & choices")),
    ("relations", _("Related records")),
    ("numbers", _("Numbers")),
    ("other", _("Other fields")),
]

# Common filter fields shown first per model (others auto-added for selection types).
_QUICK_FILTER_PRIORITY = {
    "school.student": [
        "gender",
        "city",
        "current_residence",
        "course",
        "year_of_study",
        "class_id",
        "country_id",
        "study_mode",
        "state_name",
        "ets_campus_location",
        "family_quarters",
        "blood_group",
    ],
    "school.admission": [
        "state",
        "course",
        "gender",
        "city",
        "country_id",
        "study_mode",
    ],
    "school.enrollment": ["state", "class_id", "academic_year"],
    "school.class": ["state", "academic_year", "semester", "teacher_id"],
    "school.fee": ["state", "academic_year", "product_id"],
    "school.attendance": ["state", "class_id", "date"],
    "school.grade": ["assessment_type", "class_id", "academic_year", "is_published"],
}

_FILTERABLE_TYPES = frozenset({"selection", "char", "text", "many2one", "boolean", "date"})


class KaisightReportBuilder(models.TransientModel):
    _name = "kai.view.report.builder"
    _description = "kaisight Report Builder"
    _inherit = ["kai.view.domain.mixin"]

    name = fields.Char(string="Report name")
    source_id = fields.Many2one("kai.view.report.source", string="Data source")
    model_id = fields.Many2one("ir.model", string="Model")
    model_name = fields.Char(related="model_id.model", readonly=True)
    res_model_name = fields.Char(
        related="model_id.model",
        string="Target model",
        readonly=True,
    )
    domain = fields.Char(default="[]")
    is_shared = fields.Boolean(string="Share with all users")

    # ------------------------------------------------------------------
    # Catalog API (used by the Report Builder client action)
    # ------------------------------------------------------------------

    @api.model
    def _user_can_read_model(self, model_name):
        if model_name not in self.env:
            return False
        try:
            self.env[model_name].check_access("read")
            return True
        except AccessError:
            return False

    @api.model
    def _source_visible_for_user(self, source):
        if not source.active:
            return False
        if not self._user_can_read_model(source.model_name):
            return False
        if source.group_ids and not (source.group_ids & self.env.user.group_ids):
            return False
        return True

    @api.model
    def _ordered_default_field_names(self, source):
        """Return recommended column names in a stable, business-friendly order.

        Prefer the Student directory saved-report column order when this source
        is ``school.student``; otherwise keep configured defaults.
        """
        configured = source.sudo().default_field_ids.mapped("name")
        model_name = source.model_name
        model_fields = self.env[model_name]._fields if model_name in self.env else {}

        def _valid(names):
            return [name for name in names if not model_fields or name in model_fields]

        preferred = []
        if model_name == "school.student":
            report = self.env.ref(
                "kaierp.report_student_directory", raise_if_not_found=False
            )
            if report and report.field_ids:
                preferred = [
                    line.field_id.name
                    for line in report.field_ids.sorted("sequence")
                    if line.field_id and line.field_id.name
                ]
        if preferred:
            # When defaults are empty on the source, use the full directory list.
            # When defaults exist, keep directory order for those that intersect,
            # then append any extra configured fields.
            if not configured:
                return _valid(preferred)
            configured_set = set(configured)
            ordered = [name for name in preferred if name in configured_set]
            ordered.extend(name for name in configured if name not in ordered)
            return _valid(ordered)

        saved_order = source.sudo().default_field_order
        if saved_order:
            try:
                stored = json.loads(saved_order)
            except (ValueError, TypeError):
                stored = []
            if isinstance(stored, list):
                configured_set = set(configured)
                ordered = [name for name in stored if name in configured_set]
                ordered.extend(name for name in configured if name not in ordered)
                return _valid(ordered)
        return _valid(configured)

    @api.model
    def set_source_default_fields(self, source_id, field_names):
        """Save the selected columns as this source's ordered common set."""
        if not self.env.user.has_group("kaisight.group_kai_view_manager"):
            raise AccessError(_("Only kaisight administrators can change the common set."))

        source = (
            self.env["kai.view.report.source"].sudo().browse(int(source_id)).exists()
        )
        if not source:
            raise UserError(_("This data source no longer exists."))

        model_name = source.model_name
        model_fields = self.env[model_name]._fields if model_name in self.env else {}
        ordered_names = []
        for name in field_names or []:
            if name in ordered_names:
                continue
            if model_fields and name not in model_fields:
                continue
            ordered_names.append(name)

        field_records = (
            self.env["ir.model.fields"]
            .sudo()
            .search([("model", "=", model_name), ("name", "in", ordered_names)])
        )
        source.write(
            {
                "default_field_ids": [(6, 0, field_records.ids)],
                "default_field_order": json.dumps(ordered_names),
            }
        )
        return {"default_fields": self._ordered_default_field_names(source)}

    @api.model
    def get_source_catalog(self):
        """Return data sources the current user may export from."""
        sources = self.env["kai.view.report.source"].search([])
        result = []
        for source in sources:
            if not self._source_visible_for_user(source):
                continue
            defaults = self._ordered_default_field_names(source)
            result.append(
                {
                    "id": source.id,
                    "name": source.name,
                    "description": source.description or "",
                    "icon": source.icon or "fa-table",
                    "model": source.model_name,
                    "default_fields": defaults,
                    "has_curated_fields": bool(defaults),
                }
            )
        return {
            "sources": result,
            "can_manage_sources": self.env.user.has_group(
                "kaisight.group_kai_view_manager"
            ),
        }

    @api.model
    def _field_category_key_from_meta(self, name, ftype):
        if name in {"id", "display_name", "name"} or name.endswith("_id") and name != "id":
            if name in {"id", "display_name", "name", "student_id", "ata_number", "roll_number"}:
                return "identity"
        if any(
            token in name
            for token in (
                "email",
                "phone",
                "mobile",
                "whatsapp",
                "address",
                "city",
                "zip",
                "postal",
                "country",
                "state",
            )
        ):
            return "contact"
        if ftype in {"date", "datetime"} or name.endswith("_date"):
            return "dates"
        if ftype in {"boolean", "selection"} or name in {"state", "status"}:
            return "status"
        if ftype == "many2one":
            return "relations"
        if ftype in {"integer", "float", "monetary"}:
            return "numbers"
        if name in {"name", "first_name", "middle_name", "last_name", "title"}:
            return "identity"
        return "other"

    @api.model
    def _field_category_key(self, field):
        return self._field_category_key_from_meta(field.name, field.ttype)

    @api.model
    def _safe_search_order(self, model):
        order = (model._order or "id").strip()
        if not order:
            return "id"
        safe_parts = []
        for chunk in order.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            field_name = chunk.split()[0]
            field = model._fields.get(field_name)
            if field and field.store:
                safe_parts.append(chunk)
        return ", ".join(safe_parts) if safe_parts else "id"

    @api.model
    def _is_image_export_field(self, field_name, field_type=None):
        """Binary photo/image fields may appear in PDF exports (not Excel/CSV)."""
        return _is_image_field_name(field_name, field_type)

    @api.model
    def get_field_catalog(self, model_name):
        """Return exportable fields grouped for checkbox selection."""
        if not model_name or model_name not in self.env:
            raise UserError(_("Model “%s” is not available.") % model_name)
        self.env[model_name].check_access("read")

        model = self.env[model_name]
        fields_info = model.fields_get(attributes=["string", "type"])

        buckets = {key: [] for key, _label in _FIELD_CATEGORY_ORDER}
        for field_name, info in fields_info.items():
            ftype = info.get("type")
            if field_name not in model._fields:
                continue
            if field_name.startswith("_"):
                continue
            is_image = self._is_image_export_field(field_name, ftype)
            if ftype in _LIST_SKIP_TYPES and not is_image:
                continue
            field = model._fields[field_name]
            category = (
                "identity"
                if is_image
                else self._field_category_key_from_meta(field_name, ftype)
            )
            buckets.setdefault(category, []).append(
                {
                    "name": field_name,
                    "label": info.get("string") or field.string or field_name,
                    "type": ftype,
                    "required": bool(field.required),
                    "is_image": is_image,
                }
            )

        groups = []
        for key, label in _FIELD_CATEGORY_ORDER:
            items = sorted(buckets.get(key, []), key=lambda f: f["label"].lower())
            if items:
                groups.append({"id": key, "label": label, "fields": items})
        return {"model": model_name, "groups": groups}

    @api.model
    def _selection_options(self, model, field_name):
        field = model._fields[field_name]
        selection = field.selection
        if callable(selection):
            selection = selection(model)
        return [{"value": value, "label": label} for value, label in selection]

    @api.model
    def _many2one_options(self, relation, limit=300):
        if relation not in self.env:
            return []
        try:
            self.env[relation].check_access("read")
        except AccessError:
            return []
        model = self.env[relation]
        records = model.search([], limit=limit, order=self._safe_search_order(model))
        return [{"value": record.id, "label": record.display_name} for record in records]

    @api.model
    def _filter_definition(self, model, field_name, fields_info):
        if field_name not in model._fields:
            return None
        field = model._fields[field_name]
        if field.type not in _FILTERABLE_TYPES:
            return None
        info = fields_info.get(field_name, {})
        definition = {
            "name": field_name,
            "label": info.get("string") or field.string or field_name,
            "type": field.type,
        }
        if field.type == "selection":
            definition["options"] = self._selection_options(model, field_name)
        elif field.type == "many2one":
            definition["relation"] = field.comodel_name
            definition["options"] = self._many2one_options(field.comodel_name)
        elif field.type == "boolean":
            definition["options"] = [
                {"value": "true", "label": _("Yes")},
                {"value": "false", "label": _("No")},
            ]
        elif field.type in {"char", "text"}:
            definition["placeholder"] = _("Contains…")
        return definition

    @api.model
    def get_filter_catalog(self, model_name):
        """Return user-friendly filters (gender, city, class, etc.)."""
        if not model_name or model_name not in self.env:
            raise UserError(_("Model “%s” is not available.") % model_name)
        self.env[model_name].check_access("read")

        model = self.env[model_name]
        fields_info = model.fields_get(attributes=["string", "type", "selection"])
        seen = set()
        filters = []

        for field_name in _QUICK_FILTER_PRIORITY.get(model_name, []):
            try:
                definition = self._filter_definition(model, field_name, fields_info)
            except Exception:
                continue
            if definition:
                filters.append(definition)
                seen.add(field_name)

        for field_name in ("city", "state_name", "email", "zip_code"):
            if field_name in seen:
                continue
            try:
                definition = self._filter_definition(model, field_name, fields_info)
            except Exception:
                continue
            if definition:
                filters.append(definition)
                seen.add(field_name)

        return {"model": model_name, "filters": filters}

    @api.model
    def _quick_filters_to_domain(self, model_name, quick_filters=None):
        if not quick_filters:
            return []
        if not isinstance(quick_filters, dict):
            return []
        model = self.env[model_name]
        domain = []
        for field_name, value in quick_filters.items():
            if value in (None, ""):
                continue
            if field_name not in model._fields:
                continue
            field = model._fields[field_name]
            if field.type == "selection":
                domain.append((field_name, "=", value))
            elif field.type in {"char", "text"}:
                domain.append((field_name, "ilike", value))
            elif field.type == "many2one":
                try:
                    domain.append((field_name, "=", int(value)))
                except (TypeError, ValueError):
                    continue
            elif field.type == "boolean":
                if isinstance(value, str):
                    value = value.lower() in {"1", "true", "yes"}
                domain.append((field_name, "=", bool(value)))
            elif field.type == "date":
                domain.append((field_name, "=", value))
        return domain

    @api.model
    def build_full_domain(self, model_name, domain_str="[]", quick_filters=None):
        domain = list(self._parse_domain_string(domain_str or "[]", _("Filter")))
        domain.extend(self._quick_filters_to_domain(model_name, quick_filters))
        return domain

    @api.model
    def preview_record_count(self, model_name, domain_str="[]", quick_filters=None):
        if not model_name or model_name not in self.env:
            return 0
        self.env[model_name].check_access("read")
        domain = self.build_full_domain(model_name, domain_str, quick_filters)
        return self.env[model_name].search_count(domain)

    # ------------------------------------------------------------------
    # Export helpers
    # ------------------------------------------------------------------

    @api.model
    def _format_export_value(self, record, field_name, field_type, for_pdf=False):
        value = record[field_name]
        if for_pdf and self._is_image_export_field(field_name, field_type):
            if not value:
                return {"type": "text", "value": ""}
            return {"type": "image", "value": value}
        if value is False or value is None:
            return ""
        if field_type == "many2one":
            return value.display_name if value else ""
        if field_type == "many2many":
            return ", ".join(value.mapped("display_name"))
        if field_type == "selection":
            selection = record._fields[field_name].selection
            if callable(selection):
                selection = selection(record)
            return dict(selection).get(value, value)
        if field_type == "boolean":
            return _("Yes") if value else _("No")
        if field_type == "date" and isinstance(value, date):
            return fields.Date.to_string(value)
        if field_type == "datetime" and isinstance(value, datetime):
            return fields.Datetime.to_string(value)
        if field_type == "binary":
            return ""
        return value

    @api.model
    def _resolve_field_names(self, model_name, field_names, allow_images=False):
        if not field_names:
            raise UserError(_("Select at least one column to export."))
        model = self.env[model_name]
        fields_info = model.fields_get(attributes=["type", "string"])
        resolved = []
        labels = []
        for name in field_names:
            if name not in model._fields:
                continue
            ftype = fields_info[name]["type"]
            is_image = self._is_image_export_field(name, ftype)
            if ftype in _LIST_SKIP_TYPES and not (allow_images and is_image):
                continue
            resolved.append(name)
            labels.append(fields_info[name].get("string") or name)
        if not resolved:
            raise UserError(_("None of the selected columns can be exported."))
        return resolved, labels

    @api.model
    def _get_ir_model_record(self, model_name):
        ir_model = self.env["ir.model"].sudo().search([("model", "=", model_name)], limit=1)
        if not ir_model:
            raise UserError(_("Model “%s” is not registered.") % model_name)
        return ir_model

    @api.model
    def _report_field_line_vals(self, model_name, field_names):
        names, _labels = self._resolve_field_names(model_name, field_names)
        field_records = self.env["ir.model.fields"].sudo().search(
            [("model", "=", model_name), ("name", "in", names)]
        )
        field_by_name = {field.name: field for field in field_records}
        line_vals = []
        for seq, fname in enumerate(names):
            field = field_by_name.get(fname)
            if field:
                line_vals.append((0, 0, {"field_id": field.id, "sequence": (seq + 1) * 10}))
        return line_vals

    @api.model
    def create_filter_wizard(self, model_name, domain_str="[]"):
        """Create a filter dialog record without requiring ir.model access."""
        ir_model = self._get_ir_model_record(model_name)
        wizard = self.create(
            {
                "model_id": ir_model.id,
                "domain": domain_str or "[]",
            }
        )
        return wizard.id

    @api.model
    def _build_export_rows(
        self, model_name, field_names, domain_str="[]", quick_filters=None, for_pdf=False
    ):
        domain = self.build_full_domain(model_name, domain_str, quick_filters)
        names, labels = self._resolve_field_names(
            model_name, field_names, allow_images=for_pdf
        )
        model = self.env[model_name]
        records = model.search(domain, order="id")
        fields_info = model.fields_get(attributes=["type"])
        rows = []
        for record in records:
            rows.append(
                [
                    self._format_export_value(
                        record,
                        name,
                        fields_info[name]["type"],
                        for_pdf=for_pdf,
                    )
                    for name in names
                ]
            )
        return labels, rows

    @api.model
    def _download_action(self, filename, content, mimetype):
        attachment = self.env["ir.attachment"].sudo().create(
            {
                "name": filename,
                "type": "binary",
                "datas": base64.b64encode(content),
                "mimetype": mimetype,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    @api.model
    def build_export_file(
        self,
        model_name,
        field_names,
        domain_str="[]",
        export_format="csv",
        quick_filters=None,
        report_title=None,
    ):
        """Return ``(filename, content_bytes, mimetype)`` for a tabular export."""
        if not model_name or model_name not in self.env:
            raise UserError(_("Model “%s” is not available.") % model_name)
        self.env[model_name].check_access("read")

        stamp = fields.Datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_model = model_name.replace(".", "_")
        title = report_title or model_name.replace(".", " ").title()

        if export_format == "pdf":
            from .export_report import _export_pdf_font_size

            labels, rows = self._build_export_rows(
                model_name,
                field_names,
                domain_str,
                quick_filters,
                for_pdf=True,
            )
            ir_model = self._get_ir_model_record(model_name)
            builder = self.create(
                {
                    "name": title,
                    "model_id": ir_model.id if ir_model else False,
                    "domain": str(
                        self.build_full_domain(model_name, domain_str, quick_filters)
                    ),
                }
            )
            report = self.env.ref("kaisight.action_report_export_table")
            column_count = len(labels)
            pdf_content, _report_format = report._render_qweb_pdf(
                report.report_name,
                res_ids=builder.ids,
                data={
                    "headers": labels,
                    "rows": rows,
                    "report_title": title,
                    "record_count": len(rows),
                    "generated_on": fields.Datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "column_count": column_count,
                    "font_size": _export_pdf_font_size(column_count),
                    "has_images": any(
                        isinstance(cell, dict) and cell.get("type") == "image"
                        for row in rows
                        for cell in row
                    ),
                },
            )
            builder.unlink()
            return (
                "%s_%s.pdf" % (safe_model, stamp),
                pdf_content,
                "application/pdf",
            )

        labels, rows = self._build_export_rows(
            model_name, field_names, domain_str, quick_filters, for_pdf=False
        )

        if export_format == "xlsx":
            try:
                import xlsxwriter
            except ImportError as exc:
                raise UserError(
                    _("Excel export requires xlsxwriter on the server.")
                ) from exc
            buffer = io.BytesIO()
            workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
            sheet = workbook.add_worksheet("Export")
            header_fmt = workbook.add_format({"bold": True, "bg_color": "#E8E8E8"})
            for col, label in enumerate(labels):
                sheet.write(0, col, label, header_fmt)
            for row_idx, row in enumerate(rows, start=1):
                for col_idx, cell in enumerate(row):
                    sheet.write(row_idx, col_idx, cell if not isinstance(cell, dict) else "")
            workbook.close()
            return (
                "%s_%s.xlsx" % (safe_model, stamp),
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(labels)
        writer.writerows(rows)
        return (
            "%s_%s.csv" % (safe_model, stamp),
            buffer.getvalue().encode("utf-8-sig"),
            "text/csv",
        )

    @api.model
    def export_report(
        self,
        model_name,
        field_names,
        domain_str="[]",
        export_format="csv",
        quick_filters=None,
        report_title=None,
    ):
        filename, content, mimetype = self.build_export_file(
            model_name,
            field_names,
            domain_str=domain_str,
            export_format=export_format,
            quick_filters=quick_filters,
            report_title=report_title,
        )
        return self._download_action(filename, content, mimetype)

    @api.model
    def action_open_in_odoo(
        self, model_name, field_names, domain_str="[]", name=None, quick_filters=None
    ):
        """Create a temporary saved report and open it in list view."""
        Report = self.env["kai.view.report"]
        ir_model = self._get_ir_model_record(model_name)
        line_vals = self._report_field_line_vals(model_name, field_names)
        full_domain = self.build_full_domain(model_name, domain_str, quick_filters)
        report = Report.create(
            {
                "name": name or _("%s export") % ir_model.name,
                "model_id": ir_model.id,
                "domain": str(full_domain),
                "field_ids": line_vals,
                "user_id": self.env.uid,
            }
        )
        return report.action_open_report()

    @api.model
    def save_report(
        self,
        name,
        model_name,
        field_names,
        domain_str="[]",
        is_shared=False,
        quick_filters=None,
    ):
        if not name:
            raise UserError(_("Enter a name for this report."))
        Report = self.env["kai.view.report"]
        ir_model = self._get_ir_model_record(model_name)
        line_vals = self._report_field_line_vals(model_name, field_names)
        full_domain = self.build_full_domain(model_name, domain_str, quick_filters)
        report = Report.create(
            {
                "name": name,
                "model_id": ir_model.id,
                "domain": str(full_domain),
                "field_ids": line_vals,
                "is_shared": is_shared,
                "user_id": self.env.uid,
            }
        )
        return {"id": report.id, "name": report.name}

    def action_set_domain(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Report filters"),
            "res_model": "kai.view.report.builder",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
