/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { KaisightCountWidget } from "../widgets/count_widget";
import { KaisightChartWidget } from "../widgets/chart_widget";
import { KaisightListWidget } from "../widgets/list_widget";

/**
 * Build a window action dict that satisfies the web client's ``views`` requirement.
 */
function makeActWindowAction({
    name,
    res_model,
    res_id,
    domain,
    view_mode = "list,form",
    views,
    context,
    target = "current",
}) {
    const modes = view_mode
        .split(",")
        .map((m) => m.trim())
        .filter(Boolean);
    const action = {
        type: "ir.actions.act_window",
        name,
        res_model,
        view_mode: modes.join(",") || "list,form",
        views:
            views ||
            (modes.length === 1
                ? [[false, modes[0]]]
                : modes.map((mode) => [false, mode])),
        target,
    };
    if (res_id) {
        action.res_id = res_id;
    }
    if (domain) {
        action.domain = domain;
    }
    if (context) {
        action.context = context;
    }
    return action;
}

export class KaisightDashboardAction extends Component {
    static template = "kaisight.Dashboard";
    static components = {
        KaisightCountWidget: KaisightCountWidget,
        KaisightChartWidget: KaisightChartWidget,
        KaisightListWidget: KaisightListWidget,
    };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = useState({
            loading: true,
            dashboards: [],
            reports: [],
            dashboard: null,
            selectedDashboardId: null,
            error: null,
        });

        onWillStart(async () => {
            try {
                await this.loadMeta();
                const paramId = Number(this.props.action?.params?.dashboard_id) || null;
                const firstId = this.state.dashboards[0]?.id;
                const dashboardId = paramId || firstId;
                if (dashboardId) {
                    await this.selectDashboard(dashboardId);
                } else {
                    this.state.loading = false;
                }
            } catch (error) {
                this.state.error = error.message || String(error);
                this.state.loading = false;
            }
        });
    }

    async loadMeta() {
        const [dashboards, reports] = await Promise.all([
            this.orm.call("kai.view.dashboard", "get_dashboard_list", []),
            this.orm.call("kai.view.report", "get_report_list", []),
        ]);
        this.state.dashboards = Array.isArray(dashboards) ? dashboards : [];
        this.state.reports = Array.isArray(reports) ? reports : [];
    }

    async selectDashboard(dashboardId) {
        const dashboardIdNumber = Number(dashboardId);
        this.state.loading = true;
        this.state.error = null;
        this.state.selectedDashboardId = dashboardIdNumber;
        try {
            const payload = await this.orm.call(
                "kai.view.dashboard",
                "get_dashboard_payload",
                [dashboardIdNumber]
            );
            if (!payload || typeof payload !== "object") {
                throw new Error("Invalid dashboard response from server.");
            }
            this.state.dashboard = {
                ...payload,
                widgets: Array.isArray(payload.widgets) ? payload.widgets : [],
            };
        } catch (error) {
            this.state.error = error.message || String(error);
            this.state.dashboard = null;
        }
        this.state.loading = false;
    }

    async refreshDashboard() {
        if (this.state.selectedDashboardId) {
            await this.selectDashboard(this.state.selectedDashboardId);
        }
    }

    async refreshWidget(widgetId) {
        const widgetIdNumber = Number(widgetId);
        const updated = await this.orm.call("kai.view.dashboard", "refresh_widget", [
            widgetIdNumber,
        ]);
        if (!this.state.dashboard) {
            return;
        }
        const widgets = this.state.dashboard.widgets.map((w) =>
            w.id === widgetIdNumber ? updated : w
        );
        this.state.dashboard = { ...this.state.dashboard, widgets };
    }

    gridStyle(widget) {
        const width = Math.min(Math.max(Number(widget.grid?.width) || 4, 1), 12);
        const column = Math.min(Math.max(Number(widget.grid?.column) || 1, 1), 12);
        return `grid-column: ${column} / span ${width};`;
    }

    async openWidgetAction(widgetOrId) {
        const widgetId =
            typeof widgetOrId === "object" ? widgetOrId.id : widgetOrId;
        const widgetIdNumber = Number(widgetId);
        const action = await this.orm.call("kai.view.widget", "action_open_records", [
            [widgetIdNumber],
        ]);
        await this.actionService.doAction(action);
    }

    async openListRecord(widget, resId) {
        await this.actionService.doAction(
            makeActWindowAction({
                name: widget.name,
                res_model: widget.model,
                res_id: resId,
                view_mode: "form",
                views: [[false, "form"]],
            })
        );
    }

    async onReportClick(report) {
        const action = await this.orm.call("kai.view.report", "action_open_report", [
            [report.id],
        ]);
        await this.actionService.doAction(action);
    }

    openDashboardConfig() {
        return this.actionService.doAction("kaisight.action_kai_view_dashboards");
    }

    openReportsConfig() {
        return this.actionService.doAction("kaisight.action_kai_view_reports");
    }

    onDashboardChange(ev) {
        const id = Number(ev.target.value);
        if (!Number.isNaN(id) && id > 0) {
            this.selectDashboard(id);
        }
    }
}

registry.category("actions").add("kai_view_dashboard", KaisightDashboardAction);
