# -*- coding: utf-8 -*-
"""Install/upgrade helpers for kaisight."""
import logging

_logger = logging.getLogger(__name__)

_ACCESS_RULES = (
    # name, model technical name, group xmlid, perm_read, write, create, unlink
    ("kai.view.report.source user", "kai.view.report.source", "kaisight.group_kai_view_user", 1, 0, 0, 0),
    ("kai.view.report.source manager", "kai.view.report.source", "kaisight.group_kai_view_manager", 1, 1, 1, 1),
    ("kai.view.report.builder user", "kai.view.report.builder", "kaisight.group_kai_view_user", 1, 1, 1, 1),
    ("kai.view.report.builder manager", "kai.view.report.builder", "kaisight.group_kai_view_manager", 1, 1, 1, 1),
)


def _ensure_model_access(env):
    """Create missing ACL rows by model name (works even if model XML IDs differ)."""
    Access = env["ir.model.access"].sudo()
    Model = env["ir.model"].sudo()
    for name, model_name, group_xmlid, perm_r, perm_w, perm_c, perm_u in _ACCESS_RULES:
        ir_model = Model.search([("model", "=", model_name)], limit=1)
        if not ir_model:
            _logger.warning(
                "kaisight: model %s not registered yet; skipping ACL %s",
                model_name,
                name,
            )
            continue
        group = env.ref(group_xmlid, raise_if_not_found=False)
        if not group:
            continue
        existing = Access.search(
            [
                ("model_id", "=", ir_model.id),
                ("group_id", "=", group.id),
            ],
            limit=1,
        )
        vals = {
            "name": name,
            "model_id": ir_model.id,
            "group_id": group.id,
            "perm_read": perm_r,
            "perm_write": perm_w,
            "perm_create": perm_c,
            "perm_unlink": perm_u,
        }
        if existing:
            existing.write(vals)
            # Remove accidental duplicates from earlier upgrades.
            extras = Access.search(
                [
                    ("model_id", "=", ir_model.id),
                    ("group_id", "=", group.id),
                    ("id", "!=", existing.id),
                ]
            )
            if extras:
                extras.unlink()
        else:
            Access.create(vals)


def post_init_hook(env):
    """Ensure Report Builder ACL exists after a fresh install (Odoo 19 env signature)."""
    _ensure_model_access(env)
    _logger.info("kaisight: post-init access rules verified.")
