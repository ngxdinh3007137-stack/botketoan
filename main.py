import logging, sqlite3, os, uuid, threading, pandas as pd
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
from flask import Flask

# --- CẤU HÌNH ---
TOKEN = '8374954088:AAEGsRqgysifY4gOh0df5IUz74r29T5ggW0'
ADMIN_ID = 7108698925  # Thay ID của bạn
DB_NAME, IMG_DIR = 'data_v7.db', 'bills'
S_PHOTO, S_MONEY, S_NOTE, S_CONFIRM, S_REP_S, S_REP_E = range(6)

if not os.path.exists(IMG_DIR): os.makedirs(IMG_DIR)
logging.basicConfig(level=logging.INFO)

# --- DATABASE ---
def db_query(sql, params=(), fetch=False):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.execute(sql, params)
        return cur.fetchall() if fetch else conn.commit()

# --- WEB SERVER (RENDER) ---
app = Flask('')
@app.route('/')
def home(): return "Bot Online!"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# --- LOGIC XỬ LÝ ---
def fmt_money(n): return "{:,.0f}đ".format(n)

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("📝 Gửi Bill", callback_data="add"), InlineKeyboardButton("📊 Báo Cáo", callback_data="rep")]]
    if u.effective_user.id == ADMIN_ID:
        kb.append([InlineKeyboardButton("📂 Excel", callback_data="xls"), InlineKeyboardButton("🗑 Reset", callback_data="rst")])
    msg = "🏢 **QUẢN LÝ THU CHI V7**"
    if u.callback_query: await u.callback_query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    else: await u.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return ConversationHandler.END

# --- LUỒNG GỬI BILL ---
async def start_add(u: Update, c: ContextTypes.DEFAULT_TYPE):
    c.user_data['pics'] = []
    await u.callback_query.message.reply_text("📸 Gửi ảnh bill (xong bấm Tiếp tục):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Tiếp tục", callback_data="done"), InlineKeyboardButton("❌ Hủy", callback_data="off")]]))
    return S_PHOTO

async def get_photo(u: Update, c: ContextTypes.DEFAULT_TYPE):
    path = f"{IMG_DIR}/{uuid.uuid4()}.jpg"
    await (await u.message.photo[-1].get_file()).download_to_drive(path)
    c.user_data['pics'].append(path)
    return S_PHOTO

async def get_money(u: Update, c: ContextTypes.DEFAULT_TYPE):
    try:
        txt = u.message.text.lower().replace('k','000').replace('.','').replace(',','').replace('đ','')
        c.user_data['amt'] = float(txt)
        await u.message.reply_text(f"💰 Số tiền: {fmt_money(c.user_data['amt'])}\n📝 Nhập nội dung:")
        return S_NOTE
    except:
        await u.message.reply_text("❌ Nhập số tiền hợp lệ (VD: 100k):")
        return S_MONEY

async def confirm_bill(u: Update, c: ContextTypes.DEFAULT_TYPE):
    c.user_data['note'] = u.message.text
    cap = f"🔍 **XÁC NHẬN**\n💵: {fmt_money(c.user_data['amt'])}\n📝: {c.user_data['note']}"
    kb = [[InlineKeyboardButton("✅ Lưu", callback_data="save"), InlineKeyboardButton("❌ Hủy", callback_data="off")]]
    await u.message.reply_photo(open(c.user_data['pics'][0], 'rb'), caption=cap, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return S_CONFIRM

async def save_bill(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if q.data == "save":
        db_query("INSERT INTO records (user_id, image_paths, amount, note) VALUES (?,?,?,?)", 
                 (q.from_user.id, ",".join(c.user_data['pics']), c.user_data['amt'], c.user_data['note']))
        await q.message.edit_caption("✅ Đã lưu!")
    else: await q.message.edit_caption("🚫 Đã hủy.")
    return await start(u, c)

# --- BÁO CÁO KHOẢNG NGÀY ---
async def rep_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.message.reply_text("📅 Từ ngày (ngày/tháng/năm):")
    return S_REP_S

async def rep_end(u: Update, c: ContextTypes.DEFAULT_TYPE):
    try:
        c.user_data['s'] = datetime.strptime(u.message.text, '%d/%m/%Y').strftime('%Y-%m-%d')
        await u.message.reply_text("📅 Đến ngày (ngày/tháng/năm):")
        return S_REP_E
    except: return S_REP_S

async def run_rep(u: Update, c: ContextTypes.DEFAULT_TYPE):
    try:
        e = datetime.strptime(u.message.text, '%d/%m/%Y').strftime('%Y-%m-%d')
        rows = db_query("SELECT id, amount, note, image_paths, created_at FROM records WHERE created_at BETWEEN ? AND ?", (c.user_data['s'], e), True)
        if not rows: await u.message.reply_text("❌ Không có dữ liệu."); return await start(u, c)
        
        await u.message.reply_text(f"📊 Tổng chi: {fmt_money(sum(r[1] for r in rows))}")
        for r in rows:
            txt = f"🆔 {r[0]} | 📅 {r[4]}\n💸 {fmt_money(r[1])}\n📝 {r[2]}"
            imgs = r[3].split(",")
            media = [InputMediaPhoto(open(i, 'rb'), caption=txt if idx==0 else "") for idx, i in enumerate(imgs)]
            await u.message.reply_media_group(media)
        return await start(u, c)
    except: return await start(u, c)

# --- MAIN ---
def main():
    db_query("CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY, user_id INTEGER, image_paths TEXT, amount REAL, note TEXT, created_at DATE DEFAULT (date('now','localtime')))")
    threading.Thread(target=run).start()
    bot = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add, "^add$"), CallbackQueryHandler(rep_start, "^rep$")],
        states={
            S_PHOTO: [MessageHandler(filters.PHOTO, get_photo), CallbackQueryHandler(lambda u,c: u.message.reply_text("💰 Nhập tiền:") or S_MONEY, "^done$")],
            S_MONEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_money)],
            S_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_bill)],
            S_CONFIRM: [CallbackQueryHandler(save_all, "^save|off$")],
            S_REP_S: [MessageHandler(filters.TEXT & ~filters.COMMAND, rep_end)],
            S_REP_E: [MessageHandler(filters.TEXT & ~filters.COMMAND, run_rep)],
        },
        fallbacks=[CallbackQueryHandler(start, "^off$"), CommandHandler("start", start)]
    )

    bot.add_handler(conv)
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CommandHandler("lay_id", lambda u,c: u.message.reply_text(u.effective_user.id)))
    bot.run_polling()

if __name__ == '__main__': main()
