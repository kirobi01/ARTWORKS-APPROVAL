/**
 * Click-to-select reusable logo templates on the artwork form.
 */
(function () {
    function syncTile(tile) {
        const hidden = tile.querySelector('input[name^="logo_status_"]');
        const colorsWrap = tile.querySelector('.logo-colors-wrap');
        if (!hidden) return;

        const status = hidden.value;
        tile.classList.toggle('selected', status === 'Okay');
        tile.classList.toggle('na', status === 'N/A');
        if (colorsWrap) {
            colorsWrap.hidden = status !== 'Okay';
        }
    }

    function initLogoPicker(root) {
        root.querySelectorAll('.logo-tile').forEach(function (tile) {
            const hidden = tile.querySelector('input[name^="logo_status_"]');
            const selectBtn = tile.querySelector('.logo-tile-select');
            const naBtn = tile.querySelector('.logo-na-btn');

            if (!hidden || !selectBtn) return;

            selectBtn.addEventListener('click', function () {
                if (hidden.value === 'Okay') {
                    hidden.value = '';
                } else {
                    hidden.value = 'Okay';
                }
                syncTile(tile);
            });

            if (naBtn) {
                naBtn.addEventListener('click', function (e) {
                    e.preventDefault();
                    e.stopPropagation();
                    hidden.value = hidden.value === 'N/A' ? '' : 'N/A';
                    syncTile(tile);
                });
            }

            syncTile(tile);
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        const picker = document.getElementById('logoPicker');
        if (picker) initLogoPicker(picker);
    });
})();
