# mechta-ai-bot — что изменилось в v2

## 🆕 Новые файлы

### `bot/storage/sqlite_storage.py`
**FSM persistence через SQLite**
- Состояния пользователей (активная мечта, шаг онбординга) теперь хранятся в `database/fsm.db`
- Бот после рестарта помнит, на каком экране был пользователь
- Убирает "Экран устарел" при перезапуске
- Нулевые внешние зависимости — только SQLite который уже есть

### `bot/services/alert_service.py`
**Алерты в Telegram при критических ошибках**
- Настройка: добавь `ADMIN_CHAT_ID=<твой_id>` в `.env`
- Чтобы узнать свой chat_id: напиши @userinfobot в Telegram
- Rate limiting: не более 1 алерта одного типа за 5 минут (без спама)
- Безопасный: никогда не поднимает исключений, не ломает бота

### `bot/middleware/rate_limiter.py`
**Rate limiting — защита от флуда**
- Скользящее окно: 20 сообщений / 60 секунд на пользователя (настраивается в `.env`)
- При превышении: мягкое предупреждение раз в 30 секунд
- Защищает бюджет DeepSeek API от одного флудящего пользователя

### Новые промпты в `bot/prompts/`
Каждая AI-функция теперь имеет свой специализированный промпт:
- `next_step_prompt.txt` — один actionable микро-шаг до 140 символов
- `summary_prompt.txt` — краткое резюме прогресса 2-3 предложения
- `reflection_prompt.txt` — deep personal reflection о трансформации
- `memory_compress_prompt.txt` — сжатие памяти в 7 поведенческих секций
- `focus_prompt.txt` — daily focus с мягким подходом к сопротивлению
- `diagnostic_prompt.txt` — коучинговый анализ в 4 строки

## ✏️ Изменённые файлы

### `bot/main.py`
- Подключён `SQLiteFSMStorage` как хранилище FSM
- Подключён `RateLimiterMiddleware`
- Увеличен aiohttp timeout до 60s (был дефолтный ~5s)

### `bot/services/ai_service.py`
- Каждый метод использует свой специализированный промпт
- Добавлен глобальный семафор `_MAX_CONCURRENT_AI=3` — не более 3 параллельных запросов к DeepSeek
- Улучшен парсинг `compress_identity_memory` с валидацией качества

### `bot/handlers/chat.py`
- Промежуточные статусы при AI запросе: "Считываю контекст... → Анализирую путь... → Формулирую ответ..."
- Пользователь видит прогресс вместо 30 секунд тишины

### `bot/handlers/dreams.py`
- `invalidate_next_step_cache` вызывается после завершения задачи — дашборд сразу показывает актуальный следующий шаг

### `bot/services/scheduler_service.py`
- Добавлен `fire_alert` при сбое цикла планировщика

### `.env`
Добавлены новые переменные:
```
ADMIN_CHAT_ID=           # твой Telegram ID для алертов
RATE_LIMIT_MESSAGES=20   # лимит сообщений в окне
RATE_LIMIT_WINDOW_SECONDS=60  # размер окна
```

## 🚀 Как деплоить

```bash
# 1. Загрузи файлы на сервер (замени содержимое папки)
# 2. Заполни ADMIN_CHAT_ID в .env
# 3. Перезапусти бота

# Вручную:
pkill -f "python.*main.py"
source venv/bin/activate
python -m bot.main

# Через systemd:
systemctl restart mechta-bot
```

Файл `database/fsm.db` создаётся автоматически при первом запуске.
