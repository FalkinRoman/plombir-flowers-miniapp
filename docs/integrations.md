# Интеграции этапа 3

Ниже минимальный набор переменных для полного запуска оплаты, Split и синхронизаций.

## 1) Yandex Pay Merchant API (основной сценарий) + Split

Документация: [API для бэкенда](https://pay.yandex.ru/docs/ru/custom/backend/yandex-pay-api/), [вебхук](https://pay.yandex.ru/docs/ru/custom/backend/merchant-api-hidden/webhook).

- `YANDEX_PAY_CHECKOUT_ENABLED=1`
- `YANDEX_PAY_MERCHANT_API_KEY=...` — ключ Merchant API из [настроек](https://console.pay.yandex.ru/settings) (заголовок `Authorization: Api-Key …`)
- `YANDEX_PAY_MERCHANT_ID=...` — тот же merchant id (для SDK-бейджей и проверки `merchantId` в JWT вебхука)
- `YANDEX_PAY_RETURN_URL=https://<домен>/app` — база для `redirectUrls` после оплаты (к query добавляются `order_id`, `pay=ok|abort|error`)
- **Callback URL** в личном кабинете Яндекс Пэй: **только базовый HTTPS** без пути `/v1/webhook` (Яндекс сам допишет путь). Пример: `https://<домен>` → запросы на `https://<домен>/v1/webhook`
- `YANDEX_PAY_API_SANDBOX=1` — тестовое окружение (`sandbox.pay.yandex.ru`), в тесте API-ключом часто выступает сам Merchant ID (см. их раздел «Тестирование»)
- `SPLIT_ENABLED=1`, `SPLIT_MONTHS_DEFAULT=4` — только для UI (подсказки); на форме Сплит включается через `availablePaymentMethods` в запросе создания заказа
- `YANDEX_PAY_SDK_URL`, `YANDEX_PAY_THEME` — виджеты на витрине
- `YANDEX_PAY_FISCAL_TAX=<код>` — если в кабинете включена фискализация через Яндекс Пэй: код НДС для каждой позиции корзины + `fiscalContact` (телефон из заказа)

Эндпоинт вебхука в приложении:

- `POST /v1/webhook` — тело: raw JWT (`Content-Type: application/octet-stream`), проверка подписи ES256 по JWKS (`https://pay.yandex.ru/api/jwks` или sandbox)

### Fallback: ЮKassa

Если **не** задан `YANDEX_PAY_MERCHANT_API_KEY`, онлайн-оплата идёт через ЮKassa (`create_payment`), как раньше.

- `YOOKASSA_ENABLED=1`, `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY`, `YOOKASSA_RETURN_URL`
- `YOOKASSA_WEBHOOK_URL`, `YOOKASSA_WEBHOOK_SECRET` — `POST /api/payments/yookassa/webhook`, заголовок `X-Plombir-Webhook-Token`
- `SPLIT_PAYMENT_METHOD_DATA_TYPE=yandex_pay` — для сплита через ЮKassa

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
- `MOYSKLAD_GROUP_ID=...` (опционально)
- `MOYSKLAD_SALES_CHANNEL_ID=...` (опционально)
- `MOYSKLAD_DELIVERY_PRODUCT_CODE=...` (товар "доставка", если нужен отдельной позицией)
- `MOYSKLAD_DEFAULT_AGENT_ID=...` (обязательный контрагент для `customerorder`)

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

## 5) Legacy webhook (совместимость со старой Tilda-схемой)

Если нужно принимать старый payload из кастомного php-скрипта:

- `TILDA_MOYSKLAD_WEBHOOK_ENABLED=1`
- `TILDA_MOYSKLAD_WEBHOOK_TOKEN=<секрет>`
- endpoint: `POST /api/integrations/tilda-moysklad/webhook`
- header: `Token: <TILDA_MOYSKLAD_WEBHOOK_TOKEN>`

Бэкенд:
- принимает payload старого формата,
- создает заказ в локальной БД,
- отправляет заказ в МойСклад по правилам "одиночные по коду / групповые как ручная замена".

## 6) Что остается от заказчика

- Кабинет [console.pay.yandex.ru](https://console.pay.yandex.ru): Merchant API ключ, Callback URL (базовый HTTPS), включённые Сплит/фискализация по их чеклисту.
- Либо (fallback) shopId/secret ЮKassa.
- Домен с HTTPS для Mini App и вебхука `/v1/webhook`.
- Токен МойСклад и бизнес-правила по статусам/резерву.
- Правила баллов (если отличаются от текущего дефолта).

## 7) Автозагрузка hero-баннеров с сайта

Если в `data/ui_content.json` нет локальных баннеров, backend при чтении `/api/ui-content`:
- забирает hero-картинки с `SITE_BANNERS_SOURCE_URL`,
- сохраняет кэш в `data/site_banners_cache.json`,
- использует TTL `SITE_BANNERS_TTL_SECONDS` (по умолчанию 6 часов).

Это нужно для первого запуска без ручного наполнения баннеров.
