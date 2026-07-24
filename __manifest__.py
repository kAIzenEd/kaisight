# -*- coding: utf-8 -*-
{
    "name": "kaisight",
    "version": "19.0.1.1.19",
    "category": "Productivity/Reporting",
    "summary": "Interactive dashboards and saved reports for any Odoo model",
    "description": """
kaisight provides lightweight, interactive dashboards and saved report definitions
that work with any installed addon model via the ORM (search_read / read_group).

Other addons can ship predefined dashboards and widgets through XML data or
create them programmatically on ``kai.view.dashboard``.

Administrators can also pick any readable model (custom or native) as a Report
Builder data source after install — no hardcoded school fields required.
    """,
    "author": "Kaiddons",
    "license": "LGPL-3",
    "depends": ["base", "web", "mail"],
    "data": [
        "security/kai_view_security.xml",
        "security/ir.model.access.csv",
        "security/ir_model_access_report_builder.xml",
        "security/ir_model_access_meta.xml",
        "data/demo_dashboard.xml",
        "data/report_schedule_cron.xml",
        "views/report_views.xml",
        "views/report_schedule_views.xml",
        "views/report_builder_views.xml",
        "report/export_report_templates.xml",
        "views/dashboard_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            ("include", "web.chartjs_lib"),
            "kaisight/static/src/fields/kai_domain_field.js",
            "kaisight/static/src/widgets/count_widget.xml",
            "kaisight/static/src/widgets/chart_widget.xml",
            "kaisight/static/src/widgets/list_widget.xml",
            "kaisight/static/src/dashboard_action/dashboard.xml",
            "kaisight/static/src/dashboard_action/dashboard.scss",
            "kaisight/static/src/widgets/count_widget.js",
            "kaisight/static/src/widgets/chart_widget.js",
            "kaisight/static/src/widgets/list_widget.js",
            "kaisight/static/src/dashboard_action/dashboard.js",
            "kaisight/static/src/report_builder/report_builder.xml",
            "kaisight/static/src/report_builder/report_builder.scss",
            "kaisight/static/src/report_builder/report_builder.js",
            "kaisight/static/src/reports/saved_reports.scss",
        ],
    },
    "application": True,
    "installable": True,
    "icon": "static/description/icon.svg",
    "post_init_hook": "hooks.post_init_hook",
}
