"""
Запуск Telegram-бота (polling mode для локальной разработки).
"""
from bot.bot import create_bot
from backend.config import BOT_TOKEN


def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("⚠️  Укажи BOT_TOKEN в .env файле!")
        print("   Создай бота через @BotFather и вставь токен.")
        return

    print("🤖 Запускаю бота...")
    app = create_bot()
    app.run_polling()


if __name__ == "__main__":
    main()
