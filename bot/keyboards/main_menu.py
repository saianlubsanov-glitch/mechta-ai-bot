from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Новая мечта", callback_data="dream:new")
    builder.button(text="📂 Мои мечты", callback_data="dream:list")
    builder.adjust(1, 1)
    return builder.as_markup()


def get_open_dream_keyboard(dream_id: int, primary_action: str = "💬 Продолжить") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_map = {
        "💬 Продолжить": f"dream:continue:{dream_id}",
        "🎯 Следующий шаг": f"dream:next:{dream_id}",
        "⚡ Фокус дня": f"dream:focus:{dream_id}",
        "📈 Открыть прогресс": f"dream:progress:{dream_id}",
        "✅ Выполнил": f"dream:focus:{dream_id}",
    }
    builder.button(text=primary_action, callback_data=callback_map.get(primary_action, f"dream:continue:{dream_id}"))
    builder.button(text="⋯ Еще", callback_data=f"dream:menu:{dream_id}")
    builder.adjust(1, 1)
    return builder.as_markup()


def get_dream_secondary_menu_keyboard(dream_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🧠 AI-анализ", callback_data=f"dream:analyze:{dream_id}")
    builder.button(text="📈 Прогресс", callback_data=f"dream:progress:{dream_id}")
    builder.button(text="🎯 Следующий шаг", callback_data=f"dream:next:{dream_id}")
    builder.button(text="⚡ Фокус", callback_data=f"dream:focus:{dream_id}")
    builder.button(text="✏️ Редактировать", callback_data=f"dream:edit:{dream_id}")
    builder.button(text="⏸ Пауза", callback_data=f"dream:pause:{dream_id}")
    builder.button(text="🔙 К мечте", callback_data=f"dream:open:{dream_id}")
    builder.button(text="📂 Мои мечты", callback_data="dream:list")
    builder.adjust(1)
    return builder.as_markup()
