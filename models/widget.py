# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .action_utils import prepare_act_window_action


class KaisightWidget(models.Model):
    _name = "kai.view.widget"
    _description = "kaisight Dashboard Widget"
    _inherit = ["kai.view.domain.mixin"]
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    dashboard_id = fields.Many2one(
        "kai.view.dashboard",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    widget_type = fields.Selection(
        [
            ("kpi", "KPI / Count"),
            ("chart", "Chart"),
            ("list", "Record list"),
        ],
        required=True,
        default="kpi",
    )
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

    domain = fields.Char(
        string="Filter",
        default="[]",
        help="Odoo domain, e.g. [('active', '=', True)]",
    )
    measure_field = fields.Char(
        string="Measure field",
        help="Technical field name for sum/average KPIs and charts (leave empty for count).",
    )
    measure_field_id = fields.Many2one(
        "ir.model.fields",
        string="Measure field",
        domain="[('model_id', '=', model_id), ('ttype', 'in', ['integer', 'float', 'monetary'])]",
        ondelete="set null",
    )
    groupby_field = fields.Char(
        string="Group by",
        help="Technical field name used as chart axis / categories.",
    )
    groupby_field_id = fields.Many2one(
        "ir.model.fields",
        string="Group by field",
        domain="[('model_id', '=', model_id), ('store', '=', True)]",
        ondelete="set null",
    )
    list_fields = fields.Char(
        string="List columns",
        default="name",
        help="Comma-separated field names shown in list widgets.",
    )
    list_field_ids = fields.Many2many(
        "ir.model.fields",
        "kai_view_widget_list_field_rel",
        "widget_id",
        "field_id",
        string="List columns",
        domain="[('model_id', '=', model_id), ('ttype', 'not in', ['one2many', 'many2many', 'binary', 'html', 'reference'])]",
    )
    aggregate = fields.Selection(
        [
            ("count", "Count"),
            ("sum", "Sum"),
            ("avg", "Average"),
        ],
        default="count",
    )
    chart_type = fields.Selection(
        [
            ("bar", "Bar"),
            ("line", "Line"),
            ("pie", "Pie"),
            ("doughnut", "Doughnut"),
        ],
        default="bar",
    )
    record_limit = fields.Integer(string="List limit", default=8)
    grid_column = fields.Integer(string="Column", default=1)
    grid_width = fields.Integer(
        string="Width (columns)",
        default=4,
        help="Bootstrap-like 12-column grid span.",
    )
    color_index = fields.Integer(
        string="Color",
        default=1,
        help="Odoo chart color index (1-12).",
    )
    icon = fields.Char(
        string="Icon",
        default="fa-chart-bar",
        help="Font Awesome class for KPI cards, e.g. fa-users",
    )
    subtitle = fields.Char(translate=True)

    @api.onchange("measure_field_id")
    def _onchange_measure_field_id(self):
        if self.measure_field_id:
            self.measure_field = self.measure_field_id.name

    @api.onchange("groupby_field_id")
    def _onchange_groupby_field_id(self):
        if self.groupby_field_id:
            self.groupby_field = self.groupby_field_id.name

    @api.onchange("list_field_ids")
    def _onchange_list_field_ids(self):
        if self.list_field_ids:
            self.list_fields = ",".join(self.list_field_ids.mapped("name"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._sync_field_vals(vals)
        widgets = super().create(vals_list)
        widgets._sync_list_fields_from_relations()
        return widgets

    def write(self, vals):
        self._sync_field_vals(vals)
        res = super().write(vals)
        if "list_field_ids" in vals:
            self._sync_list_fields_from_relations()
        return res

    @api.model
    def _sync_field_vals(self, vals):
        """Keep technical char fields aligned with relational field pickers."""
        if vals.get("measure_field_id"):
            field = self.env["ir.model.fields"].browse(vals["measure_field_id"])
            vals["measure_field"] = field.name
        if vals.get("groupby_field_id"):
            field = self.env["ir.model.fields"].browse(vals["groupby_field_id"])
            vals["groupby_field"] = field.name
        if vals.get("list_field_ids"):
            field_ids = []
            for command in vals["list_field_ids"]:
                if command[0] == 6:
                    field_ids = command[2]
                elif command[0] == 4:
                    field_ids.append(command[1])
                elif command[0] == 5:
                    field_ids = []
            if field_ids:
                names = self.env["ir.model.fields"].browse(field_ids).mapped("name")
                vals["list_fields"] = ",".join(names)

    def _sync_list_fields_from_relations(self):
        for widget in self:
            if widget.list_field_ids:
                widget.list_fields = ",".join(widget.list_field_ids.mapped("name"))

    @api.onchange("model_id")
    def _onchange_model_id(self):
        self.measure_field_id = False
        self.groupby_field_id = False
        self.list_field_ids = False
        self.domain = "[]"

    @api.onchange("widget_type")
    def _onchange_widget_type(self):
        if self.widget_type == "kpi":
            self.groupby_field_id = False
            self.list_field_ids = False
        elif self.widget_type == "chart":
            self.list_field_ids = False
        elif self.widget_type == "list":
            self.measure_field_id = False
            self.groupby_field_id = False

    @api.constrains("grid_width")
    def _check_grid_width(self):
        for widget in self:
            if widget.grid_width < 1 or widget.grid_width > 12:
                raise UserError(_("Widget width must be between 1 and 12 columns."))

    @api.constrains("domain", "model_id")
    def _check_domain(self):
        for widget in self.filtered("model_id"):
            try:
                widget.validate_target_domain(widget.model_name, widget.domain)
            except ValidationError as exc:
                raise ValidationError(
                    _("Widget “%(name)s”: %(error)s")
                    % {"name": widget.name, "error": exc.args[0]}
                ) from exc

    def _parse_domain(self):
        self.ensure_one()
        try:
            return self._parse_domain_string(self.domain, _("Filter"))
        except ValidationError as exc:
            raise UserError(
                _("Invalid domain on widget “%s”: %s") % (self.name, exc.args[0])
            ) from exc

    def _get_model(self):
        self.ensure_one()
        if self.model_name not in self.env:
            raise UserError(
                _("Model “%s” is not available. Install the related addon first.")
                % self.model_name
            )
        return self.env[self.model_name]

    def _measure_name(self):
        self.ensure_one()
        return (self.measure_field or self.measure_field_id.name or "").strip()

    def _groupby_name(self):
        self.ensure_one()
        return (self.groupby_field or self.groupby_field_id.name or "").strip()

    def _list_field_names(self):
        self.ensure_one()
        if self.list_field_ids:
            return self.list_field_ids.mapped("name")
        return [
            f.strip()
            for f in (self.list_fields or "name").split(",")
            if f.strip()
        ]

    def _validate_field(self, field_name, label):
        if not field_name:
            return
        if field_name not in self._get_model()._fields:
            raise UserError(
                _("%(label)s “%(field)s” does not exist on model %(model)s.")
                % {"label": label, "field": field_name, "model": self.model_name}
            )

    def _run_query(self):
        self.ensure_one()
        model = self._get_model()
        domain = self._parse_domain()
        if self.widget_type == "kpi":
            return self._query_kpi(model, domain)
        if self.widget_type == "chart":
            return self._query_chart(model, domain)
        if self.widget_type == "list":
            return self._query_list(model, domain)
        return {}

    def _query_kpi(self, model, domain):
        measure = self._measure_name()
        self._validate_field(measure, _("Measure field"))
        if self.aggregate == "count" or not measure:
            value = model.search_count(domain)
        else:
            field = measure
            if self.aggregate == "sum":
                data = model.read_group(domain, [field], [], lazy=False)
                value = data[0].get(field, 0) if data else 0
            else:
                data = model.read_group(
                    domain, [f"{field}:avg"], [], lazy=False
                )
                value = data[0].get(f"{field}_avg", 0) if data else 0
        return {
            "value": value,
            "aggregate": self.aggregate,
            "model": self.model_name,
        }

    def _query_chart(self, model, domain):
        groupby = self._groupby_name()
        if not groupby:
            raise UserError(_("Charts require a “Group by” field."))
        self._validate_field(groupby, _("Group by"))
        measure = self._measure_name()
        if self.aggregate != "count":
            self._validate_field(measure, _("Measure field"))

        if self.aggregate == "count" or not measure:
            fields = [f"{groupby}"]
            rows = model.read_group(domain, fields, [groupby], lazy=False)
            labels = []
            values = []
            for row in rows:
                label = row.get(groupby)
                if isinstance(label, tuple):
                    label = label[1] or label[0]
                labels.append(label if label is not None else _("Undefined"))
                values.append(row.get("__count", 0))
        else:
            agg = "sum" if self.aggregate == "sum" else "avg"
            spec = f"{measure}:{agg}"
            rows = model.read_group(domain, [spec], [groupby], lazy=False)
            key = measure if agg == "sum" else f"{measure}_avg"
            labels = []
            values = []
            for row in rows:
                label = row.get(groupby)
                if isinstance(label, tuple):
                    label = label[1] or label[0]
                labels.append(label if label is not None else _("Undefined"))
                values.append(row.get(key, 0) or 0)

        return {
            "labels": labels,
            "values": values,
            "chart_type": self.chart_type,
            "color_index": self.color_index,
        }

    def _query_list(self, model, domain):
        field_names = self._list_field_names()
        for fname in field_names:
            self._validate_field(fname, _("List column"))
        records = model.search_read(
            domain,
            field_names,
            limit=max(1, min(self.record_limit or 8, 50)),
            order="id desc",
        )
        columns = []
        for fname in field_names:
            field = model._fields.get(fname)
            columns.append(
                {
                    "name": fname,
                    "label": field.string if field else fname,
                }
            )
        rows = []
        for rec in records:
            row = {}
            for fname in field_names:
                val = rec.get(fname)
                if isinstance(val, tuple):
                    val = val[1]
                row[fname] = val
            rows.append({"id": rec["id"], "values": row})
        return {
            "columns": columns,
            "rows": rows,
            "model": self.model_name,
        }

    def get_widget_payload(self):
        self.ensure_one()
        data = {}
        error = None
        try:
            data = self._run_query()
        except UserError as exc:
            error = str(exc)
        except Exception as exc:  # noqa: BLE001 - surface to UI
            error = _("Query failed: %s") % exc

        return {
            "id": self.id,
            "name": self.name,
            "subtitle": self.subtitle or "",
            "type": self.widget_type,
            "icon": self.icon or "fa-chart-bar",
            "model": self.model_name,
            "grid": {
                "column": self.grid_column,
                "width": self.grid_width,
            },
            "data": data,
            "error": error,
        }

    def action_open_records(self):
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": self.model_name,
            "view_mode": "list,form",
            "domain": self._parse_domain(),
            "target": "current",
        }
        return prepare_act_window_action(action)
