# Прод-деплой: Timeweb + REG.RU

Ниже финальный чеклист запуска `app-plombirflowers.ru` в прод.

## 1) Что уже готово в проекте

- Checkout + ЮKassa (redirect + webhook + возврат в Mini App).
- Yandex Pay / Split компоненты.
- Заказы и статусы в боте: `Оплачен -> Флорист -> Курьер -> Доставлен`.
- Синхронизация в МойСклад:
  - одиночные товары по коду;
  - групповые как ручная замена менеджером.
- Совместимость со старым Tilda payload:
  - `POST /api/integrations/tilda-moysklad/webhook`
  - header `Token: <TILDA_MOYSKLAD_WEBHOOK_TOKEN>`.

## 2) Что нужно от заказчика (минимум)

- `BOT_TOKEN` (из BotFather).
- `YML_FEED_URL` (ссылка на YML фид Тильды).
- `YANDEX_PAY_MERCHANT_ID`.
- `MOYSKLAD_DELIVERY_PRODUCT_CODE` (код товара "Доставка" в МойСклад, если доставка отдельной позицией).

Остальные ключи и id в проекте уже учтены.

## 3) Подготовка сервера в Timeweb

1. Создать сервер (Ubuntu 22.04+, 2 vCPU, 2-4 GB RAM).
2. Подключить проект из GitHub (или залить вручную).
3. Установить Python 3.10+ и зависимости:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

4. Создать `.env` на сервере по `env.example.txt`.
5. Запуск приложения:

```bash
python start.py
```

6. Проверка:
- `GET /api/status`
- `GET /api/integrations/public-config`

## 4) DNS в REG.RU

Для `app-plombirflowers.ru`:
- добавить `A`-запись на IP сервера Timeweb
  (или `CNAME`, если Timeweb выдаст хост-алиас).

После обновления DNS:
- выпустить SSL (Let's Encrypt),
- убедиться, что открывается `https://app-plombirflowers.ru/app`.

## 5) ЮKassa

В кабинете ЮKassa:
- `return_url`: `https://app-plombirflowers.ru/app`
- webhook URL: `https://app-plombirflowers.ru/api/payments/yookassa/webhook`
- секрет webhook: тот же, что в `YOOKASSA_WEBHOOK_SECRET`.

## 6) Legacy webhook (если нужен старый поток)

Если старый php-скрипт заказчика продолжит отправлять данные:
- endpoint: `POST https://app-plombirflowers.ru/api/integrations/tilda-moysklad/webhook`
- header: `Token: <TILDA_MOYSKLAD_WEBHOOK_TOKEN>`

## 7) Финальная проверка перед запуском

1. Создать тестовый заказ с оплатой картой.
2. Убедиться, что платеж завершился и статус обновился.
3. Проверить, что заказ пришел в МойСклад.
4. Проверить, что бот видит заказ и меняет статусы.
5. Проверить уведомления клиенту о смене статуса.
