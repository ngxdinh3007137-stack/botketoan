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
# ⚠️ CẤU HÌNH HỆ THỐNG
TOKEN = '8374954088:AAEGsRqgysifY4gOh0df5IUz74r29T5ggW0'
ADMIN_ID = 7108698925  # Thay ID của bạn vào đây
# ==========================================

DB_NAME = 'database_kieman.db'
IMAGE_DIR = 'kho_anh_bill'

# States
UPLOADING, INPUT_MONEY, INPUT_NOTE, PREVIEW, WAITING_REPORT_DATE = range(5)

if not os.path.exists(IMAGE_DIR): os.makedirs(IMAGE_DIR)
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- WEB SERVER (CHO RENDER) ---
app_web = Flask(__name__)
@app_web.route('/')
def home(): return "BOT KETOAN V5.0 ACTIVE!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.cursor().execute('''CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER, image_path TEXT, amount REAL, note TEXT,
                    created_at DATE DEFAULT (date('now', 'localtime')))''')
    conn.commit()
    conn.close()

# --- UTILS ---
def parse_money(text):
    try:
        text = text.lower().replace('đ', '').replace('d', '').replace(' ', '').replace('.', '')
        if 'k' in text:
            return float(text.replace('k', '').replace(',', '.')) * 1000
        return float(text.replace(',', ''))
    except: return None

# --- GIAO DIỆN CHÍNH ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "🏢 **HỆ THỐNG QUẢN LÝ CHI TIÊU V5.0**\nVui lòng chọn một chức năng bên dưới:"
    btns = [
        [InlineKeyboardButton("📝 Gửi Hóa Đơn Mới", callback_data="start_bill")],
        [InlineKeyboardButton("📊 Báo Cáo Hình Ảnh", callback_data="menu_report")]
    ]
    if update.effective_user.id == ADMIN_ID:
        btns.append([InlineKeyboardButton("📂 Xuất Excel (Admin)", callback_data="admin_excel")])
        btns.append([InlineKeyboardButton("🗑️ Reset Dữ Liệu", callback_data="admin_reset")])
    
    markup = InlineKeyboardMarkup(btns)
    if update.callback_query: 
        try: await update.callback_query.message.edit_text(msg, reply_markup=markup, parse_mode='Markdown')
        except: await update.callback_query.message.reply_text(msg, reply_markup=markup, parse_mode='Markdown')
    else: 
        await update.message.reply_text(msg, reply_markup=markup, parse_mode='Markdown')
    return ConversationHandler.END

# --- LUỒNG GỬI BILL ---
async def start_bill_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data['photos'] = []
    await update.callback_query.message.reply_text("📸 **BƯỚC 1:** Bạn hãy gửi ảnh hóa đơn.\n(Gửi xong bấm nút bên dưới)", 
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Tiếp tục", callback_data="photo_done")]]))
    return UPLOADING

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.photo[-1].get_file()
    path = os.path.join(IMAGE_DIR, f"{uuid.uuid4()}.jpg")
    await file.download_to_drive(path)
    context.user_data['photos'].append(path)
    context.user_data['last_file_id'] = update.message.photo[-1].file_id
    return UPLOADING

async def photo_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    if not context.user_data.get('photos'):
        await update.callback_query.message.reply_text("⚠️ Bạn chưa gửi ảnh nào!")
        return UPLOADING
    await update.callback_query.message.reply_text("💰 **BƯỚC 2:** Nhập số tiền (VD: 150k, 1.200.000...):")
    return INPUT_MONEY

async def handle_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    money = parse_money(update.message.text)
    if money is None:
        await update.message.reply_text("⚠️ Số tiền không đúng, hãy nhập lại (VD: 50k):")
        return INPUT_MONEY
    context.user_data['amount'] = money
    await update.message.reply_text(f"✅ Đã nhận: `{'{:,.0f}'.format(money)}đ`\n📝 **BƯỚC 3:** Nhập nội dung chi tiêu:", parse_mode='Markdown')
    return INPUT_NOTE

async def handle_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['note'] = update.message.text
    msg = (f"🔍 **XÁC NHẬN LƯU ĐƠN HÀNG**\n"
           f"💵 Số tiền: `{'{:,.0f}'.format(context.user_data['amount'])}đ`\n"
           f"📝 Nội dung: {context.user_data['note']}\n\n"
           f"Bạn có đồng ý lưu vào hệ thống không?")
    btns = [[InlineKeyboardButton("✅ CHẤP NHẬN", callback_data="save_all"),
             InlineKeyboardButton("❌ HỦY BỎ", callback_data="cancel_all")]]
    await update.message.reply_photo(photo=context.user_data['last_file_id'], caption=msg, 
                                   reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')
    return PREVIEW

async def finalize_bill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "save_all":
        conn = sqlite3.connect(DB_NAME)
        conn.cursor().execute("INSERT INTO records (user_id, image_path, amount, note) VALUES (?, ?, ?, ?)",
                  (query.from_user.id, context.user_data['photos'][0], context.user_data['amount'], context.user_data['note']))
        conn.commit()
        conn.close()
        await query.message.edit_caption("🚀 **LƯU THÀNH CÔNG!**", parse_mode='Markdown')
    else:
        await query.message.edit_caption("🚫 **ĐÃ HỦY THAO TÁC.**")
    context.user_data.clear()
    return await start(update, context)

# --- BÁO CÁO HÌNH ẢNH THEO NGÀY ---
async def menu_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    btns = [
        [InlineKeyboardButton("📅 Hôm nay", callback_data="rep_today")],
        [InlineKeyboardButton("🗓️ Chọn ngày khác", callback_data="rep_pick_date")],
        [InlineKeyboardButton("⬅️ Quay lại", callback_data="back_to_start")]
    ]
    await query.message.edit_text("📊 **BÁO CÁO HÌNH ẢNH**\nBạn muốn xem dữ liệu khi nào?", 
                                reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

async def ask_report_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("📅 **Nhập ngày bạn muốn xem**\nĐịnh dạng: `ngày/tháng/năm` (VD: 27/01/2026)")
    return WAITING_REPORT_DATE

async def process_report(update: Update, context: ContextTypes.DEFAULT_TYPE, date_str=None):
    if not date_str:
        try:
            date_input = update.message.text
            date_str = datetime.strptime(date_input, '%d/%m/%Y').strftime('%Y-%m-%d')
            display_date = date_input
        except:
            await update.message.reply_text("❌ Sai định dạng! Hãy nhập lại (VD: 25/01/2026):")
            return WAITING_REPORT_DATE
    else:
        display_date = "Hôm nay"

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, amount, note, image_path FROM records WHERE created_at = ?", (date_str,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        await (update.callback_query.message if update.callback_query else update.message).reply_text(f"📅 Ngày {display_date} không có dữ liệu nào.")
        return await start(update, context)

    total = sum(row[1] for row in rows)
    head = f"📊 **DỮ LIỆU CHI TIÊU {display_date}**\n💰 Tổng cộng: `{'{:,.0f}'.format(total)}đ`"
    
    target = update.callback_query.message if update.callback_query else update.message
    await target.reply_text(head, parse_mode='Markdown')

    for row in rows:
        caption = f"🆔 ID: `{row[0]}`\n💸 Tiền: `{'{:,.0f}'.format(row[1])}đ`\n📝 Nội dung: {row[2]}"
        try: await target.reply_photo(photo=open(row[3], 'rb'), caption=caption, parse_mode='Markdown')
        except: pass
    
    return await start(update, context)

# --- ADMIN FUNCTIONS ---
async def export_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        s_date = datetime.strptime(context.args[0], '%d/%m/%Y').strftime('%Y-%m-%d')
        e_date = datetime.strptime(context.args[1], '%d/%m/%Y').strftime('%Y-%m-%d')
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql_query(f"SELECT * FROM records WHERE created_at BETWEEN '{s_date}' AND '{e_date}'", conn)
        conn.close()
        fname = f"Bao_cao_{s_date}.xlsx"
        df.to_excel(fname, index=False)
        await update.message.reply_document(open(fname, 'rb'), caption=f"📊 Báo cáo Excel {context.args[0]} - {context.args[1]}")
        os.remove(fname)
    except: await update.message.reply_text("⚠️ Cú pháp: `/xuat 01/01/2026 31/01/2026`")

async def reset_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    query = update.callback_query
    await query.answer()
    conn = sqlite3.connect(DB_NAME)
    conn.cursor().execute("DELETE FROM records")
    conn.commit()
    conn.close()
    await query.message.reply_text("🗑️ Hệ thống đã được xóa sạch dữ liệu!")
    return await start(update, context)

# --- MAIN ---
def main():
    init_db()
    threading.Thread(target=run_flask).start()
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_bill_flow, pattern="^start_bill$"),
            CallbackQueryHandler(ask_report_date, pattern="^rep_pick_date$")
        ],
        states={
            UPLOADING: [MessageHandler(filters.PHOTO, handle_photo), CallbackQueryHandler(photo_done, pattern="^photo_done$")],
            INPUT_MONEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_money)],
            INPUT_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_note)],
            PREVIEW: [CallbackQueryHandler(finalize_bill, pattern="^(save_all|cancel_all)$")],
            WAITING_REPORT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_report)]
        },
        fallbacks=[CallbackQueryHandler(start, pattern="^cancel_all$"), CommandHandler("start", start)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("xuat", export_excel))
    app.add_handler(CommandHandler("lay_id", lambda u,c: u.message.reply_text(f"ID: {u.effective_user.id}")))
    app.add_handler(CallbackQueryHandler(menu_report, pattern="^menu_report$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: process_report(u,c,datetime.now().strftime('%Y-%m-%d')), pattern="^rep_today$"))
    app.add_handler(CallbackQueryHandler(start, pattern="^back_to_start$"))
    app.add_handler(CallbackQueryHandler(reset_data, pattern="^admin_reset$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: u.callback_query.message.reply_text("Nhập: `/xuat ngày/tháng/năm ngày/tháng/năm`"), pattern="^admin_excel$"))
    app.add_handler(conv)

    app.run_polling()

if __name__ == '__main__': main()
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
