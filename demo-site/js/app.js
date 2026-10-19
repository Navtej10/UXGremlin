// BetterBrew Coffee Roasters - Core Client Application

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
    } catch (e) {
      // Ignore storage errors
    }
  }

  function updateCartBadge() {
    const cart = getCart();
    const count = cart.reduce((acc, item) => acc + (item.qty || 1), 0);
    const cartLinks = document.querySelectorAll('.nav-cart-link');
    cartLinks.forEach(link => {
      let badge = link.querySelector('.cart-count-badge');
      if (count > 0) {
        if (!badge) {
          badge = document.createElement('span');
          badge.className = 'cart-count-badge';
          badge.style.marginLeft = '4px';
          badge.style.fontSize = '12px';
          badge.style.opacity = '0.9';
          link.appendChild(badge);
        }
        badge.textContent = `(${count})`;
      } else if (badge) {
        badge.remove();
      }
    });
  }

  function addItemToCart(item) {
    if (!item) return;
    const cart = getCart();
    const existingIndex = cart.findIndex(i => i.id === item.id);
    if (existingIndex > -1) {
      cart[existingIndex].qty = (cart[existingIndex].qty || 1) + 1;
    } else {
      cart.push({ ...item, qty: 1 });
    }
    saveCart(cart);
    updateCartBadge();
  }

  // --- Pricing Plans Data & Injection ---
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

  function initPlanButtons(root) {
    const scope = root || document;
    scope.querySelectorAll('.btn-plan-select').forEach(button => {
      if (button.dataset.bbAttached) return;
      button.dataset.bbAttached = 'true';
      button.addEventListener('click', function () {
        const id = this.getAttribute('data-plan-id');
        const title = this.getAttribute('data-plan-title');
        const price = parseFloat(this.getAttribute('data-plan-price')) || 0;
        
        addItemToCart({
          id: id,
          title: title,
          price: price,
          type: id && id.startsWith('sub-') ? 'Subscription' : 'Coffee',
          frequency: id && id.startsWith('sub-') ? 'Monthly' : 'Single Purchase'
        });
      });
    });
  }

  function renderPlans(container) {
    if (!container) return;

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
        <button type="button" class="btn btn-primary btn-block btn-plan-select" data-plan-id="${plan.id}" data-plan-title="${plan.title}" data-plan-price="${plan.price}">Proceed</button>
      </div>
    `).join('');

    container.innerHTML = `<div class="plans-grid">${html}</div>`;
    initPlanButtons(container);
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

  // --- Checkout Page Logic ---
  function initCheckoutPage() {
    const form = document.getElementById('checkout-form');
    const errorBanner = document.getElementById('form-error-banner');
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

      const name = (document.getElementById('cust_name') || {}).value || '';
      const email = (document.getElementById('cust_email') || {}).value || '';
      const phone = (document.getElementById('cust_phone') || {}).value || '';
      const address = (document.getElementById('cust_address') || {}).value || '';
      const city = (document.getElementById('cust_city') || {}).value || '';
      const postal = (document.getElementById('cust_postal') || {}).value || '';
      const card = (document.getElementById('cust_card') || {}).value || '';

      if (!email.trim() || !email.includes('@') || !email.includes('.')) {
        if (errorBanner) {
          errorBanner.textContent = 'Error 422';
          errorBanner.style.display = 'block';
        }
        return;
      }

      if (!name.trim() || !phone.trim() || !address.trim() || !city.trim() || !postal.trim() || !card.trim()) {
        if (errorBanner) {
          errorBanner.textContent = 'Invalid input. Please try again.';
          errorBanner.style.display = 'block';
        }
        return;
      }

      // Successful order
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
          name: 'Coffee Lover',
          email: 'customer@example.com',
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

  // --- Newsletter Modal Implementation ---
  function initNewsletterModal() {
    const modal = document.getElementById('newsletter-modal');
    const closeBtn = document.getElementById('newsletter-modal-close');
    const form = document.getElementById('newsletter-modal-form');

    if (!modal) return;

    let timer = null;

    function openModal() {
      modal.style.display = 'flex';
    }

    function closeModal() {
      modal.style.display = 'none';
      if (timer) clearTimeout(timer);
      timer = setTimeout(openModal, 8000);
    }

    timer = setTimeout(openModal, 4000);

    if (closeBtn) {
      closeBtn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        closeModal();
      });
    }

    if (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        closeModal();
      });
    }
  }

  // --- Document Ready Handler ---
  function initApp() {
    updateCartBadge();
    initPlanButtons();
    initNewsletterModal();

    const pricingContainer = document.getElementById('pricing-plans-container');
    if (pricingContainer) {
      setTimeout(function () {
        renderPlans(pricingContainer);
      }, 5500);
    }

    initCartPage();
    initCheckoutPage();
    initThanksPage();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
  } else {
    initApp();
  }
})();
