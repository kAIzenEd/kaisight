/** @odoo-module **/

import { Component } from "@odoo/owl";

export class KaisightListWidget extends Component {
    static template = "kaisight.ListWidget";
    static props = {
        widget: Object,
        onOpenRecord: { type: Function, optional: true },
        onOpenAll: { type: Function, optional: true },
        onRefresh: { type: Function, optional: true },
    };

    get columns() {
        return this.props.widget?.data?.columns || [];
    }

    get rows() {
        return this.props.widget?.data?.rows || [];
    }

    get hasError() {
        return Boolean(this.props.widget?.error);
    }
}
