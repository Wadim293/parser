import asyncio
from pyrogram import Client
from pyrogram.types import ChatMember
import os

API_ID = "26793270"
API_HASH = "43be6adfd76ddf2e826b19c5e7235b3a"
SESSION_FOLDER = "sessions"
OUTPUT_FILE = "usernames.txt"
MESSAGE_LIMIT = 1000

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

async def main():
    api_id = API_ID or os.getenv("API_ID")
    api_hash = API_HASH or os.getenv("API_HASH")
    if not api_id:
        api_id = input("Введите api_id: ")
    if not api_hash:
        api_hash = input("Введите api_hash: ")

    chat_input = input("Введите chat_id, username или ссылку на чат: ")
    chat_id = normalize_chat_id(chat_input)

    session_name = None
    if not os.path.exists(SESSION_FOLDER):
        os.makedirs(SESSION_FOLDER)
    for file in os.listdir(SESSION_FOLDER):
        if file.endswith('.session'):
            session_name = file[:-8]
            break
    if not session_name:
        session_name = input("Сессия не найдена. Введите имя для новой сессии: ")
    session_path = os.path.join(SESSION_FOLDER, session_name)
    app = Client(session_path, api_id=api_id, api_hash=api_hash)
    await app.start()

    usernames = set()
    checked_user_ids = set()
    async for message in app.get_chat_history(chat_id, limit=MESSAGE_LIMIT):
        user = getattr(message, 'from_user', None)
        if not user or user.is_bot or not user.username:
            continue
        if user.id in checked_user_ids:
            continue
        checked_user_ids.add(user.id)
        if await has_nft_gift(app, user.id):
            usernames.add(user.username)
            print(f"Found: {user.username}")

    await app.stop()

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for username in sorted(usernames):
            f.write(f'@{username}\n')
    print(f"Saved {len(usernames)} usernames to {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main()) 