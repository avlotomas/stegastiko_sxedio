// Γνωστοποιήσεις, βήμα 1: όλα τα οικόπεδα μιας γνωστοποίησης ανήκουν στην ίδια Κοινότητα.
// Μόλις επιλεγεί ένα οικόπεδο, τα οικόπεδα άλλων Κοινοτήτων απενεργοποιούνται.
(function () {
    const form = document.querySelector("[data-plot-picker]");
    if (!form) {
        return;
    }
    const boxes = Array.from(form.querySelectorAll('input[name="plots"]'));

    function sync() {
        const chosen = boxes.find(function (box) { return box.checked; });
        const community = chosen ? chosen.dataset.community : null;
        boxes.forEach(function (box) {
            box.disabled = community !== null && box.dataset.community !== community;
        });
    }

    boxes.forEach(function (box) { box.addEventListener("change", sync); });
    sync();
})();
