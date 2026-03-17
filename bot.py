import os
import json
import logging
import asyncio
from datetime import datetime, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Poll
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    JobQueue,
)
from telegram.error import TelegramError

# إعداد التسجيل (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# مسار ملف البيانات
STATE_FILE = 'state.json'

# تحميل البيانات من الملف
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            return {"users": {}}
    return {"users": {}}

# حفظ البيانات في الملف
def save_state(state):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Error saving state: {e}")

# تهيئة بيانات المستخدم الجديد
def init_user(state, user_id):
    user_id = str(user_id)
    if user_id not in state["users"]:
        state["users"][user_id] = {
            "channels": [],
            "queue": [],
            "published": [],
            "settings": {
                "daily_limit": 5,
                "is_active": True,
                "last_post_time": None
            }
        }
        save_state(state)

# لوحة التحكم الرئيسية
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📢 إدارة القنوات", callback_data='manage_channels')],
        [InlineKeyboardButton("📦 إدارة المنشورات", callback_data='manage_posts')],
        [InlineKeyboardButton("⚙️ الإعدادات", callback_data='settings')],
        [InlineKeyboardButton("▶️ تشغيل / ⏸ إيقاف", callback_data='toggle_status')]
    ]
    return InlineKeyboardMarkup(keyboard)

# معالج أمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = load_state()
    init_user(state, user_id)
    
    await update.message.reply_text(
        "👋 أهلاً بك في بوت النشر التلقائي!\n\n"
        "يمكنك من هنا إدارة قنواتك، جدولة منشوراتك، والتحكم في إعدادات النشر.\n"
        "أرسل أي محتوى (نص، صورة، فيديو...) لإضافته إلى قائمة الانتظار.",
        reply_markup=main_menu_keyboard()
    )

# معالجة الضغط على الأزرار
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    
    state = load_state()
    user_data = state["users"].get(user_id)
    
    if not user_data:
        await query.edit_message_text("عذراً، حدث خطأ. يرجى إرسال /start مجدداً.")
        return

    if query.data == 'manage_channels':
        channels_text = "📢 القنوات المضافة حالياً:\n"
        if not user_data["channels"]:
            channels_text += "لا توجد قنوات مضافة."
        for ch in user_data["channels"]:
            channels_text += f"- {ch}\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ إضافة قناة", callback_data='add_channel_info')],
            [InlineKeyboardButton("🗑 حذف قناة", callback_data='remove_channel_info')],
            [InlineKeyboardButton("🔙 العودة", callback_data='main_menu')]
        ]
        await query.edit_message_text(channels_text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == 'add_channel_info':
        await query.edit_message_text(
            "لإضافة قناة:\n1. أضف البوت كمسؤول (Admin) في القناة.\n"
            "2. أرسل معرف القناة (مثلاً @channel_name) أو قم بتوجيه رسالة من القناة هنا.\n"
            "استخدم الأمر: /add_channel @name",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة", callback_data='manage_channels')]]))

    elif query.data == 'manage_posts':
        queue_count = len(user_data["queue"])
        published_count = len(user_data["published"])
        text = f"📦 إحصائيات المنشورات:\n- في الانتظار: {queue_count}\n- تم نشرها: {published_count}"
        
        keyboard = [
            [InlineKeyboardButton("🗑 مسح قائمة الانتظار", callback_data='clear_queue')],
            [InlineKeyboardButton("🔙 العودة", callback_data='main_menu')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == 'settings':
        limit = user_data["settings"]["daily_limit"]
        status = "متوقف ⏸" if not user_data["settings"]["is_active"] else "يعمل ▶️"
        text = f"⚙️ الإعدادات الحالية:\n- الحد اليومي: {limit} منشورات\n- الحالة: {status}\n\nلتغيير الحد اليومي استخدم: /set_daily [العدد]"
        
        keyboard = [[InlineKeyboardButton("🔙 العودة", callback_data='main_menu')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == 'toggle_status':
        user_data["settings"]["is_active"] = not user_data["settings"]["is_active"]
        save_state(state)
        status = "يعمل ▶️" if user_data["settings"]["is_active"] else "متوقف ⏸"
        await query.edit_message_text(f"تم تغيير الحالة إلى: {status}", reply_markup=main_menu_keyboard())

    elif query.data == 'main_menu':
        await query.edit_message_text("القائمة الرئيسية:", reply_markup=main_menu_keyboard())

    elif query.data == 'clear_queue':
        user_data["queue"] = []
        save_state(state)
        await query.edit_message_text("تم مسح قائمة الانتظار بنجاح.", reply_markup=main_menu_keyboard())

# إضافة قناة عبر الأمر
async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("يرجى كتابة معرف القناة بعد الأمر. مثال: /add_channel @mychannel")
        return
    
    channel_id = context.args[0]
    state = load_state()
    init_user(state, user_id)
    
    if channel_id not in state["users"][user_id]["channels"]:
        # محاولة التحقق من صلاحيات البوت في القناة
        try:
            member = await context.bot.get_chat_member(channel_id, context.bot.id)
            if member.status in ['administrator', 'creator']:
                state["users"][user_id]["channels"].append(channel_id)
                save_state(state)
                await update.message.reply_text(f"✅ تم إضافة القناة {channel_id} بنجاح!")
            else:
                await update.message.reply_text("❌ البوت ليس مسؤولاً في هذه القناة. يرجى ترقيته أولاً.")
        except Exception as e:
            await update.message.reply_text(f"❌ تعذر الوصول للقناة. تأكد من المعرف ومن وجود البوت فيها.\nالخطأ: {str(e)}")
    else:
        await update.message.reply_text("القناة مضافة بالفعل.")

# تحديد الحد اليومي
async def set_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("يرجى كتابة رقم صحيح. مثال: /set_daily 10")
        return
    
    limit = int(context.args[0])
    state = load_state()
    init_user(state, user_id)
    state["users"][user_id]["settings"]["daily_limit"] = limit
    save_state(state)
    await update.message.reply_text(f"✅ تم تحديث الحد اليومي إلى {limit} منشورات.")

# استقبال المحتوى وتخزينه
async def handle_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    state = load_state()
    init_user(state, user_id)
    
    content = {}
    msg = update.message
    
    if msg.text:
        content = {"type": "text", "text": msg.text}
    elif msg.photo:
        content = {"type": "photo", "file_id": msg.photo[-1].file_id, "caption": msg.caption}
    elif msg.video:
        content = {"type": "video", "file_id": msg.video.file_id, "caption": msg.caption}
    elif msg.audio:
        content = {"type": "audio", "file_id": msg.audio.file_id, "caption": msg.caption}
    elif msg.voice:
        content = {"type": "voice", "file_id": msg.voice.file_id, "caption": msg.caption}
    elif msg.document:
        content = {"type": "document", "file_id": msg.document.file_id, "caption": msg.caption}
    elif msg.poll:
        content = {
            "type": "poll",
            "question": msg.poll.question,
            "options": [o.text for o in msg.poll.options],
            "is_anonymous": msg.poll.is_anonymous,
            "allows_multiple_answers": msg.poll.allows_multiple_answers
        }
    
    if content:
        state["users"][user_id]["queue"].append(content)
        save_state(state)
        await update.message.reply_text(f"✅ تم إضافة المنشور إلى قائمة الانتظار. (الإجمالي: {len(state['users'][user_id]['queue'])})")

# وظيفة النشر التلقائي (تُستدعى بواسطة المجدول)
async def auto_post_job(context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    for user_id, data in state["users"].items():
        if not data["settings"]["is_active"] or not data["channels"] or not data["queue"]:
            continue
        
        # التحقق من الحد اليومي (تبسيط: النشر إذا كان هناك محتوى)
        # يمكن تطوير هذا الجزء لحساب عدد المنشورات في آخر 24 ساعة
        
        post = data["queue"].pop(0)
        success = False
        
        for channel in data["channels"]:
            try:
                if post["type"] == "text":
                    await context.bot.send_message(chat_id=channel, text=post["text"])
                elif post["type"] == "photo":
                    await context.bot.send_photo(chat_id=channel, photo=post["file_id"], caption=post.get("caption"))
                elif post["type"] == "video":
                    await context.bot.send_video(chat_id=channel, video=post["file_id"], caption=post.get("caption"))
                elif post["type"] == "audio":
                    await context.bot.send_audio(chat_id=channel, audio=post["file_id"], caption=post.get("caption"))
                elif post["type"] == "voice":
                    await context.bot.send_voice(chat_id=channel, voice=post["file_id"], caption=post.get("caption"))
                elif post["type"] == "document":
                    await context.bot.send_document(chat_id=channel, document=post["file_id"], caption=post.get("caption"))
                elif post["type"] == "poll":
                    await context.bot.send_poll(
                        chat_id=channel,
                        question=post["question"],
                        options=post["options"],
                        is_anonymous=post["is_anonymous"],
                        allows_multiple_answers=post["allows_multiple_answers"]
                    )
                success = True
            except Exception as e:
                logger.error(f"Failed to post to {channel} for user {user_id}: {e}")
        
        if success:
            data["published"].append(post)
            save_state(state)

def main():
    # الحصول على التوكن من متغيرات البيئة
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        print("Error: BOT_TOKEN environment variable is not set.")
        return

    application = Application.builder().token(TOKEN).build()

    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add_channel", add_channel))
    application.add_handler(CommandHandler("set_daily", set_daily))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # معالجة كافة أنواع الوسائط
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.AUDIO | 
         filters.VOICE | filters.Document.ALL | filters.POLL) & ~filters.COMMAND,
        handle_content
    ))

    # إعداد المجدول (تشغيل كل ساعة مثلاً)
    # يمكنك تغيير interval إلى القيمة التي تناسبك بالثواني (3600 = ساعة)
    job_queue = application.job_queue
    job_queue.run_repeating(auto_post_job, interval=3600, first=10)

    # بدء التشغيل
    application.run_polling()

if __name__ == '__main__':
    main()
