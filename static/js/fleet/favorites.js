/**
 * favorites.js — Asynchronous toggle for favorite heart buttons.
 *
 * Intercepts form submissions on form[data-favorite-form], sends an AJAX request,
 * and updates the button styling, aria attributes, and labels.
 */
(function () {
    'use strict';

    document.addEventListener('submit', function (e) {
        var form = e.target;
        if (!form || !form.matches('form[data-favorite-form]')) {
            return;
        }

        e.preventDefault();

        fetch(form.action, {
            method: 'POST',
            body: new FormData(form),
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin'
        })
        .then(function (response) {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(function (data) {
            var btn = form.querySelector('.favorite-button');
            var label = form.querySelector('[data-favorite-label]');
            var isFavorited = Boolean(data.favorited);

            if (btn) {
                if (isFavorited) {
                    btn.classList.add('is-saved');
                    btn.setAttribute('aria-pressed', 'true');
                } else {
                    btn.classList.remove('is-saved');
                    btn.setAttribute('aria-pressed', 'false');
                }
            }

            if (label) {
                label.textContent = isFavorited ? 'Saved' : 'Save';
            }
        })
        .catch(function () {
            HTMLFormElement.prototype.submit.call(form);
        });
    });
})();
