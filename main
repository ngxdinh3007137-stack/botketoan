import logging
import sqlite3
import os
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler,
)
from flask import Flask
from threading import Thread

# ======================================================
# ⚠️ CÀI ĐẶT (ĐIỀN LẠI TOKEN VÀ ID CỦA BẠN VÀO ĐÂY)
TOKEN = '8374954088:AAEGsRqgysifY4gOh0df5IUz74r29T5ggW0' 
ADMIN_ID = 7108698925  # Điền ID Admin vào đây
# ======================================================

# --- PHẦN GIỮ BOT SỐNG (KEEP ALIVE) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot đang chạy ngon lành!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
# --------------------------------------

DB_NAME = 'database_kieman.db'
IMAGE_DIR = 'kho_anh_bill'

if not os.path.exists(IMAGE_DIR):
    os.makedirs(IMAGE_DIR)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

CHOOSING = 0
UPLOADING_BILL, INPUTTING_AMOUNT, INPUTTING_NOTE = 1, 2, 3
REPORT_START_DATE, REPORT_END_DATE = 4, 5

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_path TEXT,
            amount REAL,
            note TEXT,
            created_at DATE DEFAULT (date('now', 'localtime')),
            full_timestamp DATETIME DEFAULT (datetime('now', 'localtime'))
        )
    ''')
    conn.commit()
    conn.close()

def convert_date_format(date_str):
    try:
        return datetime.strptime(date_str, '%d/%m/%Y').strftime('%Y-%m-%d')
    except ValueError:
        return None

# --- ADMIN HANDLERS ---
async def lay_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(f"🆔 ID: `{user_id}`", parse_mode='Markdown')

async def xoa_bill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Không phải Admin!")
        return
    try:
        args = context.args
        if not args:
            await update.message.reply_text("⚠️ Gõ: `/xoa ID`", parse_mode='Markdown')
            return
        record_id = int(args[0])
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT image_path FROM records WHERE id = ?", (record_id,))
        row = cursor.fetchone()
        if row:
            try: os.remove(row[0])
            except: pass
            cursor.execute("DELETE FROM records WHERE id = ?", (record_id,))
            conn.commit()
            await update.message.reply_text(f"✅ Đã xóa Bill {record_id}.")
        else:
            await update.message.reply_text(f"❌ Không tìm thấy Bill {record_id}.")
        conn.close()
    except ValueError:
        await update.message.reply_text("⚠️ ID phải là số.")

async def reset_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Cấm!")
        return
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM records")
    conn.commit()
    conn.close()
    await update.message.reply_text("♻️ Đã RESET dữ liệu!")

# --- USER HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [["📝 Gửi Bill mới"], ["📊 Báo cáo hôm nay", "📅 Báo cáo tháng này"], ["🔎 Báo cáo tùy chọn"]]
    await update.message.reply_text(
        "👋 **QUẢN LÝ THU CHI 24/7**\nAdmin commands: `/lay_id`, `/xoa`, `/reset_data`",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True), parse_mode='Markdown'
    )
    return CHOOSING

async def start_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Gửi **Ảnh Bill**:", reply_markup=ReplyKeyboardRemove())
    return UPLOADING_BILL

async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    file_name = f"bill_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    file_path = os.path.join(IMAGE_DIR, file_name)
    await photo_file.download_to_drive(file_path)
    context.user_data['path'] = file_path
    await update.message.reply_text("💰 Nhập **Số tiền**:")
    return INPUTTING_AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        raw_num = update.message.text.replace(',', '').replace('.', '')
        amount = float(raw_num)
        context.user_data['amount'] = amount
        await update.message.reply_text("📝 Nhập **Ghi chú**:")
        return INPUTTING_NOTE
    except ValueError:
        await update.message.reply_text("⚠️ Nhập số thôi:")
        return INPUTTING_AMOUNT

async def save_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text
    amount = context.user_data['amount']
    path = context.user_data['path']
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO records (image_path, amount, note) VALUES (?, ?, ?)", (path, amount, note))
    rid = cursor.lastrowid
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ **ĐÃ LƯU** (ID: {rid})\n💵 {amount:,.0f}đ\n📝 {note}", parse_mode='Markdown')
    context.user_data.clear()
    return await start(update, context)

async def ask_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📅 Ngày BẮT ĐẦU (dd/mm/yyyy):", reply_markup=ReplyKeyboardRemove())
    return REPORT_START_DATE

async def get_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = convert_date_format(update.message.text)
    if not d:
        await update.message.reply_text("⚠️ Sai định dạng. Nhập lại:")
        return REPORT_START_DATE
    context.user_data['s'] = d
    context.user_data['ds'] = update.message.text
    await update.message.reply_text("📅 Ngày KẾT THÚC (dd/mm/yyyy):")
    return REPORT_END_DATE

async def get_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = convert_date_format(update.message.text)
    if not d: return REPORT_END_DATE
    await run_report(update, context, "custom", context.user_data['s'], d, f"TỪ {context.user_data['ds']} ĐẾN {update.message.text}")
    return await start(update, context)

async def run_report(update, context, q_type, s=None, e=None, title=""):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if q_type == "today":
        c.execute("SELECT id, amount, note, image_path, full_timestamp FROM records WHERE created_at = date('now', 'localtime')")
        title = "HÔM NAY"
    elif q_type == "month":
        c.execute("SELECT id, amount, note, image_path, full_timestamp FROM records WHERE strftime('%m', created_at) = strftime('%m', 'now')")
        title = "THÁNG NÀY"
    else:
        c.execute("SELECT id, amount, note, image_path, full_timestamp FROM records WHERE created_at BETWEEN ? AND ?", (s, e))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text(f"❌ Không có dữ liệu {title}")
        return
    total = sum(r[1] for r in rows)
    await update.message.reply_text(f"📊 **BÁO CÁO: {title}**\nSL: {len(rows)} | Tổng: **{total:,.0f}đ**", parse_mode='Markdown')
    for r in rows:
        try: await update.message.reply_photo(photo=open(r[3], 'rb'), caption=f"🆔 {r[0]} | 💵 {r[1]:,.0f}đ\n📝 {r[2]}")
        except: pass

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Đã hủy.")
    return ConversationHandler.END

def main():
    init_db()
    keep_alive() # <--- Kích hoạt web server
    app_bot = Application.builder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("lay_id", lay_id))
    app_bot.add_handler(CommandHandler("xoa", xoa_bill))
    app_bot.add_handler(CommandHandler("reset_data", reset_data))
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start), MessageHandler(filters.Regex("^📝"), start_upload), MessageHandler(filters.Regex("^🔎"), ask_start_date)],
        states={
            CHOOSING: [MessageHandler(filters.Regex("^📝"), start_upload), MessageHandler(filters.Regex("^🔎"), ask_start_date), MessageHandler(filters.Regex("^📊"), lambda u, c: run_report(u, c, "today")), MessageHandler(filters.Regex("^📅"), lambda u, c: run_report(u, c, "month"))],
            UPLOADING_BILL: [MessageHandler(filters.PHOTO, get_photo)],
            INPUTTING_AMOUNT: [MessageHandler(filters.TEXT, get_amount)],
            INPUTTING_NOTE: [MessageHandler(filters.TEXT, save_data)],
            REPORT_START_DATE: [MessageHandler(filters.TEXT, get_start_date)],
            REPORT_END_DATE: [MessageHandler(filters.TEXT, get_end_date)],
        }, fallbacks=[CommandHandler("cancel", cancel)]
    )
    app_bot.add_handler(conv)
    print("BOT ĐANG CHẠY 24/7...")
    app_bot.run_polling()

if __name__ == '__main__':
    main()
