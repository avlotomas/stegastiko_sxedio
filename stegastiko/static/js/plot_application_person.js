/*
 * Αίτηση Παραρτήματος 3, ενότητες 1 και 5: αναζήτηση ατόμου με το ΑΔΤ (εικονίδιο μέσα στο πεδίο ή Enter),
 * συμπλήρωση των σταθερών στοιχείων από το μητρώο «Άτομα», κλείδωμα των πεδίων και επεξεργασία
 * τους μόνο μέσα από modal.
 */
(function () {
    "use strict";

    const form = document.querySelector("[data-plot-application-form]");
    const dialog = document.querySelector("[data-person-edit-dialog]");
    if (!form || !dialog) return;

    const lookupUrl = form.dataset.personLookupUrl;
    const FIXED_FIELDS = [
        "first_name", "last_name", "date_of_birth", "birth_place", "birth_country",
        "parents_birth_place", "parents_birth_country",
    ];
    const NEW_PERSON_TEXT = "Νέο άτομο: δεν βρέθηκε καταχωρημένο ΑΔΤ· συμπληρώστε τα στοιχεία.";
    const dialogBody = dialog.querySelector("[data-person-edit-body]");
    const dialogErrors = dialog.querySelector("[data-person-edit-errors]");

    function csrfToken() {
        const input = form.querySelector('input[name="csrfmiddlewaretoken"]');
        return input ? input.value : "";
    }

    class PersonBlock {
        constructor(root) {
            this.root = root;
            this.prefix = root.dataset.personBlock;
            this.identity = document.getElementById(`id_${this.prefix}-identity_number`);
            this.status = root.querySelector("[data-person-status]");
            this.editButton = root.querySelector("[data-person-edit]");
            this.defaultStatus = this.status.textContent;
            this.editUrl = "";
            this.locked = false;
            this.requestId = 0;
            this.bind();
            // Επεξεργασία / φόρμα με σφάλματα: ο server έχει ήδη κλειδώσει τα πεδία υπάρχοντος ατόμου.
            if (this.identity.value.trim() && this.fixedInput("first_name").readOnly) this.lookup();
        }

        fixedInput(name) {
            return document.getElementById(`id_${this.prefix}-${name}`);
        }

        bind() {
            this.root.querySelector("[data-person-lookup]").addEventListener("click", () => this.lookup());
            this.identity.addEventListener("keydown", (event) => {
                if (event.key !== "Enter") return;
                event.preventDefault();
                this.lookup();
            });
            // Αλλαγή του ΑΔΤ ακυρώνει το προηγούμενο αποτέλεσμα.
            this.identity.addEventListener("input", () => {
                this.requestId += 1;
                if (this.locked) this.release({ clear: true });
                this.setStatus(this.defaultStatus);
            });
            this.editButton.addEventListener("click", () => this.openEditor());
        }

        setStatus(text) {
            this.status.textContent = text;
        }

        fill(person) {
            FIXED_FIELDS.forEach((name) => {
                const input = this.fixedInput(name);
                input.value = person[name] || "";
                input.readOnly = true;
            });
            this.locked = true;
        }

        release({ clear }) {
            FIXED_FIELDS.forEach((name) => {
                const input = this.fixedInput(name);
                input.readOnly = false;
                if (clear) input.value = "";
            });
            this.locked = false;
            this.editButton.hidden = true;
            this.editUrl = "";
        }

        apply(data) {
            this.fill(data.person);
            this.editUrl = data.edit_url;
            this.editButton.hidden = !data.can_edit;
            this.setStatus(
                `Υπάρχον άτομο: ${data.person.first_name} ${data.person.last_name}. ` +
                (data.can_edit
                    ? "Τα στοιχεία συμπληρώθηκαν από το μητρώο· για αλλαγές πατήστε «Επεξεργασία στοιχείων ατόμου»."
                    : "Τα στοιχεία συμπληρώθηκαν από το μητρώο και δεν αλλάζουν από αυτή τη φόρμα.")
            );
        }

        lookup() {
            const identity = this.identity.value.trim();
            if (!identity) {
                if (this.locked) this.release({ clear: true });
                this.setStatus(this.defaultStatus);
                return;
            }
            const requestId = ++this.requestId;
            this.setStatus("Αναζήτηση…");
            fetch(`${lookupUrl}?identity=${encodeURIComponent(identity)}`, {
                headers: { "X-Requested-With": "XMLHttpRequest" },
            })
                .then((response) => {
                    if (!response.ok) throw new Error(String(response.status));
                    return response.json();
                })
                .then((data) => {
                    if (requestId !== this.requestId) return;
                    if (data.found) {
                        this.apply(data);
                    } else {
                        if (this.locked) this.release({ clear: true });
                        this.setStatus(NEW_PERSON_TEXT);
                    }
                })
                .catch(() => {
                    if (requestId === this.requestId) this.setStatus("Η αναζήτηση απέτυχε. Δοκιμάστε ξανά.");
                });
        }

        openEditor() {
            if (!this.editUrl) return;
            dialogErrors.hidden = true;
            dialogBody.innerHTML = "";
            fetch(this.editUrl, { headers: { "X-Requested-With": "XMLHttpRequest" } })
                .then((response) => {
                    if (!response.ok) throw new Error(String(response.status));
                    return response.text();
                })
                .then((html) => {
                    activeBlock = this;
                    dialogBody.innerHTML = html;
                    if (!dialog.open) dialog.showModal();
                })
                .catch(() => {
                    activeBlock = null;
                    dialogErrors.textContent = "Η φόρμα επεξεργασίας δεν φορτώθηκε.";
                    dialogErrors.hidden = false;
                    if (!dialog.open) dialog.showModal();
                });
        }
    }

    let activeBlock = null;
    const blocks = Array.from(form.querySelectorAll("[data-person-block]")).map((root) => new PersonBlock(root));
    if (!blocks.length) return;

    dialog.addEventListener("close", () => {
        activeBlock = null;
        dialogBody.innerHTML = "";
    });

    dialog.addEventListener("submit", (event) => {
        const editForm = event.target.closest("[data-person-edit-form]");
        if (!editForm) return;
        event.preventDefault();
        const block = activeBlock;
        dialogErrors.hidden = true;
        fetch(editForm.action, {
            method: "POST",
            body: new FormData(editForm),
            headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrfToken() },
        })
            .then((response) => {
                const contentType = response.headers.get("content-type") || "";
                if (contentType.includes("application/json") && response.ok) {
                    return response.json().then((data) => ({ saved: true, data }));
                }
                if (response.status === 422) {
                    return response.text().then((html) => ({ saved: false, html }));
                }
                throw new Error(String(response.status));
            })
            .then((result) => {
                if (!result.saved) {
                    dialogBody.innerHTML = result.html;
                    return;
                }
                if (block) block.apply(result.data);
                dialog.close();
            })
            .catch(() => {
                dialogErrors.textContent = "Η αποθήκευση απέτυχε. Δοκιμάστε ξανά.";
                dialogErrors.hidden = false;
            });
    });
})();
