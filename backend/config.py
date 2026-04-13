import os
from pathlib import Path
from dotenv import load_dotenv

_ROOT_DIR = Path(__file__).resolve().parent.parent
_DOTENV_PATH = _ROOT_DIR / ".env"

try:
    if _DOTENV_PATH.exists():
        load_dotenv(dotenv_path=_DOTENV_PATH)
except PermissionError:
    # Не валим приложение, если macOS/TCC не дает читать .env.
    pass

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
YML_FEED_URL = os.getenv("YML_FEED_URL", "")
YML_REFRESH_INTERVAL = int(os.getenv("YML_REFRESH_INTERVAL", "3600"))
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEFAULT_WEBAPP_URL = "https://app-plombirflowers.ru/app"
DEFAULT_YOOKASSA_WEBHOOK_URL = "https://app-plombirflowers.ru/api/payments/yookassa/webhook"
WEBAPP_URL = os.getenv("WEBAPP_URL", DEFAULT_WEBAPP_URL)
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


ADMIN_BOOTSTRAP_EMAIL = os.getenv("ADMIN_BOOTSTRAP_EMAIL", "admin@app-plombirflowers.ru")
ADMIN_BOOTSTRAP_PASSWORD = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "")
ADMIN_SESSION_TTL_SECONDS = _int_env("ADMIN_SESSION_TTL_SECONDS", default=86400)


# Интеграции (этап 3)
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
YOOKASSA_RETURN_URL = os.getenv("YOOKASSA_RETURN_URL", WEBAPP_URL)
YOOKASSA_WEBHOOK_URL = os.getenv("YOOKASSA_WEBHOOK_URL", DEFAULT_YOOKASSA_WEBHOOK_URL)
YOOKASSA_WEBHOOK_SECRET = os.getenv("YOOKASSA_WEBHOOK_SECRET", "")
YOOKASSA_ENABLED = _bool_env("YOOKASSA_ENABLED", default=False)

MOYSKLAD_TOKEN = os.getenv("MOYSKLAD_TOKEN", "")
MOYSKLAD_ORG_ID = os.getenv("MOYSKLAD_ORG_ID", "")
MOYSKLAD_STORE_ID = os.getenv("MOYSKLAD_STORE_ID", "")
MOYSKLAD_GROUP_ID = os.getenv("MOYSKLAD_GROUP_ID", "")
MOYSKLAD_SALES_CHANNEL_ID = os.getenv("MOYSKLAD_SALES_CHANNEL_ID", "")
MOYSKLAD_DELIVERY_PRODUCT_CODE = os.getenv("MOYSKLAD_DELIVERY_PRODUCT_CODE", "")
MOYSKLAD_DEFAULT_AGENT_ID = os.getenv("MOYSKLAD_DEFAULT_AGENT_ID", "")
MOYSKLAD_ENABLED = _bool_env("MOYSKLAD_ENABLED", default=False)

TILDA_MOYSKLAD_WEBHOOK_ENABLED = _bool_env("TILDA_MOYSKLAD_WEBHOOK_ENABLED", default=True)
TILDA_MOYSKLAD_WEBHOOK_TOKEN = os.getenv("TILDA_MOYSKLAD_WEBHOOK_TOKEN", "")

SPLIT_ENABLED = _bool_env("SPLIT_ENABLED", default=True)
SPLIT_MONTHS_DEFAULT = _int_env("SPLIT_MONTHS_DEFAULT", default=4)
# Сплит создаётся через API ЮKassa: тип способа оплаты для редиректа на Яндекс Пэй (Сплит на стороне Яндекса).
# yandex_pay — по умолчанию; bank_card — только отладка (общая страница ЮKassa, сплит может быть недоступен как отдельный сценарий).
SPLIT_PAYMENT_METHOD_DATA_TYPE = (os.getenv("SPLIT_PAYMENT_METHOD_DATA_TYPE", "yandex_pay") or "yandex_pay").strip().lower()
YANDEX_PAY_SDK_URL = os.getenv("YANDEX_PAY_SDK_URL", "https://pay.yandex.ru/sdk/v1/pay.js")
YANDEX_PAY_MERCHANT_ID = os.getenv("YANDEX_PAY_MERCHANT_ID", "")
YANDEX_PAY_THEME = os.getenv("YANDEX_PAY_THEME", "light")

# Прямой Yandex Pay Merchant API (без ЮKassa): https://pay.yandex.ru/docs/ru/custom/backend/yandex-pay-api/
YANDEX_PAY_CHECKOUT_ENABLED = _bool_env("YANDEX_PAY_CHECKOUT_ENABLED", default=True)
YANDEX_PAY_MERCHANT_API_KEY = os.getenv("YANDEX_PAY_MERCHANT_API_KEY", "").strip()
YANDEX_PAY_API_SANDBOX = _bool_env("YANDEX_PAY_API_SANDBOX", default=False)
YANDEX_PAY_API_BASE = (os.getenv("YANDEX_PAY_API_BASE") or "").strip() or (
    "https://sandbox.pay.yandex.ru/api/merchant" if YANDEX_PAY_API_SANDBOX else "https://pay.yandex.ru/api/merchant"
)
YANDEX_PAY_JWKS_URL = (os.getenv("YANDEX_PAY_JWKS_URL") or "").strip() or (
    "https://sandbox.pay.yandex.ru/api/jwks" if YANDEX_PAY_API_SANDBOX else "https://pay.yandex.ru/api/jwks"
)
# Редиректы с платёжной формы (обязательны для онлайн-магазина); по умолчанию как мини-приложение
YANDEX_PAY_RETURN_URL = os.getenv("YANDEX_PAY_RETURN_URL", WEBAPP_URL).strip()
# Если в кабинете включена фискализация через Яндекс Пэй — ставь код НДС для позиций (см. доки ФНС в их мануале)
_ypt = os.getenv("YANDEX_PAY_FISCAL_TAX", "").strip()
try:
    YANDEX_PAY_FISCAL_TAX = int(_ypt) if _ypt != "" else None
except ValueError:
    YANDEX_PAY_FISCAL_TAX = None

# Автозагрузка hero-баннеров с основного сайта при пустом локальном списке
SITE_BANNERS_SOURCE_URL = os.getenv("SITE_BANNERS_SOURCE_URL", "https://plombirflowers.ru")
SITE_BANNERS_TTL_SECONDS = _int_env("SITE_BANNERS_TTL_SECONDS", default=21600)  # 6 часов

LOYALTY_ENABLED = _bool_env("LOYALTY_ENABLED", default=False)
LOYALTY_MAX_PERCENT = _float_env("LOYALTY_MAX_PERCENT", default=30.0)
LOYALTY_RATE = _float_env("LOYALTY_RATE", default=1.0)  # 1 балл = 1 руб по умолчанию

# Категории, которые показываем в каталоге Mini App
# Если пусто — показываем все, кроме скрытых
HIDDEN_CATEGORIES = {
    "177224816201",   # Все (мета-категория)
    "587796225621",   # Идеально дополнит (допы → корзина)
    "864074196761",   # Подарочные сертификаты (отдельный раздел)
    "188415052942",   # Цветочный депозит (услуга)
    "144001936082",   # Новый год (устаревшая сезонная)
    "456982389342",   # Гортензии и георгины (мало товаров, сезонная)
    "809629679861",   # до 6 000₽ (ценовой фильтр)
    "948860458791",   # 6 000–10 000₽
    "278412653381",   # 10 000–15 000₽
    "734105227312",   # 15 000–25 000₽
    "362005716661",   # от 25 000₽
}

# Категории с низким приоритетом в основной ленте (показываем редко, в конце)
LOW_PRIORITY_CATEGORIES = {
    "420440364722",   # Винтаж
    "894097284241",   # Вазы и подарки
}

# Порядок категорий в каталоге Mini App (по id)
# Категории, которых нет в списке — добавятся в конец автоматически
CATEGORY_ORDER = [
    "114950849362",   # Бестселлеры
    "935541013691",   # Онлайн-витрина-10%
    "676801639522",   # Самый сезон
    "524485571551",   # Цветочные композиции
    "215076913311",   # Моно и дуобукеты
    "423266976071",   # Свадебные
    "814545052302",   # Все букеты и композиции
    "994242535771",   # Цветочная подписка
    "379413529441",   # Мастер-классы
    "887895679842",   # Оформление мероприятий
    "420440364722",   # Винтаж
    "894097284241",   # Вазы и подарки
]

# Tilda Store API — для получения мультикатегорийного маппинга (partuids)
TILDA_STORE_API = "https://store.tildaapi.com/api/getproductslist/"
# "Все" мета-категория — через неё получаем все товары из API
TILDA_STORE_ALL_UID = "177224816201"
# recid — ID записи магазина на сайте (первый store-блок)
TILDA_STORE_RECID = "662301126"

# Шаблонный текст, который вырезаем из описаний
BOILERPLATE_TEXTS = [
    "Важно!\nКаждый наш букет уникален. Мы не повторяем букеты 1 в 1.",
    "Важно! Каждый наш букет уникален. Мы не повторяем букеты 1 в 1.",
]
