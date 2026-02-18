"""
Production runner — запускает FastAPI сервер + Telegram бот в одном процессе.
Используется для деплоя на Railway / Render / и т.д.
"""
import threading
import uvicorn
from backend.config import HOST, PORT, BOT_TOKEN


def run_bot():
    """Запускает бота в отдельном потоке."""
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("⚠️  BOT_TOKEN не указан — бот не запущен")
        return
    try:
        from bot.bot import create_bot
        print("🤖 Запускаю Telegram-бота...")
        app = create_bot()
        app.run_polling()
    except Exception as e:
        print(f"⚠️ Ошибка запуска бота: {e}")


if __name__ == "__main__":
    # Бот в фоновом потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # API сервер (основной поток)
    print(f"🚀 Запускаю API на {HOST}:{PORT}")
    uvicorn.run("backend.app:app", host=HOST, port=PORT)
