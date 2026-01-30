import logging, os, uuid, threading, pandas as pd, cloudinary, cloudinary.uploader, psycopg2
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
from telegram.request import HTTPXRequest
from flask import Flask

# ================= CONFIG =================
TOKEN = '7904820608:AAGAo1QOjzBGOEYr0irpr5_DdMfcDMJi5Ho'
SEP_ID = 7108698925           
DATABASE_URL = "postgresql://postgres.xlcvbctcdlrqjzolamig:MINHDANG010220009@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require"
cloudinary.config(cloudinary_url="cloudinary://116873382629459:NCGEO@dje8bisnw")
# ==========================================

S_PHOTO, S_MONEY, S_NOTE, S_PREVIEW, S_REP_S, S_REP_E = range(6)
logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)

def db_q(sql, p=(), fetch=False):
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
        cur = conn.cursor(); cur.execute(sql, p)
        res = cur.fetchall() if fetch else None
        conn.commit(); cur.close(); conn.close()
        return res
    except Exception as e:
        logging.error(f"SQL Error: {e}"); return None

# Web server giữ live
app = Flask(''); 
@app.route('/')
def home(): return "Bot Live"
def run_web(): app.run(host='0.0.0.0', port=8080)

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    # Reset toàn bộ trạng thái khi bấm Start
    for k in ['pics', 'amt', 'note', 'start_d']: c.user_data.pop(k, None)
    kb = [[InlineKeyboardButton("📝 Gửi Bill (Nhiều ảnh)", callback_data="go_gui")],
          [InlineKeyboardButton("📊 Báo Cáo Chi Tiết", callback_data="go_rep")]]
    msg = "🏢 **QUẢN LÝ KẾ TOÁN**\n\nChọn chức năng bên dưới:"
    target = u.callback_query.message if u.callback_query else u.message
    await target.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return ConversationHandler.END

# --- LUỒNG GỬI BILL ---
async def cmd_gui(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.callback_query: await u.callback_query.answer()
    c.user_data['pics'] = []
    await (u.callback_query.message if u.callback_query else u.message).reply_text(
        "📸 **BƯỚC 1:** Sếp gửi ảnh hóa đơn vào đây.\n(Gửi từng cái hoặc gửi cả lứa cùng lúc đều được).\n\nSau khi gửi xong, hãy bấm nút **[Xong, tiếp tục]** bên dưới.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Xong, tiếp tục", callback_data="p_done")], [InlineKeyboardButton("❌ Hủy", callback_data="cancel")]])
    )
    return S_PHOTO

async def h_photo(u: Update, c: ContextTypes.DEFAULT_TYPE):
    # Lưu đường dẫn ảnh vào list, chưa upload vội để tránh lag
    f = await u.message.photo[-1].get_file()
    path = f"temp_{uuid.uuid4()}.jpg"
    await f.download_to_drive(path)
    if 'pics' not in c.user_data: c.user_data['pics'] = []
    c.user_data['pics'].append(path)
    return S_PHOTO

async def p_done(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not c.user_data.get('pics'):
        await u.callback_query.message.reply_text("⚠️ Sếp chưa gửi ảnh nào mà!")
        return S_PHOTO
    await u.callback_query.message.reply_text("💰 **BƯỚC 2:** Nhập số tiền (VD: 500k hoặc 500000):")
    return S_MONEY

async def h_money(u: Update, c: ContextTypes.DEFAULT_TYPE):
    txt = u.message.text.lower().replace('k','000').replace('.','').replace(',','').strip()
    if not txt.isdigit(): 
        await u.message.reply_text("⚠️ Số tiền không hợp lệ, mời Sếp nhập lại:")
        return S_MONEY
    c.user_data['amt'] = float(txt)
    await u.message.reply_text("📝 **BƯỚC 3:** Nhập ghi chú/nội dung chi:")
    return S_NOTE

async def h_note(u: Update, c: ContextTypes.DEFAULT_TYPE):
    c.user_data['note'] = u.message.text
    # Preview
    cap = f"🔍 **XÁC NHẬN LẠI:**\n💰 Số tiền: `{c.user_data['amt']:,}đ`\n📝 Nội dung: {c.user_data['note']}\n🖼 Số lượng ảnh: {len(c.user_data['pics'])}"
    await u.message.reply_text(cap, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ĐÚNG, LƯU NGAY", callback_data="save")],
        [InlineKeyboardButton("❌ SAI, HỦY LÀM LẠI", callback_data="cancel")]
    ]), parse_mode='Markdown')
    return S_PREVIEW

async def h_save(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); await q.message.edit_text("⏳ Đang xử lý ảnh & lưu dữ liệu...")
    
    links = []
    for p in c.user_data['pics']:
        try:
            res = cloudinary.uploader.upload(p)
            links.append(res['secure_url'])
            if os.path.exists(p): os.remove(p)
        except: pass

    all_links = " | ".join(links) # Dùng dấu gạch đứng để phân tách link ảnh
    db_q("INSERT INTO records (user_id, user_name, image_urls, amount, note) VALUES (%s, %s, %s, %s, %s)", 
         (q.from_user.id, q.from_user.full_name, all_links, c.user_data['amt'], c.user_data['note']))
    
    await q.message.reply_text("🚀 **LƯU THÀNH CÔNG!** Dữ liệu đã vào kho.")
    return await start(u, c)

# --- LUỒNG BÁO CÁO ---
async def cmd_rep(u: Update, c: ContextTypes.DEFAULT_TYPE):
    target = u.callback_query.message if u.callback_query else u.message
    await target.reply_text("📅 **BÁO CÁO:** Nhập ngày BẮT ĐẦU (dd/mm/yyyy):")
    return S_REP_S

async def h_rep_s(u: Update, c: ContextTypes.DEFAULT_TYPE):
    try:
        c.user_data['start_d'] = datetime.strptime(u.message.text, '%d/%m/%Y').strftime('%Y-%m-%d')
        await u.message.reply_text("➡️ Nhập ngày KẾT THÚC (dd/mm/yyyy):")
        return S_REP_E
    except:
        await u.message.reply_text("⚠️ Sai định dạng, vui lòng nhập lại (VD: 01/01/2026):")
        return S_REP_S

async def h_rep_e(u: Update, c: ContextTypes.DEFAULT_TYPE):
    try:
        end_d = datetime.strptime(u.message.text, '%d/%m/%Y').strftime('%Y-%m-%d')
        s_d = c.user_data['start_d']
        rows = db_q("SELECT id, amount, note, image_urls, created_at, user_name FROM records WHERE created_at BETWEEN %s AND %s ORDER BY created_at DESC", (s_d, end_d), True)
        
        if not rows:
            await u.message.reply_text("📭 Không có dữ liệu nào.")
            return await start(u, c)
        
        total = sum(r[1] for r in rows)
        report_msg = f"📊 **TỔNG KẾT TỪ {s_d} ĐẾN {end_d}**\n\n💰 Tổng chi: `{total:,}đ`"
        kb = [[InlineKeyboardButton("📂 TẢI FILE EXCEL CHI TIẾT", callback_data=f"xls_{s_d}_{end_d}")]]
        await u.message.reply_text(report_msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        return ConversationHandler.END
    except:
        return await start(u, c)

async def export_xls(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer(); _, s, e = q.data.split("_")
    rows = db_q("SELECT id, created_at, user_name, amount, note, image_urls FROM records WHERE created_at BETWEEN %s AND %s", (s, e), True)
    
    df = pd.DataFrame(rows, columns=['ID','Ngày','Nhân viên','Số tiền','Ghi chú','Tất cả link ảnh'])
    fn = f"Bao_cao_{s}_den_{e}.xlsx"
    df.to_excel(fn, index=False)
    
    await q.message.reply_document(open(fn, 'rb'), caption=f"📊 File báo cáo chi tiết.")
    os.remove(fn)

async def cancel(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.callback_query: await u.callback_query.answer()
    await (u.callback_query.message if u.callback_query else u.message).reply_text("🚫 Đã hủy.")
    return await start(u, c)

def main():
    threading.Thread(target=run_web, daemon=True).start()
    db_q("""CREATE TABLE IF NOT EXISTS records (id SERIAL PRIMARY KEY, user_id BIGINT, user_name TEXT, image_urls TEXT, amount DECIMAL, note TEXT, created_at DATE DEFAULT CURRENT_DATE)""")
    
    req = HTTPXRequest(connect_timeout=30, read_timeout=30)
    bot = Application.builder().token(TOKEN).request(req).build()
    
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
        fallbacks=[CommandHandler("start", start), CallbackQueryHandler(cancel, "^cancel$")]
    )
    
    bot.add_handler(conv)
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CallbackQueryHandler(export_xls, "^xls_"))
    bot.run_polling()

if __name__ == '__main__': main()
