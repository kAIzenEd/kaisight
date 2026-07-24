/** @odoo-module **/

import { Component } from "@odoo/owl";
import { formatFloat, humanNumber } from "@web/core/utils/numbers";

export class KaisightCountWidget extends Component {
    static template = "kaisight.CountWidget";
    static props = {
        widget: Object,
        onOpen: { type: Function, optional: true },
        onRefresh: { type: Function, optional: true },
    };

    get displayValue() {
        const raw = this.props.widget?.data?.value;
        if (raw === undefined || raw === null || raw === "") {
            return "—";
        }
        const value = Number(raw);
        if (Number.isNaN(value)) {
            return String(raw);
        }
        const aggregate = this.props.widget?.data?.aggregate || "count";
        try {
            if (aggregate === "count") {
                return humanNumber(value, { decimals: 0, minDigits: 1 });
            }
            return formatFloat(value, { digits: [false, 2] });
        } catch {
            return String(raw);
        }
    }

    get hasError() {
        return Boolean(this.props.widget?.error);
    }
}
