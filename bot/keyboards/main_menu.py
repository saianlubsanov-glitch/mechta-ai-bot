from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.callbacks import cb


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Новая мечта", callback_data=cb("dream", "new"))
    builder.button(text="📂 Мои мечты", callback_data=cb("dream", "list"))
    builder.adjust(1, 1)
    return builder.as_markup()


def get_open_dream_keyboard(dream_id: int, primary_action: str = "💬 Продолжить") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_map = {
        "💬 Продолжить": cb("dream", "continue", dream_id),
        "🎯 Следующий шаг": cb("dream", "next", dream_id),
        "⚡ Фокус дня": cb("dream", "focus", dream_id),
        "📈 Открыть прогресс": cb("dream", "progress", dream_id),
        "✅ Выполнил": cb("dream", "focus", dream_id),
    }
    builder.button(text=primary_action, callback_data=callback_map.get(primary_action, cb("dream", "continue", dream_id)))
    builder.button(text="⋯ Еще", callback_data=cb("dream", "menu", dream_id))
    builder.adjust(1, 1)
    return builder.as_markup()


def get_dream_secondary_menu_keyboard(dream_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🧠 AI-анализ", callback_data=cb("dream", "analyze", dream_id))
    builder.button(text="📈 Прогресс", callback_data=cb("dream", "progress", dream_id))
    builder.button(text="🎯 Следующий шаг", callback_data=cb("dream", "next", dream_id))
    builder.button(text="⚡ Фокус", callback_data=cb("dream", "focus", dream_id))
    builder.button(text="✏️ Редактировать", callback_data=cb("dream", "edit", dream_id))
    builder.button(text="⏸ Пауза", callback_data=cb("dream", "pause", dream_id))
    builder.button(text="🔙 К мечте", callback_data=cb("dream", "open", dream_id))
    builder.button(text="📂 Мои мечты", callback_data=cb("dream", "list"))
    builder.adjust(1)
    return builder.as_markup()
