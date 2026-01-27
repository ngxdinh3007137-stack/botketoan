import logging
import sqlite3
import os
import uuid
import threading
import pandas as pd
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
from flask import Flask

# ==========================================
# ⚠️ CẤU HÌNH ADMIN
TOKEN = '8374954088:AAEGsRqgysifY4gOh0df5IUz74r29T5ggW0'
ADMIN_ID = 7108698925  # ⚠️ THAY ID CỦA BẠN VÀO ĐÂY (CHẠY BOT RỒI CHAT /lay_id ĐỂ LẤY)
# ==========================================

DB_NAME = 'database_kieman.db'
IMAGE_DIR = 'kho_anh_bill'

# Các trạng thái
NHAP_TIEN, NHAP_NOTE = range(2)

if not os.path.exists(IMAGE_DIR): os.makedirs(IMAGE_DIR)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- XỬ LÝ SỐ TIỀN ---
def parse_money(text):
    try:
        text = text.lower().replace('đ', '').replace('d', '').replace(' ', '')
        text = text.replace('.', '') 
        multiplier = 1
        if 'k' in text:
            multiplier = 1000
            text = text.replace('k', '').replace(',', '.') 
        else:
            text = text.replace(',', '')
        return float(text) * multiplier
    except:
        return None

# --- WEB SERVER ---
app_web = Flask(__name__)
@app_web.route('/')
def home(): return "BOT KETOAN V2.0 ONLINE!"
def run_flask(): 
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER, image_path TEXT, amount REAL, note TEXT,
                    created_at DATE DEFAULT (date('now', 'localtime')),
                    full_timestamp DATETIME DEFAULT (datetime('now', 'localtime'))
                )''')
    conn.commit()
    conn.close()

# --- GIAO DIỆN MENU CHÍNH ---
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = "👋 **CHÀO MỪNG ĐẾN HỆ THỐNG KẾ TOÁN**\n\nHãy chọn chức năng bên dưới:"
    
    # Nút bấm cơ bản cho mọi người
    buttons = [
        [InlineKeyboardButton("📸 Gửi Hóa Đơn Mới", callback_data="btn_gui_bill")],
        [InlineKeyboardButton("📊 Báo Cáo Hôm Nay", callback_data="btn_baocao_today")]
    ]

    # Nếu là Admin thì hiện thêm nút quản trị
    if user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton("📂 Xuất Excel (Admin)", callback_data="btn_xuat_excel")])
        buttons.append([InlineKeyboardButton("🔥 Reset Data (Admin)", callback_data="btn_reset")])

    keyboard = InlineKeyboardMarkup(buttons)
    
    # Xử lý gửi mới hoặc sửa tin nhắn cũ
    if update.callback_query:
        await update.callback_query.message.edit_text(msg, reply_markup=keyboard, parse_mode='Markdown')
    else:
        await update.message.reply_text(msg, reply_markup=keyboard, parse_mode='Markdown')

# --- LUỒNG XỬ LÝ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_menu(update, context)
    return ConversationHandler.END

async def lay_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 ID của bạn: `{update.effective_user.id}`", parse_mode='Markdown')

# 1. BẮT ĐẦU GỬI BILL
async def btn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "btn_gui_bill":
        await query.message.reply_text("📸 **Vui lòng gửi ảnh hóa đơn ngay tại đây:**")
        return # Chờ người dùng gửi ảnh (không cần state vì dùng MessageHandler riêng)
    
    elif data == "btn_baocao_today":
        await bao_cao_nhanh(update, context)
    
    elif data == "btn_xuat_excel":
        await query.message.reply_text("📅 Nhập khoảng ngày xuất báo cáo theo cú pháp:\n`/xuat 01/01/2026 31/01/2026`", parse_mode='Markdown')
    
    elif data == "btn_reset":
        # Xác nhận lần nữa cho Admin
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔥 XÁC NHẬN XÓA", callback_data="confirm_reset"), InlineKeyboardButton("Hủy", callback_data="cancel_action")]])
        await query.message.edit_text("⚠️ **CẢNH BÁO ADMIN**\nBạn có chắc muốn xóa sạch dữ liệu không?", reply_markup=kb, parse_mode='Markdown')

    elif data == "confirm_reset":
        if update.effective_user.id == ADMIN_ID:
            conn = sqlite3.connect(DB_NAME)
            conn.cursor().execute("DELETE FROM records")
            conn.commit()
            conn.close()
            await query.message.edit_text("✅ Đã Reset hệ thống thành công!")
            await show_menu(update, context)
    
    elif data == "cancel_action":
        await show_menu(update, context)

# 2. NHẬN ẢNH VÀ HỎI TIỀN
async def nhan_anh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Lưu ảnh
    photo_file = await update.message.photo[-1].get_file()
    file_name = f"{uuid.uuid4()}.jpg"
    file_path = os.path.join(IMAGE_DIR, file_name)
    await photo_file.download_to_drive(file_path)
    
    context.user_data['temp_img'] = file_path
    context.user_data['temp_file_id'] = update.message.photo[-1].file_id # Lưu ID để gửi lại cho nhanh

    await update.message.reply_text("💰 **Nhập số tiền:**\n(Ví dụ: 100k, 150.000, 10,5k...)")
    return NHAP_TIEN

# 3. NHẬN TIỀN VÀ HỎI NOTE
async def nhap_tien(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = parse_money(update.message.text)
    if amount is None:
        await update.message.reply_text("⚠️ Số tiền không hợp lệ. Vui lòng nhập lại (VD: 50k):")
        return NHAP_TIEN
    
    context.user_data['temp_amount'] = amount
    await update.message.reply_text("📝 **Nhập nội dung/ghi chú cho hóa đơn này:**")
    return NHAP_NOTE

# 4. XEM TRƯỚC (PREVIEW) - QUAN TRỌNG
async def nhap_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text
    context.user_data['temp_note'] = note
    
    # Tạo nội dung xem trước
    msg = (f"🔍 **XÁC NHẬN HÓA ĐƠN**\n"
           f"💸 Số tiền: `{'{:,.0f}'.format(context.user_data['temp_amount'])} đ`\n"
           f"📝 Nội dung: {note}\n\n"
           f"Bạn có muốn lưu hóa đơn này không?")
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ LƯU NGAY", callback_data="save_bill")],
        [InlineKeyboardButton("❌ HỦY BỎ", callback_data="cancel_bill")]
    ])

    # Gửi lại ẢNH + CAPTION để user check
    await update.message.reply_photo(
        photo=context.user_data['temp_file_id'],
        caption=msg,
        reply_markup=kb,
        parse_mode='Markdown'
    )
    return ConversationHandler.END # Kết thúc state nhập liệu, chuyển sang xử lý nút bấm

# 5. XỬ LÝ NÚT LƯU / HỦY
async def save_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "save_bill":
        # Lưu vào DB
        user_id = query.from_user.id
        path = context.user_data.get('temp_img')
        amt = context.user_data.get('temp_amount')
        note = context.user_data.get('temp_note')
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO records (user_id, image_path, amount, note) VALUES (?, ?, ?, ?)", 
                  (user_id, path, amt, note))
        conn.commit()
        conn.close()
        
        await query.message.edit_caption(caption=f"✅ **ĐÃ LƯU THÀNH CÔNG!**\n💸 `{'{:,.0f}'.format(amt)} đ` - {note}", parse_mode='Markdown')
        await show_menu(update, context) # Quay về menu chính
        
    elif query.data == "cancel_bill":
        if 'temp_img' in context.user_data:
            try: os.remove(context.user_data['temp_img']) # Xóa ảnh tạm
            except: pass
        await query.message.edit_caption(caption="🚫 **ĐÃ HỦY HÓA ĐƠN NÀY**", parse_mode='Markdown')
        await show_menu(update, context)

# --- CHỨC NĂNG BÁO CÁO ---
async def bao_cao_nhanh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT SUM(amount) FROM records WHERE date(created_at) = date('now', 'localtime')")
    total = c.fetchone()[0] or 0
    conn.close()
    
    msg = f"📊 **THỐNG KÊ HÔM NAY**\n━━━━━━━━━━━━\n💰 Tổng chi: `{'{:,.0f}'.format(total)} đ`"
    
    if update.callback_query:
        await update.callback_query.message.reply_text(msg, parse_mode='Markdown')
        # Hiển thị lại menu để ko bị cụt
        await show_menu(update, context)
    else:
        await update.message.reply_text(msg, parse_mode='Markdown')

async def xuat_excel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        start_str = context.args[0]
        end_str = context.args[1]
        s_date = datetime.strptime(start_str, '%d/%m/%Y').strftime('%Y-%m-%d')
        e_date = datetime.strptime(end_str, '%d/%m/%Y').strftime('%Y-%m-%d')

        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql_query(f"SELECT id, created_at, amount, note, image_path FROM records WHERE created_at BETWEEN '{s_date}' AND '{e_date}'", conn)
        conn.close()
        
        if df.empty:
            await update.message.reply_text("❌ Không có dữ liệu.")
            return

        filename = f"Baocao_{start_str.replace('/','-')}.xlsx"
        # Logic tạo Excel cơ bản
        df.to_excel(filename, index=False)
        
        await update.message.reply_document(open(filename, 'rb'), caption=f"📂 Báo cáo từ {start_str} đến {end_str}")
        os.remove(filename)
    except:
        await update.message.reply_text("⚠️ Sai cú pháp! Ví dụ: `/xuat 01/01/2026 31/01/2026`", parse_mode='Markdown')

async def xoa_bill_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        id_can_xoa = context.args[0]
        conn = sqlite3.connect(DB_NAME)
        conn.cursor().execute("DELETE FROM records WHERE id = ?", (id_can_xoa,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Đã xóa bill ID: {id_can_xoa}")
    except:
        await update.message.reply_text("⚠️ Dùng lệnh: `/xoa [ID]`")

# --- MAIN ---
def main():
    init_db()
    threading.Thread(target=run_flask).start()
    app = Application.builder().token(TOKEN).build()

    # Conversation cho việc nhập tiền/note
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.PHOTO, nhan_anh)], # Hễ gửi ảnh là bắt đầu quy trình
        states={
            NHAP_TIEN: [MessageHandler(filters.TEXT, nhap_tien)],
            NHAP_NOTE: [MessageHandler(filters.TEXT, nhap_note)]
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("lay_id", lay_id))
    app.add_handler(CommandHandler("xuat", xuat_excel_cmd))
    app.add_handler(CommandHandler("xoa", xoa_bill_cmd))
    app.add_handler(CallbackQueryHandler(save_callback, pattern="^(save_bill|cancel_bill)$"))
    app.add_handler(CallbackQueryHandler(btn_handler)) # Xử lý các nút menu chính
    app.add_handler(conv)

    print("BOT V2.0 STARTED")
    app.run_polling()

if __name__ == '__main__':
    main()
