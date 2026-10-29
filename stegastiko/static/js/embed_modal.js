(function () {
    "use strict";

    var EMBED_PARAM = "embed";

    function isPlainLeftClick(event) {
        return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
    }

    function sameOriginUrl(anchor) {
        var href = anchor.getAttribute("href");
        if (!href || href.charAt(0) === "#" || /^(mailto:|tel:|javascript:)/i.test(href)) {
            return null;
        }
        var url;
        try {
            url = new URL(anchor.href, window.location.href);
        } catch (err) {
            return null;
        }
        if (url.origin !== window.location.origin) {
            return null;
        }
        if (url.pathname === window.location.pathname && url.search === window.location.search && url.hash) {
            return null;
        }
        return url;
    }

    function withEmbed(url) {
        url.searchParams.set(EMBED_PARAM, "1");
        return url;
    }

    /* ——— Embedded page (inside the iframe) ——— */
    function initEmbeddedPage() {
        var parentWorkspace = null;
        try {
            if (window.parent && window.parent !== window && window.parent.__embedWorkspace) {
                parentWorkspace = window.parent.__embedWorkspace;
            }
        } catch (err) {
            parentWorkspace = null;
        }

        document.addEventListener("click", function (event) {
            if (event.defaultPrevented || !isPlainLeftClick(event)) {
                return;
            }
            var anchor = event.target.closest("a[href]");
            if (!anchor || anchor.hasAttribute("download") || anchor.target === "_blank" || anchor.target === "_top") {
                return;
            }
            var url = sameOriginUrl(anchor);
            if (!url) {
                return;
            }
            if (parentWorkspace && parentWorkspace.owns(url)) {
                event.preventDefault();
                parentWorkspace.close();
                return;
            }
            anchor.href = withEmbed(url).toString();
        }, true);

        document.addEventListener("submit", function (event) {
            var form = event.target;
            if (!(form instanceof HTMLFormElement) || form.target === "_blank") {
                return;
            }
            if (!form.querySelector('input[name="' + EMBED_PARAM + '"]')) {
                var input = document.createElement("input");
                input.type = "hidden";
                input.name = EMBED_PARAM;
                input.value = "1";
                form.appendChild(input);
            }
        }, true);

        document.addEventListener("keydown", function (event) {
            if (event.key !== "Escape" || !parentWorkspace) {
                return;
            }
            if (document.querySelector("dialog[open]")) {
                return;
            }
            parentWorkspace.close();
        });
    }

    /* ——— Workspace page (opens links in the iframe modal) ——— */
    function initWorkspace(marker) {
        var dialog = document.querySelector("[data-embed-dialog]");
        if (!dialog) {
            return;
        }
        var frame = dialog.querySelector("[data-embed-frame]");
        var titleEl = dialog.querySelector("[data-embed-title]");
        var stayPrefix = marker.getAttribute("data-embed-stay-prefix") || window.location.pathname;
        var opened = false;

        function owns(url) {
            return url.origin === window.location.origin && url.pathname.indexOf(stayPrefix) === 0;
        }

        function open(url, title) {
            titleEl.textContent = title || "";
            frame.src = withEmbed(url).toString();
            opened = true;
            if (!dialog.open) {
                dialog.showModal();
            }
        }

        function close() {
            if (dialog.open) {
                dialog.close();
            }
        }

        window.__embedWorkspace = { owns: owns, close: close };

        dialog.querySelector("[data-embed-close]").addEventListener("click", close);

        dialog.addEventListener("close", function () {
            frame.removeAttribute("src");
            if (opened) {
                opened = false;
                window.location.reload();
            }
        });

        frame.addEventListener("load", function () {
            try {
                var doc = frame.contentDocument;
                if (!doc || !frame.getAttribute("src")) {
                    return;
                }
                var loc = frame.contentWindow.location;
                if (owns(new URL(loc.href))) {
                    close();
                    return;
                }
                var heading = doc.querySelector("main h1");
                if (heading && heading.textContent.trim()) {
                    titleEl.textContent = heading.textContent.trim();
                } else if (doc.title) {
                    titleEl.textContent = doc.title;
                }
            } catch (err) {
                /* cross-origin navigation: leave title as is */
            }
        });

        var scope = document.querySelector("main.page") || document.body;
        scope.addEventListener("click", function (event) {
            if (event.defaultPrevented || !isPlainLeftClick(event)) {
                return;
            }
            var anchor = event.target.closest("a[href]");
            if (!anchor || !scope.contains(anchor) || dialog.contains(anchor)) {
                return;
            }
            if (anchor.hasAttribute("download") || anchor.hasAttribute("data-embed-skip") || anchor.target === "_blank") {
                return;
            }
            var url = sameOriginUrl(anchor);
            if (!url || owns(url)) {
                return;
            }
            event.preventDefault();
            open(url, anchor.getAttribute("data-embed-title") || anchor.textContent.trim());
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (document.body.hasAttribute("data-embed-mode")) {
            initEmbeddedPage();
            return;
        }
        var marker = document.querySelector("[data-embed-workspace]");
        if (marker) {
            initWorkspace(marker);
        }
    });
})();
