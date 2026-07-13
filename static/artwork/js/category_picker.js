/**
 * Dropdown fields with inline "+" to add a new lookup value (category, supplier, etc.).
 */
(function () {
    function showAddMode(selectWrap, newWrap, select, newInput) {
        selectWrap.hidden = true;
        newWrap.hidden = false;
        select.disabled = true;
        newInput.disabled = false;
        newInput.focus();
    }

    function showSelectMode(selectWrap, newWrap, select, newInput) {
        selectWrap.hidden = false;
        newWrap.hidden = true;
        select.disabled = false;
        newInput.disabled = true;
        newInput.value = '';
    }

    function initLookupPicker(root) {
        const selectWrap = root.querySelector('.lookup-select-wrap');
        const newWrap = root.querySelector('.lookup-new-wrap');
        const addBtn = root.querySelector('.lookup-add-btn');
        const cancelBtn = root.querySelector('.lookup-back-btn');
        const select = selectWrap && selectWrap.querySelector('select');
        const newInput = newWrap && newWrap.querySelector('input');

        if (!selectWrap || !newWrap || !addBtn || !cancelBtn || !select || !newInput) return;

        addBtn.addEventListener('click', function () {
            showAddMode(selectWrap, newWrap, select, newInput);
        });

        cancelBtn.addEventListener('click', function () {
            showSelectMode(selectWrap, newWrap, select, newInput);
        });

        if ((newInput.value || '').trim()) {
            showAddMode(selectWrap, newWrap, select, newInput);
        } else {
            showSelectMode(selectWrap, newWrap, select, newInput);
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.lookup-field').forEach(initLookupPicker);
    });
})();
