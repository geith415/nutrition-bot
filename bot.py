import os
import json
import asyncio
from datetime import datetime, time
import google.generativeai as genai
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = "8583723084:AAEzZrFLNcaWvLQa91Md0a2NJBje1U6Jrm4"
GEMINI_KEY = "AQ.Ab8RN6I7VoKucHCMDHepg2k4RdQm6KtZiKnaPvbz2_2-0SCTLQ"
DATA_FILE = "user_data.json"

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-3.8-flash")

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_user_entry(user_id):
    data = load_data()
    uid = str(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    if uid not in data or data[uid].get("date") != today:
        data[uid] = {"date": today, "intake": 0, "burned": 0, "meals": []}
        save_data(data)
    return data, uid

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "أهلاً بك في بوت التغذية الذكي! 🥗\n\n"
        "1. أرسل لي صورة وجبتك مع وصف بسيط.\n"
        "2. استخدم الأمر /summary لمعرفة ملخص السعرات الحرارية لليوم.\n"
        "3. سأطلب منك التمارين/السعرات المحروقة يومياً عند الساعة 11:00 مساءً."
    )
    await update.message.reply_text(welcome_text)
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("جاري تحليل الوجبة بواسطة جيميناي... ⏳")
    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    caption = update.message.caption or "بدون وصف إضافي"
    prompt = (
        "حلل صورة الطعام هذه بناءً على الوصف التالي إذا وجد: " + caption + "\n"
        "اعطني الإجابة باللغة العربية بدقة وتنسيق واضحيين متبعاً ما يلي:\n"
        "1. اسم الوجبة وتفاصيلها.\n"
        "2. تقدير السعرات الحرارية الإجمالية برقم محدد.\n"
        "3. توزيع الماكروز (بروتين، كربوهيدرات، دهون).\n"
        "في السطر الأخير تماماً أكتب فقط: [CALORIES: X] حيث X هو رقم السعرات الحرارية فقط بدون أي نص إضافي."
    )
    try:
        response = model.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": bytes(photo_bytes)}
        ])
        text_response = response.text
        calories = 0
        if "[CALORIES:" in text_response:
            try:
                cal_part = text_response.split("[CALORIES:")[1].split("]")[0].strip()
                calories = int(cal_part)
                clean_text = text_response.split("[CALORIES:")[0].strip()
            except Exception:
                clean_text = text_response
        else:
            clean_text = text_response
        
        data, uid = get_user_entry(update.effective_user.id)
        data[uid]["intake"] += calories
        data[uid]["meals"].append({"caption": caption, "calories": calories})
        save_data(data)
        await update.message.reply_text(clean_text)
    except Exception as e:
        await update.message.reply_text(f"حدث خطأ أثناء تحليل الصورة: {e}")

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data, uid = get_user_entry(update.effective_user.id)
    user_data = data[uid]
    net = user_data["intake"] - user_data["burned"]
    msg = (
        f"📊 ملخص اليوم ({user_data['date']}):\n\n"
        f"📥 السعرات المأكولة: {user_data['intake']} د.ح\n"
        f"🔥 السعرات المحروقة: {user_data['burned']} د.ح\n"
        f"⚖️ الصافي: {net} د.ح\n\n"
        f"عدد الوجبات المسجلة: {len(user_data['meals'])}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if context.user_data.get("waiting_for_burned"):
        try:
            burned = int(text.strip())
            data, uid = get_user_entry(update.effective_user.id)
            data[uid]["burned"] += burned
            save_data(data)
            context.user_data["waiting_for_burned"] = False
            await update.message.reply_text(f"تم تسجيل {burned} سعرة محروقة بنجاح! 🔥")
        except ValueError:
            await update.message.reply_text("يرجى إدخال رقم صحيح للسعرات المحروقة.")

async def prompt_burned_calories(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    for uid in data.keys():
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text="⏰ تذكير 11:00 مساءً: كم سعرة حرارية حرقتها اليوم في التمارين/النشاط؟ أرسل الرقم مباشرة."
            )
        except Exception:
            pass

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_daily(prompt_burned_calories, time=time(hour=23, minute=0, second=0))
    
    print("البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()