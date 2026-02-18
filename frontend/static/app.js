/**
 * Plombir Flowers — Mini App
 */

const API = '/api';
const LIMIT = 20;

let state = {
    categories: [],
    products: [],
    total: 0,
    offset: 0,
    categoryId: '',
    search: '',
    loading: false,
};

// ── Telegram WebApp ──
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready();
    tg.expand();
}

// ── DOM ──
const $categories = document.getElementById('categories');
const $products = document.getElementById('products');
const $loading = document.getElementById('loading');
const $loadMore = document.getElementById('load-more');
const $btnLoadMore = document.getElementById('btn-load-more');
const $search = document.getElementById('search');
const $modal = document.getElementById('modal');
const $modalContent = document.getElementById('modal-content');

// ── Init ──
async function init() {
    showLoading(true);
    await loadCategories();
    await loadProducts(true);
    showLoading(false);
}

// ── Categories ──
async function loadCategories() {
    try {
        const res = await fetch(`${API}/categories`);
        state.categories = await res.json();
        renderCategories();
    } catch (e) {
        console.error('Ошибка загрузки категорий:', e);
    }
}

function renderCategories() {
    let html = `<button class="category-btn active" data-id="">Все</button>`;
    for (const cat of state.categories) {
        html += `<button class="category-btn" data-id="${cat.id}">${cat.name}</button>`;
    }
    $categories.innerHTML = html;

    $categories.querySelectorAll('.category-btn').forEach(btn => {
        btn.addEventListener('click', () => onCategoryClick(btn));
    });
}

function onCategoryClick(btn) {
    $categories.querySelectorAll('.category-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.categoryId = btn.dataset.id;
    state.offset = 0;
    loadProducts(true);
}

// ── Products ──
async function loadProducts(reset = false) {
    if (state.loading) return;
    state.loading = true;

    if (reset) {
        state.offset = 0;
        $products.innerHTML = '';
    }

    showLoading(true);

    try {
        const params = new URLSearchParams({
            limit: LIMIT,
            offset: state.offset,
        });
        if (state.categoryId) params.set('category_id', state.categoryId);
        if (state.search) params.set('search', state.search);

        const res = await fetch(`${API}/products?${params}`);
        const data = await res.json();

        state.total = data.total;
        state.offset += data.items.length;

        if (reset) {
            state.products = data.items;
        } else {
            state.products = [...state.products, ...data.items];
        }

        renderProducts(data.items, reset);
        updateLoadMore();
    } catch (e) {
        console.error('Ошибка загрузки товаров:', e);
    }

    state.loading = false;
    showLoading(false);
}

function renderProducts(items, reset) {
    if (reset) $products.innerHTML = '';

    if (state.products.length === 0) {
        $products.innerHTML = '<div class="empty">Ничего не найдено 😔</div>';
        return;
    }

    for (const p of items) {
        const card = document.createElement('div');
        card.className = 'product-card';
        card.onclick = () => openProduct(p.id);

        let priceHtml = formatPrice(p.price);
        if (p.old_price) {
            priceHtml += `<span class="product-card__price--old">${formatPrice(p.old_price)}</span>`;
        }
        if (p.price_max && p.price_max !== p.price) {
            priceHtml += `<span class="product-card__price--range"> – ${formatPrice(p.price_max)}</span>`;
        }

        let badgeHtml = '';
        if (p.old_price) {
            const discount = Math.round((1 - p.price / p.old_price) * 100);
            badgeHtml = `<div class="product-card__badge">-${discount}%</div>`;
        }

        card.innerHTML = `
            <img class="product-card__img" src="${p.picture || ''}" alt="${p.name}" loading="lazy" />
            <div class="product-card__info">
                ${badgeHtml}
                <div class="product-card__name">${p.name}</div>
                <div class="product-card__price">${priceHtml}</div>
            </div>
        `;
        $products.appendChild(card);
    }
}

function updateLoadMore() {
    if (state.offset < state.total) {
        $loadMore.style.display = 'block';
    } else {
        $loadMore.style.display = 'none';
    }
}

// ── Product Detail ──
async function openProduct(id) {
    try {
        const res = await fetch(`${API}/products/${id}`);
        const p = await res.json();
        renderModal(p);
        $modal.classList.add('open');
        document.body.style.overflow = 'hidden';

        // Back button в Telegram
        if (tg) {
            tg.BackButton.show();
            tg.BackButton.onClick(closeModal);
        }
    } catch (e) {
        console.error('Ошибка загрузки товара:', e);
    }
}

function renderModal(p) {
    // Галерея
    let galleryHtml = '';
    let dotsHtml = '';
    for (let i = 0; i < p.pictures.length; i++) {
        galleryHtml += `<img src="${p.pictures[i]}" alt="${p.name}" loading="lazy" />`;
        dotsHtml += `<div class="modal__gallery-dot${i === 0 ? ' active' : ''}"></div>`;
    }

    // Цена
    let priceHtml = `<div class="modal__price">${formatPrice(p.price)}`;
    if (p.price_max && p.price_max !== p.price) {
        priceHtml += ` <span style="font-size:16px;color:var(--hint)">– ${formatPrice(p.price_max)}</span>`;
    }
    priceHtml += `</div>`;
    if (p.old_price) {
        priceHtml += `<div class="modal__old-price">${formatPrice(p.old_price)}</div>`;
    }

    // Варианты
    let variantsHtml = '';
    if (p.variants && p.variants.length > 0) {
        variantsHtml = `
            <div class="modal__variants">
                <div class="modal__variants-title">${p.variant_param || 'Вариант'}:</div>
                ${p.variants.map((v, i) => `
                    <button class="modal__variant-btn${i === 0 ? ' active' : ''}"
                            data-price="${v.price}"
                            data-old-price="${v.old_price || ''}"
                            onclick="selectVariant(this)">
                        ${v.label}${v.price !== p.price ? ' · ' + formatPrice(v.price) : ''}
                    </button>
                `).join('')}
            </div>
        `;
    }

    $modalContent.innerHTML = `
        <button class="modal__close" onclick="closeModal()">← Назад</button>
        <div class="modal__gallery" id="gallery">${galleryHtml}</div>
        ${p.pictures.length > 1 ? `<div class="modal__gallery-dots" id="gallery-dots">${dotsHtml}</div>` : ''}
        <div class="modal__body">
            <div class="modal__name">${p.name}</div>
            ${priceHtml}
            ${variantsHtml}
            ${p.description ? `<div class="modal__desc">${p.description}</div>` : ''}
            ${p.url ? `<a class="modal__link" href="${p.url}" target="_blank">Смотреть на сайте →</a>` : ''}
        </div>
    `;

    // Gallery scroll dots
    setupGalleryDots();
}

function selectVariant(btn) {
    btn.parentElement.querySelectorAll('.modal__variant-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    const price = parseFloat(btn.dataset.price);
    const oldPrice = btn.dataset.oldPrice ? parseFloat(btn.dataset.oldPrice) : null;

    const $price = $modalContent.querySelector('.modal__price');
    if ($price) $price.textContent = formatPrice(price);

    const $oldPrice = $modalContent.querySelector('.modal__old-price');
    if ($oldPrice) {
        $oldPrice.textContent = oldPrice ? formatPrice(oldPrice) : '';
    }
}

function closeModal() {
    $modal.classList.remove('open');
    document.body.style.overflow = '';
    if (tg) {
        tg.BackButton.hide();
        tg.BackButton.offClick(closeModal);
    }
}

function setupGalleryDots() {
    const gallery = document.getElementById('gallery');
    const dots = document.querySelectorAll('#gallery-dots .modal__gallery-dot');
    if (!gallery || dots.length === 0) return;

    gallery.addEventListener('scroll', () => {
        const idx = Math.round(gallery.scrollLeft / gallery.offsetWidth);
        dots.forEach((d, i) => d.classList.toggle('active', i === idx));
    });
}

// ── Search ──
let searchTimeout;
$search.addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        state.search = e.target.value.trim();
        loadProducts(true);
    }, 400);
});

// ── Load more ──
$btnLoadMore.addEventListener('click', () => loadProducts(false));

// ── Helpers ──
function formatPrice(price) {
    if (!price) return '';
    return new Intl.NumberFormat('ru-RU').format(Math.round(price)) + ' ₽';
}

function showLoading(show) {
    $loading.classList.toggle('visible', show);
}

// ── Start ──
init();
