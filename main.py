#!/usr/bin/env python3
# main.py - N6 .meta bot (لا للإحتيكار)
# يتطلب: python-telegram-bot==20.6
#Telegram : @O000000000000o_X_o000000000000O 

import io
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ------------ إعداد ------------
TOKEN = "YOUR_BOT_TOKEN_HEREU"
MAX_FILE_SIZE = 30 * 1024 * 1024

SESSIONS: Dict[int, Dict[str, Any]] = {}

MAP_OPTION_BUTTONS = [
    ("Nexterra", bytes([0x88, 0x01, 0x16])),
    ("Bermuda", bytes([0x88, 0x01, 0x01])),
    ("100x100", bytes([0x88, 0x01, 0x0A])),
    ("50x50", bytes([0x88, 0x01, 0x19])),
    ("NOLAND", bytes([0x88, 0x01, 0x20])),
]
MAP_CODES = {code: name for name, code in MAP_OPTION_BUTTONS}

# ------------ دوال مساعدة تحليل النص والباينري ------------
def safe_decode_text(b: bytes) -> str:
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return b.decode(enc, errors="ignore")
        except Exception:
            continue
    return ""

def find_map_name(data_text: str) -> Optional[str]:
    m = re.search(r"(MAP_[A-Za-z0-9_\-\.]{3,200})", data_text, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    m2 = re.search(r"\b([A-Za-z0-9_\-]{6,80}(_Cs_|_cs_|Assault|Dust2|de_|map_)[A-Za-z0-9_\-]{0,80})\b", data_text, flags=re.IGNORECASE)
    if m2:
        return m2.group(1)
    return None

def find_description_keep_colors(data_text: str) -> str:
    candidates = re.findall(r"[^\r\n]{30,1000}", data_text)
    best = None
    for cand in candidates:
        cleaned = re.sub(r"\s+", " ", cand).strip()
        if re.search(r"GR_[0-9a-fA-F\-]+", cleaned) and len(cleaned) < 60:
            continue
        if len(cleaned) >= 30:
            best = cleaned
            break
    if best:
        best = re.sub(r"[^\x20-\x7E\u0600-\u06FF\[\]A-Fa-f0-9\.\,\!\?\:\ \" \-\_\/\(\)]", " ", best)
        best = re.sub(r"\s+", " ", best).strip()
        return best
    return "غير متوفر"

def extract_color_codes(text: str) -> List[str]:
    codes = re.findall(r"\[([0-9A-Fa-f]{2,6})\]", text)
    seen = []
    for c in codes:
        if c not in seen:
            seen.append(c)
    return seen

def find_player_name(data_text: str, uid_exists: bool) -> Optional[str]:
    m = re.search(r"@[\w\-\_]{3,32}", data_text)
    if m:
        uname = m.group(0)
        if len(uname.strip("@")) >= 5 and uid_exists:
            return uname
        else:
            return None
    m2 = re.search(r"(?:author|creator|playername|nickname)[:=]\s*([A-Za-z0-9\-_ ]{3,40})", data_text, flags=re.IGNORECASE)
    if m2:
        name = m2.group(1).strip()
        if len(name) >= 5 and uid_exists:
            return name
    return None

def find_uid_textual(data_text: str, data_bytes: bytes) -> Optional[str]:
    m = re.search(r"\b(\d{8,11})\b", data_text)
    if m:
        return m.group(1)
    for i in range(0, len(data_bytes) - 8):
        v8 = int.from_bytes(data_bytes[i:i+8], byteorder= little , signed=False)
        if 10_000_000 <= v8 <= 99_999_999_999:
            return str(v8)
    for i in range(0, len(data_bytes) - 4):
        v4 = int.from_bytes(data_bytes[i:i+4], byteorder= little , signed=False)
        if 10_000_000 <= v4 <= 99_999_999_999:
            return str(v4)
    return None

def find_first_map_code(data_bytes: bytes) -> Optional[bytes]:
    for code_bytes in MAP_CODES.keys():
        idx = data_bytes.find(code_bytes)
        if idx != -1:
            return code_bytes
    return None

def find_all_timestamps(data_bytes: bytes, limit: int = 12) -> List[Tuple[int, str, int]]:
    res = []
    for i in range(0, len(data_bytes) - 4):
        val = int.from_bytes(data_bytes[i:i+4], byteorder= little , signed=False)
        try:
            dt = datetime.fromtimestamp(val, datetime.UTC)
            if 2000 < dt.year < 2036:
                res.append((i, dt.strftime("%Y-%m-%d %H:%M"), val))
        except Exception:
            continue
        if len(res) >= limit:
            break
    return res

def analyze_meta_bytes(data_bytes: bytes, filename: str) -> Dict[str, Any]:
    text = safe_decode_text(data_bytes)
    size = len(data_bytes)
    map_name = find_map_name(text) or "غير معروف"
    description = find_description_keep_colors(text)
    color_codes = extract_color_codes(description)
    uid_text = find_uid_textual(text, data_bytes)
    uid_display = uid_text if uid_text and 8 <= len(uid_text) <= 11 else None
    owner = find_player_name(text, uid_exists=bool(uid_display))
    if not owner:
        owner = "غير متوفر"
    found_code = find_first_map_code(data_bytes)
    found_code_name = MAP_CODES.get(found_code, "غير معروف") if found_code else "لم يُكشف"
    timestamps = find_all_timestamps(data_bytes)
    last_ts = timestamps[-1][1] if timestamps else "غير محدد"
    return {
        "filename": filename,
        "map_name": map_name,
        "player_name": owner,
        "uid": uid_display,
        "map_code": found_code,
        "map_code_name": found_code_name,
        "description": description,
        "color_codes": color_codes,
        "timestamps": timestamps,
        "last_ts": last_ts,
        "size": size,
    }

def modify_map_code_in_bytes(data: bytes, old_code: bytes, new_code: bytes) -> bytes:
    return data.replace(old_code, new_code)

# ------------ القائمة الرئيسية ------------
def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("عرض المعلومات 📝", callback_data="show_info")],
        [InlineKeyboardButton("تغيير الخريطة 🔁", callback_data="change_map")]
    ])

# ------------ Handlers تيليجرام ------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "مرحبًا. أرسل ملف بصيغة .meta 📦"
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user_id = msg.from_user.id
    doc = msg.document
    if not doc:
        await msg.reply_text("أرسل ملفًا كـ Document.")
        return
    if not doc.file_name.lower().endswith(".meta"):
        await msg.reply_text("الرجاء إرسال ملف بلاحقة .meta فقط.")
        return
    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await msg.reply_text("حجم الملف أكبر من الحد المسموح.")
        return

    await msg.reply_text("جارٍ تنزيل الملف وتحليله...")
    file = await context.bot.get_file(doc.file_id)
    bio = io.BytesIO()
    await file.download_to_memory(out=bio)
    data_bytes = bio.getvalue()

    info = analyze_meta_bytes(data_bytes, doc.file_name)
    SESSIONS[user_id] = {"file_bytes": data_bytes, "info": info}

    await msg.reply_text(
        f"تم تحليل الملف: {doc.file_name}\nخريطة متوقعة: {info[ map_name ]}\nكود مكتشف: {info[ map_code_name ]}",
        reply_markup=main_menu_kb()
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    session = SESSIONS.get(user_id)
    if not session:
        await query.message.reply_text("لم يتم العثور على ملف سابق. أرسل ملف .meta أولًا.")
        return
    info = session["info"]

    # --- عرض المعلومات ---
    if query.data == "show_info":
        uid_field = f"UID = {info[ uid ]}" if info.get("uid") else "غير موجود"
        ts_list = info.get("timestamps", [])
        ts_lines = "\n".join([f"- offset {pos}: {date_str}" for pos, date_str, _ in ts_list]) if ts_list else "لا تواريخ محتملة."
        colors_text = ", ".join(info.get("color_codes", [])) or "لا توجد ألوان داخل الوصف."
        msg_text = (
            f"📄 اسم ملف: {info[ filename ]}\n"
            f"🏝 اسم خريطه: {info[ map_name ]}\n"
            f"👤 صاحب الخريطه: {info[ player_name ]}\n"
            f"🆔 {uid_field}\n"
            f"🌍 نوع خريطه: {info[ map_code_name ]}\n"
            f"📝 وصف خريطه:\n{info[ description ]}\n\n"
            f"🎨 أكواد اللون الموجودة: {colors_text}\n\n"
            f"🕒 تواريخ محتملة:\n{ts_lines}\n\n"
            f"🕓 آخر تعديل (محتمَل): {info[ last_ts ]}\n"
            f"📦 حجم الملف: {info[ size ]} بايت"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]])
        await query.edit_message_text(msg_text, reply_markup=kb)
        return

    # --- تغيير الخريطة ---
    if query.data == "change_map":
        rows = [[InlineKeyboardButton(label, callback_data=f"setmap|{label}")] for label, _ in MAP_OPTION_BUTTONS]
        rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="back")])
        await query.edit_message_text("اختر الخريطة التي تريد الاستبدال بها:", reply_markup=InlineKeyboardMarkup(rows))
        return

    if query.data.startswith("setmap|"):
        _, chosen_label = query.data.split("|", 1)
        chosen_code = next((c for l, c in MAP_OPTION_BUTTONS if l == chosen_label), None)
        if not chosen_code:
            await query.message.reply_text("خيار غير معروف.")
            return
        old_code = info.get("map_code")
        if not old_code:
            await query.message.reply_text("لم يتم العثور على كود خريطة أصلي في الملف.")
            return
        if old_code == chosen_code:
            await query.message.reply_text("الكود الحالي مطابق للاختيار. لا تغيير مطلوب.")
            return
        modified_bytes = modify_map_code_in_bytes(session["file_bytes"], old_code, chosen_code)
        session["modified_bytes"] = modified_bytes
        send_name = f"N6_{info[ filename ]}"
        bio = io.BytesIO(modified_bytes)
        bio.name = send_name
        bio.seek(0)
        await query.edit_message_text(f"✅ تم استبدال الكود إلى {chosen_label}. جاري إرسال الملف المعدّل...")
        await context.bot.send_document(chat_id=user_id, document=bio, filename=send_name)
        return

    # --- زر رجوع للقائمة الرئيسية ---
    if query.data == "back":
        await query.edit_message_text("اختر أحد الخيارات:", reply_markup=main_menu_kb())
        return

    await query.message.reply_text("خيار غير معروف.")

async def unknown_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أرسل ملف .meta أو استخدم /start.")

# ------------ تشغيل البوت ------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL & (~filters.COMMAND), handle_document))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_cmd))
    print("Bot started.")
    app.run_polling()

if __name__ == "__main__":
    main()

#غير مهم:
#YT : @0o________________________o0me
