// Γνωστοποιήσεις, βήμα 1: η ανακοίνωση εκδίδεται από τον Έπαρχο, άρα οι Κοινότητες
// είναι μίας Επαρχίας. Μόλις επιλεγεί μία Κοινότητα, οι άλλες Επαρχίες απενεργοποιούνται.
(function () {
    const form = document.querySelector("[data-community-picker]");
    if (!form) {
        return;
    }
    const boxes = Array.from(form.querySelectorAll('input[name="communities"]'));

    function sync() {
        const chosen = boxes.find(function (box) { return box.checked; });
        const district = chosen ? chosen.dataset.district : null;
        boxes.forEach(function (box) {
            box.disabled = district !== null && box.dataset.district !== district;
        });
    }

    boxes.forEach(function (box) { box.addEventListener("change", sync); });
    sync();
})();
