import os
import asyncio
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from pyrogram import Client
from pyrogram.enums import ChatMembersFilter
from models import User, Account, ChatLink, Session
from config import API_ID, API_HASH
from redis_client import redis_client
from sqlalchemy import select, update

router = Router()

MESSAGE_LIMIT = 10000
SESSION_FOLDER = "Аккаунты"

class ParseStates(StatesGroup):
    waiting_for_chat_link = State()
    choosing_parse_method = State()

def normalize_chat_id(chat_input):
    chat_input = chat_input.strip()
    if chat_input.startswith("https://t.me/"):
        chat_input = chat_input.replace("https://t.me/", "")
    elif chat_input.startswith("t.me/"):
        chat_input = chat_input.replace("t.me/", "")
    if not chat_input.startswith("@") and not chat_input.lstrip("-").isdigit():
        chat_input = "@" + chat_input
    return chat_input

async def has_nft_gift(client, user_id):
    async for gift in client.get_chat_gifts(user_id):
        if getattr(gift, 'collectible_id', None) is not None:
            return True
    return False

@router.callback_query(lambda c: c.data == "start_parse")
async def handle_parse(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить парсинг", callback_data="run_parser")],
        [InlineKeyboardButton(text="⚙️ Настройки парсинга", callback_data="parse_settings")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_menu")]
    ])

    await callback.message.answer(
        text="🔍 <b>Вы выбрали парсинг.</b>\n\nНажмите кнопку ниже, чтобы начать.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "parse_settings")
async def parse_settings(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    user_id = callback.from_user.id
    async with Session() as session:
        user = await session.scalar(select(User).where(User.telegram_id == user_id))
        if not user:
            await callback.message.answer("❌ Вы не зарегистрированы. Введите /start.")
            return

        text = (
            "<b>⚙️ Настройки парсинга:</b>\n\n"
            f"<b>• Парсить всех с NFT: {'✅' if user.parse_nft_all else '❌'}</b>\n"
            f"<b>• Парсить только премиум с NFT: {'✅' if user.parse_nft_premium else '❌'}</b>\n"
            f"<b>• Исключать админов: {'✅' if user.parse_exclude_admins else '❌'}</b>\n"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{'✅' if user.parse_nft_all else '❌'} Всех с NFT", callback_data="toggle_nft_all")],
            [InlineKeyboardButton(
                text=f"{'✅' if user.parse_nft_premium else '❌'} Только премиум NFT", callback_data="toggle_nft_premium")],
            [InlineKeyboardButton(
                text=f"{'✅' if user.parse_exclude_admins else '❌'} Исключить админов", callback_data="toggle_exclude_admins")],
            [InlineKeyboardButton(text="Назад", callback_data="start_parse")]
        ])
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()

@router.callback_query(lambda c: c.data == "toggle_nft_all")
async def toggle_nft_all(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with Session() as session:
        user = await session.scalar(select(User).where(User.telegram_id == user_id))
        if not user:
            await callback.message.answer("❌ Вы не зарегистрированы.")
            return
        user.parse_nft_all = not user.parse_nft_all
        if not user.parse_nft_all and not user.parse_nft_premium:
            user.parse_nft_premium = True
        await session.commit()
    await parse_settings(callback)

@router.callback_query(lambda c: c.data == "toggle_nft_premium")
async def toggle_nft_premium(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with Session() as session:
        user = await session.scalar(select(User).where(User.telegram_id == user_id))
        if not user:
            await callback.message.answer("❌ Вы не зарегистрированы.")
            return
        user.parse_nft_premium = not user.parse_nft_premium
        if not user.parse_nft_all and not user.parse_nft_premium:
            user.parse_nft_all = True
        await session.commit()
    await parse_settings(callback)

@router.callback_query(lambda c: c.data == "toggle_exclude_admins")
async def toggle_exclude_admins(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with Session() as session:
        user = await session.scalar(select(User).where(User.telegram_id == user_id))
        if not user:
            await callback.message.answer("❌ Вы не зарегистрированы.")
            return
        user.parse_exclude_admins = not user.parse_exclude_admins
        await session.commit()
    await parse_settings(callback)

@router.callback_query(lambda c: c.data == "run_parser")
async def run_parser(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    user_id = callback.from_user.id
    async with Session() as session:
        user = await session.scalar(select(User).where(User.telegram_id == user_id))
        if not user:
            await callback.message.answer("❌ Вы не зарегистрированы. Введите /start.")
            return

        accounts = await session.execute(select(Account).where(Account.user_id == user.id))
        accounts = accounts.scalars().all()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    if accounts:
        for acc in accounts:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text=acc.phone_number,
                    callback_data=f"use_for_parsing:{acc.id}"
                )
            ])
    else:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="❌ Аккаунты не найдены", callback_data="noop")
        ])

    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="Назад", callback_data="start_parse")
    ])

    await callback.message.answer(
        text="👥 <b>Выберите аккаунт для парсинга:</b>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("use_for_parsing:"))
async def use_for_parsing(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except:
        pass

    account_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    await redis_client.hset(f"parse:{user_id}", mapping={"account_id": str(account_id)})
    await state.update_data(account_id=account_id, telegram_id=user_id)
    await state.set_state(ParseStates.waiting_for_chat_link)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="run_parser")]
    ])

    await callback.message.answer(
        text=(
            "🔗 <b>Пришлите ссылку на чат для парсинга:</b>\n"
            "⚠️ <b>Пример ссылки: https://t.me/</b>"
        ),
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(ParseStates.waiting_for_chat_link)
async def save_chat_link(message: Message, state: FSMContext):
    chat_link = message.text.strip()
    user_id = message.from_user.id

    data = await state.get_data()
    account_id = data.get("account_id")
    telegram_id = data.get("telegram_id")

    async with Session() as session:
        account = await session.scalar(select(Account).where(Account.id == account_id))
        if not account:
            await message.answer("❌ Аккаунт не найден!")
            return

        session_name = os.path.splitext(account.session_name)[0]
        session_path = os.path.join(SESSION_FOLDER, str(user_id), session_name)

        existing = await session.scalar(select(ChatLink).where(ChatLink.url == chat_link))
        await state.update_data(chat_link=chat_link, account_id=account_id, telegram_id=telegram_id)

        if existing:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Продолжить", callback_data="confirm_parse_chat"),
                    InlineKeyboardButton(text="Сменить ссылку", callback_data="change_chat_link")
                ]
            ])
            await message.answer(
                "<b>⚠️ Этот чат уже был спаршен ранее.</b>\nВы хотите продолжить или ввести другую ссылку?",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await state.set_state(ParseStates.choosing_parse_method)
            return

        new_link = ChatLink(url=chat_link)
        session.add(new_link)
        await session.commit()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 По сообщениям", callback_data="parse_by_messages")],
        [InlineKeyboardButton(text="👥 По участникам", callback_data="parse_by_members")],
        [InlineKeyboardButton(text="Назад", callback_data="run_parser")]
    ])
    await message.answer(
        "<b>Выберите метод парсинга:</b>\n\n"
        "🔎 <b>По сообщениям</b> — находит активных писавших с NFT Gift\n"
        "👥 <b>По участникам</b> — ищет NFT Gift у каждого участника (медленнее, но можно найти даже скрытых/неактивных!)",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(ParseStates.choosing_parse_method)

@router.callback_query(lambda c: c.data == "confirm_parse_chat")
async def confirm_parse_chat(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        await callback.message.delete()
    except:
        pass
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 По сообщениям", callback_data="parse_by_messages")],
        [InlineKeyboardButton(text="👥 По участникам", callback_data="parse_by_members")],
        [InlineKeyboardButton(text="Назад", callback_data="run_parser")]
    ])
    await callback.message.answer(
        "<b>Выберите метод парсинга:</b>\n\n"
        "🔎 <b>По сообщениям</b> — находит активных писавших с NFT Gift\n"
        "👥 <b>По участникам</b> — ищет NFT Gift у каждого участника (медленнее, но можно найти даже скрытых/неактивных!)",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(ParseStates.choosing_parse_method)

@router.callback_query(lambda c: c.data == "parse_by_messages")
async def parse_by_messages(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        await callback.message.delete()
    except:
        pass

    data = await state.get_data()
    user_id = callback.from_user.id
    account_id = data.get("account_id")
    chat_link = data.get("chat_link")

    async with Session() as session:
        account = await session.scalar(select(Account).where(Account.id == account_id))
        if not account:
            await callback.message.answer("❌ Аккаунт не найден!")
            return

        session_name = os.path.splitext(account.session_name)[0]
        session_path = os.path.join(SESSION_FOLDER, str(user_id), session_name)

    await callback.message.answer("⏳ Парсинг по сообщениям запущен! Результат придёт, когда всё будет готово.")
    asyncio.create_task(background_parse(user_id, callback.message.chat.id, session_path, normalize_chat_id(chat_link), API_ID, API_HASH, callback.bot))

@router.callback_query(lambda c: c.data == "parse_by_members")
async def parse_by_members(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        await callback.message.delete()
    except:
        pass

    data = await state.get_data()
    user_id = callback.from_user.id
    account_id = data.get("account_id")
    chat_link = data.get("chat_link")

    async with Session() as session:
        account = await session.scalar(select(Account).where(Account.id == account_id))
        if not account:
            await callback.message.answer("❌ Аккаунт не найден!")
            return

        session_name = os.path.splitext(account.session_name)[0]
        session_path = os.path.join(SESSION_FOLDER, str(user_id), session_name)

    await callback.message.answer("⏳ Парсинг по участникам запущен! Это может занять дольше обычного.")
    asyncio.create_task(background_parse_members(user_id, callback.message.chat.id, session_path, normalize_chat_id(chat_link), API_ID, API_HASH, callback.bot))

@router.callback_query(lambda c: c.data == "change_chat_link")
async def change_chat_link(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except:
        pass

    await state.set_state(ParseStates.waiting_for_chat_link)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="run_parser")]
    ])
    await callback.message.answer(
        text="🔗 <b>Введите новую ссылку на чат:</b>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

# === Парсинг по сообщениям ===
async def background_parse(user_id, chat_id, session_path, channel_id, api_id, api_hash, bot):
    OUTPUT_FILE = f"parsed_nft_{user_id}.txt"
    usernames = set()
    checked_user_ids = set()
    from sqlalchemy import select
    async with Session() as session:
        user_settings = await session.scalar(select(User).where(User.telegram_id == user_id))
        parse_nft_all = getattr(user_settings, "parse_nft_all", True)
        parse_nft_premium = getattr(user_settings, "parse_nft_premium", False)
        parse_exclude_admins = getattr(user_settings, "parse_exclude_admins", True)

    try:
        app = Client(session_path, api_id=api_id, api_hash=api_hash)
        await app.start()

        admin_ids = set()
        if parse_exclude_admins:
            async for member in app.get_chat_members(channel_id, filter=ChatMembersFilter.ADMINISTRATORS):
                admin_ids.add(member.user.id)

        async for message in app.get_chat_history(channel_id, limit=MESSAGE_LIMIT):
            user = getattr(message, 'from_user', None)
            if not user or user.is_bot or not user.username:
                continue
            if user.id in checked_user_ids:
                continue
            if parse_exclude_admins and user.id in admin_ids:
                continue
            checked_user_ids.add(user.id)

            nft = await has_nft_gift(app, user.id)
            if not nft:
                continue
            if parse_nft_premium and not getattr(user, "is_premium", False):
                continue
            usernames.add(user.username)

        await app.stop()
    except Exception as e:
        await bot.send_message(chat_id, f"❌ Ошибка при парсинге или невалидная сессия: {e}")
        return

    if not usernames:
        await bot.send_message(chat_id, "⚠️ В чате не найдено пользователей с NFT Gift.")
        return

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for username in sorted(usernames):
            f.write(f'@{username}\n')

    await bot.send_document(chat_id, FSInputFile(OUTPUT_FILE), caption=f"✅ Готово! {len(usernames)} пользователей с NFT Gift.")

# === Парсинг по участникам ===
async def background_parse_members(user_id, chat_id, session_path, channel_id, api_id, api_hash, bot):
    OUTPUT_FILE = f"parsed_nft_{user_id}.txt"
    usernames = set()
    from sqlalchemy import select
    async with Session() as session:
        user_settings = await session.scalar(select(User).where(User.telegram_id == user_id))
        parse_nft_all = getattr(user_settings, "parse_nft_all", True)
        parse_nft_premium = getattr(user_settings, "parse_nft_premium", False)
        parse_exclude_admins = getattr(user_settings, "parse_exclude_admins", True)

    try:
        app = Client(session_path, api_id=api_id, api_hash=api_hash)
        await app.start()

        admin_ids = set()
        if parse_exclude_admins:
            async for member in app.get_chat_members(channel_id, filter=ChatMembersFilter.ADMINISTRATORS):
                admin_ids.add(member.user.id)

        limit = 6500
        count = 0
        async for member in app.get_chat_members(channel_id):
            if count >= limit:
                break
            user = getattr(member, 'user', None)
            if not user or user.is_bot or not user.username:
                continue
            if parse_exclude_admins and user.id in admin_ids:
                continue

            nft = await has_nft_gift(app, user.id)
            if not nft:
                continue
            if parse_nft_premium and not getattr(user, "is_premium", False):
                continue
            usernames.add(user.username)
            count += 1

        await app.stop()
    except Exception as e:
        await bot.send_message(chat_id, f"❌ Ошибка при парсинге или невалидная сессия: {e}")
        return

    if not usernames:
        await bot.send_message(chat_id, "⚠️ В чате не найдено пользователей с NFT Gift.")
        return

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for username in sorted(usernames):
            f.write(f'@{username}\n')

    await bot.send_document(chat_id, FSInputFile(OUTPUT_FILE), caption=f"✅ Готово! {len(usernames)} пользователей с NFT Gift.")