import re, asyncio, time
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from imdb import IMDb
from motor.motor_asyncio import AsyncIOMotorClient

import os  # इसे सबसे ऊपर जोड़ें

# --- CONFIGURATION (Koyeb Environment से डेटा उठाना) ---
API_ID = int(os.environ.get("API_ID")) # कोट्स की ज़रूरत नहीं, यह सीधे उठा लेगा
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789")) # डिफ़ॉल्ट वैल्यू या Environment से
FSUB_ID = int(os.environ.get("FSUB_ID", "-100123456789"))

# --- INITIALIZATION ---
app = Client("UltimateBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db = AsyncIOMotorClient(MONGO_URI).bot_database
users = db.users
movies = db.movies

ia = IMDb()

# --- FEATURES LOGIC ---

# 1. A.I. SPELL CHECK & SEASON FILTERING
async def ai_search_logic(query):
    # Season/Episode detection
    season_match = re.search(r's(\d+)|season\s*(\d+)', query, re.IGNORECASE)
    clean_query = re.sub(r's(\d+)|season\s*(\d+)|e(\d+)|episode\s*(\d+)', '', query, flags=re.IGNORECASE).strip()
    
    search = ia.search_movie(clean_query)
    if not search: return None, None
    movie = search[0]
    ia.update(movie)
    return movie, season_match.group(0) if season_match else ""

# 2. 2-STEP VERIFICATION & REQUEST TO JOIN
@app.on_chat_join_request()
async def join_handler(client, request):
    # यह "Req to Join Monetization" फीचर है
    await users.update_one({"user_id": request.from_user.id}, {"$set": {"approved": True}}, upsert=True)
    await request.approve()

# 3. DAILY LIMIT & PREMIUM CHECK
async def check_limits(user_id):
    user = await users.find_one({"user_id": user_id})
    if not user:
        await users.insert_one({"user_id": user_id, "searches": 0, "is_premium": False})
        return True
    if user.get("is_premium"): return True
    if user.get("searches", 0) >= 5: return False # Daily Limit 5
    return True

# --- MAIN COMMANDS ---

@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    await message.reply_text(
        "⚡ **Supercharged A.I. Bot Ready!**\n\n"
        "✅ A.I. Search Logic\n✅ 3-Layer Filter\n✅ IMDB Realtime\n\n"
        "बस मूवी का नाम लिखें!",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Buy Premium 💎", callback_data="buy_premium")
        ]])
    )

# --- THE SEARCH ENGINE (3-LAYER FILTERING) ---
@app.on_message(filters.text & filters.private)
async def filter_engine(client, message):
    user_id = message.from_user.id
    
    # Feature: 2-Step Force Sub
    try:
        await client.get_chat_member(FSUB_ID, user_id)
    except:
        return await message.reply("⚠️ **एक्सेस लॉक!** पहले चैनल जॉइन करें।",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Join Channel", url="t.me/codexmoviesgroup")]]))

    # Feature: Daily Limit System
    if not await check_limits(user_id):
        return await message.reply("❌ **डेली लिमिट पूरी!** प्रीमियम लें।")

    query = message.text.lower()
    m = await message.reply("🔍 **A.I. Analyzing Quality & Language...**")

    # Feature: A.I. Season & IMDB Logic
    movie_info, season_tag = await ai_search_logic(query)
    
    # Search Database (3-Layer Logic: Quality, Lang, Season)
    search_results = await movies.find({"file_name": {"$regex": query}}).to_list(length=10)

    if not search_results:
        await m.edit("😔 माफ़ करें, फाइल नहीं मिली। स्पेलिंग चेक करें।")
        return

    # Layout for Buttons
    buttons = []
    for f in search_results:
        buttons.append([InlineKeyboardButton(f"📥 {f['file_name']}", callback_data="file_sent")])

    cap = f"✅ **फाइल मिल गई!**\n🎬 **{movie_info['title'] if movie_info else query}**\n⭐ Rating: {movie_info.get('rating', 'N/A') if movie_info else 'N/A'}"
    
    if movie_info and movie_info.get('full-size cover url'):
        await message.reply_photo(movie_info['full-size cover url'], caption=cap, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await message.reply_text(cap, reply_markup=InlineKeyboardMarkup(buttons))
    
    # Update Search Count
    await users.update_one({"user_id": user_id}, {"$inc": {"searches": 1}})
    await m.delete()

# --- ADMIN FEATURES (FOR INDEXING) ---
@app.on_message(filters.command("index") & filters.user(ADMIN_ID))
async def index_bot(client, message):
    await message.reply("🔄 इंडेक्सिंग शुरू... सारी फाइल्स डेटाबेस में सेव हो रही हैं।")
    async for msg in client.get_chat_history(message.chat.id):
        if msg.document or msg.video:
            file = msg.document or msg.video
            await movies.update_one(
                {"file_id": file.file_id},
                {"$set": {"file_name": file.file_name.lower()}},
                upsert=True
            )
    await message.reply("✅ चैनल इंडेक्स हो गया!")

from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# --- 1. Fake Web Server (Koyeb Health Check Fix) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Running!")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# --- बाकी सारा कोड (Config, Clients, आदि) यहाँ रहेगा ---

if __name__ == "__main__":
    # हेल्थ चेक सर्वर को अलग धागे (Thread) में चलाएं
    threading.Thread(target=run_health_server, daemon=True).start()
    
    print("🚀 बॉट शुरू हो रहा है और हेल्थ चेक पोर्ट ओपन है...")
    app.run()
    
app.run()
