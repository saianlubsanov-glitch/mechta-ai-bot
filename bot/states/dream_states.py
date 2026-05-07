from aiogram.fsm.state import State, StatesGroup


class DreamStates(StatesGroup):
    waiting_for_dream_title = State()
