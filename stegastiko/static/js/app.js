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

        if (close) {
            const dialog = close.closest("dialog");
            if (dialog) {
                dialog.close();
            }
            return;
        }

        if (
            event.target &&
            event.target.matches &&
            event.target.matches(
                "dialog[data-documents-modal], dialog[data-incomplete-reject-dialog], dialog[data-eligibility-override-dialog]"
            )
        ) {
            const rect = event.target.getBoundingClientRect();
            const inside =
                event.clientX >= rect.left &&
                event.clientX <= rect.right &&
                event.clientY >= rect.top &&
                event.clientY <= rect.bottom;
            if (!inside) {
                event.target.close();
            }
        }

    });

})();

// Top toolbar actions dropdown menu ([data-actions-dropdown]) and eligibility override reason toggle.
(function () {
    function closeAllActionDropdowns(except) {
        document.querySelectorAll("[data-actions-dropdown].is-open").forEach(function (dropdown) {
            if (dropdown === except) {
                return;
            }
            dropdown.classList.remove("is-open");
            const toggle = dropdown.querySelector("[data-actions-dropdown-toggle]");
            if (toggle) {
                toggle.setAttribute("aria-expanded", "false");
            }
        });
    }

    document.addEventListener("click", function (event) {
        if (event.target.closest && event.target.closest("[data-ui-edit-trigger]")) {
            return;
        }
        const toggle = event.target.closest ? event.target.closest("[data-actions-dropdown-toggle]") : null;
        if (toggle) {
            event.preventDefault();
            const dropdown = toggle.closest("[data-actions-dropdown]");
            if (!dropdown) {
                return;
            }
            const willOpen = !dropdown.classList.contains("is-open");
            closeAllActionDropdowns(dropdown);
            dropdown.classList.toggle("is-open", willOpen);
            toggle.setAttribute("aria-expanded", willOpen ? "true" : "false");
            return;
        }

        const item = event.target.closest
            ? event.target.closest("[data-actions-dropdown-menu] .actions-dropdown__item")
            : null;
        if (item) {
            closeAllActionDropdowns(null);
            return;
        }

        if (!event.target.closest || !event.target.closest("[data-actions-dropdown]")) {
            closeAllActionDropdowns(null);
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            closeAllActionDropdowns(null);
        }
    });

    document.querySelectorAll("[data-eligibility-override-form]").forEach(function (formEl) {
        const select = formEl.querySelector('select[name="eligibility_override"]');
        const wrap = formEl.querySelector("[data-eligibility-override-reason-wrap]");
        const textarea = formEl.querySelector('textarea[name="eligibility_override_reason"]');
        if (!select || !wrap) {
            return;
        }
        const sync = function () {
            wrap.hidden = !select.value;
            if (textarea) {
                textarea.required = Boolean(select.value);
            }
        };
        select.addEventListener("change", sync);
        sync();
    });

    document.querySelectorAll("[data-incomplete-reject-form]").forEach(function (formEl) {
        const textarea = formEl.querySelector('textarea[name="incomplete_rejection_reason"]');
        const dialog = formEl.closest("dialog");
        const errorEl = dialog ? dialog.querySelector("[data-incomplete-reject-error]") : null;
        if (!textarea) {
            return;
        }
        textarea.addEventListener("input", function () {
            if (errorEl) {
                errorEl.hidden = true;
                errorEl.textContent = "";
            }
        });
        formEl.addEventListener("submit", function (event) {
            if (!textarea.value.trim()) {
                event.preventDefault();
                textarea.value = "";
                if (errorEl) {
                    errorEl.textContent = "Ο λόγος απόρριψης είναι υποχρεωτικός.";
                    errorEl.hidden = false;
                }
                textarea.focus();
            }
        });
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

        if (document.body.hasAttribute("data-embed-mode")) {

            params.set("embed", "1");

        }

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
            if (typeof window.refreshUiTexts === "function") {
                const updated = document.querySelector(selector);
                if (updated) {
                    window.refreshUiTexts(updated);
                }
            }
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
            if (typeof window.refreshUiTexts === "function") {
                window.refreshUiTexts(body);
            }
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



    // 2.2 deficiencies email dialog & plot application email dialog, sent without reloading so unsaved edits survive.

    function escapeEmailHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function formatEmailBodyHtml(rawText) {
        return escapeEmailHtml(rawText).replace(
            /\*\*\*([^\n*]+?)\*\*\*/g,
            '<strong class="email-doc-note"><em>$1</em></strong>'
        );
    }

    function serializeEmailRichNode(node) {
        if (!node) {
            return "";
        }
        if (node.nodeType === 3) {
            return node.nodeValue || "";
        }
        if (node.nodeType !== 1) {
            return "";
        }
        const tag = (node.tagName || "").toUpperCase();
        if (tag === "BR") {
            return "\n";
        }
        const isBoldItalicNote =
            node.classList.contains("email-doc-note") ||
            ((tag === "STRONG" || tag === "B") &&
                node.childElementCount === 1 &&
                (node.firstElementChild.tagName === "EM" || node.firstElementChild.tagName === "I")) ||
            ((tag === "EM" || tag === "I") &&
                node.childElementCount === 1 &&
                (node.firstElementChild.tagName === "STRONG" || node.firstElementChild.tagName === "B"));
        if (isBoldItalicNote) {
            const noteText = (node.textContent || "").replace(/\s+/g, " ").trim();
            return noteText ? "***" + noteText + "***" : "";
        }
        let inner = "";
        Array.from(node.childNodes).forEach(function (child) {
            inner += serializeEmailRichNode(child);
        });
        if (tag === "DIV" || tag === "P") {
            if (inner === "\n") {
                return "\n";
            }
            return "\n" + inner;
        }
        return inner;
    }

    function serializeEmailRichBody(richEl) {
        if (!richEl) {
            return "";
        }
        let out = "";
        Array.from(richEl.childNodes).forEach(function (child, idx) {
            let chunk = serializeEmailRichNode(child);
            if (idx === 0 && (child.tagName === "DIV" || child.tagName === "P") && chunk.startsWith("\n")) {
                chunk = chunk.slice(1);
            }
            out += chunk;
        });
        return out.replace(/\u00a0/g, " ");
    }

    function syncEmailRichBodyFromTextarea(dialog) {
        if (!dialog) {
            return;
        }
        const body = dialog.querySelector("[data-email-body]");
        const rich = dialog.querySelector("[data-email-rich-body]");
        if (!body || !rich) {
            return;
        }
        rich.innerHTML = formatEmailBodyHtml(body.value || "");
    }

    function collectLiveMissingDocumentsText() {
        const plotForm = document.querySelector("[data-plot-application-form]");
        const docScope = plotForm || document.getElementById("plot-application-documents-dialog");
        if (!docScope) {
            return null;
        }
        const missing = [];
        docScope.querySelectorAll("[data-document-code]:not([hidden])").forEach(function (label) {
            const code = label.dataset.documentCode || "";
            const checkbox = label.querySelector('input[type="checkbox"]');
            const row = label.closest("[data-document-row]") || docScope;
            const noteInput = code
                ? row.querySelector('[data-document-note-input="' + code + '"]')
                : null;
            const note = noteInput ? (noteInput.value || "").trim() : "";
            const isMissing = checkbox
                ? (!checkbox.disabled && !checkbox.checked)
                : label.dataset.documentMissing === "1";
            if (isMissing || note) {
                const textEl =
                    label.querySelector("[data-ui-text-node]") ||
                    label.querySelector("[data-document-label]") ||
                    label.querySelector("span");
                const text = (textEl ? textEl.textContent : label.textContent || "").trim();
                if (text) {
                    missing.push(note ? "- " + text + " ***" + note + "***" : "- " + text);
                }
            }
        });
        if (!missing.length) {
            return "";
        }
        return ["Ελλείποντα δικαιολογητικά έγγραφα:", ...missing].join("\n");
    }

    (function () {

        document.addEventListener("input", function (event) {
            const noteInput = event.target.closest("[data-document-note-input]");
            if (noteInput) {
                const code = noteInput.dataset.documentNoteInput;
                const value = noteInput.value || "";
                const trimmed = value.trim();
                document.querySelectorAll('[data-document-note-input="' + code + '"]').forEach(function (other) {
                    if (other !== noteInput && other.value !== value) {
                        other.value = value;
                    }
                });
                document.querySelectorAll('[data-document-note-toggle="' + code + '"]').forEach(function (btn) {
                    btn.classList.toggle("has-note", Boolean(trimmed));
                    btn.title = trimmed ? "Σημείωση: " + trimmed : "Προσθήκη σημείωσης";
                });
                return;
            }
            const richBody = event.target.closest("[data-email-rich-body]");
            if (richBody) {
                const dialog = richBody.closest("dialog");
                const body = dialog ? dialog.querySelector("[data-email-body]") : null;
                if (body) {
                    body.value = serializeEmailRichBody(richBody);
                }
            }
        });

        document.addEventListener("change", function (event) {
            const overrideInput = event.target.closest(
                '[data-documents-completeness-form] input[name="documents_complete_override"]'
            );
            if (!overrideInput) {
                return;
            }
            const form = overrideInput.closest("[data-documents-completeness-form]");
            const wrap = form ? form.querySelector("[data-documents-override-reason-wrap]") : null;
            if (wrap) {
                wrap.hidden = !overrideInput.checked;
            }
        });

        document.addEventListener("click", function (event) {

            const noteToggle = event.target.closest("[data-document-note-toggle]");

            if (noteToggle) {

                event.preventDefault();

                const code = noteToggle.dataset.documentNoteToggle;

                const row = noteToggle.closest("[data-document-row]") || document;

                const wrap = row.querySelector('[data-document-note-wrap="' + code + '"]');

                if (!wrap) {

                    return;

                }

                const willShow = wrap.hidden;

                wrap.hidden = !willShow;

                noteToggle.setAttribute("aria-expanded", willShow ? "true" : "false");

                noteToggle.classList.toggle("is-open", willShow);

                if (willShow) {

                    const input = wrap.querySelector("[data-document-note-input]");

                    if (input) {

                        input.focus();

                    }

                }

                return;

            }

            const insertBtn = event.target.closest("[data-insert-missing-documents]");

            if (insertBtn) {

                const dialog = insertBtn.closest("dialog");

                if (!dialog) {

                    return;

                }

                const body = dialog.querySelector("[data-email-body]");

                const rich = dialog.querySelector("[data-email-rich-body]");

                if (!body) {

                    return;

                }

                if (rich) {

                    body.value = serializeEmailRichBody(rich);

                }

                const liveMissing = dialog.dataset.collectLiveMissing === "1"
                    ? collectLiveMissingDocumentsText()
                    : null;

                const missingText = liveMissing !== null
                    ? liveMissing
                    : (dialog.dataset.missingDocuments || "");

                if (missingText) {

                    const current = (body.value || "").trim();

                    if (!current) {

                        body.value = missingText;

                    } else if (!current.includes(missingText)) {

                        body.value = current + "\n\n" + missingText;

                    }

                }

                syncEmailRichBodyFromTextarea(dialog);

                if (rich) {

                    rich.focus();

                } else {

                    body.focus();

                }

                return;

            }

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

            dialog.dataset.collectLiveMissing = button.dataset.collectLiveMissing || "";

            const liveMissing = button.dataset.collectLiveMissing === "1"
                ? collectLiveMissingDocumentsText()
                : null;

            const source = liveMissing !== null ? liveMissing : (button.dataset.copyText || "");

            dialog.dataset.missingDocuments = source;

            const body = dialog.querySelector("[data-email-body]");

            if (body) {

                const hasInsertMissingBtn = Boolean(
                    dialog.querySelector("[data-insert-missing-documents]")
                );

                body.value = hasInsertMissingBtn ? "" : source;

            }

            syncEmailRichBodyFromTextarea(dialog);

            const recipientInput = form.querySelector("[data-email-recipient-input]");

            if (recipientInput) {

                const liveEmail = document.querySelector('#id_main-email');

                const emailValue = liveEmail && button.dataset.collectLiveMissing === "1"
                    ? liveEmail.value
                    : (button.dataset.emailRecipient || "");

                recipientInput.value = emailValue;

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

                const formData = new FormData(form);

                const docScope =
                    document.querySelector("[data-plot-application-form]") ||
                    document.getElementById("plot-application-documents-dialog");

                if (docScope && dialog && dialog.id === "plot-application-email-dialog") {

                    docScope.querySelectorAll("[data-document-note-input]").forEach(function (input) {

                        if (input.name) {

                            formData.set(input.name, input.value || "");

                        }

                    });

                }

                requestJson(form.action, { method: "POST", body: formData })

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

            const sender = dialog.querySelector("[data-communication-view-sender]");

            const stageWrap = dialog.querySelector("[data-communication-view-stage-wrap]");

            const stage = dialog.querySelector("[data-communication-view-stage]");

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

            if (sender) {

                sender.textContent = "…";

            }

            if (stageWrap) {

                stageWrap.hidden = true;

            }

            if (stage) {

                stage.textContent = "—";

            }

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

            const sender = dialog.querySelector("[data-communication-view-sender]");

            const stageWrap = dialog.querySelector("[data-communication-view-stage-wrap]");

            const stage = dialog.querySelector("[data-communication-view-stage]");

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

                    if (sender) {

                        sender.textContent = data.sender || "—";

                    }

                    if (stageWrap && stage) {

                        if (data.stage_label) {

                            stage.textContent = data.stage_label;

                            stageWrap.hidden = false;

                        } else {

                            stage.textContent = "—";

                            stageWrap.hidden = true;

                        }

                    }

                    status.textContent = data.status_display || "—";

                    sentAt.textContent = data.sent_at || "—";

                    subject.textContent = data.subject || "—";

                    if (data.body) {

                        body.innerHTML = formatEmailBodyHtml(data.body);

                    } else {

                        body.textContent = "—";

                    }

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

            const filterBtn = event.target.closest("[data-announcement-emails-filter]");

            if (filterBtn) {

                event.preventDefault();

                const dialog = filterBtn.closest("[data-announcement-emails-dialog]");

                if (!dialog) {

                    return;

                }

                const targetStage = filterBtn.getAttribute("data-announcement-emails-filter");

                dialog.querySelectorAll("[data-announcement-emails-filter]").forEach(function (btn) {

                    const isSelected = btn === filterBtn;

                    btn.classList.toggle("btn-primary", isSelected);

                    btn.classList.toggle("btn-secondary", !isSelected);

                });

                dialog.querySelectorAll("[data-announcement-emails-stage-group]").forEach(function (group) {

                    const code = group.getAttribute("data-announcement-emails-stage-group");

                    group.hidden = targetStage !== "all" && code !== targetStage;

                });

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
                if (typeof window.refreshUiTexts === "function") {
                    window.refreshUiTexts(body);
                }
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

    // History timeline modal: load on open for both PlotApplication and Case.
    if (!window.__historyTimelineBound) {
        window.__historyTimelineBound = true;
        document.addEventListener("click", function (event) {
            const open = event.target.closest("[data-history-timeline-open]");
            if (!open) {
                return;
            }
            event.preventDefault();
            const dialog = document.getElementById("history-timeline-dialog");
            const body = dialog ? dialog.querySelector("[data-history-timeline-body]") : null;
            const statusEl = dialog ? dialog.querySelector("[data-history-timeline-status]") : null;
            if (!dialog || !body) {
                return;
            }
            const titleEl = dialog.querySelector("[data-history-timeline-title-el]");
            if (titleEl && open.dataset.historyTimelineTitle) {
                titleEl.textContent = "Ιστορικό αλλαγών — " + open.dataset.historyTimelineTitle;
            }
            const leadEl = dialog.querySelector("[data-history-timeline-lead-el]");
            if (leadEl && open.dataset.historyTimelineLead) {
                leadEl.textContent = open.dataset.historyTimelineLead;
            }
            if (statusEl) {
                statusEl.innerHTML = "";
            }
            body.innerHTML = '<p class="text-muted">Φόρτωση…</p>';
            if (!dialog.open) {
                if (typeof dialog.showModal === "function") {
                    dialog.showModal();
                } else {
                    dialog.setAttribute("open", "");
                }
            }
            requestJson(open.dataset.historyTimelineOpen)
                .then(function (data) {
                    if (!data.ok) {
                        throw new Error("bad response");
                    }
                    body.innerHTML = data.timeline_html;
                    if (typeof window.refreshUiTexts === "function") {
                        window.refreshUiTexts(body);
                    }
                })
                .catch(function () {
                    body.innerHTML = "";
                    showStatusAlert(
                        "[data-history-timeline-status]",
                        "Αποτυχία φόρτωσης του ιστορικού αλλαγών.",
                        "error"
                    );
                });
        });
    }

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

    // Plot applications list grid: sticky locked columns offset calculation and column sorting.
    function syncLockedTableColumns(table) {
        if (!table) {
            return;
        }
        const lockedCount = parseInt(table.getAttribute("data-locked-columns") || "0", 10);
        if (!lockedCount || lockedCount <= 0) {
            return;
        }
        const headerCells = Array.from(table.querySelectorAll("thead th[data-locked-col]"));
        if (!headerCells.length) {
            return;
        }
        let offset = 0;
        headerCells.forEach(function (th) {
            const pos = th.getAttribute("data-locked-col");
            const leftPx = offset + "px";
            th.style.left = leftPx;
            table.querySelectorAll('tbody td[data-locked-col="' + pos + '"]').forEach(function (td) {
                td.style.left = leftPx;
            });
            offset += Math.round(th.getBoundingClientRect().width || th.offsetWidth || 0);
        });
    }

    document.querySelectorAll("table[data-locked-columns]").forEach(syncLockedTableColumns);
    window.addEventListener("resize", function () {
        document.querySelectorAll("table[data-locked-columns]").forEach(syncLockedTableColumns);
    });

    document.addEventListener("click", function (event) {
        const button = event.target.closest ? event.target.closest("[data-plot-application-sort]") : null;
        if (!button) {
            return;
        }
        event.preventDefault();
        const table = button.closest("[data-plot-application-table]");
        const tbody = table ? table.querySelector("tbody") : null;
        if (!tbody) {
            return;
        }
        const key = button.getAttribute("data-plot-application-sort");
        const nextDir = toggleSortDir(table, key);
        table.querySelectorAll("th").forEach(function (th) {
            th.removeAttribute("aria-sort");
        });
        const header = button.closest("th");
        if (header) {
            header.setAttribute("aria-sort", nextDir === "asc" ? "ascending" : "descending");
        }
        let comparator = GREEK_COLLATOR.compare;
        if (key === "children") {
            comparator = compareBy(numberValue);
        }
        reorderRows(tbody, "tr[data-plot-application-row]", key, nextDir, comparator);
        syncLockedTableColumns(table);
    });

    // The four fixed publication methods are dated inline in the same table: a change is saved
    // at once (an empty date removes the row) and the table is re-rendered from the server.
    document.addEventListener("change", function (event) {
        const input = event.target.closest ? event.target.closest("[data-publication-date]") : null;
        if (!input) {
            return;
        }
        const data = csrfFormData();
        data.append("published_on", input.value);
        input.disabled = true;
        requestJson(input.getAttribute("data-publication-date"), { method: "POST", body: data })
            .then(function (result) {
                if (result.grid_html) {
                    replaceOuterHtml("[data-publication-container]", result.grid_html);
                } else {
                    input.disabled = false;
                }
                showStatusAlert("[data-publication-status]", result.message, result.ok ? "success" : "error");
            })
            .catch(function () {
                showStatusAlert("[data-publication-status]", SERVER_ERROR_MESSAGE, "error");
                input.disabled = false;
            });
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

// Role setup per function (Ρυθμίσεις → Ρόλοι και δικαιώματα):
// function selector, expandable subsection panels under «Εμφάνιση» and «Επεξεργασία», and «Όλα» toggle.
(function () {
    const functionSelect = document.querySelector("[data-role-function-select]");
    if (functionSelect) {
        const syncPanels = function () {
            const selected = functionSelect.value;
            document.querySelectorAll("[data-role-function-panel]").forEach(function (panel) {
                panel.hidden = panel.getAttribute("data-role-function-panel") !== selected;
            });
        };
        functionSelect.addEventListener("change", syncPanels);
        syncPanels();
    }

    document.querySelectorAll("[data-role-function-panel]").forEach(function (panel) {
        const getSubBoxes = function (action) {
            const subPanel = panel.querySelector('[data-subsections-panel="' + action + '"]');
            if (!subPanel) {
                return [];
            }
            return Array.from(
                subPanel.querySelectorAll('[data-subsection-item="' + action + '"] input[type="checkbox"]')
            );
        };

        const syncAllToggle = function (action) {
            const subPanel = panel.querySelector('[data-subsections-panel="' + action + '"]');
            if (!subPanel) {
                return;
            }
            const allToggle = subPanel.querySelector('[data-subsection-all="' + action + '"]');
            if (!allToggle) {
                return;
            }
            const boxes = getSubBoxes(action);
            allToggle.checked = boxes.length > 0 && boxes.every(function (b) { return b.checked; });
            allToggle.indeterminate = !allToggle.checked && boxes.some(function (b) { return b.checked; });
        };

        const syncActionPanel = function (action, clearIfUnchecked) {
            const actionToggle = panel.querySelector(
                'input[type="checkbox"][data-action-with-subsections="' + action + '"]'
            );
            const subPanel = panel.querySelector('[data-subsections-panel="' + action + '"]');
            if (!actionToggle || !subPanel) {
                return;
            }
            if (actionToggle.checked) {
                subPanel.hidden = false;
            } else {
                subPanel.hidden = true;
                if (clearIfUnchecked) {
                    getSubBoxes(action).forEach(function (b) { b.checked = false; });
                }
            }
            syncAllToggle(action);
        };

        panel.addEventListener("change", function (event) {
            const target = event.target;
            if (target.hasAttribute("data-action-with-subsections")) {
                const action = target.getAttribute("data-action-with-subsections");
                syncActionPanel(action, true);
            } else if (target.hasAttribute("data-subsection-all")) {
                const action = target.getAttribute("data-subsection-all");
                const checked = target.checked;
                getSubBoxes(action).forEach(function (b) { b.checked = checked; });
                syncAllToggle(action);
            } else {
                const itemLabel = target.closest("[data-subsection-item]");
                if (itemLabel) {
                    syncAllToggle(itemLabel.getAttribute("data-subsection-item"));
                }
            }
        });

        ["view", "edit"].forEach(function (action) {
            syncActionPanel(action, false);
        });
    });
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

(function () {
    // Pages marked [data-keep-scroll] post their forms and redirect back to themselves: after the
    // reload, return to the card that was being worked on ([data-scroll-anchor]) instead of the
    // top of the page, and float the result message so it stays visible there.
    if (!document.querySelector("[data-keep-scroll]")) {
        return;
    }
    const STORAGE_KEY = "keepScroll:" + window.location.pathname;
    const MAX_AGE_MS = 60000;

    function anchorSelector(el) {
        return '[data-scroll-anchor="' + el.getAttribute("data-scroll-anchor") + '"]';
    }

    document.addEventListener("submit", function (event) {
        const form = event.target;
        if (event.defaultPrevented || !(form instanceof HTMLFormElement)) {
            return;
        }
        if ((form.getAttribute("method") || "").toLowerCase() !== "post" || form.target === "_blank" || form.closest("dialog")) {
            return;
        }
        const anchors = [];
        for (let el = form.closest("[data-scroll-anchor]"); el; el = el.parentElement && el.parentElement.closest("[data-scroll-anchor]")) {
            anchors.push({ selector: anchorSelector(el), top: el.getBoundingClientRect().top });
        }
        try {
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ at: Date.now(), scrollY: window.scrollY, anchors: anchors }));
        } catch (_err) {
            // sessionStorage unavailable
        }
    });

    let saved = null;
    try {
        saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null");
        sessionStorage.removeItem(STORAGE_KEY);
    } catch (_err) {
        saved = null;
    }
    if (!saved || typeof saved.scrollY !== "number" || Date.now() - saved.at > MAX_AGE_MS) {
        return;
    }

    const stack = document.querySelector("main .messages-stack");
    if (stack) {
        stack.classList.add("messages-stack--floating");
        stack.addEventListener("click", function () {
            stack.remove();
        });
        if (!stack.querySelector(".alert--error")) {
            window.setTimeout(function () {
                stack.remove();
            }, 6000);
        }
    }

    const applyScroll = function () {
        let targetY = saved.scrollY;
        const match = (saved.anchors || []).map(function (anchor) {
            return { anchor: anchor, el: document.querySelector(anchor.selector) };
        }).find(function (item) {
            return item.el;
        });
        if (match) {
            targetY = Math.max(0, Math.round(match.el.getBoundingClientRect().top + window.scrollY - match.anchor.top));
        }
        window.scrollTo(0, targetY);
    };
    applyScroll();
    window.requestAnimationFrame(applyScroll);
})();

// In-place UI Text Edit Mode (§Α.9.1): applies custom text overrides across all screens
// and, while Edit Mode is active, attaches an inline edit icon next to every editable text
// that opens the popup modal to edit or reset the text.
(function () {
    function parseJsonScript(id) {
        const node = document.getElementById(id);
        if (!node) {
            return {};
        }
        try {
            return JSON.parse(node.textContent || "{}") || {};
        } catch (_err) {
            return {};
        }
    }

    const overridesMap = parseJsonScript("ui-text-overrides");
    const defaultsMap = parseJsonScript("ui-text-defaults");

    const sectionKeys = Object.keys(defaultsMap)
        .filter(function (k) { return k.startsWith("caseSectionLabel."); })
        .map(function (k) { return k.slice("caseSectionLabel.".length); })
        .sort(function (a, b) { return b.length - a.length; });

    const subsectionKeys = Object.keys(defaultsMap)
        .filter(function (k) { return k.startsWith("caseSubsectionLabel."); })
        .map(function (k) { return k.slice("caseSubsectionLabel.".length); })
        .sort(function (a, b) { return b.length - a.length; });

    const TARGET_RULES = [
        { selector: "[data-ui-key]", category: "explicit" },
        { selector: "[data-ui-text]", category: "h1" },
        { selector: ".site-brand__title", category: "brand" },
        { selector: ".page-header h1, .login-card h1", category: "h1" },
        { selector: ".page-header__lead, .card__lead, .login-card__sub", category: "lead" },
        {
            selector:
                ".wizard-steps__link, .wizard-steps__item, .list-tabs__item, .dashboard-stage-pill__label, .case-actions-nav__label, .settings-toc__list a",
            category: "tab",
        },
        {
            selector:
                "h2.card__title, h3.card__title, h2.form-section-title, h3.form-section-title, h3.form-section-subtitle, h4.form-section-subtitle, .card > h4, .completeness-panel__title, .completeness-panel__section-title, .case-actions-sidebar__title, .settings-case-labels__group-title, .settings-toc__label, .dashboard-kpi-card__title, fieldset > legend, details > summary, .tile__title",
            category: "heading",
        },
        {
            selector:
                ".tile__desc, p.helptext, div.helptext, span.helptext, .case-actions-sidebar__hint, .completeness-panel__summary, .completeness-panel__empty, p.text-muted, li.text-muted, td.text-muted, table.data-table tbody td[colspan], .alert:not([hidden])",
            category: "desc",
        },
        {
            selector:
                "button.btn, a.btn, .btn-link:not(.btn-link--table), .btn-logout, .approved-design-plots-fab",
            category: "btn",
        },
        {
            selector:
                ".form-field > label:not(.checkbox-label), label.checkbox-label > span, .login-form label, .filter-form label, dl.detail-grid dt, td > label, .announcement-summary-header strong, .dashboard-kpi-card__metrics > span, p[data-objection-period] > strong, .attachment-list__remove",
            category: "label",
        },
        { selector: "table.data-table thead th, button.btn-link--table", category: "th" },
        { selector: ".badge, .history-timeline__badge", category: "badge" },
        { selector: ".breadcrumb a, .breadcrumb > span, .case-actions-sidebar__footer a, .settings-nav a", category: "nav" },
    ];

    const PENCIL_SVG =
        '<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" focusable="false">' +
        '<path fill="currentColor" d="M11.8 1.5a1.5 1.5 0 0 1 2.12 0l.58.58a1.5 1.5 0 0 1 0 2.12L5.2 13.5l-3.45.75.75-3.45 9.3-9.3zm1.06 1.06L4.3 11.12l-.33 1.51 1.51-.33 8.56-8.56-.18-.18z"/>' +
        "</svg>";

    function normalizeText(value) {
        return (value || "").replace(/\s+/g, " ").trim();
    }

    function computeUiTextKey(category, defaultText) {
        const input = category + ":" + defaultText;
        let h1 = 0x811c9dc5;
        let h2 = 0x01000193;
        for (let i = 0; i < input.length; i += 1) {
            const ch = input.charCodeAt(i);
            h1 ^= ch;
            h1 = Math.imul(h1, 0x01000193) >>> 0;
            h2 ^= ch + (i & 0xff);
            h2 = Math.imul(h2, 0x85ebca6b) >>> 0;
        }
        return (
            "uiText." +
            category +
            "_" +
            h1.toString(16).padStart(8, "0") +
            h2.toString(16).padStart(8, "0")
        );
    }

    function shouldSkipElement(el, category) {
        if (!el || el.nodeType !== 1) {
            return true;
        }
        if (
            el.hasAttribute("data-ui-skip") ||
            el.closest("[data-ui-skip]") ||
            el.closest("[data-ui-text-dialog]") ||
            el.closest("[data-ui-text-node]") ||
            el.hasAttribute("data-ui-edit-mode-toggle") ||
            el.hasAttribute("data-file-remove") ||
            el.hasAttribute("data-reorder-status") ||
            el.hasAttribute("data-ui-text-default-hint") ||
            el.hasAttribute("data-email-check-label") ||
            el.hasAttribute("data-save-tooltip") ||
            el.hasAttribute("data-person-status")
        ) {
            return true;
        }
        if (!el.hasAttribute("data-ui-text") && !el.hasAttribute("data-ui-key")) {
            if (el.querySelector("[data-ui-text], [data-ui-key]")) {
                return true;
            }
        }
        if (el.classList.contains("wizard-steps__item") && el.querySelector(".wizard-steps__link")) {
            return true;
        }
        if (category === "lead" || category === "desc") {
            if (el.closest(".messages-stack")) {
                return true;
            }
            if (!el.hasAttribute("data-ui-text") && !el.hasAttribute("data-ui-key")) {
                if (el.querySelector("a, .badge, input, select, button, textarea, table, ul, ol")) {
                    return true;
                }
            }
        }
        if (category === "badge") {
            if (!el.hasAttribute("data-ui-text") && !el.hasAttribute("data-ui-key")) {
                if (el.querySelector("a, input, select, button")) {
                    return true;
                }
            }
        }
        if (category === "th" && el.tagName === "TH") {
            if (el.querySelector("button, input, .visually-hidden")) {
                return true;
            }
        }
        return false;
    }

    function isInlineFormattingChild(child) {
        if (!child || child.nodeType !== 1) {
            return false;
        }
        if (
            child.hasAttribute("data-ui-skip") ||
            child.hasAttribute("data-ui-text") ||
            child.hasAttribute("data-ui-key") ||
            child.hasAttribute("data-ui-edit-trigger") ||
            child.classList.contains("badge") ||
            child.classList.contains("visually-hidden") ||
            child.getAttribute("aria-hidden") === "true"
        ) {
            return false;
        }
        if (
            child.querySelector(
                "[data-ui-skip], [data-ui-text], [data-ui-key], a, button, input, select, textarea, .badge"
            )
        ) {
            return false;
        }
        const tag = (child.tagName || "").toUpperCase();
        if (tag === "CODE" || tag === "EM" || tag === "I" || tag === "B") {
            return true;
        }
        if (tag === "STRONG" || tag === "SPAN") {
            const txt = normalizeText(child.textContent);
            if (!txt || /^[\d.,€%\s—-]+$/.test(txt)) {
                return false;
            }
            return true;
        }
        return false;
    }

    function ensureTextSpan(el) {
        const existing = el.querySelector(":scope > [data-ui-text-node]");
        if (existing) {
            return existing;
        }
        const elementChildren = Array.from(el.children).filter(function (c) {
            return !c.hasAttribute("data-ui-edit-trigger");
        });
        if (
            elementChildren.length > 0 &&
            elementChildren.every(isInlineFormattingChild)
        ) {
            const fullRaw = normalizeText(el.textContent);
            if (!fullRaw) {
                return null;
            }
            const span = document.createElement("span");
            span.className = "ui-editable-text";
            span.setAttribute("data-ui-text-node", "");
            while (el.firstChild) {
                span.appendChild(el.firstChild);
            }
            span.setAttribute("data-ui-default-html", span.innerHTML);
            el.appendChild(span);
            return span;
        }
        const textNodes = [];
        Array.from(el.childNodes).forEach(function (node) {
            if (node.nodeType === 3 && normalizeText(node.nodeValue)) {
                textNodes.push(node);
            }
        });
        if (!textNodes.length) {
            return null;
        }
        const firstNode = textNodes[0];
        const raw = normalizeText(
            textNodes.map(function (n) { return n.nodeValue; }).join(" ")
        );
        if (!raw) {
            return null;
        }
        const hasFollowingElement = Boolean(
            firstNode.nextSibling &&
            Array.from(el.childNodes).slice(Array.from(el.childNodes).indexOf(firstNode) + 1).some(function (n) {
                return n.nodeType === 1 && !n.hasAttribute("data-ui-edit-trigger");
            })
        );
        const span = document.createElement("span");
        span.className = "ui-editable-text";
        span.setAttribute("data-ui-text-node", "");
        span.textContent = raw;
        if (hasFollowingElement && /\s$/.test(firstNode.nodeValue || "")) {
            span.setAttribute("data-ui-trailing-space", "1");
        }
        el.insertBefore(span, firstNode);
        textNodes.forEach(function (n) {
            n.remove();
        });
        return span;
    }

    function matchesKnownLabel(key, valueText) {
        if (!valueText) {
            return false;
        }
        if (Object.prototype.hasOwnProperty.call(defaultsMap, key) && defaultsMap[key] === valueText) {
            return true;
        }
        if (Object.prototype.hasOwnProperty.call(overridesMap, key) && overridesMap[key] === valueText) {
            return true;
        }
        return false;
    }

    function detectSectionOrSubsection(rawText) {
        for (let i = 0; i < sectionKeys.length; i += 1) {
            const sec = sectionKeys[i];
            const prefix = sec + ". ";
            if (rawText.startsWith(prefix)) {
                const valueText = rawText.slice(prefix.length).trim();
                const candidateKey = "caseSectionLabel." + sec;
                if (matchesKnownLabel(candidateKey, valueText)) {
                    return {
                        key: candidateKey,
                        prefix: prefix,
                        suffix: "",
                        valueText: valueText,
                    };
                }
            }
        }
        for (let i = 0; i < subsectionKeys.length; i += 1) {
            const sub = subsectionKeys[i];
            const prefix = sub + " ";
            if (rawText.startsWith(prefix)) {
                let valueText = rawText.slice(prefix.length).trim();
                let suffix = "";
                if (valueText.endsWith(" (3.2)")) {
                    suffix = " (3.2)";
                    valueText = valueText.slice(0, -suffix.length).trim();
                }
                const candidateKey = "caseSubsectionLabel." + sub;
                if (matchesKnownLabel(candidateKey, valueText)) {
                    return {
                        key: candidateKey,
                        prefix: prefix,
                        suffix: suffix,
                        valueText: valueText,
                    };
                }
            }
        }
        return null;
    }

    function renderElementText(el) {
        const span = el.querySelector(":scope > [data-ui-text-node]");
        if (!span) {
            return;
        }
        const key = el.getAttribute("data-ui-resolved-key") || "";
        const prefix = el.getAttribute("data-ui-prefix") || "";
        const suffix = el.getAttribute("data-ui-suffix") || "";
        const defaultText = el.getAttribute("data-ui-default") || "";
        const initialValue = el.getAttribute("data-ui-initial") || defaultText;
        const hasOverride = Object.prototype.hasOwnProperty.call(overridesMap, key) && overridesMap[key] !== "";
        const activeValue = hasOverride ? overridesMap[key] : initialValue;
        el.setAttribute("data-ui-current", activeValue);
        const trailing = span.getAttribute("data-ui-trailing-space") === "1" ? " " : "";
        const defaultHtml = span.getAttribute("data-ui-default-html");
        if (!hasOverride && defaultHtml !== null && activeValue === initialValue && !prefix && !suffix) {
            span.innerHTML = defaultHtml;
        } else {
            span.textContent = prefix + activeValue + suffix + trailing;
        }
    }

    function syncEditIconOnElement(el, editModeActive) {
        const existingIcon = el.querySelector(":scope > [data-ui-edit-trigger]");
        if (!editModeActive) {
            if (existingIcon) {
                existingIcon.remove();
            }
            return;
        }
        if (existingIcon) {
            return;
        }
        const icon = document.createElement("span");
        icon.className = "ui-edit-icon";
        icon.setAttribute("role", "button");
        icon.setAttribute("tabindex", "0");
        icon.setAttribute("data-ui-edit-trigger", "");
        icon.setAttribute("title", "Επεξεργασία κειμένου");
        icon.setAttribute("aria-label", "Επεξεργασία κειμένου");
        icon.innerHTML = PENCIL_SVG;
        const span = el.querySelector(":scope > [data-ui-text-node]");
        if (span && span.nextSibling) {
            el.insertBefore(icon, span.nextSibling);
        } else {
            el.appendChild(icon);
        }
    }

    function bindElement(el, category, editModeActive) {
        if (el.hasAttribute("data-ui-bound")) {
            renderElementText(el);
            syncEditIconOnElement(el, editModeActive);
            return;
        }
        if (shouldSkipElement(el, category)) {
            return;
        }
        const span = ensureTextSpan(el);
        if (!span) {
            return;
        }
        const rawText = normalizeText(span.textContent);
        if (!rawText || rawText === "—" || !/[Α-Ωα-ωΆ-Ώά-ώA-Za-z]{2,}/.test(rawText)) {
            return;
        }
        if (category === "nav" && (/^[A-Z0-9._/-]+$/.test(rawText) || /\d{2,}/.test(rawText))) {
            return;
        }

        let key = el.getAttribute("data-ui-key") || "";
        if (!key && category === "brand") {
            key = "appTitle";
        }
        if (!key && category === "h1") {
            const header = el.closest("[data-header-ui-key]");
            if (header) {
                key = header.getAttribute("data-header-ui-key") || "";
            }
        }

        let prefix = el.getAttribute("data-ui-prefix") || "";
        let suffix = el.getAttribute("data-ui-suffix") || "";
        let valueText = rawText;

        if (prefix && valueText.startsWith(prefix.trim())) {
            valueText = valueText.slice(prefix.trim().length).trim();
        }
        if (suffix && valueText.endsWith(suffix.trim())) {
            valueText = valueText.slice(0, valueText.length - suffix.trim().length).trim();
        }
        if (!key && !prefix && !suffix && category === "heading") {
            const detected = detectSectionOrSubsection(rawText);
            if (detected) {
                key = detected.key;
                prefix = detected.prefix;
                suffix = detected.suffix;
                valueText = detected.valueText;
            }
        }

        const defaultText =
            key && Object.prototype.hasOwnProperty.call(defaultsMap, key)
                ? defaultsMap[key]
                : valueText;

        if (!key) {
            key = computeUiTextKey(category, defaultText);
        }

        el.setAttribute("data-ui-bound", "1");
        el.setAttribute("data-ui-resolved-key", key);
        el.setAttribute("data-ui-default", defaultText);
        el.setAttribute("data-ui-initial", valueText);
        el.setAttribute("data-ui-prefix", prefix);
        el.setAttribute("data-ui-suffix", suffix);
        el.setAttribute("data-ui-category", category);

        renderElementText(el);
        syncEditIconOnElement(el, editModeActive);
    }

    function refreshUiTexts(root) {
        const scope = root || document;
        const editModeActive = document.body.classList.contains("ui-edit-mode");
        TARGET_RULES.forEach(function (rule) {
            if (scope.nodeType === 1 && scope.matches && scope.matches(rule.selector)) {
                bindElement(scope, rule.category, editModeActive);
            }
            scope.querySelectorAll(rule.selector).forEach(function (el) {
                bindElement(el, rule.category, editModeActive);
            });
        });
    }

    window.refreshUiTexts = refreshUiTexts;
    refreshUiTexts(document);

    // Header Edit Mode toggle button.
    const toggleBtn = document.querySelector("[data-ui-edit-mode-toggle]");
    if (toggleBtn) {
        toggleBtn.addEventListener("click", function () {
            const nextState = !document.body.classList.contains("ui-edit-mode");
            document.body.classList.toggle("ui-edit-mode", nextState);
            toggleBtn.classList.toggle("is-active", nextState);
            toggleBtn.setAttribute("aria-pressed", nextState ? "true" : "false");
            refreshUiTexts(document);

            const tokenInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
            const data = new FormData();
            data.append("csrfmiddlewaretoken", tokenInput ? tokenInput.value : "");
            data.append("enabled", nextState ? "1" : "0");
            fetch(toggleBtn.getAttribute("data-ui-edit-mode-toggle"), {
                method: "POST",
                headers: { Accept: "application/json" },
                credentials: "same-origin",
                body: data,
            }).catch(function () {
                // Keep visual state even if background session sync fails.
            });
        });
    }

    const dialog = document.getElementById("ui-text-edit-dialog");
    if (!dialog) {
        return;
    }

    const form = dialog.querySelector("[data-ui-text-form]");
    const keyInput = dialog.querySelector("[data-ui-text-key]");
    const descInput = dialog.querySelector("[data-ui-text-description]");
    const textInput = dialog.querySelector("[data-ui-text-input]");
    const defaultHint = dialog.querySelector("[data-ui-text-default-hint]");
    const errorsBox = dialog.querySelector("[data-ui-text-errors]");
    const saveBtn = dialog.querySelector("[data-ui-text-save]");
    const resetBtn = dialog.querySelector("[data-ui-text-reset]");

    function showError(msg) {
        if (!errorsBox) {
            return;
        }
        errorsBox.textContent = msg || "";
        errorsBox.hidden = !msg;
    }

    function openEditDialogForElement(el) {
        const key = el.getAttribute("data-ui-resolved-key") || "";
        const currentText = el.getAttribute("data-ui-current") || "";
        const defaultText = el.getAttribute("data-ui-default") || "";
        const category = el.getAttribute("data-ui-category") || "text";
        if (!key) {
            return;
        }
        showError("");
        keyInput.value = key;
        descInput.value = "Κείμενο (" + category + "): «" + defaultText.slice(0, 120) + "»";
        textInput.value = currentText;
        textInput.rows = currentText.length > 70 || defaultText.length > 70 ? 3 : 2;
        if (defaultHint) {
            defaultHint.textContent = defaultText ? "Προεπιλογή: «" + defaultText + "»" : "";
        }
        if (typeof dialog.showModal === "function") {
            dialog.showModal();
        } else {
            dialog.setAttribute("open", "");
        }
        textInput.focus();
        textInput.select();
    }

    // Intercept clicks and keyboard activation on `.ui-edit-icon` in the capture phase
    // so buttons do not submit, links do not navigate, and labels do not toggle inputs.
    document.addEventListener(
        "click",
        function (event) {
            const trigger = event.target.closest ? event.target.closest("[data-ui-edit-trigger]") : null;
            if (!trigger) {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
            const host = trigger.closest("[data-ui-bound]");
            if (host) {
                openEditDialogForElement(host);
            }
        },
        true
    );

    document.addEventListener(
        "keydown",
        function (event) {
            if (event.key !== "Enter" && event.key !== " ") {
                return;
            }
            const trigger = event.target.closest ? event.target.closest("[data-ui-edit-trigger]") : null;
            if (!trigger) {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            const host = trigger.closest("[data-ui-bound]");
            if (host) {
                openEditDialogForElement(host);
            }
        },
        true
    );

    function applySavedKey(key, value, isReset) {
        if (isReset && key.startsWith("uiText.")) {
            delete overridesMap[key];
        } else {
            overridesMap[key] = value;
        }
        document.querySelectorAll("[data-ui-bound]").forEach(function (el) {
            if (el.getAttribute("data-ui-resolved-key") === key) {
                if (!key.startsWith("uiText.")) {
                    el.setAttribute("data-ui-initial", value);
                } else if (isReset) {
                    el.setAttribute("data-ui-initial", el.getAttribute("data-ui-default") || "");
                }
                renderElementText(el);
            }
        });
    }

    function submitTextChange(isReset) {
        showError("");
        const data = new FormData(form);
        if (isReset) {
            data.append("reset", "1");
        }
        saveBtn.disabled = true;
        resetBtn.disabled = true;
        fetch(form.action, {
            method: "POST",
            headers: { Accept: "application/json" },
            credentials: "same-origin",
            body: data,
        })
            .then(function (response) {
                return response.json();
            })
            .then(function (result) {
                if (!result || !result.ok) {
                    showError((result && result.message) || "Αποτυχία αποθήκευσης κειμένου.");
                    return;
                }
                applySavedKey(result.key, result.value, Boolean(result.reset));
                if (typeof dialog.close === "function") {
                    dialog.close();
                } else {
                    dialog.removeAttribute("open");
                }
            })
            .catch(function () {
                showError("Αποτυχία επικοινωνίας με τον διακομιστή.");
            })
            .finally(function () {
                saveBtn.disabled = false;
                resetBtn.disabled = false;
            });
    }

    form.addEventListener("submit", function (event) {
        event.preventDefault();
        submitTextChange(false);
    });

    resetBtn.addEventListener("click", function () {
        submitTextChange(true);
    });
})();

(function () {
    // ?open=<name> opens the "plot-application-<name>-dialog" action dialog on load.
    const name = new URLSearchParams(window.location.search).get("open");
    if (!name || !/^[a-z-]+$/.test(name)) {
        return;
    }
    document.addEventListener("DOMContentLoaded", function () {
        const opener = document.querySelector('[data-dialog-open="plot-application-' + name + '-dialog"]');
        if (opener && !opener.disabled) {
            opener.click();
        }
    });
})();
