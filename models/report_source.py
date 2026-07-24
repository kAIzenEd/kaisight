# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_SKIP_DEFAULT_TYPES = frozenset({"one2many", "many2many", "binary", "html", "reference"})
_PREFERRED_DEFAULT_FIELDS = (
    "name",
    "display_name",
    "email",
    "phone",
    "mobile",
    "state",
    "active",
    "create_date",
    "partner_id",
    "user_id",
)


class KaisightReportSource(models.Model):
    _name = "kai.view.report.source"
    _description = "kaisight Exportable Data Source"
    _order = "sequence, name, id"

    name = fields.Char(required=True, translate=True)
    description = fields.Text(translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    icon = fields.Char(default="fa-table", help="Font Awesome icon class, e.g. fa-users")
    model_id = fields.Many2one(
        "ir.model",
        string="Model",
        required=True,
        ondelete="cascade",
    )
    model_name = fields.Char(related="model_id.model", store=True, readonly=True)
    group_ids = fields.Many2many(
        "res.groups",
        string="Allowed groups",
        help="Leave empty to allow all kaisight users who can read the model.",
    )
    default_field_ids = fields.Many2many(
        "ir.model.fields",
        string="Recommended columns",
        domain="[('model_id', '=', model_id)]",
        help="Pre-selected when opening this data source in the report builder.",
    )
    default_field_order = fields.Char(
        string="Common column order",
        help="JSON-encoded ordered field names for the common set. Managed from "
        "the Report Builder.",
        copy=False,
    )

    @api.model
    def ensure_access_rights(self):
        """Called from XML data / hooks so upgrades do not depend on model_* XML IDs."""
        from odoo.addons.kaisight.hooks import _ensure_model_access

        _ensure_model_access(self.env)
        return True

    def _register_hook(self):
        super()._register_hook()
        try:
            self.ensure_access_rights()
        except Exception:
            # Registry may not be ready for ACL writes during some tests.
            pass

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
    def _suggest_default_field_records(self, model_name):
        if model_name not in self.env:
            return self.env["ir.model.fields"]
        fields_info = self.env[model_name].fields_get(attributes=["type", "string"])
        chosen = []
        for name in _PREFERRED_DEFAULT_FIELDS:
            info = fields_info.get(name)
            if not info or info.get("type") in _SKIP_DEFAULT_TYPES:
                continue
            chosen.append(name)
        if not chosen:
            for name, info in fields_info.items():
                if name.startswith("_") or info.get("type") in _SKIP_DEFAULT_TYPES:
                    continue
                chosen.append(name)
                if len(chosen) >= 6:
                    break
        return (
            self.env["ir.model.fields"]
            .sudo()
            .search([("model", "=", model_name), ("name", "in", chosen)])
        )

    @api.model
    def get_model_catalog(self, search=""):
        """Return installable/reportable models the current user can read."""
        if not self.env.user.has_group("kaisight.group_kai_view_manager"):
            raise AccessError(_("Only kaisight administrators can browse models."))

        domain = [
            ("transient", "=", False),
            ("model", "not like", "kai.view.%"),
        ]
        needle = (search or "").strip()
        if needle:
            domain = [
                "&",
                *domain,
                "|",
                ("name", "ilike", needle),
                ("model", "ilike", needle),
            ]

        models = self.env["ir.model"].sudo().search(domain, order="name, model", limit=250)
        existing = set(self.search([]).mapped("model_name"))
        result = []
        for ir_model in models:
            model_name = ir_model.model
            if model_name in existing:
                continue
            if model_name not in self.env:
                continue
            # Skip abstract mixin-style models that are not instantiable tables.
            if getattr(self.env[model_name], "_abstract", False):
                continue
            if not self._user_can_read_model(model_name):
                continue
            result.append(
                {
                    "model": model_name,
                    "name": ir_model.name,
                    "already_added": False,
                }
            )
        return result

    @api.model
    def add_data_source(self, model_name, name=None, description=None, icon=None):
        """Create a Report Builder card for any readable Odoo model."""
        if not self.env.user.has_group("kaisight.group_kai_view_manager"):
            raise AccessError(_("Only kaisight administrators can add data sources."))
        if not model_name or model_name not in self.env:
            raise UserError(_("Model “%s” is not available.") % model_name)
        if not self._user_can_read_model(model_name):
            raise AccessError(_("You cannot read model “%s”.") % model_name)

        existing = self.search([("model_name", "=", model_name)], limit=1)
        if existing:
            return {
                "id": existing.id,
                "name": existing.name,
                "description": existing.description or "",
                "icon": existing.icon or "fa-table",
                "model": existing.model_name,
                "default_fields": existing.sudo().default_field_ids.mapped("name"),
            }

        ir_model = self.env["ir.model"].sudo().search([("model", "=", model_name)], limit=1)
        if not ir_model:
            raise UserError(_("Model “%s” is not registered.") % model_name)

        source = self.create(
            {
                "name": name or ir_model.name or model_name,
                "description": description or "",
                "icon": icon or "fa-table",
                "model_id": ir_model.id,
                "default_field_ids": [(6, 0, self._suggest_default_field_records(model_name).ids)],
            }
        )
        return {
            "id": source.id,
            "name": source.name,
            "description": source.description or "",
            "icon": source.icon or "fa-table",
            "model": source.model_name,
            "default_fields": source.sudo().default_field_ids.mapped("name"),
        }
