/**
 * auth_prompt.js — Login prompt modal for guests.
 *
 * Any element with [data-auth-prompt] opens #auth-prompt instead of following
 * its href. The modal's Log in / Sign up links carry ?next= so the guest comes
 * back to the same page (with chosen booking dates kept). Without JS (or
 * without <dialog> support) the trigger's own login?next= href still works.
 */
(function () {
    'use strict';

    var dialog = document.getElementById('auth-prompt');
    if (!dialog || typeof dialog.showModal !== 'function') {
        return;
    }

    var DEFAULT_TITLE = 'Log in to continue';
    var titleEl = document.getElementById('auth-prompt-title');
    var loginLink = document.getElementById('auth-prompt-login');
    var signupLink = document.getElementById('auth-prompt-signup');
    var iconSlot = dialog.querySelector('[data-auth-prompt-icon]');
    var closeBtn = dialog.querySelector('[data-auth-prompt-close]');
    var lastTrigger = null;

    function setIcon(name) {
        var template = dialog.querySelector('template[data-auth-icon="' + name + '"]') ||
            dialog.querySelector('template[data-auth-icon="user"]');
        if (!template || !iconSlot) {
            return;
        }
        iconSlot.textContent = '';
        iconSlot.appendChild(template.content.cloneNode(true));
    }

    function bookingNext() {
        var start = document.getElementById('booking-start-date');
        var end = document.getElementById('booking-end-date');
        if (start && end && start.value && end.value) {
            return window.location.pathname +
                '?start_date=' + encodeURIComponent(start.value) +
                '&end_date=' + encodeURIComponent(end.value);
        }
        return null;
    }

    function resolveNext(trigger) {
        if (trigger.hasAttribute('data-auth-booking')) {
            var next = bookingNext();
            if (next) {
                return next;
            }
        }
        return trigger.getAttribute('data-auth-next') ||
            (window.location.pathname + window.location.search);
    }

    function open(trigger) {
        var next = encodeURIComponent(resolveNext(trigger));
        lastTrigger = trigger;
        titleEl.textContent = trigger.getAttribute('data-auth-title') || DEFAULT_TITLE;
        setIcon(trigger.getAttribute('data-auth-icon') || 'user');
        loginLink.href = dialog.getAttribute('data-login-url') + '?next=' + next;
        signupLink.href = dialog.getAttribute('data-register-url') + '?next=' + next;
        dialog.showModal();
        loginLink.focus();
    }

    document.addEventListener('click', function (e) {
        var trigger = e.target.closest('[data-auth-prompt]');
        if (!trigger) {
            return;
        }
        e.preventDefault();
        open(trigger);
    });

    if (closeBtn) {
        closeBtn.addEventListener('click', function () {
            dialog.close();
        });
    }

    // Backdrop click: the dialog itself has no padding, so only the backdrop hits it.
    dialog.addEventListener('click', function (e) {
        if (e.target === dialog) {
            dialog.close();
        }
    });

    // Fires for the X, Esc (native) and backdrop clicks alike.
    dialog.addEventListener('close', function () {
        if (lastTrigger && typeof lastTrigger.focus === 'function') {
            lastTrigger.focus();
        }
        lastTrigger = null;
    });
})();
