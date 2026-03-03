/**
 * Plombir Flowers — Mini App (Sprint 2)
 * Каталог + Корзина + Оформление заказа + Фильтр цен
 * Стилистика адаптирована под plombirflowers.ru
 */

const API = '/api';
const LIMIT = 20;
const CONTACTS_COORDS = [59.948702, 30.36033]; // ул. Кирочная, 8Б
const MAPS_URL = 'https://yandex.ru/maps/?text=%D1%83%D0%BB.%20%D0%9A%D0%B8%D1%80%D0%BE%D1%87%D0%BD%D0%B0%D1%8F%2C%208%D0%91';
const SERVICE_PREVIEW = {
    delivery: 'https://optim.tildacdn.com/tild3033-3464-4334-a666-346339363130/-/cover/200x200/center/center/-/format/webp/80594010.jpg.webp',
    payment: 'https://optim.tildacdn.com/tild3466-3139-4433-a639-306438323036/-/cover/200x200/center/center/-/format/webp/IMG_1889.jpg.webp',
};
const FALLBACK_BANNERS = [
    {
        id: 'plombir-top-2',
        title: '',
        subtitle: '',
        target: 'catalog',
        image_url: 'https://optim.tildacdn.com/tild6434-3265-4536-a134-636562306563/-/format/webp/F4.jpg.webp',
    },
    {
        id: 'plombir-top-1',
        title: '',
        subtitle: '',
        target: 'catalog',
        image_url: 'https://optim.tildacdn.com/tild3464-3235-4331-a136-633031386530/-/format/webp/Frame_9.jpg.webp',
    },
    {
        id: 'plombir-top-3',
        title: '',
        subtitle: '',
        target: 'catalog',
        image_url: 'https://optim.tildacdn.com/tild3436-3739-4134-b261-613064396336/-/format/webp/Frame_12.jpg.webp',
    },
    {
        id: 'plombir-top-4',
        title: '',
        subtitle: '',
        target: 'catalog',
        image_url: 'https://optim.tildacdn.com/tild6265-3865-4463-b736-303137666334/-/format/webp/F3.jpg.webp',
    },
    {
        id: 'plombir-top-5',
        title: '',
        subtitle: '',
        target: 'catalog',
        image_url: 'https://optim.tildacdn.com/tild6431-6164-4164-b436-643938336364/-/format/webp/Frame_13.jpg.webp',
    },
];

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
    currentScreen: 'catalog',  // catalog | product | cart | order | success | info
    currentProduct: null,
    selectedVariant: null,
    infoPage: 'about',         // about | contacts | payment | delivery
    uiContent: {
        ticker_items: [],
        banners: [],
    },
    heroIndex: 0,
    heroTimer: null,
    heroRenderKey: '',
    initialBootLoading: true,
    initialProductsPending: null,
    integrations: {
        payments: {
            yookassa_enabled: false,
            split_enabled: false,
            split_months_default: 4,
            yandex_pay_sdk_url: 'https://pay.yandex.ru/sdk/v1/pay.js',
            yandex_pay_merchant_id: '',
            yandex_pay_theme: 'light',
            methods: ['manual', 'card', 'split'],
        },
        loyalty: {
            enabled: false,
            max_percent: 30,
            rate: 1,
        },
        moysklad: { enabled: false },
    },
    orderPricing: null,
};
let yandexMapsPromise = null;
let contactsMapInstance = null;
let heroSwiper = null;
let yandexPayScriptPromise = null;
const widgetMountTimers = {};

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
    closeMenu();
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
    } else {
        requestAnimationFrame(() => restartTickerAnimation());
    }
    const menuTarget = name === 'info' ? (state.infoPage || 'about') : 'catalog';
    setActiveMenuLink(menuTarget);
}

function goBack() {
    if (state.currentScreen === 'product') showScreen('catalog');
    else if (state.currentScreen === 'cart') showScreen('catalog');
    else if (state.currentScreen === 'order') showScreen('cart');
    else if (state.currentScreen === 'success') showScreen('catalog');
    else if (state.currentScreen === 'info') showScreen('catalog');
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
const $screenInfo = document.getElementById('screen-info');
const $heroTrack = document.getElementById('hero-track');
const $heroDots = document.getElementById('hero-dots');
const $tickerInner = document.getElementById('ticker-inner');

// ── Init ──
async function init() {
    await loadIntegrationsConfig();
    await ensureYandexPaySdk();
    await loadUiContent();
    renderTicker();
    renderHeroSlider();
    startHeroAutoplay();
    await loadCategories();
    await loadProducts(true);
    updateCartBadge();
    setupPriceFilter();
    await handlePaymentReturnFromUrl();
}

async function loadIntegrationsConfig() {
    try {
        const res = await fetch(`${API}/integrations/public-config`);
        if (!res.ok) throw new Error('integrations config failed');
        const data = await res.json();
        state.integrations = {
            ...state.integrations,
            ...data,
            payments: { ...state.integrations.payments, ...(data.payments || {}) },
            loyalty: { ...state.integrations.loyalty, ...(data.loyalty || {}) },
            moysklad: { ...state.integrations.moysklad, ...(data.moysklad || {}) },
        };
    } catch (e) {
        console.warn('Не удалось загрузить конфиг интеграций, применены фолбэки');
    }
}

function hasSplitSdkConfig() {
    const p = state.integrations?.payments || {};
    return !!(p.split_enabled && p.yandex_pay_sdk_url && p.yandex_pay_merchant_id);
}

async function ensureYandexPaySdk() {
    if (!hasSplitSdkConfig()) return;
    if (window.YaPay) return;
    if (yandexPayScriptPromise) return yandexPayScriptPromise;
    const existing = Array.from(document.scripts).find((s) => (s.src || '').includes('pay.yandex.ru/sdk/v1/pay.js'));
    if (existing) {
        yandexPayScriptPromise = new Promise((resolve) => {
            if (window.YaPay) {
                resolve();
                return;
            }
            existing.addEventListener('load', () => resolve(), { once: true });
            existing.addEventListener('error', () => resolve(), { once: true });
        });
        return yandexPayScriptPromise;
    }
    yandexPayScriptPromise = new Promise((resolve) => {
        const script = document.createElement('script');
        script.src = state.integrations.payments.yandex_pay_sdk_url;
        script.async = true;
        script.onload = () => {
            if (window.customElements?.get('yandex-pay-badge')) {
                document.documentElement.classList.add('split-sdk-ready');
            }
            resolve();
        };
        script.onerror = () => resolve();
        document.head.appendChild(script);
    });
    return yandexPayScriptPromise;
}

// ══════════════════════════════════════════════
// ══ SIDE MENU
// ══════════════════════════════════════════════
function openMenu() {
    const menu = document.getElementById('side-menu');
    const overlay = document.getElementById('side-menu-overlay');
    if (!menu || !overlay) return;
    menu.classList.add('side-menu--open');
    overlay.classList.add('side-menu-overlay--open');
    document.body.classList.add('menu-open');
}

function closeMenu() {
    const menu = document.getElementById('side-menu');
    const overlay = document.getElementById('side-menu-overlay');
    if (!menu || !overlay) return;
    menu.classList.remove('side-menu--open');
    overlay.classList.remove('side-menu-overlay--open');
    document.body.classList.remove('menu-open');
}

function menuOpenCatalog() {
    closeMenu();
    showScreen('catalog');
}

function menuOpenInfo(page) {
    closeMenu();
    openInfoPage(page);
}

function openExternalUrl(url) {
    if (!url) return;
    if (tg && typeof tg.openLink === 'function') {
        tg.openLink(url);
        return;
    }
    window.open(url, '_blank', 'noopener,noreferrer');
}

function openMap(event) {
    if (event) event.preventDefault();
    openExternalUrl(MAPS_URL);
}

function renderServiceSwitcher(activePage) {
    return `
        <div class="service-switcher">
            <button class="service-switcher__item" onclick="openInfoPage('delivery')" aria-label="Открыть страницу доставки">
                <img src="${SERVICE_PREVIEW.delivery}" alt="Доставка" loading="lazy" />
                <span>Доставка</span>
            </button>
            <button class="service-switcher__item" onclick="openInfoPage('payment')" aria-label="Открыть страницу оплаты">
                <img src="${SERVICE_PREVIEW.payment}" alt="Оплата" loading="lazy" />
                <span>Оплата</span>
            </button>
        </div>
    `;
}

function setActiveMenuLink(target) {
    document.querySelectorAll('.side-menu__link').forEach((link) => {
        link.classList.toggle('active', link.dataset.menuTarget === target);
    });
}

// ── UI Content (hero + ticker) ──
async function loadUiContent() {
    try {
        const res = await fetch(`${API}/ui-content`);
        if (!res.ok) throw new Error('ui-content failed');
        state.uiContent = await res.json();
    } catch (e) {
        state.uiContent = {
            ticker_items: [
                'БЕСПЛАТНАЯ ДОСТАВКА ОТ 10 000 ₽ В ПРЕДЕЛАХ КАД',
            ],
            banners: FALLBACK_BANNERS,
        };
    }
    if (!Array.isArray(state.uiContent.banners) || state.uiContent.banners.length === 0) {
        state.uiContent.banners = FALLBACK_BANNERS;
    }
}

function getEffectiveBanners() {
    if (Array.isArray(state.uiContent.banners) && state.uiContent.banners.length) {
        return state.uiContent.banners;
    }
    return FALLBACK_BANNERS;
}

function handleBannerTarget(target) {
    const t = (target || 'catalog').trim();
    if (!t || t === 'catalog') {
        showScreen('catalog');
        return;
    }
    if (t === 'about' || t === 'contacts' || t === 'payment' || t === 'delivery') {
        openInfoPage(t);
        return;
    }
    if (/^https?:\/\//i.test(t)) {
        openExternalUrl(t);
    }
}

function renderHeroSlider() {
    if (!$heroTrack || !$heroDots) return;
    const banners = getEffectiveBanners();
    if (!banners.length) {
        if (heroSwiper) {
            heroSwiper.destroy(true, true);
            heroSwiper = null;
        }
        $heroTrack.innerHTML = '';
        $heroDots.innerHTML = '';
        state.heroRenderKey = '';
        return;
    }

    const key = [
        banners.map((b) => `${b.id}|${b.image_url}|${b.title}|${b.subtitle}|${b.target}`).join('||'),
    ].join('::');
    if (key !== state.heroRenderKey) {
        $heroTrack.innerHTML = `
            <div class="swiper hero-swiper" id="hero-swiper">
                <div class="swiper-wrapper">
                    ${banners.map((b, idx) => `
                        <div class="swiper-slide">
                            <button class="hero-swiper__slide" data-target="${b.target || 'catalog'}" aria-label="Баннер ${idx + 1}">
                                ${b.image_url
                                    ? `<img class="hero-swiper__img" src="${b.image_url}" alt="" loading="lazy" />`
                                    : `<div class="hero-swiper__placeholder" style="--banner-placeholder:${getBannerPlaceholder(idx, b.id)}"></div>`
                                }
            </button>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;

        $heroTrack.querySelectorAll('.hero-swiper__slide').forEach((slide) => {
            slide.addEventListener('click', () => handleBannerTarget(slide.dataset.target));
        });
        applyHeroSmartFit();

        initHeroSwiper(banners.length);
        state.heroRenderKey = key;
    }
}

function startHeroAutoplay() {
    if (heroSwiper?.autoplay) heroSwiper.autoplay.start();
}

function renderTicker() {
    if (!$tickerInner) return;
    const promo = 'БЕСПЛАТНАЯ ДОСТАВКА ОТ 10 000 ₽ В ПРЕДЕЛАХ КАД';
    const items = (state.uiContent.ticker_items || []).filter(Boolean);
    const safeItems = items.length ? items : [promo];
    const repeated = [];
    const minCopies = 6;
    for (let i = 0; i < minCopies; i++) {
        for (const item of safeItems) repeated.push(item);
    }
    $tickerInner.innerHTML = repeated.map((text) => `<span class="ticker__item">${text}</span>`).join('');
    requestAnimationFrame(() => restartTickerAnimation());
}

function restartTickerAnimation() {
    if (!$tickerInner) return;
    const parent = $tickerInner.parentElement;
    if (!parent) return;

    // If initial content is too short for movement, extend it before restarting animation.
    if ($tickerInner.scrollWidth <= parent.clientWidth) {
        const original = $tickerInner.innerHTML;
        $tickerInner.innerHTML = `${original}${original}`;
    }

    $tickerInner.style.animation = 'none';
    void $tickerInner.offsetWidth;
    $tickerInner.style.animation = 'tickerMove 22s linear infinite';
}

function updateHeroActiveState() {
    // Swiper handles active states internally.
}

function initHeroSwiper(slideCount) {
    if (heroSwiper) {
        heroSwiper.destroy(true, true);
        heroSwiper = null;
    }
    if (!$heroDots) return;
    if (typeof window.Swiper !== 'function') {
        $heroDots.innerHTML = '';
        return;
    }

    heroSwiper = new window.Swiper('#hero-swiper', {
        slidesPerView: 1,
        spaceBetween: 0,
        loop: slideCount > 1,
        speed: 520,
        autoplay: slideCount > 1 ? {
            delay: 4500,
            disableOnInteraction: false,
            pauseOnMouseEnter: false,
        } : false,
        pagination: {
            el: '#hero-dots',
            clickable: true,
            bulletClass: 'hero__dot',
            bulletActiveClass: 'active',
            renderBullet: function (index, className) {
                return `<button class="${className}" aria-label="Слайд ${index + 1}"></button>`;
            },
        },
    });
}

function applyHeroSmartFit() {
    const imgs = $heroTrack ? $heroTrack.querySelectorAll('.hero-swiper__img') : [];
    imgs.forEach((img) => {
        const setFit = () => {
            const w = Number(img.naturalWidth || 0);
            const h = Number(img.naturalHeight || 0);
            if (!w || !h) return;
            const ratio = w / h;
            // Очень широкие баннеры лучше показывать contain, чтобы не резать края.
            img.classList.toggle('hero-swiper__img--contain', ratio >= 1.7);
        };
        if (img.complete) {
            setFit();
        } else {
            img.addEventListener('load', setFit, { once: true });
        }
    });
}

function getBannerPlaceholder(index, id) {
    const palette = [
        'linear-gradient(135deg, #efe6de 0%, #f8f2ec 100%)',
        'linear-gradient(135deg, #efe8f0 0%, #f7f1f8 100%)',
        'linear-gradient(135deg, #e8edf2 0%, #f3f6fa 100%)',
        'linear-gradient(135deg, #f2ece4 0%, #fbf7f2 100%)',
        'linear-gradient(135deg, #e8efea 0%, #f4faf6 100%)',
    ];
    const key = `${id || ''}${index}`;
    let hash = 0;
    for (let i = 0; i < key.length; i++) {
        hash = ((hash << 5) - hash) + key.charCodeAt(i);
        hash |= 0;
    }
    return palette[Math.abs(hash) % palette.length];
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
    let html = '';
    for (let i = 0; i < state.categories.length; i++) {
        const cat = state.categories[i];
        const isActive = i === 0 ? ' active' : '';
        html += `<button class="category-btn${isActive}" data-id="${cat.id}">${cat.name}</button>`;
    }
    $categories.innerHTML = html;

    // Выбираем первую категорию по умолчанию
    if (state.categories.length && !state.categoryId) {
        state.categoryId = state.categories[0].id;
    }

    $categories.querySelectorAll('.category-btn').forEach(btn => {
        btn.addEventListener('click', () => onCategoryClick(btn));
    });
}

function onCategoryClick(btn) {
    $categories.querySelectorAll('.category-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.categoryId = btn.dataset.id;
    state.offset = 0;
    // Сбрасываем поиск при выборе категории
    if (state.search) {
        state.search = '';
        $search.value = '';
    }
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
            // Сбрасываем поиск при выборе цены
            if (state.search) {
                state.search = '';
                $search.value = '';
            }
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
            <div class="skeleton-card__buttons">
                <div class="skeleton-card__btn"></div>
                <div class="skeleton-card__btn"></div>
            </div>
        `;
        $products.appendChild(sk);
    }
}

function removeSkeletons() {
    $products.querySelectorAll('.skeleton-card').forEach(sk => sk.remove());
}

// ── Products ──
let _loadAbort = null;   // AbortController для отмены предыдущего запроса

async function loadProducts(reset = false) {
    // Отменяем предыдущий запрос, если он ещё в полёте
    if (_loadAbort) {
        _loadAbort.abort();
        _loadAbort = null;
    }

    const abort = new AbortController();
    _loadAbort = abort;

    state.loading = true;

    if (reset) {
        state.offset = 0;
        $products.innerHTML = '';
    }

    // Показываем скелетоны
    if (reset) {
        showSkeletons(LIMIT);
    } else {
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
            fetch(`${API}/products?${params}`, { signal: abort.signal }),
            new Promise(r => setTimeout(r, 800)),
        ]);

        // Если пока ждали ответ — пришёл новый запрос, не рендерим устаревшие данные
        if (abort.signal.aborted) return;

        const data = await res.json();

        state.total = data.total;
        state.offset += data.items.length;

        if (reset) {
            state.products = data.items;
        } else {
            state.products = [...state.products, ...data.items];
        }

        if (state.initialBootLoading && reset) {
            state.initialProductsPending = { items: data.items, reset };
        } else {
            removeSkeletons();
            renderProducts(data.items, reset);
            updateLoadMore();
        }
    } catch (e) {
        if (e.name === 'AbortError') return;   // отменили — норм
        console.error('Ошибка загрузки товаров:', e);
        if (state.initialBootLoading && reset) {
            state.total = 0;
            state.offset = 0;
            state.products = [];
            state.initialProductsPending = { items: [], reset: true };
        } else {
            removeSkeletons();
        }
    } finally {
        if (_loadAbort === abort) {
            state.loading = false;
            _loadAbort = null;
        }
        if (state.initialBootLoading) {
            state.initialBootLoading = false;
            state.heroRenderKey = '';
            renderHeroSlider();
            if (state.initialProductsPending) {
                removeSkeletons();
                renderProducts(state.initialProductsPending.items, state.initialProductsPending.reset);
                updateLoadMore();
                state.initialProductsPending = null;
            }
        }
        showLoading(false);
    }
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
        // Диапазон цен на карточке не показываем — только минимальная

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
                ${renderSplitHint(p.price, 'product-card__split')}
            </div>
            <div class="product-card__buttons">
                <button class="product-card__btn product-card__btn--detail" data-id="${p.id}">Подробнее</button>
                <button class="product-card__btn product-card__btn--cart" data-id="${p.id}">В корзину</button>
            </div>
        `;
        $products.appendChild(card);

        // Button handlers (stop propagation so card click doesn't fire)
        card.querySelector('.product-card__btn--detail').addEventListener('click', (e) => {
            e.stopPropagation();
            openProduct(p.id);
        });
        card.querySelector('.product-card__btn--cart').addEventListener('click', (e) => {
            e.stopPropagation();
            addToCartFromCard(p, e.currentTarget);
        });

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

function getSplitMonths() {
    const months = Number(state.integrations?.payments?.split_months_default || 4);
    return Number.isFinite(months) && months > 1 ? months : 4;
}

function getSplitMonthly(price) {
    const months = getSplitMonths();
    const amount = Number(price || 0);
    if (!amount) return '';
    return formatPrice(amount / months);
}

function renderSplitHint(price, className) {
    if (!state.integrations?.payments?.split_enabled) return '';
    const months = getSplitMonths();
    const merchantId = state.integrations?.payments?.yandex_pay_merchant_id || '';
    const theme = state.integrations?.payments?.yandex_pay_theme || 'light';
    const amount = Math.max(1, Math.round(Number(price || 0)));
    const badgeBnpl = merchantId
        ? `<yandex-pay-badge type="bnpl" amount="${amount}" merchant-id="${merchantId}" theme="${theme}" size="s" align="left" color="primary"></yandex-pay-badge>`
        : '';
    const badgeCashback = merchantId
        ? `<yandex-pay-badge type="cashback" amount="${amount}" merchant-id="${merchantId}" theme="${theme}" size="s" align="left" color="primary"></yandex-pay-badge>`
        : '';
    return `
        <div class="${className}">
            <div class="split-component" data-split-months="${months}">${badgeBnpl}${badgeCashback}</div>
        </div>
    `;
}

function scheduleUltimateWidget(containerId, amount) {
    clearTimeout(widgetMountTimers[containerId]);
    widgetMountTimers[containerId] = setTimeout(() => {
        mountUltimateWidget(containerId, amount);
    }, 80);
}

async function mountUltimateWidget(containerId, amount) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!hasSplitSdkConfig()) {
        container.innerHTML = '';
        return;
    }
    await ensureYandexPaySdk();
    if (!window.YaPay) {
        container.innerHTML = '';
        return;
    }

    const merchantId = state.integrations?.payments?.yandex_pay_merchant_id || '';
    const theme = state.integrations?.payments?.yandex_pay_theme || 'light';
    const totalAmount = Math.max(1, Math.round(Number(amount || 0)));
    const themeMap = {
        dark: window.YaPay.WidgetTheme?.Dark || 'dark',
        light: window.YaPay.WidgetTheme?.Light || 'light',
    };

    const paymentData = {
        version: 4,
        totalAmount,
        merchantId,
        currencyCode: window.YaPay.CurrencyCode?.Rub || 'RUB',
        availablePaymentMethods: ['SPLIT', 'CARD'],
    };

    try {
        container.innerHTML = '';
        const paymentSession = await window.YaPay.createSession(paymentData, {
            source: 'cms',
            onPayButtonClick: () => '',
        });
        paymentSession.mountWidget(container, {
            widgetType: window.YaPay.WidgetType?.Ultimate,
            widgetTheme: themeMap[theme] || theme,
        });
    } catch (e) {
        console.warn('Не удалось смонтировать YaPay Ultimate widget:', e);
        container.innerHTML = '';
    }
}

function calculateOrderPricing(subtotal, pointsUsedRaw) {
    const subtotalSafe = Math.max(0, Number(subtotal || 0));
    const loyaltyCfg = state.integrations?.loyalty || {};
    if (!loyaltyCfg.enabled) {
        return {
            subtotal: subtotalSafe,
            points_used: 0,
            discount: 0,
            total: subtotalSafe,
            points_max: 0,
            split_months: getSplitMonths(),
            split_monthly_payment: subtotalSafe / getSplitMonths(),
        };
    }
    const rate = Number(loyaltyCfg.rate || 1) || 1;
    const maxPercent = Number(loyaltyCfg.max_percent || 30) || 30;
    const maxDiscount = subtotalSafe * (maxPercent / 100);
    const pointsRequested = Math.max(0, Number(pointsUsedRaw || 0));
    const discountByPoints = pointsRequested * rate;
    const discount = Math.min(maxDiscount, discountByPoints, subtotalSafe);
    const pointsUsed = discount / rate;
    const total = Math.max(0, subtotalSafe - discount);
    const splitMonths = getSplitMonths();
    return {
        subtotal: subtotalSafe,
        points_used: pointsUsed,
        discount,
        total,
        points_max: maxDiscount / rate,
        split_months: splitMonths,
        split_monthly_payment: total / splitMonths,
    };
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
            <div class="detail__gallery" id="detail-gallery">${galleryHtml}</div>
            ${p.pictures.length > 1 ? `<div class="detail__gallery-dots" id="detail-dots">${dotsHtml}</div>` : ''}
            <div class="detail__body">
                <div class="detail__name">${p.name}</div>
                <div class="detail__price-block">
                    <span class="detail__price" id="detail-price">${formatPrice(currentPrice)}</span>
                    ${currentOldPrice ? `<span class="detail__old-price" id="detail-old-price">${formatPrice(currentOldPrice)}</span>` : '<span class="detail__old-price" id="detail-old-price"></span>'}
                </div>
                <div id="detail-split-hint">${renderSplitHint(currentPrice, 'detail__split')}</div>
                <div id="detail-ultimate-widget" class="detail__ultimate-widget"></div>
                ${variantsHtml}
                <button class="btn-primary detail__add-to-cart" onclick="addCurrentToCart()">
                    В корзину
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
    scheduleUltimateWidget('detail-ultimate-widget', currentPrice);
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
    const $splitHint = document.getElementById('detail-split-hint');
    if ($price) $price.textContent = formatPrice(state.selectedVariant.price);
    if ($oldPrice) $oldPrice.textContent = state.selectedVariant.old_price ? formatPrice(state.selectedVariant.old_price) : '';
    if ($splitHint) {
        $splitHint.innerHTML = renderSplitHint(state.selectedVariant.price, 'detail__split');
    }
    scheduleUltimateWidget('detail-ultimate-widget', state.selectedVariant.price);
}

function addCurrentToCart() {
    const p = state.currentProduct;
    if (!p) return;

    const v = state.selectedVariant;
    const item = {
        product_id: p.id,
        variant_id: v ? v.id : null,
        product_code: (v && v.code) || p.code || p.id,
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

// Quick add-to-cart from product card
function addToCartFromCard(product, btnEl) {
    const item = {
        product_id: product.id,
        variant_id: null,
        product_code: product.code || product.id,
        name: product.name,
        variant_label: null,
        price: product.price,
        quantity: 1,
        picture: product.picture || null,
    };
    addToCart(item);

    // Visual feedback on button
    if (btnEl) {
        btnEl.classList.add('btn-added');
        btnEl.textContent = '✓ Добавлено';
        setTimeout(() => {
            btnEl.classList.remove('btn-added');
            btnEl.textContent = 'В корзину';
        }, 1200);
    }

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

    const subtotal = getCartTotal();
    const supportsCard = !!state.integrations?.payments?.yookassa_enabled;
    const supportsSplit = !!state.integrations?.payments?.split_enabled;
    const loyaltyEnabled = !!state.integrations?.loyalty?.enabled;
    const initialPricing = calculateOrderPricing(subtotal, 0);
    state.orderPricing = initialPricing;

    $screenOrder.innerHTML = `
        <div class="order-form">
            <div class="cart__header">
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
                <div class="form-group">
                    <label class="form-label">Тип доставки</label>
                    <select class="form-input" name="delivery_type">
                        <option value="Курьер">Курьер</option>
                        <option value="Самовывоз с ул. Кирочная 8Б">Самовывоз с ул. Кирочная 8Б</option>
                        <option value="Узнать адрес у получателя*">Узнать адрес у получателя</option>
                    </select>
                </div>

                <div class="form-group">
                    <label class="form-label">Дата</label>
                    <input class="form-input" type="date" name="delivery_date" min="${minDate}" placeholder="Выберите дату" />
                </div>
                <div class="form-group">
                    <label class="form-label">Время</label>
                    <select class="form-input" name="delivery_time">
                        <option value="">Любое</option>
                        <option value="09:00–12:00">09:00–12:00</option>
                        <option value="12:00–15:00">12:00–15:00</option>
                        <option value="15:00–18:00">15:00–18:00</option>
                        <option value="18:00–21:00">18:00–21:00</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Получатель</label>
                    <input class="form-input" type="text" name="recipient_name" placeholder="Имя получателя" />
                </div>
                <div class="form-group">
                    <label class="form-label">Телефон получателя</label>
                    <input class="form-input" type="tel" name="recipient_phone" placeholder="+7 (___) ___-__-__" />
                </div>
                <div class="form-group">
                    <label class="form-label">Как связаться для подтверждения</label>
                    <select class="form-input" name="contact_method">
                        <option value="Telegram">Telegram</option>
                        <option value="WhatsApp">WhatsApp</option>
                        <option value="Связываться не нужно (только в случае необходимости пересогласовать состав заказа)">
                            Связываться не нужно
                        </option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Никнейм в Telegram</label>
                    <input class="form-input" type="text" name="telegram_nickname" placeholder="@username" />
                </div>
                <div class="form-group">
                    <label class="form-label">Комментарий курьеру</label>
                    <textarea class="form-input form-textarea" name="courier_comment" placeholder="Подъезд, домофон, этаж..." rows="2"></textarea>
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

                <div class="form-section-title">Оплата</div>
                <div class="payment-methods">
                    <label class="payment-methods__item">
                        <input type="radio" name="payment_method" value="manual" checked />
                        <div>
                            <strong>В студии / при согласовании</strong>
                            <span>Менеджер подтвердит заказ и подскажет способ оплаты.</span>
                        </div>
                    </label>
                    <label class="payment-methods__item${supportsCard ? '' : ' payment-methods__item--disabled'}">
                        <input type="radio" name="payment_method" value="card" ${supportsCard ? '' : 'disabled'} />
                        <div>
                            <strong>Онлайн картой</strong>
                            <span>${supportsCard ? 'Перейдете на защищенную страницу ЮKassa после оформления.' : 'Появится после подключения ЮKassa.'}</span>
                        </div>
                    </label>
                    <label class="payment-methods__item${supportsSplit ? '' : ' payment-methods__item--disabled'}">
                        <input type="radio" name="payment_method" value="split" ${supportsSplit ? '' : 'disabled'} />
                        <div>
                            <strong>Яндекс Сплит</strong>
                            <span>${supportsSplit ? `Платеж частями: от ${formatPrice(initialPricing.split_monthly_payment)} x ${initialPricing.split_months}.` : 'Появится после активации Сплит в ЮKassa.'}</span>
                        </div>
                    </label>
                </div>

                ${loyaltyEnabled ? `
                    <div class="form-section-title">Баллы</div>
                    <div class="form-group">
                        <label class="form-label">Списать баллы</label>
                        <input class="form-input" type="number" name="loyalty_points_used" id="loyalty-points-input" min="0" step="1" value="0" placeholder="0" />
                        <div class="order-hint" id="loyalty-hint"></div>
                    </div>
                ` : ''}

                <div id="order-split-component">${renderSplitHint(initialPricing.total, 'order-split')}</div>
                <div id="order-ultimate-widget" class="order__ultimate-widget"></div>

                <!-- Сводка заказа -->
                <div class="order-summary">
                    <div class="order-summary__title">Ваш заказ</div>
                    ${cart.map(item => `
                        <div class="order-summary__item">
                            <span>${item.name}${item.variant_label ? ` (${item.variant_label})` : ''} × ${item.quantity}</span>
                            <span>${formatPrice(item.price * item.quantity)}</span>
                        </div>
                    `).join('')}
                    <div class="order-summary__item">
                        <span>Подытог</span>
                        <span id="order-subtotal">${formatPrice(initialPricing.subtotal)}</span>
                    </div>
                    <div class="order-summary__item" id="order-discount-row" style="display:${initialPricing.discount > 0 ? 'flex' : 'none'};">
                        <span>Списано баллами</span>
                        <span id="order-discount">-${formatPrice(initialPricing.discount)}</span>
                    </div>
                    <div class="order-summary__total">
                        <span>Итого</span>
                        <span id="order-total">${formatPrice(initialPricing.total)}</span>
                    </div>
                    <div class="order-hint" id="order-split-hint"></div>
                </div>
                <input type="hidden" name="subtotal" value="${initialPricing.subtotal}" />
                <input type="hidden" name="total" id="order-total-input" value="${initialPricing.total}" />
                <input type="hidden" name="split_months" id="order-split-months-input" value="${initialPricing.split_months}" />

                <button class="btn-primary order-form__submit" type="submit" id="btn-submit-order">
                    Отправить заказ — <span id="submit-total-label">${formatPrice(initialPricing.total)}</span>
                </button>
            </form>
        </div>
    `;

    bindOrderFormInteractions();
    showScreen('order');
}

function bindOrderFormInteractions() {
    const form = document.getElementById('order-form');
    if (!form) return;
    const pointsInput = document.getElementById('loyalty-points-input');
    const paymentInputs = form.querySelectorAll('input[name="payment_method"]');

    if (pointsInput) {
        pointsInput.addEventListener('input', () => updateOrderPricingUI());
        pointsInput.addEventListener('change', () => updateOrderPricingUI());
    }
    paymentInputs.forEach((input) => input.addEventListener('change', () => updateOrderPricingUI()));
    updateOrderPricingUI();
}

function updateOrderPricingUI() {
    const form = document.getElementById('order-form');
    if (!form) return;
    const pointsInput = document.getElementById('loyalty-points-input');
    const pointsValue = pointsInput ? Number(pointsInput.value || 0) : 0;
    const pricing = calculateOrderPricing(getCartTotal(), pointsValue);
    state.orderPricing = pricing;

    if (pointsInput) {
        pointsInput.value = String(Math.floor(pricing.points_used));
        const hint = document.getElementById('loyalty-hint');
        if (hint) hint.textContent = `Максимум к списанию: ${Math.floor(pricing.points_max)} баллов`;
    }

    const paymentMethod = (form.querySelector('input[name="payment_method"]:checked') || {}).value || 'manual';
    const splitHint = document.getElementById('order-split-hint');
    const splitComponent = document.getElementById('order-split-component');
    if (splitHint) {
        if (paymentMethod === 'split') {
            splitHint.textContent = `Сплит: ${formatPrice(pricing.split_monthly_payment)} x ${pricing.split_months} мес.`;
        } else {
            splitHint.textContent = '';
        }
    }
    if (splitComponent) {
        splitComponent.innerHTML = renderSplitHint(pricing.total, 'order-split');
    }
    scheduleUltimateWidget('order-ultimate-widget', pricing.total);

    const subtotalNode = document.getElementById('order-subtotal');
    const discountRow = document.getElementById('order-discount-row');
    const discountNode = document.getElementById('order-discount');
    const totalNode = document.getElementById('order-total');
    const totalInput = document.getElementById('order-total-input');
    const splitMonthsInput = document.getElementById('order-split-months-input');
    const submitLabel = document.getElementById('submit-total-label');

    if (subtotalNode) subtotalNode.textContent = formatPrice(pricing.subtotal);
    if (discountNode) discountNode.textContent = `-${formatPrice(pricing.discount)}`;
    if (discountRow) discountRow.style.display = pricing.discount > 0 ? 'flex' : 'none';
    if (totalNode) totalNode.textContent = formatPrice(pricing.total);
    if (totalInput) totalInput.value = String(pricing.total);
    if (splitMonthsInput) splitMonthsInput.value = String(pricing.split_months);
    if (submitLabel) submitLabel.textContent = formatPrice(pricing.total);
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
        delivery_type: formData.get('delivery_type') || '',
        contact_method: formData.get('contact_method') || '',
        recipient_name: formData.get('recipient_name') || '',
        recipient_phone: formData.get('recipient_phone') || '',
        courier_comment: formData.get('courier_comment') || '',
        telegram_nickname: formData.get('telegram_nickname') || '',
        comment: formData.get('comment') || '',
        card_text: formData.get('card_text') || '',
        payment_method: formData.get('payment_method') || 'manual',
        loyalty_points_used: Number(formData.get('loyalty_points_used') || 0),
        split_months: Number(formData.get('split_months') || getSplitMonths()),
        items: cart.map(item => ({
            product_id: item.product_id,
            variant_id: item.variant_id || null,
            product_code: item.product_code || item.product_id,
            name: item.name,
            variant_label: item.variant_label || null,
            price: item.price,
            quantity: item.quantity,
            picture: item.picture || null,
        })),
        subtotal: Number(formData.get('subtotal') || getCartTotal()),
        total: Number(formData.get('total') || getCartTotal()),
    };

    try {
        const res = await fetch(`${API}/orders`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(orderData),
        });

        if (!res.ok) throw new Error('Ошибка сервера');

        const result = await res.json();

        if (result.payment?.enabled && result.payment?.confirmation_url) {
            // Заказ уже создан; перед редиректом в ЮKassa показываем промежуточный экран.
            saveCart([]);
            showPaymentAwaitingRedirect(result.order_id, orderData.payment_method, result.payment.confirmation_url);
            return;
        } else if (orderData.payment_method !== 'manual' && result.payment?.enabled === false) {
            showToast('Онлайн-оплата пока недоступна, заказ принят менеджером');
        }

        // Для офлайн/фолбэк-сценария заказ оформлен сразу.
        saveCart([]);
        showOrderSuccess(result.order_id);
    } catch (e) {
        console.error('Ошибка оформления:', e);
        btn.disabled = false;
        btn.textContent = `Отправить заказ — ${formatPrice(getCartTotal())}`;
        showToast('Ошибка! Попробуйте ещё раз');
    }
}

function showPaymentAwaitingRedirect(orderId, paymentMethod, confirmationUrl) {
    const methodTitle = paymentMethod === 'split' ? 'Яндекс Сплит' : 'Онлайн-оплата картой';
    $screenSuccess.innerHTML = `
        <div class="success">
            <div class="success__icon">↗</div>
            <h2 class="success__title">Переходим к оплате</h2>
            <p class="success__text">Заказ <strong>#${orderId}</strong> создан.</p>
            <p class="success__text">${methodTitle}. Сейчас откроется защищенная страница ЮKassa.</p>
            <button class="btn-primary success__btn" onclick="openExternalUrl('${confirmationUrl}')">Перейти к оплате</button>
            <button class="btn-secondary success__btn" onclick="showScreen('catalog')">Вернуться в каталог</button>
        </div>
    `;
    showScreen('success');
    setTimeout(() => openExternalUrl(confirmationUrl), 250);
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

function clearPaymentParamsFromUrl() {
    try {
        const url = new URL(window.location.href);
        url.searchParams.delete('order_id');
        window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
    } catch (e) {
        console.warn('Не удалось очистить payment-параметры URL', e);
    }
}

async function handlePaymentReturnFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const orderIdRaw = params.get('order_id');
    if (!orderIdRaw) return;
    const orderId = Number(orderIdRaw);
    if (!Number.isFinite(orderId) || orderId <= 0) {
        clearPaymentParamsFromUrl();
        return;
    }
    try {
        const res = await fetch(`${API}/orders/${orderId}`);
        if (!res.ok) throw new Error('order fetch failed');
        const order = await res.json();
        showPaymentReturnStatus(order);
    } catch (e) {
        console.error('Не удалось проверить статус оплаты после возврата:', e);
        showToast('Не удалось получить статус оплаты. Проверьте заказ в "Мои заказы".');
    } finally {
        clearPaymentParamsFromUrl();
    }
}

function showPaymentReturnStatus(order) {
    const paymentStatus = String(order?.payment_status || '').toLowerCase();
    const orderStatus = order?.status || 'Создан';
    const isPaid = ['succeeded', 'waiting_for_capture'].includes(paymentStatus) || orderStatus === 'Оплачен';
    const isCanceled = ['canceled'].includes(paymentStatus) || orderStatus === 'Отменен';
    const paymentUrl = order?.payment_url || '';

    let title = 'Статус оплаты';
    let text = 'Проверяем оплату. Обычно подтверждение приходит за несколько секунд.';
    let icon = '…';

    if (isPaid) {
        title = 'Оплата прошла успешно';
        text = 'Спасибо! Заказ оплачен и передан в работу флористу.';
        icon = '✓';
    } else if (isCanceled) {
        title = 'Оплата не завершена';
        text = 'Платеж отменен. Можно попробовать оплатить еще раз.';
        icon = '!';
    }

    $screenSuccess.innerHTML = `
        <div class="success">
            <div class="success__icon">${icon}</div>
            <h2 class="success__title">${title}</h2>
            <p class="success__text">Номер заказа: <strong>#${order.id}</strong></p>
            <p class="success__text">${text}</p>
            ${paymentUrl && !isPaid ? `<button class="btn-primary success__btn" onclick="openExternalUrl('${paymentUrl}')">Оплатить заказ</button>` : ''}
            <button class="btn-secondary success__btn" onclick="showScreen('catalog')">Вернуться в каталог</button>
        </div>
    `;
    showScreen('success');
}

// ══════════════════════════════════════════════
// ══ INFO PAGES
// ══════════════════════════════════════════════
function openInfoPage(page = 'about') {
    state.infoPage = page;
    renderInfoScreen(page);
    showScreen('info');
}

function renderInfoScreen(page) {
    if (page === 'about') {
        $screenInfo.innerHTML = `
            <div class="info-page info-page--about-mobile">
                <div class="about-mobile__line"></div>

                <div class="about-mobile__section about-mobile__section--top">
                    <h2 class="about-mobile__title">О нас</h2>

                    <h3 class="about-mobile__subtitle">Неповторимая флористика</h3>
                    <p class="about-mobile__text">
                        Мы обладаем своим индивидуальным и узнаваемым стилем. В первую очередь это наши пломбирные букеты,
                        которые никого не оставляют равнодушными.
                    </p>
                    <p class="about-mobile__text">
                        Также у нас представлена коллекция интерьерных букетов, каждый из которых украсит ваш дом и наполнит его жизнью.
                    </p>

                    <h3 class="about-mobile__subtitle">Сервис высокого уровня</h3>
                    <p class="about-mobile__text">
                        Наши флористы и менеджеры постоянно проходят обучения, чтобы дарить вам высший уровень заботы.
                    </p>
                    <p class="about-mobile__text">
                        Для нас сервис — это забота о госте. Мы делаем все, чтобы вы совершали заказы быстро и с удовольствием.
                    </p>

                    <h3 class="about-mobile__subtitle">Винтаж</h3>
                    <p class="about-mobile__text">
                        Мы развиваем новое направление и собираем для вас винтажные вазы, посуду и другие предметы интерьера.
                        Они сохраняют свой характер и создают особую атмосферу в доме.
                    </p>

                    <h3 class="about-mobile__subtitle">Гарантия качества</h3>
                    <p class="about-mobile__text">
                        Если вы остались недовольны собранным букетом, сообщите нам об этом в течение 2-х часов с момента его получения.
                    </p>

                    <div class="about-mobile__img-wrap about-mobile__img-wrap--xl">
                        <img class="about-mobile__img" src="/app/static/img/guys.png" alt="Plombir Flowers" loading="lazy" />
                    </div>
                </div>

                <div class="about-mobile__line"></div>

                <div class="about-mobile__section">
                    <h3 class="about-mobile__mission-title">
                        Наша миссия - быть рядом в каждый особенный день.
                    </h3>
                    <h3 class="about-mobile__mission-title">
                        А также создавать особенные события каждый день.
                    </h3>

                    <p class="about-mobile__text about-mobile__text--mission">
                        За время существования Plombir наши клиенты уже стали нашими друзьями и знают, что на нас можно положиться.
                        Наши цветы застали ключевые моменты во многих жизнях, стали свидетелями новых этапов и событий.
                    </p>

                    <div class="about-mobile__founders">
                        <img class="about-mobile__avatar-img" src="https://static.tildacdn.com/tild3062-3337-4663-a532-356136396638/IMG_1857.jpg" alt="Основатели Plombir Flowers" loading="lazy" />
                        <p>— Валентина и Никита, <br/>основатели Plombir Flowers</p>
                    </div>
                </div>

                <div class="about-mobile__line"></div>

                <div class="about-mobile__section">
                    <h3 class="about-mobile__visit-title">Приходите в гости в дом Plombir</h3>
                    <p class="about-mobile__visit-text">
                        Мы будем рады видеть вас в гостях в нашей студии, где можно не только порадовать себя и близких букетом,
                        но и насладиться атмосферой и сделать красивые кадры.
                    </p>

                    <div class="about-mobile__visit-grid">
                        <div class="about-mobile__visit-card">
                            <p class="about-mobile__visit-address">Кирочная, 8Б</p>
                            <p class="about-mobile__visit-hours">с 8:30 до 22:00</p>
                            <a class="about-mobile__visit-btn" href="${MAPS_URL}" onclick="openMap(event)" target="_blank" rel="noopener noreferrer">Смотреть на карте</a>
                        </div>
                        <div class="about-mobile__img-wrap about-mobile__img-wrap--side">
                            <img class="about-mobile__img" src="https://static.tildacdn.com/tild3238-3165-4564-b364-366665373462/DSC00674-HDR_resized.jpg" alt="Интерьер студии Plombir" loading="lazy" />
                        </div>
                    </div>

                    <div class="about-mobile__img-wrap about-mobile__img-wrap--wide">
                        <img class="about-mobile__img" src="https://static.tildacdn.com/tild6531-6434-4138-b437-356362363636/DSC00648-2_resized_1.jpg" alt="Студия Plombir Flowers" loading="lazy" />
                    </div>
                </div>
            </div>
        `;
        return;
    }

    if (page === 'contacts') {
        $screenInfo.innerHTML = `
            <div class="info-page info-page--contacts-mobile">
                <div class="contacts-mobile">
                    <div class="contacts-mobile__header">
                        <h2 class="contacts-mobile__title">Контакты</h2>
                        <p class="contacts-mobile__time">Мы на связи с 8:30 до 22:00</p>
                    </div>

                    <div class="contacts-mobile__grid">
                        <div class="contacts-mobile__item">
                            <p class="contacts-mobile__label">Email</p>
                            <a class="contacts-mobile__link" href="mailto:info@plombirflowers.ru">info@plombirflowers.ru</a>
                        </div>

                        <div class="contacts-mobile__item">
                            <p class="contacts-mobile__label">Телефон</p>
                            <a class="contacts-mobile__link" href="tel:+79819672833">+7 981 967 28 33</a>
                        </div>

                        <div class="contacts-mobile__item">
                            <p class="contacts-mobile__label">По вопросам сотрудничества</p>
                            <a class="contacts-mobile__link" href="mailto:pr@plombirflowers.ru">pr@plombirflowers.ru</a>
                        </div>

                        <div class="contacts-mobile__item">
                            <p class="contacts-mobile__label">Телеграм</p>
                            <a class="contacts-mobile__link" href="https://t.me/plombir_flowers" target="_blank" rel="noopener noreferrer">@plombir_flowers</a>
                        </div>

                        <div class="contacts-mobile__item">
                            <p class="contacts-mobile__label">Инстаграм*</p>
                            <a class="contacts-mobile__link" href="https://instagram.com/plombir_flowers" target="_blank" rel="noopener noreferrer">@plombir_flowers</a>
                        </div>
                    </div>

                    <div class="contacts-mobile__address-block">
                        <p class="contacts-mobile__label contacts-mobile__label--home">Наш цветочный дом</p>
                        <a class="contacts-mobile__address" href="${MAPS_URL}" onclick="openMap(event)" target="_blank" rel="noopener noreferrer">
                            <span class="contacts-mobile__pin" aria-hidden="true">📍</span>
                            ул. Кирочная, 8Б
                        </a>
                    </div>

                    <p class="contacts-mobile__notice">
                        Хотим обратить ваше внимание на то, что совершить заказ возможно исключительно по указанному номеру телефона,
                        на нашем сайте и оффлайн в студии. Будьте внимательны!
                    </p>

                    <div class="contacts-mobile__map-wrap">
                        <div id="contacts-map" class="contacts-mobile__map contacts-mobile__map--gray" aria-label="Карта Plombir Flowers"></div>
                    </div>
                </div>
            </div>
        `;
        initContactsMap();
        return;
    }

    if (page === 'delivery') {
        $screenInfo.innerHTML = `
            <div class="info-page info-page--service-mobile">
                ${renderServiceSwitcher('delivery')}
                <div class="service-mobile">
                    <h2 class="service-mobile__title">Доставка</h2>
                    <p class="service-mobile__lead">
                        <strong>Доставляем по СПб и ЛО с 9:30 до 22:30</strong> в выбранном интервале.<br/>
                        <strong>Принимаем заказы ежедневно с 9:00 до 22:00</strong><br/>
                        <strong>Доставка осуществляется только от 4000 ₽.</strong>
                    </p>

                    <p class="service-mobile__text">
                        В праздничные дни и дни, когда движение по городу затруднено, стоимость доставки и интервал могут быть увеличены.
                    </p>

                    <h3 class="service-mobile__subtitle">Самовывоз</h3>
                    <p class="service-mobile__text">
                        Забрать заказ самостоятельно можно в нашем цветочном доме на Кирочной, 8Б, когда вы получите уведомление о его готовности.
                    </p>

                    <h3 class="service-mobile__subtitle">Доставка курьером</h3>
                    <p class="service-mobile__text">
                        Доставку в <strong>трехчасовом интервале</strong> при <strong>заказе от 10 000 руб.</strong> мы осуществим <strong>бесплатно</strong>.
                    </p>
                    <p class="service-mobile__text">
                        Стоимость доставки в трехчасовом интервале рассчитывается индивидуально в зависимости от удаленности адреса.
                        Точную стоимость можно узнать в корзине при оформлении заказа или уточнить у менеджера.
                    </p>

                    <h3 class="service-mobile__subtitle">Сокращенные интервалы</h3>
                    <p class="service-mobile__text">
                        Также возможна доставка в сокращенных интервалах:
                    </p>
                    <ul class="service-mobile__list">
                        <li>в трехчасовом интервале — от 390 ₽ в зависимости от удаленности адреса и <strong>бесплатно</strong> при заказе от <strong>10 000 ₽</strong> (в пределах КАД);</li>
                        <li>в полуторачасовом интервале — тариф <strong>x1.5</strong> к стандартной доставке;</li>
                        <li>к точному времени в интервале 15 минут — тариф <strong>x2</strong> к стандартной доставке.</li>
                    </ul>

                    <h3 class="service-mobile__subtitle">Возврат</h3>
                    <p class="service-mobile__text">
                        Если вы остались недовольны собранным букетом, сообщите нам об этом в течение 2-х часов с момента его получения.
                        Мы заменим его на новый или вернем вам деньги.
                    </p>

                    <h3 class="service-mobile__subtitle">Упаковка и комплектация</h3>
                    <p class="service-mobile__text">
                        Классическая упаковка в стиле Plombir — бумага тишью и матовая пленка, которая делает букет воздушным и объемным.
                        Также каждый букет можно оформить в фирменную транспортировочную коробку в подарок.
                    </p>
                    <p class="service-mobile__text">
                        К каждому букету мы добавляем инструкцию по уходу, средство для сохранения свежести и по желанию фирменную открытку с вашим текстом.
                    </p>
                    <p class="service-mobile__text">
                        Каждый букет мы помещаем на акваножку (мешочек с водой), которая поддерживает свежесть цветов.
                        В студии также доступны картонные аквабоксы для воды (+150 ₽).
                    </p>

                    <p class="service-mobile__text">
                        Для ускорения осуществления доставки наши клиенты часто пользуются сторонним сервисом.
                        Мы можем передать композицию курьеру Яндекс.Доставки и проследить, чтобы заказ приехал целым и невредимым.
                    </p>
                    <p class="service-mobile__text">
                        Если вы хотите сделать сюрприз, мы сами узнаем адрес получателя и доставим букет в удобном для него интервале.
                    </p>
                </div>
            </div>
        `;
        return;
    }

    if (page === 'payment') {
        $screenInfo.innerHTML = `
            <div class="info-page info-page--service-mobile">
                ${renderServiceSwitcher('payment')}
                <div class="service-mobile">
                    <h2 class="service-mobile__title">Оплата</h2>
                    <p class="service-mobile__text">
                        В нашей студии вы можете оплатить заказ наличными или банковской картой.
                    </p>
                    <p class="service-mobile__text">
                        На сайте после оформления заказа автоматически произойдет переход к оплате.
                        Также менеджер может сформировать для вас официальную банковскую ссылку.
                        К оплате принимаются банковские карты VISA, Mastercard, МИР российских банков,
                        возможна оплата по Системе быстрых платежей (СБП).
                    </p>
                    <h3 class="service-mobile__subtitle">Способы оплаты</h3>
                    <ul class="service-mobile__list">
                        <li>Банковской картой или СБП через ЮKassa;</li>
                        <li>Долями от Т-Банк;</li>
                        <li>Яндекс Пэй и Сплит.</li>
                    </ul>
                    <p class="service-mobile__text">
                        Платежи происходят через систему ЮKassa, защищены сертификатом SSL и протоколом 3D Secure.
                        Plombir Flowers не собирает и не хранит платежные данные клиентов.
                    </p>
                    <p class="service-mobile__text">
                        Также мы принимаем оплату иностранной картой. Для уточнения подробностей обращайтесь к менеджеру.
                    </p>
                    <p class="service-mobile__text">
                        Наши менеджеры отправят вам фото готового букета перед тем, как отправить его на доставку.
                    </p>

                    <div class="service-mobile__help">
                        <h3>Мы всегда рады помочь</h3>
                        <p>Если вы не нашли ответа на ваш вопрос, свяжитесь с нами любым удобным способом:</p>
                        <a href="tel:+79819672833">Позвонить +7 981 967 28 33</a>
                        <a href="https://t.me/plombir_flowers" target="_blank" rel="noopener noreferrer">Написать в Telegram</a>
                        <a href="https://wa.me/79819672833" target="_blank" rel="noopener noreferrer">Написать в WhatsApp</a>
                    </div>
                </div>
            </div>
        `;
        return;
    }

    const pages = {
        about: {
            title: 'О нас',
            subtitle: 'Plombir Flowers - студия современной флористики в Санкт-Петербурге.',
            cards: [
                {
                    title: 'Концепция',
                    text: 'Мы собираем букеты в минималистичной эстетике: акцент на форму, фактуру и чистую палитру. Каждый заказ собирается вручную флористом.'
                },
                {
                    title: 'Подход',
                    text: 'Работаем с сезонным цветком, поэтому композиции всегда живые и актуальные. Можно оформить как быстрый заказ, так и индивидуальный запрос.'
                },
                {
                    title: 'Город',
                    text: 'Основная зона работы - Санкт-Петербург. На сайте и в мини-аппе доступен заказ с доставкой и согласованием времени.'
                }
            ]
        },
        contacts: {
            title: 'Контакты',
            subtitle: 'Связаться с нами можно любым удобным способом.',
            cards: [
                {
                    title: 'Телефон',
                    text: '<a href="tel:+79819672833"><strong>+7 981 967-28-33</strong></a>'
                },
                {
                    title: 'Email',
                    text: '<a href="mailto:info@plombirflowers.ru"><strong>info@plombirflowers.ru</strong></a>'
                },
                {
                    title: 'Адрес',
                    text: '<a href="https://yandex.ru/maps/?text=%D0%A1%D0%9F%D0%B1%2C%20%D1%83%D0%BB.%20%D0%9A%D0%B8%D1%80%D0%BE%D1%87%D0%BD%D0%B0%D1%8F%2C%208%D0%91" target="_blank" rel="noopener noreferrer">г. Санкт-Петербург, ул. Кирочная, 8Б</a>'
                },
                {
                    title: 'Сайт',
                    text: '<a href="https://plombirflowers.ru" target="_blank" rel="noopener noreferrer">plombirflowers.ru</a>'
                },
                {
                    title: 'Соцсети',
                    text: '<a href="https://t.me/plombir_flowers" target="_blank" rel="noopener noreferrer">Telegram</a> · <a href="https://wa.me/79819672833" target="_blank" rel="noopener noreferrer">WhatsApp</a>'
                }
            ]
        },
        payment: {
            title: 'Оплата',
            subtitle: 'Все способы оплаты и порядок подтверждения заказа.',
            cards: [
                {
                    title: 'Онлайн-оплата',
                    text: 'Оплата проходит при оформлении заказа в Mini App. После оплаты заказ попадает в обработку.'
                },
                {
                    title: 'Подтверждение',
                    text: 'Менеджер связывается только если нужно уточнить состав, адрес или интервал.'
                },
                {
                    title: 'Важно',
                    text: 'Для срочных заказов рекомендуем указывать корректный телефон и комментарий для курьера.'
                }
            ]
        },
        delivery: {
            title: 'Доставка',
            subtitle: 'Условия доставки в стиле основного сайта.',
            cards: [
                {
                    title: 'Бесплатно',
                    text: 'Бесплатная доставка при заказе от <strong>10 000 ₽</strong> в пределах КАД. Возможна доставка в день заказа при наличии слота.'
                },
                {
                    title: 'Интервалы',
                    text: 'Стандартный 3-часовой интервал, ускоренный 1.5-часовой (коэффициент x1.5), доставка к точному времени (коэффициент x2).'
                },
                {
                    title: 'Адрес и контакт',
                    text: 'Проверьте адрес и телефон получателя перед отправкой — это сокращает время подтверждения и исключает переносы.'
                }
            ]
        }
    };

    const content = pages[page] || pages.about;
    $screenInfo.innerHTML = `
        <div class="info-page">
            <div class="info-page__header">
                <h2 class="info-page__title">${content.title}</h2>
                <p class="info-page__subtitle">${content.subtitle}</p>
            </div>
            <div class="info-page__content">
                ${content.cards.map(card => `
                    <div class="info-card">
                        <div class="info-card__title">${card.title}</div>
                        <div class="info-card__text">${card.text}</div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

function ensureYandexMapsApi() {
    if (window.ymaps) return Promise.resolve(window.ymaps);
    if (yandexMapsPromise) return yandexMapsPromise;

    yandexMapsPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'https://api-maps.yandex.ru/2.1/?lang=ru_RU';
        script.async = true;
        script.onload = () => {
            if (!window.ymaps) {
                reject(new Error('Yandex Maps API not available'));
                return;
            }
            window.ymaps.ready(() => resolve(window.ymaps));
        };
        script.onerror = () => reject(new Error('Failed to load Yandex Maps API'));
        document.head.appendChild(script);
    });

    return yandexMapsPromise;
}

async function initContactsMap() {
    const mapNode = document.getElementById('contacts-map');
    if (!mapNode) return;

    try {
        const ymaps = await ensureYandexMapsApi();
        const currentNode = document.getElementById('contacts-map');
        if (!currentNode) return;

        if (contactsMapInstance && typeof contactsMapInstance.destroy === 'function') {
            contactsMapInstance.destroy();
            contactsMapInstance = null;
        }

        contactsMapInstance = new ymaps.Map('contacts-map', {
            center: CONTACTS_COORDS,
            zoom: 15,
            controls: ['zoomControl'],
        }, {
            suppressMapOpenBlock: true,
            yandexMapDisablePoiInteractivity: true,
        });

        contactsMapInstance.behaviors.disable('scrollZoom');

        const placemark = new ymaps.Placemark(CONTACTS_COORDS, {
            balloonContent: 'Plombir Flowers, ул. Кирочная, 8Б',
            hintContent: 'Plombir Flowers',
        }, {
            preset: 'islands#circleDotIcon',
            iconColor: '#3f3f3f',
        });

        contactsMapInstance.geoObjects.add(placemark);
    } catch (e) {
        mapNode.innerHTML = `
            <iframe
                class="contacts-mobile__map"
                src="https://yandex.ru/map-widget/v1/?text=%D1%83%D0%BB.%20%D0%9A%D0%B8%D1%80%D0%BE%D1%87%D0%BD%D0%B0%D1%8F%2C%208%D0%91%2C%20%D0%A1%D0%B0%D0%BD%D0%BA%D1%82-%D0%9F%D0%B5%D1%82%D0%B5%D1%80%D0%B1%D1%83%D1%80%D0%B3&z=15"
                loading="lazy"
                allowfullscreen
                referrerpolicy="no-referrer-when-downgrade"
                title="Карта Plombir Flowers"
            ></iframe>
        `;
    }
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
        const q = e.target.value.trim();
        state.search = q;
        // При поиске сбрасываем категорию и ценовой фильтр
        if (q) {
            state.categoryId = '';
            state.priceMin = null;
            state.priceMax = null;
            // Визуально сбрасываем активные кнопки
            $categories.querySelectorAll('.category-btn').forEach(b => b.classList.remove('active'));
            const allBtn = $categories.querySelector('[data-id=""]');
            if (allBtn) allBtn.classList.add('active');
            document.querySelectorAll('.price-btn').forEach(b => b.classList.remove('active'));
            const allPriceBtn = document.querySelector('.price-btn[data-min=""]');
            if (allPriceBtn) allPriceBtn.classList.add('active');
        }
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

// ── Закрытие клавиатуры при тапе вне input/textarea ──
document.addEventListener('touchstart', (e) => {
    const active = document.activeElement;
    if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA')) {
        if (!e.target.closest('input, textarea, select, label')) {
            active.blur();
        }
    }
}, { passive: true });

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeMenu();
});

// ── Start ──
init();
setActiveMenuLink('catalog');

document.addEventListener('visibilitychange', () => {
    if (!document.hidden && state.currentScreen === 'catalog') {
        requestAnimationFrame(() => restartTickerAnimation());
    }
});
