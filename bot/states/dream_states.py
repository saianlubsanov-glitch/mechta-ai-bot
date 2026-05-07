from aiogram.fsm.state import State, StatesGroup


class DreamStates(StatesGroup):
    waiting_for_dream_title = State()
    waiting_for_why_important = State()
    waiting_for_obstacles = State()
    waiting_for_emotional_state = State()
    waiting_for_first_focus_task = State()
    waiting_for_task_title = State()
    waiting_commitment = State()
    waiting_action = State()
    waiting_result = State()
    waiting_reflection = State()
    dream_check_step_1 = State()
    dream_check_step_2 = State()
    dream_check_step_3 = State()
    dream_check_step_4 = State()
    dream_check_step_5 = State()
    dream_release_reflection = State()
    dream_delete_confirmation = State()
