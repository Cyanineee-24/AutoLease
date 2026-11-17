/**
 * favorites.js: instant toggle for the favorite heart buttons.
 *
 * On submit of a form[data-favorite-form] the heart flips straight away, then
 * the same POST is sent in the background:
 *   - success: the server's answer wins (the heart is corrected if it differs);
 *   - failure: the heart flips back and the form is submitted the normal way.
 * While a request is in flight, further clicks on that heart are ignored.
 *
 * This handler calls preventDefault(), so confirm.js's double-submit guard
 * (which runs later, on window, and skips prevented submits) never marks a
 * heart button aria-disabled. The in-flight flag below is the hearts' own guard.
 *
 * Guest hearts are plain links with data-auth-prompt, not forms, so they never
 * reach this script.
 */
(function () {
    'use strict';

    function render(form, saved, animate) {
        var button = form.querySelector('.favorite-button');
        var label = form.querySelector('[data-favorite-label]');
        if (button) {
            button.classList.toggle('is-saved', saved);
            button.setAttribute('aria-pressed', saved ? 'true' : 'false');
            // Restart the pop each time the heart becomes saved.
            button.classList.remove('is-popping');
            if (saved && animate) {
                void button.offsetWidth;
                button.classList.add('is-popping');
            }
        }
        if (label) {
            label.textContent = saved ? 'Saved' : 'Save';
        }
    }

    document.addEventListener('submit', function (event) {
        var form = event.target;
        if (!form || !form.matches('form[data-favorite-form]')) {
            return;
        }
        event.preventDefault();
        if (form.hasAttribute('data-favorite-busy')) {
            return;
        }

        var button = form.querySelector('.favorite-button');
        var wasSaved = Boolean(button && button.classList.contains('is-saved'));
        form.setAttribute('data-favorite-busy', '');
        render(form, !wasSaved, true);

        fetch(form.action, {
            method: 'POST',
            body: new FormData(form),
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin'
        })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(function (data) {
                var saved = Boolean(data.favorited);
                if (saved !== !wasSaved) {
                    render(form, saved, false);
                }
                form.removeAttribute('data-favorite-busy');
            })
            .catch(function () {
                render(form, wasSaved, false);
                form.removeAttribute('data-favorite-busy');
                HTMLFormElement.prototype.submit.call(form);
            });
    });
})();
