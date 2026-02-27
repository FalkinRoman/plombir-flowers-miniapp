# Интеграции этапа 3

Ниже минимальный набор переменных для полного запуска оплаты, Split и синхронизаций.

## 1) ЮKassa + Yandex Pay / Split

- `YOOKASSA_ENABLED=1`
- `YOOKASSA_SHOP_ID=...`
- `YOOKASSA_SECRET_KEY=...`
- `YOOKASSA_RETURN_URL=https://<домен>/app`
- `YOOKASSA_WEBHOOK_URL=https://<домен>/api/payments/yookassa/webhook`
- `YOOKASSA_WEBHOOK_SECRET=<любой_секрет>`
- `SPLIT_ENABLED=1`
- `SPLIT_MONTHS_DEFAULT=4`
- `YANDEX_PAY_SDK_URL=https://pay.yandex.ru/sdk/v1/pay.js`
- `YANDEX_PAY_MERCHANT_ID=<merchant_id>`
- `YANDEX_PAY_THEME=light`

Webhook endpoint (в кабинете ЮKassa указываем `YOOKASSA_WEBHOOK_URL`):

- `POST /api/payments/yookassa/webhook`
- Header: `X-Plombir-Webhook-Token: <YOOKASSA_WEBHOOK_SECRET>`

## 2) Баллы

- `LOYALTY_ENABLED=1`
- `LOYALTY_MAX_PERCENT=30`
- `LOYALTY_RATE=1`

Текущая логика: `1 балл = LOYALTY_RATE руб`, лимит списания `LOYALTY_MAX_PERCENT` от подытога.

## 3) МойСклад (подготовка)

- `MOYSKLAD_ENABLED=1`
- `MOYSKLAD_TOKEN=...`
- `MOYSKLAD_ORG_ID=...`
- `MOYSKLAD_STORE_ID=...`

В этой версии флаг уже проброшен в публичный конфиг API, чтобы фронт/бэк могли включать интеграцию без изменения кода.

## 4) Публичный endpoint для фронта

- `GET /api/integrations/public-config`

Отдает feature-flags (без секретов) для:
- методов оплаты,
- Split,
- баллов,
- МойСклад.

Фронт использует официальный web-sdk Яндекс Пэй/Сплит:
- подключается `pay.js`,
- в карточках/товаре рендерится компонент `yandex-pay-badge`.

## 5) Что остается от заказчика

- shopId/secret ЮKassa + включенный Yandex Pay/Split в кабинете.
- Домен с HTTPS для Mini App и webhook.
- Токен МойСклад и бизнес-правила по статусам/резерву.
- Правила баллов (если отличаются от текущего дефолта).

## 6) Автозагрузка hero-баннеров с сайта

Если в `data/ui_content.json` нет локальных баннеров, backend при чтении `/api/ui-content`:
- забирает hero-картинки с `SITE_BANNERS_SOURCE_URL`,
- сохраняет кэш в `data/site_banners_cache.json`,
- использует TTL `SITE_BANNERS_TTL_SECONDS` (по умолчанию 6 часов).

Это нужно для первого запуска без ручного наполнения баннеров.
