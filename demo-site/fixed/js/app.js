// BetterBrew Coffee Roasters - Fixed Client Application (Accessible & Friction-Free)

(function () {
  'use strict';

  // --- Cart State Management ---
  function getCart() {
    try {
      const data = sessionStorage.getItem('betterbrew_cart');
      return data ? JSON.parse(data) : [];
    } catch (e) {
      return [];
    }
  }

  function saveCart(cart) {
    try {
      sessionStorage.setItem('betterbrew_cart', JSON.stringify(cart));
      updateCartBadge();
    } catch (e) {
      // Ignore storage errors
    }
  }

  function updateCartBadge() {
    const badge = document.getElementById('nav-cart-count');
    if (!badge) return;
    const cart = getCart();
    const count = cart.reduce((acc, item) => acc + (item.qty || 1), 0);
    badge.textContent = count;
    badge.setAttribute('aria-label', `${count} items in cart`);
  }

  function showToast(message, linkText, linkUrl) {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-live', 'polite');
    toast.innerHTML = `
      <div class="toast-message">${message}</div>
      ${linkText ? `<a href="${linkUrl}" class="toast-link">${linkText} &rarr;</a>` : ''}
    `;

    container.appendChild(toast);

    setTimeout(() => {
      toast.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      setTimeout(() => {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, 300);
    }, 4500);
  }

  function addItemToCart(item) {
    const cart = getCart();
    const existingIndex = cart.findIndex(i => i.id === item.id);
    if (existingIndex > -1) {
      cart[existingIndex].qty = (cart[existingIndex].qty || 1) + 1;
    } else {
      cart.push({ ...item, qty: 1 });
    }
    saveCart(cart);

    showToast(`Added ${item.title} to your cart!`, 'View Cart', 'cart.html');
  }

  // --- Pricing Plans Data & Injection (Fix 6: Fast load <= 800ms with Skeleton) ---
  const SUBSCRIPTION_PLANS = [
    {
      id: 'sub-starter',
      title: 'Casual Sipper',
      price: 18,
      period: '/month',
      description: 'One 12oz bag of seasonal single-origin roast delivered fresh monthly.',
      features: [
        '1 bag per month (12oz)',
        'Whole bean or fresh drip grind',
        'Tasting notes & brew card included',
        'Standard shipping included'
      ]
    },
    {
      id: 'sub-monthly',
      title: "Roaster's Choice",
      price: 24,
      period: '/month',
      featured: true,
      description: 'Two curated 12oz bags of freshly roasted micro-lots selected by our head roaster.',
      features: [
        '2 bags per month (24oz total)',
        'Exclusive micro-lot access',
        'Free expedited shipping',
        'Free seasonal sample with each box'
      ]
    },
    {
      id: 'sub-connoisseur',
      title: 'Espresso Club',
      price: 36,
      period: '/month',
      description: 'Three 12oz bags of rich, complex roasts optimized for espresso and pour-over.',
      features: [
        '3 bags per month (36oz total)',
        'Single-origin & signature espresso',
        'Priority roasting batch delivery',
        'Invitations to virtual cupping sessions'
      ]
    }
  ];

  function renderSkeleton(container) {
    if (!container) return;
    container.setAttribute('aria-busy', 'true');
    container.setAttribute('aria-live', 'polite');

    const skeletonCards = [1, 2, 3].map(() => `
      <div class="skeleton-card" aria-hidden="true">
        <div class="skeleton-shimmer skeleton-title"></div>
        <div class="skeleton-shimmer skeleton-text"></div>
        <div class="skeleton-shimmer skeleton-price"></div>
        <div class="skeleton-shimmer skeleton-line"></div>
        <div class="skeleton-shimmer skeleton-line"></div>
        <div class="skeleton-shimmer skeleton-btn"></div>
      </div>
    `).join('');

    container.innerHTML = `<div class="plans-grid">${skeletonCards}</div>`;
  }

  function renderPlans(container) {
    if (!container) return;
    container.setAttribute('aria-busy', 'false');

    const html = SUBSCRIPTION_PLANS.map(plan => `
      <div class="plan-card ${plan.featured ? 'featured' : ''}">
        ${plan.featured ? '<span class="featured-pill">Most Popular</span>' : ''}
        <h3 class="plan-title">${plan.title}</h3>
        <p class="plan-description">${plan.description}</p>
        <div class="plan-price-box">
          <span class="plan-price">$${plan.price}</span>
          <span class="plan-period">${plan.period}</span>
        </div>
        <ul class="plan-features">
          ${plan.features.map(f => `
            <li>
              <svg viewBox="0 0 20 20">
                <path d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"/>
              </svg>
              <span>${f}</span>
            </li>
          `).join('')}
        </ul>
        <!-- Fix 2: Honest label "Add to Cart" -->
        <button type="button" class="btn btn-primary btn-block btn-plan-select" data-plan-id="${plan.id}" data-plan-title="${plan.title} Subscription" data-plan-price="${plan.price}" aria-label="Add ${plan.title} subscription for $${plan.price} per month to cart">Add to Cart</button>
      </div>
    `).join('');

    container.innerHTML = `<div class="plans-grid">${html}</div>`;

    container.querySelectorAll('.btn-plan-select').forEach(button => {
      button.addEventListener('click', function () {
        const id = this.getAttribute('data-plan-id');
        const title = this.getAttribute('data-plan-title');
        const price = parseFloat(this.getAttribute('data-plan-price'));

        addItemToCart({
          id: id,
          title: title,
          price: price,
          type: 'Subscription',
          frequency: 'Monthly'
        });
      });
    });
  }

  // --- Cart Page Logic ---
  function initCartPage() {
    const tableBody = document.getElementById('cart-items-body');
    const subtotalEl = document.getElementById('cart-subtotal');
    const totalEl = document.getElementById('cart-total');
    const emptyStateEl = document.getElementById('cart-empty-state');
    const contentWrapperEl = document.getElementById('cart-content-wrapper');

    if (!tableBody) return;

    const cart = getCart();

    if (cart.length === 0) {
      if (emptyStateEl) emptyStateEl.style.display = 'block';
      if (contentWrapperEl) contentWrapperEl.style.display = 'none';
      return;
    }

    if (emptyStateEl) emptyStateEl.style.display = 'none';
    if (contentWrapperEl) contentWrapperEl.style.display = 'block';

    let subtotal = 0;
    tableBody.innerHTML = cart.map((item, index) => {
      const lineTotal = item.price * (item.qty || 1);
      subtotal += lineTotal;
      return `
        <tr>
          <td>
            <div class="cart-item-info">
              <div>
                <div class="cart-item-title">${item.title}</div>
                <div class="cart-item-type">${item.type || 'Product'} &bull; ${item.frequency || 'Single Purchase'}</div>
              </div>
            </div>
          </td>
          <td>$${item.price.toFixed(2)}</td>
          <td>${item.qty || 1}</td>
          <td>$${lineTotal.toFixed(2)}</td>
        </tr>
      `;
    }).join('');

    if (subtotalEl) subtotalEl.textContent = `$${subtotal.toFixed(2)}`;
    if (totalEl) totalEl.textContent = `$${subtotal.toFixed(2)}`;
  }

  // --- Checkout Page Logic (Fix 4: Accessible Form Validation) ---
  function initCheckoutPage() {
    const form = document.getElementById('checkout-form');
    const errorSummary = document.getElementById('error-summary');
    const errorSummaryList = document.getElementById('error-summary-list');
    const orderItemsList = document.getElementById('checkout-items-list');
    const orderTotalEl = document.getElementById('checkout-order-total');

    if (!form) return;

    const cart = getCart();
    let total = 0;

    if (orderItemsList) {
      if (cart.length === 0) {
        orderItemsList.innerHTML = '<p>Your cart is empty.</p>';
      } else {
        orderItemsList.innerHTML = cart.map(item => {
          const itemTotal = item.price * (item.qty || 1);
          total += itemTotal;
          return `
            <div class="order-detail-line">
              <span>${item.title} (x${item.qty || 1})</span>
              <span>$${itemTotal.toFixed(2)}</span>
            </div>
          `;
        }).join('');
      }
    }

    if (orderTotalEl) {
      orderTotalEl.textContent = `$${total.toFixed(2)}`;
    }

    form.addEventListener('submit', function (e) {
      e.preventDefault();

      // Clear previous error state
      if (errorSummary) errorSummary.style.display = 'none';
      if (errorSummaryList) errorSummaryList.innerHTML = '';
      
      const fields = [
        { id: 'cust_name', label: 'Full name', validator: val => val.trim().length > 0, message: 'Please enter your full name' },
        { id: 'cust_email', label: 'Email address', validator: val => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val), message: 'Please enter a valid email address (e.g. name@example.com)' },
        { id: 'cust_phone', label: 'Phone number', validator: val => val.trim().length >= 7, message: 'Please enter a valid phone number so we can text delivery updates' },
        { id: 'cust_address', label: 'Street address', validator: val => val.trim().length > 0, message: 'Please enter your delivery street address' },
        { id: 'cust_city', label: 'City', validator: val => val.trim().length > 0, message: 'Please enter your city' },
        { id: 'cust_postal', label: 'Postal code', validator: val => val.trim().length > 0, message: 'Please enter your postal or ZIP code' },
        { id: 'cust_card', label: 'Card number', validator: val => val.trim().length >= 12, message: 'Please enter a valid card number' }
      ];

      const errors = [];
      let firstInvalidInput = null;

      fields.forEach(field => {
        const input = document.getElementById(field.id);
        const errorEl = document.getElementById(`${field.id}-error`);
        if (!input) return;

        const val = input.value || '';
        const isValid = field.validator(val);

        if (!isValid) {
          input.classList.add('input-error');
          input.setAttribute('aria-invalid', 'true');
          if (errorEl) {
            errorEl.textContent = field.message;
            errorEl.classList.add('active');
          }
          errors.push({ fieldId: field.id, label: field.label, message: field.message });
          if (!firstInvalidInput) {
            firstInvalidInput = input;
          }
        } else {
          input.classList.remove('input-error');
          input.removeAttribute('aria-invalid');
          if (errorEl) {
            errorEl.classList.remove('active');
          }
        }
      });

      if (errors.length > 0) {
        if (errorSummary && errorSummaryList) {
          errorSummaryList.innerHTML = errors.map(err => `
            <li><a href="#${err.fieldId}">${err.message}</a></li>
          `).join('');
          errorSummary.style.display = 'block';
          errorSummary.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        if (firstInvalidInput) {
          firstInvalidInput.focus();
        }
        return;
      }

      // Successful order
      const name = document.getElementById('cust_name').value;
      const email = document.getElementById('cust_email').value;
      const phone = document.getElementById('cust_phone').value;
      const address = document.getElementById('cust_address').value;
      const city = document.getElementById('cust_city').value;
      const postal = document.getElementById('cust_postal').value;

      const orderData = {
        orderId: 'BB-' + Math.floor(10000 + Math.random() * 90000),
        date: new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }),
        customer: { name, email, phone, address, city, postal },
        items: cart.length > 0 ? cart : [
          {
            id: 'sub-monthly',
            title: "Roaster's Choice Monthly Subscription",
            price: 24,
            qty: 1,
            frequency: 'Monthly'
          }
        ],
        total: total > 0 ? total : 24.00
      };

      try {
        sessionStorage.setItem('betterbrew_last_order', JSON.stringify(orderData));
        sessionStorage.removeItem('betterbrew_cart');
      } catch (err) {
        // storage fallback
      }

      window.location.href = 'thanks.html';
    });
  }

  // --- Thanks Page Logic ---
  function initThanksPage() {
    const orderIdEl = document.getElementById('order-summary-id');
    const orderItemsEl = document.getElementById('order-summary-items');
    const orderTotalEl = document.getElementById('order-summary-total');
    const orderCustomerEl = document.getElementById('order-summary-customer');
    const orderAddressEl = document.getElementById('order-summary-address');

    if (!orderIdEl) return;

    let order = null;
    try {
      const data = sessionStorage.getItem('betterbrew_last_order');
      if (data) order = JSON.parse(data);
    } catch (e) {
      order = null;
    }

    if (!order) {
      order = {
        orderId: 'BB-84920',
        date: 'Today',
        customer: {
          name: 'Coffee Enthusiast',
          email: 'alex@example.com',
          phone: '555-019-2834',
          address: '742 Evergreen Terrace',
          city: 'Springfield',
          postal: '97477'
        },
        items: [
          {
            title: "Roaster's Choice Monthly Subscription",
            price: 24,
            qty: 1,
            frequency: 'Monthly'
          }
        ],
        total: 24.00
      };
    }

    orderIdEl.textContent = order.orderId;
    if (orderTotalEl) orderTotalEl.textContent = `$${order.total.toFixed(2)}`;
    if (orderCustomerEl) orderCustomerEl.textContent = `${order.customer.name} (${order.customer.email})`;
    if (orderAddressEl) orderAddressEl.textContent = `${order.customer.address}, ${order.customer.city} ${order.customer.postal}`;

    if (orderItemsEl) {
      orderItemsEl.innerHTML = order.items.map(item => `
        <div class="order-detail-line">
          <span>${item.title} (x${item.qty || 1})</span>
          <span>$${(item.price * (item.qty || 1)).toFixed(2)}</span>
        </div>
      `).join('');
    }
  }

  // --- Newsletter Modal (Fix 3: Polite, saved in localStorage, 44px close target, Esc/overlay close, focus trap) ---
  function initNewsletterModal() {
    const modal = document.getElementById('newsletter-modal');
    const closeBtn = document.getElementById('newsletter-modal-close');
    const form = document.getElementById('newsletter-modal-form');
    const openTrigger = document.getElementById('newsletter-open-trigger');

    if (!modal) return;

    let previousActiveElement = null;

    function openModal() {
      if (localStorage.getItem('betterbrew_newsletter_dismissed') === 'true') {
        return;
      }
      previousActiveElement = document.activeElement;
      modal.style.display = 'flex';
      if (closeBtn) closeBtn.focus();
    }

    function closeModal() {
      modal.style.display = 'none';
      localStorage.setItem('betterbrew_newsletter_dismissed', 'true');
      if (previousActiveElement && typeof previousActiveElement.focus === 'function') {
        previousActiveElement.focus();
      }
    }

    // Trigger after 20s if not previously dismissed
    if (localStorage.getItem('betterbrew_newsletter_dismissed') !== 'true') {
      setTimeout(openModal, 20000);
    }

    // Allow manual open via footer link
    if (openTrigger) {
      openTrigger.addEventListener('click', function (e) {
        e.preventDefault();
        previousActiveElement = document.activeElement;
        modal.style.display = 'flex';
        if (closeBtn) closeBtn.focus();
      });
    }

    // Close on close button click
    if (closeBtn) {
      closeBtn.addEventListener('click', closeModal);
    }

    // Close on overlay backdrop click
    modal.addEventListener('click', function (e) {
      if (e.target === modal) {
        closeModal();
      }
    });

    // Close on Escape key
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && modal.style.display === 'flex') {
        closeModal();
      }
    });

    if (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        closeModal();
        showToast('Thank you for subscribing! Your 10% discount code is BREW10.');
      });
    }
  }

  // --- Document Ready Handler ---
  document.addEventListener('DOMContentLoaded', function () {
    updateCartBadge();
    initNewsletterModal();

    const pricingContainer = document.getElementById('pricing-plans-container');
    if (pricingContainer) {
      renderSkeleton(pricingContainer);
      // Fast simulated fetch under 800ms (350ms)
      setTimeout(function () {
        renderPlans(pricingContainer);
      }, 350);
    }

    initCartPage();
    initCheckoutPage();
    initThanksPage();

    // Bind all generic add to cart buttons on shop page
    document.querySelectorAll('.btn-add-product').forEach(btn => {
      btn.addEventListener('click', function () {
        const id = this.getAttribute('data-product-id');
        const title = this.getAttribute('data-product-title');
        const price = parseFloat(this.getAttribute('data-product-price'));
        addItemToCart({
          id: id,
          title: title,
          price: price,
          type: 'Coffee Bag',
          frequency: 'Single Purchase'
        });
      });
    });
  });
})();
