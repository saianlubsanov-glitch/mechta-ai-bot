import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.main_menu import (
    get_dream_manage_keyboard,
    get_main_menu_keyboard,
    get_open_dream_keyboard,
    get_post_release_quick_access_keyboard,
)
from bot.services.ai_service import ai_service
from bot.services.dashboard_service import (
    get_user_mutex,
    open_dashboard_screen,
    render_dashboard,
    should_ignore_double_click,
    update_dashboard,
    validate_dashboard_callback,
)
from bot.services.db_service import (
    archive_dream,
    create_dream_lineage,
    create_user,
    hard_delete_dream_cascade,
    mark_dream_deleted,
    release_dream,
    save_dream_check_insight,
    update_dream_status,
    update_dream_summary,
)
from bot.services.dream_check_service import evaluate_dream_check, get_dream_check_questions
from bot.services.event_service import evaluate_and_store_events
from bot.services.focus_service import generate_daily_focus, get_current_focus
from bot.services.memory_service import save_onboarding_memory
from bot.services.progress_service import build_progress_text, complete_action_task, create_action_task, get_progress_snapshot
from bot.services.dream_service import create_user_dream, get_user_dream_by_id, list_user_dreams
from bot.states.dream_states import DreamStates
from bot.utils.callbacks import cb, parse_callback_data
from bot.utils.telegram_safe import safe_answer

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("menu:main"))
async def open_main_menu(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    if not await validate_dashboard_callback(callback):
        return
    logger.debug("callback received: %s", callback.data)
    await update_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream_id=0,
        screen="main",
        text="Mechta.ai\nВыбери один следующий шаг.",
        reply_markup=get_main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dream:new"))
async def new_dream_request(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    if not await validate_dashboard_callback(callback):
        return
    logger.debug("callback matched: dream:new state_before=%s", await state.get_state())
    await state.clear()
    await state.set_state(DreamStates.waiting_for_dream_title)
    await update_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream_id=0,
        screen="new_dream",
        text="Шаг 1/5\n✨ Как называется твоя мечта?",
        reply_markup=None,
    )
    logger.debug("state_after=%s", await state.get_state())
    await callback.answer()


@router.message(DreamStates.waiting_for_dream_title)
async def onboarding_dream_title(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not message.text:
        return
    title = message.text.strip()
    if not title:
        await safe_answer(message, "Название мечты не должно быть пустым.", user_id=message.from_user.id)
        return
    await state.update_data(onboarding_dream_title=title)
    await state.set_state(DreamStates.waiting_for_why_important)
    await safe_answer(message, "Шаг 2/5\n💛 Почему эта мечта важна для тебя прямо сейчас?", user_id=message.from_user.id)


@router.message(DreamStates.waiting_for_why_important)
async def onboarding_why(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    await state.update_data(onboarding_why=message.text.strip())
    await state.set_state(DreamStates.waiting_for_obstacles)
    await safe_answer(message, "Шаг 3/5\n🧱 Что чаще всего мешает двигаться?", user_id=message.from_user.id)


@router.message(DreamStates.waiting_for_obstacles)
async def onboarding_obstacles(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    await state.update_data(onboarding_obstacles=message.text.strip())
    await state.set_state(DreamStates.waiting_for_emotional_state)
    await safe_answer(message, "Шаг 4/5\n🌡 Как ты себя чувствуешь относительно этой мечты сейчас?", user_id=message.from_user.id)


@router.message(DreamStates.waiting_for_emotional_state)
async def onboarding_emotion(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    await state.update_data(onboarding_emotional_state=message.text.strip())
    await state.set_state(DreamStates.waiting_for_first_focus_task)
    await safe_answer(message, "Шаг 5/5\n🎯 Назови один очень маленький шаг, который сделаешь сегодня.", user_id=message.from_user.id)


@router.message(DreamStates.waiting_for_first_focus_task)
async def onboarding_first_win(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not message.text:
        return
    payload = await state.get_data()
    title = str(payload.get("onboarding_dream_title", "")).strip()
    why = str(payload.get("onboarding_why", "")).strip()
    obstacles = str(payload.get("onboarding_obstacles", "")).strip()
    emotional_state = str(payload.get("onboarding_emotional_state", "")).strip()
    first_task = message.text.strip()
    if not title or not first_task:
        await safe_answer(message, "Давай еще раз: нужна мечта и один первый шаг.", user_id=message.from_user.id)
        return

    user_id = create_user(message.from_user.id, message.from_user.username)
    dream_id = create_user_dream(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        title=title,
    )
    create_action_task(dream_id=dream_id, dream_title=title, task_title=first_task)
    save_onboarding_memory(
        user_id=user_id,
        why_important=why,
        obstacles=obstacles,
        emotional_state=emotional_state,
    )
    await state.clear()
    await state.update_data(active_dream_id=dream_id)
    focus = await generate_daily_focus(dream_id=dream_id, dream_title=title)
    await safe_answer(
        message,
        "Первый quick win зафиксирован ✅\n"
        f"⚡ Фокус дня: {focus['focus_text']}",
        user_id=message.from_user.id,
    )
    await open_dashboard_screen(
        user_id=message.from_user.id,
        message=message,
        dream_id=dream_id,
        screen="dashboard",
        text="Мечта создана. Выбери следующий шаг.",
        reply_markup=get_open_dream_keyboard(dream_id, primary_action="⚡ Фокус дня"),
    )


@router.callback_query(F.data.startswith("dream:list"))
async def show_dreams(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    logger.debug("callback matched: dream:list")
    if not await validate_dashboard_callback(callback):
        return
    dreams = list_user_dreams(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
    )
    if not dreams:
        await update_dashboard(
            user_id=callback.from_user.id,
            message=callback.message,
            dream_id=0,
            screen="dreams_empty",
            text="Пока нет мечт. Начни с «➕ Новая мечта».",
            reply_markup=get_main_menu_keyboard(),
        )
        await callback.answer()
        return
    builder = InlineKeyboardBuilder()
    for dream in dreams:
        builder.button(
            text=f"✨ {dream.get('title', 'Без названия')}",
            callback_data=cb("dream", "open", int(dream.get("id", 0))),
        )
    builder.button(text="🏠 Главное меню", callback_data=cb("menu", "main"))
    builder.adjust(1)
    await update_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream_id=0,
        screen="dreams",
        text="Выбери мечту:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dream:open:"))
async def open_dream_context(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    logger.debug("callback received: %s state_before=%s", callback.data, await state.get_state())
    if not await validate_dashboard_callback(callback):
        return
    parsed = parse_callback_data(callback.data)
    if parsed is None or parsed.entity_id is None:
        await callback.answer("Некорректная команда.", show_alert=True)
        return
    dream_id = parsed.entity_id
    dream = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, dream_id)
    if dream is None:
        await callback.answer("Мечта недоступна.", show_alert=True)
        return
    await state.update_data(active_dream_id=dream_id)
    await render_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream=dream,
        screen="dashboard",
        primary_action="🎯 Следующий шаг",
    )
    logger.debug("dashboard redraw for user=%s dream=%s", callback.from_user.id, dream_id)
    await callback.answer()


@router.callback_query(F.data.startswith("dream:menu:"))
async def open_secondary_menu(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    parsed = parse_callback_data(callback.data)
    dream_id = parsed.entity_id if parsed else None
    if dream_id is None:
        await callback.answer("Некорректная команда.", show_alert=True)
        return
    if not await validate_dashboard_callback(callback):
        return
    await callback.answer()
    dream = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, dream_id)
    if dream is None:
        return
    await render_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream=dream,
        screen="secondary",
        primary_action="🎯 Следующий шаг",
    )


@router.callback_query(F.data.startswith("dream:manage:"))
async def open_dream_manage(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    parsed = parse_callback_data(callback.data)
    dream_id = parsed.entity_id if parsed else None
    if dream_id is None:
        await callback.answer("Некорректная команда.", show_alert=True)
        return
    if not await validate_dashboard_callback(callback):
        return
    dream = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, dream_id)
    if dream is None:
        await callback.answer("Мечта недоступна.", show_alert=True)
        return
    await callback.answer()
    await update_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream_id=dream_id,
        screen="manage",
        text=(
            "Управление мечтой\n\n"
            "Иногда человек перерастает старые желания.\n"
            "Выбери, как ты хочешь бережно обойтись с этой мечтой."
        ),
        reply_markup=get_dream_manage_keyboard(dream_id),
    )


@router.callback_query(F.data.startswith("dream:continue:"))
async def continue_dream_chat(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    parsed = parse_callback_data(callback.data)
    dream_id = parsed.entity_id if parsed else None
    if dream_id is None:
        await callback.answer("Некорректная команда.", show_alert=True)
        return
    if not await validate_dashboard_callback(callback):
        return
    await state.update_data(active_dream_id=dream_id)
    await callback.answer()
    await update_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream_id=dream_id,
        screen="continue",
        text="Окей. Пиши одну мысль/вопрос, и идем следующим шагом.",
        reply_markup=get_open_dream_keyboard(dream_id, primary_action="💬 Продолжить"),
    )


@router.callback_query(F.data.startswith("dream:analyze:"))
async def run_ai_analysis(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    if should_ignore_double_click(callback.from_user.id):
        await callback.answer("Подожди секунду…")
        return
    if not await validate_dashboard_callback(callback):
        return
    parsed = parse_callback_data(callback.data)
    dream_id = parsed.entity_id if parsed else None
    if dream_id is None:
        await callback.answer("Некорректная команда.", show_alert=True)
        return
    async with get_user_mutex(callback.from_user.id):
        logger.debug("callback matched: dream:analyze user=%s", callback.from_user.id)
        dream = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, dream_id)
        if dream is None:
            await callback.answer("Мечта недоступна.", show_alert=True)
            return
        await callback.answer("Анализирую...")
        summary = await ai_service.generate_summary_memory(dream_id=dream_id, dream_title=str(dream.get("title", "")))
        update_dream_summary(dream_id=dream_id, summary=summary)
        refreshed = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, dream_id)
        if refreshed is None:
            return
        await render_dashboard(
            user_id=callback.from_user.id,
            message=callback.message,
            dream=refreshed,
            screen="dashboard",
            primary_action="🎯 Следующий шаг",
        )


@router.callback_query(F.data.startswith("dream:pause:"))
async def pause_dream(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    parsed = parse_callback_data(callback.data)
    dream_id = parsed.entity_id if parsed else None
    if dream_id is None:
        await callback.answer("Некорректная команда.", show_alert=True)
        return
    if not await validate_dashboard_callback(callback):
        return
    update_dream_status(dream_id=dream_id, status="paused")
    await callback.answer("Поставил на паузу.")
    dream = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, dream_id)
    if dream is None:
        return
    await render_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream=dream,
        screen="dashboard",
        primary_action="💬 Продолжить",
    )


@router.callback_query(F.data.startswith("dream:progress:"))
async def progress_dashboard(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    parsed = parse_callback_data(callback.data)
    dream_id = parsed.entity_id if parsed else None
    if dream_id is None:
        await callback.answer("Некорректная команда.", show_alert=True)
        return
    if not await validate_dashboard_callback(callback):
        return
    dream = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, dream_id)
    if dream is None:
        await callback.answer("Мечта недоступна.", show_alert=True)
        return
    await state.update_data(active_dream_id=dream_id)
    snapshot = get_progress_snapshot(dream_id=dream_id, dream_title=str(dream.get("title", "")))
    text = build_progress_text(dream_title=str(dream.get("title", "")), snapshot=snapshot)
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить 1 задачу", callback_data=cb("task", "add", dream_id))
    open_tasks = snapshot["open_tasks"]
    if open_tasks:
        builder.button(text=f"✅ Закрыть: {str(open_tasks[0]['title'])[:22]}", callback_data=f"task:done:{int(open_tasks[0]['id'])}:{dream_id}")
    builder.button(text="🔙 К мечте", callback_data=cb("dream", "open", dream_id))
    builder.adjust(1)
    await callback.answer()
    await update_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream_id=dream_id,
        screen="progress",
        text=text,
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("task:add:"))
async def add_task_start(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    parsed = parse_callback_data(callback.data)
    dream_id = parsed.entity_id if parsed else None
    if dream_id is None:
        await callback.answer("Некорректная команда.", show_alert=True)
        return
    if not await validate_dashboard_callback(callback):
        return
    await state.set_state(DreamStates.waiting_for_task_title)
    await state.update_data(task_dream_id=dream_id)
    await callback.answer()
    await update_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream_id=dream_id,
        screen="task_add",
        text="Напиши одну следующую задачу (1 действие).",
        reply_markup=None,
    )


@router.message(DreamStates.waiting_for_task_title)
async def save_task_title(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not message.text:
        return
    title = message.text.strip()
    data = await state.get_data()
    dream_id = data.get("task_dream_id")
    if not title or not isinstance(dream_id, int):
        await safe_answer(message, "Нужен короткий текст задачи.", user_id=message.from_user.id)
        return
    dream = get_user_dream_by_id(message.from_user.id, message.from_user.username, dream_id)
    if dream is None:
        await state.clear()
        return
    create_action_task(dream_id=dream_id, dream_title=str(dream.get("title", "")), task_title=title)
    await state.clear()
    await state.update_data(active_dream_id=dream_id)
    await safe_answer(
        message,
        "Задача добавлена ✅",
        user_id=message.from_user.id,
    )
    await open_dashboard_screen(
        user_id=message.from_user.id,
        message=message,
        dream_id=dream_id,
        screen="dashboard",
        text="Задача добавлена. Продолжим движение.",
        reply_markup=get_open_dream_keyboard(dream_id, primary_action="📈 Открыть прогресс"),
    )


@router.callback_query(F.data.startswith("task:done:"))
async def complete_task_flow(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    raw = callback.data.split("|v=", maxsplit=1)[0]
    parts = raw.split(":")
    task_id = int(parts[2])
    dream_id = int(parts[3])
    if not await validate_dashboard_callback(callback):
        return
    updated_dream_id = complete_action_task(task_id=task_id)
    if updated_dream_id is None:
        await callback.answer("Задача не найдена.", show_alert=True)
        return
    evaluate_and_store_events(dream_id=dream_id)
    await callback.answer("Отлично, шаг закрыт 🔥")
    dream = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, updated_dream_id)
    if dream is None:
        return
    await render_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream=dream,
        screen="dashboard",
        primary_action="🎯 Следующий шаг",
    )


@router.callback_query(F.data.startswith("dream:next:"))
async def next_step_flow(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    parsed = parse_callback_data(callback.data)
    dream_id = parsed.entity_id if parsed else None
    if dream_id is None:
        await callback.answer("Некорректная команда.", show_alert=True)
        return
    if not await validate_dashboard_callback(callback):
        return
    dream = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, dream_id)
    if dream is None:
        await callback.answer("Мечта недоступна.", show_alert=True)
        return
    step = await ai_service.generate_next_step(dream_id=dream_id, dream_title=str(dream.get("title", "")))
    await callback.answer()
    await update_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream_id=dream_id,
        screen="next",
        text=f"🎯 Next best action:\n{step}",
        reply_markup=get_open_dream_keyboard(dream_id, primary_action="💬 Продолжить"),
    )


@router.callback_query(F.data.startswith("dream:focus:"))
async def focus_flow(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    parsed = parse_callback_data(callback.data)
    dream_id = parsed.entity_id if parsed else None
    if dream_id is None:
        await callback.answer("Некорректная команда.", show_alert=True)
        return
    if not await validate_dashboard_callback(callback):
        return
    dream = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, dream_id)
    if dream is None:
        await callback.answer("Мечта недоступна.", show_alert=True)
        return
    focus = get_current_focus(dream_id=dream_id)
    if not focus["focus_text"]:
        focus = await generate_daily_focus(dream_id=dream_id, dream_title=str(dream.get("title", "")))
    builder = InlineKeyboardBuilder()
    if isinstance(focus["focus_task_id"], int):
        builder.button(text="✅ Выполнил", callback_data=f"task:done:{focus['focus_task_id']}:{dream_id}")
    builder.button(text="🔄 Обновить", callback_data=cb("focus", "refresh", dream_id))
    builder.button(text="🔙 К мечте", callback_data=cb("dream", "open", dream_id))
    builder.adjust(1)
    await callback.answer()
    await update_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream_id=dream_id,
        screen="focus",
        text=f"⚡ Фокус дня\n{focus['focus_text']}",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("dream:check:"))
async def start_dream_check(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    parsed = parse_callback_data(callback.data)
    dream_id = parsed.entity_id if parsed else None
    if dream_id is None:
        await callback.answer("Некорректная команда.", show_alert=True)
        return
    if not await validate_dashboard_callback(callback):
        return
    dream = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, dream_id)
    if dream is None:
        await callback.answer("Мечта недоступна.", show_alert=True)
        return
    update_dream_status(dream_id=dream_id, status="questioned")
    questions = get_dream_check_questions()
    await state.update_data(
        active_dream_id=dream_id,
        dream_check_answers=[],
        dream_check_title=str(dream.get("title", "")),
    )
    await state.set_state(DreamStates.dream_check_step_1)
    await callback.answer()
    await update_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream_id=dream_id,
        screen="dream_check",
        text=f"🧠 Проверка мечты\nШаг 1/5\n{questions[0]}",
        reply_markup=get_open_dream_keyboard(dream_id, primary_action="💬 Продолжить"),
    )


@router.callback_query(F.data.startswith("dream:archive:"))
async def archive_dream_flow(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    parsed = parse_callback_data(callback.data)
    dream_id = parsed.entity_id if parsed else None
    if dream_id is None:
        await callback.answer("Некорректная команда.", show_alert=True)
        return
    if not await validate_dashboard_callback(callback):
        return
    dream = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, dream_id)
    if dream is None:
        await callback.answer("Мечта недоступна.", show_alert=True)
        return
    archive_dream(dream_id)
    await state.update_data(active_dream_id=None)
    await state.set_state(DreamStates.waiting_action)
    await callback.answer("Мечта архивирована.")
    await update_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream_id=0,
        screen="post_archive",
        text=(
            "📦 Мечта архивирована.\n"
            "Это не отказ. Просто не сейчас."
        ),
        reply_markup=get_post_release_quick_access_keyboard(),
    )


@router.callback_query(F.data.startswith("dream:release:"))
async def release_dream_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    parsed = parse_callback_data(callback.data)
    dream_id = parsed.entity_id if parsed else None
    if dream_id is None:
        await callback.answer("Некорректная команда.", show_alert=True)
        return
    if not await validate_dashboard_callback(callback):
        return
    await state.update_data(manage_dream_id=dream_id, manage_action="release")
    await state.set_state(DreamStates.dream_release_reflection)
    await callback.answer()
    await update_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream_id=dream_id,
        screen="release_reflection",
        text=(
            "🌙 Похоже, эта мечта больше не ощущается живой.\n\n"
            "Что ты понял благодаря этой мечте?"
        ),
        reply_markup=get_open_dream_keyboard(dream_id, primary_action="💬 Продолжить"),
    )


@router.callback_query(F.data.startswith("dream:delete:"))
async def delete_dream_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    parsed = parse_callback_data(callback.data)
    dream_id = parsed.entity_id if parsed else None
    if dream_id is None:
        await callback.answer("Некорректная команда.", show_alert=True)
        return
    if not await validate_dashboard_callback(callback):
        return
    await state.update_data(manage_dream_id=dream_id, manage_action="delete")
    await state.set_state(DreamStates.dream_release_reflection)
    await callback.answer()
    await update_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream_id=dream_id,
        screen="delete_reflection",
        text=(
            "🗑 Перед тем как отпустить это полностью:\n"
            "Что ты понял благодаря этой мечте?"
        ),
        reply_markup=get_open_dream_keyboard(dream_id, primary_action="💬 Продолжить"),
    )


async def _handle_dream_check_step(message: Message, state: FSMContext, step: int) -> None:
    if message.from_user is None or not message.text:
        return
    data = await state.get_data()
    dream_id = data.get("active_dream_id")
    if not isinstance(dream_id, int):
        await state.clear()
        return
    answers = list(data.get("dream_check_answers", []))
    answers.append(message.text.strip())
    questions = get_dream_check_questions()

    if step < 5:
        await state.update_data(dream_check_answers=answers)
        next_step = step + 1
        next_state = getattr(DreamStates, f"dream_check_step_{next_step}")
        await state.set_state(next_state)
        await safe_answer(
            message,
            f"Шаг {next_step}/5\n{questions[next_step - 1]}",
            user_id=message.from_user.id,
        )
        return

    result = evaluate_dream_check(answers)
    status_map = {
        "validated": "active",
        "evolving": "evolving",
        "dissolved": "archived",
    }
    update_dream_status(dream_id=dream_id, status=status_map[result.outcome])
    save_dream_check_insight(
        dream_id=dream_id,
        outcome=result.outcome,
        fear_patterns=result.fear_patterns,
        shame_triggers=result.shame_triggers,
        external_validation_dependency=result.external_validation_dependency,
        intrinsic_motivation=result.intrinsic_motivation,
        energy_resonance=result.energy_resonance,
        avoidance_signals=result.avoidance_signals,
    )

    await state.update_data(dream_check_answers=answers)
    if result.outcome == "evolving":
        await state.set_state(DreamStates.waiting_reflection)
        await safe_answer(
            message,
            (
                f"{result.summary}\n\n"
                "Хочешь создать новую, более настоящую версию этой мечты?\n"
                "Напиши: да / нет"
            ),
            user_id=message.from_user.id,
        )
    elif result.outcome == "dissolved":
        await state.set_state(DreamStates.waiting_action)
        await safe_answer(
            message,
            (
                f"{result.summary}\n\n"
                "Мы можем бережно отпустить эту цель и выбрать более живое направление."
            ),
            user_id=message.from_user.id,
        )
    else:
        await state.set_state(DreamStates.waiting_action)
        await safe_answer(
            message,
            f"{result.summary}\n\nМечта подтверждена. Продолжай мягким, живым шагом.",
            user_id=message.from_user.id,
        )


@router.message(DreamStates.dream_check_step_1)
async def dream_check_step_1(message: Message, state: FSMContext) -> None:
    await _handle_dream_check_step(message, state, 1)


@router.message(DreamStates.dream_check_step_2)
async def dream_check_step_2(message: Message, state: FSMContext) -> None:
    await _handle_dream_check_step(message, state, 2)


@router.message(DreamStates.dream_check_step_3)
async def dream_check_step_3(message: Message, state: FSMContext) -> None:
    await _handle_dream_check_step(message, state, 3)


@router.message(DreamStates.dream_check_step_4)
async def dream_check_step_4(message: Message, state: FSMContext) -> None:
    await _handle_dream_check_step(message, state, 4)


@router.message(DreamStates.dream_check_step_5)
async def dream_check_step_5(message: Message, state: FSMContext) -> None:
    await _handle_dream_check_step(message, state, 5)


@router.message(DreamStates.waiting_reflection)
async def handle_dream_evolution_confirmation(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not message.text:
        return
    text = message.text.strip().lower()
    data = await state.get_data()
    dream_id = data.get("active_dream_id")
    if not isinstance(dream_id, int):
        await state.clear()
        return
    dream = get_user_dream_by_id(message.from_user.id, message.from_user.username, dream_id)
    if dream is None:
        await state.clear()
        return

    if text in {"да", "yes", "ага"}:
        await state.set_state(DreamStates.waiting_commitment)
        await safe_answer(
            message,
            "Как назвать новую, более настоящую версию этой мечты?",
            user_id=message.from_user.id,
        )
        return
    await state.set_state(DreamStates.waiting_action)
    await safe_answer(
        message,
        "Принято. Продолжаем с текущей мечтой и бережным темпом.",
        user_id=message.from_user.id,
    )


@router.message(DreamStates.dream_release_reflection)
async def handle_release_reflection(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not message.text:
        return
    data = await state.get_data()
    dream_id = data.get("manage_dream_id")
    manage_action = data.get("manage_action")
    reflection = message.text.strip()
    if not isinstance(dream_id, int) or manage_action not in {"release", "delete"}:
        await state.clear()
        return
    if manage_action == "release":
        release_dream(dream_id=dream_id, reflection_text=reflection)
        await state.set_state(DreamStates.waiting_action)
        await safe_answer(
            message,
            "🌙 Мечта отпущена.\nИногда это и есть честный шаг к себе.",
            user_id=message.from_user.id,
        )
        await open_dashboard_screen(
            user_id=message.from_user.id,
            message=message,
            dream_id=0,
            screen="post_release",
            text="🌙 Мечта отпущена. Выбери следующий мягкий шаг.",
            reply_markup=get_post_release_quick_access_keyboard(),
        )
        return

    mark_dream_deleted(dream_id=dream_id, reflection_text=reflection)
    await state.set_state(DreamStates.dream_delete_confirmation)
    await state.update_data(delete_reflection=reflection)
    await safe_answer(
        message,
        "Это действие нельзя отменить.\nЕсли ты уверен, напиши: УДАЛИТЬ",
        user_id=message.from_user.id,
    )


@router.message(DreamStates.dream_delete_confirmation)
async def confirm_hard_delete(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not message.text:
        return
    data = await state.get_data()
    dream_id = data.get("manage_dream_id")
    if not isinstance(dream_id, int):
        await state.clear()
        return
    if message.text.strip().upper() != "УДАЛИТЬ":
        await safe_answer(
            message,
            "Удаление отменено. Чтобы удалить, напиши точное слово: УДАЛИТЬ",
            user_id=message.from_user.id,
        )
        return
    hard_delete_dream_cascade(dream_id=dream_id)
    await state.set_state(DreamStates.waiting_action)
    await state.update_data(active_dream_id=None, manage_dream_id=None, manage_action=None)
    await safe_answer(
        message,
        "🗑 Мечта и связанные данные удалены.",
        user_id=message.from_user.id,
    )
    await open_dashboard_screen(
        user_id=message.from_user.id,
        message=message,
        dream_id=0,
        screen="post_delete",
        text="🗑 Мечта удалена. Можно выбрать новую точку фокуса.",
        reply_markup=get_post_release_quick_access_keyboard(),
    )


@router.message(DreamStates.waiting_commitment)
async def create_evolved_dream(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not message.text:
        return
    new_title = message.text.strip()
    if not new_title:
        await safe_answer(message, "Нужно название новой версии мечты.", user_id=message.from_user.id)
        return
    data = await state.get_data()
    old_dream_id = data.get("active_dream_id")
    if not isinstance(old_dream_id, int):
        await state.clear()
        return
    new_dream_id = create_user_dream(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        title=new_title,
    )
    update_dream_status(old_dream_id, "evolving")
    create_dream_lineage(from_dream_id=old_dream_id, to_dream_id=new_dream_id)
    await state.update_data(active_dream_id=new_dream_id)
    await state.set_state(DreamStates.waiting_action)
    await safe_answer(
        message,
        f"Создана новая версия мечты: {new_title}\nСтарая мечта сохранена в линии эволюции.",
        user_id=message.from_user.id,
    )
    await open_dashboard_screen(
        user_id=message.from_user.id,
        message=message,
        dream_id=new_dream_id,
        screen="dashboard",
        text=f"Создана новая версия мечты: {new_title}",
        reply_markup=get_open_dream_keyboard(new_dream_id, primary_action="🎯 Следующий шаг"),
    )


@router.callback_query(F.data.startswith("focus:refresh:"))
async def refresh_focus(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    parsed = parse_callback_data(callback.data)
    dream_id = parsed.entity_id if parsed else None
    if dream_id is None:
        await callback.answer("Некорректная команда.", show_alert=True)
        return
    if not await validate_dashboard_callback(callback):
        return
    dream = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, dream_id)
    if dream is None:
        await callback.answer("Мечта недоступна.", show_alert=True)
        return
    focus = await generate_daily_focus(dream_id=dream_id, dream_title=str(dream.get("title", "")))
    await callback.answer("Обновил.")
    await update_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream_id=dream_id,
        screen="focus",
        text=f"⚡ Новый фокус\n{focus['focus_text']}",
        reply_markup=get_open_dream_keyboard(dream_id, primary_action="✅ Выполнил"),
    )


@router.callback_query(F.data.startswith("dream:edit:"))
async def edit_stub(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return
    if not await validate_dashboard_callback(callback):
        return
    await callback.answer()
    await update_dashboard(
        user_id=callback.from_user.id,
        message=callback.message,
        dream_id=0,
        screen="edit",
        text="Редактирование будет в отдельном guided flow.",
        reply_markup=get_main_menu_keyboard(),
    )
