from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import Message

from bot.keyboards.main_menu import get_main_menu_keyboard
from bot.services.dashboard_service import get_dashboard_state, update_dashboard_by_id
from bot.services.dream_service import ensure_user, get_user_dream_by_id, list_user_dreams
from bot.states.dream_states import DreamStates
from bot.utils.callbacks import cb
from bot.utils.telegram_safe import safe_answer

router = Router()


async def _render_command_screen(
    message: Message,
    state: FSMContext,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    screen: str,
    dream_id: int = 0,
) -> None:
    if message.from_user is None:
        return
    dash_state = get_dashboard_state(user_id=message.from_user.id)
    if dash_state.active_message_id:
        edited = await update_dashboard_by_id(
            bot=message.bot,
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            message_id=dash_state.active_message_id,
            dream_id=dream_id,
            screen=screen,
            text=text,
            reply_markup=reply_markup,
        )
        if edited:
            return
    sent = await safe_answer(
        message,
        text,
        reply_markup=reply_markup,
        user_id=message.from_user.id,
    )
    if sent:
        await state.update_data(active_dream_id=dream_id if dream_id > 0 else None)


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    ensure_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
    )
    await state.clear()
    await _render_command_screen(
        message,
        state,
        text=(
            "Привет! Я твой AI-коуч Mechta.\n"
            "Каждая мечта живет в отдельном контексте, и я помогаю двигаться по каждой из них отдельно."
        ),
        reply_markup=get_main_menu_keyboard(),
        screen="menu",
    )


@router.message(Command("menu"))
async def command_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _render_command_screen(
        message,
        state,
        text="Mechta.ai\nВыбери один следующий шаг.",
        reply_markup=get_main_menu_keyboard(),
        screen="menu",
    )


@router.message(Command("dreams"))
async def command_dreams(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    await state.clear()
    dreams = list_user_dreams(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
    )
    if not dreams:
        await _render_command_screen(
            message,
            state,
            text="Пока нет мечт. Нажми «➕ Новая мечта».",
            reply_markup=get_main_menu_keyboard(),
            screen="dreams_empty",
        )
        return
    builder = InlineKeyboardBuilder()
    for dream in dreams:
        builder.button(
            text=f"✨ {dream.get('title', 'Без названия')}",
            callback_data=cb("dream", "open", int(dream.get("id", 0))),
        )
    builder.button(text="🏠 Главное меню", callback_data=cb("menu", "main"))
    builder.adjust(1)
    await _render_command_screen(
        message,
        state,
        text="Твои мечты:",
        reply_markup=builder.as_markup(),
        screen="dreams",
    )


@router.message(Command("new"))
async def command_new(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(DreamStates.waiting_for_dream_title)
    await _render_command_screen(
        message,
        state,
        text="Шаг 1/5\n✨ Как называется твоя мечта?",
        reply_markup=get_main_menu_keyboard(),
        screen="new_dream",
    )


async def _render_dream_action_command(
    message: Message,
    state: FSMContext,
    *,
    action: str,
    title: str,
) -> None:
    if message.from_user is None:
        return
    state_data = await state.get_data()
    active_dream_id = state_data.get("active_dream_id")
    if isinstance(active_dream_id, int):
        dream = get_user_dream_by_id(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            dream_id=active_dream_id,
        )
        if dream is not None:
            builder = InlineKeyboardBuilder()
            builder.button(text=title, callback_data=cb("dream", action, active_dream_id))
            builder.button(text="📂 Мои мечты", callback_data=cb("dream", "list"))
            builder.adjust(1)
            await _render_command_screen(
                message,
                state,
                text=f"Текущая мечта: {dream['title']}\nНажми, чтобы открыть {title.lower()}",
                reply_markup=builder.as_markup(),
                screen=f"cmd_{action}",
                dream_id=active_dream_id,
            )
            return
    await command_dreams(message, state)


@router.message(Command("focus"))
async def command_focus(message: Message, state: FSMContext) -> None:
    await _render_dream_action_command(
        message,
        state,
        action="focus",
        title="🔥 Фокус дня",
    )


@router.message(Command("progress"))
async def command_progress(message: Message, state: FSMContext) -> None:
    await _render_dream_action_command(
        message,
        state,
        action="progress",
        title="📈 Прогресс",
    )


@router.message(Command("check"))
async def command_check(message: Message, state: FSMContext) -> None:
    await _render_dream_action_command(
        message,
        state,
        action="check",
        title="🧠 Проверить мечту",
    )


@router.message(Command("pause"))
async def command_pause(message: Message, state: FSMContext) -> None:
    await state.set_state(DreamStates.waiting_action)
    await _render_command_screen(
        message,
        state,
        text=(
            "Пауза — это не откат.\n"
            "Вернись к себе, а затем выбери один мягкий шаг."
        ),
        reply_markup=get_main_menu_keyboard(),
        screen="pause",
    )


@router.message(Command("help"))
async def command_help(message: Message, state: FSMContext) -> None:
    await _render_command_screen(
        message,
        state,
        text=(
            "Как работает mechta.ai:\n"
            "1) Выбираешь мечту.\n"
            "2) Двигаешься маленькими шагами.\n"
            "3) Проверяешь, что мечта остается живой через /check."
        ),
        reply_markup=get_main_menu_keyboard(),
        screen="help",
    )
