/**
 * nav.js — Dropdown toggle for the site navbar menu.
 *
 * Toggles .is-open on the dropdown and aria-expanded on the button.
 * Closes on outside-click or the Escape key.
 */
(function () {
    'use strict';

    var toggle = document.getElementById('menu-toggle');
    var dropdown = document.getElementById('nav-dropdown');

    if (!toggle || !dropdown) return;

    toggle.addEventListener('click', function (e) {
        e.stopPropagation();
        var isOpen = dropdown.classList.toggle('is-open');
        toggle.setAttribute('aria-expanded', isOpen);
    });

    document.addEventListener('click', function (e) {
        if (!dropdown.contains(e.target)) {
            dropdown.classList.remove('is-open');
            toggle.setAttribute('aria-expanded', 'false');
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            dropdown.classList.remove('is-open');
            toggle.setAttribute('aria-expanded', 'false');
        }
    });
})();
