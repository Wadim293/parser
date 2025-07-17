from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import BOT_TOKEN, WEBHOOK_URL, WEBHOOK_PATH, WEBHOOK_PORT
from start import router as start_router
from parse import router as parse_router
from add_account import router as add_account_router
from my_accounts import router as my_accounts_router
from aiogram.fsm.storage.memory import MemoryStorage
from models import init_db

storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=storage)

dp.include_router(start_router)
dp.include_router(parse_router)
dp.include_router(add_account_router)
dp.include_router(my_accounts_router)

async def on_startup(app: web.Application):
    await init_db()
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app: web.Application):
    await bot.delete_webhook()

def main():
    app = web.Application()
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=f"/{WEBHOOK_PATH}")
    setup_application(app, dp, bot=bot)
    web.run_app(app, port=WEBHOOK_PORT)

if __name__ == "__main__":
    main()