/**
 * photos.js: drop zone for the "More photos" upload form.
 *
 * Progressive enhancement only. Without it, the file input is visible and the
 * form uploads normally. With it:
 *   - the input is hidden from view (still focusable) and the chosen files are
 *     listed under the drop zone;
 *   - files can be dropped onto the zone;
 *   - a selection larger than the remaining slots shows a warning in that text.
 * Nothing is submitted automatically, and the server decides what is accepted.
 */
(function () {
    'use strict';

    var form = document.querySelector('[data-photo-upload]');
    if (!form) {
        return;
    }
    var zone = form.querySelector('[data-photo-dropzone]');
    var input = zone.querySelector('input[type="file"]');
    var selection = form.querySelector('[data-photo-selection]');
    var remaining = parseInt(form.getAttribute('data-remaining'), 10);

    zone.classList.add('is-enhanced');

    function plural(count) {
        return count + (count === 1 ? ' photo' : ' photos');
    }

    function describe(note) {
        var files = input.files;
        selection.textContent = '';
        selection.classList.remove('is-warning');
        if (!files.length && !note) {
            selection.hidden = true;
            return;
        }
        if (files.length) {
            var names = Array.prototype.map.call(files, function (file) { return file.name; });
            var count = document.createElement('strong');
            count.textContent = plural(files.length) + ' selected';
            selection.appendChild(count);
            // File names come from the user's machine: text nodes only, never HTML.
            selection.appendChild(document.createTextNode(': ' + names.join(', ')));
            if (files.length > remaining) {
                note = 'You can add ' + plural(remaining).replace(' photo', ' more photo') +
                    ' to this car. Choose fewer before uploading.';
            }
        }
        if (note) {
            selection.classList.add('is-warning');
            selection.appendChild(document.createTextNode((files.length ? '. ' : '') + note));
        }
        selection.hidden = false;
    }

    input.addEventListener('change', function () {
        describe();
    });

    function hasFiles(event) {
        var types = event.dataTransfer && event.dataTransfer.types;
        return Boolean(types) && Array.prototype.indexOf.call(types, 'Files') !== -1;
    }

    ['dragenter', 'dragover'].forEach(function (type) {
        zone.addEventListener(type, function (event) {
            if (hasFiles(event)) {
                zone.classList.add('is-dragover');
            }
        });
    });

    ['dragleave', 'drop'].forEach(function (type) {
        zone.addEventListener(type, function () {
            zone.classList.remove('is-dragover');
        });
    });

    zone.addEventListener('drop', function (event) {
        if (!hasFiles(event)) {
            return;
        }
        var dropped = event.dataTransfer.files;
        try {
            input.files = dropped;
        } catch (error) {
            // Some browsers don't allow setting input.files.
        }
        if (input.files.length === dropped.length) {
            describe();
        } else {
            describe("Dropping files isn't supported in this browser. Use \"choose files\" instead.");
        }
    });

    // A file dropped anywhere on the page (even beside the zone) must not make
    // the browser navigate away to that file.
    ['dragover', 'drop'].forEach(function (type) {
        window.addEventListener(type, function (event) {
            if (hasFiles(event)) {
                event.preventDefault();
            }
        });
    });
})();
