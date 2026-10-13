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



(function () {

    const groups = Array.from(document.querySelectorAll("[data-nav-group]"));

    if (!groups.length) {

        return;

    }

    function setOpen(group, open) {

        group.classList.toggle("is-open", open);

        group.querySelector("[data-nav-group-toggle]").setAttribute("aria-expanded", open ? "true" : "false");

    }

    groups.forEach(function (group) {

        group.querySelector("[data-nav-group-toggle]").addEventListener("click", function () {

            const open = !group.classList.contains("is-open");

            groups.forEach(function (other) {

                setOpen(other, other === group && open);

            });

        });

    });

    document.addEventListener("click", function (event) {

        groups.forEach(function (group) {

            if (!group.contains(event.target)) {

                setOpen(group, false);

            }

        });

    });

    document.addEventListener("keydown", function (event) {

        if (event.key !== "Escape") {

            return;

        }

        groups.forEach(function (group) {

            if (group.classList.contains("is-open")) {

                setOpen(group, false);

                group.querySelector("[data-nav-group-toggle]").focus();

            }

        });

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



// Ενότητα 6 — PDF export with selectable subsections 6.1–6.6.

(function () {

    document.addEventListener("click", function (event) {

        const exportBtn = event.target.closest("[data-section-6-report-pdf-export]");

        if (!exportBtn) {

            return;

        }

        const dialog = exportBtn.closest("dialog");

        if (!dialog) {

            return;

        }

        const baseUrl = dialog.dataset.pdfBaseUrl;

        const error = dialog.querySelector("[data-section-6-report-pdf-error]");

        const checked = dialog.querySelectorAll('input[name="subsection"]:checked');

        if (!baseUrl) {

            return;

        }

        if (checked.length === 0) {

            if (error) {

                error.hidden = false;

            }

            return;

        }

        if (error) {

            error.hidden = true;

        }

        const params = new URLSearchParams();

        checked.forEach(function (box) {

            params.append("include", box.value);

        });

        window.location.href = baseUrl + "?" + params.toString();

        dialog.close();

    });

})();



// Grids and dialogs driven by JSON endpoints; helpers are scoped to this block.
(function () {
    // ---------------------------------------------------------------------------
    // Shared helpers for the JSON endpoints, status alerts and sortable grids below.
    // ---------------------------------------------------------------------------

    const SERVER_ERROR_MESSAGE = "Αποτυχία επικοινωνίας με τον διακομιστή.";

    const GREEK_COLLATOR = new Intl.Collator("el", { numeric: true, sensitivity: "base" });

    function requestJson(url, options) {
        return fetch(url, Object.assign({
            headers: { Accept: "application/json" },
            credentials: "same-origin",
        }, options)).then(function (response) {
            return response.json();
        });
    }

    // POST body carrying only the page's CSRF token (used by the grid delete buttons).
    function csrfFormData() {
        const token = document.querySelector('input[name="csrfmiddlewaretoken"]');
        const data = new FormData();
        data.append("csrfmiddlewaretoken", token ? token.value : "");
        return data;
    }

    // Replaces the contents of the status area `selector` with one alert (text only).
    function showStatusAlert(selector, message, kind) {
        const status = document.querySelector(selector);
        if (!status) {
            return;
        }
        status.textContent = "";
        const alert = document.createElement("div");
        alert.className = "alert alert--" + (kind || "success");
        alert.setAttribute("role", "status");
        alert.textContent = message;
        status.appendChild(alert);
    }

    // Swaps a server-rendered fragment (grid, log) in place.
    function replaceOuterHtml(selector, html) {
        const element = document.querySelector(selector);
        if (element) {
            element.outerHTML = html;
        }
    }

    // Same column clicked again flips the direction; another column starts ascending.
    function toggleSortDir(table, key) {
        const currentKey = table.dataset.sortKey || "";
        const currentDir = table.dataset.sortDir || "asc";
        const nextDir = currentKey === key && currentDir === "asc" ? "desc" : "asc";
        table.dataset.sortKey = key;
        table.dataset.sortDir = nextDir;
        return nextDir;
    }

    function sortValue(row, key) {
        const cell = row.querySelector("[data-sort-" + key + "]");
        return cell ? cell.getAttribute("data-sort-" + key) || "" : "";
    }

    // Reorders `rowSelector` rows of `tbody` by their data-sort-<key> cells; `compare` sorts ascending.
    function reorderRows(tbody, rowSelector, key, dir, compare) {
        const rows = Array.from(tbody.querySelectorAll(rowSelector));
        rows.sort(function (a, b) {
            const order = compare(sortValue(a, key), sortValue(b, key));
            return dir === "asc" ? order : -order;
        });
        rows.forEach(function (row) {
            tbody.appendChild(row);
        });
    }

    // Ascending comparator on transform(value).
    function compareBy(transform) {
        return function (a, b) {
            const left = transform(a);
            const right = transform(b);
            if (left < right) {
                return -1;
            }
            if (left > right) {
                return 1;
            }
            return 0;
        };
    }

    function rankOf(ranks) {
        return function (value) {
            return ranks[value] || 0;
        };
    }

    function dateValue(value) {
        return Date.parse(value) || 0;
    }

    function numberValue(value) {
        return Number(value) || 0;
    }

    function lowerValue(value) {
        return value.toLowerCase();
    }

    // Sorting of the modal grids that follow the data-<name>-table / -row / -sort convention:
    // Greek-aware collation and aria-sort on the clicked header.
    function collatorSort(name) {
        return {
            button: "[data-" + name + "-sort]",
            apply: function (button) {
                const table = button.closest("[data-" + name + "-table]");
                const tbody = table ? table.querySelector("tbody") : null;
                if (!tbody) {
                    return;
                }
                const key = button.getAttribute("data-" + name + "-sort");
                const nextDir = toggleSortDir(table, key);
                table.querySelectorAll("th").forEach(function (th) {
                    th.removeAttribute("aria-sort");
                });
                button.closest("th").setAttribute("aria-sort", nextDir === "asc" ? "ascending" : "descending");
                reorderRows(tbody, "tr[data-" + name + "-row]", key, nextDir, GREEK_COLLATOR.compare);
            },
        };
    }

    // Binds the form fragments that host «Άλλο» choices and multiple-file pickers.
    function bindOtherGroupsAndFilePickers(body, pendingFiles) {
        bindOtherGroups(body);
        bindFilePickers(body, pendingFiles);
    }

    /*
     * Grid edited in a modal, each change saved immediately so unsaved edits elsewhere on the page
     * survive. The markup follows a naming convention on `config.name` (e.g. "consultation"):
     *   [data-<name>-dialog] > [data-<name>-errors], [data-<name>-dialog-body]
     *   [data-<name>-open]="<form url>"      opens the dialog with the server-rendered form
     *   [data-<name>-form]                   form fragment (JSON {ok, html} / {ok, grid_html, message})
     *   [data-<name>-delete]="<url>" + [data-<name>-label]
     *   [data-<name>-container]              grid replaced from grid_html (config.containerSelector)
     *   [data-<name>-status]                 success / error alerts
     * Options:
     *   requireDialog      skip everything (sorting too) when the page has no dialog
     *   sort               {button, apply(button)} column sorting, active even without the dialog
     *   bindForm(body, pendingFiles)  binders run on the freshly mounted fragment
     *   afterMount(form)   extra binding after the submit handler is attached
     *   focusSelector      first field to focus (none when omitted)
     *   keepFiles          on a validation re-render, carry the chosen files over
     *   reloadOnSave       honour {reload: true} on save
     *   loadingHtml, loadErrorMessage
     *   deleteRow(button, ui)  custom delete; otherwise confirm(deleteConfirm + label + ";") + POST
     *   reloadOnDelete     honour {reload: true} on delete
     *   serverDeleteErrors show the server's message (or the thrown error) instead of deleteErrorMessage
     */
    function initGridModal(config) {
        const name = config.name;
        const attr = function (suffix) {
            return "data-" + name + "-" + suffix;
        };
        const sel = function (suffix) {
            return "[" + attr(suffix) + "]";
        };

        const dialog = document.querySelector(sel("dialog"));
        if (config.requireDialog && !dialog) {
            return;
        }
        const body = dialog ? dialog.querySelector(sel("dialog-body")) : null;
        const errors = dialog ? dialog.querySelector(sel("errors")) : null;
        const containerSelector = config.containerSelector || sel("container");

        const ui = {
            showStatus: function (message, kind) {
                showStatusAlert(sel("status"), message, kind);
            },
            replaceGrid: function (html) {
                replaceOuterHtml(containerSelector, html);
                if (config.afterGridReplace) {
                    config.afterGridReplace(document.querySelector(containerSelector));
                }
            },
        };

        const showDialogError = function (message) {
            if (!errors) {
                return;
            }
            errors.textContent = message;
            errors.hidden = !message;
        };

        const mountForm = function (html, pendingFiles) {
            body.innerHTML = html;
            if (config.bindForm) {
                config.bindForm(body, pendingFiles);
            }
            const form = body.querySelector(sel("form"));
            form.addEventListener("submit", onSubmit);
            if (config.afterMount) {
                config.afterMount(form);
            }
            if (config.focusSelector) {
                const first = form.querySelector(config.focusSelector);
                if (first) {
                    first.focus();
                }
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
                        if (config.keepFiles) {
                            // Browsers cannot refill a file input, so keep the chosen files across the re-render.
                            const fileInput = form.querySelector('[data-file-picker] input[type="file"]');
                            mountForm(data.html, fileInput ? Array.from(fileInput.files) : []);
                        } else {
                            mountForm(data.html);
                        }
                        return;
                    }
                    if (config.reloadOnSave && data.reload) {
                        window.location.reload();
                        return;
                    }
                    ui.replaceGrid(data.grid_html);
                    ui.showStatus(data.message);
                    dialog.close();
                })
                .catch(function () {
                    showDialogError(SERVER_ERROR_MESSAGE);
                })
                .finally(function () {
                    submit.disabled = false;
                });
        };

        const openForm = function (url) {
            showDialogError("");
            body.innerHTML = config.loadingHtml || '<p class="text-muted">Φόρτωση…</p>';
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
                    showDialogError(config.loadErrorMessage);
                });
        };

        const deleteRow = function (button) {
            if (config.deleteRow) {
                config.deleteRow(button, ui);
                return;
            }
            const label = button.getAttribute(attr("label")) || "";
            if (!window.confirm(config.deleteConfirm + label + ";")) {
                return;
            }
            button.disabled = true;
            requestJson(button.getAttribute(attr("delete")), { method: "POST", body: csrfFormData() })
                .then(function (result) {
                    if (!result.ok) {
                        throw new Error(config.serverDeleteErrors ? result.message || "bad response" : "bad response");
                    }
                    if (config.reloadOnDelete && result.reload) {
                        window.location.reload();
                        return;
                    }
                    ui.replaceGrid(result.grid_html);
                    ui.showStatus(result.message);
                })
                .catch(function (error) {
                    button.disabled = false;
                    ui.showStatus(
                        config.serverDeleteErrors && error.message !== "bad response"
                            ? error.message
                            : config.deleteErrorMessage,
                        "error"
                    );
                });
        };

        document.addEventListener("click", function (event) {
            if (config.sort) {
                const sort = event.target.closest(config.sort.button);
                if (sort) {
                    event.preventDefault();
                    config.sort.apply(sort);
                    return;
                }
            }
            if (!dialog) {
                return;
            }
            const open = event.target.closest(sel("open"));
            if (open) {
                event.preventDefault();
                openForm(open.getAttribute(attr("open")));
                return;
            }
            const remove = event.target.closest(sel("delete"));
            if (remove) {
                event.preventDefault();
                deleteRow(remove);
            }
        });
    }



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

            const error = dialog.querySelector("[data-section-6-report-pdf-error]");

            if (error) {

                error.hidden = true;

            }

            dialog.showModal();

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

            // 3.1 Each plot row carries its own predefined subject.
            const subject = form.querySelector('[name="subject"]');

            if (subject && button.dataset.emailSubject !== undefined) {

                subject.value = button.dataset.emailSubject;

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

                requestJson(form.action, { method: "POST", body: new FormData(form) })

                    .then(function (data) {

                        if (!data.ok) {

                            showErrors(errors, data.errors || []);

                            return;

                        }

                        // 2.2 is the default; the 3.1 land plot dialog names its own targets.
                        replaceOuterHtml(
                            form.dataset.emailLogTarget || "[data-deficiency-email-log]",
                            data.log_html
                        );

                        if (data.grid_html) {

                            replaceOuterHtml(
                                form.dataset.emailGridTarget || "[data-completeness-check-container]",
                                data.grid_html
                            );

                        }

                        showStatusAlert(
                            form.dataset.emailStatusTarget || "[data-completeness-check-status]",
                            data.message
                        );

                        dialog.close();

                    })

                    .catch(function () {

                        showErrors(errors, [SERVER_ERROR_MESSAGE]);

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



        const statusRank = rankOf({ sent: 2, draft: 1 });

        const sortCommunicationGrid = function (button) {
            const table = button.closest("[data-communication-table]");
            if (!table) {
                return;
            }
            const key = button.dataset.communicationSort;
            const nextDir = toggleSortDir(table, key);
            const tbody = table.querySelector("tbody");
            if (!tbody) {
                return;
            }
            let transform = lowerValue;
            if (key === "sent-at") {
                transform = dateValue;
            } else if (key === "status") {
                transform = statusRank;
            }
            reorderRows(tbody, "tr[data-communication-row]", key, nextDir, compareBy(transform));
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
        const resultRank = rankOf({ yes: 2, no: 1 });

        const sortGrid = function (button) {
            const table = document.querySelector("[data-completeness-check-table]");
            if (!table) {
                return;
            }
            const key = button.dataset.completenessSort;
            const nextDir = toggleSortDir(table, key);
            const tbody = table.querySelector("tbody");
            if (!tbody) {
                return;
            }
            let transform = lowerValue;
            if (key === "sequence" || key === "emails") {
                transform = numberValue;
            } else if (key === "date") {
                transform = dateValue;
            } else if (key === "result") {
                transform = resultRank;
            }
            reorderRows(tbody, "tr[data-completeness-row]", key, nextDir, compareBy(transform));
        };

        // A check that blocks deletion (e.g. has sent emails) explains why instead of asking;
        // a refused delete may still refresh the grid.
        const deleteCheck = function (button, ui) {
            const blockedReason = button.dataset.completenessCheckDeleteBlockedReason || "";
            if (blockedReason) {
                ui.showStatus(blockedReason, "error");
                return;
            }
            const label = button.dataset.completenessCheckLabel || "";
            if (!window.confirm("Διαγραφή του ελέγχου " + label + ";")) {
                return;
            }
            button.disabled = true;
            requestJson(button.dataset.completenessCheckDelete, { method: "POST", body: csrfFormData() })
                .then(function (result) {
                    if (!result.ok) {
                        ui.showStatus(result.message || "Αποτυχία διαγραφής του ελέγχου.", "error");
                        if (result.grid_html) {
                            ui.replaceGrid(result.grid_html);
                        }
                        return;
                    }
                    ui.replaceGrid(result.grid_html);
                    ui.showStatus(result.message);
                })
                .catch(function () {
                    ui.showStatus("Αποτυχία διαγραφής του ελέγχου.", "error");
                })
                .finally(function () {
                    button.disabled = false;
                });
        };

        initGridModal({
            name: "completeness-check",
            requireDialog: true,
            sort: { button: "[data-completeness-sort]", apply: sortGrid },
            bindForm: bindCompletenessDeficiencies,
            loadingHtml: '<p class="text-muted">Φόρτωση...</p>',
            loadErrorMessage: "Αποτυχία φόρτωσης της φόρμας ελέγχου.",
            deleteRow: deleteCheck,
        });
    })();


    // Land plot grids — 3.1 add / edit / delete and 4.1 edit of the technical evaluation — in a
    // modal, each saved immediately so unsaved edits elsewhere on the page survive.
    (function () {
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

        const deletePlot = function (button, ui) {
            const url = button.dataset.landPlotDelete;
            const label = button.dataset.landPlotLabel || "";
            const warning = button.dataset.landPlotWarning || "";
            if (!confirmDelete(label, warning)) {
                return;
            }
            const send = function (evaluationConfirmed) {
                const data = csrfFormData();
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
                        ui.replaceGrid(result.grid_html);
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
                    if (!result.ok && result.message) {
                        // Refused, e.g. the parcel is the origin of a 7.3 plot.
                        if (result.grid_html) {
                            ui.replaceGrid(result.grid_html);
                        }
                        ui.showStatus(result.message, "error");
                        return;
                    }
                    if (!result.ok) {
                        throw new Error("bad response");
                    }
                    ui.replaceGrid(result.grid_html);
                    ui.showStatus(result.message);
                })
                .catch(function () {
                    button.disabled = false;
                    ui.showStatus("Αποτυχία διαγραφής του τεμαχίου.", "error");
                });
        };

        initGridModal({
            name: "land-plot",
            requireDialog: true,
            containerSelector: "[data-land-plot-grid]",
            bindForm: bindOtherGroupsAndFilePickers,
            keepFiles: true,
            focusSelector: "input:not([type=hidden]), select, textarea",
            loadErrorMessage: "Αποτυχία φόρτωσης της φόρμας τεμαχίου.",
            deleteRow: deletePlot,
        });
    })();


    const MODAL_FOCUS = "select, input:not([type=hidden]), textarea";

    // Utility services grid (4.2): columns sort on click (also on the read-only case folder);
    // add / edit / delete in a modal, each saved immediately.
    initGridModal({
        name: "utility-service",
        sort: collatorSort("utility-service"),
        focusSelector: MODAL_FOCUS,
        reloadOnSave: true,
        loadErrorMessage: "Αποτυχία φόρτωσης της φόρμας υπηρεσίας.",
        deleteConfirm: "Διαγραφή της υπηρεσίας ",
        deleteErrorMessage: "Αποτυχία διαγραφής της υπηρεσίας.",
    });


    // Consultations grid (Ενότητα 5 and 7.4): sortable columns; add / edit / delete in a modal.
    initGridModal({
        name: "consultation",
        sort: collatorSort("consultation"),
        bindForm: bindOtherGroupsAndFilePickers,
        keepFiles: true,
        focusSelector: MODAL_FOCUS,
        loadErrorMessage: "Αποτυχία φόρτωσης της φόρμας διαβούλευσης.",
        deleteConfirm: "Διαγραφή της διαβούλευσης ",
        deleteErrorMessage: "Αποτυχία διαγραφής της διαβούλευσης.",
    });


    // Ministry decision rounds grid (6.7): sortable columns; add / edit / delete in a modal.
    // A refused delete shows the server's reason; a delete may ask for a full reload.
    initGridModal({
        name: "ministry-decision-round",
        sort: collatorSort("ministry-decision-round"),
        bindForm: bindOtherGroupsAndFilePickers,
        keepFiles: true,
        focusSelector: MODAL_FOCUS,
        loadErrorMessage: "Αποτυχία φόρτωσης της φόρμας.",
        deleteConfirm: "Διαγραφή της εγγραφής ",
        deleteErrorMessage: "Αποτυχία διαγραφής της εγγραφής.",
        reloadOnDelete: true,
        serverDeleteErrors: true,
    });


    const MAX_BULK_ROWS = 500;

    // 7.3 «Μαζική προσθήκη»: one numbering textbox per row while «Χειροκίνητη» is selected.
    function bindBulkNumbering(form) {
        const countInput = form.querySelector("[data-bulk-count]");
        const manual = form.querySelector("[data-bulk-manual]");
        const rows = manual ? manual.querySelector("[data-bulk-manual-rows]") : null;
        if (!countInput || !rows) {
            return;
        }
        const isManual = function () {
            const checked = form.querySelector("[data-bulk-numbering-mode]:checked");
            return Boolean(checked) && checked.value === "manual";
        };
        const addRow = function (index) {
            const row = document.createElement("tr");
            const position = document.createElement("td");
            position.textContent = String(index);
            const cell = document.createElement("td");
            const input = document.createElement("input");
            input.type = "text";
            input.name = "manual_numbers";
            input.className = "input";
            input.maxLength = 64;
            input.setAttribute("aria-label", "Αρίθμηση εγγραφής " + index);
            cell.appendChild(input);
            row.appendChild(position);
            row.appendChild(cell);
            rows.appendChild(row);
        };
        const sync = function () {
            const manualMode = isManual();
            const parsed = parseInt(countInput.value, 10);
            const count = Number.isFinite(parsed) ? Math.min(Math.max(parsed, 0), MAX_BULK_ROWS) : 0;
            if (manualMode) {
                while (rows.children.length > count) {
                    rows.lastElementChild.remove();
                }
                while (rows.children.length < count) {
                    addRow(rows.children.length + 1);
                }
            }
            manual.hidden = !manualMode || count === 0;
            rows.querySelectorAll("input").forEach(function (input) {
                input.disabled = !manualMode;
            });
        };
        countInput.addEventListener("input", sync);
        form.querySelectorAll("[data-bulk-numbering-mode]").forEach(function (radio) {
            radio.addEventListener("change", sync);
        });
        sync();
    }

    // Approved design plots workspace: load only when opened so every case screen stays lightweight.
    document.addEventListener("click", function (event) {
        const open = event.target.closest("[data-approved-design-plots-workspace-open]");
        if (!open) {
            return;
        }
        event.preventDefault();
        const dialog = document.getElementById("approved-design-plots-workspace");
        const body = dialog ? dialog.querySelector("[data-approved-design-plots-workspace-body]") : null;
        if (!dialog || !body) {
            return;
        }
        body.innerHTML = '<p class="text-muted">Φόρτωση…</p>';
        dialog.showModal();
        requestJson(open.dataset.approvedDesignPlotsWorkspaceOpen)
            .then(function (data) {
                if (!data.ok) {
                    throw new Error("bad response");
                }
                body.innerHTML = data.grid_html;
                bindOtherGroups(body);
            })
            .catch(function () {
                body.innerHTML = "";
                showStatusAlert(
                    "[data-approved-design-plot-status]",
                    "Αποτυχία φόρτωσης του πίνακα οικοπέδων.",
                    "error"
                );
            });
    });

    // Additions use a form dialog; existing rows save inline.
    initGridModal({
        name: "approved-design-plot",
        sort: collatorSort("approved-design-plot"),
        bindForm: bindOtherGroups,
        afterGridReplace: function (container) {
            if (container) {
                bindOtherGroups(container);
            }
        },
        afterMount: function (form) {
            if (form.hasAttribute("data-approved-design-plot-bulk")) {
                bindBulkNumbering(form);
            }
        },
        focusSelector: MODAL_FOCUS,
        loadErrorMessage: "Αποτυχία φόρτωσης της φόρμας.",
        deleteConfirm: "Διαγραφή της εγγραφής ",
        deleteErrorMessage: "Αποτυχία διαγραφής της εγγραφής.",
    });

    document.addEventListener("submit", function (event) {
        const form = event.target.closest("[data-approved-design-plot-inline-form]");
        if (!form) {
            return;
        }
        event.preventDefault();
        const submit = form.querySelector('button[type="submit"]');
        submit.disabled = true;
        requestJson(form.action, { method: "POST", body: new FormData(form) })
            .then(function (data) {
                if (data.grid_html) {
                    replaceOuterHtml("[data-approved-design-plot-container]", data.grid_html);
                    const container = document.querySelector("[data-approved-design-plot-container]");
                    if (container) {
                        bindOtherGroups(container);
                    }
                }
                if (!data.ok) {
                    showStatusAlert(
                        "[data-approved-design-plot-status]",
                        "Η εγγραφή δεν αποθηκεύτηκε. Ελέγξτε τα επισημασμένα πεδία.",
                        "error"
                    );
                    return;
                }
                showStatusAlert("[data-approved-design-plot-status]", data.message);
            })
            .catch(function () {
                submit.disabled = false;
                showStatusAlert(
                    "[data-approved-design-plot-status]",
                    SERVER_ERROR_MESSAGE,
                    "error"
                );
            });
    });


    // Construction works checks grid (7.6): sortable columns; add / edit / delete in a modal.
    initGridModal({
        name: "infrastructure-check",
        sort: collatorSort("infrastructure-check"),
        focusSelector: MODAL_FOCUS,
        loadErrorMessage: "Αποτυχία φόρτωσης της φόρμας.",
        deleteConfirm: "Διαγραφή του ελέγχου ",
        deleteErrorMessage: "Αποτυχία διαγραφής του ελέγχου.",
    });

    // Publication methods grid of an announcement (9.2): add / edit / delete in a modal.
    initGridModal({
        name: "publication",
        sort: collatorSort("publication"),
        focusSelector: MODAL_FOCUS,
        loadErrorMessage: "Αποτυχία φόρτωσης της φόρμας.",
        deleteConfirm: "Διαγραφή του τρόπου δημοσίευσης ",
        deleteErrorMessage: "Αποτυχία διαγραφής του τρόπου δημοσίευσης.",
        serverDeleteErrors: true,
    });
})();

// Role permission matrix: «Όλα» per row; any access implies «Προβολή» on the row and on the
// parent function, and removing «Προβολή» clears the row (and the sub-functions of a function).
(function () {
    const matrix = document.querySelector("[data-access-matrix]");
    if (!matrix) {
        return;
    }
    const grantBoxes = function (row) {
        return Array.from(row.querySelectorAll('input[type="checkbox"][name^="grant__"]'));
    };
    const viewBox = function (row) {
        return row.querySelector('input[type="checkbox"][name$="__view"]');
    };
    const parentRow = function (row) {
        return matrix.querySelector('tr[data-access-parent][data-access-group="' + row.dataset.accessGroup + '"]');
    };
    const childRows = function (row) {
        return Array.from(matrix.querySelectorAll('tr[data-access-group="' + row.dataset.accessGroup + '"]'))
            .filter(function (other) { return other !== row; });
    };
    const syncToggle = function (row) {
        const toggle = row.querySelector("[data-access-row-toggle]");
        const boxes = grantBoxes(row);
        toggle.checked = boxes.length > 0 && boxes.every(function (box) { return box.checked; });
        toggle.indeterminate = !toggle.checked && boxes.some(function (box) { return box.checked; });
    };
    const syncAll = function () {
        matrix.querySelectorAll("tr[data-access-row]").forEach(syncToggle);
    };
    const ensureView = function (row) {
        const view = viewBox(row);
        if (view) {
            view.checked = true;
        }
        if (!row.hasAttribute("data-access-parent")) {
            const parent = parentRow(row);
            if (parent && viewBox(parent)) {
                viewBox(parent).checked = true;
            }
        }
    };
    const clearRow = function (row) {
        grantBoxes(row).forEach(function (box) { box.checked = false; });
        if (row.hasAttribute("data-access-parent")) {
            childRows(row).forEach(function (child) {
                grantBoxes(child).forEach(function (box) { box.checked = false; });
            });
        }
    };
    matrix.addEventListener("change", function (event) {
        const box = event.target;
        const row = box.closest("tr[data-access-row]");
        if (!row) {
            return;
        }
        if (box.hasAttribute("data-access-row-toggle")) {
            if (box.checked) {
                grantBoxes(row).forEach(function (other) { other.checked = true; });
                ensureView(row);
            } else {
                clearRow(row);
            }
        } else if (box.checked) {
            ensureView(row);
        } else if (box === viewBox(row)) {
            clearRow(row);
        }
        syncAll();
    });
    syncAll();
})();

(function () {
    // Plain POST forms that ask before an irreversible action: <form data-confirm="...">.
    document.addEventListener("submit", function (event) {
        const form = event.target.closest("form[data-confirm]");
        if (form && !window.confirm(form.getAttribute("data-confirm"))) {
            event.preventDefault();
        }
    });
})();
