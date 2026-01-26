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
# ⚠️ CẤU HÌNH CỦA BẠN (SỬA Ở ĐÂY)
TOKEN = 'DÁN_TOKEN_CỦA_BẠN_VÀO_ĐÂY'
ADMIN_ID = 0  # Chạy bot, chat /lay_id để lấy số này điền vào (hoặc để 0 nếu muốn ai cũng dùng được)
# ==========================================

DB_NAME = 'database_kieman.db'
IMAGE_DIR = 'kho_anh_bill'

# Các trạng thái hội thoại
CHOOSING, UPLOADING_BILL, INPUTTING_AMOUNT, INPUTTING_NOTE = range(4)

if not os.path.exists(IMAGE_DIR): os.makedirs(IMAGE_DIR)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- PHẦN 1: WEB SERVER (ĐỂ GIỮ BOT SỐNG TRÊN RENDER) ---
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "BOT KETOAN (NHIEU ANH) DANG CHAY NGON LANH!"

def run_flask():
    # Render yêu cầu chạy trên cổng 0.0.0.0 (Port mặc định 10000 hoặc 8080)
    app_web.run(host='0.0.0.0', port=8080)

# --- PHẦN 2: DATABASE ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Lưu ý: Cột image_paths (số nhiều) để lưu chuỗi các ảnh
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

# Hàm kiểm tra chủ nhà
async def check_auth(update: Update):
    if ADMIN_ID != 0 and update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Xin lỗi, Bot này là tài sản riêng!")
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Nếu chưa điền ADMIN_ID thì bỏ qua check, nếu điền rồi thì check
    if ADMIN_ID != 0 and update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(f"⛔ Bot riêng tư.\nID của bạn là: `{update.effective_user.id}` (Dùng để điền vào code)", parse_mode='Markdown')
        return ConversationHandler.END

    user_name = update.effective_user.first_name
    reply_keyboard = [["📝 Gửi Bill (Nhiều ảnh)"], ["📊 Báo cáo Hôm nay"]]
    await update.message.reply_text(
        f"👋 Chào sếp {user_name}!\nBot đã sẵn sàng chế độ **GOM NHIỀU ẢNH**.",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )
    return CHOOSING

async def lay_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 ID Của Bạn: `{update.effective_user.id}`", parse_mode='Markdown')

# Bắt đầu quy trình gửi ảnh
async def bat_dau_gui_anh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return ConversationHandler.END
    
    context.user_data['temp_photos'] = [] # Tạo giỏ hàng rỗng
    
    reply_keyboard = [["✅ Đã gửi xong ảnh", "❌ Hủy"]]
    await update.message.reply_text(
        "📸 **CHẾ ĐỘ GỬI NHIỀU ẢNH**\n\n"
        "1. Chọn 1 hoặc nhiều ảnh gửi vào đây.\n"
        "2. Bot sẽ tự gom lại.\n"
        "3. Gửi xong bấm nút **'✅ Đã gửi xong ảnh'**.",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )
    return UPLOADING_BILL

# Vòng lặp nhận ảnh
async def nhan_anh_loop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    file_name = f"{uuid.uuid4()}.jpg"
    file_path = os.path.join(IMAGE_DIR, file_name)
    await photo_file.download_to_drive(file_path)
    
    # Thêm vào giỏ
    context.user_data['temp_photos'].append(file_path)
    
    # Phản hồi nhẹ (nếu gửi album nó sẽ nhảy liên tục, Telegram tự xử lý)
    return UPLOADING_BILL

# Chốt đơn ảnh
async def chot_anh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    so_luong = len(context.user_data.get('temp_photos', []))
    
    if so_luong == 0:
        await update.message.reply_text("⚠️ Chưa có ảnh nào cả! Gửi lại đi sếp.")
        return UPLOADING_BILL

    await update.message.reply_text(
        f"👌 **Đã gom {so_luong} ảnh.**\n"
        "💰 Nhập **TỔNG SỐ TIỀN** (ví dụ: 150k):",
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
        await update.message.reply_text("📝 Nhập **Ghi chú** (Ăn uống, cafe, xăng...):")
        return INPUTTING_NOTE
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền sai rồi. Nhập lại số (ví dụ: 50000):")
        return INPUTTING_AMOUNT

async def nhap_ghi_chu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text
    amount = context.user_data['amount']
    photos = context.user_data['temp_photos']
    user_id = update.effective_user.id
    
    # Nối danh sách ảnh thành chuỗi: "anh1.jpg;anh2.jpg"
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
        f"✅ **LƯU THÀNH CÔNG!**\n\n"
        f"💸 Tiền: `{'{:,.0f}'.format(amount)}`\n"
        f"📸 Ảnh: {len(photos)} tấm\n"
        f"📝 Note: {note}",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )
    return CHOOSING

async def bao_cao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return ConversationHandler.END
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT SUM(amount) FROM records WHERE date(created_at) = date('now', 'localtime')")
    row = c.fetchone()
    total = row[0] if row[0] else 0
    conn.close()
    
    await update.message.reply_text(f"📊 **Hôm nay tiêu hết:** `{'{:,.0f}'.format(total)}` VNĐ", parse_mode='Markdown')
    return CHOOSING

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Đã hủy.", reply_markup=ReplyKeyboardRemove())
    return await start(update, context)

# --- CHẠY CHƯƠNG TRÌNH ---
def main():
    init_db()
    
    # 1. Chạy Web Server ở luồng riêng (Cho Render & UptimeRobot)
    threading.Thread(target=run_flask).start()

    # 2. Chạy Bot Telegram
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

    app.add_handler(CommandHandler("lay_id", lay_id))
    app.add_handler(conv_handler)
    
    print("BOT FULL CHUC NANG DANG CHAY...")
    app.run_polling()

if __name__ == '__main__':
    main()
