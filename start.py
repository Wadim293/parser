from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from models import User, Session
from sqlalchemy import select

router = Router()

# 👤 Обработка команды /start
@router.message(F.text == "/start")
async def start_cmd(message: Message):
    async with Session() as session:
        user = await session.scalar(select(User).where(User.telegram_id == message.from_user.id))
        if not user:
            user = User(
                telegram_id=message.from_user.id,
                full_name=message.from_user.full_name,
                username=message.from_user.username
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
    await send_main_menu(message)

async def send_main_menu(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔍 Парсер", callback_data="start_parse"),
        ],
        [
            #InlineKeyboardButton(text="💣 Спамер по ЛС", callback_data="start_spam"),
        ],
        [
            InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="add_account"),
            InlineKeyboardButton(text="📁 Мои аккаунты", callback_data="my_accounts"),
        ]
    ])

    await message.answer(
        text="👋 <b>Добро пожаловать!</b>\nВыберите действие ниже:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    await callback.message.delete()
    await send_main_menu(callback.message)
    await callback.answer()