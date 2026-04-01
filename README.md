# UZ Football Collector — Backend

FastAPI + SQLite бэкенд для Telegram Mini App.

## Быстрый старт (локально)

```bash
pip install -r requirements.txt
BOT_TOKEN=your_token uvicorn main:app --reload
```

Открой http://localhost:8000/docs — там интерактивная документация всех эндпоинтов.

## Эндпоинты

| Метод | URL | Описание |
|-------|-----|----------|
| GET | /health | Проверка работы сервера |
| POST | /auth | Логин / регистрация через Telegram |
| GET | /collection | Получить свою коллекцию |
| PUT | /collection | Сохранить коллекцию |
| GET | /leaderboard | Таблица лидеров (топ-20) |

## Авторизация

Все запросы (кроме /health) требуют заголовок:
```
X-Init-Data: <Telegram WebApp initData>
```

В режиме разработки (BOT_TOKEN не задан) можно передать JSON:
```
X-Init-Data: {"id": 123456, "first_name": "Тест"}
```

## Деплой на Railway

1. Создай аккаунт на https://railway.app
2. New Project → Deploy from GitHub (загрузи этот код)
3. В настройках добавь переменную: `BOT_TOKEN=твой_токен_от_BotFather`
4. Railway автоматически запустит через Procfile

## Деплой на Render

1. Создай аккаунт на https://render.com
2. New → Web Service → подключи GitHub
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Добавь Environment Variable: `BOT_TOKEN=твой_токен`

## База данных

SQLite файл `game.db` создаётся автоматически при первом запуске.
Таблица `users`:
- `telegram_id` — ID пользователя Telegram
- `username` — @username
- `first_name` — имя
- `collected` — JSON-массив индексов собранных игроков, например [0, 2, 5]
- `completed_at` — timestamp когда собрал всех (NULL если не завершил)
