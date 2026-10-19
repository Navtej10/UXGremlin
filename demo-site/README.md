# BetterBrew Coffee - UX Friction Test Fixture for UXGremlin

A realistic, offline static e-commerce fixture designed to evaluate how AI agents (such as **UXGremlin**) detect, quantify, and document user experience friction and accessibility barriers.

Built with **plain HTML, CSS, and JavaScript only**. No build steps, no npm dependencies, no external CDN requests, and pure relative paths.

---

## Quick Start (How to Run)

From your terminal, start a local HTTP server:

```bash
# Option A: Serve from the repository root
python -m http.server 8080

# Option B: Or serve directly inside /demo-site
cd demo-site
python -m http.server 8080
```

### URLs

| Version | Description | URL (Served from repo root) | URL (Served from `demo-site/`) |
|---|---|---|---|
| **Bad Version** | Contains 6 deliberate, realistic UX friction points | `http://localhost:8080/demo-site/index.html` | `http://localhost:8080/index.html` |
| **Fixed Version** | Accessible, friction-free implementation | `http://localhost:8080/demo-site/fixed/index.html` | `http://localhost:8080/fixed/index.html` |

---

## The Demo Task

> **Task Prompt:**  
> *"A user wants to subscribe to the monthly coffee plan and complete checkout."*

### Completing the Task

The demo task is 100% completable end-to-end in **both** versions and terminates on `thanks.html` displaying the order summary. In the "Bad" version, completing it requires navigating several realistic friction points:

1. **Find Subscription:**  
   - *Bad:* Hunting down the faint 11px footer link "Subscribe" (`#bbb` on `#eee`) because header/hero CTAs are missing.  
   - *Fixed:* Clicking the prominent "Subscribe" button in the header nav or hero CTA.
2. **View Plans:**  
   - *Bad:* Waiting ~5.5s while the pricing section appears blank with no indicator, then experiencing layout jump.  
   - *Fixed:* Immediate skeleton loader with smooth load in ~350ms.
3. **Add Monthly Plan:**  
   - *Bad:* Clicking "Proceed" silently adds the plan to cart without any confirmation.  
   - *Fixed:* Clicking "Add to Cart" displays an instant toast confirmation with a link to cart and updates the cart badge.
4. **Navigate Cart:**  
   - *Bad:* Ignoring the misleading "Continue" button (which returns to shop) and clicking the plain text link "Next".  
   - *Fixed:* Clicking the primary "Proceed to Checkout →" button.
5. **Fill Checkout:**  
   - *Bad:* Submitting without a phone number triggers a generic red banner: *"Invalid input. Please try again."* Users must realize phone is required despite lacking a label or asterisk. On mobile screens (<=600px), user must scroll past or deal with the sticky promo bar covering the "Next" button.  
   - *Fixed:* Clear labels, explicit required markings with hints, inline error validation with focus shift, and unobstructed "Place Order" button.
6. **Order Confirmation:**  
   - Arrives at `thanks.html` with full order summary and confirmation number.

---

## Before & After Checklist

| Problem Area | "Bad" Version (`/demo-site`) | "Fixed" Version (`/demo-site/fixed`) |
|---|---|---|
| **1. Subscribe CTA** | Missing from header & hero; only an 11px faint link in footer (`#bbb` on `#eee`, contrast 1.46:1). | Prominent, high-contrast header button (`>= 44px`, 4.54:1 ratio) + hero CTA + clear footer link. |
| **2. Button Labels** | "Proceed" adds to cart silently; "Continue" bounces back to shop; "Next" places order. | Honest labels: "Add to Cart", "Proceed to Checkout", "Place Order". Instant toast confirmation. |
| **3. Newsletter Modal** | Triggers after 4s; reappears every 8s after closing; tiny 14px close button; no Esc/backdrop close; no `localStorage`. | Triggers politely after 20s or on demand; saved in `localStorage`; 44px close target; closes on Esc & backdrop; focus trapped. |
| **4. Form Validation** | Placeholders instead of labels; phone required without indicator; vague *"Invalid input"* banner; email gives *"Error 422"*; no field highlights. | Visible semantic `<label>`s; `* (required)` markings; plain-English inline errors; accessible top error summary with jump links; auto-focus. |
| **5. Mobile Sticky Bar** | On `<= 600px`, fixed promo bar sits directly on top of the "Next" button; 0px bottom padding prevents tapping. | Promo bar suppressed on checkout; generous 80px bottom padding ensures CTA is always visible and tap-friendly. |
| **6. Async Pricing** | Blank empty section for 5.5s with no loader/spinner; sudden layout shift (CLS). | Instant skeleton cards (`aria-busy="true"`); zero layout shift; fast load within 350ms. |

---

## Project Structure

```text
/demo-site
├── index.html          (Homepage)
├── shop.html           (Products & subscription tiers)
├── cart.html           (Cart review & actions)
├── checkout.html       (Checkout form & order submission)
├── thanks.html         (Order confirmation & receipt)
├── css/
│   └── styles.css      (Styles with deliberate UX flaws)
├── js/
│   └── app.js          (Client application with planted behaviors)
├── ISSUES.md           (Ground truth manifest with WCAG & heuristic mapping)
├── README.md           (Setup instructions, demo task, and checklist)
└── fixed/              (Fully self-contained remediated version)
    ├── index.html
    ├── shop.html
    ├── cart.html
    ├── checkout.html
    ├── thanks.html
    ├── css/
    │   └── styles.css  (Accessible, responsive styles)
    └── js/
        └── app.js      (Friction-free, accessible client logic)
```

Both versions are completely self-contained with no shared parent assets, allowing `/demo-site/fixed` to be deployed or served as an independent standalone site.
