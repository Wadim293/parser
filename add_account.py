import os
import zipfile
from aiogram import Router, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from pyrogram import Client
from start import send_main_menu
from config import API_ID, API_HASH
from models import User, Account, Session
from sqlalchemy import select

router = Router()

class AccountStates(StatesGroup):
    waiting_for_file = State()

@router.callback_query(lambda c: c.data == "add_account")
async def handle_add_account(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_menu")]
    ])
    await callback.message.answer(
        text=(
            "➕ <b>Для подключения аккаунта ОТПРАВЬТЕ архив .zip или файл .session</b>\n\n"
            "<blockquote>"
            "<b>ВНИМАНИЕ! ПОДДЕРЖИВАЮТСЯ ТОЛЬКО СЕССИИ PYROGRAM!</b>\n"
            "<b>TELETHON .SESSION НЕ ПОДХОДИТ!</b>"
            "</blockquote>"
        ),
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(AccountStates.waiting_for_file)
    await callback.answer()

@router.message(AccountStates.waiting_for_file)
async def handle_file(message: Message, state: FSMContext):
    user_id = message.from_user.id

    async with Session() as session:
        user = await session.scalar(select(User).where(User.telegram_id == user_id))
        if not user:
            user = User(telegram_id=user_id, full_name=message.from_user.full_name, username=message.from_user.username)
            session.add(user)
            await session.commit()
            await session.refresh(user)

    if not message.document:
        await message.answer("❌ Пожалуйста, отправьте файл .zip или .session")
        return

    file = message.document
    filename = file.file_name
    ext = os.path.splitext(filename)[1].lower()

    user_dir = f"Аккаунты/{user_id}"
    os.makedirs(user_dir, exist_ok=True)

    file_path = os.path.join(user_dir, filename)
    bot: Bot = message.bot
    await bot.download(file=file, destination=file_path)

    session_paths = []

    if ext == ".zip":
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(user_dir)
            os.remove(file_path)
            for name in os.listdir(user_dir):
                if name.endswith(".session"):
                    session_paths.append(os.path.join(user_dir, name))
        except Exception as e:
            await message.answer(f"❌ Ошибка при распаковке архива: {e}")
            return
    elif ext == ".session":
        session_paths.append(file_path)
    else:
        os.remove(file_path)
        await message.answer("❌ Неверный формат файла. Только .zip или .session")
        return

    await validate_sessions(session_paths, API_ID, API_HASH, user_id, message)
    await state.clear()

async def connect_and_validate_async(session_path, api_id, api_hash):
    try:
        session_name = os.path.splitext(session_path)[0]
        client = Client(session_name, api_id=api_id, api_hash=api_hash)
        await client.start()
        me = await client.get_me()
        phone_number = me.phone_number
        await client.stop()
        return phone_number, session_name
    except Exception:
        return None, None

async def validate_sessions(session_paths, api_id, api_hash, user_telegram_id, message):
    found_valid = False
    async with Session() as db:
        user = await db.scalar(select(User).where(User.telegram_id == user_telegram_id))
        for session_file in session_paths:
            phone_number, session_name = await connect_and_validate_async(session_file, api_id, api_hash)
            display_name = os.path.basename(session_file)
            if phone_number is None:
                await message.answer(f"❌ Сессия невалидная: {display_name}")
                continue

            result = await db.execute(
                select(Account).where(
                    (Account.phone_number == phone_number) &
                    (Account.user_id == user.id)
                )
            )
            account_obj = result.scalar_one_or_none()

            if account_obj is None:
                account = Account(
                    phone_number=phone_number,
                    session_name=display_name,
                    user_id=user.id
                )
                db.add(account)
                await db.commit()
                await message.answer(
                    f"✅ Успешно добавлен аккаунт: <b>{phone_number}</b> ({display_name})",
                    parse_mode="HTML"
                )
            else:
                await message.answer(
                    f"ℹ️ Аккаунт уже был добавлен ранее: <b>{phone_number}</b>",
                    parse_mode="HTML"
                )
            found_valid = True
            break

    if not found_valid:
        await message.answer("⚠️ Ни одна из сессий невалидна.")

@router.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await send_main_menu(callback.message)
    await state.clear()
    await callback.answer()