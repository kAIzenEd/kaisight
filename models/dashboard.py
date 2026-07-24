# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class KaisightDashboard(models.Model):
    _name = "kai.view.dashboard"
    _description = "kaisight Dashboard"
    _order = "sequence, name, id"

    name = fields.Char(required=True, translate=True)
    description = fields.Text(translate=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    user_id = fields.Many2one(
        "res.users",
        string="Owner",
        default=lambda self: self.env.user,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
    )
    is_shared = fields.Boolean(
        string="Shared with all users",
        help="When enabled, every internal user can open this dashboard.",
    )
    widget_ids = fields.One2many(
        "kai.view.widget",
        "dashboard_id",
        string="Widgets",
        copy=True,
    )
    widget_count = fields.Integer(compute="_compute_widget_count")

    @api.depends("widget_ids")
    def _compute_widget_count(self):
        for dashboard in self:
            dashboard.widget_count = len(dashboard.widget_ids)

    def _check_dashboard_access(self, mode="read"):
        self.ensure_one()
        if self.env.su:
            return
        if self.env.user.has_group("kaisight.group_kai_view_manager"):
            return
        if mode == "read" and self.is_shared:
            return
        if self.user_id == self.env.user:
            return
        raise AccessError(_("You do not have access to this dashboard."))

    @api.model
    def get_dashboard_list(self):
        """Return dashboards visible to the current user."""
        domain = [
            "|",
            ("is_shared", "=", True),
            ("user_id", "=", self.env.uid),
        ]
        if self.env.user.has_group("kaisight.group_kai_view_manager"):
            domain = []
        dashboards = self.search(domain, order="sequence, name")
        return [
            {
                "id": d.id,
                "name": d.name,
                "description": d.description or "",
                "widget_count": d.widget_count,
                "is_shared": d.is_shared,
                "is_owner": d.user_id.id == self.env.uid,
            }
            for d in dashboards
        ]

    @api.model
    def get_dashboard_payload(self, dashboard_id):
        try:
            dashboard_id = int(dashboard_id)
        except (TypeError, ValueError):
            raise UserError(_("Dashboard not found."))
        dashboard = self.browse(dashboard_id)
        if not dashboard.exists():
            raise UserError(_("Dashboard not found."))
        dashboard._check_dashboard_access("read")
        widgets = []
        for widget in dashboard.widget_ids.filtered("active").sorted("sequence"):
            widgets.append(widget.get_widget_payload())
        return {
            "id": dashboard.id,
            "name": dashboard.name,
            "description": dashboard.description or "",
            "widgets": widgets,
        }

    @api.model
    def refresh_widget(self, widget_id):
        try:
            widget_id = int(widget_id)
        except (TypeError, ValueError):
            raise UserError(_("Widget not found."))
        widget = self.env["kai.view.widget"].browse(widget_id)
        if not widget.exists():
            raise UserError(_("Widget not found."))
        widget.dashboard_id._check_dashboard_access("read")
        return widget.get_widget_payload()

    def action_open_dashboard(self):
        self.ensure_one()
        self._check_dashboard_access("read")
        return {
            "type": "ir.actions.client",
            "tag": "kai_view_dashboard",
            "name": self.name,
            "params": {"dashboard_id": self.id},
        }

    @api.model
    def register_widgets_from_addon(self, dashboard_ref, widget_vals_list):
        """Helper for other addons: attach widgets to a dashboard xmlid.

        Usage from another module::

            self.env['kai.view.dashboard'].register_widgets_from_addon(
                'my_addon.dashboard_sales',
                [{'name': 'Open SO', 'widget_type': 'kpi', ...}],
            )
        """
        dashboard = self.env.ref(dashboard_ref, raise_if_not_found=False)
        if not dashboard:
            raise UserError(_("Dashboard reference %s was not found.") % dashboard_ref)
        Widget = self.env["kai.view.widget"]
        created = Widget.browse()
        for vals in widget_vals_list:
            vals = dict(vals, dashboard_id=dashboard.id)
            created |= Widget.create(vals)
        return created.ids
