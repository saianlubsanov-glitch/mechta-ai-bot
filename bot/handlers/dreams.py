from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.main_menu import get_main_menu_keyboard, get_open_dream_keyboard
from bot.services.dream_service import create_user_dream, get_user_dream_by_id, list_user_dreams
from bot.states.dream_states import DreamStates

router = Router()


@router.callback_query(F.data == "menu:main")
async def open_main_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "Главное меню Mechta.ai",
        reply_markup=get_main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "dream:new")
async def new_dream_request(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(DreamStates.waiting_for_dream_title)
    await callback.message.answer("Как называется твоя мечта?")
    await callback.answer()


@router.message(DreamStates.waiting_for_dream_title)
async def save_new_dream(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not message.text:
        return

    title = message.text.strip()
    if not title:
        await message.answer("Название мечты не должно быть пустым. Попробуй еще раз.")
        return

    dream_id = create_user_dream(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        title=title,
    )
    await state.update_data(active_dream_id=dream_id)
    await state.clear()
    await state.update_data(active_dream_id=dream_id)

    await message.answer(
        f"Мечта создана: {title}\n"
        "Контекст активирован. Напиши сообщение, и я продолжу работать с этой мечтой.",
        reply_markup=get_open_dream_keyboard(dream_id),
    )


@router.callback_query(F.data == "dream:list")
async def show_dreams(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return

    dreams = list_user_dreams(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
    )
    if not dreams:
        await callback.message.answer(
            "У тебя пока нет мечт. Нажми «➕ Новая мечта», чтобы создать первую.",
            reply_markup=get_main_menu_keyboard(),
        )
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    for dream in dreams:
        builder.button(
            text=f"✨ {dream['title']}",
            callback_data=f"dream:open:{dream['id']}",
        )
    builder.button(text="🏠 Главное меню", callback_data="menu:main")
    builder.adjust(1)

    await callback.message.answer("Твои мечты:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("dream:open:"))
async def open_dream_context(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        return

    dream_id_raw = callback.data.split(":")[-1]
    if not dream_id_raw.isdigit():
        await callback.answer("Некорректный идентификатор мечты.", show_alert=True)
        return

    dream_id = int(dream_id_raw)
    dream = get_user_dream_by_id(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        dream_id=dream_id,
    )
    if dream is None:
        await callback.answer("Мечта не найдена или недоступна.", show_alert=True)
        return

    await state.update_data(active_dream_id=dream_id)
    await callback.message.answer(
        f"Открыт контекст мечты: {dream['title']}\n"
        "Все следующие сообщения пойдут в этот AI-thread.",
        reply_markup=get_open_dream_keyboard(dream_id),
    )
    await callback.answer()


@router.callback_query(F.data.in_({"feature:focus", "feature:progress"}))
async def feature_stub(callback: CallbackQuery) -> None:
    feature_title = "Фокус" if callback.data == "feature:focus" else "Прогресс"
    await callback.answer()
    await callback.message.answer(
        f"Раздел «{feature_title}» будет реализован в следующем релизе.\n"
        "Базовая архитектура для расширения уже подготовлена."
    )
