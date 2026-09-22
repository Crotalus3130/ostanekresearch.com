/* Ostanek Research — theme toggle. 2026-09-22, Claude Vardjan.
 *
 * Progressive enhancement, in the strict sense: with this file blocked or
 * JavaScript off, the site still follows the reader's system setting through
 * prefers-color-scheme, and no dead button is left on the page — the button
 * is created here, not in the HTML.
 *
 * The stored value is an OVERRIDE. "System" is a real third state, not the
 * absence of a choice, so a reader who flips their Mac to dark at sunset gets
 * the site following along unless they explicitly said otherwise.
 */
(function () {
  "use strict";

  var KEY = "or-theme"; // "light" | "dark" | absent = follow the system
  var root = document.body;
  if (!root) return;

  function stored() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }
  function store(v) {
    try { v ? localStorage.setItem(KEY, v) : localStorage.removeItem(KEY); }
    catch (e) { /* Safari private mode throws on setItem; ignore. */ }
  }
  function systemIsDark() {
    return window.matchMedia &&
           window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  // A theme-night page is dark BY DEFAULT (Ara's direction, 2026-09-22):
  // its baseline is "dark" regardless of the reader's system, and the
  // toggle overrides that. Other pages keep following the system.
  var nightDefault = root.classList.contains("theme-night");
  function baseTheme() {
    return nightDefault ? "dark" : (systemIsDark() ? "dark" : "light");
  }
  function active() {
    return stored() || baseTheme();
  }

  function apply(v) {
    if (v) root.setAttribute("data-theme", v);
    else root.removeAttribute("data-theme");
    // Once the real toggle governs, the pre-boot hint must not linger:
    // a stale data-preboot outranks the stylesheet and would pin the page
    // to the boot-time theme after the reader toggles away from it.
    document.documentElement.removeAttribute("data-preboot");
  }

  function label(btn) {
    var now = active();
    btn.textContent = now === "dark" ? "Day" : "Night";
    btn.setAttribute("aria-label",
      now === "dark" ? "Switch to the light paper theme"
                     : "Switch to the dark theme");
    btn.setAttribute("aria-pressed", now === "dark" ? "true" : "false");
  }

  apply(stored());

  var nav = document.querySelector(".nav");
  if (!nav) return;

  var btn = document.createElement("button");
  btn.type = "button";
  btn.className = "theme-toggle nav-end";
  label(btn);
  btn.addEventListener("click", function () {
    var next = active() === "dark" ? "light" : "dark";
    // If the reader's choice matches the page's baseline (night pages:
    // dark; others: the system), drop the override so the page goes back
    // to its default. Storing the baseline itself would have made "Day"
    // a no-op on a system-light machine: store("light"), baseline dark,
    // and the null round-trip shows dark again.
    store(next === baseTheme() ? null : next);
    apply(stored());
    label(btn);
  });
  nav.appendChild(btn);

  // Follow the system live while no explicit override is set.
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    var onChange = function () { if (!stored()) label(btn); };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
    else if (mq.addListener) mq.addListener(onChange);
  }
})();
