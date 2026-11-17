/**
 * inbox.js: small conveniences for Booking requests. The page works without it.
 *
 *   - The Car and Sort selects apply as soon as they change, so the Apply
 *     button is hidden.
 *   - "Keep trip" (shown only when this script runs) closes the cancel box.
 */
(function () {
    'use strict';

    document.querySelectorAll('form[data-auto-submit]').forEach(function (form) {
        var button = form.querySelector('[data-auto-submit-button]');
        if (button) {
            button.hidden = true;
        }
        form.querySelectorAll('select').forEach(function (select) {
            select.addEventListener('change', function () {
                form.submit();
            });
        });
    });

    document.querySelectorAll('[data-cancel-details]').forEach(function (details) {
        var keep = details.querySelector('[data-keep-trip]');
        if (!keep) {
            return;
        }
        keep.hidden = false;
        keep.addEventListener('click', function () {
            details.open = false;
            details.querySelector('summary').focus();
        });
    });
})();
