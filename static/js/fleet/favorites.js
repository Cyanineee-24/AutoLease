/**
 * favorites.js: the favorite heart is a pure UI action; the server catches up.
 *
 * Every click on a form[data-favorite-form] flips the heart at once, even
 * while an earlier request is still on its way. Nothing waits and nothing locks.
 * Per heart, three values are kept:
 *   desired    what the heart shows now (the user's latest choice)
 *   confirmed  the last state the server reported (at first, what the page rendered)
 *   inFlight   whether a request is pending
 * A request asks for a state (saved=1 or saved=0), never for a flip. At most
 * one request per heart is in flight; when it returns and the user has changed
 * their mind meanwhile, one more is sent for the latest choice. Hearts for
 * different cars sync independently.
 *
 * Leaving the page early doesn't lose the choice: requests use `keepalive`, so
 * the browser finishes them after the page is gone, and any heart whose latest
 * choice hasn't been sent yet is sent with sendBeacon() on pagehide.
 *
 * Failures:
 *   - session expired (the request was redirected to the login page): go to
 *     the login page, and come back to this page afterwards;
 *   - anything else: the heart returns to the confirmed state and a short
 *     message appears at the bottom of the page. There is no full-page fallback.
 *
 * This handler calls preventDefault(), so confirm.js's double-submit guard
 * (which runs later, on window, and skips prevented submits) never marks a
 * heart button aria-disabled.
 *
 * Without JavaScript the form posts normally (no `saved` field) and the server
 * toggles. Guest hearts are links with data-auth-prompt, not forms, so they
 * never reach this script.
 */
(function () {
    'use strict';

    var FAILURE_TEXT = "Couldn't update your saved cars. Try again.";
    var TOAST_MS = 4000;
    var loginPath = document.body.getAttribute('data-login-url') || '/login/';

    var states = new WeakMap();
    var tracked = [];  // forms that have been clicked, for the pagehide check
    var toast = null;
    var toastTimer = null;

    function stateFor(form) {
        var state = states.get(form);
        if (!state) {
            var button = form.querySelector('.favorite-button');
            var saved = Boolean(button && button.classList.contains('is-saved'));
            // `sent` is the state the pending request asks for (meaningful while inFlight).
            state = { desired: saved, confirmed: saved, inFlight: false, sent: saved };
            states.set(form, state);
            tracked.push(form);
        }
        return state;
    }

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

    // One shared live region, created the first time it is needed.
    function showFailure() {
        if (!toast) {
            toast = document.createElement('div');
            toast.className = 'alert alert-error favorite-toast';
            toast.setAttribute('role', 'status');
            toast.hidden = true;
            document.body.appendChild(toast);
        }
        toast.textContent = FAILURE_TEXT;
        toast.hidden = false;
        window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(function () {
            toast.hidden = true;
        }, TOAST_MS);
    }

    function sessionExpired(response) {
        if (!response.redirected) {
            return false;
        }
        var path = new URL(response.url, window.location.href).pathname;
        return path.indexOf(loginPath) === 0;
    }

    function fail(form, state) {
        state.inFlight = false;
        state.desired = state.confirmed;
        render(form, state.confirmed, false);
        showFailure();
    }

    function payload(form, saved) {
        var body = new FormData(form);
        body.set('saved', saved ? '1' : '0');
        return body;
    }

    function sync(form) {
        var state = stateFor(form);
        if (state.inFlight || state.desired === state.confirmed) {
            return;
        }
        var sent = state.desired;
        state.sent = sent;
        state.inFlight = true;

        fetch(form.action, {
            method: 'POST',
            body: payload(form, sent),
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin',
            keepalive: true  // let it finish even if the user navigates away
        })
            .then(function (response) {
                if (sessionExpired(response)) {
                    // Log in, then come back to this page (not to the POST-only endpoint).
                    var here = window.location.pathname + window.location.search;
                    window.location.assign(loginPath + '?next=' + encodeURIComponent(here));
                    return null;
                }
                if (!response.ok) {
                    throw new Error('Unexpected status ' + response.status);
                }
                return response.json();
            })
            .then(function (data) {
                if (data === null) {
                    return;  // on the way to the login page
                }
                if (typeof data.favorited !== 'boolean') {
                    throw new Error('Unexpected response');
                }
                state.inFlight = false;
                state.confirmed = data.favorited;
                if (state.desired === state.confirmed) {
                    return;  // already showing the right thing: leave the DOM alone
                }
                if (state.confirmed === sent) {
                    // The request did what it asked; the user has clicked again since.
                    sync(form);
                } else {
                    // The server ended somewhere else: show what is really stored.
                    state.desired = state.confirmed;
                    render(form, state.confirmed, false);
                }
            })
            .catch(function () {
                fail(form, state);
            });
    }

    document.addEventListener('submit', function (event) {
        var form = event.target;
        if (!form || !form.matches('form[data-favorite-form]')) {
            return;
        }
        event.preventDefault();

        // The UI first, on every click; the network comes after.
        var state = stateFor(form);
        state.desired = !state.desired;
        render(form, state.desired, true);
        sync(form);
    });

    // Leaving the page: a heart whose latest choice was never sent (the user
    // clicked again while a request was pending) gets one last request. It asks
    // for a state, so it is safe even if it overlaps the pending one.
    window.addEventListener('pagehide', function () {
        if (!navigator.sendBeacon) {
            return;
        }
        tracked.forEach(function (form) {
            var state = states.get(form);
            var lastAsked = state.inFlight ? state.sent : state.confirmed;
            if (state.desired !== lastAsked) {
                navigator.sendBeacon(form.action, payload(form, state.desired));
            }
        });
    });
})();
