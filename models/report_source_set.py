# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class KaisightReportSourceSet(models.Model):
    """Named common-column presets for a Report Builder data source."""

    _name = "kai.view.report.source.set"
    _description = "Report Builder Common Set"
    _order = "sequence, name, id"

    source_id = fields.Many2one(
        "kai.view.report.source",
        string="Data source",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    is_default = fields.Boolean(
        string="Default",
        help="Applied automatically when this data source is opened.",
    )
    field_names = fields.Json(default=lambda self: [])

    @api.constrains("source_id", "name")
    def _check_unique_name(self):
        for rec in self:
            if not rec.source_id or not rec.name:
                continue
            if self.sudo().search_count(
                [
                    ("source_id", "=", rec.source_id.id),
                    ("name", "=", rec.name),
                    ("id", "!=", rec.id),
                ]
            ):
                raise ValidationError(
                    "A common set with this name already exists for the data source."
                )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.filtered("is_default")._unset_other_defaults()
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals.get("is_default"):
            self.filtered("is_default")._unset_other_defaults()
        return res

    def _unset_other_defaults(self):
        for rec in self:
            others = self.sudo().search(
                [
                    ("source_id", "=", rec.source_id.id),
                    ("is_default", "=", True),
                    ("id", "!=", rec.id),
                ]
            )
            if others:
                others.write({"is_default": False})
