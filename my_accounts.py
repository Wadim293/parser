import os
from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from start import send_main_menu
from models import User, Account, Session
from redis_client import redis_client
from sqlalchemy import select, delete

router = Router()

@router.callback_query(lambda c: c.data == "my_accounts")
async def handle_my_accounts(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    user_id = callback.from_user.id
    async with Session() as session:
        user = await session.scalar(select(User).where(User.telegram_id == user_id))
        if not user:
            accounts = []
        else:
            accounts = await session.execute(select(Account).where(Account.user_id == user.id))
            accounts = accounts.scalars().all()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    if accounts:
        for acc in accounts:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text=acc.phone_number,
                    callback_data=f"view_account:{acc.id}"
                )
            ])
    else:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="❌ Аккаунты не найдены", callback_data="noop")
        ])

    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="Назад", callback_data="back_to_menu")
    ])

    await callback.message.answer(
        text="📁 <b>Аккаунты:</b>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("view_account:"))
async def view_account(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    account_id = int(callback.data.split(":")[1])
    async with Session() as session:
        account = await session.scalar(select(Account).where(Account.id == account_id))

    if not account:
        await callback.message.answer("⚠️ Аккаунт не найден.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Удалить аккаунт", callback_data=f"delete_account:{account.id}")],
        [InlineKeyboardButton(text="Назад", callback_data="my_accounts")]
    ])

    await callback.message.answer(
        text=f"📱 <b>{account.phone_number}</b>\n\nЧто вы хотите сделать с этим аккаунтом?",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("delete_account:"))
async def delete_account(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    account_id = int(callback.data.split(":")[1])
    async with Session() as session:
        account = await session.scalar(select(Account).where(Account.id == account_id))
        if not account:
            await callback.message.answer("⚠️ Аккаунт не найден.")
            return

        # user нужен только для user_id
        user = await session.scalar(select(User).where(User.id == account.user_id))
        user_id = user.telegram_id if user else None

    redis_key = f"parsing:{user_id}"
    if await redis_client.get(redis_key) == "1":
        await callback.message.answer(
            text="<b>❌ Нельзя удалить аккаунт — он используется в активном парсинге.</b>",
            parse_mode="HTML"
        )
        return

    session_path = os.path.join("Аккаунты", str(user_id), account.session_name)
    file_deleted = False

    if os.path.exists(session_path):
        try:
            os.remove(session_path)
            file_deleted = True
        except Exception as e:
            await callback.message.answer(f"⚠️ Не удалось удалить .session файл: {e}")
    else:
        await callback.message.answer("⚠️ Файл сессии не найден, но аккаунт всё равно будет удалён.")

    async with Session() as session:
        await session.execute(delete(Account).where(Account.id == account_id))
        await session.commit()

    await callback.message.answer(
        f"✅ Аккаунт <code>{account.phone_number}</code> удалён {'с файлом' if file_deleted else '(файл не найден)'}",
        parse_mode="HTML"
    )

    await handle_my_accounts(callback)