/**
 * vehicle_detail.js — Date calculations for the booking card and gallery modal.
 */
(function () {
    'use strict';

    var bookingCard = document.querySelector('[data-rate]');
    var startInput = document.getElementById('booking-start-date');
    var endInput = document.getElementById('booking-end-date');
    var dateError = document.getElementById('booking-date-error');
    var breakdownEmpty = document.getElementById('breakdown-empty');
    var breakdownDetails = document.getElementById('breakdown-details');
    var breakdownRateLine = document.getElementById('breakdown-rate-line');
    var breakdownLineAmount = document.getElementById('breakdown-line-amount');
    var breakdownTotal = document.getElementById('breakdown-total');

    function updateBookingCalculations() {
        if (!startInput || !endInput || !bookingCard) {
            return;
        }

        var startVal = startInput.value;
        var endVal = endInput.value;

        if (startVal) {
            endInput.min = startVal;
        }

        if (!startVal || !endVal) {
            if (dateError) {
                dateError.style.display = 'none';
            }
            if (breakdownDetails) {
                breakdownDetails.style.display = 'none';
            }
            if (breakdownEmpty) {
                breakdownEmpty.style.display = 'block';
            }
            return;
        }

        var startDate = new Date(startVal + 'T00:00:00');
        var endDate = new Date(endVal + 'T00:00:00');

        if (endDate < startDate) {
            if (dateError) {
                dateError.textContent = 'Drop-off must be on or after pick-up.';
                dateError.style.display = 'block';
            }
            if (breakdownDetails) {
                breakdownDetails.style.display = 'none';
            }
            if (breakdownEmpty) {
                breakdownEmpty.style.display = 'none';
            }
            return;
        }

        if (dateError) {
            dateError.style.display = 'none';
        }
        if (breakdownEmpty) {
            breakdownEmpty.style.display = 'none';
        }
        if (breakdownDetails) {
            breakdownDetails.style.display = 'block';
        }

        var days = Math.round((endDate - startDate) / 86400000) + 1;
        var rate = parseFloat(bookingCard.getAttribute('data-rate')) || 0;
        var total = days * rate;

        var formatter = new Intl.NumberFormat('en-PH', {
            style: 'currency',
            currency: 'PHP',
            minimumFractionDigits: 0,
            maximumFractionDigits: 2
        });

        var formattedRate = formatter.format(rate);
        var formattedTotal = formatter.format(total);

        if (breakdownRateLine) {
            breakdownRateLine.textContent = formattedRate + ' x ' + days + (days === 1 ? ' day' : ' days');
        }
        if (breakdownLineAmount) {
            breakdownLineAmount.textContent = formattedTotal;
        }
        if (breakdownTotal) {
            breakdownTotal.textContent = formattedTotal;
        }
    }

    if (startInput) {
        startInput.addEventListener('input', updateBookingCalculations);
    }
    if (endInput) {
        endInput.addEventListener('input', updateBookingCalculations);
    }

    updateBookingCalculations();

    // Gallery <dialog> handlers
    var openDialogBtn = document.getElementById('open-gallery-dialog');
    var galleryDialog = document.getElementById('gallery-dialog');
    var closeDialogBtn = document.getElementById('close-gallery-dialog');

    if (openDialogBtn && galleryDialog) {
        openDialogBtn.addEventListener('click', function () {
            galleryDialog.showModal();
        });
    }

    if (closeDialogBtn && galleryDialog) {
        closeDialogBtn.addEventListener('click', function () {
            galleryDialog.close();
        });
    }

    if (galleryDialog) {
        galleryDialog.addEventListener('click', function (e) {
            if (e.target === galleryDialog) {
                galleryDialog.close();
            }
        });
    }
})();
