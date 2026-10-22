/* seller.js — which merchant sells Orrery. ONE line to change: `which`.
 *
 * 2026-10-08. Paddle's website review is still failing; Lemon Squeezy is the
 * second seller being readied. Whichever approves first goes live by editing
 * `which` below — nothing else on the site changes. Until then it is "none"
 * and the page behaves exactly as before (buttons scroll to the price section).
 *
 * 2026-10-10: neither approved. Stripe Managed Payments went live instead and
 * `which` is "stripe" — the paragraph above is the record of how we got here,
 * not the current state. Read `which`, never this comment.
 *
 * Everything in this file is PUBLIC by design (price IDs, client-side token,
 * checkout URLs). Never put an API key here.
 */
window.ORRERY_SELLER = {
  which: "stripe",          // "none" | "stripe" | "paddle" | "lemonsqueezy"   — LIVE 2026-10-10

  // Stripe Managed Payments (merchant of record), live 2026-10-10. Payment
  // Links redirect to thanks.html with ?session_id= (and kind=monthly).
  stripe: {
    once: "https://buy.stripe.com/bJe6oJ2T5dzA1yi2bW9EI00",      // $79, one time
    monthly: "https://buy.stripe.com/5kQ8wRdxJ678ccW5o89EI01",   // $5 / month
  },
  paddle: {
    token: "",              // client-side token, starts live_  (Developer tools → Authentication)
    once: "pri_01m2hh6n6tsbgyzdrgy8nevnad",      // $79, one time
    monthly: "pri_01m2vrzkee7286g0mkkvv83d56",   // $5 / month
  },
  lemonsqueezy: {
    once: "",               // checkout link for the $79 product (Share → Checkout link)
    monthly: "",            // checkout link for the $5/month product
  },

  thanks: "https://ostanekresearch.com/orrery/thanks.html",
};

(function () {
  var S = window.ORRERY_SELLER;
  var MOR = {
    paddle: "Our order process is conducted by Paddle.com, who are the Merchant of Record for all our orders. Paddle provides all customer service inquiries and handles returns.",
    stripe: "Orders are sold through Link, operated by Stripe, our Merchant of Record, which handles payment, sales tax and VAT.",
    lemonsqueezy: "Orders are processed by Lemon Squeezy, our Merchant of Record, which handles payment, sales tax and VAT.",
  };
  // Every other merchant-specific sentence on the site. Added 2026-10-22: the
  // 10-10 swap to Stripe corrected #mor on download.html and left refunds.html
  // — which carries MORE of these sentences than download.html does — naming
  // Paddle to every visitor, because that page was never wired to this file.
  // A page about money must be true before any script runs, so each page now
  // ships the live merchant's wording as its own text and these only re-state
  // it. Switching `which` rewrites all three ids; there is no fourth place.
  var LINES = {
    "card-statement": {
      paddle: "Your card statement will show Paddle, not Ostanek Research.",
      stripe: "Your card statement will show Stripe, not Ostanek Research.",
      lemonsqueezy: "Your card statement will show Lemon Squeezy, not Ostanek Research.",
    },
    "refund-route": {
      paddle: "You can also request a refund directly through Paddle using the receipt they emailed you.",
      stripe: "You can also request a refund using the receipt Stripe emailed you.",
      lemonsqueezy: "You can also request a refund through Lemon Squeezy using the receipt they emailed you.",
    },
  };

  function ready(fn) { document.readyState !== "loading" ? fn() : document.addEventListener("DOMContentLoaded", fn); }

  var paddleLoading = null;
  function withPaddle(cb) {
    if (window.Paddle && window.Paddle.Checkout) return cb();
    if (!paddleLoading) {
      paddleLoading = new Promise(function (res, rej) {
        var s = document.createElement("script");
        s.src = "https://cdn.paddle.com/paddle/v2/paddle.js";
        s.onload = function () { window.Paddle.Initialize({ token: S.paddle.token }); res(); };
        s.onerror = rej;
        document.head.appendChild(s);
      });
    }
    paddleLoading.then(cb, function () { alert("The checkout couldn't load. Please try again, or write to kevin@ostanekresearch.com."); });
  }

  function buy(kind) {
    if (S.which === "paddle" && S.paddle.token && S.paddle[kind]) {
      withPaddle(function () {
        window.Paddle.Checkout.open({
          items: [{ priceId: S.paddle[kind], quantity: 1 }],
          settings: { successUrl: S.thanks },
        });
      });
      return true;
    }
    if (S.which === "stripe" && S.stripe[kind]) {
      window.location.href = S.stripe[kind];
      return true;
    }
    if (S.which === "lemonsqueezy" && S.lemonsqueezy[kind]) {
      window.location.href = S.lemonsqueezy[kind];
      return true;
    }
    return false;   // no live seller: fall through to the link's own href
  }

  ready(function () {
    document.querySelectorAll("[data-buy]").forEach(function (el) {
      el.addEventListener("click", function (e) {
        if (buy(el.getAttribute("data-buy"))) e.preventDefault();
      });
    });
    // "none" leaves every page's own line alone: the HTML is the truthful
    // default, not a placeholder, so a dead script degrades to correct text.
    var mor = document.getElementById("mor");
    if (mor && MOR[S.which]) mor.textContent = MOR[S.which];
    Object.keys(LINES).forEach(function (id) {
      var el = document.getElementById(id);
      if (el && LINES[id][S.which]) el.textContent = LINES[id][S.which];
    });
    var live = S.which !== "none";
    document.querySelectorAll("[data-when-live]").forEach(function (el) { el.hidden = !live; });
    document.querySelectorAll("[data-when-not-live]").forEach(function (el) { el.hidden = live; });
  });
})();
