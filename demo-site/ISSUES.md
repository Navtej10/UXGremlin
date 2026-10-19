# UX Friction Manifest: BetterBrew Coffee (Test Fixture)

This document serves as the ground truth manifest for **UXGremlin**, detailing the 6 deliberate, realistic UX friction points implemented in `/demo-site` (the "Bad" version) and how each is remediated in `/demo-site/fixed` (the "Fixed" version).

---

## Summary Table

| ID | Issue Name | Page(s) | Primary Severity | Heuristic / WCAG Standard |
|---|---|---|---|---|
| **ISSUE-01** | Hidden Subscribe CTA | `index.html`, `shop.html` | High | WCAG 1.4.3 (Contrast), Nielsen #6 (Recognition over Recall) |
| **ISSUE-02** | Confusing Button Labels & Broken Flow Feedback | `shop.html`, `cart.html`, `checkout.html` | High | Nielsen #2 (Match Real World), Nielsen #1 (Visibility of System Status) |
| **ISSUE-03** | Aggressive, Inaccessible Newsletter Modal | All pages sitewide | High | WCAG 2.1.1 (Keyboard), WCAG 2.5.5 (Target Size), Nielsen #3 (User Control) |
| **ISSUE-04** | Form Validation Deficits & Placeholder Labels | `checkout.html` | Critical | WCAG 3.3.1 (Error Identification), WCAG 3.3.2 (Labels/Instructions) |
| **ISSUE-05** | Mobile Sticky Bar Obstructing Primary CTA | `checkout.html` (<=600px) | Critical | WCAG 2.5.8 (Pointer Target Spacing), Nielsen #7 (Flexibility & Efficiency) |
| **ISSUE-06** | Slow Pricing Load Without Loading Indicator | `shop.html` | Medium | Nielsen #1 (Visibility of System Status), Cumulative Layout Shift (CLS) |

---

## Detailed Issue Manifest

### ISSUE-01: Hidden Subscribe Call-to-Action (CTA)

- **ID:** `ISSUE-01`
- **Page(s):** `index.html`, `shop.html`
- **What's Wrong in `/demo-site`:**
  - There is no "Subscribe" button or navigation link in the top header nav.
  - The hero section only provides an "Explore Blends" button pointing to general retail coffee bags, omitting any subscription pathway.
  - The subscription tier on `shop.html` is buried at the bottom without anchor navigation from the page header or hero.
  - The **only** direct path to subscribing on the homepage is an obscure footer link labeled "Subscribe" rendered at `11px`, styled in light grey (`#bbbbbb`) on a light grey background (`#eeeeee`), with no underline and no hover state change.
  - The contrast ratio of `#bbb` on `#eee` is **1.46:1**, failing WCAG minimums drastically.
- **Why It Hurts Users:**
  - Users with visual or cognitive impairments cannot discern the link.
  - High intent users wanting to start a monthly subscription abandon the site because the core offering is virtually invisible.
  - Increases time-to-task dramatically, forcing users to hunt through footers for critical conversion paths.
- **How `/fixed` Resolves It:**
  - Adds a prominent, primary "Subscribe" button in the sticky header nav (`min-height: 44px`, high-contrast `#ffffff` on `#b85d19`, contrast ratio `4.54:1`).
  - Adds a hero CTA button: "Subscribe & Save 15%" linking directly to `#subscription`.
  - Upgrades the footer link to high-contrast white text on espresso dark background (contrast ratio `> 14:1`), with `15px` font size and an underline hover effect.
- **WCAG / Heuristic Reference:**
  - **WCAG 2.1 SC 1.4.3 Contrast (Minimum):** Requires a contrast ratio of at least 4.5:1 for normal text.
  - **Nielsen Norman Heuristic #6:** Recognition rather than recall. Essential actions must be clearly visible and accessible.

---

### ISSUE-02: Confusing Button Labels & Missing Feedback (Mismatched Intent)

- **ID:** `ISSUE-02`
- **Page(s):** `shop.html`, `cart.html`, `checkout.html`
- **What's Wrong in `/demo-site`:**
  - **Shop Page:** On the monthly subscription card, the primary action button is labeled **"Proceed"**. Clicking it adds the subscription to `sessionStorage` cart and remains on the page with **zero feedback** (no confirmation message, no toast, no cart count update, no visual state change). Users assume "Proceed" will take them forward, but nothing appears to happen.
  - **Cart Page:** The dominant primary button is labeled **"Continue"**. In standard e-commerce conventions, a primary button on a cart page advances to checkout. Here, clicking "Continue" executes `window.location.href='shop.html'`, bouncing the user backwards to the shop ("continue shopping"). Meanwhile, the actual action to checkout is an unstyled, plain text link labeled **"Next"** (`color: #555555; text-decoration: none;`).
  - **Checkout Page:** The final submit button is labeled **"Next"**. Users expect "Next" to advance to an order review or payment confirmation screen; instead, it immediately finalizes the transaction and submits the order.
  - **Result:** "Proceed", "Continue", and "Next" each contradict standard convention and user expectations.
- **Why It Hurts Users:**
  - Breaches the principle of least astonishment. Users experience rage clicks when clicking "Proceed" because the UI appears frozen or unresponsive.
  - Users clicking "Continue" on the cart page are disoriented when redirected back to the catalog, assuming an error occurred.
  - Misleading final CTAs generate anxiety regarding whether funds will be captured before review.
- **How `/fixed` Resolves It:**
  - **Shop Page:** Button is explicitly labeled **"Add to Cart"** (with descriptive `aria-label`). Clicking immediately triggers an accessible toast notification ("✓ Added BetterBrew Roaster's Choice Subscription ($24/mo) to cart!") with a direct "View Cart" link, while the header cart badge pulses and increments to `1`.
  - **Cart Page:** The primary CTA is clearly labeled **"Proceed to Checkout →"**; a secondary button is provided labeled **"Continue Shopping"**.
  - **Checkout Page:** The submit button is explicitly labeled **"Place Order"**.
- **WCAG / Heuristic Reference:**
  - **Nielsen Norman Heuristic #1:** Visibility of system status. The system should always keep users informed about what is going on through appropriate feedback within reasonable time.
  - **Nielsen Norman Heuristic #2:** Match between system and the real world. Follow real-world conventions and standard e-commerce terminology.
  - **WCAG 2.1 SC 4.1.3 Status Messages:** Status messages must be presented to users without receiving focus.

---

### ISSUE-03: Aggressive, Inaccessible Newsletter Modal

- **ID:** `ISSUE-03`
- **Page(s):** All pages (`index.html`, `shop.html`, `cart.html`, `checkout.html`, `thanks.html`)
- **What's Wrong in `/demo-site`:**
  - An intrusive newsletter overlay interrupts the user ~4 seconds after initial load on every single page.
  - Closing the modal does **not** persist dismissal state (no `localStorage` or cookie). The modal reopens automatically 8 seconds later, and resets again on any subsequent page navigation.
  - The close button is an 11px light grey "✕" (`#bbbbbb`) on a white dialog background (contrast ratio `1.46:1`), with an inaccessible touch target of 14px × 14px, and missing `aria-label`.
  - Clicking the backdrop overlay does nothing; pressing the `Escape` key does nothing.
- **Why It Hurts Users:**
  - Causes severe task interruption, especially while attempting to enter credit card details on checkout or reading subscription terms.
  - Frustrates mobile and motor-impaired users who struggle to hit the 14px close target.
  - Traps keyboard-only and screen reader users due to lack of `Escape` handling and missing modal semantics.
- **How `/fixed` Resolves It:**
  - The modal only triggers once after a polite 20-second delay or via explicit user intent (footer link "Join Newsletter").
  - Dismissal is permanently stored in `localStorage.setItem('betterbrew_newsletter_dismissed', 'true')` so it never pops up again once closed.
  - Close button is an accessible 44px × 44px button with high contrast, clear hover state, and `aria-label="Close newsletter signup offer"`.
  - Closes immediately upon clicking the background overlay or pressing `Escape`.
  - Contains semantic ARIA attributes (`role="dialog"`, `aria-modal="true"`, `aria-labelledby`), with focus restored to the previous active element on close.
- **WCAG / Heuristic Reference:**
  - **WCAG 2.1 SC 2.1.1 Keyboard:** All functionality must be operable through a keyboard interface.
  - **WCAG 2.1 SC 2.5.5 / 2.5.8 Target Size:** Minimum target size of 44×44px (or 24×24px minimum with spacing).
  - **Nielsen Norman Heuristic #3:** User control and freedom. Support undo, easy exits, and avoid trapping users in unsolicited dialogs.

---

### ISSUE-04: Checkout Form Validation Deficits & Placeholder Labels

- **ID:** `ISSUE-04`
- **Page(s):** `checkout.html`
- **What's Wrong in `/demo-site`:**
  - Inputs use HTML `placeholder` attributes instead of `<label>` elements. Once text is typed, the label vanishes; screen readers lack proper accessible associations.
  - The **Phone** field is strictly required by the submission script, but gives zero visual cue (no asterisk, no helper text, no "(required)" indicator). Users naturally assume phone is optional.
  - When form validation fails, a vague red banner appears at the very top: *"Invalid input. Please try again."*
  - If the email address is invalid, the banner displays a cryptic system error: *"Error 422"*.
  - No inputs are highlighted with error borders; no inline error messages exist; keyboard focus is not moved to the invalid field.
- **Why It Hurts Users:**
  - Users are trapped in a guessing game trying to figure out which field caused "Invalid input. Please try again."
  - Vanishing placeholders cause cognitive strain and memory load during data entry.
  - Blind or low-vision users using assistive technology receive no announcement of errors linked to specific form controls.
- **How `/fixed` Resolves It:**
  - Persistent `<label for="...">` tags for every single input field.
  - Required fields are clearly identified with red asterisks and `<span class="sr-only">(required)</span>`.
  - Phone field includes visible helper text: *"Enter a phone number so we can text delivery updates."*
  - Accessible error summary alert box appears at the top on submit, containing clickable jump links (`<a href="#cust_phone">`) directly to each offending field.
  - Focus automatically moves to the first invalid field (`input.focus()`).
  - Inputs receive red highlight borders, `aria-invalid="true"`, and `aria-describedby` pointing to plain-language inline error messages.
  - Email error is formatted in human-readable plain English: *"Please enter a valid email address (e.g. name@example.com)"*.
- **WCAG / Heuristic Reference:**
  - **WCAG 2.1 SC 3.3.1 Error Identification:** If an input error is detected, the item is identified and described in text.
  - **WCAG 2.1 SC 3.3.2 Labels or Instructions:** Labels or instructions are provided when content requires user input.
  - **WCAG 2.1 SC 3.3.3 Error Suggestion:** Provide suggestions to fix errors when known.
  - **Nielsen Norman Heuristic #9:** Help users recognize, diagnose, and recover from errors.

---

### ISSUE-05: Mobile Sticky Bar Obstructing the Primary Checkout Button

- **ID:** `ISSUE-05`
- **Page(s):** `checkout.html` (viewport width `<= 600px`, e.g. 375px mobile view)
- **What's Wrong in `/demo-site`:**
  - On viewports `<= 600px`, a fixed promotional banner ("Free shipping over $30 | Chat with us") is pinned to the bottom: `position: fixed; bottom: 0; left: 0; right: 0; height: 52px; z-index: 999;`.
  - The checkout container lacks bottom padding (`padding-bottom: 0px`).
  - The primary submit button ("Next") is located at the bottom of the form container.
  - When scrolling to the bottom of the page, the sticky bar sits directly on top of the submit button, completely obscuring it and intercepting tap events. The button cannot be tapped under normal scrolling.
- **Why It Hurts Users:**
  - Absolute conversion blocker for mobile customers.
  - Users are physically unable to complete checkout, causing abandonment right at the final step.
- **How `/fixed` Resolves It:**
  - On the fixed checkout page, the promotional sticky bar is suppressed (`display: none;`) to avoid unnecessary distraction during checkout.
  - Generous bottom safe-area padding (`padding-bottom: 80px;`) is enforced so the "Place Order" button is always 100% visible, unobstructed, and comfortable to tap on mobile screens down to 320px.
- **WCAG / Heuristic Reference:**
  - **WCAG 2.1 SC 2.5.8 Pointer Target Spacing & Target Clearance:** Content must not obscure interactive controls.
  - **WCAG 2.1 SC 1.4.10 Reflow:** Content can be presented without loss of information or functionality on narrow viewports (320 CSS pixels).
  - **Nielsen Norman Heuristic #7:** Flexibility and efficiency of use.

---

### ISSUE-06: Slow Pricing Load Without Loading Indicator (Cumulative Layout Shift)

- **ID:** `ISSUE-06`
- **Page(s):** `shop.html`
- **What's Wrong in `/demo-site`:**
  - The coffee subscription pricing cards load asynchronously via JavaScript with a simulated 5.5-second delay.
  - During this prolonged loading period, the `#pricing-plans-container` element has `min-height: 0` and renders completely blank: no spinner, no skeleton loader, no placeholder text, and no `aria-busy` attribute.
  - Users arriving at the subscription section see an empty white gap and assume the feature is broken.
  - After 5.5 seconds, the three large pricing cards abruptly inject into the DOM, causing a massive Cumulative Layout Shift (CLS) that shoves the footer down by over 450 pixels.
- **Why It Hurts Users:**
  - Severe layout shift can cause users to accidentally click the wrong element if they were about to tap something else when the layout jumps.
  - Lack of feedback violates expectations for network requests, prompting impatient users to leave.
- **How `/fixed` Resolves It:**
  - Container reserves the exact required height (`min-height: 480px`), completely eliminating Cumulative Layout Shift (`CLS = 0`).
  - Renders an immediate skeleton loading animation (3 shimmering placeholder cards) on DOM ready.
  - Communicates progress to screen readers via `aria-busy="true"` and `aria-live="polite"`.
  - Loads swiftly within 350ms (well under the 800ms threshold), then smoothly swaps the skeleton for the interactive plan cards and sets `aria-busy="false"`.
- **WCAG / Heuristic Reference:**
  - **Nielsen Norman Heuristic #1:** Visibility of system status. Immediate and continuous visual feedback during async operations.
  - **Core Web Vitals:** Cumulative Layout Shift (CLS < 0.1).
  - **WCAG 2.1 SC 4.1.3 Status Messages:** Dynamic changes announced appropriately to assistive technologies.
