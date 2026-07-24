/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { Dialog } from "@web/core/dialog/dialog";

export class KaisightSaveReportDialog extends Component {
    static template = "kaisight.SaveReportDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        onSave: Function,
        defaultName: { type: String, optional: true },
    };

    setup() {
        this.state = useState({
            name: this.props.defaultName || "",
            isShared: false,
            saving: false,
            error: null,
        });
    }

    async onConfirm() {
        if (!this.state.name.trim()) {
            this.state.error = _t("Enter a report name.");
            return;
        }
        this.state.saving = true;
        this.state.error = null;
        try {
            await this.props.onSave(this.state.name.trim(), this.state.isShared);
            this.props.close();
        } catch (e) {
            this.state.error = e.message || _t("Could not save report.");
            this.state.saving = false;
        }
    }
}

export class KaisightAddSourceDialog extends Component {
    static template = "kaisight.AddSourceDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        onAdded: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            search: "",
            models: [],
            selectedModel: null,
            label: "",
            saving: false,
            error: null,
        });
        onWillStart(async () => {
            await this.loadModels();
        });
    }

    async loadModels() {
        this.state.loading = true;
        this.state.error = null;
        try {
            this.state.models = await this.orm.call(
                "kai.view.report.source",
                "get_model_catalog",
                [this.state.search]
            );
        } catch (e) {
            this.state.error = e.message || _t("Could not load models.");
        } finally {
            this.state.loading = false;
        }
    }

    async onSearchInput(ev) {
        this.state.search = ev.target.value;
        await this.loadModels();
    }

    selectModel(model) {
        this.state.selectedModel = model;
        this.state.label = model.name;
    }

    async onConfirm() {
        if (!this.state.selectedModel) {
            this.state.error = _t("Select a model / table.");
            return;
        }
        this.state.saving = true;
        this.state.error = null;
        try {
            const source = await this.orm.call("kai.view.report.source", "add_data_source", [
                this.state.selectedModel.model,
                this.state.label.trim() || this.state.selectedModel.name,
            ]);
            await this.props.onAdded(source);
            this.props.close();
        } catch (e) {
            this.state.error = e.message || _t("Could not add data source.");
            this.state.saving = false;
        }
    }
}

export class KaisightReportBuilderAction extends Component {
    static template = "kaisight.ReportBuilder";
    static components = { KaisightSaveReportDialog, KaisightAddSourceDialog };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            sources: [],
            canManageSources: false,
            selectedSource: null,
            fieldGroups: [],
            curatedFields: [],
            showAllFields: false,
            collapsedFieldGroups: {},
            filterCatalog: [],
            selectedFields: {},
            selectedOrder: [],
            savingCommonSet: false,
            dragFieldName: null,
            fieldSearch: "",
            quickFilters: {},
            domain: "[]",
            showFiltersPanel: true,
            recordCount: null,
            exporting: false,
            showSaveDialog: false,
            error: null,
        });

        onWillStart(async () => {
            await this.loadSources();
        });
    }

    async loadSources(preferSourceId = null) {
        this.state.loading = true;
        this.state.error = null;
        try {
            const catalog = await this.orm.call(
                "kai.view.report.builder",
                "get_source_catalog",
                []
            );
            // Backward compatible if an older server still returns a bare list.
            const sources = Array.isArray(catalog) ? catalog : catalog.sources || [];
            this.state.sources = sources;
            this.state.canManageSources = Array.isArray(catalog)
                ? false
                : !!catalog.can_manage_sources;

            const preferred =
                sources.find((s) => s.id === preferSourceId) ||
                (sources.length === 1 ? sources[0] : null) ||
                (this.state.selectedSource &&
                    sources.find((s) => s.id === this.state.selectedSource.id));
            if (preferred) {
                await this.selectSource(preferred);
            } else if (!sources.length) {
                this.state.selectedSource = null;
            }
        } catch (e) {
            this.state.error = e.message || _t("Could not load data sources.");
        } finally {
            this.state.loading = false;
        }
    }

    openAddSourceDialog() {
        this.dialog.add(KaisightAddSourceDialog, {
            onAdded: async (source) => {
                this.notification.add(_t("Data source added."), { type: "success" });
                await this.loadSources(source.id);
            },
        });
    }

    openManageSources() {
        this.actionService.doAction("kaisight.action_kai_view_report_sources");
    }

    async selectSource(source) {
        this.state.selectedSource = source;
        this.state.fieldSearch = "";
        this.state.domain = "[]";
        this.state.quickFilters = {};
        this.state.recordCount = null;
        this.state.collapsedFieldGroups = {};
        try {
            const catalog = await this.orm.call(
                "kai.view.report.builder",
                "get_field_catalog",
                [source.model]
            );
            this.state.fieldGroups = catalog.groups || [];

            const byName = {};
            for (const group of this.state.fieldGroups) {
                for (const field of group.fields || []) {
                    byName[field.name] = field;
                }
            }
            const curatedNames = source.default_fields || [];
            this.state.curatedFields = curatedNames
                .map((name) => byName[name])
                .filter(Boolean);
            this.state.showAllFields = this.state.curatedFields.length === 0;

            try {
                const filterCatalog = await this.orm.call(
                    "kai.view.report.builder",
                    "get_filter_catalog",
                    [source.model]
                );
                this.state.filterCatalog = filterCatalog.filters || [];
            } catch (filterError) {
                console.warn("Could not load quick filters", filterError);
                this.state.filterCatalog = [];
            }

            if (this.state.curatedFields.length) {
                this.applySelection(this.state.curatedFields.map((field) => field.name));
            } else {
                const firstGroup = this.state.fieldGroups[0];
                const pick = (firstGroup?.fields || []).slice(0, 6).map((f) => f.name);
                this.applySelection(pick);
            }
            await this.refreshCount();
        } catch (e) {
            this.state.error = e.message || _t("Could not load fields.");
        }
    }

    get hasCuratedFields() {
        return (this.state.curatedFields || []).length > 0;
    }

    get filteredGroups() {
        const q = (this.state.fieldSearch || "").trim().toLowerCase();
        const searching = !!q;

        // Curated mode: only the common columns unless expanded or searching.
        if (this.hasCuratedFields && !this.state.showAllFields && !searching) {
            return [
                {
                    id: "curated",
                    label: _t("Common columns"),
                    fields: this.state.curatedFields,
                },
            ];
        }

        const groups = this.state.fieldGroups;
        if (!searching) {
            return groups;
        }
        return groups
            .map((group) => ({
                ...group,
                fields: group.fields.filter(
                    (f) =>
                        f.label.toLowerCase().includes(q) ||
                        f.name.toLowerCase().includes(q)
                ),
            }))
            .filter((g) => g.fields.length);
    }

    // Single source of truth for the export column order is state.selectedOrder.
    // state.selectedFields is kept as a lookup map so checkbox rendering stays O(1).
    applySelection(names) {
        const seen = new Set();
        const order = [];
        for (const name of names) {
            if (name && !seen.has(name)) {
                seen.add(name);
                order.push(name);
            }
        }
        this.state.selectedOrder = order;
        this.state.selectedFields = Object.fromEntries(order.map((n) => [n, true]));
    }

    get selectedCount() {
        return this.state.selectedOrder.length;
    }

    get selectedFieldList() {
        return this.state.selectedOrder;
    }

    get selectedColumns() {
        const labels = {};
        for (const group of this.state.fieldGroups) {
            for (const field of group.fields || []) {
                labels[field.name] = field.label;
            }
        }
        return this.state.selectedOrder.map((name) => ({
            name,
            label: labels[name] || name,
        }));
    }

    isFieldSelected(name) {
        return !!this.state.selectedFields[name];
    }

    isFieldGroupCollapsed(groupId) {
        // Search results should always be visible, regardless of the saved group state.
        return !this.state.fieldSearch && !!this.state.collapsedFieldGroups[groupId];
    }

    toggleFieldGroup(groupId) {
        this.state.collapsedFieldGroups = {
            ...this.state.collapsedFieldGroups,
            [groupId]: !this.state.collapsedFieldGroups[groupId],
        };
    }

    expandAllFieldGroups() {
        this.state.collapsedFieldGroups = {};
    }

    collapseAllFieldGroups() {
        this.state.collapsedFieldGroups = Object.fromEntries(
            this.filteredGroups.map((group) => [group.id, true])
        );
    }

    toggleField(name) {
        if (this.state.selectedFields[name]) {
            this.applySelection(this.state.selectedOrder.filter((n) => n !== name));
        } else {
            this.applySelection([...this.state.selectedOrder, name]);
        }
    }

    removeSelected(name) {
        this.applySelection(this.state.selectedOrder.filter((n) => n !== name));
    }

    moveSelected(name, direction) {
        const order = [...this.state.selectedOrder];
        const index = order.indexOf(name);
        const target = index + direction;
        if (index === -1 || target < 0 || target >= order.length) {
            return;
        }
        [order[index], order[target]] = [order[target], order[index]];
        this.applySelection(order);
    }

    onColumnDragStart(name, ev) {
        this.state.dragFieldName = name;
        if (ev.dataTransfer) {
            ev.dataTransfer.effectAllowed = "move";
            // Firefox requires data to be set for the drag to start.
            ev.dataTransfer.setData("text/plain", name);
        }
    }

    onColumnDragOver(ev) {
        ev.preventDefault();
        if (ev.dataTransfer) {
            ev.dataTransfer.dropEffect = "move";
        }
    }

    onColumnDrop(targetName, ev) {
        ev.preventDefault();
        const dragged = this.state.dragFieldName;
        this.state.dragFieldName = null;
        if (!dragged || dragged === targetName) {
            return;
        }
        const order = this.state.selectedOrder.filter((n) => n !== dragged);
        const targetIndex = order.indexOf(targetName);
        if (targetIndex === -1) {
            order.push(dragged);
        } else {
            order.splice(targetIndex, 0, dragged);
        }
        this.applySelection(order);
    }

    onColumnDragEnd() {
        this.state.dragFieldName = null;
    }

    async saveCommonSet() {
        if (!this.state.canManageSources || !this.state.selectedSource) {
            return;
        }
        if (!this.selectedCount) {
            this.notification.add(_t("Select at least one column first."), {
                type: "warning",
            });
            return;
        }
        this.state.savingCommonSet = true;
        try {
            const result = await this.orm.call(
                "kai.view.report.builder",
                "set_source_default_fields",
                [this.state.selectedSource.id, this.selectedFieldList]
            );
            const defaults = result?.default_fields || this.selectedFieldList;
            this.state.selectedSource.default_fields = defaults;
            const byName = {};
            for (const group of this.state.fieldGroups) {
                for (const field of group.fields || []) {
                    byName[field.name] = field;
                }
            }
            this.state.curatedFields = defaults.map((name) => byName[name]).filter(Boolean);
            this.notification.add(_t("Common columns saved as the default."), {
                type: "success",
            });
        } catch (error) {
            this.notification.add(
                error.message || _t("Could not save the common columns."),
                { type: "danger" }
            );
        } finally {
            this.state.savingCommonSet = false;
        }
    }

    toggleShowAllFields() {
        this.state.showAllFields = !this.state.showAllFields;
        if (!this.state.showAllFields) {
            this.state.fieldSearch = "";
        }
    }

    selectRecommended() {
        const curated = this.state.curatedFields || [];
        if (curated.length) {
            this.applySelection(curated.map((field) => field.name));
            this.state.showAllFields = false;
            this.state.fieldSearch = "";
            return;
        }
        const defaults = this.state.selectedSource?.default_fields || [];
        if (defaults.length) {
            this.applySelection(defaults);
        } else {
            this.selectAllVisible();
        }
    }

    selectAllVisible() {
        const names = [...this.state.selectedOrder];
        for (const group of this.filteredGroups) {
            for (const field of group.fields) {
                names.push(field.name);
            }
        }
        this.applySelection(names);
    }

    clearSelection() {
        this.applySelection([]);
    }

    toggleFiltersPanel() {
        this.state.showFiltersPanel = !this.state.showFiltersPanel;
    }

    get hasActiveFilters() {
        const quick = Object.values(this.state.quickFilters).some(
            (v) => v !== undefined && v !== null && v !== ""
        );
        const advanced = (this.state.domain || "[]").trim() !== "[]";
        return quick || advanced;
    }

    get activeFilterCount() {
        let count = Object.values(this.state.quickFilters).filter(
            (v) => v !== undefined && v !== null && v !== ""
        ).length;
        if ((this.state.domain || "[]").trim() !== "[]") {
            count += 1;
        }
        return count;
    }

    async onQuickFilterChange(fieldName, value) {
        const next = { ...this.state.quickFilters };
        if (value === "" || value === null || value === undefined) {
            delete next[fieldName];
        } else {
            next[fieldName] = value;
        }
        this.state.quickFilters = next;
        await this.refreshCount();
    }

    async clearAllFilters() {
        this.state.quickFilters = {};
        this.state.domain = "[]";
        await this.refreshCount();
    }

    filterSelectValue(fieldName) {
        const value = this.state.quickFilters[fieldName];
        return value === undefined || value === null ? "" : String(value);
    }

    filterTextValue(fieldName) {
        return this.state.quickFilters[fieldName] || "";
    }

    async onQuickFilterText(fieldName, ev) {
        await this.onQuickFilterChange(fieldName, ev.target.value.trim());
    }

    async refreshCount() {
        if (!this.state.selectedSource) {
            return;
        }
        this.state.recordCount = await this.orm.call(
            "kai.view.report.builder",
            "preview_record_count",
            [this.state.selectedSource.model, this.state.domain],
            { quick_filters: this.state.quickFilters }
        );
    }

    async openFilters() {
        const builderId = await this.orm.call(
            "kai.view.report.builder",
            "create_filter_wizard",
            [this.state.selectedSource.model, this.state.domain]
        );
        const [, filterViewId] = await this.orm.call(
            "ir.model.data",
            "check_object_reference",
            ["kaisight", "view_kai_view_report_builder_filter_form"]
        );
        this.actionService.doAction(
            {
                type: "ir.actions.act_window",
                name: _t("Report filters"),
                res_model: "kai.view.report.builder",
                res_id: builderId,
                views: [[filterViewId, "form"]],
                target: "new",
            },
            {
                onClose: async () => {
                    const record = await this.orm.read(
                        "kai.view.report.builder",
                        [builderId],
                        ["domain"]
                    );
                    if (record.length) {
                        this.state.domain = record[0].domain || "[]";
                        await this.refreshCount();
                    }
                    await this.orm.unlink("kai.view.report.builder", [builderId]);
                },
            }
        );
    }

    async exportReport(format) {
        if (!this.selectedCount) {
            this.notification.add(_t("Select at least one column."), { type: "warning" });
            return;
        }
        this.state.exporting = true;
        try {
            const action = await this.orm.call(
                "kai.view.report.builder",
                "export_report",
                [
                    this.state.selectedSource.model,
                    this.selectedFieldList,
                    this.state.domain,
                    format,
                ],
                {
                    quick_filters: this.state.quickFilters,
                    report_title: this.state.selectedSource.name,
                }
            );
            await this.actionService.doAction(action);
            this.notification.add(_t("Export started."), { type: "success" });
        } catch (e) {
            this.notification.add(e.message || _t("Export failed."), { type: "danger" });
        } finally {
            this.state.exporting = false;
        }
    }

    async openInOdoo() {
        if (!this.selectedCount) {
            this.notification.add(_t("Select at least one column."), { type: "warning" });
            return;
        }
        try {
            const action = await this.orm.call(
                "kai.view.report.builder",
                "action_open_in_odoo",
                [
                    this.state.selectedSource.model,
                    this.selectedFieldList,
                    this.state.domain,
                    this.state.selectedSource.name,
                ],
                { quick_filters: this.state.quickFilters }
            );
            await this.actionService.doAction(action);
        } catch (e) {
            this.notification.add(e.message || _t("Could not open report."), { type: "danger" });
        }
    }

    openSaveDialog() {
        if (!this.selectedCount) {
            this.notification.add(_t("Select at least one column."), { type: "warning" });
            return;
        }
        this.dialog.add(KaisightSaveReportDialog, {
            defaultName: this.state.selectedSource?.name || "",
            onSave: this.saveReport.bind(this),
        });
    }

    async saveReport(name, isShared) {
        await this.orm.call("kai.view.report.builder", "save_report", [], {
            name,
            model_name: this.state.selectedSource.model,
            field_names: this.selectedFieldList,
            domain_str: this.state.domain,
            is_shared: isShared,
            quick_filters: this.state.quickFilters,
        });
        this.notification.add(_t("Report saved."), { type: "success" });
    }

    async openSavedReports() {
        const [, actionId] = await this.orm.call(
            "ir.model.data",
            "check_object_reference",
            ["kaisight", "action_kai_view_reports"]
        );
        const action = await this.actionService.loadAction(actionId);
        await this.actionService.doAction(action);
    }
}

registry.category("actions").add("kai_view_report_builder", KaisightReportBuilderAction);
