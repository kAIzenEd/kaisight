# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    views = env["ir.ui.view"].sudo().search(
        [
            ("type", "=", "list"),
            ("name", "ilike", "kaisight report"),
        ]
    )
    if views:
        views.write({"priority": 999})
        _logger.info(
            "Set priority=999 on %s kaisight report list view(s).",
            len(views),
        )
