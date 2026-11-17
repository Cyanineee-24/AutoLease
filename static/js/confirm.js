/**
 * confirm.js: themed confirmation for form[data-confirm], plus a double-submit guard.
 *
 * Form attributes:
 *   data-confirm         body text; its presence turns the confirmation on
 *   data-confirm-title   heading (default "Are you sure?")
 *   data-confirm-action  confirm button label (default "Confirm")
 *   data-confirm-cancel  cancel button label (default "Go back")
 *   data-confirm-danger  present: the confirm button is red (.button-danger)
 *   data-confirm-when    "field:value1,value2": only confirm when that field holds
 *                        one of the values AND differs from the value the page
 *                        loaded with (form only)
 *
 * The same attributes on a submit button win over the form's: when the clicked
 * button has data-confirm, its whole set is used. That lets two buttons in one
 * form (Approve / Decline) ask different questions, or one of them ask nothing.
 *
 * Without JavaScript every form submits normally. Without <dialog> support the
 * browser's own confirm() is used instead.
 *
 * Double-submit guard: once a POST form really submits, its submit buttons get
 * aria-disabled="true" and later submits are ignored. The disabled attribute is
 * never set, because disabled buttons drop their name/value from the POST.
 */
(function () {
    'use strict';

    var dialog = document.getElementById('confirm-dialog');
    var hasDialog = Boolean(dialog && typeof dialog.showModal === 'function');
    var titleEl = dialog && dialog.querySelector('#confirm-dialog-title');
    var textEl = dialog && dialog.querySelector('#confirm-dialog-text');
    var acceptBtn = dialog && dialog.querySelector('[data-confirm-accept]');
    var dismissBtn = dialog && dialog.querySelector('[data-confirm-dismiss]');
    var closeBtn = dialog && dialog.querySelector('[data-confirm-close]');

    var approved = new WeakSet();  // forms the user just confirmed
    var pending = null;            // { form, submitter } while the dialog is open

    var SUBMIT_BUTTONS = 'button[type="submit"], button:not([type]), input[type="submit"]';

    function isPost(form) {
        // getAttribute, because a field named "method" would shadow form.method.
        return (form.getAttribute('method') || '').toLowerCase() === 'post';
    }

    function initialValue(field) {
        if (field.tagName === 'SELECT') {
            for (var i = 0; i < field.options.length; i++) {
                if (field.options[i].defaultSelected) {
                    return field.options[i].value;
                }
            }
            return field.options.length ? field.options[0].value : '';
        }
        return field.defaultValue;
    }

    // Where the confirmation settings come from: the clicked button if it has
    // its own, else the form. Null when neither asks for a confirmation.
    function confirmSource(form, submitter) {
        if (submitter && submitter.hasAttribute('data-confirm')) {
            return submitter;
        }
        return form.hasAttribute('data-confirm') ? form : null;
    }

    function needsConfirm(form, submitter) {
        var source = confirmSource(form, submitter);
        if (!source) {
            return false;
        }
        if (source !== form) {
            return true;
        }
        var when = form.getAttribute('data-confirm-when');
        if (!when) {
            return true;
        }
        var parts = when.split(':');
        var field = form.querySelector('[name="' + parts[0].trim() + '"]');
        if (!field) {
            return true;  // misconfigured: ask rather than skip
        }
        var values = (parts[1] || '').split(',').map(function (v) { return v.trim(); });
        return values.indexOf(field.value) !== -1 && field.value !== initialValue(field);
    }

    function lock(form) {
        form.setAttribute('data-submitting', '');
        form.querySelectorAll(SUBMIT_BUTTONS).forEach(function (button) {
            button.setAttribute('aria-disabled', 'true');
        });
    }

    function unlock(form) {
        form.removeAttribute('data-submitting');
        form.querySelectorAll(SUBMIT_BUTTONS).forEach(function (button) {
            button.removeAttribute('aria-disabled');
        });
    }

    function proceed(form, submitter) {
        approved.add(form);
        if (typeof form.requestSubmit === 'function') {
            // Fires submit again with the same submitter, so its name/value is posted.
            if (submitter) {
                form.requestSubmit(submitter);
            } else {
                form.requestSubmit();
            }
            return;
        }
        // Older browsers: carry the clicked button's name/value by hand.
        approved.delete(form);
        if (submitter && submitter.name) {
            var hidden = document.createElement('input');
            hidden.type = 'hidden';
            hidden.name = submitter.name;
            hidden.value = submitter.value;
            form.appendChild(hidden);
        }
        if (isPost(form)) {
            lock(form);
        }
        HTMLFormElement.prototype.submit.call(form);
    }

    function ask(form, submitter) {
        var source = confirmSource(form, submitter);
        var text = source.getAttribute('data-confirm') || '';
        if (!hasDialog) {
            if (window.confirm(text)) {
                // Still inside the submit event here, where browsers ignore a
                // nested requestSubmit(), so wait a tick.
                window.setTimeout(function () { proceed(form, submitter); }, 0);
            }
            return;
        }
        pending = { form: form, submitter: submitter };
        titleEl.textContent = source.getAttribute('data-confirm-title') || 'Are you sure?';
        textEl.textContent = text;
        textEl.hidden = !text;
        acceptBtn.textContent = source.getAttribute('data-confirm-action') || 'Confirm';
        acceptBtn.className = source.hasAttribute('data-confirm-danger') ? 'button-danger' : 'button';
        dismissBtn.textContent = source.getAttribute('data-confirm-cancel') || 'Go back';
        dialog.showModal();
        dismissBtn.focus();
    }

    // On window, so it runs after document-level handlers such as favorites.js;
    // a submit they already took over (defaultPrevented) is left alone.
    window.addEventListener('submit', function (event) {
        var form = event.target;
        if (!(form instanceof HTMLFormElement)) {
            return;
        }
        if (form.hasAttribute('data-submitting')) {
            event.preventDefault();
            return;
        }
        if (event.defaultPrevented) {
            return;
        }
        if (approved.has(form)) {
            approved.delete(form);
        } else if (needsConfirm(form, event.submitter || null)) {
            event.preventDefault();
            ask(form, event.submitter || null);
            return;
        }
        if (isPost(form)) {
            lock(form);
        }
    });

    // Back/forward cache restores the page as it was left: re-enable the buttons.
    window.addEventListener('pageshow', function (event) {
        if (event.persisted) {
            document.querySelectorAll('form[data-submitting]').forEach(unlock);
        }
    });

    if (!hasDialog) {
        return;
    }

    acceptBtn.addEventListener('click', function () {
        var request = pending;
        pending = null;
        dialog.close();
        if (request) {
            proceed(request.form, request.submitter);
        }
    });

    dismissBtn.addEventListener('click', function () {
        dialog.close();
    });

    closeBtn.addEventListener('click', function () {
        dialog.close();
    });

    // Backdrop click: the dialog has no padding, so only the backdrop hits it.
    dialog.addEventListener('click', function (event) {
        if (event.target === dialog) {
            dialog.close();
        }
    });

    // Cancel, the X, Escape (native) and backdrop clicks all end here.
    dialog.addEventListener('close', function () {
        if (!pending) {
            return;
        }
        var target = pending.submitter || pending.form.querySelector(SUBMIT_BUTTONS);
        pending = null;
        if (target && typeof target.focus === 'function') {
            target.focus();
        }
    });
})();
