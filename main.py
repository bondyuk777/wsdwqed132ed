import os
import logging
import time
import threading
import urllib.request
from urllib.error import URLError, HTTPError
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    ConversationHandler,
)
from telegram.error import TimedOut
from dotenv import load_dotenv

# ===== ЛОГИРОВАНИЕ =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('server_bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===== НАСТРОЙКИ ОКРУЖЕНИЯ =====
load_dotenv()

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
SELF_URL = os.getenv('SELF_URL')  # URL этого же сервиса (чтобы бот пинговал сам себя)

# URL, который мониторим (меняется кнопкой)
SERVER_URL = "https://adadadadad-97sj.onrender.com/"

# интервал авто-пинга
UPDATE_INTERVAL = 60  # 1 минута

SET_SITE = 1  # состояние диалога


# ---------------------------------
# CHECK WEBSITE FUNCTION
# ---------------------------------
def check_site(url: str):
    try:
        start = time.time()
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.getcode()
            elapsed = int((time.time() - start) * 1000)
            return {"ok": True, "status": status, "elapsed": elapsed}

    except HTTPError as e:
        return {"ok": False, "status": e.code, "elapsed": None, "error": str(e)}
    except URLError as e:
        return {"ok": False, "status": None, "elapsed": None, "error": str(e)}
    except Exception as e:
        return {"ok": False, "status": None, "elapsed": None, "error": str(e)}


# ---------------------------------
# TELEGRAM BOT FUNCTIONS
# ---------------------------------
def generate_message():
    result = check_site(SERVER_URL)

    if not result["ok"]:
        return (
            f"❌ Сайт недоступен\n"
            f"🌐 URL: <code>{SERVER_URL}</code>\n"
            f"⚠️ Ошибка: <code>{result.get('error')}</code>"
        )

    return (
        f"✅ Сайт доступен\n"
        f"🌐 URL: <code>{SERVER_URL}</code>\n"
        f"📡 HTTP: <b>{result['status']}</b>\n"
        f"⏱ Пинг: <b>{result['elapsed']} мс</b>"
    )


def send_update(context: CallbackContext):
    try:
        msg = generate_message()
        logger.info(f"Пинг {SERVER_URL} → отправка в канал")
        context.bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Ошибка отправки в канал: {e}")


def ping_self(context: CallbackContext):
    if not SELF_URL:
        return
    res = check_site(SELF_URL)
    if res["ok"]:
        logger.info(f"[SELF-PING] {SELF_URL} OK {res['status']} {res.get('elapsed')}ms")
    else:
        logger.warning(f"[SELF-PING] FAIL {res}")


def start(update: Update, context: CallbackContext):
    keyboard = [
        [KeyboardButton("📊 Статус сайта")],
        [KeyboardButton("⚙️ Сменить сайт")],
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    update.message.reply_text("Меню:", reply_markup=markup)


def show_status(update: Update, context: CallbackContext):
    update.message.reply_text(generate_message(), parse_mode='HTML')


def change_site_start(update: Update, context: CallbackContext):
    update.message.reply_text("Отправь новый URL (http/https):", parse_mode='HTML')
    return SET_SITE


def set_site(update: Update, context: CallbackContext):
    global SERVER_URL
    url = update.message.text.strip()

    if not url.startswith("http"):
        update.message.reply_text("⚠️ Неверный URL", parse_mode='HTML')
        return SET_SITE

    SERVER_URL = url
    update.message.reply_text(f"✅ Новый сайт: <code>{url}</code>", parse_mode='HTML')
    return ConversationHandler.END


# ---------------------------------
# MINI HTTP SERVER FOR RENDER
# ---------------------------------
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running")


def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    logger.info(f"HTTP сервер запущен на порту {port}")
    server.serve_forever()


# ---------------------------------
# MAIN FUNCTION
# ---------------------------------
def main():
    if not TOKEN:
        logger.critical("Нет TELEGRAM_BOT_TOKEN")
        return
    if not CHANNEL_ID:
        logger.critical("Нет TELEGRAM_CHANNEL_ID")
        return

    # Запуск маленького HTTP сервера в отдельном потоке
    threading.Thread(target=run_http_server, daemon=True).start()

    # Настройка Telegram бота
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # HANDLERS
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.regex("📊 Статус сайта"), show_status))

    dp.add_handler(ConversationHandler(
        entry_points=[MessageHandler(Filters.regex("⚙️ Сменить сайт"), change_site_start)],
        states={SET_SITE: [MessageHandler(Filters.text & ~Filters.command, set_site)]},
        fallbacks=[]
    ))

    # Периодические задачи
    updater.job_queue.run_repeating(send_update, interval=UPDATE_INTERVAL, first=0)
    updater.job_queue.run_repeating(ping_self, interval=60, first=0)

    logger.info("Бот запущен")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
