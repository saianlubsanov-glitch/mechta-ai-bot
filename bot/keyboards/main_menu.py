from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Новая мечта", callback_data="dream:new")
    builder.button(text="📂 Мои мечты", callback_data="dream:list")
    builder.button(text="🔥 Фокус", callback_data="feature:focus")
    builder.button(text="📈 Прогресс", callback_data="feature:progress")
    builder.adjust(1)
    return builder.as_markup()


def get_open_dream_keyboard(dream_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💬 Открыть контекст", callback_data=f"dream:open:{dream_id}")
    builder.button(text="📂 Мои мечты", callback_data="dream:list")
    builder.button(text="🏠 Главное меню", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()
