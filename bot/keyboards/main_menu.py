from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✨ Новая мечта")],
        [KeyboardButton(text="📂 Мои мечты")]
    ],
    resize_keyboard=True
)
