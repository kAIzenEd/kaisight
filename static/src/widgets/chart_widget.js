/** @odoo-module **/

import { loadBundle } from "@web/core/assets";
import { getColor } from "@web/core/colors/colors";
import { cookie } from "@web/core/browser/cookie";
import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";

export class KaisightChartWidget extends Component {
    static template = "kaisight.ChartWidget";
    static props = {
        widget: Object,
        onRefresh: { type: Function, optional: true },
    };

    setup() {
        this.canvasRef = useRef("canvas");
        this.state = useState({ assetsError: null });
        this.chart = null;
        onWillStart(async () => {
            try {
                await loadBundle("web.chartjs_lib");
            } catch (_error) {
                this.state.assetsError = "Chart library could not be loaded (offline or missing asset).";
            }
        });
        useEffect(
            () => {
                this.renderChart();
                return () => {
                    if (this.chart) {
                        this.chart.destroy();
                        this.chart = null;
                    }
                };
            },
            () => [this.props.widget.data, this.props.widget.error]
        );
    }

    get hasError() {
        return Boolean(this.props.widget?.error || this.state.assetsError);
    }

    get errorMessage() {
        return this.props.widget?.error || this.state.assetsError || "";
    }

    renderChart() {
    if (this.hasError || !this.canvasRef.el) {
        return;
    }
    const Chart = window.Chart;
    if (!Chart) {
        this.state.assetsError = "Chart library is not available.";
        return;
    }

    const data = this.props.widget.data || {};
    const labels = Array.isArray(data.labels) ? data.labels : [];
    const values = Array.isArray(data.values) ? data.values : [];

    if (!labels.length || values.length !== labels.length) {
        return;
    }

    if (this.chart) {
        this.chart.destroy();
    }

    const scheme = cookie.get("color_scheme");
    const colorIndex = data.color_index || 1;
    const baseColor = getColor(colorIndex, scheme, "odoo");
    const palette = Array.from({ length: Math.max(labels.length, 1) }, (_, i) =>
        getColor(((colorIndex + i - 1) % 12) + 1, scheme, "odoo")
    );

    const chartType = data.chart_type || "bar";
    const isPie = chartType === "pie" || chartType === "doughnut";
    const dataset = {
        label: this.props.widget.name,
        data: values,
        backgroundColor: isPie ? palette : baseColor,
        borderColor: isPie ? palette : baseColor,
        borderWidth: isPie ? 1 : 0,
        borderRadius: isPie ? 0 : 4,
    };

    this.chart = new Chart(this.canvasRef.el, {
        type: chartType,
        data: { labels, datasets: [dataset] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: isPie, position: "bottom" },
            },
            scales: isPie
                ? {}
                : {
                      x: { grid: { display: false } },
                      y: { beginAtZero: true, ticks: { precision: 0 } },
                  },
                },
        }   );
    }
}
