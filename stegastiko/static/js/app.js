(function () {

    const toggle = document.querySelector("[data-nav-toggle]");

    const nav = document.querySelector("[data-site-nav]");

    if (!toggle || !nav) {

        return;

    }

    toggle.addEventListener("click", function () {

        const open = nav.classList.toggle("is-open");

        toggle.setAttribute("aria-expanded", open ? "true" : "false");

    });

    document.addEventListener("click", function (event) {

        if (!nav.classList.contains("is-open")) {

            return;

        }

        if (nav.contains(event.target) || toggle.contains(event.target)) {

            return;

        }

        nav.classList.remove("is-open");

        toggle.setAttribute("aria-expanded", "false");

    });

})();



function bindCompletenessDeficiencies(root) {

    const result = root.querySelector("[data-completeness-result]");

    const section = root.querySelector("[data-completeness-deficiencies]");

    if (!result || !section) {

        return;

    }

    const sync = function () {

        section.hidden = result.value !== "no";

    };

    result.addEventListener("change", sync);

    sync();

}



// «Άλλο» choices (e.g. 3.1 ownership / access): the description shows only while "other" is selected.

function bindOtherGroups(root) {

    root.querySelectorAll("[data-other-group]").forEach(function (group) {

        const select = group.querySelector("select");

        const input = group.querySelector("[data-other-input]");

        if (!select || !input) {

            return;

        }

        const sync = function () {

            input.hidden = select.value !== "other";

        };

        select.addEventListener("change", sync);

        sync();

    });

}

bindOtherGroups(document);



// Multiple-file inputs: each new selection is added to the list instead of replacing it,

// and single files can be dropped before saving.

function bindFilePickers(root, initialFiles) {

    root.querySelectorAll("[data-file-picker]").forEach(function (picker) {

        const input = picker.querySelector('input[type="file"]');

        const list = picker.querySelector("[data-file-picker-list]");

        if (!input || !list || typeof DataTransfer === "undefined") {

            return;

        }

        const selected = new DataTransfer();

        const keyOf = function (file) {

            return [file.name, file.size, file.lastModified].join(":");

        };

        const add = function (files) {

            const known = new Set(Array.from(selected.files).map(keyOf));

            Array.from(files).forEach(function (file) {

                if (!known.has(keyOf(file))) {

                    selected.items.add(file);

                    known.add(keyOf(file));

                }

            });

        };

        const render = function () {

            input.files = selected.files;

            list.textContent = "";

            Array.from(selected.files).forEach(function (file, index) {

                const item = document.createElement("li");

                const name = document.createElement("span");

                name.textContent = file.name;

                const remove = document.createElement("button");

                remove.type = "button";

                remove.className = "btn-link";

                remove.dataset.fileRemove = String(index);

                remove.textContent = "Αφαίρεση";

                item.append(name, remove);

                list.appendChild(item);

            });

            list.hidden = selected.files.length === 0;

        };

        input.addEventListener("change", function () {

            add(input.files);

            render();

        });

        list.addEventListener("click", function (event) {

            const remove = event.target.closest("[data-file-remove]");

            if (!remove) {

                return;

            }

            selected.items.remove(Number(remove.dataset.fileRemove));

            render();

        });

        add(initialFiles || []);

        render();

    });

}

bindFilePickers(document);



// Modal close buttons (including dialogs rendered after forms).

(function () {

    document.addEventListener("click", function (event) {

        const close = event.target.closest("[data-dialog-close]");

        if (!close) {

            return;

        }

        const dialog = close.closest("dialog");

        if (dialog) {

            dialog.close();

        }

    });

})();



// 2.2 deficiencies email dialog, sent without reloading so unsaved section edits survive.

(function () {

    document.addEventListener("click", function (event) {

        const button = event.target.closest("[data-dialog-open]");

        if (!button) {

            return;

        }

        const dialog = document.getElementById(button.dataset.dialogOpen);

        if (!dialog) {

            return;

        }

        const form = dialog.querySelector("[data-email-form]");

        if (!form) {

            return;

        }

        if (button.dataset.emailAction) {

            form.action = button.dataset.emailAction;

        }

        const source = button.dataset.copyText || "";

        const body = dialog.querySelector("[data-email-body]");

        if (body) {

            body.value = source;

        }

        const checkLabel = dialog.querySelector("[data-email-check-label]");

        if (checkLabel) {

            checkLabel.textContent = button.dataset.checkLabel || "";

        }

        const errors = dialog.querySelector("[data-email-errors]");

        if (errors) {

            errors.hidden = true;

            errors.textContent = "";

        }

        dialog.showModal();

    });



    const showErrors = function (container, messages) {

        container.textContent = "";

        messages.forEach(function (message) {

            const line = document.createElement("div");

            line.textContent = message;

            container.appendChild(line);

        });

        container.hidden = messages.length === 0;

    };



    document.querySelectorAll("[data-email-form]").forEach(function (form) {

        form.addEventListener("submit", function (event) {

            event.preventDefault();

            const dialog = form.closest("dialog");

            const errors = form.querySelector("[data-email-errors]");

            const submit = form.querySelector('button[type="submit"]');

            submit.disabled = true;

            fetch(form.action, {

                method: "POST",

                body: new FormData(form),

                headers: { Accept: "application/json" },

                credentials: "same-origin",

            })

                .then(function (response) {

                    return response.json();

                })

                .then(function (data) {

                    if (!data.ok) {

                        showErrors(errors, data.errors || []);

                        return;

                    }

                    const log = document.querySelector("[data-deficiency-email-log]");

                    if (log) {

                        log.outerHTML = data.log_html;

                    }

                    if (data.grid_html) {

                        const grid = document.querySelector("[data-completeness-check-container]");

                        if (grid) {

                            grid.outerHTML = data.grid_html;

                        }

                    }

                    const status = document.querySelector("[data-completeness-check-status]");

                    if (status) {

                        status.innerHTML = "";

                        const alert = document.createElement("div");

                        alert.className = "alert alert--success";

                        alert.setAttribute("role", "status");

                        alert.textContent = data.message;

                        status.appendChild(alert);

                    }

                    dialog.close();

                })

                .catch(function () {

                    showErrors(errors, ["Αποτυχία επικοινωνίας με τον διακομιστή."]);

                })

                .finally(function () {

                    submit.disabled = false;

                });

        });

    });

})();



// 2.2 sent-email history: read-only modal for a Communication record.

(function () {

    const getDialog = function () {

        return document.getElementById("communication-email-view-dialog");

    };



    const setLoading = function (dialog) {

        const recipient = dialog.querySelector("[data-communication-view-recipient]");

        const status = dialog.querySelector("[data-communication-view-status]");

        const sentAt = dialog.querySelector("[data-communication-view-sent-at]");

        const subject = dialog.querySelector("[data-communication-view-subject]");

        const body = dialog.querySelector("[data-communication-view-body]");

        const errors = dialog.querySelector("[data-communication-view-errors]");

        if (errors) {

            errors.hidden = true;

            errors.textContent = "";

        }

        recipient.textContent = "…";

        status.textContent = "…";

        sentAt.textContent = "…";

        subject.textContent = "…";

        body.textContent = "Φόρτωση…";

    };



    const openFromTrigger = function (trigger) {

        const dialog = getDialog();

        if (!dialog) {

            return;

        }

        const url = trigger.getAttribute("data-communication-detail-url");

        if (!url) {

            return;

        }

        setLoading(dialog);

        if (typeof dialog.showModal === "function") {

            dialog.showModal();

        }



        const recipient = dialog.querySelector("[data-communication-view-recipient]");

        const status = dialog.querySelector("[data-communication-view-status]");

        const sentAt = dialog.querySelector("[data-communication-view-sent-at]");

        const subject = dialog.querySelector("[data-communication-view-subject]");

        const body = dialog.querySelector("[data-communication-view-body]");

        const errors = dialog.querySelector("[data-communication-view-errors]");



        fetch(url, {

            headers: { Accept: "application/json" },

            credentials: "same-origin",

        })

            .then(function (response) {

                return response.json().then(function (data) {

                    if (!response.ok || !data.ok) {

                        throw new Error("bad response");

                    }

                    return data;

                });

            })

            .then(function (data) {

                recipient.textContent = data.recipient || "—";

                status.textContent = data.status_display || "—";

                sentAt.textContent = data.sent_at || "—";

                subject.textContent = data.subject || "—";

                body.textContent = data.body || "—";

            })

            .catch(function () {

                if (errors) {

                    errors.textContent = "Αποτυχία φόρτωσης του email.";

                    errors.hidden = false;

                }

                body.textContent = "—";

            });

    };



    const statusRank = function (value) {

        if (value === "sent") {

            return 2;

        }

        if (value === "draft") {

            return 1;

        }

        return 0;

    };

    const sortCommunicationGrid = function (button) {

        const table = button.closest("[data-communication-table]");

        if (!table) {

            return;

        }

        const key = button.dataset.communicationSort;

        const currentKey = table.dataset.sortKey || "";

        const currentDir = table.dataset.sortDir || "asc";

        const nextDir = currentKey === key && currentDir === "asc" ? "desc" : "asc";

        table.dataset.sortKey = key;

        table.dataset.sortDir = nextDir;

        const tbody = table.querySelector("tbody");

        if (!tbody) {

            return;

        }

        const rows = Array.from(tbody.querySelectorAll("tr[data-communication-row]"));

        const read = function (row, sortKey) {

            const cell = row.querySelector("[data-sort-" + sortKey + "]");

            return cell ? cell.getAttribute("data-sort-" + sortKey) || "" : "";

        };

        rows.sort(function (a, b) {

            let left = "";

            let right = "";

            if (key === "sent-at") {

                left = Date.parse(read(a, key)) || 0;

                right = Date.parse(read(b, key)) || 0;

            } else if (key === "status") {

                left = statusRank(read(a, key));

                right = statusRank(read(b, key));

            } else {

                left = read(a, key).toLowerCase();

                right = read(b, key).toLowerCase();

            }

            if (left < right) {

                return nextDir === "asc" ? -1 : 1;

            }

            if (left > right) {

                return nextDir === "asc" ? 1 : -1;

            }

            return 0;

        });

        rows.forEach(function (row) {

            tbody.appendChild(row);

        });

    };

    document.addEventListener("click", function (event) {

        const sort = event.target.closest("[data-communication-sort]");

        if (sort) {

            event.preventDefault();

            sortCommunicationGrid(sort);

            return;

        }

        const trigger = event.target.closest("[data-communication-view]");

        if (!trigger) {

            return;

        }

        event.preventDefault();

        openFromTrigger(trigger);

    });

})();



// Completeness check grid (2.1): add / edit / delete in a modal, each saved immediately.

(function () {

    const dialog = document.querySelector("[data-completeness-check-dialog]");

    if (!dialog) {

        return;

    }

    const body = dialog.querySelector("[data-completeness-check-dialog-body]");

    const errors = dialog.querySelector("[data-completeness-check-errors]");

    const showDialogError = function (message) {

        errors.textContent = message;

        errors.hidden = !message;

    };

    const showStatus = function (message, kind) {

        const status = document.querySelector("[data-completeness-check-status]");

        if (!status) {

            return;

        }

        status.textContent = "";

        const alert = document.createElement("div");

        alert.className = "alert alert--" + (kind || "success");

        alert.setAttribute("role", "status");

        alert.textContent = message;

        status.appendChild(alert);

    };

    const replaceGrid = function (html) {

        const grid = document.querySelector("[data-completeness-check-container]");

        if (grid) {

            grid.outerHTML = html;

        }

    };

    const resultRank = function (value) {

        if (value === "yes") {

            return 2;

        }

        if (value === "no") {

            return 1;

        }

        return 0;

    };

    const sortGrid = function (button) {

        const table = document.querySelector("[data-completeness-check-table]");

        if (!table) {

            return;

        }

        const key = button.dataset.completenessSort;

        const currentKey = table.dataset.sortKey || "";

        const currentDir = table.dataset.sortDir || "asc";

        const nextDir = currentKey === key && currentDir === "asc" ? "desc" : "asc";

        table.dataset.sortKey = key;

        table.dataset.sortDir = nextDir;

        const tbody = table.querySelector("tbody");

        if (!tbody) {

            return;

        }

        const rows = Array.from(tbody.querySelectorAll("tr[data-completeness-row]"));

        const read = function (row, sortKey) {

            const cell = row.querySelector("[data-sort-" + sortKey + "]");

            return cell ? cell.getAttribute("data-sort-" + sortKey) || "" : "";

        };

        rows.sort(function (a, b) {

            let left = "";

            let right = "";

            if (key === "sequence" || key === "emails") {

                left = Number(read(a, key)) || 0;

                right = Number(read(b, key)) || 0;

            } else if (key === "date") {

                left = Date.parse(read(a, key)) || 0;

                right = Date.parse(read(b, key)) || 0;

            } else if (key === "result") {

                left = resultRank(read(a, key));

                right = resultRank(read(b, key));

            } else {

                left = read(a, key).toLowerCase();

                right = read(b, key).toLowerCase();

            }

            if (left < right) {

                return nextDir === "asc" ? -1 : 1;

            }

            if (left > right) {

                return nextDir === "asc" ? 1 : -1;

            }

            return 0;

        });

        rows.forEach(function (row) {

            tbody.appendChild(row);

        });

    };

    const requestJson = function (url, options) {

        return fetch(url, Object.assign({

            headers: { Accept: "application/json" },

            credentials: "same-origin",

        }, options)).then(function (response) {

            return response.json();

        });

    };

    const mountForm = function (html) {

        body.innerHTML = html;

        bindCompletenessDeficiencies(body);

        const form = body.querySelector("[data-completeness-check-form]");

        form.addEventListener("submit", onSubmit);

    };

    const onSubmit = function (event) {

        event.preventDefault();

        const form = event.currentTarget;

        const submit = form.querySelector('button[type="submit"]');

        submit.disabled = true;

        showDialogError("");

        requestJson(form.action, { method: "POST", body: new FormData(form) })

            .then(function (data) {

                if (!data.ok) {

                    mountForm(data.html);

                    return;

                }

                replaceGrid(data.grid_html);

                showStatus(data.message);

                dialog.close();

            })

            .catch(function () {

                showDialogError("Αποτυχία επικοινωνίας με τον διακομιστή.");

            })

            .finally(function () {

                submit.disabled = false;

            });

    };

    const openForm = function (url) {

        showDialogError("");

        body.innerHTML = '<p class="text-muted">Φόρτωση...</p>';

        dialog.showModal();

        requestJson(url)

            .then(function (data) {

                if (!data.ok) {

                    throw new Error("bad response");

                }

                mountForm(data.html);

            })

            .catch(function () {

                body.textContent = "";

                showDialogError("Αποτυχία φόρτωσης της φόρμας ελέγχου.");

            });

    };

    const deleteCheck = function (button) {

        const blockedReason = button.dataset.completenessCheckDeleteBlockedReason || "";

        if (blockedReason) {

            showStatus(blockedReason, "error");

            return;

        }

        const label = button.dataset.completenessCheckLabel || "";

        if (!window.confirm("Διαγραφή του ελέγχου " + label + ";")) {

            return;

        }

        button.disabled = true;

        const token = document.querySelector('input[name="csrfmiddlewaretoken"]');

        const data = new FormData();

        data.append("csrfmiddlewaretoken", token ? token.value : "");

        requestJson(button.dataset.completenessCheckDelete, { method: "POST", body: data })
            .then(function (result) {

                if (!result.ok) {

                    const message = result.message || "Αποτυχία διαγραφής του ελέγχου.";

                    showStatus(message, "error");

                    if (result.grid_html) {

                        replaceGrid(result.grid_html);

                    }

                    return;

                }

                replaceGrid(result.grid_html);

                showStatus(result.message);

            })
            .catch(function () {

                showStatus("Αποτυχία διαγραφής του ελέγχου.", "error");

            })
            .finally(function () {

                button.disabled = false;

            });

    };

    document.addEventListener("click", function (event) {

        const sort = event.target.closest("[data-completeness-sort]");

        if (sort) {

            event.preventDefault();

            sortGrid(sort);

            return;

        }

        const open = event.target.closest("[data-completeness-check-open]");

        if (open) {

            event.preventDefault();

            openForm(open.dataset.completenessCheckOpen);

            return;

        }

        const remove = event.target.closest("[data-completeness-check-delete]");

        if (remove) {

            event.preventDefault();

            deleteCheck(remove);

        }

    });

})();


// Land plot grids — 3.1 add / edit / delete and 4.1 edit of the technical evaluation — in a

// modal, each saved immediately so unsaved edits elsewhere on the page survive.

(function () {

    const dialog = document.querySelector("[data-land-plot-dialog]");

    if (!dialog) {

        return;

    }

    const body = dialog.querySelector("[data-land-plot-dialog-body]");

    const errors = dialog.querySelector("[data-land-plot-errors]");



    const showDialogError = function (message) {

        errors.textContent = message;

        errors.hidden = !message;

    };



    const showStatus = function (message, kind) {

        const status = document.querySelector("[data-land-plot-status]");

        if (!status) {

            return;

        }

        status.textContent = "";

        const alert = document.createElement("div");

        alert.className = "alert alert--" + (kind || "success");

        alert.setAttribute("role", "status");

        alert.textContent = message;

        status.appendChild(alert);

    };



    const replaceGrid = function (html) {

        const grid = document.querySelector("[data-land-plot-grid]");

        if (grid) {

            grid.outerHTML = html;

        }

    };



    const requestJson = function (url, options) {

        return fetch(url, Object.assign({

            headers: { Accept: "application/json" },

            credentials: "same-origin",

        }, options)).then(function (response) {

            return response.json();

        });

    };



    const mountForm = function (html, pendingFiles) {

        body.innerHTML = html;

        bindOtherGroups(body);

        bindFilePickers(body, pendingFiles);

        const form = body.querySelector("[data-land-plot-form]");

        form.addEventListener("submit", onSubmit);

        const first = form.querySelector("input:not([type=hidden]), select, textarea");

        if (first) {

            first.focus();

        }

    };



    const onSubmit = function (event) {

        event.preventDefault();

        const form = event.currentTarget;

        const submit = form.querySelector('button[type="submit"]');

        submit.disabled = true;

        showDialogError("");

        requestJson(form.action, { method: "POST", body: new FormData(form) })

            .then(function (data) {

                if (!data.ok) {

                    // Browsers cannot refill a file input, so keep the chosen files across the re-render.

                    const fileInput = form.querySelector('[data-file-picker] input[type="file"]');

                    mountForm(data.html, fileInput ? Array.from(fileInput.files) : []);

                    return;

                }

                replaceGrid(data.grid_html);

                showStatus(data.message);

                dialog.close();

            })

            .catch(function () {

                showDialogError("Αποτυχία επικοινωνίας με τον διακομιστή.");

            })

            .finally(function () {

                submit.disabled = false;

            });

    };



    const openForm = function (url) {

        showDialogError("");

        body.innerHTML = '<p class="text-muted">Φόρτωση…</p>';

        dialog.showModal();

        requestJson(url)

            .then(function (data) {

                if (!data.ok) {

                    throw new Error("bad response");

                }

                mountForm(data.html);

            })

            .catch(function () {

                body.textContent = "";

                showDialogError("Αποτυχία φόρτωσης της φόρμας τεμαχίου.");

            });

    };



    // A plot with a 4.1 technical evaluation is deleted only after the officer saw that warning.

    const confirmDelete = function (label, warning) {

        if (warning) {

            return window.confirm(warning + "\n\nΣυνέχεια με τη διαγραφή του τεμαχίου " + label + ";");

        }

        return window.confirm(

            "Διαγραφή του τεμαχίου " + label + ";\n" +

            "Θα διαγραφούν και τα αρχεία του, καθώς και τα στοιχεία του τεμαχίου στις Ενότητες 4 και 6."

        );

    };



    const deletePlot = function (button) {

        const url = button.dataset.landPlotDelete;

        const label = button.dataset.landPlotLabel || "";

        const warning = button.dataset.landPlotWarning || "";

        if (!confirmDelete(label, warning)) {

            return;

        }

        const token = document.querySelector('input[name="csrfmiddlewaretoken"]');

        const send = function (evaluationConfirmed) {

            const data = new FormData();

            data.append("csrfmiddlewaretoken", token ? token.value : "");

            if (evaluationConfirmed) {

                data.append("confirm_evaluation", "1");

            }

            return requestJson(url, { method: "POST", body: data });

        };

        button.disabled = true;

        send(Boolean(warning))

            .then(function (result) {

                if (!result.ok && result.requires_confirmation) {

                    // A 4.1 evaluation was recorded after this grid was loaded.

                    replaceGrid(result.grid_html);

                    if (!confirmDelete(label, result.message)) {

                        return null;

                    }

                    return send(true);

                }

                return result;

            })

            .then(function (result) {

                if (result === null) {

                    return;

                }

                if (!result.ok) {

                    throw new Error("bad response");

                }

                replaceGrid(result.grid_html);

                showStatus(result.message);

            })

            .catch(function () {

                button.disabled = false;

                showStatus("Αποτυχία διαγραφής του τεμαχίου.", "error");

            });

    };



    document.addEventListener("click", function (event) {

        const open = event.target.closest("[data-land-plot-open]");

        if (open) {

            event.preventDefault();

            openForm(open.dataset.landPlotOpen);

            return;

        }

        const remove = event.target.closest("[data-land-plot-delete]");

        if (remove) {

            event.preventDefault();

            deletePlot(remove);

        }

    });

})();


// Utility services grid (4.2): columns sort on click (also on the read-only case folder);
// add / edit / delete in a modal, each saved immediately.
(function () {
    const collator = new Intl.Collator("el", { numeric: true, sensitivity: "base" });

    const sortGrid = function (button) {
        const table = button.closest("[data-utility-service-table]");
        const tbody = table ? table.querySelector("tbody") : null;
        if (!tbody) {
            return;
        }
        const key = button.dataset.utilityServiceSort;
        const nextDir = table.dataset.sortKey === key && table.dataset.sortDir === "asc" ? "desc" : "asc";
        table.dataset.sortKey = key;
        table.dataset.sortDir = nextDir;
        table.querySelectorAll("th").forEach(function (th) {
            th.removeAttribute("aria-sort");
        });
        button.closest("th").setAttribute("aria-sort", nextDir === "asc" ? "ascending" : "descending");
        const read = function (row) {
            const cell = row.querySelector("[data-sort-" + key + "]");
            return cell ? cell.getAttribute("data-sort-" + key) || "" : "";
        };
        const rows = Array.from(tbody.querySelectorAll("tr[data-utility-service-row]"));
        rows.sort(function (a, b) {
            const order = collator.compare(read(a), read(b));
            return nextDir === "asc" ? order : -order;
        });
        rows.forEach(function (row) {
            tbody.appendChild(row);
        });
    };

    const dialog = document.querySelector("[data-utility-service-dialog]");
    const body = dialog ? dialog.querySelector("[data-utility-service-dialog-body]") : null;
    const errors = dialog ? dialog.querySelector("[data-utility-service-errors]") : null;

    const showDialogError = function (message) {
        errors.textContent = message;
        errors.hidden = !message;
    };

    const showStatus = function (message, kind) {
        const status = document.querySelector("[data-utility-service-status]");
        if (!status) {
            return;
        }
        status.textContent = "";
        const alert = document.createElement("div");
        alert.className = "alert alert--" + (kind || "success");
        alert.setAttribute("role", "status");
        alert.textContent = message;
        status.appendChild(alert);
    };

    const replaceGrid = function (html) {
        const grid = document.querySelector("[data-utility-service-container]");
        if (grid) {
            grid.outerHTML = html;
        }
    };

    const requestJson = function (url, options) {
        return fetch(url, Object.assign({
            headers: { Accept: "application/json" },
            credentials: "same-origin",
        }, options)).then(function (response) {
            return response.json();
        });
    };

    const mountForm = function (html) {
        body.innerHTML = html;
        const form = body.querySelector("[data-utility-service-form]");
        form.addEventListener("submit", onSubmit);
        const first = form.querySelector("select, input:not([type=hidden]), textarea");
        if (first) {
            first.focus();
        }
    };

    const onSubmit = function (event) {
        event.preventDefault();
        const form = event.currentTarget;
        const submit = form.querySelector('button[type="submit"]');
        submit.disabled = true;
        showDialogError("");
        requestJson(form.action, { method: "POST", body: new FormData(form) })
            .then(function (data) {
                if (!data.ok) {
                    mountForm(data.html);
                    return;
                }
                replaceGrid(data.grid_html);
                showStatus(data.message);
                dialog.close();
            })
            .catch(function () {
                showDialogError("Αποτυχία επικοινωνίας με τον διακομιστή.");
            })
            .finally(function () {
                submit.disabled = false;
            });
    };

    const openForm = function (url) {
        showDialogError("");
        body.innerHTML = '<p class="text-muted">Φόρτωση…</p>';
        dialog.showModal();
        requestJson(url)
            .then(function (data) {
                if (!data.ok) {
                    throw new Error("bad response");
                }
                mountForm(data.html);
            })
            .catch(function () {
                body.textContent = "";
                showDialogError("Αποτυχία φόρτωσης της φόρμας υπηρεσίας.");
            });
    };

    const deleteService = function (button) {
        const label = button.dataset.utilityServiceLabel || "";
        if (!window.confirm("Διαγραφή της υπηρεσίας " + label + ";")) {
            return;
        }
        button.disabled = true;
        const token = document.querySelector('input[name="csrfmiddlewaretoken"]');
        const data = new FormData();
        data.append("csrfmiddlewaretoken", token ? token.value : "");
        requestJson(button.dataset.utilityServiceDelete, { method: "POST", body: data })
            .then(function (result) {
                if (!result.ok) {
                    throw new Error("bad response");
                }
                replaceGrid(result.grid_html);
                showStatus(result.message);
            })
            .catch(function () {
                button.disabled = false;
                showStatus("Αποτυχία διαγραφής της υπηρεσίας.", "error");
            });
    };

    document.addEventListener("click", function (event) {
        const sort = event.target.closest("[data-utility-service-sort]");
        if (sort) {
            event.preventDefault();
            sortGrid(sort);
            return;
        }
        if (!dialog) {
            return;
        }
        const open = event.target.closest("[data-utility-service-open]");
        if (open) {
            event.preventDefault();
            openForm(open.dataset.utilityServiceOpen);
            return;
        }
        const remove = event.target.closest("[data-utility-service-delete]");
        if (remove) {
            event.preventDefault();
            deleteService(remove);
        }
    });
})();


// Suitability consultations grid (Ενότητα 5): sortable columns; add / edit / delete in a modal.
(function () {
    const collator = new Intl.Collator("el", { numeric: true, sensitivity: "base" });

    const sortGrid = function (button) {
        const table = button.closest("[data-suitability-consultation-table]");
        const tbody = table ? table.querySelector("tbody") : null;
        if (!tbody) {
            return;
        }
        const key = button.dataset.suitabilityConsultationSort;
        const nextDir = table.dataset.sortKey === key && table.dataset.sortDir === "asc" ? "desc" : "asc";
        table.dataset.sortKey = key;
        table.dataset.sortDir = nextDir;
        table.querySelectorAll("th").forEach(function (th) {
            th.removeAttribute("aria-sort");
        });
        button.closest("th").setAttribute("aria-sort", nextDir === "asc" ? "ascending" : "descending");
        const read = function (row) {
            const cell = row.querySelector("[data-sort-" + key + "]");
            return cell ? cell.getAttribute("data-sort-" + key) || "" : "";
        };
        const rows = Array.from(tbody.querySelectorAll("tr[data-suitability-consultation-row]"));
        rows.sort(function (a, b) {
            const order = collator.compare(read(a), read(b));
            return nextDir === "asc" ? order : -order;
        });
        rows.forEach(function (row) {
            tbody.appendChild(row);
        });
    };

    const dialog = document.querySelector("[data-suitability-consultation-dialog]");
    const body = dialog ? dialog.querySelector("[data-suitability-consultation-dialog-body]") : null;
    const errors = dialog ? dialog.querySelector("[data-suitability-consultation-errors]") : null;

    const showDialogError = function (message) {
        errors.textContent = message;
        errors.hidden = !message;
    };

    const showStatus = function (message, kind) {
        const status = document.querySelector("[data-suitability-consultation-status]");
        if (!status) {
            return;
        }
        status.textContent = "";
        const alert = document.createElement("div");
        alert.className = "alert alert--" + (kind || "success");
        alert.setAttribute("role", "status");
        alert.textContent = message;
        status.appendChild(alert);
    };

    const replaceGrid = function (html) {
        const grid = document.querySelector("[data-suitability-consultation-container]");
        if (grid) {
            grid.outerHTML = html;
        }
    };

    const requestJson = function (url, options) {
        return fetch(url, Object.assign({
            headers: { Accept: "application/json" },
            credentials: "same-origin",
        }, options)).then(function (response) {
            return response.json();
        });
    };

    const mountForm = function (html, pendingFiles) {
        body.innerHTML = html;
        bindOtherGroups(body);
        bindFilePickers(body, pendingFiles);
        const form = body.querySelector("[data-suitability-consultation-form]");
        form.addEventListener("submit", onSubmit);
        const first = form.querySelector("select, input:not([type=hidden]), textarea");
        if (first) {
            first.focus();
        }
    };

    const onSubmit = function (event) {
        event.preventDefault();
        const form = event.currentTarget;
        const submit = form.querySelector('button[type="submit"]');
        submit.disabled = true;
        showDialogError("");
        requestJson(form.action, { method: "POST", body: new FormData(form) })
            .then(function (data) {
                if (!data.ok) {
                    const fileInput = form.querySelector('[data-file-picker] input[type="file"]');
                    mountForm(data.html, fileInput ? Array.from(fileInput.files) : []);
                    return;
                }
                replaceGrid(data.grid_html);
                showStatus(data.message);
                dialog.close();
            })
            .catch(function () {
                showDialogError("Αποτυχία επικοινωνίας με τον διακομιστή.");
            })
            .finally(function () {
                submit.disabled = false;
            });
    };

    const openForm = function (url) {
        showDialogError("");
        body.innerHTML = '<p class="text-muted">Φόρτωση…</p>';
        dialog.showModal();
        requestJson(url)
            .then(function (data) {
                if (!data.ok) {
                    throw new Error("bad response");
                }
                mountForm(data.html);
            })
            .catch(function () {
                body.textContent = "";
                showDialogError("Αποτυχία φόρτωσης της φόρμας διαβούλευσης.");
            });
    };

    const deleteConsultation = function (button) {
        const label = button.dataset.suitabilityConsultationLabel || "";
        if (!window.confirm("Διαγραφή της διαβούλευσης " + label + ";")) {
            return;
        }
        button.disabled = true;
        const token = document.querySelector('input[name="csrfmiddlewaretoken"]');
        const data = new FormData();
        data.append("csrfmiddlewaretoken", token ? token.value : "");
        requestJson(button.dataset.suitabilityConsultationDelete, { method: "POST", body: data })
            .then(function (result) {
                if (!result.ok) {
                    throw new Error("bad response");
                }
                replaceGrid(result.grid_html);
                showStatus(result.message);
            })
            .catch(function () {
                button.disabled = false;
                showStatus("Αποτυχία διαγραφής της διαβούλευσης.", "error");
            });
    };

    document.addEventListener("click", function (event) {
        const sort = event.target.closest("[data-suitability-consultation-sort]");
        if (sort) {
            event.preventDefault();
            sortGrid(sort);
            return;
        }
        if (!dialog) {
            return;
        }
        const open = event.target.closest("[data-suitability-consultation-open]");
        if (open) {
            event.preventDefault();
            openForm(open.dataset.suitabilityConsultationOpen);
            return;
        }
        const remove = event.target.closest("[data-suitability-consultation-delete]");
        if (remove) {
            event.preventDefault();
            deleteConsultation(remove);
        }
    });
})();


