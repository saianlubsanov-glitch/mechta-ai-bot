from aiogram.fsm.state import State, StatesGroup


class DreamStates(StatesGroup):
    waiting_for_dream_title = State()
    waiting_for_why_important = State()
    waiting_for_obstacles = State()
    waiting_for_emotional_state = State()
    waiting_for_first_focus_task = State()
    waiting_for_task_title = State()
