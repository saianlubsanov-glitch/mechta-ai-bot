import os

from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

client = AsyncOpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# память диалогов пользователей
user_memory = {}

SYSTEM_PROMPT = """
Ты — AI coach проекта Mechta.ai.

Твоя задача:
- помогать человеку разобраться в мечтах
- помогать убрать внутренние ограничения
- усиливать веру человека в себя
- помогать структурировать цели
- помогать менять мышление
- поддерживать эмоционально

Ты говоришь:
- тепло
- спокойно
- глубоко
- по-человечески

Ты НЕ:
- обещаешь магию
- не говоришь про эзотерику
- не гарантируешь исполнение желаний

Ты помогаешь человеку:
- лучше понимать себя
- видеть внутренние блоки
- двигаться к мечте
"""


async def ask_ai(user_id: int, user_message: str):

    # создаем память для нового пользователя
    if user_id not in user_memory:
        user_memory[user_id] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ]

    # сохраняем сообщение пользователя
    user_memory[user_id].append({
        "role": "user",
        "content": user_message
    })

    try:

        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=user_memory[user_id],
            temperature=0.8,
            max_tokens=500
        )

        ai_reply = response.choices[0].message.content

        # сохраняем ответ ИИ в память
        user_memory[user_id].append({
            "role": "assistant",
            "content": ai_reply
        })

        return ai_reply

    except Exception as e:

        print("AI ERROR:", e)

        return "Сейчас я немного задумался 🤔 Попробуй отправить сообщение ещё раз через пару секунд."
