/**
 * Plombir Flowers — Mini App (Sprint 2)
 * Каталог + Корзина + Оформление заказа + Фильтр цен
 * Стилистика адаптирована под plombirflowers.ru
 */

const API = '/api';
const LIMIT = 20;

// ── State ──
let state = {
    categories: [],
    products: [],
    total: 0,
    offset: 0,
    categoryId: '',
    priceMin: null,
    priceMax: null,
    search: '',
    loading: false,
    currentScreen: 'catalog',  // catalog | product | cart | order | success
    currentProduct: null,
    selectedVariant: null,
};

// ── Cart (localStorage) ──
function getCart() {
    try {
        return JSON.parse(localStorage.getItem('plombir_cart') || '[]');
    } catch { return []; }
}

function saveCart(cart) {
    localStorage.setItem('plombir_cart', JSON.stringify(cart));
    updateCartBadge();
}

function addToCart(item) {
    const cart = getCart();
    const key = item.variant_id ? `${item.product_id}_${item.variant_id}` : item.product_id;
    const existing = cart.find(c => {
        const k = c.variant_id ? `${c.product_id}_${c.variant_id}` : c.product_id;
        return k === key;
    });

    if (existing) {
        existing.quantity += item.quantity;
    } else {
        cart.push({ ...item, quantity: item.quantity || 1 });
    }
    saveCart(cart);
}

function removeFromCart(index) {
    const cart = getCart();
    cart.splice(index, 1);
    saveCart(cart);
}

function updateCartQuantity(index, delta) {
    const cart = getCart();
    cart[index].quantity += delta;
    if (cart[index].quantity <= 0) {
        cart.splice(index, 1);
    }
    saveCart(cart);
}

function getCartTotal() {
    return getCart().reduce((sum, item) => sum + item.price * item.quantity, 0);
}

function getCartCount() {
    return getCart().reduce((sum, item) => sum + item.quantity, 0);
}

function updateCartBadge() {
    const count = getCartCount();
    const $badge = document.getElementById('cart-badge');
    const $cartBtn = document.getElementById('btn-cart');
    if (count > 0) {
        const changed = $badge.textContent !== String(count);
        $badge.textContent = count;
        $badge.style.display = 'flex';
        // Bounce animation
        if (changed) {
            $badge.classList.remove('bounce');
            $cartBtn.classList.remove('pulse');
            void $badge.offsetWidth; // reflow trick
            $badge.classList.add('bounce');
            $cartBtn.classList.add('pulse');
            setTimeout(() => {
                $badge.classList.remove('bounce');
                $cartBtn.classList.remove('pulse');
            }, 500);
        }
    } else {
        $badge.style.display = 'none';
    }
}

// ── Telegram WebApp ──
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready();
    tg.expand();
    // Ставим цвета хедера под стиль Mini App
    tg.setHeaderColor('#ffffff');
    tg.setBackgroundColor('#ffffff');
}

// ── Header scroll shadow ──
const $header = document.querySelector('.header');
window.addEventListener('scroll', () => {
    if (window.scrollY > 10) {
        $header.classList.add('header--scrolled');
    } else {
        $header.classList.remove('header--scrolled');
    }
}, { passive: true });

// ── Navigation ──
function showScreen(name) {
    document.querySelectorAll('.screen').forEach(s => {
        s.style.display = 'none';
        s.classList.remove('screen-enter');
    });
    const target = document.getElementById(`screen-${name}`);
    target.style.display = 'block';
    target.classList.add('screen-enter');
    state.currentScreen = name;

    // Telegram back button
    if (tg) {
        if (name === 'catalog') {
            tg.BackButton.hide();
        } else {
            tg.BackButton.show();
        }
    }

    // Scroll to top
    if (name !== 'catalog') {
        window.scrollTo(0, 0);
    }
}

function goBack() {
    if (state.currentScreen === 'product') showScreen('catalog');
    else if (state.currentScreen === 'cart') showScreen('catalog');
    else if (state.currentScreen === 'order') showScreen('cart');
    else if (state.currentScreen === 'success') showScreen('catalog');
    else showScreen('catalog');
}

// Telegram BackButton
if (tg) {
    tg.BackButton.onClick(goBack);
}

// ── DOM ──
const $categories = document.getElementById('categories');
const $products = document.getElementById('products');
const $loading = document.getElementById('loading');
const $loadMore = document.getElementById('load-more');
const $btnLoadMore = document.getElementById('btn-load-more');
const $search = document.getElementById('search');
const $screenProduct = document.getElementById('screen-product');
const $screenCart = document.getElementById('screen-cart');
const $screenOrder = document.getElementById('screen-order');
const $screenSuccess = document.getElementById('screen-success');

// ── Init ──
async function init() {
    await loadCategories();
    await loadProducts(true);
    updateCartBadge();
    setupPriceFilter();
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

// ── Price Filter ──
function setupPriceFilter() {
    document.querySelectorAll('.price-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.price-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.priceMin = btn.dataset.min ? parseFloat(btn.dataset.min) : null;
            state.priceMax = btn.dataset.max ? parseFloat(btn.dataset.max) : null;
            state.offset = 0;
            loadProducts(true);
        });
    });
}

// ── Skeleton cards ──
function showSkeletons(count = 4) {
    for (let i = 0; i < count; i++) {
        const sk = document.createElement('div');
        sk.className = 'skeleton-card';
        sk.innerHTML = `
            <div class="skeleton-card__img"></div>
            <div class="skeleton-card__info">
                <div class="skeleton-card__line skeleton-card__line--title"></div>
                <div class="skeleton-card__line skeleton-card__line--price"></div>
            </div>
        `;
        $products.appendChild(sk);
    }
}

function removeSkeletons() {
    $products.querySelectorAll('.skeleton-card').forEach(sk => sk.remove());
}

// ── Products ──
async function loadProducts(reset = false) {
    if (state.loading) return;
    state.loading = true;

    if (reset) {
        state.offset = 0;
        $products.innerHTML = '';
    }

    // Показываем скелетоны
    if (reset) {
        showSkeletons(LIMIT);
    } else {
        // Скрываем кнопку «Загрузить ещё» и показываем скелетоны внизу грида
        $loadMore.style.display = 'none';
        showSkeletons(LIMIT);
    }

    try {
        const params = new URLSearchParams({
            limit: LIMIT,
            offset: state.offset,
        });
        if (state.categoryId) params.set('category_id', state.categoryId);
        if (state.priceMin !== null) params.set('price_min', state.priceMin);
        if (state.priceMax !== null) params.set('price_max', state.priceMax);
        if (state.search) params.set('search', state.search);

        // Запрос + минимальная задержка, чтобы скелетоны были видны
        const [res] = await Promise.all([
            fetch(`${API}/products?${params}`),
            new Promise(r => setTimeout(r, 800)),
        ]);
        const data = await res.json();

        state.total = data.total;
        state.offset += data.items.length;

        if (reset) {
            state.products = data.items;
        } else {
            state.products = [...state.products, ...data.items];
        }

        removeSkeletons();
        renderProducts(data.items, reset);
        updateLoadMore();
    } catch (e) {
        console.error('Ошибка загрузки товаров:', e);
        removeSkeletons();
    }

    state.loading = false;
    showLoading(false);
}

function renderProducts(items, reset) {
    if (reset) {
        $products.innerHTML = '';
    }
    _renderCards(items);
}

function _renderCards(items) {
    if (state.products.length === 0) {
        $products.innerHTML = '<div class="empty">Ничего не найдено</div>';
        return;
    }

    const startIdx = $products.children.length;

    for (let i = 0; i < items.length; i++) {
        const p = items[i];
        const card = document.createElement('div');
        card.className = 'product-card animate-in';
        card.style.setProperty('--appear-delay', `${(startIdx + i) * 0.05}s`);
        card.onclick = () => openProduct(p.id);

        // Price
        let priceHtml = formatPrice(p.price);
        if (p.old_price) {
            priceHtml += `<span class="product-card__price--old">${formatPrice(p.old_price)}</span>`;
        }
        if (p.price_max && p.price_max !== p.price) {
            priceHtml += `<span class="product-card__price--range"> – ${formatPrice(p.price_max)}</span>`;
        }

        // Badge (discount or "ХИТ" style)
        let badgeHtml = '';
        if (p.old_price) {
            const discount = Math.round((1 - p.price / p.old_price) * 100);
            badgeHtml = `<div class="product-card__badge">-${discount}%</div>`;
        }

        card.innerHTML = `
            ${badgeHtml}
            <img class="product-card__img" src="${p.picture || ''}" alt="${p.name}" loading="lazy" />
            <div class="product-card__info">
                <div class="product-card__name">${p.name}</div>
                <div class="product-card__price">${priceHtml}</div>
            </div>
        `;
        $products.appendChild(card);

        // Image fade-in on load
        const img = card.querySelector('.product-card__img');
        if (img.complete) {
            img.classList.add('loaded');
        } else {
            img.addEventListener('load', () => img.classList.add('loaded'));
            img.addEventListener('error', () => img.classList.add('loaded'));
        }
    }
}

function updateLoadMore() {
    $loadMore.style.display = state.offset < state.total ? 'block' : 'none';
}

// ══════════════════════════════════════════════
// ══ PRODUCT DETAIL
// ══════════════════════════════════════════════
async function openProduct(id) {
    try {
        const res = await fetch(`${API}/products/${id}`);
        const p = await res.json();
        state.currentProduct = p;

        // Default variant
        if (p.variants && p.variants.length > 0) {
            state.selectedVariant = p.variants[0];
        } else {
            state.selectedVariant = null;
        }

        renderProductScreen(p);
        showScreen('product');
    } catch (e) {
        console.error('Ошибка загрузки товара:', e);
    }
}

function renderProductScreen(p) {
    // Gallery
    let galleryHtml = '';
    let dotsHtml = '';
    for (let i = 0; i < p.pictures.length; i++) {
        galleryHtml += `<img src="${p.pictures[i]}" alt="${p.name}" loading="lazy" />`;
        dotsHtml += `<div class="gallery-dot${i === 0 ? ' active' : ''}"></div>`;
    }

    // Price
    const currentPrice = state.selectedVariant ? state.selectedVariant.price : p.price;
    const currentOldPrice = state.selectedVariant ? state.selectedVariant.old_price : p.old_price;

    // Variants
    let variantsHtml = '';
    if (p.variants && p.variants.length > 0) {
        variantsHtml = `
            <div class="detail__variants">
                <div class="detail__variants-title">${p.variant_param || 'Вариант'}:</div>
                <div class="detail__variants-list">
                    ${p.variants.map((v, i) => `
                        <button class="detail__variant-btn${i === 0 ? ' active' : ''}"
                                data-index="${i}"
                                onclick="selectVariant(${i})">
                            ${v.label}${v.price !== p.price ? ' · ' + formatPrice(v.price) : ''}
                        </button>
                    `).join('')}
                </div>
            </div>
        `;
    }

    $screenProduct.innerHTML = `
        <div class="detail">
            <button class="detail__back" onclick="showScreen('catalog')">← Назад</button>
            <div class="detail__gallery" id="detail-gallery">${galleryHtml}</div>
            ${p.pictures.length > 1 ? `<div class="detail__gallery-dots" id="detail-dots">${dotsHtml}</div>` : ''}
            <div class="detail__body">
                <div class="detail__name">${p.name}</div>
                <div class="detail__price-block">
                    <span class="detail__price" id="detail-price">${formatPrice(currentPrice)}</span>
                    ${currentOldPrice ? `<span class="detail__old-price" id="detail-old-price">${formatPrice(currentOldPrice)}</span>` : '<span class="detail__old-price" id="detail-old-price"></span>'}
                </div>
                ${variantsHtml}
                <button class="btn-primary detail__add-to-cart" onclick="addCurrentToCart()">
                    В корзину
                </button>
                <button class="btn-secondary" onclick="showScreen('catalog')" style="margin-top:8px;">
                    Подробнее на сайте
                </button>
                ${p.description ? `<div class="detail__desc">${p.description}</div>` : ''}
            </div>
        </div>
    `;

    // Gallery scroll dots
    setupDetailGallery();

    // Image fade-in for gallery
    $screenProduct.querySelectorAll('.detail__gallery img').forEach(img => {
        if (img.complete) img.classList.add('loaded');
        else {
            img.addEventListener('load', () => img.classList.add('loaded'));
            img.addEventListener('error', () => img.classList.add('loaded'));
        }
    });
}

function selectVariant(index) {
    const p = state.currentProduct;
    if (!p || !p.variants[index]) return;

    state.selectedVariant = p.variants[index];

    // Update buttons
    document.querySelectorAll('.detail__variant-btn').forEach((btn, i) => {
        btn.classList.toggle('active', i === index);
    });

    // Update price
    const $price = document.getElementById('detail-price');
    const $oldPrice = document.getElementById('detail-old-price');
    if ($price) $price.textContent = formatPrice(state.selectedVariant.price);
    if ($oldPrice) $oldPrice.textContent = state.selectedVariant.old_price ? formatPrice(state.selectedVariant.old_price) : '';
}

function addCurrentToCart() {
    const p = state.currentProduct;
    if (!p) return;

    const v = state.selectedVariant;
    const item = {
        product_id: p.id,
        variant_id: v ? v.id : null,
        name: p.name,
        variant_label: v ? v.label : null,
        price: v ? v.price : p.price,
        quantity: 1,
        picture: p.pictures[0] || null,
    };

    addToCart(item);

    // Button visual feedback
    const btn = document.querySelector('.detail__add-to-cart');
    if (btn) {
        btn.classList.add('btn-added');
        btn.textContent = '✓ Добавлено';
        setTimeout(() => {
            btn.classList.remove('btn-added');
            btn.textContent = 'В корзину';
        }, 1200);
    }

    // Haptic feedback in Telegram
    if (tg && tg.HapticFeedback) {
        tg.HapticFeedback.impactOccurred('light');
    }

    showToast('Добавлено в корзину');
}

function setupDetailGallery() {
    const gallery = document.getElementById('detail-gallery');
    const dots = document.querySelectorAll('#detail-dots .gallery-dot');
    if (!gallery || dots.length === 0) return;

    gallery.addEventListener('scroll', () => {
        const idx = Math.round(gallery.scrollLeft / gallery.offsetWidth);
        dots.forEach((d, i) => d.classList.toggle('active', i === idx));
    });
}

// ══════════════════════════════════════════════
// ══ CART SCREEN
// ══════════════════════════════════════════════
function openCart() {
    renderCartScreen();
    showScreen('cart');
}

function renderCartScreen() {
    const cart = getCart();

    if (cart.length === 0) {
        $screenCart.innerHTML = `
            <div class="cart">
                <div class="cart__header">
                    <button class="detail__back" onclick="showScreen('catalog')">← Назад</button>
                    <h2 class="cart__title">Корзина</h2>
                </div>
                <div class="empty">Корзина пуста</div>
                <div style="padding:0 16px;">
                    <button class="btn-secondary" onclick="showScreen('catalog')">Перейти в каталог</button>
                </div>
            </div>
        `;
        return;
    }

    let itemsHtml = '';
    for (let i = 0; i < cart.length; i++) {
        const item = cart[i];
        itemsHtml += `
            <div class="cart-item">
                <img class="cart-item__img" src="${item.picture || ''}" alt="${item.name}" />
                <div class="cart-item__info">
                    <div class="cart-item__name">${item.name}</div>
                    ${item.variant_label ? `<div class="cart-item__variant">${item.variant_label}</div>` : ''}
                    <div class="cart-item__price">${formatPrice(item.price)}</div>
                </div>
                <div class="cart-item__controls">
                    <button class="cart-item__qty-btn" onclick="changeQty(${i}, -1)">−</button>
                    <span class="cart-item__qty">${item.quantity}</span>
                    <button class="cart-item__qty-btn" onclick="changeQty(${i}, 1)">+</button>
                </div>
                <button class="cart-item__remove" onclick="removeItem(${i})">✕</button>
            </div>
        `;
    }

    $screenCart.innerHTML = `
        <div class="cart">
            <div class="cart__header">
                <button class="detail__back" onclick="showScreen('catalog')">← Назад</button>
                <h2 class="cart__title">Корзина</h2>
            </div>
            <div class="cart__items">${itemsHtml}</div>
            <div class="cart__footer">
                <div class="cart__total">
                    <span>Итого</span>
                    <span class="cart__total-price">${formatPrice(getCartTotal())}</span>
                </div>
                <button class="btn-primary" onclick="openOrderForm()">Оформить заказ</button>
                <button class="btn-secondary cart__continue" onclick="showScreen('catalog')">Продолжить покупки</button>
            </div>
        </div>
    `;

    // Image fade-in for cart items
    $screenCart.querySelectorAll('.cart-item__img').forEach(img => {
        if (img.complete) img.classList.add('loaded');
        else img.addEventListener('load', () => img.classList.add('loaded'));
    });
}

function changeQty(index, delta) {
    if (tg && tg.HapticFeedback) tg.HapticFeedback.selectionChanged();
    updateCartQuantity(index, delta);
    renderCartScreen();
}

function removeItem(index) {
    if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
    removeFromCart(index);
    renderCartScreen();
}

// ══════════════════════════════════════════════
// ══ ORDER FORM
// ══════════════════════════════════════════════
function openOrderForm() {
    const cart = getCart();
    if (cart.length === 0) return;

    // Tomorrow as min date
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const minDate = tomorrow.toISOString().split('T')[0];

    $screenOrder.innerHTML = `
        <div class="order-form">
            <div class="cart__header">
                <button class="detail__back" onclick="showScreen('cart')">← Назад</button>
                <h2 class="cart__title">Оформление</h2>
            </div>

            <form id="order-form" onsubmit="submitOrder(event)">
                <div class="form-section-title">Ваши данные</div>

                <div class="form-group">
                    <label class="form-label">Имя *</label>
                    <input class="form-input" type="text" name="customer_name" required placeholder="Как к вам обращаться?" />
                </div>

                <div class="form-group">
                    <label class="form-label">Телефон *</label>
                    <input class="form-input" type="tel" name="customer_phone" required placeholder="+7 (___) ___-__-__" />
                </div>

                <div class="form-section-title">Доставка</div>

                <div class="form-group">
                    <label class="form-label">Адрес доставки</label>
                    <input class="form-input" type="text" name="delivery_address" placeholder="Улица, дом, квартира" />
                </div>

                <div class="form-row">
                    <div class="form-group form-group--half">
                        <label class="form-label">Дата</label>
                        <input class="form-input" type="date" name="delivery_date" min="${minDate}" />
                    </div>
                    <div class="form-group form-group--half">
                        <label class="form-label">Время</label>
                        <select class="form-input" name="delivery_time">
                            <option value="">Любое</option>
                            <option value="09:00–12:00">09:00–12:00</option>
                            <option value="12:00–15:00">12:00–15:00</option>
                            <option value="15:00–18:00">15:00–18:00</option>
                            <option value="18:00–21:00">18:00–21:00</option>
                        </select>
                    </div>
                </div>

                <div class="form-section-title">Дополнительно</div>

                <div class="form-group">
                    <label class="form-label">Текст открытки</label>
                    <textarea class="form-input form-textarea" name="card_text" placeholder="Напишите пожелание для получателя..." rows="3"></textarea>
                </div>

                <div class="form-group">
                    <label class="form-label">Комментарий</label>
                    <textarea class="form-input form-textarea" name="comment" placeholder="Особые пожелания, домофон, этаж..." rows="2"></textarea>
                </div>

                <!-- Сводка заказа -->
                <div class="order-summary">
                    <div class="order-summary__title">Ваш заказ</div>
                    ${cart.map(item => `
                        <div class="order-summary__item">
                            <span>${item.name}${item.variant_label ? ` (${item.variant_label})` : ''} × ${item.quantity}</span>
                            <span>${formatPrice(item.price * item.quantity)}</span>
                        </div>
                    `).join('')}
                    <div class="order-summary__total">
                        <span>Итого</span>
                        <span>${formatPrice(getCartTotal())}</span>
                    </div>
                </div>

                <button class="btn-primary order-form__submit" type="submit" id="btn-submit-order">
                    Отправить заказ — ${formatPrice(getCartTotal())}
                </button>
            </form>
        </div>
    `;

    showScreen('order');
}

async function submitOrder(e) {
    e.preventDefault();

    const form = document.getElementById('order-form');
    const btn = document.getElementById('btn-submit-order');
    const formData = new FormData(form);
    const cart = getCart();

    if (cart.length === 0) return;

    btn.disabled = true;
    btn.textContent = 'Отправляем...';

    // Telegram user data
    let telegramUserId = '';
    let telegramUsername = '';
    if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) {
        telegramUserId = String(tg.initDataUnsafe.user.id || '');
        telegramUsername = tg.initDataUnsafe.user.username || '';
    }

    const orderData = {
        telegram_user_id: telegramUserId,
        telegram_username: telegramUsername,
        customer_name: formData.get('customer_name'),
        customer_phone: formData.get('customer_phone'),
        delivery_address: formData.get('delivery_address') || '',
        delivery_date: formData.get('delivery_date') || '',
        delivery_time: formData.get('delivery_time') || '',
        comment: formData.get('comment') || '',
        card_text: formData.get('card_text') || '',
        items: cart.map(item => ({
            product_id: item.product_id,
            variant_id: item.variant_id || null,
            name: item.name,
            variant_label: item.variant_label || null,
            price: item.price,
            quantity: item.quantity,
            picture: item.picture || null,
        })),
        total: getCartTotal(),
    };

    try {
        const res = await fetch(`${API}/orders`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(orderData),
        });

        if (!res.ok) throw new Error('Ошибка сервера');

        const result = await res.json();

        // Очищаем корзину
        saveCart([]);

        // Показываем успех
        showOrderSuccess(result.order_id);
    } catch (e) {
        console.error('Ошибка оформления:', e);
        btn.disabled = false;
        btn.textContent = `Отправить заказ — ${formatPrice(getCartTotal())}`;
        showToast('Ошибка! Попробуйте ещё раз');
    }
}

function showOrderSuccess(orderId) {
    $screenSuccess.innerHTML = `
        <div class="success">
            <div class="success__icon">✓</div>
            <h2 class="success__title">Заказ оформлен</h2>
            <p class="success__text">Номер заказа: <strong>#${orderId}</strong></p>
            <p class="success__text">Мы свяжемся с вами для подтверждения.</p>
            <button class="btn-primary success__btn" onclick="showScreen('catalog')">Вернуться в каталог</button>
        </div>
    `;
    showScreen('success');
}

// ── Toast ──
function showToast(message) {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 2000);
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
