/*
 * Αίτηση Παραρτήματος 3: εμφάνιση ενοτήτων ανά κατηγορία διαμονής / οικογενειακή κατάσταση,
 * προσθήκη και επεξεργασία γραμμών (τέκνα, εισοδήματα) σε modal με έλεγχο εγκυρότητας,
 * και αυτόματος υπολογισμός συνόλων εισοδημάτων / δικαιολογητικών.
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
        ["applicant_party", "spouse_party"].forEach((prefix) => {
            const isOther = fieldValue(`${prefix}-citizenship`) === "other";
            const input = form.querySelector(`[name="${prefix}-citizenship_other"]`);
            const label = form.querySelector(`label[for="id_${prefix}-citizenship_other"]`);
            if (input) input.required = isOther;
            if (label) label.classList.toggle("required", true);
        });
    }

    // Ενότ. 11 (Ι, ΙΙ, ΙV): Αυτόχθονας / Εκτοπισθείς / Επαναπατρισθείς διαμένουν στην Κοινότητα της αίτησης,
    // οπότε η Κοινότητα διαμονής κλειδώνει σε αυτήν· για τους υπόλοιπους παραμένει ελεύθερη.
    const LOCKED_CATEGORIES = ["autochthon", "displaced", "repatriated"];
    const communityNamesEl = document.getElementById("community-names");
    const communityNames = communityNamesEl ? JSON.parse(communityNamesEl.textContent) : {};
    const incomeParamsEl = document.getElementById("income-parameters");
    const incomeParams = incomeParamsEl
        ? JSON.parse(incomeParamsEl.textContent)
        : {
              limits: { 2: "45000", 3: "50000", 4: "55000", 5: "65000" },
              minor_max_age: 18,
              student_max_age_female: 23,
              student_max_age_male: 25,
              large_family_children: 4,
          };
    const FAMILY_STATUS_LABELS = {
        couple_with_children: "Ζεύγος με τέκνα",
        couple_without_children: "Ζεύγος χωρίς τέκνα",
        single_parent: "Μονογονεϊκή οικογένεια",
    };

    function announcementFieldName() {
        return form.querySelector('[name="main-announcement"]') ? "main-announcement" : "main-community";
    }

    function syncResidenceCommunity() {
        const input = form.querySelector('[name="main-residence_community"]');
        if (!input) return;
        if (LOCKED_CATEGORIES.includes(fieldValue("main-residence_category"))) {
            input.value = communityNames[fieldValue(announcementFieldName())] || "";
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

    function parseIsoDate(value) {
        const match = (value || "").trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (!match) return null;
        const year = parseInt(match[1], 10);
        const month = parseInt(match[2], 10);
        const day = parseInt(match[3], 10);
        if (month < 1 || month > 12 || day < 1 || day > 31) return null;
        const dt = new Date(Date.UTC(year, month - 1, day));
        if (
            dt.getUTCFullYear() !== year ||
            dt.getUTCMonth() + 1 !== month ||
            dt.getUTCDate() !== day
        ) {
            return null;
        }
        return { year, month, day };
    }

    function todayIsoDate() {
        const now = new Date();
        return {
            year: now.getFullYear(),
            month: now.getMonth() + 1,
            day: now.getDate(),
        };
    }

    function compareDates(a, b) {
        if (a.year !== b.year) return a.year - b.year;
        if (a.month !== b.month) return a.month - b.month;
        return a.day - b.day;
    }

    function ageAt(refDate, birthDate) {
        if (!refDate || !birthDate) return null;
        let years = refDate.year - birthDate.year;
        if (
            refDate.month < birthDate.month ||
            (refDate.month === birthDate.month && refDate.day < birthDate.day)
        ) {
            years -= 1;
        }
        return years;
    }

    function formatDisplayValue(prefix, fieldName, control) {
        if (!control) return "—";
        if (control.tagName === "SELECT") {
            if (!control.value) return "—";
            const opt = control.options[control.selectedIndex];
            return opt ? opt.textContent.trim() : control.value;
        }
        const raw = (control.value || "").trim();
        if (!raw) return "—";
        if (fieldName === "date_of_birth") {
            const parsed = parseIsoDate(raw);
            if (!parsed) return raw;
            const dd = String(parsed.day).padStart(2, "0");
            const mm = String(parsed.month).padStart(2, "0");
            return `${dd}/${mm}/${parsed.year}`;
        }
        if (fieldName === "gross_annual_income") {
            const num = parseFloat(raw);
            return Number.isFinite(num) ? `€ ${num.toFixed(2)}` : raw;
        }
        return raw;
    }

    function syncRowDisplay(row, prefix) {
        row.querySelectorAll("[data-cell-display]").forEach((span) => {
            const fieldName = span.dataset.cellDisplay;
            const control = row.querySelector(`[name$="-${fieldName}"]`);
            if (!control) return;
            span.textContent = formatDisplayValue(prefix, fieldName, control);
        });
    }

    function syncAllFormsetDisplays() {
        form.querySelectorAll("[data-formset]").forEach((container) => {
            const prefix = container.dataset.formset;
            container.querySelectorAll("[data-formset-rows] [data-formset-row]").forEach((row) => {
                syncRowDisplay(row, prefix);
            });
        });
    }

    function personFullName(prefix) {
        const firstEl = form.querySelector(`#id_${prefix}-first_name`);
        const lastEl = form.querySelector(`#id_${prefix}-last_name`);
        const first = (firstEl ? firstEl.value : "").trim();
        const last = (lastEl ? lastEl.value : "").trim();
        return `${first} ${last}`.trim();
    }

    function buildIncomeMemberChoices() {
        const familyStatus = fieldValue("main-family_status");
        const isCouple = familyStatus !== "single_parent";
        const allowsChildren = familyStatus !== "couple_without_children";

        const applicantName = personFullName("applicant");
        const choices = [
            {
                value: "applicant",
                label: applicantName ? `Αιτητής/τρια (${applicantName})` : "Αιτητής/τρια",
            },
        ];

        if (isCouple) {
            const spouseName = personFullName("spouse");
            choices.push({
                value: "spouse",
                label: spouseName ? `Σύζυγος/Συμβίος (${spouseName})` : "Σύζυγος/Συμβίος",
            });
        }

        if (allowsChildren) {
            const childrenContainer = form.querySelector('[data-formset="children"]');
            if (childrenContainer) {
                let childNumber = 0;
                childrenContainer.querySelectorAll("[data-formset-rows] [data-formset-row]").forEach((row) => {
                    if (row.hidden) return;
                    const deleteInput = row.querySelector('input[name$="-DELETE"]');
                    if (deleteInput && deleteInput.checked) return;
                    const firstInput = row.querySelector('input[name$="-first_name"]');
                    if (!firstInput) return;
                    const match = firstInput.name.match(/^children-(\d+)-/);
                    if (!match) return;
                    childNumber += 1;
                    const idx = match[1];
                    const first = (firstInput.value || "").trim();
                    const lastInput = row.querySelector('input[name$="-last_name"]');
                    const last = (lastInput ? lastInput.value : "").trim();
                    const fullName = `${first} ${last}`.trim();
                    choices.push({
                        value: `child:${idx}`,
                        label: fullName ? `Τέκνο: ${fullName}` : `Τέκνο #${childNumber}`,
                    });
                });
            }
        }

        choices.push({ value: "other", label: "Άλλο μέλος της οικογένειας" });
        return { choices, isCouple, allowsChildren };
    }

    function populateMemberSelect(select, choices, preserveCurrent) {
        const current = select.value;
        const allowed = new Set(choices.map((c) => c.value));
        select.innerHTML = "";
        const list = [...choices];
        if (preserveCurrent && current && !allowed.has(current)) {
            if (current === "spouse") {
                list.push({ value: "spouse", label: "Σύζυγος/Συμβίος" });
            } else if (current === "child" || current.startsWith("child:")) {
                list.push({ value: current, label: "Τέκνο" });
            }
        }
        list.forEach(({ value, label }) => {
            const option = document.createElement("option");
            option.value = value;
            option.textContent = label;
            select.appendChild(option);
        });
        if (list.some((c) => c.value === current)) {
            select.value = current;
        } else if (list.length) {
            select.value = list[0].value;
        }
    }

    function syncIncomeMembers() {
        const incomesContainer = form.querySelector('[data-formset="incomes"]');
        if (!incomesContainer) return;
        const { choices, isCouple } = buildIncomeMemberChoices();

        incomesContainer.querySelectorAll("[data-formset-rows] [data-formset-row]").forEach((row) => {
            const deleteInput = row.querySelector('input[name$="-DELETE"]');
            if (deleteInput && deleteInput.checked) return;
            const select = row.querySelector('select[name$="-member"]');
            if (!select) return;
            populateMemberSelect(select, choices, true);
            const hideForFamily = !isCouple && select.value === "spouse";
            row.hidden = hideForFamily;
            syncRowDisplay(row, "incomes");
        });

        const template = incomesContainer.querySelector("[data-formset-template]");
        if (template && template.content) {
            const templateSelect = template.content.querySelector('select[name$="-member"]');
            if (templateSelect) populateMemberSelect(templateSelect, choices, false);
        }

        const emptyRow = incomesContainer.querySelector("[data-formset-empty]");
        if (emptyRow) {
            const hasVisibleRow = Array.from(
                incomesContainer.querySelectorAll("[data-formset-rows] [data-formset-row]")
            ).some((row) => !row.hidden);
            emptyRow.hidden = hasVisibleRow;
        }
    }

    function refreshIncomeTotals() {
        let family = 0;
        const incomesContainer = form.querySelector('[data-formset="incomes"]');
        if (incomesContainer) {
            incomesContainer.querySelectorAll("[data-formset-rows] [data-formset-row]").forEach((row) => {
                if (row.hidden) return;
                const deleteInput = row.querySelector('input[name$="-DELETE"]');
                if (deleteInput && deleteInput.checked) return;
                const amountInput = row.querySelector('input[name$="-gross_annual_income"]');
                family += toNumber(amountInput);
            });
        }
        const familyEl = form.querySelector("[data-family-income-total]");
        if (familyEl) familyEl.textContent = family.toFixed(2);
        refreshIncomeCriterion(family);
    }

    function countRecognizedChildren() {
        const childrenContainer = form.querySelector('[data-formset="children"]');
        if (!childrenContainer) return 0;
        const submittedOn = parseIsoDate(fieldValue("main-submitted_on"));
        let recognized = 0;

        childrenContainer.querySelectorAll("[data-formset-rows] [data-formset-row]").forEach((row) => {
            if (row.hidden) return;
            const deleteInput = row.querySelector('input[name$="-DELETE"]');
            if (deleteInput && deleteInput.checked) return;

            const first = (row.querySelector('input[name$="-first_name"]')?.value || "").trim();
            const last = (row.querySelector('input[name$="-last_name"]')?.value || "").trim();
            const dobStr = (row.querySelector('input[name$="-date_of_birth"]')?.value || "").trim();
            const status = (row.querySelector('select[name$="-status"]')?.value || "").trim();
            const sex = (row.querySelector('select[name$="-sex"]')?.value || "").trim();

            if (!first && !last && !dobStr && !status) return;

            const age = ageAt(submittedOn, parseIsoDate(dobStr));
            if (status === "minor") {
                if (age === null || age < incomeParams.minor_max_age) recognized += 1;
            } else if (status === "student") {
                if (age === null || !sex) {
                    recognized += 1;
                } else {
                    const maxAge =
                        sex === "F" ? incomeParams.student_max_age_female : incomeParams.student_max_age_male;
                    if (age <= maxAge) recognized += 1;
                }
            } else {
                recognized += 1;
            }
        });
        return recognized;
    }

    function incomeTierForMembers(members) {
        const limits = incomeParams.limits || {};
        if (members <= 2) {
            return {
                limit: parseFloat(limits["2"] || "45000"),
                label: "Ζεύγος και Μονογονεϊκή οικογένεια (έως 2 μέλη)",
            };
        }
        if (members === 3) {
            return {
                limit: parseFloat(limits["3"] || "50000"),
                label: "Οικογένεια 3 ατόμων",
            };
        }
        if (members === 4) {
            return {
                limit: parseFloat(limits["4"] || "55000"),
                label: "Οικογένεια 4 ατόμων",
            };
        }
        return {
            limit: parseFloat(limits["5"] || "65000"),
            label: `Οικογένεια 5+ ατόμων (${members} μέλη)`,
        };
    }

    function refreshIncomeCriterion(familyTotal) {
        const compositionEl = form.querySelector("[data-income-composition]");
        const limitEl = form.querySelector("[data-income-limit]");
        const badgeEl = form.querySelector("[data-income-criterion-badge]");
        const noteEl = form.querySelector("[data-income-criterion-note]");
        if (!compositionEl || !limitEl || !badgeEl || !noteEl) return;

        const familyStatus = fieldValue("main-family_status");
        if (!familyStatus) {
            compositionEl.textContent = "Δεν έχει επιλεγεί οικογενειακή κατάσταση";
            limitEl.textContent = "—";
            badgeEl.className = "badge badge--pending";
            badgeEl.textContent = "ΕΚΚΡΕΜΕΙ";
            noteEl.textContent = "Επιλέξτε οικογενειακή κατάσταση στην Ενότητα 3.";
            return;
        }

        const adults = familyStatus === "single_parent" ? 1 : 2;
        const recognizedChildren = countRecognizedChildren();
        const members = adults + recognizedChildren;
        const { limit, label: tierLabel } = incomeTierForMembers(members);
        const statusLabel = FAMILY_STATUS_LABELS[familyStatus] || familyStatus;

        compositionEl.textContent = `${statusLabel} · ${members} μέλη (${tierLabel})`;
        limitEl.textContent = `€ ${limit.toFixed(2)}`;

        if (familyTotal <= limit) {
            badgeEl.className = "badge badge--pass";
            badgeEl.textContent = "ΠΛΗΡΟΥΤΑΙ";
            noteEl.textContent = `Σύνολο € ${familyTotal.toFixed(2)} ≤ όριο € ${limit.toFixed(2)} για ${members} μέλη.`;
        } else {
            badgeEl.className = "badge badge--fail";
            badgeEl.textContent = "ΔΕΝ ΠΛΗΡΟΥΤΑΙ";
            noteEl.textContent = `Σύνολο € ${familyTotal.toFixed(2)} > όριο € ${limit.toFixed(2)} για ${members} μέλη.`;
        }
    }

    function checkboxChecked(name) {
        const el = form.querySelector(`input[type="checkbox"][name="${name}"]`);
        return Boolean(el && el.checked);
    }

    function activeChildrenData() {
        const childrenContainer = form.querySelector('[data-formset="children"]');
        if (!childrenContainer) return { count: 0, statuses: new Set() };
        let count = 0;
        const statuses = new Set();
        childrenContainer.querySelectorAll("[data-formset-rows] [data-formset-row]").forEach((row) => {
            if (row.hidden) return;
            const deleteInput = row.querySelector('input[name$="-DELETE"]');
            if (deleteInput && deleteInput.checked) return;

            const first = (row.querySelector('input[name$="-first_name"]')?.value || "").trim();
            const last = (row.querySelector('input[name$="-last_name"]')?.value || "").trim();
            const dob = (row.querySelector('input[name$="-date_of_birth"]')?.value || "").trim();
            const idNum = (row.querySelector('input[name$="-identity_number"]')?.value || "").trim();
            const status = (row.querySelector('select[name$="-status"]')?.value || "").trim();

            if (!first && !last && !dob && !idNum && !status) return;
            count += 1;
            if (status) statuses.add(status);
        });
        return { count, statuses };
    }

    function activeIncomePairs(isCouple) {
        const pairs = new Set();
        const incomesContainer = form.querySelector('[data-formset="incomes"]');
        if (!incomesContainer) return pairs;
        incomesContainer.querySelectorAll("[data-formset-rows] [data-formset-row]").forEach((row) => {
            if (row.hidden) return;
            const deleteInput = row.querySelector('input[name$="-DELETE"]');
            if (deleteInput && deleteInput.checked) return;

            const member = (row.querySelector('select[name$="-member"]')?.value || "").trim();
            const empType = (row.querySelector('select[name$="-employment_type"]')?.value || "").trim();
            if (!empType) return;
            if (!isCouple && member === "spouse") return;

            let normMember = "other_member";
            if (!member || member === "applicant") {
                normMember = "applicant";
            } else if (member === "spouse") {
                normMember = "spouse";
            }
            pairs.add(`${normMember}:${empType}`);
        });
        return pairs;
    }

    function computeApplicableDocumentCodes() {
        const codes = new Set();
        const familyStatus = fieldValue("main-family_status");
        const isCouple = familyStatus === "couple_with_children" || familyStatus === "couple_without_children";
        const isSingleParent = familyStatus === "single_parent";
        const singleParentStatus = fieldValue("main-single_parent_status");
        const residenceCategory = fieldValue("main-residence_category");

        const applicantCitizenship = fieldValue("applicant_party-citizenship");
        const applicantRefugeeId = (fieldValue("applicant_party-refugee_identity_number") || "").trim();
        const applicantIsEmployee = checkboxChecked("applicant_party-is_employee");
        const applicantIsSelfEmployed = checkboxChecked("applicant_party-is_self_employed");
        const applicantHasDisability = checkboxChecked("applicant_party-has_disability");

        const spouseCitizenship = fieldValue("spouse_party-citizenship");
        const spouseRefugeeId = (fieldValue("spouse_party-refugee_identity_number") || "").trim();
        const spouseAlienNumber = (fieldValue("spouse_party-alien_registration_number") || "").trim();
        const spouseIsEmployee = checkboxChecked("spouse_party-is_employee");
        const spouseIsSelfEmployed = checkboxChecked("spouse_party-is_self_employed");
        const spouseHasDisability = checkboxChecked("spouse_party-has_disability");

        const { count: childrenCount, statuses: childStatuses } = activeChildrenData();
        const largeFamilyChildren = incomeParams.large_family_children || 4;
        const incomePairs = activeIncomePairs(isCouple);

        const hasAlienatedProperty = fieldValue("main-has_alienated_property");

        // Α. Κυπριακή ή άλλη Υπηκοότητα και Ηλικία
        codes.add("A1");
        if (
            residenceCategory === "displaced" ||
            Boolean(applicantRefugeeId) ||
            (isCouple && Boolean(spouseRefugeeId))
        ) {
            codes.add("A2");
        }
        if (
            applicantCitizenship === "other" ||
            (!isSingleParent && spouseCitizenship === "other")
        ) {
            codes.add("A4");
        }

        // Β. Οικογενειακή Κατάσταση
        if (isCouple) {
            codes.add("B1");
            codes.add("B2");
        }
        if (isSingleParent) {
            codes.add("B3");
            if (singleParentStatus === "unmarried") {
                codes.add("B4");
            } else if (singleParentStatus === "divorced") {
                codes.add("B5");
            } else if (singleParentStatus === "widowed") {
                codes.add("B7");
            } else if (singleParentStatus === "other") {
                codes.add("B6");
                codes.add("B7");
                codes.add("B8");
            }
        }
        if (childrenCount >= largeFamilyChildren) {
            codes.add("B9");
        }
        if (applicantHasDisability || (isCouple && spouseHasDisability)) {
            codes.add("B10");
        }
        if (childrenCount > 0 || familyStatus === "couple_with_children" || familyStatus === "single_parent") {
            codes.add("B11");
        }
        if (childStatuses.has("student")) {
            codes.add("B12");
        }
        if (childStatuses.has("national_guard")) {
            codes.add("B13");
        }
        if (childStatuses.has("adult_disability")) {
            codes.add("B14");
        }

        // Γ. Τόπος Διαμονής
        if (["autochthon", "displaced", "internal_emigrant", "repatriated"].includes(residenceCategory)) {
            codes.add("C1");
        }
        if (residenceCategory === "autochthon" || residenceCategory === "displaced") {
            codes.add("C3");
            codes.add("C4");
            codes.add("C5");
        }
        if (residenceCategory === "internal_emigrant") {
            codes.add("C6");
        }
        if (residenceCategory === "repatriated") {
            codes.add("C7");
            codes.add("C8");
        }
        if (residenceCategory === "neighbouring") {
            codes.add("C9");
            codes.add("C10");
        }

        // Δ. Ακίνητη ιδιοκτησία (ΤΚΧ — DLS Portal, Παγκύπρια)
        codes.add("D1");
        codes.add("D2");
        codes.add("D3");
        if (hasAlienatedProperty !== "True") {
            codes.add("D4");
            codes.add("D5");
        }

        // Ε. Εισοδήματα
        if (applicantIsEmployee || incomePairs.has("applicant:employee")) {
            codes.add("E1");
        }
        if (applicantIsSelfEmployed || incomePairs.has("applicant:self_employed")) {
            codes.add("E2");
        }
        if (incomePairs.has("applicant:other")) {
            codes.add("E3");
        }
        if (isCouple) {
            if (spouseIsEmployee || incomePairs.has("spouse:employee")) {
                codes.add("E4");
            }
            if (spouseIsSelfEmployed || incomePairs.has("spouse:self_employed")) {
                codes.add("E5");
            }
            if (incomePairs.has("spouse:other")) {
                codes.add("E6");
            }
        }
        if (incomePairs.has("other_member:employee")) {
            codes.add("E7");
        }
        if (incomePairs.has("other_member:self_employed")) {
            codes.add("E8");
        }
        if (incomePairs.has("other_member:other")) {
            codes.add("E9");
        }

        return codes;
    }

    function computeRequiredDocumentGroups() {
        const required = [];
        const need = (...codes) => required.push(codes);

        const familyStatus = fieldValue("main-family_status");
        const isCouple = familyStatus === "couple_with_children" || familyStatus === "couple_without_children";
        const residenceCategory = fieldValue("main-residence_category");
        const applicantRefugeeId = (fieldValue("applicant_party-refugee_identity_number") || "").trim();
        const applicantHasDisability = checkboxChecked("applicant_party-has_disability");
        const spouseHasDisability = checkboxChecked("spouse_party-has_disability");

        const { count: childrenCount, statuses: childStatuses } = activeChildrenData();
        const incomePairs = activeIncomePairs(isCouple);

        const hasAlienatedProperty = fieldValue("main-has_alienated_property");

        need("A1");
        if (residenceCategory === "displaced" || Boolean(applicantRefugeeId)) {
            need("A2");
        }
        if (isCouple) {
            need("B1", "B2");
        }
        if (childrenCount > 0) {
            need("B11");
        }
        if (childStatuses.has("student")) {
            need("B12");
        }
        if (childStatuses.has("national_guard")) {
            need("B13");
        }
        if (childStatuses.has("adult_disability")) {
            need("B14");
        }
        if (applicantHasDisability || (isCouple && spouseHasDisability)) {
            need("B10");
        }
        if (residenceCategory === "neighbouring") {
            need("C9");
            need("C10");
        } else {
            need("C1");
        }
        if (residenceCategory === "internal_emigrant") {
            need("C6");
        }
        if (residenceCategory === "repatriated") {
            need("C7");
            need("C8");
        }
        need("D1");
        need("D2");
        need("D3");
        if (hasAlienatedProperty !== "True") {
            need("D4");
            need("D5");
        }
        if (incomePairs.has("applicant:employee")) {
            need("E1");
        }
        if (incomePairs.has("applicant:self_employed")) {
            need("E2");
        }
        if (incomePairs.has("applicant:other")) {
            need("E3");
        }
        if (isCouple) {
            if (incomePairs.has("spouse:employee")) {
                need("E4");
            }
            if (incomePairs.has("spouse:self_employed")) {
                need("E5");
            }
            if (incomePairs.has("spouse:other")) {
                need("E6");
            }
        }
        if (incomePairs.has("other_member:employee")) {
            need("E7");
        }
        if (incomePairs.has("other_member:self_employed")) {
            need("E8");
        }
        if (incomePairs.has("other_member:other")) {
            need("E9");
        }

        return required;
    }

    function documentLabelForCode(code) {
        const labelEl = form.querySelector(`[data-document-code="${code}"]`);
        if (labelEl) {
            const textEl =
                labelEl.querySelector("[data-ui-text-node]") ||
                labelEl.querySelector("span");
            const text = (textEl ? textEl.textContent : labelEl.textContent || "").trim();
            if (text) return text;
        }
        const docLabels = incomeParams.document_labels || {};
        return docLabels[code] || code;
    }

    const PERSON_COMPLETENESS_FIELDS = [
        ["identity_number", "Αρ. Δελτίου Ταυτότητας"],
        ["first_name", "Όνομα"],
        ["last_name", "Επίθετο"],
        ["date_of_birth", "Ημερομηνία Γέννησης"],
        ["birth_place", "Τόπος Γέννησης"],
        ["birth_country", "Χώρα Γέννησης"],
        ["parents_birth_place", "Τόπος γέννησης γονέων"],
        ["parents_birth_country", "Χώρα Γέννησης Γονέων"],
    ];

    function collectMissingCompletenessFields() {
        const missing = [];
        const add = (name, label) => missing.push({ name, label });

        const annField = announcementFieldName();
        if (!(fieldValue(annField) || "").trim()) {
            add(annField, annField === "main-announcement" ? "Γνωστοποίηση" : "Κοινότητα");
        }
        if (!(fieldValue("main-submitted_on") || "").trim()) {
            add("main-submitted_on", "Ημερομηνία υποβολής");
        }

        PERSON_COMPLETENESS_FIELDS.forEach(([attr, label]) => {
            if (!(fieldValue(`applicant-${attr}`) || "").trim()) {
                add(`applicant-${attr}`, `Αιτητής/τρια: ${label}`);
            }
        });

        const applicantCit = (fieldValue("applicant_party-citizenship") || "").trim();
        if (!applicantCit) {
            add("applicant_party-citizenship", "Αιτητής/τρια: Υπηκοότητα / Ιδιότητα");
        } else if (
            applicantCit === "other" &&
            !(fieldValue("applicant_party-citizenship_other") || "").trim()
        ) {
            add("applicant_party-citizenship_other", "Αιτητής/τρια: Άλλο (περιγραφή υπηκοότητας)");
        }
        if (!(fieldValue("applicant_party-mobile_phone") || "").trim()) {
            add("applicant_party-mobile_phone", "Αιτητής/τρια: Τηλέφωνο Κινητό");
        }
        if (!(fieldValue("main-email") || "").trim()) {
            add("main-email", "Ηλεκτρονική Διεύθυνση");
        }

        const residenceCategory = (fieldValue("main-residence_category") || "").trim();
        if (!residenceCategory) {
            add("main-residence_category", "Τόπος διαμονής: Κατηγορία");
        } else if (residenceCategory === "neighbouring") {
            if (!(fieldValue("main-neighbouring_community") || "").trim()) {
                add("main-neighbouring_community", "Τόπος διαμονής: Γειτονική Κοινότητα");
            }
        } else if (!(fieldValue("main-residence_community") || "").trim()) {
            add("main-residence_community", "Τόπος διαμονής: Κοινότητα / Δ.Δ. διαμονής");
        }

        const familyStatus = (fieldValue("main-family_status") || "").trim();
        const isCouple =
            familyStatus === "couple_with_children" || familyStatus === "couple_without_children";
        if (!familyStatus) {
            add("main-family_status", "Οικογενειακή κατάσταση");
        } else if (familyStatus === "single_parent") {
            const singleStatus = (fieldValue("main-single_parent_status") || "").trim();
            if (!singleStatus) {
                add("main-single_parent_status", "Μονογονιός (περίπτωση)");
            } else if (
                singleStatus === "other" &&
                !(fieldValue("main-single_parent_other") || "").trim()
            ) {
                add("main-single_parent_other", "Μονογονιός: Άλλο (περιγραφή)");
            }
        }

        if (isCouple) {
            PERSON_COMPLETENESS_FIELDS.forEach(([attr, label]) => {
                if (!(fieldValue(`spouse-${attr}`) || "").trim()) {
                    add(`spouse-${attr}`, `Σύζυγος/Συμβίος: ${label}`);
                }
            });
            const spouseCit = (fieldValue("spouse_party-citizenship") || "").trim();
            if (!spouseCit) {
                add("spouse_party-citizenship", "Σύζυγος/Συμβίος: Υπηκοότητα / Ιδιότητα");
            } else if (
                spouseCit === "other" &&
                !(fieldValue("spouse_party-citizenship_other") || "").trim()
            ) {
                add("spouse_party-citizenship_other", "Σύζυγος/Συμβίος: Άλλο (περιγραφή υπηκοότητας)");
            }
            if (!(fieldValue("spouse_party-mobile_phone") || "").trim()) {
                add("spouse_party-mobile_phone", "Σύζυγος/Συμβίος: Τηλέφωνο Κινητό");
            }
        }

        const hasAnswer = (name) => {
            const val = (fieldValue(name) || "").trim();
            return val === "True" || val === "False";
        };
        if (!hasAnswer("main-has_dwelling")) {
            add("main-has_dwelling", "Εγγεγραμμένη κατοικία (Ναι/Όχι)");
        }
        if (!hasAnswer("main-has_residential_land")) {
            add("main-has_residential_land", "Οικόπεδο/τεμάχιο σε Οικιστική Ζώνη (Ναι/Όχι)");
        }
        if (!hasAnswer("main-has_alienated_property")) {
            add("main-has_alienated_property", "Αποξένωση εντός 3 ετών (Ναι/Όχι)");
        }
        if (!hasAnswer("main-previous_housing_aid")) {
            add("main-previous_housing_aid", "Προηγούμενη κρατική στεγαστική ενίσχυση (Ναι/Όχι)");
        }

        if (!checkboxChecked("main-applicant_signed")) {
            add("main-applicant_signed", "Υπογραφή Αιτητή/Αιτήτριας");
        }
        if (isCouple && !checkboxChecked("main-spouse_signed")) {
            add("main-spouse_signed", "Υπογραφή Συζύγου/Συμβίου");
        }

        return missing;
    }

    function collectDocumentState() {
        const applicable = computeApplicableDocumentCodes();
        const checkedCodes = new Set();
        form.querySelectorAll("[data-document-code]").forEach((label) => {
            const code = label.dataset.documentCode;
            const input = label.querySelector('input[type="checkbox"]');
            if (input && applicable.has(code) && input.checked) {
                checkedCodes.add(code);
            }
        });
        const requiredGroups = computeRequiredDocumentGroups();
        const missingDocs = [];
        requiredGroups.forEach((codes) => {
            if (!codes.some((code) => checkedCodes.has(code))) {
                const primaryCode = codes[0];
                missingDocs.push({
                    code: primaryCode,
                    label: documentLabelForCode(primaryCode),
                });
            }
        });
        const requiredCount = requiredGroups.length;
        const missingCount = missingDocs.length;
        const satisfiedCount = Math.max(0, requiredCount - missingCount);
        const overrideChecked = checkboxChecked("main-documents_complete_override");
        const isComplete = missingCount === 0 || overrideChecked;
        return {
            applicable,
            checkedCodes,
            requiredCount,
            satisfiedCount,
            missingCount,
            missingDocs,
            overrideChecked,
            isComplete,
        };
    }

    function refreshDocumentChecklist() {
        if (!isSubsectionEditable("documents")) return;
        const applicable = computeApplicableDocumentCodes();
        form.querySelectorAll("[data-document-code]").forEach((label) => {
            const code = label.dataset.documentCode;
            const isApplicable = applicable.has(code);
            label.hidden = false;
            label.classList.toggle("is-disabled", !isApplicable);
            const input = label.querySelector('input[type="checkbox"]');
            if (input) {
                input.disabled = !isApplicable;
            }
        });
        form.querySelectorAll("[data-document-group]").forEach((group) => {
            group.hidden = false;
        });

        const {
            requiredCount,
            satisfiedCount,
            missingCount,
            isComplete,
        } = collectDocumentState();

        const badgeEl = form.querySelector("[data-documents-completeness-badge]");
        if (badgeEl) {
            badgeEl.className = `badge ${isComplete ? "badge--pass" : "badge--fail"}`;
            badgeEl.textContent = isComplete ? "ΟΛΟΚΛΗΡΩΜΕΝΗ" : "ΕΛΛΙΠΗΣ";
        }
        const countsEl = form.querySelector("[data-documents-completeness-counts]");
        if (countsEl) {
            const missingText = missingCount > 0 ? `${missingCount} ελλείποντα` : "χωρίς ελλείψεις";
            countsEl.textContent = `${satisfiedCount} από ${requiredCount} απαιτούμενα (${missingText})`;
        }
        const btnBadgeEl = form.querySelector("[data-documents-button-badge]");
        if (btnBadgeEl) {
            btnBadgeEl.className = `badge ${isComplete ? "badge--pass" : "badge--fail"}`;
            btnBadgeEl.textContent = isComplete ? "Ολοκληρωμένη" : "Ελλιπής";
        }
    }

    function refreshCompletenessPanel() {
        const panel = form.querySelector("[data-completeness-panel]");
        if (!panel) return;

        const missingFields = collectMissingCompletenessFields();
        const hasEditableDocs = isSubsectionEditable("documents") && Boolean(form.querySelector("[data-document-code]"));
        let missingDocs = [];
        let overrideChecked = checkboxChecked("main-documents_complete_override");
        let docsComplete = false;

        if (hasEditableDocs) {
            const docState = collectDocumentState();
            missingDocs = docState.missingDocs;
            overrideChecked = docState.overrideChecked;
            docsComplete = docState.isComplete;
        } else {
            const existingDocItems = panel.querySelectorAll("[data-missing-documents-list] [data-missing-document]");
            existingDocItems.forEach((li) => {
                const code = li.dataset.missingDocument || "";
                const label = (li.textContent || "").trim();
                if (code || label) missingDocs.push({ code, label });
            });
            docsComplete = missingDocs.length === 0 || overrideChecked;
        }

        const effectiveMissingDocs = overrideChecked ? [] : missingDocs;
        const isComplete = missingFields.length === 0 && docsComplete;

        panel.classList.toggle("is-complete", isComplete);
        panel.classList.toggle("is-incomplete", !isComplete);
        panel.dataset.completenessState = isComplete ? "complete" : "incomplete";

        const panelBadge = panel.querySelector("[data-completeness-panel-badge]");
        if (panelBadge) {
            panelBadge.className = `badge ${isComplete ? "badge--pass" : "badge--fail"}`;
            panelBadge.textContent = isComplete ? "ΠΛΗΡΗΣ" : "ΕΛΛΙΠΗΣ";
        }

        const summaryEl = panel.querySelector("[data-completeness-panel-summary]");
        if (summaryEl) {
            summaryEl.textContent = isComplete
                ? "Η αίτηση είναι συμπληρωμένη. Όλα τα υποχρεωτικά πεδία και τα απαιτούμενα δικαιολογητικά έχουν συμπληρωθεί."
                : "Η αίτηση είναι ελλιπής. Συμπληρώστε τα πεδία και τα δικαιολογητικά που λείπουν.";
        }

        const fieldsCountEl = panel.querySelector("[data-missing-fields-count]");
        if (fieldsCountEl) {
            fieldsCountEl.textContent = String(missingFields.length);
            fieldsCountEl.className = `badge ${missingFields.length === 0 ? "badge--pass" : "badge--fail"}`;
        }

        const fieldsListEl = panel.querySelector("[data-missing-fields-list]");
        if (fieldsListEl) {
            fieldsListEl.innerHTML = "";
            missingFields.forEach(({ name, label }) => {
                const li = document.createElement("li");
                li.className = "completeness-panel__item";
                li.dataset.missingField = name;
                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = "completeness-panel__jump";
                btn.dataset.focusField = name;
                btn.textContent = label;
                li.appendChild(btn);
                fieldsListEl.appendChild(li);
            });
            fieldsListEl.hidden = missingFields.length === 0;
        }

        const fieldsEmptyEl = panel.querySelector("[data-missing-fields-empty]");
        if (fieldsEmptyEl) {
            fieldsEmptyEl.hidden = missingFields.length > 0;
        }

        const docsCountEl = panel.querySelector("[data-missing-documents-count]");
        if (docsCountEl) {
            docsCountEl.textContent = String(effectiveMissingDocs.length);
            docsCountEl.className = `badge ${docsComplete ? "badge--pass" : "badge--fail"}`;
        }

        const docsListEl = panel.querySelector("[data-missing-documents-list]");
        if (docsListEl && hasEditableDocs) {
            docsListEl.innerHTML = "";
            effectiveMissingDocs.forEach(({ code, label }) => {
                const li = document.createElement("li");
                li.className = "completeness-panel__item";
                li.dataset.missingDocument = code;
                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = "completeness-panel__jump";
                btn.dataset.focusDocument = code;
                btn.textContent = label;
                li.appendChild(btn);
                docsListEl.appendChild(li);
            });
            docsListEl.hidden = docsComplete || effectiveMissingDocs.length === 0;
        }

        const docsEmptyEl = panel.querySelector("[data-missing-documents-empty]");
        if (docsEmptyEl) {
            docsEmptyEl.hidden = !docsComplete;
            docsEmptyEl.textContent =
                overrideChecked && missingDocs.length > 0
                    ? "Ορίστηκε ότι τα δικαιολογητικά είναι εντάξει (παρά τις ελλείψεις)."
                    : "Όλα τα απαιτούμενα δικαιολογητικά έχουν επισυναφθεί.";
        }
    }

    // -------------------------------------------------------------------------
    // Validations for Τέκνο (Section 7) and Εισόδημα (Section 8)
    // -------------------------------------------------------------------------

    function validateChildValues(values, editingRow) {
        const errors = {};
        const first = (values.first_name || "").trim();
        const last = (values.last_name || "").trim();
        const dobRaw = (values.date_of_birth || "").trim();
        const idNum = (values.identity_number || "").trim();
        const status = (values.status || "").trim();
        const sex = (values.sex || "").trim();

        if (!first) {
            errors.first_name = "Υποχρεωτικό πεδίο.";
        }
        if (!last) {
            errors.last_name = "Υποχρεωτικό πεδίο.";
        }
        if (!status) {
            errors.status = "Υποχρεωτικό πεδίο.";
        }
        if (status === "student" && !sex) {
            errors.sex = "Για φοιτητή/τρια απαιτείται το φύλο (όριο 23 θήλυ / 25 άρρεν).";
        }

        if (!dobRaw) {
            errors.date_of_birth = "Υποχρεωτικό πεδίο.";
        } else {
            const dob = parseIsoDate(dobRaw);
            if (!dob) {
                errors.date_of_birth = "Μη έγκυρη ημερομηνία.";
            } else {
                const refDate = parseIsoDate(fieldValue("main-submitted_on")) || todayIsoDate();
                if (compareDates(dob, refDate) > 0) {
                    errors.date_of_birth =
                        "Η ημερομηνία γέννησης δεν μπορεί να είναι μεταγενέστερη της ημερομηνίας υποβολής.";
                } else if (status) {
                    const age = ageAt(refDate, dob);
                    const minorMax = incomeParams.minor_max_age || 18;
                    if (status === "minor" && age >= minorMax) {
                        errors.date_of_birth = `Ηλικία ${age} ετών: για ανήλικο τέκνο η ηλικία πρέπει να είναι μικρότερη των ${minorMax} ετών (Ενότ. 10.Α).`;
                    } else if (status === "student" && sex) {
                        const studentMax =
                            sex === "F"
                                ? incomeParams.student_max_age_female || 23
                                : incomeParams.student_max_age_male || 25;
                        if (age > studentMax) {
                            errors.date_of_birth = `Ηλικία ${age} ετών: υπερβαίνει το όριο των ${studentMax} ετών για φοιτητή/τρια (Ενότ. 10.Α).`;
                        }
                    } else if (status === "adult_disability" && age < minorMax) {
                        errors.date_of_birth = `Ηλικία ${age} ετών: για ενήλικο τέκνο με αναπηρία η ηλικία πρέπει να είναι τουλάχιστον ${minorMax} ετών (Ενότ. 10.Α).`;
                    }
                }
            }
        }

        if (idNum) {
            const applicantId = (fieldValue("applicant-identity_number") || "").trim();
            const familyStatus = (fieldValue("main-family_status") || "").trim();
            const isCouple = familyStatus !== "single_parent";
            const spouseId = isCouple ? (fieldValue("spouse-identity_number") || "").trim() : "";

            if ((applicantId && idNum === applicantId) || (spouseId && idNum === spouseId)) {
                errors.identity_number =
                    "Το τέκνο δεν μπορεί να έχει το ίδιο ΑΔΤ με τον/την αιτητή/τρια ή τον/τη σύζυγο.";
            } else {
                const childrenContainer = form.querySelector('[data-formset="children"]');
                if (childrenContainer) {
                    const duplicate = Array.from(
                        childrenContainer.querySelectorAll("[data-formset-rows] [data-formset-row]")
                    ).some((row) => {
                        if (row === editingRow || row.hidden) return false;
                        const deleteInput = row.querySelector('input[name$="-DELETE"]');
                        if (deleteInput && deleteInput.checked) return false;
                        const otherId = (
                            row.querySelector('input[name$="-identity_number"]')?.value || ""
                        ).trim();
                        return otherId && otherId === idNum;
                    });
                    if (duplicate) {
                        errors.identity_number = "Υπάρχει ήδη τέκνο με το ίδιο ΑΔΤ στην αίτηση.";
                    }
                }
            }
        }

        return errors;
    }

    function validateIncomeValues(values) {
        const errors = {};
        const member = (values.member || "").trim();
        const empType = (values.employment_type || "").trim();
        const desc = (values.description || "").trim();
        const rawAmount = (values.gross_annual_income || "").trim();

        const { choices } = buildIncomeMemberChoices();
        const allowedMembers = new Set(choices.map((c) => c.value));
        if (!member) {
            errors.member = "Επιλέξτε μέλος οικογένειας.";
        } else if (!allowedMembers.has(member)) {
            errors.member = "Επιλέξτε έγκυρο μέλος οικογένειας.";
        }

        if (!empType) {
            errors.employment_type = "Επιλέξτε κατάσταση / είδος εισοδήματος.";
        }

        if (rawAmount === "") {
            errors.gross_annual_income = "Συμπληρώστε το ετήσιο ποσό.";
        } else {
            const parsed = Number(rawAmount);
            if (!Number.isFinite(parsed)) {
                errors.gross_annual_income = "Συμπληρώστε έγκυρο αριθμητικό ποσό.";
            } else if (parsed < 0) {
                errors.gross_annual_income = "Το ποσό δεν μπορεί να είναι αρνητικό.";
            } else if (empType && empType !== "unemployed" && parsed <= 0) {
                errors.gross_annual_income =
                    "Για την επιλεγμένη κατάσταση απαιτείται ετήσιο ποσό μεγαλύτερο του μηδενός.";
            }
        }

        if (empType === "other" && !desc) {
            errors.description = "Περιγράψτε την πηγή εισοδήματος.";
        }

        return errors;
    }

    const APPLICANT_MINIMUM_FIELDS = [
        ["identity_number", "Αρ. Δελτίου Ταυτότητας"],
        ["first_name", "Όνομα"],
        ["last_name", "Επίθετο"],
    ];

    function isValidEmail(value) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
    }

    function isSubsectionEditable(code) {
        const block = form.querySelector(`[data-plot-subsection="${code}"]`);
        return !block || !block.hasAttribute("data-subsection-hidden");
    }

    function collectSaveErrors() {
        const errors = [];

        if (isSubsectionEditable("basic")) {
            const annField = announcementFieldName();
            if (!(fieldValue(annField) || "").trim()) {
                errors.push(
                    annField === "main-announcement"
                        ? "Γνωστοποίηση υποβολής αιτήσεων: Υποχρεωτικό πεδίο."
                        : "Κοινότητα στην οποία ζητείται η παραχώρηση οικοπέδου: Υποχρεωτικό πεδίο."
                );
            }
        }

        if (isSubsectionEditable("section_1")) {
            APPLICANT_MINIMUM_FIELDS.forEach(([field, label]) => {
                if (!(fieldValue(`applicant-${field}`) || "").trim()) {
                    errors.push(`1. Αιτητής/τρια — ${label}: Υποχρεωτικό πεδίο.`);
                }
            });

            const applicantCit = (fieldValue("applicant_party-citizenship") || "").trim();
            if (applicantCit === "other" && !(fieldValue("applicant_party-citizenship_other") || "").trim()) {
                errors.push("1. Αιτητής/τρια — Άλλο (περιγραφή): Συμπληρώστε την υπηκοότητα / ιδιότητα.");
            }
            if (!(fieldValue("applicant_party-mobile_phone") || "").trim()) {
                errors.push("1. Αιτητής/τρια — Τηλέφωνο Κινητό: Υποχρεωτικό πεδίο.");
            }

            const email = (fieldValue("main-email") || "").trim();
            if (email && !isValidEmail(email)) {
                errors.push("1. Ηλεκτρονική Διεύθυνση: Μη έγκυρη διεύθυνση email.");
            }
        }

        const familyStatus = (fieldValue("main-family_status") || "").trim();
        const isCouple = familyStatus === "couple_with_children" || familyStatus === "couple_without_children";

        if (isCouple && isSubsectionEditable("section_5")) {
            const applicantId = (fieldValue("applicant-identity_number") || "").trim();
            const spouseId = (fieldValue("spouse-identity_number") || "").trim();
            if (applicantId && spouseId && applicantId === spouseId) {
                errors.push("5. Σύζυγος/Συμβίος — Αρ. Δελτίου Ταυτότητας: Δεν μπορεί να έχει το ίδιο ΑΔΤ με τον/την αιτητή/τρια.");
            }
            const spouseCit = (fieldValue("spouse_party-citizenship") || "").trim();
            if (spouseCit === "other" && !(fieldValue("spouse_party-citizenship_other") || "").trim()) {
                errors.push("5. Σύζυγος/Συμβίος — Άλλο (περιγραφή): Συμπληρώστε την υπηκοότητα / ιδιότητα.");
            }
            const spouseEmail = (fieldValue("spouse_party-email") || "").trim();
            if (spouseEmail && !isValidEmail(spouseEmail)) {
                errors.push("5. Σύζυγος/Συμβίος — Ηλεκτρονικό Ταχυδρομείο: Μη έγκυρη διεύθυνση email.");
            }
        }

        const CHILD_FIELD_LABELS = {
            first_name: "Όνομα",
            last_name: "Επίθετο",
            date_of_birth: "Ημερομηνία Γέννησης",
            identity_number: "Αρ. Δελτίου Ταυτότητας",
            status: "Κατάσταση",
            sex: "Φύλο",
        };
        const childrenContainer = form.querySelector('[data-formset="children"]');
        if (childrenContainer && isSubsectionEditable("section_7")) {
            let childIdx = 0;
            childrenContainer.querySelectorAll("[data-formset-rows] [data-formset-row]").forEach((row) => {
                if (row.hidden) return;
                const deleteInput = row.querySelector('input[name$="-DELETE"]');
                if (deleteInput && deleteInput.checked) return;
                childIdx += 1;
                const idVal = (row.querySelector('input[name$="-id"]')?.value || "").trim();
                const values = {
                    first_name: (row.querySelector('input[name$="-first_name"]')?.value || "").trim(),
                    last_name: (row.querySelector('input[name$="-last_name"]')?.value || "").trim(),
                    date_of_birth: (row.querySelector('input[name$="-date_of_birth"]')?.value || "").trim(),
                    identity_number: (row.querySelector('input[name$="-identity_number"]')?.value || "").trim(),
                    sex: (row.querySelector('select[name$="-sex"]')?.value || "").trim(),
                    status: (row.querySelector('select[name$="-status"]')?.value || "").trim(),
                };
                if (
                    !idVal &&
                    !values.first_name &&
                    !values.last_name &&
                    !values.date_of_birth &&
                    !values.identity_number &&
                    !values.sex &&
                    !values.status
                ) {
                    return;
                }
                const rowErrors = validateChildValues(values, row);
                Object.entries(rowErrors).forEach(([field, msg]) => {
                    errors.push(`7. Τέκνο #${childIdx} — ${CHILD_FIELD_LABELS[field] || field}: ${msg}`);
                });
            });
        }

        const INCOME_FIELD_LABELS = {
            member: "Μέλος",
            employment_type: "Κατάσταση / Είδος",
            description: "Περιγραφή / Πηγή",
            gross_annual_income: "Ετήσιο Ποσό",
        };
        const incomesContainer = form.querySelector('[data-formset="incomes"]');
        if (incomesContainer && isSubsectionEditable("section_8")) {
            let incomeIdx = 0;
            incomesContainer.querySelectorAll("[data-formset-rows] [data-formset-row]").forEach((row) => {
                if (row.hidden) return;
                const deleteInput = row.querySelector('input[name$="-DELETE"]');
                if (deleteInput && deleteInput.checked) return;
                const values = {
                    member: (row.querySelector('select[name$="-member"]')?.value || "").trim(),
                    employment_type: (row.querySelector('select[name$="-employment_type"]')?.value || "").trim(),
                    description: (row.querySelector('input[name$="-description"]')?.value || "").trim(),
                    gross_annual_income: (
                        row.querySelector('input[name$="-gross_annual_income"]')?.value || ""
                    ).trim(),
                };
                if (!values.employment_type && !values.description && !values.gross_annual_income) {
                    return;
                }
                incomeIdx += 1;
                const rowErrors = validateIncomeValues(values);
                Object.entries(rowErrors).forEach(([field, msg]) => {
                    errors.push(`8. Εισόδημα #${incomeIdx} — ${INCOME_FIELD_LABELS[field] || field}: ${msg}`);
                });
            });
        }

        return errors;
    }

    const saveButton = form.querySelector("[data-save-button]");
    const saveWrapper = form.querySelector("[data-save-button-wrapper]");
    const saveTooltip = form.querySelector("[data-save-tooltip]");

    function refreshSaveButtonState() {
        if (!saveButton) return;
        const errors = collectSaveErrors();
        const hasErrors = errors.length > 0;
        saveButton.disabled = hasErrors;
        if (saveWrapper) {
            saveWrapper.classList.toggle("has-errors", hasErrors);
        }
        if (hasErrors) {
            const summary = ["Δεν είναι δυνατή η αποθήκευση:", ...errors.map((e) => `• ${e}`)].join("\n");
            saveButton.title = summary;
            if (saveTooltip) {
                saveTooltip.textContent = "";
                const titleEl = document.createElement("p");
                titleEl.className = "save-btn-tooltip__title";
                titleEl.textContent = "Δεν είναι δυνατή η αποθήκευση:";
                const listEl = document.createElement("ul");
                listEl.className = "save-btn-tooltip__list";
                errors.forEach((err) => {
                    const li = document.createElement("li");
                    li.textContent = err;
                    listEl.appendChild(li);
                });
                saveTooltip.append(titleEl, listEl);
                saveTooltip.hidden = false;
            }
        } else {
            saveButton.removeAttribute("title");
            if (saveTooltip) {
                saveTooltip.textContent = "";
                saveTooltip.hidden = true;
            }
        }
    }

    const SCROLL_STORAGE_KEY = "plotApplicationScrollState";

    function saveScrollPosition() {
        try {
            sessionStorage.setItem(
                SCROLL_STORAGE_KEY,
                JSON.stringify({
                    scrollY: window.scrollY,
                    formViewportTop: form.getBoundingClientRect().top,
                })
            );
        } catch (_err) {
            // sessionStorage unavailable
        }
    }

    function restoreScrollPosition() {
        try {
            const raw = sessionStorage.getItem(SCROLL_STORAGE_KEY);
            if (!raw) return;
            sessionStorage.removeItem(SCROLL_STORAGE_KEY);
            const saved = JSON.parse(raw);
            if (!saved || typeof saved.scrollY !== "number") return;
            if ("scrollRestoration" in history) {
                history.scrollRestoration = "manual";
            }
            const applyScroll = () => {
                let targetY = saved.scrollY;
                if (saved.scrollY > 0 && Number.isFinite(saved.formViewportTop)) {
                    const currentFormTop = form.getBoundingClientRect().top + window.scrollY;
                    targetY = Math.max(0, Math.round(currentFormTop - saved.formViewportTop));
                }
                window.scrollTo(0, targetY);
            };
            applyScroll();
            window.requestAnimationFrame(applyScroll);
        } catch (_err) {
            // Ignore malformed state
        }
    }

    // -------------------------------------------------------------------------
    // Modal helpers for Τέκνο (Section 7) and Εισόδημα (Section 8)
    // -------------------------------------------------------------------------

    const childDialog = document.querySelector("[data-child-modal]");
    const incomeDialog = document.querySelector("[data-income-modal]");
    let editingChildRow = null;
    let editingIncomeRow = null;

    function clearModalErrors(dialog, summarySelector) {
        if (!dialog) return;
        const summary = dialog.querySelector(summarySelector);
        if (summary) {
            summary.textContent = "";
            summary.hidden = true;
        }
        dialog.querySelectorAll("[data-modal-error]").forEach((el) => {
            el.textContent = "";
            el.hidden = true;
        });
    }

    function showModalErrors(dialog, errors) {
        let firstInvalid = null;
        Object.entries(errors).forEach(([fieldName, message]) => {
            const errorEl = dialog.querySelector(`[data-modal-error="${fieldName}"]`);
            if (errorEl) {
                errorEl.textContent = "";
                const li = document.createElement("li");
                li.textContent = message;
                errorEl.appendChild(li);
                errorEl.hidden = false;
            }
            if (!firstInvalid) {
                firstInvalid = dialog.querySelector(`[data-modal-field="${fieldName}"]`);
            }
        });
        if (firstInvalid) {
            firstInvalid.focus();
        }
    }

    function createFormsetRow(prefix) {
        const container = form.querySelector(`[data-formset="${prefix}"]`);
        const total = container.querySelector(`#id_${prefix}-TOTAL_FORMS`);
        const template = container.querySelector("[data-formset-template]");
        const rows = container.querySelector("[data-formset-rows]");
        const index = parseInt(total.value, 10);
        const html = template.innerHTML.replace(/__prefix__/g, String(index));
        rows.insertAdjacentHTML("beforeend", html);
        total.value = String(index + 1);
        const allRows = rows.querySelectorAll("[data-formset-row]");
        return allRows[allRows.length - 1];
    }

    function syncEmptyRowForContainer(container) {
        const emptyRow = container.querySelector("[data-formset-empty]");
        const rows = container.querySelector("[data-formset-rows]");
        if (!emptyRow || !rows) return;
        const hasVisibleRow = Array.from(rows.querySelectorAll("[data-formset-row]")).some(
            (row) => !row.hidden
        );
        emptyRow.hidden = hasVisibleRow;
    }

    function afterFormsetChange() {
        syncIncomeMembers();
        form.querySelectorAll("[data-formset]").forEach(syncEmptyRowForContainer);
        syncAllFormsetDisplays();
        refreshIncomeTotals();
        refreshDocumentChecklist();
        refreshCompletenessPanel();
        refreshSaveButtonState();
    }

    // --- Child Modal ---
    if (childDialog) {
        const childForm = childDialog.querySelector("[data-child-modal-form]");
        const childTitle = childDialog.querySelector("[data-child-modal-title]");
        const sexLabel = childDialog.querySelector("[data-modal-child-sex-label]");
        const statusSelect = childDialog.querySelector('[data-modal-field="status"]');

        const syncChildModalSexRequirement = () => {
            if (!sexLabel || !statusSelect) return;
            sexLabel.classList.toggle("required", statusSelect.value === "student");
        };

        if (statusSelect) {
            statusSelect.addEventListener("change", syncChildModalSexRequirement);
        }

        childDialog.querySelectorAll("[data-modal-field]").forEach((input) => {
            const clearFieldErr = () => {
                const errEl = childDialog.querySelector(`[data-modal-error="${input.dataset.modalField}"]`);
                if (errEl) {
                    errEl.textContent = "";
                    errEl.hidden = true;
                }
            };
            input.addEventListener("input", clearFieldErr);
            input.addEventListener("change", clearFieldErr);
        });

        childDialog.addEventListener("close", () => {
            editingChildRow = null;
        });

        childForm.addEventListener("submit", (event) => {
            event.preventDefault();
            clearModalErrors(childDialog, "[data-child-modal-errors]");

            const values = {};
            childDialog.querySelectorAll("[data-modal-field]").forEach((input) => {
                values[input.dataset.modalField] = (input.value || "").trim();
            });

            const errors = validateChildValues(values, editingChildRow);
            if (Object.keys(errors).length > 0) {
                showModalErrors(childDialog, errors);
                return;
            }

            const targetRow = editingChildRow || createFormsetRow("children");
            Object.entries(values).forEach(([fieldName, value]) => {
                const control = targetRow.querySelector(`[name$="-${fieldName}"]`);
                if (control) control.value = value;
            });
            targetRow.querySelectorAll(".errorlist").forEach((el) => el.remove());
            syncRowDisplay(targetRow, "children");
            childDialog.close();
            afterFormsetChange();
        });
    }

    function openChildModal(row) {
        if (!childDialog) return;
        editingChildRow = row || null;
        clearModalErrors(childDialog, "[data-child-modal-errors]");
        const childTitle = childDialog.querySelector("[data-child-modal-title]");
        if (childTitle) {
            childTitle.textContent = row ? "Επεξεργασία τέκνου" : "Προσθήκη τέκνου";
        }
        childDialog.querySelectorAll("[data-modal-field]").forEach((input) => {
            const fieldName = input.dataset.modalField;
            if (row) {
                const rowControl = row.querySelector(`[name$="-${fieldName}"]`);
                input.value = rowControl ? rowControl.value : "";
            } else {
                input.value = "";
            }
        });
        const sexLabel = childDialog.querySelector("[data-modal-child-sex-label]");
        const statusSelect = childDialog.querySelector('[data-modal-field="status"]');
        if (sexLabel && statusSelect) {
            sexLabel.classList.toggle("required", statusSelect.value === "student");
        }
        if (!childDialog.open && typeof childDialog.showModal === "function") {
            childDialog.showModal();
        }
        const firstInput = childDialog.querySelector('[data-modal-field="first_name"]');
        if (firstInput) firstInput.focus();
    }

    // --- Income Modal ---
    if (incomeDialog) {
        const incomeForm = incomeDialog.querySelector("[data-income-modal-form]");
        const empTypeSelect = incomeDialog.querySelector('[data-modal-field="employment_type"]');
        const descLabel = incomeDialog.querySelector("[data-modal-income-description-label]");
        const amountInput = incomeDialog.querySelector('[data-modal-field="gross_annual_income"]');

        const syncIncomeModalFields = () => {
            if (descLabel && empTypeSelect) {
                descLabel.classList.toggle("required", empTypeSelect.value === "other");
            }
            if (empTypeSelect && amountInput && empTypeSelect.value === "unemployed" && !amountInput.value.trim()) {
                amountInput.value = "0";
            }
        };

        if (empTypeSelect) {
            empTypeSelect.addEventListener("change", syncIncomeModalFields);
        }

        incomeDialog.querySelectorAll("[data-modal-field]").forEach((input) => {
            const clearFieldErr = () => {
                const errEl = incomeDialog.querySelector(`[data-modal-error="${input.dataset.modalField}"]`);
                if (errEl) {
                    errEl.textContent = "";
                    errEl.hidden = true;
                }
            };
            input.addEventListener("input", clearFieldErr);
            input.addEventListener("change", clearFieldErr);
        });

        incomeDialog.addEventListener("close", () => {
            editingIncomeRow = null;
        });

        incomeForm.addEventListener("submit", (event) => {
            event.preventDefault();
            clearModalErrors(incomeDialog, "[data-income-modal-errors]");

            const values = {};
            incomeDialog.querySelectorAll("[data-modal-field]").forEach((input) => {
                values[input.dataset.modalField] = (input.value || "").trim();
            });
            if (values.employment_type === "unemployed" && values.gross_annual_income === "") {
                values.gross_annual_income = "0";
            }

            const errors = validateIncomeValues(values);
            if (Object.keys(errors).length > 0) {
                showModalErrors(incomeDialog, errors);
                return;
            }

            const targetRow = editingIncomeRow || createFormsetRow("incomes");
            const rowMemberSelect = targetRow.querySelector('select[name$="-member"]');
            if (rowMemberSelect) {
                populateMemberSelect(rowMemberSelect, buildIncomeMemberChoices().choices, false);
            }
            Object.entries(values).forEach(([fieldName, value]) => {
                const control = targetRow.querySelector(`[name$="-${fieldName}"]`);
                if (control) control.value = value;
            });
            targetRow.querySelectorAll(".errorlist").forEach((el) => el.remove());
            syncRowDisplay(targetRow, "incomes");
            incomeDialog.close();
            afterFormsetChange();
        });
    }

    function openIncomeModal(row) {
        if (!incomeDialog) return;
        editingIncomeRow = row || null;
        clearModalErrors(incomeDialog, "[data-income-modal-errors]");
        const incomeTitle = incomeDialog.querySelector("[data-income-modal-title]");
        if (incomeTitle) {
            incomeTitle.textContent = row ? "Επεξεργασία εισοδήματος" : "Προσθήκη εισοδήματος";
        }
        const memberSelect = incomeDialog.querySelector('[data-modal-field="member"]');
        if (memberSelect) {
            const { choices } = buildIncomeMemberChoices();
            populateMemberSelect(memberSelect, choices, false);
        }
        incomeDialog.querySelectorAll("[data-modal-field]").forEach((input) => {
            const fieldName = input.dataset.modalField;
            if (row) {
                const rowControl = row.querySelector(`[name$="-${fieldName}"]`);
                input.value = rowControl ? rowControl.value : "";
            } else if (fieldName === "member") {
                if (memberSelect && memberSelect.options.length) {
                    memberSelect.value = memberSelect.options[0].value;
                }
            } else {
                input.value = "";
            }
        });
        const empTypeSelect = incomeDialog.querySelector('[data-modal-field="employment_type"]');
        const descLabel = incomeDialog.querySelector("[data-modal-income-description-label]");
        if (descLabel && empTypeSelect) {
            descLabel.classList.toggle("required", empTypeSelect.value === "other");
        }
        if (!incomeDialog.open && typeof incomeDialog.showModal === "function") {
            incomeDialog.showModal();
        }
        if (memberSelect) memberSelect.focus();
    }

    function removeFormsetRow(row) {
        const deleteInput = row.querySelector('input[name$="-DELETE"]');
        const idInput = row.querySelector('input[name$="-id"]');
        if (deleteInput) deleteInput.checked = true;
        if (!idInput || !idInput.value) {
            row.querySelectorAll("input:not([type='hidden']):not([name$='-DELETE']), select, textarea").forEach(
                (field) => {
                    field.value = "";
                }
            );
        }
        row.hidden = true;
    }

    function linkedChildIncomeRows(row) {
        const firstInput = row.querySelector('input[name$="-first_name"]');
        const match = firstInput && firstInput.name.match(/^children-(\d+)-/);
        if (!match) return [];
        const childKey = `child:${match[1]}`;
        const incomesContainer = form.querySelector('[data-formset="incomes"]');
        if (!incomesContainer) return [];
        return Array.from(
            incomesContainer.querySelectorAll("[data-formset-rows] [data-formset-row]")
        ).filter((incRow) => {
            if (incRow.hidden) return false;
            const deleteInput = incRow.querySelector('input[name$="-DELETE"]');
            if (deleteInput && deleteInput.checked) return false;
            const memberSelect = incRow.querySelector('select[name$="-member"]');
            return Boolean(memberSelect && memberSelect.value === childKey);
        });
    }

    function confirmFormsetRemove(prefix, row) {
        if (prefix === "children") {
            const first = (row.querySelector('input[name$="-first_name"]')?.value || "").trim();
            const last = (row.querySelector('input[name$="-last_name"]')?.value || "").trim();
            const fullName = `${first} ${last}`.trim();
            const baseMsg = fullName ? `Διαγραφή του τέκνου «${fullName}»;` : "Διαγραφή του τέκνου;";
            const linkedIncomes = linkedChildIncomeRows(row);
            const message = linkedIncomes.length
                ? `${baseMsg}\nΘα διαγραφούν και τα δηλωμένα εισοδήματα του τέκνου.`
                : baseMsg;
            return window.confirm(message);
        }
        if (prefix === "incomes") {
            const memberText = formatDisplayValue("incomes", "member", row.querySelector('select[name$="-member"]'));
            const empText = formatDisplayValue(
                "incomes",
                "employment_type",
                row.querySelector('select[name$="-employment_type"]')
            );
            const amountText = formatDisplayValue(
                "incomes",
                "gross_annual_income",
                row.querySelector('input[name$="-gross_annual_income"]')
            );
            const parts = [memberText, empText, amountText].filter((part) => part && part !== "—");
            const label = parts.join(" · ");
            const message = label ? `Διαγραφή του εισοδήματος (${label});` : "Διαγραφή του εισοδήματος;";
            return window.confirm(message);
        }
        return window.confirm("Διαγραφή της εγγραφής;");
    }

    form.querySelectorAll("[data-formset]").forEach((container) => {
        const prefix = container.dataset.formset;
        const rows = container.querySelector("[data-formset-rows]");

        container.querySelector("[data-formset-add]").addEventListener("click", () => {
            if (prefix === "children") {
                openChildModal(null);
            } else if (prefix === "incomes") {
                openIncomeModal(null);
            }
        });

        rows.addEventListener("click", (event) => {
            const editBtn = event.target.closest("[data-formset-edit]");
            if (editBtn) {
                const row = editBtn.closest("[data-formset-row]");
                if (!row) return;
                if (prefix === "children") {
                    openChildModal(row);
                } else if (prefix === "incomes") {
                    openIncomeModal(row);
                }
                return;
            }

            const removeBtn = event.target.closest("[data-formset-remove]");
            if (!removeBtn) return;
            const row = removeBtn.closest("[data-formset-row]");
            if (!row) return;

            if (!confirmFormsetRemove(prefix, row)) return;

            if (prefix === "children") {
                linkedChildIncomeRows(row).forEach((incRow) => {
                    removeFormsetRow(incRow);
                });
            }

            removeFormsetRow(row);
            afterFormsetChange();
        });

        syncEmptyRowForContainer(container);
    });

    const documentsDialog = form.querySelector("[data-documents-modal]");
    const readonlyDocumentsDialog = document.getElementById("plot-application-documents-readonly-dialog");
    form.querySelectorAll("[data-documents-modal-open]").forEach((btn) => {
        btn.addEventListener("click", () => {
            refreshDocumentChecklist();
        });
    });
    if (documentsDialog) {
        documentsDialog.addEventListener("click", (event) => {
            if (event.target !== documentsDialog) return;
            const rect = documentsDialog.getBoundingClientRect();
            const inside =
                event.clientX >= rect.left &&
                event.clientX <= rect.right &&
                event.clientY >= rect.top &&
                event.clientY <= rect.bottom;
            if (!inside) {
                documentsDialog.close();
            }
        });
    }

    const completenessPanel = form.querySelector("[data-completeness-panel]");
    if (completenessPanel) {
        completenessPanel.addEventListener("click", (event) => {
            const fieldBtn = event.target.closest("[data-focus-field]");
            if (fieldBtn) {
                const fieldName = fieldBtn.dataset.focusField;
                const control = form.querySelector(`[name="${fieldName}"]`);
                if (control) {
                    const container = control.closest(".form-field") || control;
                    if (typeof container.scrollIntoView === "function") {
                        container.scrollIntoView({ behavior: "smooth", block: "center" });
                    }
                    if (!control.disabled && typeof control.focus === "function") {
                        control.focus({ preventScroll: true });
                    }
                }
                return;
            }

            const docBtn = event.target.closest("[data-focus-document]");
            const openDocsBtn = event.target.closest("[data-completeness-open-documents]");
            if (docBtn || openDocsBtn) {
                refreshDocumentChecklist();
                const targetDialog = documentsDialog || readonlyDocumentsDialog;
                if (targetDialog && typeof targetDialog.showModal === "function") {
                    if (!targetDialog.open) {
                        targetDialog.showModal();
                    }
                    if (docBtn) {
                        const docCode = docBtn.dataset.focusDocument;
                        const row = targetDialog.querySelector(`[data-document-row="${docCode}"]`);
                        if (row && typeof row.scrollIntoView === "function") {
                            row.scrollIntoView({ behavior: "smooth", block: "center" });
                        }
                        const checkbox = row ? row.querySelector('input[type="checkbox"]') : null;
                        if (checkbox && !checkbox.disabled && typeof checkbox.focus === "function") {
                            checkbox.focus({ preventScroll: true });
                        }
                    }
                }
            }
        });
    }

    form.addEventListener("submit", () => {
        saveScrollPosition();
    });

    form.addEventListener("change", () => {
        syncResidenceCommunity();
        refreshVisibility();
        syncIncomeMembers();
        refreshIncomeTotals();
        refreshDocumentChecklist();
        refreshCompletenessPanel();
        refreshSaveButtonState();
    });
    form.addEventListener("input", () => {
        syncResidenceCommunity();
        refreshVisibility();
        syncIncomeMembers();
        refreshIncomeTotals();
        refreshDocumentChecklist();
        refreshCompletenessPanel();
        refreshSaveButtonState();
    });
    syncResidenceCommunity();
    refreshVisibility();
    syncIncomeMembers();
    syncAllFormsetDisplays();
    refreshIncomeTotals();
    refreshDocumentChecklist();
    refreshCompletenessPanel();
    refreshSaveButtonState();
    restoreScrollPosition();
})();
