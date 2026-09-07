/**
 * register.js — Dynamic form field visibility for AutoLease registration.
 *
 * Shows "Business name" only when "I manage a rental business" (agency) is selected.
 * Hides it when "I want to rent a vehicle" (renter) is selected.
 */
(function () {
    'use strict';

    var businessGroup = document.getElementById('business-name-group');
    if (!businessGroup) return;

    var businessInput = businessGroup.querySelector('input');
    var accountTypeRadios = document.querySelectorAll('input[name="account_type"]');

    function updateVisibility() {
        var selected = document.querySelector('input[name="account_type"]:checked');
        if (selected && selected.value === 'agency') {
            businessGroup.classList.remove('is-hidden');
            if (businessInput) businessInput.required = true;
        } else {
            businessGroup.classList.add('is-hidden');
            if (businessInput) {
                businessInput.required = false;
            }
        }
    }

    accountTypeRadios.forEach(function (radio) {
        radio.addEventListener('change', function () {
            if (radio.value === 'renter' && businessInput) {
                businessInput.value = '';
            }
            updateVisibility();
        });
    });

    // Run on initial load to reflect current selection (e.g. on validation errors)
    updateVisibility();
})();
