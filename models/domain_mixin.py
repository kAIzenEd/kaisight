# -*- coding: utf-8 -*-
import ast

from odoo import _, api, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval


class KaiViewDomainMixin(models.AbstractModel):
    _name = "kai.view.domain.mixin"
    _description = "kaisight domain helpers"

    @api.model
    def _parse_domain_string(self, domain_str, label=_("Filter")):
        """Parse a domain stored on a Char field (Python literal from the domain widget)."""
        text = (domain_str or "[]").strip()
        if not text:
            return []
        try:
            domain = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            try:
                domain = safe_eval(text)
            except Exception as exc:
                raise ValidationError(
                    _("%(label)s is not valid: %(error)s") % {"label": label, "error": exc}
                ) from exc
        if not isinstance(domain, list):
            raise ValidationError(_("%s must be a list.") % label)
        return domain

    @api.model
    def validate_target_domain(self, model_name, domain_str):
        """Used by the UI to validate filters against the target model.

        Returns True when valid. Raises ValidationError with a clear message otherwise.
        """
        if not model_name:
            raise ValidationError(_("Select a model before configuring the filter."))
        if model_name not in self.env:
            raise ValidationError(
                _("Model “%s” is not available in your database.") % model_name
            )
        domain = self._parse_domain_string(domain_str)
        try:
            self.env[model_name].sudo()._search(domain)
        except Exception as exc:
            raise ValidationError(
                _("Filter is not valid for model “%(model)s”: %(error)s")
                % {"model": model_name, "error": exc}
            ) from exc
        return True
