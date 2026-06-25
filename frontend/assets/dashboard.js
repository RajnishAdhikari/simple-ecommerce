'use strict';

// Social media format definitions
const FORMATS = [
  { key: 'instagram_caption', label: '📸 Instagram' },
  { key: 'facebook_post',     label: 'f Facebook' },
  { key: 'whatsapp_message',  label: '💬 WhatsApp' },
  { key: 'short_video_script', label: '🎬 Video Script' },
  { key: 'hashtags',          label: '# Hashtags' },
];

const state = {
  apiKey:         sessionStorage.getItem('dash_key') || '',
  products:       [],
  categories:     ['All'],
  activeCategory: 'All',
  search:         '',
};

// -------------------------
// Utilities
// -------------------------

function esc(str) {
  return String(str == null ? '' : str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function money(price) {
  return '$' + Number(price).toFixed(2);
}

function showToast(msg, isError) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast ' + (isError ? 'toast-error' : 'toast-success');
  el.classList.remove('hidden');
  clearTimeout(el._t);
  el._t = setTimeout(function() { el.classList.add('hidden'); }, 3000);
}

function showScreen(name) {
  ['loginScreen', 'loadingScreen', 'dashboard'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.classList.toggle('hidden', id !== name);
  });
}

function getFormatContent(item, formatKey) {
  var val = item.social_content[formatKey];
  if (formatKey === 'hashtags') {
    return Array.isArray(val) ? val.join(' ') : String(val || '');
  }
  return String(val || '');
}

// -------------------------
// Login
// -------------------------

function showLogin(errorMsg) {
  showScreen('loginScreen');
  var errEl = document.getElementById('loginError');
  if (errorMsg) {
    errEl.textContent = errorMsg;
    errEl.classList.remove('hidden');
  } else {
    errEl.classList.add('hidden');
  }
  var input = document.getElementById('apiKeyInput');
  if (input) setTimeout(function() { input.focus(); }, 50);
}

function handleLogin() {
  var input = document.getElementById('apiKeyInput');
  var key = input.value.trim();
  if (!key) {
    var errEl = document.getElementById('loginError');
    errEl.textContent = 'Please enter your Admin API Key.';
    errEl.classList.remove('hidden');
    return;
  }
  state.apiKey = key;
  sessionStorage.setItem('dash_key', key);
  loadDashboard();
}

// -------------------------
// API fetch
// -------------------------

function apiFetch(path) {
  return fetch(path, {
    headers: { 'X-Admin-API-Key': state.apiKey },
  });
}

// -------------------------
// Dashboard loading
// -------------------------

function loadDashboard() {
  showScreen('loadingScreen');

  var url = '/api/admin/products/dashboard';
  apiFetch(url)
    .then(function(res) {
      if (res.status === 401 || res.status === 503) {
        state.apiKey = '';
        sessionStorage.removeItem('dash_key');
        showLogin('Invalid API key. Please try again.');
        return null;
      }
      if (!res.ok) {
        showScreen('dashboard');
        showToast('Failed to load products. Try refreshing.', true);
        return null;
      }
      return res.json();
    })
    .then(function(data) {
      if (!data) return;
      state.products = data.products || [];
      state.categories = ['All'].concat(data.categories || []);
      document.getElementById('productCount').textContent =
        data.total + ' product' + (data.total !== 1 ? 's' : '');
      showScreen('dashboard');
      renderCategories();
      renderProducts();
    })
    .catch(function() {
      showScreen('dashboard');
      showToast('Network error. Please try again.', true);
    });
}

// -------------------------
// Category bar
// -------------------------

function renderCategories() {
  var bar = document.getElementById('categoryBar');
  bar.innerHTML = state.categories.map(function(cat) {
    var active = cat === state.activeCategory ? ' active' : '';
    return '<button class="cat-btn' + active + '" data-cat="' + esc(cat) + '">' + esc(cat) + '</button>';
  }).join('');

  bar.querySelectorAll('.cat-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      state.activeCategory = btn.dataset.cat;
      bar.querySelectorAll('.cat-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.cat === state.activeCategory);
      });
      renderProducts();
    });
  });
}

// -------------------------
// Product list
// -------------------------

function getFiltered() {
  var q = state.search.trim().toLowerCase();
  return state.products.filter(function(item) {
    var p = item.product;
    var matchCat = state.activeCategory === 'All' || p.category === state.activeCategory;
    if (!matchCat) return false;
    if (!q) return true;
    return (
      p.name.toLowerCase().includes(q) ||
      p.brand.toLowerCase().includes(q) ||
      p.category.toLowerCase().includes(q) ||
      item.description.toLowerCase().includes(q)
    );
  });
}

function renderProducts() {
  var list  = document.getElementById('productList');
  var empty = document.getElementById('emptyState');
  var items = getFiltered();

  if (!items.length) {
    list.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');
  list.innerHTML = items.map(function(item, idx) {
    return buildCardHTML(item, idx);
  }).join('');

  // Attach interactive listeners to every card
  list.querySelectorAll('.product-card').forEach(function(card) {
    var idx  = parseInt(card.dataset.idx, 10);
    var item = items[idx];

    // Tab switching
    card.querySelectorAll('.tab-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var formatKey = btn.dataset.format;
        card.querySelectorAll('.tab-btn').forEach(function(b) {
          b.classList.toggle('active', b === btn);
        });
        card.querySelector('.content-text').textContent = getFormatContent(item, formatKey);
      });
    });

    // Image error fallback
    var img = card.querySelector('.card-image');
    if (img) {
      img.addEventListener('error', function() {
        img.style.background = '#f1f5f9';
        img.style.visibility = 'hidden';
      });
    }

    // Copy button
    card.querySelector('.copy-btn').addEventListener('click', function() {
      var btn  = card.querySelector('.copy-btn');
      var text = card.querySelector('.content-text').textContent;
      doCopy(text, btn);
    });
  });
}

function doCopy(text, btn) {
  function onSuccess() {
    btn.textContent = '✓ Copied!';
    btn.classList.add('copied');
    showToast('Copied to clipboard!');
    setTimeout(function() {
      btn.textContent = '📋 Copy';
      btn.classList.remove('copied');
    }, 2200);
  }

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(onSuccess).catch(function() {
      fallbackCopy(text, onSuccess);
    });
  } else {
    fallbackCopy(text, onSuccess);
  }
}

function fallbackCopy(text, onSuccess) {
  var ta = document.createElement('textarea');
  ta.value = text;
  ta.setAttribute('readonly', '');
  ta.style.position = 'fixed';
  ta.style.opacity  = '0';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); onSuccess(); } catch (e) { /* silent */ }
  document.body.removeChild(ta);
}

// -------------------------
// Card HTML builder
// -------------------------

function buildCardHTML(item, idx) {
  var p = item.product;
  var discount = (p.original_price > p.price)
    ? Math.round((1 - p.price / p.original_price) * 100)
    : 0;

  var badgesHTML = '';
  if (p.badge)   badgesHTML += '<span class="badge badge-label">' + esc(p.badge) + '</span>';
  if (p.is_new)  badgesHTML += '<span class="badge badge-new">NEW</span>';
  if (discount > 0) badgesHTML += '<span class="badge badge-sale">-' + discount + '%</span>';

  var defaultContent = getFormatContent(item, FORMATS[0].key);

  var tabsHTML = FORMATS.map(function(f, i) {
    return '<button class="tab-btn' + (i === 0 ? ' active' : '') +
      '" data-format="' + esc(f.key) + '">' + esc(f.label) + '</button>';
  }).join('');

  var colorsHTML = '';
  if (p.colors && p.colors.length) {
    colorsHTML = '<span class="meta-sep">·</span><span>' + esc(p.colors.slice(0,3).join(', ')) + '</span>';
  }

  return [
    '<article class="product-card" data-idx="' + idx + '">',
    '  <div class="card-left">',
    '    <img class="card-image" src="' + esc(p.image) + '" alt="' + esc(p.name) + '" loading="lazy" />',
    '    <div class="card-badges">' + badgesHTML + '</div>',
    '  </div>',
    '  <div class="card-right">',
    '    <div>',
    '      <h3 class="card-name">' + esc(p.name) + '</h3>',
    '      <div class="card-meta">',
    '        <span class="card-brand">' + esc(p.brand) + '</span>',
    '        <span class="meta-sep">·</span>',
    '        <span>' + esc(p.category) + '</span>',
    '        <span class="meta-sep">·</span>',
    '        <span class="card-rating"><span class="star">★</span> ' + p.rating.toFixed(1) + ' (' + p.reviews.toLocaleString() + ')</span>',
    colorsHTML,
    '      </div>',
    '      <div class="card-pricing">',
    '        <span class="card-price">' + money(p.price) + '</span>',
    (p.original_price > p.price
      ? '<span class="card-original">' + money(p.original_price) + '</span>' +
        '<span class="card-discount">-' + discount + '%</span>'
      : ''),
    '      </div>',
    '    </div>',

    '    <div class="desc-block">',
    '      <p class="desc-label">Product Description</p>',
    '      <p class="desc-text">' + esc(item.description) + '</p>',
    '    </div>',

    '    <div class="social-block">',
    '      <p class="social-label">Copy for Social Media</p>',
    '      <div class="tab-bar">' + tabsHTML + '</div>',
    '      <div class="content-box">',
    '        <pre class="content-text">' + esc(defaultContent) + '</pre>',
    '      </div>',
    '      <div class="copy-row">',
    '        <span class="copy-hint">Click a platform tab then copy the text</span>',
    '        <button class="copy-btn">📋 Copy</button>',
    '      </div>',
    '    </div>',
    '  </div>',
    '</article>',
  ].join('\n');
}

// -------------------------
// Init
// -------------------------

document.addEventListener('DOMContentLoaded', function() {
  // Login button
  document.getElementById('loginBtn').addEventListener('click', handleLogin);
  document.getElementById('apiKeyInput').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') handleLogin();
  });

  // Logout
  document.getElementById('logoutBtn').addEventListener('click', function() {
    state.apiKey = '';
    state.products = [];
    state.categories = ['All'];
    state.activeCategory = 'All';
    state.search = '';
    sessionStorage.removeItem('dash_key');
    document.getElementById('apiKeyInput').value = '';
    showLogin();
  });

  // Search input
  document.getElementById('dashSearch').addEventListener('input', function(e) {
    state.search = e.target.value;
    renderProducts();
  });

  // Clear search button
  document.getElementById('clearSearchBtn').addEventListener('click', function() {
    state.search = '';
    document.getElementById('dashSearch').value = '';
    renderProducts();
  });

  // Boot
  if (state.apiKey) {
    loadDashboard();
  } else {
    showLogin();
  }
});
