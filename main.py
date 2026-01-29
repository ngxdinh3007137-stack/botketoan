import logging, os, uuid, threading, pandas as pd, zipfile, cloudinary, cloudinary.uploader
import psycopg2
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
from flask import Flask

# ================= CONFIG (Sếp điền ở đây) =================
TOKEN = '8374954088:AAEGsRqgysifY4gOh0df5IUz74r29T5ggW0'
SEP_ID =  7108698925          # ID của Sếp
QUAN_LY_IDS = []     # ID các Quản lý [123, 456]
# Link SQL (Lấy từ Supabase hoặc ElephantSQL)
DATABASE_URL = 'postgres://user:pass@host:5432/dbname'
# Cloudinary (Lấy tại cloudinary.com - Miễn phí) để tạo link ảnh
cloudinary.config(cloud_name='xxx', api_key='xxx', api_secret='xxx')
# ==========================================================

S_PHOTO, S_MONEY, S_NOTE, S_PREVIEW, S_REP_S, S_REP_E = range(6)
IMG_DIR = 'temp_img'
if not os.path.exists(IMG_DIR): os.makedirs(IMG_DIR)
logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)

# --- KẾT NỐI SQL SERVER ---
def db_q(sql, p=(), fetch=False):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cur = conn.cursor()
    cur.execute(sql, p)
    if fetch:
        res = cur.fetchall()
        cur.close(); conn.close()
        return res
    conn.commit()
    cur.close(); conn.close()

# Khởi tạo bảng SQL
db_q("""CREATE TABLE IF NOT EXISTS records (
    id SERIAL PRIMARY KEY, user_id BIGINT, user_name TEXT, 
    image_urls TEXT, amount DECIMAL, note TEXT, created_at DATE DEFAULT CURRENT_DATE)""")

app = Flask('')
@app.route('/')
def home(): return "SQL Server Active"
def run_web(): app.run(host='0.0.0.0', port=8080)

def is_admin(u_id): return u_id == SEP_ID or u_id in QUAN_LY_IDS

# --- GIAO DIỆN CHÍNH ---
async def setup_menu(app: Application):
    await app.bot.set_my_commands([BotCommand("start","Menu"), BotCommand("gui","Gửi Bill"), BotCommand("baocao","Báo Cáo")])

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("📝 Gửi Hóa Đơn", callback_data="go_gui")],
          [InlineKeyboardButton("📊 Báo Cáo Khoảng Ngày", callback_data="go_rep")]]
    if u.effective_user.id == SEP_ID:
        kb.append([InlineKeyboardButton("🗑 Xóa sạch dữ liệu (Sếp)", callback_data="go_rst")])
    msg = "🏢 **HỆ THỐNG KẾ TOÁN ENTERPRISE**\nChào Sếp và Quản lý."
    target = u.callback_query.message if u.callback_query else u.message
    await target.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return ConversationHandler.END

# --- LUỒNG GỬI BILL ---
async def cmd_gui(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.callback_query: await u.callback_query.answer()
    c.user_data['pics'] = []
    kb = [[InlineKeyboardButton("❌ Hủy", callback_data="cancel"), InlineKeyboardButton("➡️ Tiếp tục", callback_data="p_done")]]
    await (u.callback_query.message if u.callback_query else u.message).reply_text("📸 **Gửi ảnh Bill:**", reply_markup=InlineKeyboardMarkup(kb))
    return S_PHOTO

async def h_photo(u: Update, c: ContextTypes.DEFAULT_TYPE):
    f = await u.message.photo[-1].get_file()
    p = f"{IMG_DIR}/{uuid.uuid4()}.jpg"
    await f.download_to_drive(p)
    c.user_data['pics'].append(p)
    return S_PHOTO

async def p_done(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not c.user_data.get('pics'): return S_PHOTO
    await u.callback_query.message.reply_text("💰 **Số tiền (VD: 500k):**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel")]]))
    return S_MONEY

async def h_money(u: Update, c: ContextTypes.DEFAULT_TYPE):
    t = u.message.text.lower().replace('k','000').replace('.','').replace(',','').strip()
    if not t.isdigit(): return S_MONEY
    c.user_data['amt'] = float(t)
    await u.message.reply_text("📝 **Ghi chú:**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Hủy", callback_data="cancel")]]))
    return S_NOTE

async def h_note(u: Update, c: ContextTypes.DEFAULT_TYPE):
    c.user_data['note'] = u.message.text
    media = [InputMediaPhoto(open(p, 'rb')) for p in c.user_data['pics']]
    await u.message.reply_media_group(media=media)
    cap = f"🔍 **XÁC NHẬN:**\n💰 Tiền: `{c.user_data['amt']:,}đ`\n📝 Nội dung: {c.user_data['note']}"
    kb = [[InlineKeyboardButton("❌ HỦY", callback_data="cancel"), InlineKeyboardButton("✅ LƯU LẠI", callback_data="save")]]
    await u.message.reply_text(cap, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return S_PREVIEW

async def h_save(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    await q.answer(); await q.message.edit_text("⏳ Đang tải ảnh lên SQL Server...")
    
    links = []
    for p in c.user_data['pics']:
        res = cloudinary.uploader.upload(p)
        links.append(res['secure_url'])
        os.remove(p) # Xóa ảnh tạm

    db_q("INSERT INTO records (user_id, user_name, image_urls, amount, note) VALUES (%s, %s, %s, %s, %s)", 
         (q.from_user.id, q.from_user.full_name, ",".join(links), c.user_data['amt'], c.user_data['note']))
    
    if SEP_ID != 0:
        await c.bot.send_message(SEP_ID, f"🔔 **Bill mới từ {q.from_user.full_name}:**\n💸 `{c.user_data['amt']:,}đ` - {c.user_data['note']}\n🔗 [Xem ảnh]({links[0]})", parse_mode='Markdown')
    
    await q.message.reply_text("🚀 **ĐÃ LƯU VÀO SQL SERVER THÀNH CÔNG!**")
    return await start(u, c)

# --- BÁO CÁO SQL ---
async def cmd_rep(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await (u.callback_query.message if u.callback_query else u.message).reply_text("📅 **Từ ngày** (dd/mm/yyyy):")
    return S_REP_S

async def h_rep_s(u: Update, c: ContextTypes.DEFAULT_TYPE):
    try:
        c.user_data['start'] = datetime.strptime(u.message.text, '%d/%m/%Y').strftime('%Y-%m-%d')
        await u.message.reply_text("➡️ **Đến ngày** (dd/mm/yyyy):")
        return S_REP_E
    except: return S_REP_S

async def h_rep_e(u: Update, c: ContextTypes.DEFAULT_TYPE):
    try:
        end = datetime.strptime(u.message.text, '%d/%m/%Y').strftime('%Y-%m-%d')
        rows = db_q("SELECT id, amount, note, image_urls, created_at, user_name FROM records WHERE created_at BETWEEN %s AND %s", (c.user_data['start'], end), True)
        if not rows: await u.message.reply_text("📭 Trống."); return await start(u, c)
        
        await u.message.reply_text(f"📊 **TỔNG CHI:** `{sum(r[1] for r in rows):,}đ`", parse_mode='Markdown')
        if is_admin(u.effective_user.id):
            kb = [[InlineKeyboardButton("📂 Xuất Excel (Có Link Ảnh)", callback_data=f"xls_{c.user_data['start']}_{end}")]]
            await u.message.reply_text("Tiện ích Sếp/Quản lý:", reply_markup=InlineKeyboardMarkup(kb))
        return await start(u, c)
    except: return await start(u, c)

async def export_xls(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    _, s, e = q.data.split("_")
    rows = db_q("SELECT id, created_at, user_name, amount, note, image_urls FROM records WHERE created_at BETWEEN %s AND %s", (s, e), True)
    
    fn = f"Bao_Cao_{s}_{e}.xlsx"
    df = pd.DataFrame(rows, columns=['ID','Ngày','Nhân viên','Số tiền','Ghi chú','Link Ảnh'])
    
    # Tạo Excel có link click được
    writer = pd.ExcelWriter(fn, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Data')
    writer.close()
    
    await q.message.reply_document(open(fn, 'rb'), caption=f"📊 Báo cáo từ {s} đến {e}\n(Mở Excel, click vào Link Ảnh để xem trực tiếp)")
    os.remove(fn)

async def cancel(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.callback_query: await u.callback_query.answer()
    await (u.callback_query.message if u.callback_query else u.message).reply_text("🚫 Hủy.")
    return await start(u, c)

def main():
    threading.Thread(target=run_web).start()
    bot = Application.builder().token(TOKEN).post_init(setup_menu).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler("gui", cmd_gui), CommandHandler("baocao", cmd_rep), CallbackQueryHandler(cmd_gui, "^go_gui$"), CallbackQueryHandler(cmd_rep, "^go_rep$")],
        states={
            S_PHOTO: [MessageHandler(filters.PHOTO, h_photo), CallbackQueryHandler(p_done, "^p_done$")],
            S_MONEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, h_money)],
            S_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, h_note)],
            S_PREVIEW: [CallbackQueryHandler(h_save, "^save$")],
            S_REP_S: [MessageHandler(filters.TEXT & ~filters.COMMAND, h_rep_s)],
            S_REP_E: [MessageHandler(filters.TEXT & ~filters.COMMAND, h_rep_e)],
        },
        fallbacks=[CallbackQueryHandler(cancel, "^cancel$"), CommandHandler("start", start)]
    )
    bot.add_handler(conv); bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CommandHandler("id", lambda u,c: u.message.reply_text(f"ID: `{u.effective_user.id}`", parse_mode='Markdown')))
    bot.add_handler(CallbackQueryHandler(export_xls, "^xls_"))
    bot.add_handler(CallbackQueryHandler(lambda u,c: db_q("DELETE FROM records") or u.callback_query.message.reply_text("🗑 Reset xong!"), "^go_rst$"))
    bot.run_polling()

if __name__ == '__main__': main()
