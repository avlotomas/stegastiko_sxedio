/*
 * Application form (10.3.1): pick an existing Person by ΑΔΤ, lock its fixed fields,
 * list its previous applications and optionally prefill this application from one of them.
 */
(function () {
    "use strict";

    const configEl = document.getElementById("person-form-config");
    if (!configEl) return;
    const config = JSON.parse(configEl.textContent);

    // Fixed Person fields (never change between applications).
    const FIXED_FIELDS = [
        "first_name", "last_name", "date_of_birth", "birth_place", "birth_country",
        "parents_birth_place", "parents_birth_country",
    ];
    const SEARCH_DELAY_MS = 250;

    const state = { person1: {}, person2: {} };

    function el(id) {
        return document.getElementById(id);
    }

    function identityInput(prefix) {
        return el(`id_${prefix}_identity_number`);
    }

    function panel(prefix) {
        return document.querySelector(`[data-person-panel="${prefix}"]`);
    }

    function suggestList(prefix) {
        return document.querySelector(`[data-person-suggest="${prefix}"]`);
    }

    function escapeHtml(value) {
        return String(value ?? "").replace(/[&<>"']/g, (c) => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
        }[c]));
    }

    function setValue(input, value) {
        if (!input) return;
        if (input.type === "checkbox") {
            input.checked = value === true || value === "true";
        } else {
            input.value = value ?? "";
        }
        input.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function lockFixedFields(prefix, person) {
        FIXED_FIELDS.forEach((name) => {
            const input = el(`id_${prefix}_${name}`);
            if (!input) return;
            input.value = person[name] ?? "";
            input.readOnly = true;
        });
        state[prefix].locked = true;
    }

    function unlockFixedFields(prefix) {
        if (!state[prefix].locked) return;
        FIXED_FIELDS.forEach((name) => {
            const input = el(`id_${prefix}_${name}`);
            if (!input) return;
            input.readOnly = false;
            input.value = "";
        });
        state[prefix].locked = false;
    }

    function showPanel(prefix, html, tone) {
        const box = panel(prefix);
        box.className = `person-panel${tone ? ` person-panel--${tone}` : ""}`;
        box.innerHTML = html;
        box.hidden = !html;
    }

    function hideSuggestions(prefix) {
        const list = suggestList(prefix);
        list.hidden = true;
        list.innerHTML = "";
    }

    /* ---------- search as you type ---------- */

    function search(prefix) {
        const query = identityInput(prefix).value.trim();
        if (query.length < 2) {
            hideSuggestions(prefix);
            return;
        }
        fetch(`${config.searchUrl}?q=${encodeURIComponent(query)}`)
            .then((r) => r.json())
            .then((data) => {
                if (identityInput(prefix).value.trim() !== query) return;
                const list = suggestList(prefix);
                const results = data.results || [];
                if (!results.length) {
                    hideSuggestions(prefix);
                    return;
                }
                list.innerHTML = results.map((item) =>
                    `<li role="option"><button type="button" data-identity="${escapeHtml(item.identity_number)}">` +
                    `${escapeHtml(item.label)}</button></li>`
                ).join("");
                list.hidden = false;
            })
            .catch(() => hideSuggestions(prefix));
    }

    /* ---------- lookup / select ---------- */

    function lookup(prefix, { force = false } = {}) {
        const identity = identityInput(prefix).value.trim();
        hideSuggestions(prefix);
        if (!identity) {
            unlockFixedFields(prefix);
            state[prefix].identity = "";
            showPanel(prefix, "");
            return Promise.resolve(null);
        }
        if (!force && state[prefix].identity === identity) return Promise.resolve(state[prefix].data);
        state[prefix].identity = identity;

        const params = new URLSearchParams({ identity, prefix });
        if (config.applicationId) params.set("exclude", config.applicationId);
        return fetch(`${config.lookupUrl}?${params}`)
            .then((r) => r.json())
            .then((data) => {
                state[prefix].data = data;
                if (!data.found) {
                    unlockFixedFields(prefix);
                    showPanel(
                        prefix,
                        "<strong>Νέο άτομο.</strong> Δεν υπάρχει καταχωρημένο άτομο με αυτό το ΑΔΤ — " +
                        "συμπληρώστε τα σταθερά στοιχεία· το άτομο θα δημιουργηθεί με την αποθήκευση.",
                        "new"
                    );
                    return data;
                }
                lockFixedFields(prefix, data.person);
                renderPersonPanel(prefix, data);
                return data;
            });
    }

    function renderPersonPanel(prefix, data) {
        const p = data.person;
        const others = config.isCreate ? "προηγούμενες αιτήσεις" : "άλλες αιτήσεις";
        let html =
            `<p><strong>Υπάρχον άτομο:</strong> ${escapeHtml(p.first_name)} ${escapeHtml(p.last_name)} ` +
            `(ΑΔΤ ${escapeHtml(p.identity_number)}, γεν. ${escapeHtml(p.date_of_birth)}). ` +
            `Τα σταθερά στοιχεία συμπληρώθηκαν από το μητρώο και δεν αλλάζουν.</p>`;

        if (!data.applications.length) {
            html += `<p class="text-muted">Δεν υπάρχουν ${others}.</p>`;
            showPanel(prefix, html, "found");
            return;
        }

        html += `<p><strong>${data.applications_count} ${others}</strong> του ατόμου:</p>`;
        html += '<div class="table-wrap"><table class="data-table"><thead><tr>' +
            "<th>Αρ. Φακέλου</th><th>Ημ. υποβολής</th><th>Κοινότητα</th><th>Ρόλος</th>" +
            "<th>Σύζυγος / συμβίος</th><th>Τύπος οικογένειας</th><th>Τέκνα</th><th></th>" +
            "</tr></thead><tbody>";
        data.applications.forEach((a) => {
            html += "<tr>" +
                `<td><a href="${escapeHtml(a.url)}" target="_blank" rel="noopener">${escapeHtml(a.folder_number)}</a></td>` +
                `<td>${escapeHtml(a.submitted_on)}</td>` +
                `<td>${escapeHtml(a.community)}</td>` +
                `<td>${escapeHtml(a.role)}</td>` +
                `<td>${escapeHtml(a.partner) || "—"}</td>` +
                `<td>${escapeHtml(a.family_type)}</td>` +
                `<td>${escapeHtml(a.children_count)}</td>` +
                `<td><button type="button" class="btn btn-secondary btn-sm" data-prefill-from="${a.id}">` +
                "Προσυμπλήρωση</button></td>" +
                "</tr>";
        });
        html += "</tbody></table></div>";
        html += '<p class="helptext">Η «Προσυμπλήρωση» αντιγράφει τα στοιχεία που αλλάζουν ανά αίτηση ' +
            "(υπηκοότητα, διαμονή, εισόδημα, ιδιοκτησία" +
            (prefix === "person1" ? ", τύπο οικογένειας, σύζυγο/συμβίο και τέκνα" : "") +
            ") από την επιλεγμένη αίτηση. Ελέγξτε τα και διορθώστε ό,τι διαφέρει στο νέο Παράρτημα 3.</p>";
        showPanel(prefix, html, "found");
    }

    /* ---------- prefill from a previous application ---------- */

    function prefillFrom(prefix, sourceId) {
        const identity = identityInput(prefix).value.trim();
        const params = new URLSearchParams({ identity, prefix, source: sourceId });
        if (config.applicationId) params.set("exclude", config.applicationId);
        fetch(`${config.lookupUrl}?${params}`)
            .then((r) => r.json())
            .then((data) => {
                if (!data.found || !data.prefill) return;
                applyPrefill(prefix, data.prefill, data.prefill_source);
            });
    }

    function applyPrefill(prefix, prefill, source) {
        Object.entries(prefill.fields).forEach(([key, value]) => setValue(el(`id_${key}`), value));

        const notes = [`Προσυμπληρώθηκαν στοιχεία από την αίτηση ${source.folder_number}.`];

        if (prefix === "person1" && prefill.children.length) {
            const added = addChildren(prefill.children);
            if (added) notes.push(`Προστέθηκαν ${added} τέκνα — ελέγξτε αν ισχύουν ακόμη.`);
        }

        const partnerInput = identityInput("person2");
        if (prefix === "person1" && prefill.partner_identity_number && partnerInput &&
            !partnerInput.value.trim()) {
            partnerInput.value = prefill.partner_identity_number;
            lookup("person2", { force: true });
            notes.push("Ο/Η σύζυγος/συμβίος της αίτησης επιλέχθηκε ως Πρόσωπο 2 — αφαιρέστε το ΑΔΤ αν δεν ισχύει.");
        }

        const box = panel(prefix);
        const note = document.createElement("p");
        note.className = "person-panel__note";
        note.textContent = notes.join(" ");
        box.querySelectorAll(".person-panel__note").forEach((n) => n.remove());
        box.appendChild(note);
    }

    /* ---------- children formset ---------- */

    const childForms = el("children-forms");
    const childTemplate = el("child-form-template");
    const totalForms = el("id_children-TOTAL_FORMS");

    function addChildForm() {
        const index = parseInt(totalForms.value, 10);
        const wrapper = document.createElement("div");
        wrapper.innerHTML = childTemplate.innerHTML.replace(/__prefix__/g, String(index));
        const fieldset = wrapper.firstElementChild;
        childForms.appendChild(fieldset);
        totalForms.value = String(index + 1);
        return index;
    }

    function childRowIsEmpty(index) {
        const name = el(`id_children-${index}-full_name`);
        const dob = el(`id_children-${index}-date_of_birth`);
        return name && !name.value.trim() && dob && !dob.value;
    }

    function existingChildNames() {
        return new Set(
            Array.from(childForms.querySelectorAll('input[name$="-full_name"]'))
                .map((input) => input.value.trim().toLowerCase())
                .filter(Boolean)
        );
    }

    function addChildren(children) {
        const names = existingChildNames();
        let added = 0;
        children.forEach((child) => {
            if (names.has(child.full_name.trim().toLowerCase())) return;
            let index = null;
            const total = parseInt(totalForms.value, 10);
            for (let i = 0; i < total; i += 1) {
                if (childRowIsEmpty(i)) {
                    index = i;
                    break;
                }
            }
            if (index === null) index = addChildForm();
            setValue(el(`id_children-${index}-full_name`), child.full_name);
            setValue(el(`id_children-${index}-date_of_birth`), child.date_of_birth);
            setValue(el(`id_children-${index}-category`), child.category);
            setValue(el(`id_children-${index}-is_recognized_dependent`), child.is_recognized_dependent);
            added += 1;
        });
        return added;
    }

    const addChildButton = el("add-child");
    if (addChildButton && childTemplate && totalForms) {
        addChildButton.addEventListener("click", () => {
            const index = addChildForm();
            el(`id_children-${index}-full_name`)?.focus();
        });
    }

    /* ---------- wiring ---------- */

    ["person1", "person2"].forEach((prefix) => {
        const input = identityInput(prefix);
        if (!input) return;
        let timer = null;

        input.addEventListener("input", () => {
            clearTimeout(timer);
            timer = setTimeout(() => search(prefix), SEARCH_DELAY_MS);
        });
        input.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                lookup(prefix);
            } else if (event.key === "Escape") {
                hideSuggestions(prefix);
            }
        });
        // Delay so a click on a suggestion is handled before the list closes.
        input.addEventListener("blur", () => setTimeout(() => lookup(prefix), 150));

        suggestList(prefix).addEventListener("mousedown", (event) => {
            const button = event.target.closest("[data-identity]");
            if (!button) return;
            event.preventDefault();
            input.value = button.dataset.identity;
            lookup(prefix);
        });

        document.querySelector(`[data-person-lookup="${prefix}"]`)
            .addEventListener("click", () => lookup(prefix, { force: true }));

        panel(prefix).addEventListener("click", (event) => {
            const button = event.target.closest("[data-prefill-from]");
            if (button) prefillFrom(prefix, button.dataset.prefillFrom);
        });

        // Edit page / re-rendered form: show the person panel for an already entered ΑΔΤ.
        if (input.value.trim()) {
            state[prefix].locked = FIXED_FIELDS.some((name) => el(`id_${prefix}_${name}`)?.readOnly);
            lookup(prefix);
        }
    });
})();
