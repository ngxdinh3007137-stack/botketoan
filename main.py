import logging
import sqlite3
import os
import uuid
import threading
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from flask import Flask

# ==========================================
# ⚠️ CẤU HÌNH ADMIN (QUAN TRỌNG)
TOKEN = '8374954088:AAEGsRqgysifY4gOh0df5IUz74r29T5ggW0'

# Điền ID của bạn vào đây để dùng lệnh /reset (Xóa dữ liệu)
# Nếu chưa biết ID, hãy chạy bot rồi chat /lay_id để lấy
ADMIN_ID = 7108698925 
# ==========================================

DB_NAME = 'database_kieman.db'
IMAGE_DIR = 'kho_anh_bill'

# Các trạng thái hội thoại
CHOOSING, UPLOADING_BILL, INPUTTING_AMOUNT, INPUTTING_NOTE = range(4)

if not os.path.exists(IMAGE_DIR): os.makedirs(IMAGE_DIR)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- PHẦN 1: WEB SERVER (GIỮ BOT SỐNG) ---
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "BOT KETOAN PUBLIC DANG CHAY!"

def run_flask():
    app_web.run(host='0.0.0.0', port=8080)

# --- PHẦN 2: DATABASE ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    image_paths TEXT,
                    amount REAL,
                    note TEXT,
                    created_at DATE DEFAULT (date('now', 'localtime')),
                    full_timestamp DATETIME DEFAULT (datetime('now', 'localtime'))
                )''')
    conn.commit()
    conn.close()

# --- PHẦN 3: LOGIC BOT ---

# Lệnh lấy ID (Ai cũng dùng được để biết ID của mình)
async def lay_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 ID Telegram của bạn là: `{update.effective_user.id}`", parse_mode='Markdown')

# Lệnh Reset dữ liệu (CHỈ ADMIN MỚI ĐƯỢC DÙNG)
async def reset_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Kiểm tra xem người bấm có phải Admin không
    if ADMIN_ID == 0:
        await update.message.reply_text("⚠️ Bạn chưa cài đặt ADMIN_ID trong code! Hãy điền ID vào file main.py trước.")
        return
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ **BẠN KHÔNG CÓ QUYỀN!**\nChỉ Admin mới được xóa dữ liệu.")
        return

    # Nếu đúng là Admin thì xóa sạch
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM records")                 # Xóa hết dòng
    c.execute("DELETE FROM sqlite_sequence WHERE name='records'") # Reset ID về 1
    conn.commit()
    conn.close()
    
    await update.message.reply_text("🗑️ **ĐÃ XÓA SẠCH DỮ LIỆU!**\nBộ đếm ID đã quay về 1.")

# Bắt đầu (Ai cũng dùng được)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    reply_keyboard = [["📝 Gửi Bill (Nhiều ảnh)"], ["📊 Báo cáo Hôm nay"]]
    await update.message.reply_text(
        f"👋 Chào {user_name}!\nBot Kế Toán đã sẵn sàng nhận đơn.",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )
    return CHOOSING

# Quy trình gửi ảnh (Ai cũng dùng được)
async def bat_dau_gui_anh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_photos'] = [] 
    reply_keyboard = [["✅ Đã gửi xong ảnh", "❌ Hủy"]]
    await update.message.reply_text(
        "📸 **Mời gửi ảnh Bill!**\n(Bạn có thể chọn nhiều ảnh cùng lúc)\n\n👉 Gửi xong bấm **'✅ Đã gửi xong ảnh'**.",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )
    return UPLOADING_BILL

async def nhan_anh_loop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    file_name = f"{uuid.uuid4()}.jpg"
    file_path = os.path.join(IMAGE_DIR, file_name)
    await photo_file.download_to_drive(file_path)
    context.user_data['temp_photos'].append(file_path)
    return UPLOADING_BILL

async def chot_anh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    so_luong = len(context.user_data.get('temp_photos', []))
    if so_luong == 0:
        await update.message.reply_text("⚠️ Chưa có ảnh nào! Gửi lại đi ạ.")
        return UPLOADING_BILL

    await update.message.reply_text(
        f"👌 Đã nhận {so_luong} ảnh.\n💰 **Tổng tiền là bao nhiêu?** (VD: 150k)",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    return INPUTTING_AMOUNT

async def nhap_tien(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    clean_text = text.lower().replace('k', '000').replace(',', '').replace('.', '').replace(' ', '')
    try:
        amount = float(clean_text)
        context.user_data['amount'] = amount
        await update.message.reply_text("📝 **Ghi chú cho đơn này:**")
        return INPUTTING_NOTE
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền không đúng. Nhập lại số (VD: 50000):")
        return INPUTTING_AMOUNT

async def nhap_ghi_chu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text
    amount = context.user_data['amount']
    photos = context.user_data['temp_photos']
    user_id = update.effective_user.id
    photos_str = ";".join(photos)

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO records (user_id, image_paths, amount, note) VALUES (?, ?, ?, ?)",
              (user_id, photos_str, amount, note))
    conn.commit()
    conn.close()

    context.user_data.clear()
    reply_keyboard = [["📝 Gửi Bill (Nhiều ảnh)"], ["📊 Báo cáo Hôm nay"]]
    await update.message.reply_text(
        f"✅ **LƯU XONG!**\n💸: `{'{:,.0f}'.format(amount)}`\n📝: {note}",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )
    return CHOOSING

async def bao_cao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT SUM(amount) FROM records WHERE date(created_at) = date('now', 'localtime')")
    row = c.fetchone()
    total = row[0] if row[0] else 0
    conn.close()
    await update.message.reply_text(f"📊 **Hôm nay cả nhóm tiêu:** `{'{:,.0f}'.format(total)}` VNĐ", parse_mode='Markdown')
    return CHOOSING

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Đã hủy.", reply_markup=ReplyKeyboardRemove())
    return await start(update, context)

def main():
    init_db()
    threading.Thread(target=run_flask).start()
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            MessageHandler(filters.Regex("^📝 Gửi Bill"), bat_dau_gui_anh),
            MessageHandler(filters.Regex("^📊 Báo cáo"), bao_cao)
        ],
        states={
            CHOOSING: [
                MessageHandler(filters.Regex("^📝 Gửi Bill"), bat_dau_gui_anh),
                MessageHandler(filters.Regex("^📊 Báo cáo"), bao_cao)
            ],
            UPLOADING_BILL: [
                MessageHandler(filters.PHOTO, nhan_anh_loop),      
                MessageHandler(filters.Regex("^✅ Đã gửi xong ảnh"), chot_anh),
                MessageHandler(filters.Regex("^❌ Hủy"), cancel)
            ],
            INPUTTING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_tien)],
            INPUTTING_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_ghi_chu)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Đăng ký các lệnh phụ
    app.add_handler(CommandHandler("lay_id", lay_id))
    app.add_handler(CommandHandler("reset", reset_data)) # Lệnh này chỉ Admin dùng được
    app.add_handler(conv_handler)
    
    print("BOT PUBLIC DANG CHAY...")
    app.run_polling()

if __name__ == '__main__':
    main()
