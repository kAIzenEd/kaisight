# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .action_utils import prepare_act_window_action

_LIST_SKIP_TYPES = frozenset({"one2many", "many2many", "binary", "html", "reference"})
_IMAGE_FIELD_TOKENS = ("photo", "image", "avatar", "picture", "logo")


def _is_image_field_name(field_name, field_type=None):
    if field_type and field_type != "binary":
        return False
    lname = (field_name or "").lower()
    return any(token in lname for token in _IMAGE_FIELD_TOKENS)


class KaisightReportField(models.Model):
    _name = "kai.view.report.field"
    _description = "kaisight Report Field"
    _order = "sequence, id"

    report_id = fields.Many2one(
        "kai.view.report",
        string="Report",
        required=True,
        ondelete="cascade",
    )
    field_id = fields.Many2one(
        "ir.model.fields",
        string="Field",
        required=True,
        ondelete="cascade",
        domain="[('model_id', '=', parent.model_id)]",
    )
    sequence = fields.Integer(default=10)


class KaisightReport(models.Model):
    _name = "kai.view.report"
    _description = "kaisight Saved Report"
    _inherit = ["kai.view.domain.mixin"]
    _order = "sequence, name, id"

    name = fields.Char(required=True, translate=True)
    description = fields.Text(translate=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    model_id = fields.Many2one(
        "ir.model",
        string="Model",
        required=True,
        ondelete="cascade",
    )
    model_name = fields.Char(related="model_id.model", store=True, readonly=True)
    res_model_name = fields.Char(
        related="model_id.model",
        string="Target model",
        readonly=True,
    )
    field_ids = fields.One2many(
        "kai.view.report.field",
        "report_id",
        string="Columns",
        help="Fields shown in the list view when opening this report.",
    )
    list_view_id = fields.Many2one(
        "ir.ui.view",
        string="List view",
        copy=False,
        ondelete="set null",
        readonly=True,
    )
    domain = fields.Char(default="[]")
    context = fields.Char(
        default="{}",
        help="Extra context passed to the action (JSON object).",
    )
    view_mode = fields.Char(
        default="list,form",
        help="Comma-separated view types, e.g. list,form,kanban",
    )
    user_id = fields.Many2one(
        "res.users",
        string="Owner",
        default=lambda self: self.env.user,
        index=True,
    )
    is_shared = fields.Boolean(string="Shared with all users")
    is_favorite = fields.Boolean(string="Favorite", groups="base.group_no_one")

    @api.onchange("model_id")
    def _onchange_model_id(self):
        self.field_ids = False
        self.domain = "[]"

    @api.model_create_multi
    def create(self, vals_list):
        reports = super().create(vals_list)
        reports._sync_list_view()
        return reports

    def write(self, vals):
        res = super().write(vals)
        if {"field_ids", "model_id", "name"} & set(vals):
            self._sync_list_view()
        return res

    def _check_report_access(self, mode="read"):
        self.ensure_one()
        if self.env.su:
            return
        if self.env.user.has_group("kaisight.group_kai_view_manager"):
            return
        if mode == "read" and self.is_shared:
            return
        if self.user_id == self.env.user:
            return
        raise AccessError(_("You do not have access to this report."))

    @api.constrains("domain", "model_id")
    def _check_domain(self):
        for report in self.filtered("model_id"):
            try:
                report.validate_target_domain(report.model_name, report.domain)
            except ValidationError as exc:
                raise ValidationError(
                    _("Report “%(name)s”: %(error)s")
                    % {"name": report.name, "error": exc.args[0]}
                ) from exc

    def _parse_domain(self):
        self.ensure_one()
        try:
            return self._parse_domain_string(self.domain, _("Filter"))
        except ValidationError as exc:
            raise UserError(_("Invalid domain: %s") % exc.args[0]) from exc

    def _parse_context(self):
        self.ensure_one()
        import ast

        ctx_str = (self.context or "{}").strip()
        if not ctx_str:
            return {}
        try:
            ctx = ast.literal_eval(ctx_str)
        except (SyntaxError, ValueError) as exc:
            raise UserError(_("Invalid context: %s") % exc) from exc
        if not isinstance(ctx, dict):
            raise UserError(_("Context must evaluate to a dict."))
        return ctx

    def _get_list_field_names(self, include_images=True):
        self.ensure_one()
        names = []
        # Field metadata is technical; resolve with sudo so report users
        # (Registrar/Secretary) can open/export without Access Rights group.
        model = self.env[self.model_name] if self.model_name in self.env else None
        for report_field in self.sudo().field_ids.sorted("sequence"):
            field = report_field.field_id
            if not field:
                continue
            is_image = _is_image_field_name(field.name, field.ttype)
            if field.ttype in _LIST_SKIP_TYPES and not (include_images and is_image):
                continue
            if model and field.name not in model._fields:
                continue
            names.append(field.name)
        return names

    def _build_list_arch(self):
        self.ensure_one()
        field_names = self._get_list_field_names(include_images=True)
        if not field_names:
            field_names = ["name"] if "name" in self.env[self.model_name]._fields else []
        if not field_names:
            raise UserError(
                _("Select at least one column, or pick a model with a “name” field.")
            )
        # Wide reports keep readable column widths and scroll horizontally
        # instead of compressing every field into the viewport.
        wide = len(field_names) > 12
        list_attrs = ' class="o_kaisight_wide_report"' if wide else ""
        parts = ["<list%s>" % list_attrs]
        for fname in field_names:
            field = self.env[self.model_name]._fields.get(fname)
            width_attr = ' width="120px"' if wide else ""
            if field and _is_image_field_name(fname, field.type):
                parts.append(
                    '<field name="%s" widget="image" options="{\'size\': [40, 40]}"%s/>'
                    % (fname, width_attr)
                )
            else:
                parts.append('<field name="%s"%s/>' % (fname, width_attr))
        parts.append("</list>")
        return "".join(parts)

    def _sync_list_view(self):
        for report in self.filtered("model_id"):
            if not report.field_ids:
                if report.list_view_id:
                    report.sudo().list_view_id.unlink()
                    report.sudo().list_view_id = False
                continue
            arch = report._build_list_arch()
            # High priority so these never replace the model's default list
            # (e.g. Students menu). Report open still uses list_view_id explicitly.
            view_vals = {
                "arch": arch,
                "model": report.model_name,
                "priority": 999,
                "mode": "primary",
            }
            list_view = report.sudo().list_view_id
            if list_view:
                list_view.sudo().write(view_vals)
            else:
                view = self.env["ir.ui.view"].sudo().create(
                    {
                        "name": "kaisight report %s" % report.id,
                        "type": "list",
                        **view_vals,
                    }
                )
                report.sudo().list_view_id = view.id

    @api.model
    def get_report_list(self):
        domain = [
            "|",
            ("is_shared", "=", True),
            ("user_id", "=", self.env.uid),
        ]
        if self.env.user.has_group("kaisight.group_kai_view_manager"):
            domain = []
        reports = self.search(domain, order="sequence, name")
        return [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description or "",
                "model": r.model_name,
                "is_shared": r.is_shared,
            }
            for r in reports
        ]

    def action_edit_report(self):
        """Open the saved report definition (filters, columns, etc.)."""
        self.ensure_one()
        self._check_report_access("read")
        return prepare_act_window_action(
            {
                "type": "ir.actions.act_window",
                "name": self.name,
                "res_model": self._name,
                "res_id": self.id,
                "view_mode": "form",
                "views": [(False, "form")],
                "target": "current",
            }
        )

    def action_open_report(self):
        """Open the filtered Odoo records for this report (not the definition)."""
        self.ensure_one()
        self._check_report_access("read")
        if self.model_name not in self.env:
            raise UserError(
                _("Model “%s” is not available.") % self.model_name
            )
        self._sync_list_view()
        view_modes = (self.view_mode or "list,form").split(",")
        view_modes = [m.strip() for m in view_modes if m.strip()]
        views = []
        for mode in view_modes:
            if mode == "list" and self.list_view_id:
                views.append((self.list_view_id.id, "list"))
            else:
                views.append((False, mode))

        # Drop list-button context so the client opens the target model,
        # not the saved-report record again.
        skip_keys = {
            "active_id",
            "active_ids",
            "active_model",
            "default_name",
            "default_model_id",
        }
        ctx = {
            key: value
            for key, value in self.env.context.items()
            if key not in skip_keys and not str(key).startswith("default_")
        }
        ctx.update(self._parse_context())

        action = {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": self.model_name,
            "view_mode": ",".join(view_modes),
            "views": views,
            "domain": self._parse_domain(),
            "context": ctx,
            "target": "current",
        }
        return prepare_act_window_action(action)

    def _export_field_names(self):
        self.ensure_one()
        names = self._get_list_field_names()
        if names:
            return names
        model = self.env[self.model_name]
        if "name" in model._fields:
            return ["name"]
        raise UserError(
            _("Add at least one column to this saved report before exporting.")
        )

    def _action_export(self, export_format):
        self.ensure_one()
        self._check_report_access("read")
        if self.model_name not in self.env:
            raise UserError(_("Model “%s” is not available.") % self.model_name)
        return self.env["kai.view.report.builder"].export_report(
            self.model_name,
            self._export_field_names(),
            domain_str=self.domain or "[]",
            export_format=export_format,
            report_title=self.name,
        )

    def action_export_xlsx(self):
        return self._action_export("xlsx")

    def action_export_pdf(self):
        return self._action_export("pdf")

    def action_export_csv(self):
        return self._action_export("csv")

    def action_schedule_report(self):
        """Open a new schedule pre-filled for this saved report."""
        self.ensure_one()
        self._check_report_access("read")
        return {
            "type": "ir.actions.act_window",
            "name": _("Schedule Report"),
            "res_model": "kai.view.report.schedule",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_report_id": self.id,
                "default_name": _("Schedule: %s") % self.name,
                "default_partner_ids": [(6, 0, [self.env.user.partner_id.id])]
                if self.env.user.partner_id
                else [],
            },
        }
