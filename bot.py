import re
import random
import subprocess
from datetime import datetime
from io import BytesIO

import requests
import telebot
from telebot import types

# ====== Sozlamalar ======
TELEGRAM_TOKEN = "8380227353:AAGPHRQmsS0YMgm4HILCKf38kmf8TBmAKXY"
OPENROUTER_API_KEY = "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"
AUDD_API_KEY = "cfea48f9655049594a4f244e603713ce"
ADMIN_ID = 2025577808  # O'zingizning chat_id

MODEL = "openai/gpt-4o-mini"

INSTAGRAM_REGEX = r"(https?://(?:www\.)?instagram\.com/[^\s]+)"
YOUTUBE_REGEX = r"(https?://(?:www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[^\s]+)"
stickers = ["😊", "😃", "👍", "❤️", "🤔", "😉", "🔥", "😁"]
video_formats = ["360", "480", "720"]

bot = telebot.TeleBot(TELEGRAM_TOKEN)
user_languages = {}

# ====== Til tanlash ======
@bot.message_handler(commands=['start'])
def cmd_start(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row("🇺🇿 O‘zbek", "🇷🇺 Русский", "🇬🇧 English")
    bot.send_message(message.chat.id, "Tilni tanlang / Choose language:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["🇺🇿 O‘zbek", "🇷🇺 Русский", "🇬🇧 English"])
def set_lang(message):
    langmap = {"🇺🇿 O‘zbek": "o'zbek", "🇷🇺 Русский": "rus", "🇬🇧 English": "english"}
    user_languages[message.chat.id] = langmap[message.text]
    resp = {
        "o'zbek": "✅ Til o‘zbek tiliga o‘rnatildi.",
        "rus": "✅ Язык установлен на русский.",
        "english": "✅ Language set to English."
    }[langmap[message.text]]
    bot.send_message(message.chat.id, resp, reply_markup=types.ReplyKeyboardRemove())

# ====== Video yuklash funksiyasi ======
def send_video(chat_id, url, format_choice=None):
    try:
        cmd = ["yt-dlp", "-f"]
        if format_choice:
            cmd.append(f"bestvideo[height<={format_choice}]+bestaudio/best")
        else:
            cmd.append("best")
        cmd.append(url)
        cmd.append("-g")  # direct URL

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        video_url = result.stdout.strip().splitlines()[0] if result.stdout else None

        if not video_url:
            bot.send_message(chat_id, "❌ Video URL olinmadi.")
            return False

        # Stream orqali yuborish
        with requests.get(video_url, stream=True, timeout=60) as r:
            buf = BytesIO()
            for chunk in r.iter_content(chunk_size=1024*1024):
                if chunk:
                    buf.write(chunk)
            buf.seek(0)
            buf.name = "video.mp4"

        # Inline tugma — "Muzikasini top"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🎵 Muzikasini top", callback_data="find_music"))

        bot.send_video(chat_id, buf, caption="🎬 Video yuklab olindi", reply_markup=markup)
        return True

    except Exception as e:
        bot.send_message(chat_id, f"❌ Xatolik yuz berdi: {e}")
        return False

# ====== Inline tugma handler (Muzika topish) ======
@bot.callback_query_handler(func=lambda call: call.data == "find_music")
def find_music(call):
    if not call.message.video:
        bot.answer_callback_query(call.id, "❌ Video topilmadi")
        return
    bot.answer_callback_query(call.id, "⏳ Musiqasi topilmoqda, kuting…")
    file_id = call.message.video.file_id
    file_info = bot.get_file(file_id)
    downloaded = bot.download_file(file_info.file_path)

    files = {'file': ('video.mp4', downloaded)}
    data = {'return': 'apple_music,spotify', 'api_token': AUDD_API_KEY}

    try:
        r = requests.post('https://api.audd.io/', data=data, files=files, timeout=60)
        res = r.json()
        if res.get('status') == 'success' and res.get('result'):
            music_info = res['result']
            title = music_info.get('title', 'Noma’lum')
            artist = music_info.get('artist', 'Noma’lum')
            link = music_info.get('song_link') or music_info.get('spotify', {}).get('external_urls', {}).get('spotify', '')
            text = f"🎵 Musiqa topildi:\n💿 {title} — {artist}\n🔗 {link}"
            bot.send_message(call.message.chat.id, text)
        else:
            bot.send_message(call.message.chat.id, "❌ Musiqa topilmadi.")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Xatolik: {e}")

# ====== Asosiy handler ======
@bot.message_handler(func=lambda m: True)
def main_handler(message):
    text = message.text or ""

    # Instagram link
    if re.search(INSTAGRAM_REGEX, text):
        bot.send_message(message.chat.id, "⏳ Instagram videosi yuklanmoqda…")
        send_video(message.chat.id, text)
        return

    # YouTube link
    yt_match = re.search(YOUTUBE_REGEX, text)
    if yt_match:
        if "shorts/" in text or "youtu.be" in text:
            bot.send_message(message.chat.id, "⏳ Video yuklanmoqda…")
            send_video(message.chat.id, text)
        else:
            markup = types.InlineKeyboardMarkup()
            for f in video_formats:
                markup.add(types.InlineKeyboardButton(f"{f}p", callback_data=f"yt_{f}_{text}"))
            bot.send_message(message.chat.id, "📌 Formatni tanlang:", reply_markup=markup)
        return

    # AI chat
    lang = user_languages.get(message.chat.id, "o'zbek")
    system_prompt = {
        "o'zbek": "Siz faqat o‘zbek tilida javob berasiz.",
        "rus": "Вы отвечаете только на русском языке.",
        "english": "You must always respond in English only."
    }[lang]

    try:
        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ]
        }
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                     "Content-Type": "application/json"},
            timeout=30
        )
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if "choices" in data:
            answer = data["choices"][0]["message"]["content"]
            bot.reply_to(message, answer + " " + random.choice(stickers))
            # Admin log
            uname = f"@{message.from_user.username}" if message.from_user.username else "❌ Username yo‘q"
            fullname = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
            cid = message.chat.id
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log = f"📌 {now}\n👤 {fullname}\n🔗 {uname}\n🆔 {cid}\n❓ {text}\n💬 {answer}\n---"
            bot.send_message(ADMIN_ID, log)
        else:
            bot.reply_to(message, "❌ AI javob bera olmadi.")
    except Exception as e:
        bot.reply_to(message, "❌ Xatolik yuz berdi.")
        print("AI xatosi:", e)

# ====== Inline tugma handler (YouTube format tanlash) ======
@bot.callback_query_handler(func=lambda call: call.data.startswith("yt_"))
def youtube_format(call):
    try:
        _, format_choice, url = call.data.split("_", 2)
        bot.answer_callback_query(call.id, f"⏳ {format_choice}p formatida yuklanmoqda…")
        send_video(call.message.chat.id, url, format_choice)
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Xatolik yuz berdi: {e}")

# ====== Ishga tushurish ======
print("✅ Bot ishga tushdi…")
bot.polling(non_stop=True, timeout=60, long_polling_timeout=60)