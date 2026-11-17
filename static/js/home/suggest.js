/**
 * suggest.js: search suggestions for the dashboard's Where and What fields.
 *
 * Accessible combobox (WAI-ARIA list autocomplete): the input keeps focus, the
 * listbox below it shows suggestions, and aria-activedescendant points at the
 * highlighted option. Picking a suggestion only fills the field; the user still
 * presses the search button. Without JavaScript the form works as a plain search.
 *
 * Keys: Down/Up move (and wrap), Enter picks the highlighted option (and does
 * not submit), Enter with nothing highlighted submits as usual, Escape and Tab
 * close the list.
 *
 * Suggestions come from GET <data-suggest-url>?field=...&term=...; requests are
 * debounced and the previous one is aborted, so a late, older response can't
 * replace newer results. All text is set with textContent, never innerHTML.
 */
(function () {
    'use strict';

    var form = document.querySelector('form[data-suggest-url]');
    if (!form || typeof window.AbortController !== 'function') {
        return;
    }
    var endpoint = form.getAttribute('data-suggest-url');
    var DEBOUNCE_MS = 200;
    var EMPTY_TEXT = 'No matches. Try another spelling.';
    var SVG_NS = 'http://www.w3.org/2000/svg';
    var ICONS = {
        // Location pin for Where, car for What.
        location: ['M12 21s-6-5.6-6-10.5A6 6 0 0 1 18 10.5C18 15.4 12 21 12 21z', 'M12 12.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4z'],
        q: ['M5 11l1.6-4.2A2 2 0 0 1 8.5 5.5h7a2 2 0 0 1 1.9 1.3L19 11', 'M3 11h18v6H3z', 'M6 17v2M18 17v2']
    };

    function icon(field) {
        var svg = document.createElementNS(SVG_NS, 'svg');
        svg.setAttribute('width', '18');
        svg.setAttribute('height', '18');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('fill', 'none');
        svg.setAttribute('aria-hidden', 'true');
        svg.setAttribute('class', 'suggest-icon');
        ICONS[field].forEach(function (d) {
            var path = document.createElementNS(SVG_NS, 'path');
            path.setAttribute('d', d);
            path.setAttribute('stroke', 'currentColor');
            path.setAttribute('stroke-width', '1.8');
            path.setAttribute('stroke-linejoin', 'round');
            path.setAttribute('stroke-linecap', 'round');
            svg.appendChild(path);
        });
        return svg;
    }

    // "Toyota Vios" with the typed part in bold, built from text nodes only.
    function highlighted(label, term) {
        var span = document.createElement('span');
        span.className = 'suggest-label';
        var at = label.toLowerCase().indexOf(term.toLowerCase());
        if (!term || at === -1) {
            span.textContent = label;
            return span;
        }
        span.appendChild(document.createTextNode(label.slice(0, at)));
        var strong = document.createElement('strong');
        strong.textContent = label.slice(at, at + term.length);
        span.appendChild(strong);
        span.appendChild(document.createTextNode(label.slice(at + term.length)));
        return span;
    }

    function setUp(input) {
        var field = input.name;  // 'location' or 'q', the endpoint's field names
        var list = document.getElementById(input.getAttribute('aria-controls'));
        var options = [];
        var active = -1;
        var timer = null;
        var controller = null;
        var lastTerm = null;

        function isOpen() {
            return input.getAttribute('aria-expanded') === 'true';
        }

        function highlight(index) {
            options.forEach(function (option, i) {
                option.classList.toggle('is-active', i === index);
                option.setAttribute('aria-selected', i === index ? 'true' : 'false');
            });
            active = index;
            if (index >= 0) {
                input.setAttribute('aria-activedescendant', options[index].id);
                options[index].scrollIntoView({ block: 'nearest' });
            } else {
                input.removeAttribute('aria-activedescendant');
            }
        }

        function close() {
            list.hidden = true;
            input.setAttribute('aria-expanded', 'false');
            highlight(-1);
        }

        function open() {
            list.hidden = false;
            input.setAttribute('aria-expanded', 'true');
        }

        function pick(index) {
            input.value = options[index].getAttribute('data-value');
            lastTerm = input.value.trim();  // don't re-suggest for the value just picked
            close();
        }

        function render(suggestions, term) {
            list.textContent = '';
            options = [];
            active = -1;
            if (!suggestions.length) {
                var empty = document.createElement('li');
                empty.className = 'suggest-empty';
                // Not an option, so it can't be highlighted or picked.
                empty.setAttribute('role', 'presentation');
                empty.textContent = EMPTY_TEXT;
                list.appendChild(empty);
            }
            suggestions.forEach(function (item, i) {
                var option = document.createElement('li');
                option.id = list.id + '-option-' + i;
                option.className = 'suggest-option';
                option.setAttribute('role', 'option');
                option.setAttribute('aria-selected', 'false');
                option.setAttribute('data-value', item.value);
                option.appendChild(icon(field));
                option.appendChild(highlighted(item.label, term));
                var meta = document.createElement('span');
                meta.className = 'suggest-meta';
                meta.textContent = item.meta;
                option.appendChild(meta);
                option.addEventListener('mouseenter', function () { highlight(i); });
                // mousedown + preventDefault: the input keeps focus until the pick lands.
                option.addEventListener('mousedown', function (event) { event.preventDefault(); });
                option.addEventListener('click', function () { pick(i); });
                list.appendChild(option);
                options.push(option);
            });
            input.removeAttribute('aria-activedescendant');
            open();
        }

        function fetchSuggestions(term) {
            if (controller) {
                controller.abort();  // only the newest request may answer
            }
            controller = new AbortController();
            var url = endpoint + '?field=' + encodeURIComponent(field) + '&term=' + encodeURIComponent(term);
            fetch(url, { signal: controller.signal, headers: { 'Accept': 'application/json' } })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error('HTTP ' + response.status);
                    }
                    return response.json();
                })
                .then(function (data) {
                    // Ignore it if the field changed (or was emptied) meanwhile.
                    if (input.value.trim() === term && document.activeElement === input) {
                        render(data.suggestions || [], term);
                    }
                })
                .catch(function (error) {
                    if (error.name !== 'AbortError') {
                        close();  // suggestions are optional; typing and searching still work
                    }
                });
        }

        input.addEventListener('input', function () {
            var term = input.value.trim();
            window.clearTimeout(timer);
            if (!term) {
                if (controller) {
                    controller.abort();
                }
                lastTerm = null;
                close();
                return;
            }
            timer = window.setTimeout(function () {
                lastTerm = term;
                fetchSuggestions(term);
            }, DEBOUNCE_MS);
        });

        input.addEventListener('keydown', function (event) {
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                if (!isOpen() || !options.length) {
                    return;
                }
                event.preventDefault();
                var step = event.key === 'ArrowDown' ? 1 : -1;
                var next = active === -1 ? (step === 1 ? 0 : options.length - 1) : (active + step + options.length) % options.length;
                highlight(next);
            } else if (event.key === 'Enter') {
                if (isOpen() && active >= 0) {
                    event.preventDefault();  // pick, don't submit
                    pick(active);
                }
            } else if (event.key === 'Escape') {
                if (isOpen()) {
                    event.preventDefault();
                    close();
                }
            } else if (event.key === 'Tab') {
                close();
            }
        });

        input.addEventListener('blur', function () {
            close();
        });

        // Clicking anywhere else closes the list.
        document.addEventListener('mousedown', function (event) {
            if (isOpen() && event.target !== input && !list.contains(event.target)) {
                close();
            }
        });
    }

    form.querySelectorAll('input[role="combobox"]').forEach(setUp);
})();
