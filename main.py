import logging
import sqlite3
import os
import uuid
import threading
import pandas as pd
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from flask import Flask

# ==========================================
# ⚠️ CẤU HÌNH HỆ THỐNG
TOKEN = '8374954088:AAEGsRqgysifY4gOh0df5IUz74r29T5ggW0'
ADMIN_ID = 7108698925  # THAY ID CỦA BẠN VÀO ĐÂY (Dùng lệnh /lay_id để lấy)
# ==========================================

DB_NAME = 'database_kieman.db'
IMAGE_DIR = 'kho_anh_bill'

# Các trạng thái hội thoại
CHOOSING, UPLOADING_BILL, INPUTTING_AMOUNT, INPUTTING_NOTE, CONFIRMING_SAVE = range(5)

if not os.path.exists(IMAGE_DIR): os.makedirs(IMAGE_DIR)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- HÀM XỬ LÝ TIỀN THÔNG MINH ---
def parse_money(text):
    try:
        text = text.lower().replace('đ', '').replace('d', '').replace(' ', '')
        text = text.replace('.', '') # Xóa dấu chấm phân cách hàng nghìn
        
        multiplier = 1
        if 'k' in text:
            multiplier = 1000
            text = text.replace('k', '').replace(',', '.') # Chuyển 10,5k thành 10.5
        else:
            text = text.replace(',', '') # Xóa dấu phẩy nếu là dạng 100,000

        amount = float(text) * multiplier
        return amount
    except:
        return None

# --- WEB SERVER (GIỮ BOT SỐNG) ---
app_web = Flask(__name__)
@app_web.route('/')
def home(): return "BOT KETOAN VIP ĐANG CHẠY!"

def run_flask(): app_web.run(host='0.0.0.0', port=8080)

# --- DATABASE ---
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

# --- LOGIC ĐIỀU KHIỂN ---

async def lay_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 ID của bạn là: `{update.effective_user.id}`", parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [["📝 Gửi Bill"], ["📊 Báo cáo Hôm nay"]]
    await update.message.reply_text(
        "👋 **HỆ THỐNG QUẢN LÝ HÓA ĐƠN**\nChọn chức năng bên dưới:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )
    return CHOOSING

# --- LUỒNG GỬI BILL ---

async def bat_dau_gui_anh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_photos'] = []
    await update.message.reply_text(
        "📸 **BƯỚC 1: GỬI ẢNH**\nBạn có thể gửi nhiều ảnh cùng lúc. Gửi xong hãy bấm nút xác nhận.",
        reply_markup=ReplyKeyboardMarkup([["✅ Đã gửi xong ảnh"], ["❌ Hủy đơn"]], resize_keyboard=True),
        parse_mode='Markdown'
    )
    return UPLOADING_BILL

async def nhan_anh_loop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    file_path = os.path.join(IMAGE_DIR, f"{uuid.uuid4()}.jpg")
    await photo_file.download_to_drive(file_path)
    context.user_data['temp_photos'].append(file_path)
    return UPLOADING_BILL

async def chot_anh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('temp_photos'):
        await update.message.reply_text("⚠️ Bạn chưa gửi ảnh nào! Vui lòng gửi ảnh hoặc bấm Hủy.")
        return UPLOADING_BILL
    
    await update.message.reply_text(
        f"👌 Đã nhận {len(context.user_data['temp_photos'])} ảnh.\n💰 **BƯỚC 2: NHẬP SỐ TIỀN**\n(VD: 100k, 10,5k, 200.000...)",
        reply_markup=ReplyKeyboardMarkup([["❌ Hủy đơn"]], resize_keyboard=True),
        parse_mode='Markdown'
    )
    return INPUTTING_AMOUNT

async def nhap_tien(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = parse_money(update.message.text)
    if amount is None:
        await update.message.reply_text("⚠️ Không hiểu số tiền này. Hãy nhập lại (VD: 50k, 150000):")
        return INPUTTING_AMOUNT
    
    context.user_data['amount'] = amount
    await update.message.reply_text(
        f"✅ Tiền: `{'{:,.0f}'.format(amount)}đ`\n📝 **BƯỚC 3: NHẬP NỘI DUNG/GHI CHÚ**",
        reply_markup=ReplyKeyboardMarkup([["❌ Hủy đơn"]], resize_keyboard=True),
        parse_mode='Markdown'
    )
    return INPUTTING_NOTE

async def xem_truoc_don(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['note'] = update.message.text
    
    # Tạo bản xem trước
    preview = (
        f"🔍 **XÁC NHẬN THÔNG TIN**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📸 Số ảnh: {len(context.user_data['temp_photos'])}\n"
        f"💰 Số tiền: `{'{:,.0f}'.format(context.user_data['amount'])}đ`\n"
        f"📝 Ghi chú: {context.user_data['note']}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"Bấm **LƯU** để hoàn tất hoặc **HỦY** để làm lại."
    )
    
    await update.message.reply_text(
        preview,
        reply_markup=ReplyKeyboardMarkup([["💾 XÁC NHẬN LƯU"], ["❌ Hủy bỏ"]], resize_keyboard=True),
        parse_mode='Markdown'
    )
    return CONFIRMING_SAVE

async def hoan_tat_luu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photos = ";".join(context.user_data['temp_photos'])
    amount = context.user_data['amount']
    note = context.user_data['note']

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO records (user_id, image_paths, amount, note) VALUES (?, ?, ?, ?)", 
              (user_id, photos, amount, note))
    new_id = c.lastrowid
    conn.commit()
    conn.close()

    context.user_data.clear()
    await update.message.reply_text(
        f"🚀 **ĐÃ LƯU THÀNH CÔNG!**\n🆔 Mã hóa đơn: `{new_id}`",
        reply_markup=ReplyKeyboardMarkup([["📝 Gửi Bill"], ["📊 Báo cáo Hôm nay"]], resize_keyboard=True),
        parse_mode='Markdown'
    )
    return CHOOSING

# --- CHỨC NĂNG ADMIN & BÁO CÁO ---

async def xuat_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        start_str = context.args[0]
        end_str = context.args[1]
        
        # Chuyển ngày sang định dạng SQL
        start_dt = datetime.strptime(start_str, '%d/%m/%Y').strftime('%Y-%m-%d')
        end_dt = datetime.strptime(end_str, '%d/%m/%Y').strftime('%Y-%m-%d')

        conn = sqlite3.connect(DB_NAME)
        query = f"SELECT id, full_timestamp, amount, note, image_paths FROM records WHERE created_at BETWEEN '{start_dt}' AND '{end_dt}'"
        df = pd.read_sql_query(query, conn)
        conn.close()

        if df.empty:
            await update.message.reply_text("❌ Không có dữ liệu trong khoảng này.")
            return

        file_name = f"Bao_cao_{start_str.replace('/','_')}.xlsx"
        df.columns = ['ID Hóa đơn', 'Thời gian gửi', 'Tổng tiền', 'Nội dung', 'Đường dẫn ảnh']
        df.to_excel(file_name, index=False)

        await update.message.reply_document(document=open(file_name, 'rb'), caption=f"📊 Báo cáo từ {start_str} đến {end_str}")
        os.remove(file_name)
    except:
        await update.message.reply_text("⚠️ Cú pháp: `/xuat 01/01/2026 10/01/2026`", parse_mode='Markdown')

async def xoa_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Chỉ Admin mới có quyền xóa!")
        return
    try:
        target_id = context.args[0]
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM records WHERE id = ?", (target_id,))
        conn.commit()
        if c.rowcount > 0:
            await update.message.reply_text(f"✅ Đã xóa hóa đơn ID: {target_id}")
        else:
            await update.message.reply_text("❓ Không tìm thấy ID này.")
        conn.close()
    except:
        await update.message.reply_text("⚠️ Cú pháp: `/xoa 5`", parse_mode='Markdown')

async def reset_he_thong(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Quyền Admin!")
        return
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM records")
    c.execute("DELETE FROM sqlite_sequence WHERE name='records'")
    conn.commit()
    conn.close()
    await update.message.reply_text("🗑️ **DỮ LIỆU ĐÃ ĐƯỢC RESET VỀ 0!**")

async def bao_cao_nhanh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT SUM(amount) FROM records WHERE date(created_at) = date('now', 'localtime')")
    total = c.fetchone()[0] or 0
    conn.close()
    await update.message.reply_text(f"📊 **Tổng chi hôm nay:** `{'{:,.0f}'.format(total)}đ`", parse_mode='Markdown')
    return CHOOSING

async def huy_thao_tac(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🚫 Đã hủy.", reply_markup=ReplyKeyboardMarkup([["📝 Gửi Bill"], ["📊 Báo cáo Hôm nay"]], resize_keyboard=True))
    return CHOOSING

def main():
    init_db()
    threading.Thread(target=run_flask).start()
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            MessageHandler(filters.Regex("^📝 Gửi Bill"), bat_dau_gui_anh),
            MessageHandler(filters.Regex("^📊 Báo cáo"), bao_cao_nhanh)
        ],
        states={
            CHOOSING: [
                MessageHandler(filters.Regex("^📝 Gửi Bill"), bat_dau_gui_anh),
                MessageHandler(filters.Regex("^📊 Báo cáo"), bao_cao_nhanh)
            ],
            UPLOADING_BILL: [
                MessageHandler(filters.PHOTO, nhan_anh_loop),
                MessageHandler(filters.Regex("^✅ Đã gửi xong ảnh"), chot_anh),
                MessageHandler(filters.Regex("^❌ Hủy đơn"), huy_thao_tac)
            ],
            INPUTTING_AMOUNT: [
                MessageHandler(filters.Regex("^❌ Hủy đơn"), huy_thao_tac),
                MessageHandler(filters.TEXT & ~filters.COMMAND, nhap_tien)
            ],
            INPUTTING_NOTE: [
                MessageHandler(filters.Regex("^❌ Hủy đơn"), huy_thao_tac),
                MessageHandler(filters.TEXT & ~filters.COMMAND, xem_truoc_don)
            ],
            CONFIRMING_SAVE: [
                MessageHandler(filters.Regex("^💾 XÁC NHẬN LƯU"), hoan_tat_luu),
                MessageHandler(filters.Regex("^❌ Hủy bỏ"), huy_thao_tac)
            ]
        },
        fallbacks=[CommandHandler('cancel', huy_thao_tac)]
    )

    app.add_handler(CommandHandler("lay_id", lay_id))
    app.add_handler(CommandHandler("xuat", xuat_excel))
    app.add_handler(CommandHandler("xoa", xoa_id))
    app.add_handler(CommandHandler("reset", reset_he_thong))
    app.add_handler(conv_handler)

    print("--- BOT KẾ TOÁN ĐANG CHẠY ---")
    app.run_polling()

if __name__ == '__main__':
    main()
