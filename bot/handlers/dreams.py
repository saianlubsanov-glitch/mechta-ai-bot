from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.main_menu import (
    get_dream_secondary_menu_keyboard,
    get_main_menu_keyboard,
    get_open_dream_keyboard,
)
from bot.services.ai_service import ai_service
from bot.services.dashboard_service import build_dream_dashboard_text
from bot.services.db_service import create_user, update_dream_status, update_dream_summary
from bot.services.event_service import evaluate_and_store_events, get_next_event_prompt
from bot.services.focus_service import generate_daily_focus, get_current_focus
from bot.services.memory_service import save_onboarding_memory
from bot.services.progress_service import (
    build_progress_text,
    complete_action_task,
    create_action_task,
    get_progress_snapshot,
)
from bot.services.dream_service import create_user_dream, get_user_dream_by_id, list_user_dreams
from bot.states.dream_states import DreamStates

router = Router()


@router.callback_query(F.data == "menu:main")
async def open_main_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "Mechta.ai\nВыбери один следующий шаг.",
        reply_markup=get_main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "dream:new")
async def new_dream_request(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(DreamStates.waiting_for_dream_title)
    await callback.message.answer("Шаг 1/5\n✨ Как называется твоя мечта?")
    await callback.answer()


@router.message(DreamStates.waiting_for_dream_title)
async def onboarding_dream_title(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not message.text:
        return
    title = message.text.strip()
    if not title:
        await message.answer("Название мечты не должно быть пустым.")
        return
    await state.update_data(onboarding_dream_title=title)
    await state.set_state(DreamStates.waiting_for_why_important)
    await message.answer("Шаг 2/5\n💛 Почему эта мечта важна для тебя прямо сейчас?")


@router.message(DreamStates.waiting_for_why_important)
async def onboarding_why(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    await state.update_data(onboarding_why=message.text.strip())
    await state.set_state(DreamStates.waiting_for_obstacles)
    await message.answer("Шаг 3/5\n🧱 Что чаще всего мешает двигаться?")


@router.message(DreamStates.waiting_for_obstacles)
async def onboarding_obstacles(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    await state.update_data(onboarding_obstacles=message.text.strip())
    await state.set_state(DreamStates.waiting_for_emotional_state)
    await message.answer("Шаг 4/5\n🌡 Как ты себя чувствуешь относительно этой мечты сейчас?")


@router.message(DreamStates.waiting_for_emotional_state)
async def onboarding_emotion(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    await state.update_data(onboarding_emotional_state=message.text.strip())
    await state.set_state(DreamStates.waiting_for_first_focus_task)
    await message.answer("Шаг 5/5\n🎯 Назови один очень маленький шаг, который сделаешь сегодня.")


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
        await message.answer("Давай еще раз: нужна мечта и один первый шаг.")
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
    await message.answer(
        "Первый quick win зафиксирован ✅\n"
        f"⚡ Фокус дня: {focus['focus_text']}",
        reply_markup=get_open_dream_keyboard(dream_id, primary_action="⚡ Фокус дня"),
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
        await callback.message.answer("Пока нет мечт. Начни с «➕ Новая мечта».", reply_markup=get_main_menu_keyboard())
        await callback.answer()
        return
    builder = InlineKeyboardBuilder()
    for dream in dreams:
        builder.button(text=f"✨ {dream['title']}", callback_data=f"dream:open:{dream['id']}")
    builder.button(text="🏠 Главное меню", callback_data="menu:main")
    builder.adjust(1)
    await callback.message.answer("Выбери мечту:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("dream:open:"))
async def open_dream_context(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        return
    dream_id = int(callback.data.split(":")[-1])
    dream = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, dream_id)
    if dream is None:
        await callback.answer("Мечта недоступна.", show_alert=True)
        return
    await state.update_data(active_dream_id=dream_id)
    dashboard_text = await build_dream_dashboard_text(dream)
    next_event = get_next_event_prompt(dream_id=dream_id)
    addon = f"\n\n🔔 {next_event}" if next_event else ""
    await callback.message.answer(
        f"{dashboard_text}{addon}",
        reply_markup=get_open_dream_keyboard(dream_id, primary_action="🎯 Следующий шаг"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dream:menu:"))
async def open_secondary_menu(callback: CallbackQuery) -> None:
    dream_id = int(callback.data.split(":")[-1])
    await callback.answer()
    await callback.message.answer("Дополнительные действия:", reply_markup=get_dream_secondary_menu_keyboard(dream_id))


@router.callback_query(F.data.startswith("dream:continue:"))
async def continue_dream_chat(callback: CallbackQuery, state: FSMContext) -> None:
    dream_id = int(callback.data.split(":")[-1])
    await state.update_data(active_dream_id=dream_id)
    await callback.answer()
    await callback.message.answer("Окей. Пиши одну мысль/вопрос, и идем следующим шагом.")


@router.callback_query(F.data.startswith("dream:analyze:"))
async def run_ai_analysis(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return
    dream_id = int(callback.data.split(":")[-1])
    dream = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, dream_id)
    if dream is None:
        await callback.answer("Мечта недоступна.", show_alert=True)
        return
    await callback.answer("Анализирую...")
    summary = await ai_service.generate_summary_memory(dream_id=dream_id, dream_title=str(dream["title"]))
    update_dream_summary(dream_id=dream_id, summary=summary)
    await callback.message.answer(
        f"🧠 Обновленная память:\n{summary}",
        reply_markup=get_open_dream_keyboard(dream_id, primary_action="🎯 Следующий шаг"),
    )


@router.callback_query(F.data.startswith("dream:pause:"))
async def pause_dream(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return
    dream_id = int(callback.data.split(":")[-1])
    update_dream_status(dream_id=dream_id, status="paused")
    await callback.answer("Поставил на паузу.")
    await callback.message.answer("Мечта на паузе. Когда вернешься, продолжим с одного шага.")


@router.callback_query(F.data.startswith("dream:progress:"))
async def progress_dashboard(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        return
    dream_id = int(callback.data.split(":")[-1])
    dream = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, dream_id)
    if dream is None:
        await callback.answer("Мечта недоступна.", show_alert=True)
        return
    await state.update_data(active_dream_id=dream_id)
    snapshot = get_progress_snapshot(dream_id=dream_id, dream_title=str(dream["title"]))
    text = build_progress_text(dream_title=str(dream["title"]), snapshot=snapshot)
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить 1 задачу", callback_data=f"task:add:{dream_id}")
    open_tasks = snapshot["open_tasks"]
    if open_tasks:
        builder.button(text=f"✅ Закрыть: {str(open_tasks[0]['title'])[:22]}", callback_data=f"task:done:{int(open_tasks[0]['id'])}:{dream_id}")
    builder.button(text="🔙 К мечте", callback_data=f"dream:open:{dream_id}")
    builder.adjust(1)
    await callback.answer()
    await callback.message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("task:add:"))
async def add_task_start(callback: CallbackQuery, state: FSMContext) -> None:
    dream_id = int(callback.data.split(":")[-1])
    await state.set_state(DreamStates.waiting_for_task_title)
    await state.update_data(task_dream_id=dream_id)
    await callback.answer()
    await callback.message.answer("Напиши одну следующую задачу (1 действие).")


@router.message(DreamStates.waiting_for_task_title)
async def save_task_title(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not message.text:
        return
    title = message.text.strip()
    data = await state.get_data()
    dream_id = data.get("task_dream_id")
    if not title or not isinstance(dream_id, int):
        await message.answer("Нужен короткий текст задачи.")
        return
    dream = get_user_dream_by_id(message.from_user.id, message.from_user.username, dream_id)
    if dream is None:
        await state.clear()
        return
    create_action_task(dream_id=dream_id, dream_title=str(dream["title"]), task_title=title)
    await state.clear()
    await state.update_data(active_dream_id=dream_id)
    await message.answer("Задача добавлена ✅", reply_markup=get_open_dream_keyboard(dream_id, primary_action="📈 Открыть прогресс"))


@router.callback_query(F.data.startswith("task:done:"))
async def complete_task_flow(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return
    parts = callback.data.split(":")
    task_id = int(parts[2])
    dream_id = int(parts[3])
    updated_dream_id = complete_action_task(task_id=task_id)
    if updated_dream_id is None:
        await callback.answer("Задача не найдена.", show_alert=True)
        return
    evaluate_and_store_events(dream_id=dream_id)
    await callback.answer("Отлично, шаг закрыт 🔥")
    await callback.message.answer(
        "Шаг засчитан. Готов к следующему?",
        reply_markup=get_open_dream_keyboard(updated_dream_id, primary_action="🎯 Следующий шаг"),
    )


@router.callback_query(F.data.startswith("dream:next:"))
async def next_step_flow(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return
    dream_id = int(callback.data.split(":")[-1])
    dream = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, dream_id)
    if dream is None:
        await callback.answer("Мечта недоступна.", show_alert=True)
        return
    step = await ai_service.generate_next_step(dream_id=dream_id, dream_title=str(dream["title"]))
    await callback.answer()
    await callback.message.answer(
        f"🎯 Next best action:\n{step}",
        reply_markup=get_open_dream_keyboard(dream_id, primary_action="💬 Продолжить"),
    )


@router.callback_query(F.data.startswith("dream:focus:"))
async def focus_flow(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return
    dream_id = int(callback.data.split(":")[-1])
    dream = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, dream_id)
    if dream is None:
        await callback.answer("Мечта недоступна.", show_alert=True)
        return
    focus = get_current_focus(dream_id=dream_id)
    if not focus["focus_text"]:
        focus = await generate_daily_focus(dream_id=dream_id, dream_title=str(dream["title"]))
    builder = InlineKeyboardBuilder()
    if isinstance(focus["focus_task_id"], int):
        builder.button(text="✅ Выполнил", callback_data=f"task:done:{focus['focus_task_id']}:{dream_id}")
    builder.button(text="🔄 Обновить", callback_data=f"focus:refresh:{dream_id}")
    builder.button(text="🔙 К мечте", callback_data=f"dream:open:{dream_id}")
    builder.adjust(1)
    await callback.answer()
    await callback.message.answer(f"⚡ Фокус дня\n{focus['focus_text']}", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("focus:refresh:"))
async def refresh_focus(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return
    dream_id = int(callback.data.split(":")[-1])
    dream = get_user_dream_by_id(callback.from_user.id, callback.from_user.username, dream_id)
    if dream is None:
        await callback.answer("Мечта недоступна.", show_alert=True)
        return
    focus = await generate_daily_focus(dream_id=dream_id, dream_title=str(dream["title"]))
    await callback.answer("Обновил.")
    await callback.message.answer(
        f"⚡ Новый фокус\n{focus['focus_text']}",
        reply_markup=get_open_dream_keyboard(dream_id, primary_action="✅ Выполнил"),
    )


@router.callback_query(F.data.startswith("dream:edit:"))
async def edit_stub(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("Редактирование будет в отдельном guided flow.")
