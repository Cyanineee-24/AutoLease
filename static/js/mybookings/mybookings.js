/**
 * mybookings.js — confirm before cancelling a pending request.
 */
(function () {
    'use strict';

    document.querySelectorAll('form[data-confirm]').forEach(function (form) {
        form.addEventListener('submit', function (event) {
            if (!window.confirm(form.getAttribute('data-confirm'))) {
                event.preventDefault();
            }
        });
    });
})();
