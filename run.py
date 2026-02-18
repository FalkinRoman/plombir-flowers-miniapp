"""
Точка входа — запуск FastAPI сервера.
Бот запускается отдельно: python -m bot.run
"""
import uvicorn
from backend.config import HOST, PORT

if __name__ == "__main__":
    uvicorn.run("backend.app:app", host=HOST, port=PORT, reload=True)
