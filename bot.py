import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import time
import os
import logging
from flask import Flask

# إعداد نظام التسجيل (Logging)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# قراءة التوكن من متغيرات البيئة
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN لم يتم تعيين")
    raise ValueError("الرجاء تعيين TELEGRAM_BOT_TOKEN في متغيرات البيئة")

bot = telebot.TeleBot(TOKEN)
games = {}
games_lock = threading.RLock()  # قفل للحماية من التصادم بين الخيوط

# Flask app للحفاظ على البوت نشط (اختياري لـ Railway)
app = Flask(__name__)

@app.route('/')
def home():
    return "البوت يعمل بشكل طبيعي!"

@app.route('/health')
def health():
    with games_lock:
        return {"status": "healthy", "active_games": len(games)}

def run_flask():
    """تشغيل خادم Flask في خيط منفصل"""
    try:
        # استخدام PORT من متغيرات البيئة للتوافق مع Railway
        port = int(os.getenv('PORT', 5000))
        app.run(host='0.0.0.0', port=port, debug=False)
    except Exception as e:
        logger.error(f"خطأ في تشغيل خادم Flask: {e}")

# --- دوال مساعدة ---

def create_board(size):
    """إنشاء لوحة اللعب مع زر الاستسلام"""
    try:
        markup = InlineKeyboardMarkup()
        markup.row_width = size
        for i in range(size):
            row_buttons = []
            for j in range(size):
                row_buttons.append(InlineKeyboardButton(" ", callback_data=f"play_{i}_{j}"))
            markup.add(*row_buttons)
        
        markup.add(InlineKeyboardButton("🏳️ استسلام (Resign)", callback_data="resign"))
        return markup
    except Exception as e:
        logger.error(f"خطأ في إنشاء اللوحة: {e}")
        return None

def check_winner(board):
    """التحقق من وجود فائز"""
    try:
        size = len(board)
        # فحص الصفوف
        for i in range(size):
            if len(set(board[i])) == 1 and board[i][0] != " ": 
                return board[i][0]
        
        # فحص الأعمدة
        for i in range(size):
            column = [board[r][i] for r in range(size)]
            if len(set(column)) == 1 and column[0] != " ": 
                return column[0]
        
        # فحص القطر الأول
        diag1 = [board[i][i] for i in range(size)]
        if len(set(diag1)) == 1 and diag1[0] != " ": 
            return diag1[0]
        
        # فحص القطر الثاني
        diag2 = [board[i][size - 1 - i] for i in range(size)]
        if len(set(diag2)) == 1 and diag2[0] != " ": 
            return diag2[0]
        
        return None
    except Exception as e:
        logger.error(f"خطأ في فحص الفائز: {e}")
        return None

def game_timeout_checker(chat_id, message_id):
    """پشکنینی یارییەکان دوای ٥ خولەک"""
    try:
        time.sleep(300)  # 5 دقائق
        game_key = f"{chat_id}:{message_id}"
        with games_lock:
            if game_key in games and games[game_key]['player_o_id'] is None:
                try:
                    bot.edit_message_text(
                        "انتهى وقت انتظار هذه اللعبة وتم إلغاؤها.",
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=None
                    )
                    del games[game_key]
                    logger.info(f"تم إلغاء اللعبة {game_key} بسبب انتهاء الوقت")
                except Exception as e:
                    logger.error(f"خطأ في إلغاء اللعبة: {e}")
    except Exception as e:
        logger.error(f"خطأ في فحص انتهاء الوقت: {e}")

# --- أوامر البوت ---

@bot.message_handler(commands=['start', 'help'])
def show_help(message):
    try:
        help_text = (
            "مرحباً بك في بوت لعبة إكس-أو! 🎮\n\n"
            "**طرق بدء اللعبة:**\n"
            "1️⃣ `/new_game` - لبدء لعبة مفتوحة لأي شخص.\n"
            "2️⃣ `/yala_ta3al` - قم بالرد على رسالة شخص ما بهذا الأمر لدعوته للعب.\n\n"
            "🔹 `/help` - لعرض هذه الرسالة.\n"
            "🔹 `/status` - لعرض عدد الألعاب النشطة."
        )
        bot.reply_to(message, help_text, parse_mode="Markdown")
        logger.info(f"تم عرض المساعدة للمستخدم {message.from_user.id}")
    except Exception as e:
        logger.error(f"خطأ في عرض المساعدة: {e}")
        try:
            bot.reply_to(message, "حدث خطأ في عرض المساعدة، حاول مرة أخرى.")
        except:
            pass

@bot.message_handler(commands=['status'])
def show_status(message):
    try:
        with games_lock:
            active_games = len(games)
        status_text = f"📊 **حالة البوت:**\n\nعدد الألعاب النشطة: {active_games}"
        bot.reply_to(message, status_text, parse_mode="Markdown")
        logger.info(f"تم عرض الحالة للمستخدم {message.from_user.id}")
    except Exception as e:
        logger.error(f"خطأ في عرض الحالة: {e}")

@bot.message_handler(commands=['new_game', 'yala_ta3al'])
def start_game_handler(message):
    try:
        chat_id = message.chat.id
        command = message.text.split()[0]
        
        invited_player_id = None
        invited_player_name = None
        
        if command == '/yala_ta3al':
            if message.reply_to_message:
                invited_player_id = message.reply_to_message.from_user.id
                invited_player_name = message.reply_to_message.from_user.first_name
                if invited_player_id == message.from_user.id:
                    bot.reply_to(message, "لا يمكنك أن تلعب مع نفسك! 😄")
                    return
            else:
                bot.reply_to(message, "لبدء لعبة مع شخص معين، يجب أن ترد على إحدى رسائله باستخدام الأمر `/yala_ta3al`.")
                return

        board_size = 3
        markup = create_board(board_size)
        
        if markup is None:
            bot.reply_to(message, "حدث خطأ في إنشاء اللعبة، حاول مرة أخرى.")
            return
        
        if invited_player_id:
            text = (
                f"🎮 بدأت لعبة إكس-أو (٣x٣)!\n"
                f"اللاعب {message.from_user.first_name} (❌) دعا {invited_player_name} (⭕) للعب.\n"
                f"الدور لـ {message.from_user.first_name} (❌)."
            )
        else:
            text = (
                f"🎮 بدأت لعبة إكس-أو (٣x٣)!\n"
                f"اللاعب {message.from_user.first_name} (❌) يبدأ.\n"
                f"بانتظار انضمام اللاعب الثاني (⭕)..."
            )
        
        msg = bot.send_message(chat_id, text, reply_markup=markup)
        message_id = msg.message_id
        game_key = f"{chat_id}:{message_id}"

        with games_lock:
            games[game_key] = {
                'chat_id': chat_id,
                'board': [[" " for _ in range(board_size)] for _ in range(board_size)],
                'turn': 'X',
                'player_x_id': message.from_user.id,
                'player_x_name': message.from_user.first_name,
                'player_o_id': invited_player_id,
                'player_o_name': invited_player_name,
                'board_size': board_size,
                'created_at': time.time()
            }
        
        if invited_player_id is None:
            timeout_thread = threading.Thread(target=game_timeout_checker, args=(chat_id, message_id))
            timeout_thread.daemon = True
            timeout_thread.start()
        
        logger.info(f"تم إنشاء لعبة جديدة {game_key} بواسطة {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"خطأ في إنشاء اللعبة: {e}")
        try:
            bot.reply_to(message, "حدث خطأ في إنشاء اللعبة، حاول مرة أخرى.")
        except:
            pass

# --- معالجة الاستجابات ---

@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    try:
        if call.data.startswith('play_'):
            handle_play_move(call)
        elif call.data == 'resign':
            handle_resign(call)
    except Exception as e:
        logger.error(f"خطأ في معالجة الاستجابة: {e}")
        try:
            bot.answer_callback_query(call.id, "حدث خطأ، حاول مرة أخرى.", show_alert=True)
        except:
            pass

def handle_resign(call):
    try:
        message_id = call.message.message_id
        chat_id = call.message.chat.id
        game_key = f"{chat_id}:{message_id}"
        user = call.from_user
        
        with games_lock:
            if game_key not in games:
                bot.answer_callback_query(call.id, "هذه اللعبة قد انتهت بالفعل.", show_alert=True)
                return
                
            game = games[game_key]
            
            if user.id == game['player_x_id']:
                winner_name = game.get('player_o_name', "اللاعب O")
            elif user.id == game['player_o_id']:
                winner_name = game['player_x_name']
            else:
                bot.answer_callback_query(call.id, "أنت لست جزءاً من هذه اللعبة.", show_alert=True)
                return
                
            text = f"🏳️ استسلم اللاعب {user.first_name}!\n🏆 الفائز هو: {winner_name}\n\nلبدء لعبة جديدة: /new_game"
            bot.edit_message_text(text, game['chat_id'], message_id, reply_markup=None)
            del games[game_key]
            logger.info(f"تم استسلام اللاعب {user.id} في اللعبة {game_key}")
        
    except Exception as e:
        logger.error(f"خطأ في الاستسلام: {e}")

def handle_play_move(call):
    try:
        message_id = call.message.message_id
        chat_id = call.message.chat.id
        game_key = f"{chat_id}:{message_id}"
        user = call.from_user
        
        with games_lock:
            if game_key not in games:
                bot.answer_callback_query(call.id, "هذه اللعبة قد انتهت أو تم إلغاؤها.", show_alert=True)
                return
                
            game = games[game_key]
        
            # إذا لم ينضم اللاعب الثاني بعد
            if game['player_o_id'] is None and user.id != game['player_x_id']:
                game['player_o_id'] = user.id
                game['player_o_name'] = user.first_name
                bot.answer_callback_query(call.id, f"🎉 {user.first_name} انضم كلاعب 'O'!")
                logger.info(f"انضم اللاعب {user.id} للعبة {game_key}")

            # فحص الدور
            if (game['turn'] == 'X' and user.id != game['player_x_id']) or \
               (game['turn'] == 'O' and user.id != game['player_o_id']):
                bot.answer_callback_query(call.id, "ليس دورك! ⏰", show_alert=True)
                return

            # معالجة الحركة
            _, r_str, c_str = call.data.split('_')
            row, col = int(r_str), int(c_str)

            if game['board'][row][col] == " ":
                game['board'][row][col] = game['turn']
                symbol = "❌" if game['turn'] == 'X' else "⭕"
                
                # فحص الفائز
                winner = check_winner(game['board'])
                if winner:
                    winner_name = game['player_x_name'] if winner == 'X' else game['player_o_name']
                    symbol = "❌" if winner == 'X' else "⭕"
                    text = f"🎉 انتهت اللعبة!\n🏆 الفائز: {winner_name} ({symbol})\n\nلبدء لعبة جديدة: /new_game"
                    bot.edit_message_text(text, game['chat_id'], message_id, reply_markup=None)
                    del games[game_key]
                    logger.info(f"انتهت اللعبة {game_key} بفوز {winner_name}")
                    return

                # فحص التعادل
                if all(cell != " " for row_board in game['board'] for cell in row_board):
                    text = "🤝 انتهت اللعبة بالتعادل!\nلبدء لعبة جديدة: /new_game"
                    bot.edit_message_text(text, game['chat_id'], message_id, reply_markup=None)
                    del games[game_key]
                    logger.info(f"انتهت اللعبة {game_key} بالتعادل")
                    return

                # تبديل الدور
                game['turn'] = 'O' if game['turn'] == 'X' else 'X'
                
                # تحديث اللوحة
                markup = create_board(game['board_size'])
                if markup:
                    for i in range(game['board_size']):
                        for j in range(game['board_size']):
                            if game['board'][i][j] == 'X':
                                markup.keyboard[i][j].text = "❌"
                            elif game['board'][i][j] == 'O':
                                markup.keyboard[i][j].text = "⭕"
                    
                    next_player_name = game['player_x_name'] if game['turn'] == 'X' else game['player_o_name']
                    next_symbol = "❌" if game['turn'] == 'X' else "⭕"
                    text = f"🎮 اللعبة بين {game['player_x_name']} (❌) و {game['player_o_name']} (⭕).\n⏳ الدور الآن لـ {next_player_name} ({next_symbol})."
                    bot.edit_message_text(text, game['chat_id'], message_id, reply_markup=markup)
            else:
                bot.answer_callback_query(call.id, "هذه الخانة ممتلئة! ❌", show_alert=True)
            
    except Exception as e:
        logger.error(f"خطأ في معالجة الحركة: {e}")
        try:
            bot.answer_callback_query(call.id, "حدث خطأ، حاول مرة أخرى.", show_alert=True)
        except:
            pass

def cleanup_old_games():
    """تنظيف الألعاب القديمة كل ساعة"""
    while True:
        try:
            current_time = time.time()
            old_games = []
            
            # الحصول على نسخة آمنة من الألعاب لتجنب التصادم
            with games_lock:
                games_snapshot = list(games.items())
            
            for game_key, game in games_snapshot:
                # إزالة الألعاب التي مر عليها أكثر من ساعتين
                if current_time - game.get('created_at', 0) > 7200:
                    old_games.append(game_key)
            
            for game_key in old_games:
                try:
                    with games_lock:
                        if game_key in games:  # فحص مجدد داخل القفل
                            game = games[game_key]
                            try:
                                # استخراج chat_id و message_id من المفتاح المركب
                                chat_id, message_id = game_key.split(':', 1)
                                bot.edit_message_text(
                                    "تم إنهاء هذه اللعبة تلقائياً لعدم النشاط.",
                                    int(chat_id),
                                    int(message_id),
                                    reply_markup=None
                                )
                            except Exception as edit_error:
                                logger.warning(f"خطأ في تعديل رسالة اللعبة {game_key}: {edit_error}")
                            del games[game_key]
                            logger.info(f"تم حذف اللعبة القديمة {game_key}")
                except Exception as delete_error:
                    logger.error(f"خطأ في حذف اللعبة {game_key}: {delete_error}")
            
            time.sleep(3600)  # ساعة واحدة
        except Exception as e:
            logger.error(f"خطأ في تنظيف الألعاب القديمة: {e}")
            # في حالة الخطأ، انتظر فقط دقيقة واحدة قبل المحاولة مرة أخرى
            time.sleep(60)

def main():
    """دالة التشغيل الرئيسية"""
    try:
        logger.info("بدء تشغيل البوت...")
        
        # تشغيل خادم Flask في خيط منفصل
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()
        logger.info("تم تشغيل خادم Flask")
        
        # تشغيل تنظيف الألعاب القديمة في خيط منفصل
        cleanup_thread = threading.Thread(target=cleanup_old_games)
        cleanup_thread.daemon = True
        cleanup_thread.start()
        logger.info("تم تشغيل نظام تنظيف الألعاب")
        
        # تشغيل البوت مع إعادة التشغيل التلقائي
        while True:
            try:
                logger.info("البوت جاهز وبدأ بالعمل...")
                bot.polling(none_stop=True, interval=0, timeout=20)
            except Exception as e:
                logger.error(f"خطأ في تشغيل البوت: {e}")
                logger.info("إعادة تشغيل البوت خلال 10 ثوان...")
                time.sleep(10)
                
    except KeyboardInterrupt:
        logger.info("تم إيقاف البوت بواسطة المستخدم")
    except Exception as e:
        logger.error(f"خطأ عام في البوت: {e}")

if __name__ == "__main__":
    main()