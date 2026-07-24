# -*- coding: utf-8 -*-
import base64
import logging
from calendar import monthrange
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class KaisightReportSchedule(models.Model):
    _name = "kai.view.report.schedule"
    _description = "kaisight Scheduled Report Export"
    _order = "name, id"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    report_id = fields.Many2one(
        "kai.view.report",
        string="Saved Report",
        required=True,
        ondelete="cascade",
        index=True,
    )
    model_id = fields.Many2one(
        related="report_id.model_id",
        string="Data",
        store=True,
        readonly=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Owner",
        required=True,
        default=lambda self: self.env.user,
        index=True,
        help="Exports run with this user's access rights.",
    )

    interval_type = fields.Selection(
        [
            ("daily", "Every day"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
        ],
        string="Frequency",
        required=True,
        default="monthly",
    )
    weekday = fields.Selection(
        [
            ("0", "Monday"),
            ("1", "Tuesday"),
            ("2", "Wednesday"),
            ("3", "Thursday"),
            ("4", "Friday"),
            ("5", "Saturday"),
            ("6", "Sunday"),
        ],
        string="Day of week",
        default="0",
    )
    day_of_month = fields.Integer(
        string="Day of month",
        default=1,
        help="Day of the month to generate the file (1–28 recommended).",
    )
    use_last_day = fields.Boolean(
        string="Last day of month",
        help="If set, ignore Day of month and run on the last calendar day.",
    )

    export_format = fields.Selection(
        [
            ("xlsx", "Excel (.xlsx)"),
            ("csv", "CSV"),
            ("pdf", "PDF"),
        ],
        string="File format",
        required=True,
        default="xlsx",
    )
    store_file = fields.Boolean(
        string="Save for download",
        default=True,
        help="Keep each generated file under Generated Reports.",
    )
    send_email = fields.Boolean(
        string="Send by email",
        default=True,
    )
    partner_ids = fields.Many2many(
        "res.partner",
        "kai_view_report_schedule_partner_rel",
        "schedule_id",
        "partner_id",
        string="Email recipients",
        help="Partners who receive the exported file by email.",
    )

    last_run_date = fields.Date(string="Last run date", readonly=True)
    last_run_id = fields.Many2one(
        "kai.view.report.run",
        string="Last generated file",
        readonly=True,
        ondelete="set null",
    )
    run_ids = fields.One2many(
        "kai.view.report.run",
        "schedule_id",
        string="Generated files",
    )
    run_count = fields.Integer(compute="_compute_run_count")

    @api.depends("run_ids")
    def _compute_run_count(self):
        for rec in self:
            rec.run_count = len(rec.run_ids)

    @api.onchange("report_id")
    def _onchange_report_id(self):
        if self.report_id and not self.name:
            self.name = _("Schedule: %s") % self.report_id.name

    @api.onchange("user_id")
    def _onchange_user_id_default_partner(self):
        if self.user_id and self.user_id.partner_id and not self.partner_ids:
            self.partner_ids = self.user_id.partner_id

    @api.constrains("day_of_month", "use_last_day", "interval_type")
    def _check_day_of_month(self):
        for rec in self:
            if rec.interval_type != "monthly" or rec.use_last_day:
                continue
            if not (1 <= rec.day_of_month <= 28):
                raise UserError(
                    _("Day of month must be between 1 and 28 "
                      "(or enable “Last day of month”).")
                )

    @api.constrains("send_email", "partner_ids", "store_file")
    def _check_delivery(self):
        for rec in self:
            if not rec.store_file and not rec.send_email:
                raise UserError(
                    _("Enable “Save for download” and/or “Send by email”.")
                )
            if rec.send_email and not rec.partner_ids:
                raise UserError(
                    _("Add at least one email recipient, or turn off email.")
                )

    def _should_run_on(self, run_date):
        self.ensure_one()
        if not self.active or not self.report_id:
            return False
        if self.last_run_date == run_date:
            return False
        if self.interval_type == "daily":
            return True
        if self.interval_type == "weekly":
            return str(run_date.weekday()) == (self.weekday or "0")
        # monthly
        if self.use_last_day:
            last = monthrange(run_date.year, run_date.month)[1]
            return run_date.day == last
        return run_date.day == (self.day_of_month or 1)

    def action_run_now(self):
        """Manually generate the file (same path as the nightly cron)."""
        for schedule in self:
            schedule._execute(force=True)
        msg = _("The file is ready under Generated Reports.")
        if any(self.mapped("send_email")):
            msg = _(
                "The file is ready under Generated Reports and was emailed "
                "to the recipients."
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Report generated"),
                "message": msg,
                "type": "success",
                "sticky": False,
            },
        }

    def action_open_runs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Generated Reports"),
            "res_model": "kai.view.report.run",
            "view_mode": "list,form",
            "domain": [("schedule_id", "=", self.id)],
            "context": {"default_schedule_id": self.id},
        }

    def _execute(self, force=False):
        self.ensure_one()
        today = fields.Date.context_today(self)
        if not force and not self._should_run_on(today):
            return False

        report = self.report_id
        if not report:
            raise UserError(_("This schedule has no saved report."))

        # Run with the owner's rights so record rules apply correctly.
        user = self.user_id or self.env.user
        report_as_user = report.with_user(user).sudo(False)
        report_as_user._check_report_access("read")

        builder = self.env["kai.view.report.builder"].with_user(user)
        filename, content, mimetype = builder.build_export_file(
            report.model_name,
            report_as_user._export_field_names(),
            domain_str=report.domain or "[]",
            export_format=self.export_format,
            report_title=report.name,
        )

        run = self.env["kai.view.report.run"].sudo().create(
            {
                "name": _("%s — %s") % (report.name, fields.Datetime.now()),
                "schedule_id": self.id,
                "report_id": report.id,
                "user_id": user.id,
                "export_format": self.export_format,
                "state": "done",
                "row_count": 0,
            }
        )

        attachment = self.env["ir.attachment"].sudo().create(
            {
                "name": filename,
                "type": "binary",
                "datas": base64.b64encode(content),
                "mimetype": mimetype,
                "res_model": "kai.view.report.run",
                "res_id": run.id,
            }
        )
        run.sudo().write(
            {
                "attachment_id": attachment.id,
                "filename": filename,
            }
        )

        if not self.store_file:
            # Still keep the run row for audit, but drop the linked file later
            # only if email is the sole delivery — keep attachment until mailed.
            pass

        emailed = False
        if self.send_email:
            emailed = run._send_email(self.partner_ids)
            run.sudo().write({"email_sent": emailed})

        if not self.store_file and attachment:
            # Email has its own copies; remove stored download if not requested.
            attachment.sudo().unlink()
            run.sudo().write({"attachment_id": False, "filename": filename})

        self.sudo().write(
            {
                "last_run_date": today,
                "last_run_id": run.id,
            }
        )
        return run

    @api.model
    def _cron_run_due_schedules(self):
        today = fields.Date.context_today(self)
        due = self.search([("active", "=", True)])
        for schedule in due:
            try:
                if schedule._should_run_on(today):
                    schedule._execute()
            except Exception:
                _logger.exception(
                    "kaisight schedule %s failed", schedule.id
                )
                self.env["kai.view.report.run"].sudo().create(
                    {
                        "name": _("FAILED — %s") % (schedule.name or schedule.id),
                        "schedule_id": schedule.id,
                        "report_id": schedule.report_id.id,
                        "user_id": schedule.user_id.id,
                        "export_format": schedule.export_format,
                        "state": "failed",
                        "error_message": _(
                            "Generation failed. Check the server log."
                        ),
                    }
                )


class KaisightReportRun(models.Model):
    _name = "kai.view.report.run"
    _description = "kaisight Generated Report File"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True)
    schedule_id = fields.Many2one(
        "kai.view.report.schedule",
        string="Schedule",
        ondelete="set null",
        index=True,
    )
    report_id = fields.Many2one(
        "kai.view.report",
        string="Saved Report",
        required=True,
        ondelete="cascade",
        index=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Generated for",
        required=True,
        default=lambda self: self.env.user,
        index=True,
    )
    export_format = fields.Selection(
        [
            ("xlsx", "Excel"),
            ("csv", "CSV"),
            ("pdf", "PDF"),
        ],
        default="xlsx",
        required=True,
    )
    state = fields.Selection(
        [
            ("done", "Ready"),
            ("failed", "Failed"),
        ],
        default="done",
        required=True,
    )
    error_message = fields.Text(readonly=True)
    attachment_id = fields.Many2one(
        "ir.attachment",
        string="File",
        ondelete="set null",
        copy=False,
    )
    filename = fields.Char()
    datas = fields.Binary(
        related="attachment_id.datas",
        string="Download",
        readonly=True,
    )
    email_sent = fields.Boolean(string="Emailed", readonly=True)
    row_count = fields.Integer(readonly=True)
    create_date = fields.Datetime(readonly=True)

    def action_download(self):
        self.ensure_one()
        if not self.attachment_id:
            raise UserError(_("No file is stored for this run."))
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % self.attachment_id.id,
            "target": "self",
        }

    def _send_email(self, partners):
        self.ensure_one()
        partners = partners.filtered(lambda p: p.email)
        if not partners or not self.attachment_id:
            return False
        report_name = self.report_id.name or self.name
        body = _(
            "<p>Your scheduled kaisight report <strong>%s</strong> "
            "is attached.</p><p>Generated on %s.</p>"
        ) % (
            report_name,
            fields.Datetime.to_string(self.create_date or fields.Datetime.now()),
        )
        # mail.mail copies attachments; unlink=False keeps our stored file.
        mail = self.env["mail.mail"].sudo().create(
            {
                "subject": _("Scheduled report: %s") % report_name,
                "body_html": body,
                "email_to": ",".join(partners.mapped("email")),
                "auto_delete": True,
                "attachment_ids": [(4, self.attachment_id.id)],
            }
        )
        mail.send()
        return True
