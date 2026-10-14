/*
 * Αίτηση Παραρτήματος 3: εμφάνιση ενοτήτων ανά κατηγορία διαμονής / οικογενειακή κατάσταση,
 * προσθήκη γραμμών (τέκνα, διακοπές διαμονής) και σύνολα εισοδημάτων.
 */
(function () {
    "use strict";

    const form = document.querySelector("[data-plot-application-form]");
    if (!form) return;

    function fieldValue(name) {
        const checked = form.querySelector(`[name="${name}"]:checked`);
        if (checked) return checked.value;
        const input = form.querySelector(`[name="${name}"]:not([type="radio"])`);
        return input ? input.value : "";
    }

    // data-show-when="field=a,b|other=c": visible when any condition matches.
    function matches(rule) {
        return rule.split("|").some((part) => {
            const [name, values] = part.split("=");
            return values.split(",").includes(fieldValue(name));
        });
    }

    function refreshVisibility() {
        form.querySelectorAll("[data-show-when]").forEach((block) => {
            block.hidden = !matches(block.dataset.showWhen);
        });
    }

    // Ενότ. 11 (Ι, ΙΙ, ΙV): Αυτόχθονας / Εκτοπισθείς / Επαναπατρισθείς διαμένουν στην Κοινότητα της αίτησης,
    // οπότε η Κοινότητα διαμονής κλειδώνει σε αυτήν· για τους υπόλοιπους παραμένει ελεύθερη.
    const LOCKED_CATEGORIES = ["autochthon", "displaced", "repatriated"];
    const communityNamesEl = document.getElementById("community-names");
    const communityNames = communityNamesEl ? JSON.parse(communityNamesEl.textContent) : {};

    function syncResidenceCommunity() {
        const input = form.querySelector('[name="main-residence_community"]');
        if (!input) return;
        if (LOCKED_CATEGORIES.includes(fieldValue("main-residence_category"))) {
            input.value = communityNames[fieldValue("main-community")] || "";
            input.readOnly = true;
        } else if (input.readOnly) {
            input.readOnly = false;
            input.value = "";
        }
    }

    function toNumber(input) {
        const value = parseFloat((input && input.value) || "0");
        return Number.isFinite(value) ? value : 0;
    }

    function refreshIncomeTotals() {
        let family = 0;
        form.querySelectorAll("[data-income-block]").forEach((block) => {
            let total = 0;
            block.querySelectorAll('input[name$="gross_annual_income"], input[name$="_amount"]').forEach((input) => {
                total += toNumber(input);
            });
            block.querySelector("[data-income-total]").textContent = total.toFixed(2);
            if (!block.hidden) family += total;
        });
        const familyEl = form.querySelector("[data-family-income-total]");
        if (familyEl) familyEl.textContent = family.toFixed(2);
    }

    form.querySelectorAll("[data-formset]").forEach((container) => {
        const prefix = container.dataset.formset;
        const total = container.querySelector(`#id_${prefix}-TOTAL_FORMS`);
        const template = container.querySelector("[data-formset-template]");
        const rows = container.querySelector("[data-formset-rows]");
        container.querySelector("[data-formset-add]").addEventListener("click", () => {
            const index = parseInt(total.value, 10);
            const html = template.innerHTML.replace(/__prefix__/g, String(index));
            rows.insertAdjacentHTML("beforeend", html);
            total.value = String(index + 1);
        });
    });

    form.addEventListener("change", () => {
        syncResidenceCommunity();
        refreshVisibility();
        refreshIncomeTotals();
    });
    form.addEventListener("input", refreshIncomeTotals);
    syncResidenceCommunity();
    refreshVisibility();
    refreshIncomeTotals();
})();
