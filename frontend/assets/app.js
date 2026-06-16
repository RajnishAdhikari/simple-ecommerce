const state = {
  token: "",
  user: null,
  products: [],
  recommendations: [],
  categories: [],
  banners: [],
  cart: { items: [], summary: { subtotal: 0, shipping: 0, total: 0, item_count: 0 } },
  query: "",
  sort: "trending",
  category: "All",
  slideIndex: 0,
  slideTimer: null,
  pendingProductId: null,
  searchController: null,
  suggestController: null,
  catalogCache: new Map(),
  sessionId: null,
};

const el = {
  ticker: document.getElementById("ticker"),
  searchInput: document.getElementById("searchInput"),
  searchSuggestions: document.getElementById("searchSuggestions"),
  sortSelect: document.getElementById("sortSelect"),
  categoryChips: document.getElementById("categoryChips"),
  productGrid: document.getElementById("productGrid"),
  productHeading: document.getElementById("productHeading"),
  resultCount: document.getElementById("resultCount"),
  recommendGrid: document.getElementById("recommendGrid"),
  recommendHeading: document.getElementById("recommendHeading"),
  recommendCount: document.getElementById("recommendCount"),
  heroSlides: document.getElementById("heroSlides"),
  cartCount: document.getElementById("cartCount"),
  cartItems: document.getElementById("cartItems"),
  subtotalValue: document.getElementById("subtotalValue"),
  shippingValue: document.getElementById("shippingValue"),
  totalValue: document.getElementById("totalValue"),
  addressInput: document.getElementById("addressInput"),
  authBtn: document.getElementById("authBtn"),
  cartBtn: document.getElementById("cartBtn"),
  cartDrawer: document.getElementById("cartDrawer"),
  closeCartBtn: document.getElementById("closeCartBtn"),
  authModal: document.getElementById("authModal"),
  closeAuthBtn: document.getElementById("closeAuthBtn"),
  overlay: document.getElementById("overlay"),
  loginTab: document.getElementById("loginTab"),
  registerTab: document.getElementById("registerTab"),
  loginForm: document.getElementById("loginForm"),
  registerForm: document.getElementById("registerForm"),
  quickViewModal: document.getElementById("quickViewModal"),
  quickViewBody: document.getElementById("quickViewBody"),
  closeQuickViewBtn: document.getElementById("closeQuickViewBtn"),
  checkoutBtn: document.getElementById("checkoutBtn"),
  toast: document.getElementById("toast"),
  mobileMenuBtn: document.getElementById("mobileMenuBtn"),
  mobileMenu: document.getElementById("mobileMenu"),
  mobileAuthBtn: document.getElementById("mobileAuthBtn"),
  mobileCartBtn: document.getElementById("mobileCartBtn"),
};

const heroBackgrounds = [
  "linear-gradient(120deg, #ff7a1a, #2eb8ff)",
  "linear-gradient(130deg, #0b87c9, #ff9f43)",
  "linear-gradient(130deg, #ff9f43, #1ea7e8)",
];

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function generateSessionId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID().replace(/-/g, "");
  }

  const random = Math.random().toString(36).slice(2);
  return `sess_${Date.now()}_${random}`;
}

function ensureSessionId() {
  let sessionId = sessionStorage.getItem("skycart_session_id");
  if (!sessionId || sessionId.length < 16) {
    sessionId = generateSessionId();
    sessionStorage.setItem("skycart_session_id", sessionId);
  }
  state.sessionId = sessionId;
}

function showToast(message, isError = false) {
  el.toast.textContent = message;
  el.toast.style.background = isError ? "#8f1f1f" : "#0f2740";
  el.toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => {
    el.toast.hidden = true;
  }, 2400);
}

function money(value) {
  return `$${Number(value || 0).toFixed(2)}`;
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    "X-Session-ID": state.sessionId,
    ...(options.headers || {}),
  };

  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }

  const response = await fetch(path, {
    ...options,
    headers,
    credentials: "same-origin",
  });

  if (response.status === 401 && (state.token || state.user)) {
    logout(true);
  }

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "Request failed");
  }

  return payload;
}

function openOverlay() {
  el.overlay.hidden = false;
}

function closeOverlayIfUnused() {
  const hasOpenPanel = [el.cartDrawer, el.authModal, el.quickViewModal].some((node) => node.classList.contains("open"));
  if (!hasOpenPanel) {
    el.overlay.hidden = true;
  }
}

function closeAllPanels() {
  el.cartDrawer.classList.remove("open");
  el.authModal.classList.remove("open");
  el.quickViewModal.classList.remove("open");
  closeOverlayIfUnused();
}

function openPanel(panel) {
  closeAllPanels();
  if (panel === "cart") {
    el.cartDrawer.classList.add("open");
  }
  if (panel === "auth") {
    el.authModal.classList.add("open");
  }
  if (panel === "quick") {
    el.quickViewModal.classList.add("open");
  }
  openOverlay();
}

function closePanel(panel) {
  if (panel === "cart") {
    el.cartDrawer.classList.remove("open");
  }
  if (panel === "auth") {
    el.authModal.classList.remove("open");
  }
  if (panel === "quick") {
    el.quickViewModal.classList.remove("open");
  }
  closeOverlayIfUnused();
}

function setAuthMode(mode) {
  const login = mode === "login";
  el.loginTab.classList.toggle("active", login);
  el.registerTab.classList.toggle("active", !login);
  el.loginForm.classList.toggle("hidden", !login);
  el.registerForm.classList.toggle("hidden", login);
}

function renderHero() {
  if (!state.banners.length) {
    el.heroSlides.innerHTML = "";
    return;
  }

  const slidesHtml = state.banners
    .map((banner, index) => {
      const active = index === state.slideIndex ? "active" : "";
      const bg = heroBackgrounds[index % heroBackgrounds.length];
      return `
        <article class="hero-slide ${active}" style="background:${bg}">
          <h2>${escapeHtml(banner.title)}</h2>
          <p>${escapeHtml(banner.subtitle)}</p>
          <button type="button">${escapeHtml(banner.cta)}</button>
        </article>
      `;
    })
    .join("");

  const dotsHtml = state.banners
    .map(
      (_, index) =>
        `<button class="hero-dot ${index === state.slideIndex ? "active" : ""}" data-slide="${index}" aria-label="Slide ${index + 1}"></button>`
    )
    .join("");

  el.heroSlides.innerHTML = `${slidesHtml}<div class="hero-dots">${dotsHtml}</div>`;
}

function startHeroRotation() {
  if (state.slideTimer) {
    clearInterval(state.slideTimer);
  }

  state.slideTimer = setInterval(() => {
    if (!state.banners.length) {
      return;
    }
    state.slideIndex = (state.slideIndex + 1) % state.banners.length;
    renderHero();
  }, 4200);
}

function renderCategoryChips() {
  const chips = state.categories
    .map(
      (item) =>
        `<button class="chip ${state.category === item.name ? "active" : ""}" data-category="${escapeHtml(item.name)}">${escapeHtml(item.name)} (${Number(item.count || 0)})</button>`
    )
    .join("");

  el.categoryChips.innerHTML = chips;
}

function productCardTemplate(product) {
  return `
    <article class="product-card" data-product-id="${Number(product.id)}">
      <div class="card-media">
        <img src="${escapeHtml(product.image)}" alt="${escapeHtml(product.name)}" loading="lazy" />
        <span class="badge">${escapeHtml(product.badge)}</span>
      </div>
      <div class="card-body">
        <p class="brand-line">${escapeHtml(product.brand)}</p>
        <p class="name-line">${escapeHtml(product.name)}</p>
        <p class="rating-line">* ${Number(product.rating).toFixed(1)} (${Number(product.reviews)})</p>
        <div class="price-line">
          <span class="price">${money(product.price)}</span>
          <span class="old-price">${money(product.original_price)}</span>
        </div>
        <div class="card-actions">
          <button type="button" data-action="quick-view" data-id="${Number(product.id)}">Quick View</button>
          <button type="button" class="quick-add-btn" data-action="add" data-id="${Number(product.id)}">Add</button>
        </div>
      </div>
    </article>
  `;
}

function recommendationCardTemplate(product) {
  return `
    <article class="recommend-card">
      <img src="${escapeHtml(product.image)}" alt="${escapeHtml(product.name)}" loading="lazy" />
      <h4>${escapeHtml(product.name)}</h4>
      <p>${escapeHtml(product.brand)} | ${escapeHtml(product.category)}</p>
      <p><strong>${money(product.price)}</strong> <span class="old-price">${money(product.original_price)}</span></p>
      <button type="button" data-action="recommend-quick-view" data-id="${Number(product.id)}">View</button>
    </article>
  `;
}

function sortProductsLocal(items, sort) {
  const copy = [...items];
  if (sort === "price_asc") {
    return copy.sort((a, b) => a.price - b.price);
  }
  if (sort === "price_desc") {
    return copy.sort((a, b) => b.price - a.price);
  }
  if (sort === "rating") {
    return copy.sort((a, b) => b.rating - a.rating);
  }
  if (sort === "newest") {
    return copy.sort((a, b) => Number(b.is_new) - Number(a.is_new) || b.id - a.id);
  }
  return copy;
}

function renderProducts() {
  if (!state.products.length) {
    el.productGrid.innerHTML = `<div class="empty-state">No products matched your filter. Try another keyword.</div>`;
  } else {
    el.productGrid.innerHTML = state.products.map(productCardTemplate).join("");
  }

  el.resultCount.textContent = `${state.products.length} products`;

  if (state.query.trim()) {
    el.productHeading.textContent = `Search: ${state.query.trim()}`;
  } else if (state.category === "All") {
    el.productHeading.textContent = "Trending Picks";
  } else {
    el.productHeading.textContent = `${state.category} Collection`;
  }
}

function renderRecommendations() {
  if (!state.recommendations.length) {
    el.recommendGrid.innerHTML = `<div class="empty-state">Recommendations will appear as you browse.</div>`;
  } else {
    el.recommendGrid.innerHTML = state.recommendations.map(recommendationCardTemplate).join("");
  }

  el.recommendCount.textContent = `${state.recommendations.length} products`;
  el.recommendHeading.textContent = state.user ? "Recommended For You" : "Recommended Now";
}

function renderSuggestions(products, query) {
  const normalizedQuery = query.trim();
  if (!normalizedQuery || !products.length) {
    el.searchSuggestions.classList.add("hidden");
    el.searchSuggestions.innerHTML = "";
    return;
  }

  el.searchSuggestions.innerHTML = products
    .slice(0, 6)
    .map(
      (product) => `
        <button class="suggestion-item" type="button" data-id="${Number(product.id)}">
          <div>
            <strong>${escapeHtml(product.name)}</strong>
            <span>${escapeHtml(product.brand)} | ${escapeHtml(product.category)}</span>
          </div>
          <strong>${money(product.price)}</strong>
        </button>
      `
    )
    .join("");
  el.searchSuggestions.classList.remove("hidden");
}

function hideSuggestions() {
  el.searchSuggestions.classList.add("hidden");
}

function renderCart() {
  const { items, summary } = state.cart;

  if (!items.length) {
    el.cartItems.innerHTML = `<div class="empty-state">Your cart is empty.</div>`;
  } else {
    el.cartItems.innerHTML = items
      .map(
        (item) => `
          <article class="cart-item" data-product-id="${Number(item.product_id)}">
            <img src="${escapeHtml(item.image)}" alt="${escapeHtml(item.name)}" />
            <div class="cart-meta">
              <h4>${escapeHtml(item.name)}</h4>
              <p>${money(item.price)} x ${Number(item.quantity)}</p>
              <p>${escapeHtml(item.size || "Default")} / ${escapeHtml(item.color || "Default")}</p>
              <div class="qty-wrap">
                <button type="button" data-action="minus" data-id="${Number(item.product_id)}">-</button>
                <span>${Number(item.quantity)}</span>
                <button type="button" data-action="plus" data-id="${Number(item.product_id)}">+</button>
                <button type="button" data-action="remove" data-id="${Number(item.product_id)}">Remove</button>
              </div>
            </div>
            <strong>${money(item.line_total)}</strong>
          </article>
        `
      )
      .join("");
  }

  el.cartCount.textContent = String(summary.item_count || 0);
  el.subtotalValue.textContent = money(summary.subtotal);
  el.shippingValue.textContent = money(summary.shipping);
  el.totalValue.textContent = money(summary.total);
}

function getCatalogCacheKey() {
  return `${state.query.trim().toLowerCase()}|${state.category.toLowerCase()}|${state.sort.toLowerCase()}`;
}

function getCachedCatalog() {
  const key = getCatalogCacheKey();
  const entry = state.catalogCache.get(key);
  if (!entry) {
    return null;
  }

  if (Date.now() - entry.ts > 120000) {
    state.catalogCache.delete(key);
    return null;
  }

  return entry.payload;
}

function setCatalogCache(products) {
  const key = getCatalogCacheKey();
  state.catalogCache.set(key, {
    ts: Date.now(),
    payload: products,
  });

  if (state.catalogCache.size > 90) {
    const oldestKey = state.catalogCache.keys().next().value;
    state.catalogCache.delete(oldestKey);
  }
}

async function loadCatalog() {
  const cached = getCachedCatalog();
  if (cached) {
    state.products = cached;
    renderProducts();
    renderSuggestions(cached, state.query);
    return;
  }

  let products = [];

  if (state.query.trim()) {
    if (state.searchController) {
      state.searchController.abort();
    }

    state.searchController = new AbortController();
    const params = new URLSearchParams({
      q: state.query.trim(),
      limit: "40",
    });
    if (state.category !== "All") {
      params.set("category", state.category);
    }

    const data = await api(`/api/products/search?${params.toString()}`, {
      signal: state.searchController.signal,
    });

    products = state.sort === "relevance" ? data.products || [] : sortProductsLocal(data.products || [], state.sort);
  } else {
    const params = new URLSearchParams({ sort: state.sort });
    if (state.category !== "All") {
      params.set("category", state.category);
    }

    const data = await api(`/api/products?${params.toString()}`);
    products = data.products || [];
  }

  state.products = products;
  setCatalogCache(products);
  renderProducts();
  renderSuggestions(products, state.query);
}

async function loadSearchSuggestions() {
  const query = state.query.trim();
  if (!query) {
    hideSuggestions();
    return;
  }

  if (state.suggestController) {
    state.suggestController.abort();
  }

  state.suggestController = new AbortController();

  const params = new URLSearchParams({
    q: query,
    limit: "6",
  });
  if (state.category !== "All") {
    params.set("category", state.category);
  }

  try {
    const data = await api(`/api/products/search?${params.toString()}`, {
      signal: state.suggestController.signal,
    });
    renderSuggestions(data.products || [], query);
  } catch (error) {
    if (error.name !== "AbortError") {
      hideSuggestions();
    }
  }
}

async function loadRecommendations(contextProductId = null) {
  const params = new URLSearchParams({ limit: "8" });
  if (contextProductId) {
    params.set("context_product_id", String(contextProductId));
  }

  try {
    const data = await api(`/api/recommendations?${params.toString()}`);
    state.recommendations = data.products || [];
    renderRecommendations();
  } catch (error) {
    state.recommendations = [];
    renderRecommendations();
    if (error.message && !error.message.includes("Session id")) {
      showToast(error.message, true);
    }
  }
}

async function trackView(productId) {
  try {
    await api("/api/recommendations/track-view", {
      method: "POST",
      body: JSON.stringify({ product_id: productId }),
    });
  } catch {
    // Keep browsing experience uninterrupted on analytics failure.
  }
}

async function loadCategories() {
  const data = await api("/api/categories");
  state.categories = data.categories || [];
  renderCategoryChips();
}

async function loadHeroBanners() {
  const data = await api("/api/hero-banners");
  state.banners = data.banners || [];
  renderHero();
  startHeroRotation();
}

async function fetchMe() {
  try {
    const user = await api("/api/users/me");
    state.user = user;
    el.authBtn.textContent = `Hi, ${user.username}`;
  } catch {
    logout(true);
  }
}

function logout(silent = false) {
  state.token = "";
  state.user = null;
  fetch("/api/auth/logout", {
    method: "POST",
    credentials: "same-origin",
  }).catch(() => {});
  state.cart = { items: [], summary: { subtotal: 0, shipping: 0, total: 0, item_count: 0 } };
  renderCart();
  el.authBtn.textContent = "Sign In";
  loadRecommendations();
  if (!silent) {
    showToast("You are logged out.");
  }
}

async function loadCart() {
  if (!state.user) {
    state.cart = { items: [], summary: { subtotal: 0, shipping: 0, total: 0, item_count: 0 } };
    renderCart();
    return;
  }

  const data = await api("/api/cart");
  state.cart = data;
  renderCart();
}

async function addToCart(productId) {
  if (!state.user) {
    state.pendingProductId = productId;
    setAuthMode("login");
    openPanel("auth");
    showToast("Login required to add items.", true);
    return;
  }

  const product = state.products.find((item) => item.id === productId) || state.recommendations.find((item) => item.id === productId);
  await api("/api/cart/items", {
    method: "POST",
    body: JSON.stringify({
      product_id: productId,
      quantity: 1,
      size: product?.sizes?.[0] || null,
      color: product?.colors?.[0] || null,
    }),
  });

  await loadCart();
  await loadRecommendations(productId);
  showToast("Added to cart.");
}

async function updateCartQuantity(productId, direction) {
  const item = state.cart.items.find((entry) => entry.product_id === productId);
  if (!item) {
    return;
  }

  const targetQty = Math.max(1, Math.min(20, item.quantity + direction));
  await api(`/api/cart/items/${productId}`, {
    method: "PATCH",
    body: JSON.stringify({ quantity: targetQty }),
  });
  await loadCart();
  await loadRecommendations(productId);
}

async function removeFromCart(productId) {
  await api(`/api/cart/items/${productId}`, {
    method: "DELETE",
  });
  await loadCart();
  await loadRecommendations();
}

async function checkout() {
  const address = el.addressInput.value.trim();
  if (!address) {
    showToast("Please enter shipping address.", true);
    return;
  }

  if (!state.cart.items.length) {
    showToast("Your cart is empty.", true);
    return;
  }

  const data = await api("/api/checkout", {
    method: "POST",
    body: JSON.stringify({ shipping_address: address }),
  });

  el.addressInput.value = "";
  await loadCart();
  await loadRecommendations();
  closePanel("cart");
  showToast(`Order #${data.order.order_id} confirmed.`);
}

async function openQuickView(productId) {
  const product = await api(`/api/products/${productId}`);
  const sizes = (product.sizes || []).map((size) => `<span>${escapeHtml(size)}</span>`).join("");
  const colors = (product.colors || []).map((color) => `<span>${escapeHtml(color)}</span>`).join("");

  el.quickViewBody.innerHTML = `
    <img src="${escapeHtml(product.image)}" alt="${escapeHtml(product.name)}" />
    <h4>${escapeHtml(product.name)}</h4>
    <p>${escapeHtml(product.description)}</p>
    <p><strong>${money(product.price)}</strong> <span class="old-price">${money(product.original_price)}</span></p>
    <div class="inline-tags">${sizes}</div>
    <div class="inline-tags">${colors}</div>
    <button class="quick-add-btn" type="button" data-action="quick-add" data-id="${Number(product.id)}">Add To Cart</button>
  `;

  openPanel("quick");
  await trackView(productId);
  await loadRecommendations(productId);
}

function debounce(fn, delay = 250) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

async function handleAuthSubmit(event, mode) {
  event.preventDefault();

  const formData = new FormData(event.currentTarget);
  const payload = Object.fromEntries(formData.entries());

  try {
    const data = await api(`/api/auth/${mode}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });

    state.user = data.user;
    el.authBtn.textContent = `Hi, ${data.user.username}`;

    await loadCart();
    await loadRecommendations();
    closePanel("auth");
    showToast(mode === "login" ? "Welcome back." : "Account created.");

    if (state.pendingProductId) {
      const pending = state.pendingProductId;
      state.pendingProductId = null;
      await addToCart(pending);
    }
  } catch (error) {
    showToast(error.message, true);
  }
}

function bindEvents() {
  el.searchInput.addEventListener(
    "input",
    debounce(async (event) => {
      state.query = event.target.value.slice(0, 80);
      try {
        await Promise.all([loadCatalog(), loadSearchSuggestions()]);
      } catch (error) {
        if (error.name !== "AbortError") {
          showToast(error.message, true);
        }
      }
    }, 140)
  );

  el.searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      hideSuggestions();
    }
  });

  el.sortSelect.addEventListener("change", async (event) => {
    state.sort = event.target.value;
    try {
      await loadCatalog();
    } catch (error) {
      showToast(error.message, true);
    }
  });

  el.categoryChips.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-category]");
    if (!button) {
      return;
    }

    state.category = button.dataset.category;
    renderCategoryChips();
    hideSuggestions();
    try {
      await loadCatalog();
    } catch (error) {
      showToast(error.message, true);
    }
  });

  el.searchSuggestions.addEventListener("click", async (event) => {
    const item = event.target.closest("button[data-id]");
    if (!item) {
      return;
    }

    const productId = Number(item.dataset.id);
    hideSuggestions();
    try {
      await openQuickView(productId);
    } catch (error) {
      showToast(error.message, true);
    }
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".search-wrap")) {
      hideSuggestions();
    }
  });

  el.productGrid.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) {
      return;
    }

    const action = button.dataset.action;
    const productId = Number(button.dataset.id);

    try {
      if (action === "add") {
        await addToCart(productId);
      }
      if (action === "quick-view") {
        await openQuickView(productId);
      }
    } catch (error) {
      showToast(error.message, true);
    }
  });

  el.recommendGrid.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action='recommend-quick-view']");
    if (!button) {
      return;
    }

    try {
      await openQuickView(Number(button.dataset.id));
    } catch (error) {
      showToast(error.message, true);
    }
  });

  el.quickViewBody.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action='quick-add']");
    if (!button) {
      return;
    }

    try {
      await addToCart(Number(button.dataset.id));
      closePanel("quick");
    } catch (error) {
      showToast(error.message, true);
    }
  });

  el.cartItems.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) {
      return;
    }

    const action = button.dataset.action;
    const id = Number(button.dataset.id);

    try {
      if (action === "plus") {
        await updateCartQuantity(id, 1);
      }
      if (action === "minus") {
        await updateCartQuantity(id, -1);
      }
      if (action === "remove") {
        await removeFromCart(id);
      }
    } catch (error) {
      showToast(error.message, true);
    }
  });

  el.authBtn.addEventListener("click", () => {
    if (state.user) {
      logout();
      return;
    }
    setAuthMode("login");
    openPanel("auth");
  });

  el.cartBtn.addEventListener("click", () => {
    if (!state.user) {
      setAuthMode("login");
      openPanel("auth");
      showToast("Login to access cart.", true);
      return;
    }
    openPanel("cart");
  });

  el.checkoutBtn.addEventListener("click", async () => {
    try {
      await checkout();
    } catch (error) {
      showToast(error.message, true);
    }
  });

  el.loginTab.addEventListener("click", () => setAuthMode("login"));
  el.registerTab.addEventListener("click", () => setAuthMode("register"));
  el.loginForm.addEventListener("submit", (event) => handleAuthSubmit(event, "login"));
  el.registerForm.addEventListener("submit", (event) => handleAuthSubmit(event, "register"));

  el.closeCartBtn.addEventListener("click", () => closePanel("cart"));
  el.closeAuthBtn.addEventListener("click", () => closePanel("auth"));
  el.closeQuickViewBtn.addEventListener("click", () => closePanel("quick"));
  el.overlay.addEventListener("click", closeAllPanels);

  el.heroSlides.addEventListener("click", (event) => {
    const dot = event.target.closest("button[data-slide]");
    if (!dot) {
      return;
    }
    state.slideIndex = Number(dot.dataset.slide);
    renderHero();
    startHeroRotation();
  });

  el.mobileMenuBtn.addEventListener("click", () => {
    el.mobileMenu.classList.toggle("hidden");
  });

  el.mobileAuthBtn.addEventListener("click", () => {
    setAuthMode("login");
    openPanel("auth");
    el.mobileMenu.classList.add("hidden");
  });

  el.mobileCartBtn.addEventListener("click", () => {
    if (state.user) {
      openPanel("cart");
    } else {
      setAuthMode("login");
      openPanel("auth");
      showToast("Login to access cart.", true);
    }
    el.mobileMenu.classList.add("hidden");
  });
}

async function init() {
  ensureSessionId();
  el.ticker.innerHTML = "<span>SPRING FLASH SALE 2026 | FREE SHIPPING ABOVE $99 | DAILY NEW DROPS | ORANGE + SKY COLLECTION LIVE NOW</span>";
  bindEvents();
  setAuthMode("login");

  try {
    await Promise.all([loadHeroBanners(), loadCategories(), loadCatalog(), loadRecommendations()]);
    await fetchMe();
    await loadCart();
    await loadRecommendations();
  } catch (error) {
    showToast(error.message || "Failed to load app", true);
  }
}

init();
