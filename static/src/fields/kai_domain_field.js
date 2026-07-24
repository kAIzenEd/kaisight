/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { DomainField } from "@web/views/fields/domain/domain_field";

const KAI_DOMAIN_MODELS = new Set(["kai.view.widget", "kai.view.report"]);

/**
 * On widget/report forms, validate filters with kaisight's server helper so users
 * get a clear error instead of a generic “Domain is invalid”.
 */
patch(DomainField.prototype, {
    async checkProps(props = this.props) {
        if (!KAI_DOMAIN_MODELS.has(props.record.resModel)) {
            return super.checkProps(props);
        }
        const resModel = this.getResModel(props);
        if (!resModel) {
            this.updateState({ isValid: false, recordCount: 0, hasLimitedCount: false });
            return;
        }
        const domain = this.getEvaluatedDomain(props);
        if (domain.isInvalid) {
            this.updateState({ isValid: false, recordCount: 0, hasLimitedCount: false });
            return;
        }
        try {
            await this.orm.call(props.record.resModel, "validate_target_domain", [
                resModel,
                this.getDomain(props),
            ]);
        } catch (error) {
            const message =
                error.data?.message ||
                error.message ||
                _t("Filter is not valid for this model.");
            this.notification.add(message, { type: "danger" });
            this.updateState({ isValid: false, recordCount: 0, hasLimitedCount: false });
            return;
        }
        return super.checkProps(props);
    },
});
