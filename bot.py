import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
import requests
import hashlib
import base64
import json
import logging
import threading
import time
import socketio
import random
import string
import os
from datetime import datetime, timedelta
from functools import wraps
import re

# ==========================================
# CẤU HÌNH
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger('engineio').setLevel(logging.WARNING)
logging.getLogger('socketio').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

BOT_TOKEN = '8296926605:AAH32SNx9cbvcROyZV2ZXcszM3DOU9Wi7ro'
ADMIN_ID = 8375848425
ADMIN_CONTACT = '@nhan161019'

# ==========================================
# KÊNH/NHÓM YÊU CẦU THAM GIA (BẮT BUỘC)
# ==========================================
REQUIRED_CHANNELS = [
    {"name": "📢 Kênh Thông Tin", "url": "https://t.me/thongbaotoolgamevip"},
    {"name": "💬 Nhóm Chat", "url": "https://t.me/nhomgiaolmd5"},
]

GROUP_LINK = 'https://t.me/nhomgiaolmd5'
CHANNEL_LINK = 'https://t.me/thongbaotoolgamevip'

DATA_COLLECTOR_USER = "acc_clone_soi_cau"
DATA_COLLECTOR_PASS = "matkhau123"

# ==========================================
# QR CODE CỐ ĐỊNH
# ==========================================
BANK_BIN = 'BIDV'
BANK_ACC = '8887596710'
BANK_NAME = 'NGUYEN THANH NHAN'
QR_CODE_URL = 'https://vietqr.app/img?bank=BIDV&acc=96247KBYXG&template=compact&showinfo=true&holder=NGUYEN%20THANH%20NHAN'

# ==========================================
# BOT INIT
# ==========================================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')
DB_FILE = 'database.json'

# ==========================================
# BẢNG GIÁ KEY VIP
# ==========================================
KEY_PRICES = {
    1: 40000,      # 1 Ngày - 40k
    3: 90000,      # 3 Ngày - 90k
    7: 130000,     # 1 Tuần - 130k
    30: 170000,    # 1 Tháng - 170k
    365: 250000,   # 1 Năm - 250k
    9999: 300000   # Vĩnh Viễn - 300k
}

# ==========================================
# DATABASE
# ==========================================
def load_db():
    default = {"users": {}, "keys": {}, "giftcodes": {}, "pending_deposits": {}, 
               "pending_feedbacks": {}, "history_md5": [], "is_reversed_mode": False,
               "joined_users": [], "processed_trans": [], "transaction_history": {}}
    if not os.path.exists(DB_FILE): return default
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for k in default: data.setdefault(k, default[k])
            return data
    except: return default

def save_db(): 
    with open(DB_FILE, 'w', encoding='utf-8') as f: 
        json.dump(db, f, ensure_ascii=False, indent=4)

db = load_db()

# ==========================================
# CHECK USER JOINED
# ==========================================
def check_user_joined(user_id):
    if str(user_id) == str(ADMIN_ID):
        return True
    if str(user_id) in db.get("joined_users", []):
        return True
    return False

def require_joined(func):
    @wraps(func)
    def wrapper(message):
        user_id = message.from_user.id
        if not check_user_joined(user_id):
            msg = (
                "🔔 <b>YÊU CẦU BẤT BUỘC</b>\n"
                "Để sử dụng bot, vui lòng tham gia đầy đủ các kênh và nhóm bên dưới.\n"
                "Nhấn nút <b>Xác Nhận Join</b> sau khi đã hoàn tất."
            )
            bot.send_message(message.chat.id, msg, reply_markup=kb_verify_join())
            return
        return func(message)
    return wrapper

def kb_verify_join():
    markup = InlineKeyboardMarkup(row_width=2)
    for channel in REQUIRED_CHANNELS:
        markup.add(InlineKeyboardButton(f"📢 {channel['name']}", url=channel['url']))
    markup.add(InlineKeyboardButton("✅ Xác Nhận Join", callback_data="verify_join"))
    return markup

# ==========================================
# GLOBAL VARIABLES
# ==========================================
active_sockets = {}
active_sockets_md5 = {}
user_states = {}
user_states_md5 = {}
history_lock = threading.Lock()
processed_message_ids = set()
AUTO_VIP_ENABLED = False
GLOBAL_HISTORY = []
MAX_GLOBAL_HISTORY = 2000
GLOBAL_STATS = {"total_win": 0, "total_lose": 0, "total_draw": 0, "total_profit": 0,
                "current_streak_win": 0, "max_streak_win": 0,
                "current_streak_lose": 0, "max_streak_lose": 0}
SPAM_TRACKER = {}
SPAM_THRESHOLD = 1.2
MAX_WARNINGS = 2

# ==========================================
# USER MANAGEMENT
# ==========================================
def get_user(user_id):
    user_id = str(user_id)
    if user_id not in db["users"]:
        db["users"][user_id] = {"username": "", "balance": 0, "key_expiry": None, 
                                "is_blocked": False, "can_create_giftcode": True}
        save_db()
    return db["users"][user_id]

def update_user(user_id, **kwargs):
    user = get_user(user_id)
    user.update(kwargs)
    db["users"][str(user_id)] = user
    save_db()

def check_active_key(user_id):
    if AUTO_VIP_ENABLED or str(user_id) == str(ADMIN_ID):
        return True
    user = get_user(user_id)
    if not user.get("key_expiry"):
        return False
    try:
        expiry = datetime.fromisoformat(user["key_expiry"])
        if datetime.now() > expiry:
            update_user(user_id, key_expiry=None)
            return False
        return True
    except:
        return False

def is_vip(chat_id):
    return check_active_key(chat_id)

def get_footer():
    return f"--------------------------------------------------\n⏱ {datetime.now().strftime('%H:%M:%S • %d/%m/%Y')} • THÀNH NHÂN ADM {ADMIN_CONTACT}"

def is_user_blocked(user_id):
    if str(user_id) == str(ADMIN_ID): return False
    return get_user(user_id).get("is_blocked", False)

def check_anti_spam(user_id, chat_id):
    if str(user_id) == str(ADMIN_ID): return False
    now = time.time()
    user_data = SPAM_TRACKER.get(user_id, {"count": 0, "last_time": 0})
    time_diff = now - user_data["last_time"]
    if time_diff < 1.2:
        user_data["count"] += 1
        user_data["last_time"] = now
        SPAM_TRACKER[user_id] = user_data
        if user_data["count"] > 2:
            update_user(user_id, is_blocked=True)
            bot.send_message(chat_id, f"🚫 <b>TÀI KHOẢN ĐÃ BỊ KHÓA VĨNH VIỄN!</b>\n👤 Liên hệ {ADMIN_CONTACT}")
            return True
        else:
            rem = 2 - user_data["count"] + 1
            bot.send_message(chat_id, f"⚠️ <b>CẢNH BÁO SPAM!</b> Còn {rem} lần sẽ bị KHÓA!")
            return True
    elif time_diff > 30:
        user_data["count"] = 0
    user_data["last_time"] = now
    SPAM_TRACKER[user_id] = user_data
    return False

def check_and_block(call_or_msg):
    user_id = call_or_msg.from_user.id
    chat_id = call_or_msg.message.chat.id if isinstance(call_or_msg, telebot.types.CallbackQuery) else call_or_msg.chat.id
    if is_user_blocked(user_id):
        msg = f"🚫 <b>TÀI KHOẢN BỊ KHÓA</b>\nLiên hệ {ADMIN_CONTACT}\n" + get_footer()
        if isinstance(call_or_msg, telebot.types.CallbackQuery):
            bot.answer_callback_query(call_or_msg.id, "❌ Bạn đã bị khóa!", show_alert=True)
            bot.edit_message_text(msg, chat_id=chat_id, message_id=call_or_msg.message.message_id)
        else:
            bot.send_message(chat_id, msg)
        return True
    if check_anti_spam(user_id, chat_id):
        return True
    return False

def init_user_state(chat_id):
    if chat_id not in user_states:
        user_states[chat_id] = {"profit_loss": 0, "auto_bet_enabled": False, "x2_mode": False,
                                "win_streak": 0, "base_bet_amount": 10000, "current_bet": 10000,
                                "target_profit": None, "current_prediction": None,
                                "waiting_for_result": False, "has_bet_this_session": False,
                                "session_id": None, "balance": 0, "history_15": []}

def init_user_state_md5(chat_id):
    if chat_id not in user_states_md5:
        user_states_md5[chat_id] = {"profit_loss": 0, "auto_bet_enabled": False, "x2_mode": False,
                                    "win_streak": 0, "base_bet_amount": 10000, "current_bet": 10000,
                                    "target_profit": None, "current_prediction": None,
                                    "waiting_for_result": False, "has_bet_this_session": False,
                                    "session_id": None, "balance": 0, "history_15": []}

# ==========================================
# DECORATORS
# ==========================================
def require_vip(func):
    @wraps(func)
    def wrapper(message):
        if not is_vip(message.chat.id):
            return bot.reply_to(message, "⛔ <b>BẠN CHƯA KÍCH HOẠT VIP!</b> Vui lòng mua Key để dùng chức năng.", parse_mode="HTML")
        return func(message)
    return wrapper

def admin_only(func):
    @wraps(func)
    def wrapper(message):
        if str(message.from_user.id) != str(ADMIN_ID):
            return
        return func(message)
    return wrapper

# ==========================================
# THUẬT TOÁN AI SOI CẦU
# ==========================================
def make_prediction_smart(chat_id):
    with history_lock:
        history = list(GLOBAL_HISTORY)
    if len(history) < 3: return None
    recent_str = "".join(["T" if x == "TAI" else "X" for x in history[-15:]])
    if recent_str.endswith("TTT"): return "TAI"
    if recent_str.endswith("XXX"): return "XIU"
    if recent_str.endswith("TXT"): return "XIU"
    if recent_str.endswith("XTX"): return "TAI"
    if recent_str.endswith("TTXX"): return "TAI"
    if recent_str.endswith("XXTT"): return "XIU"
    if recent_str.endswith("TTXT"): return "TAI"
    if recent_str.endswith("XXTX"): return "XIU"
    t_count = recent_str[-3:].count("T")
    return "TAI" if t_count >= 2 else "XIU"

def analyze_ai_deep(hash_str):
    clean_hash = hash_str.strip().lower()
    x = int(clean_hash[:8], 16)
    tai_percent = x % 100
    xiu_percent = 100 - tai_percent
    if tai_percent < 10:
        tai_percent += 15
        xiu_percent = 100 - tai_percent
    elif xiu_percent < 10:
        xiu_percent += 15
        tai_percent = 100 - xiu_percent
    base_result = "TÀI" if tai_percent >= xiu_percent else "XỈU"
    is_reversed = db.get("is_reversed_mode", False)
    if is_reversed:
        base_result = "XỈU" if base_result == "TÀI" else "TÀI"
    return {"result": base_result, "tai_percent": tai_percent, "xiu_percent": xiu_percent, "is_reversed": is_reversed}

# ==========================================
# XỬ LÝ NẠP TIỀN TỪ WEBHOOK THUEAPI (GỌI TỪ FILE webhook.py)
# ==========================================
def process_deposit_from_webhook(user_id, amount, va=""):
    """Xử lý nạp tiền từ webhook ThueAPI - HÀM NÀY ĐƯỢC GỌI TỪ WEBHOOK.PY"""
    try:
        user = get_user(user_id)
        if user is None:
            logger.warning(f"User {user_id} không tồn tại")
            return False
        
        new_balance = user["balance"] + amount
        update_user(user_id, balance=new_balance)
        
        # Lưu lịch sử giao dịch
        db.setdefault("transaction_history", {}).setdefault(user_id, [])
        db["transaction_history"][user_id].append({
            "type": "deposit",
            "amount": amount,
            "balance": new_balance,
            "trans_id": f"VA-{va}",
            "time": datetime.now().isoformat()
        })
        save_db()
        
        # Gửi thông báo cho user
        try:
            bot.send_message(
                user_id,
                f"🎉 <b>NẠP TIỀN TỰ ĐỘNG THÀNH CÔNG!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 Số tiền: <code>+{amount:,}đ</code>\n"
                f"💳 Số dư mới: <code>{new_balance:,}đ</code>\n"
                f"📅 Lúc: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ <b>GIAO DỊCH ĐÃ ĐƯỢC TỰ ĐỘNG DUYỆT!</b>",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Không thể gửi tin cho user {user_id}: {e}")
        
        # Gửi thông báo cho admin
        try:
            bot.send_message(
                ADMIN_ID,
                f"✅ <b>TỰ ĐỘNG DUYỆT NẠP TIỀN</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🆔 User ID: <code>{user_id}</code>\n"
                f"💰 Số tiền: <code>+{amount:,}đ</code>\n"
                f"💳 Số dư mới: <code>{new_balance:,}đ</code>\n"
                f"📝 Mã GD: <code>VA-{va}</code>\n"
                f"📅 Lúc: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Không thể gửi tin cho admin: {e}")
        
        logger.info(f"✅ Nạp {amount:,}đ cho user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Lỗi xử lý nạp: {e}")
        return False

# ==========================================
# GAME FUNCTIONS
# ==========================================
def md5_hash(text): 
    return hashlib.md5(text.encode()).hexdigest()

def login_and_get_token(username, password):
    try:
        pw_md5 = md5_hash(password)
        r = requests.get(f"https://apifo88daigia.tele68.com/api?c=3&un={username}&pw={pw_md5}&cp=R&cl=R&pf=web&at=", timeout=12)
        data = r.json()
        if not data.get("success"): 
            return {"_error": f"Lỗi Game: {data.get('message', 'Sai thông tin')}"}
        
        session_key = data["sessionKey"]
        session_key += "=" * ((4 - len(session_key) % 4) % 4)
        session_data = json.loads(base64.b64decode(session_key).decode('utf-8'))
        nickname = session_data.get("nickname") or session_data.get("nickName")
        
        access_token = data["accessToken"]
        r2 = requests.post("https://wlb.tele68.com/v1/lobby/auth/login?cp=R&cl=R&pf=web&at=",
                          headers={"authority": "wlb.tele68.com", "content-type": "application/json"},
                          json={"nickName": nickname, "accessToken": access_token}, timeout=12)
        lobby = r2.json()
        token = lobby.get("token")
        if not token: 
            return {"_error": "Lobby không trả về JWT token."}
        return {"token": token, "nickname": nickname, "money": lobby.get("remoteLoginResp", {}).get("money", 0)}
    except Exception as e:
        return {"_error": f"Lỗi kết nối: {e}"}

# ==========================================
# WEBSOCKET FUNCTIONS
# ==========================================
def start_websocket(chat_id, token, is_background=False):
    if chat_id in active_sockets and not is_background:
        try: active_sockets[chat_id].disconnect()
        except: pass
        
    sio = socketio.Client(reconnection=True, reconnection_attempts=15, logger=False, engineio_logger=False)
    if not is_background:
        active_sockets[chat_id] = sio
        init_user_state(chat_id)

    @sio.event(namespace='/tx')
    def connect():
        if not is_background:
            bot.send_message(chat_id, "💎 <b>KẾT NỐI BÀN TÀI XỈU THƯỜNG THÀNH CÔNG</b>\n🎯 HŨ: 111 (Xỉu) - 666 (Tài)", parse_mode="HTML")

    @sio.on('new-session', namespace='/tx')
    def on_new_session(data):
        if is_background: return
        state = user_states[chat_id]
        state["session_id"] = data.get('id', 'N/A')
        state["has_bet_this_session"] = False
        
        if state["auto_bet_enabled"] and state["target_profit"] is not None:
            if state["profit_loss"] >= state["target_profit"]:
                state["auto_bet_enabled"] = False
                bot.send_message(chat_id, f"🏆 <b>ĐẠT MỤC TIÊU!</b> Lãi: <code>+{state['profit_loss']:,}đ</code>", parse_mode="HTML")

        prediction = make_prediction_smart(chat_id)
        state["current_prediction"] = prediction
        
        if state["x2_mode"] and state["win_streak"] >= 1:
            state["current_bet"] = state["base_bet_amount"] * 2
        else:
            state["current_bet"] = state["base_bet_amount"]

        msg = f"🔮 <b>PHIÊN MỚI:</b> <code>#{state['session_id']}</code>\n"
        if prediction:
            pred_emoji = "🔵 TÀI" if prediction == "TAI" else "🔴 XỈU"
            msg += f"💎 <b>AI CHỐT CẦU:</b> {pred_emoji}\n"
            if state["auto_bet_enabled"]:
                msg += f"✅ <b>Auto Bet:</b> Chuẩn bị VÀO <code>{state['current_bet']:,}đ</code>"
            else:
                msg += "⏸ Auto Bet đang tắt → Dùng /autobettx on"
        bot.send_message(chat_id, msg, parse_mode="HTML")

    @sio.on('tick-update', namespace='/tx')
    def on_tick_update(data):
        if is_background: return
        game_state = data.get('state')
        remain_time = data.get('tick', 0)
        state = user_states[chat_id]
        
        is_betting = game_state in ['BETTING', 'betting', 'OPEN'] or data.get('canBet') == True
        if is_betting and 5 <= remain_time <= 45:
            if state["auto_bet_enabled"] and state["current_prediction"] and not state["has_bet_this_session"]:
                sio.emit('bet', {"type": str(state["current_prediction"]), "amount": int(state["current_bet"])}, namespace='/tx')
                state["has_bet_this_session"] = True
                sio.emit('get-current-my-info', None, namespace='/tx')

    @sio.on('bet-result', namespace='/tx')
    def on_bet_result(data):
        if is_background: return
        state = user_states[chat_id]
        is_success = data.get('success') or data.get('status') == 1 or 'postBalance' in data or 'balance' in data
        if is_success:
            if 'postBalance' in data: state["balance"] = data["postBalance"]
            elif 'balance' in data: state["balance"] = data["balance"]
            state["waiting_for_result"] = True
            bot.send_message(chat_id, f"🚀 <b>CƯỢC THÀNH CÔNG!</b>\nCửa: <b>{state['current_prediction']}</b> | <code>{state['current_bet']:,}đ</code>", parse_mode="HTML")
        else:
            error_msg = data.get('message', data.get('msg', data.get('error', 'Lỗi')))
            bot.send_message(chat_id, f"❌ <b>CƯỢC THẤT BẠI:</b> {error_msg}", parse_mode="HTML")
            state["waiting_for_result"] = False

    @sio.on('session-result', namespace='/tx')
    def on_session_result(data):
        global GLOBAL_HISTORY, GLOBAL_STATS
        result = data.get('resultTruyenThong', 'N/A')
        dices = data.get('dices', [0, 0, 0])
        total_point = data.get('point', sum(dices))
        
        if result in ["TAI", "XIU"]:
            with history_lock:
                GLOBAL_HISTORY.append(result)
                if len(GLOBAL_HISTORY) > MAX_GLOBAL_HISTORY: GLOBAL_HISTORY.pop(0)

        if is_background: return
        state = user_states[chat_id]
        
        is_jackpot = False
        jackpot_result = None
        if dices[0] == dices[1] == dices[2]:
            if dices[0] == 1:
                is_jackpot = True
                jackpot_result = "XIU"
                jackpot_type = "💎 HŨ XỈU 111 💎"
            elif dices[0] == 6:
                is_jackpot = True
                jackpot_result = "TAI"
                jackpot_type = "💎 HŨ TÀI 666 💎"
        
        result_emoji = "🔵 TÀI" if result == "TAI" else ("🔴 XỈU" if result == "XIU" else "⚪ HOÀN")
        msg = f"🎲 <b>KẾT QUẢ:</b> {result_emoji} • <b>{dices[0]} + {dices[1]} + {dices[2]} = {total_point}</b>"
        
        if is_jackpot:
            msg += f"\n{jackpot_type}"
            if state["current_prediction"] == jackpot_result:
                msg += "\n🎉🎊 <b>CHÚC MỪNG ĐÃ HÚP HŨ!</b> 🎊🎉"
            else:
                msg += "\n😭 <b>MẤT HŨ! LÀM LẠI!</b>"
        
        if state["current_prediction"]:
            if state["current_prediction"] == result:
                if state["waiting_for_result"]:
                    win_amount = int(state["current_bet"] * 0.98)
                    state["profit_loss"] += win_amount
                    state["win_streak"] += 1
                    GLOBAL_STATS["total_win"] += 1
                    GLOBAL_STATS["total_profit"] += win_amount
                    msg += f"\n🎉 <b>HÚP!</b> <code>+{win_amount:,}đ</code>"
            elif result in ["TAI", "XIU"]:
                if state["waiting_for_result"]:
                    state["profit_loss"] -= state["current_bet"]
                    state["win_streak"] = 0
                    GLOBAL_STATS["total_lose"] += 1
                    GLOBAL_STATS["total_profit"] -= state["current_bet"]
                    msg += f"\n❌ <b>GÃY!</b> <code>-{state['current_bet']:,}đ</code>"
            state["waiting_for_result"] = False

        pl_sign = "+" if state["profit_loss"] >= 0 else ""
        msg += f"\n💰 <b>Ví:</b> <code>{state['balance']:,}đ</code> | <b>Lãi/Lỗ:</b> <code>{pl_sign}{state['profit_loss']:,}đ</code>"
        bot.send_message(chat_id, msg, parse_mode="HTML")

    @sio.on('my-info', namespace='/tx')
    def on_my_info(data):
        if is_background: return
        if data and 'balance' in data:
            user_states[chat_id]["balance"] = data["balance"]

    try:
        sio.connect('https://wtx.tele68.com', socketio_path='tx/', transports=['websocket'],
                   auth={"token": token}, headers={"User-Agent": "Mozilla/5.0"})
        sio.wait()
    except Exception as e:
        if not is_background: 
            bot.send_message(chat_id, f"⚠️ Lỗi: <code>{e}</code>", parse_mode="HTML")

def start_websocket_md5(chat_id, token, is_background=False):
    if chat_id in active_sockets_md5 and not is_background:
        try: active_sockets_md5[chat_id].disconnect()
        except: pass
        
    sio = socketio.Client(reconnection=True, reconnection_attempts=15, logger=False, engineio_logger=False)
    if not is_background:
        active_sockets_md5[chat_id] = sio
        init_user_state_md5(chat_id)

    @sio.event(namespace='/txmd5')
    def connect():
        if not is_background:
            bot.send_message(chat_id, "💎 <b>KẾT NỐI MD5 THÀNH CÔNG</b>", parse_mode="HTML")

    @sio.on('new-session', namespace='/txmd5')
    def on_new_session(data):
        if is_background: return
        state = user_states_md5[chat_id]
        state["session_id"] = data.get('id', 'N/A')
        state["has_bet_this_session"] = False
        
        if state["auto_bet_enabled"] and state["target_profit"] is not None:
            if state["profit_loss"] >= state["target_profit"]:
                state["auto_bet_enabled"] = False
                bot.send_message(chat_id, f"🏆 <b>ĐẠT MỤC TIÊU!</b> Lãi: <code>+{state['profit_loss']:,}đ</code>", parse_mode="HTML")

        prediction = make_prediction_smart(chat_id)
        state["current_prediction"] = prediction
        
        if state["x2_mode"] and state["win_streak"] >= 1:
            state["current_bet"] = state["base_bet_amount"] * 2
        else:
            state["current_bet"] = state["base_bet_amount"]

        msg = f"🔮 <b>PHIÊN MỚI (MD5):</b> <code>#{state['session_id']}</code>\n"
        if prediction:
            pred_emoji = "🔵 TÀI" if prediction == "TAI" else "🔴 XỈU"
            msg += f"💎 <b>AI CHỐT CẦU:</b> {pred_emoji}\n"
            if state["auto_bet_enabled"]:
                msg += f"✅ <b>Auto Bet:</b> Chuẩn bị VÀO <code>{state['current_bet']:,}đ</code>"
            else:
                msg += "⏸ Auto Bet đang tắt → Dùng /autobetmd5 on"
        bot.send_message(chat_id, msg, parse_mode="HTML")

    @sio.on('tick-update', namespace='/txmd5')
    def on_tick_update(data):
        if is_background: return
        state = user_states_md5[chat_id]
        if data.get('state') == 'BETTING' and 10 <= data.get('tick', 0) <= 45:
            if state["auto_bet_enabled"] and state["current_prediction"] and not state["has_bet_this_session"]:
                sio.emit('bet', {"type": str(state["current_prediction"]), "amount": int(state["current_bet"])}, namespace='/txmd5')
                state["has_bet_this_session"] = True

    @sio.on('bet-result', namespace='/txmd5')
    def on_bet_result(data):
        if is_background: return
        state = user_states_md5[chat_id]
        is_success = data.get('success') or data.get('status') == 1 or 'postBalance' in data
        if is_success:
            if 'postBalance' in data: state["balance"] = data["postBalance"]
            state["waiting_for_result"] = True
            bot.send_message(chat_id, f"🚀 <b>CƯỢC THÀNH CÔNG!</b>\nCửa: <b>{state['current_prediction']}</b> | <code>{state['current_bet']:,}đ</code>", parse_mode="HTML")
        else:
            bot.send_message(chat_id, f"❌ <b>CƯỢC THẤT BẠI:</b> {data.get('message', 'Lỗi')}", parse_mode="HTML")
            state["waiting_for_result"] = False

    @sio.on('session-result', namespace='/txmd5')
    def on_session_result(data):
        global GLOBAL_HISTORY, GLOBAL_STATS
        result = data.get('resultTruyenThong', 'N/A')
        if result in ["TAI", "XIU"]:
            with history_lock:
                GLOBAL_HISTORY.append(result)
                if len(GLOBAL_HISTORY) > MAX_GLOBAL_HISTORY: GLOBAL_HISTORY.pop(0)

        if is_background: return
        state = user_states_md5[chat_id]
        dices = data.get('dices', [0, 0, 0])
        total_dice = sum(dices)
        result_emoji = "🔵 TÀI" if result == "TAI" else ("🔴 XỈU" if result == "XIU" else "⚪ HOÀN")
        msg = f"🎲 <b>KẾT QUẢ:</b> {result_emoji} • <b>{dices[0]} + {dices[1]} + {dices[2]} = {total_dice}</b>"
        
        if state["current_prediction"]:
            if state["current_prediction"] == result:
                if state["waiting_for_result"]:
                    win_amount = int(state["current_bet"] * 0.98)
                    state["profit_loss"] += win_amount
                    state["win_streak"] += 1
                    GLOBAL_STATS["total_win"] += 1
                    GLOBAL_STATS["total_profit"] += win_amount
                    msg += f"\n🎉 <b>HÚP!</b> <code>+{win_amount:,}đ</code>"
            elif result in ["TAI", "XIU"]:
                if state["waiting_for_result"]:
                    state["profit_loss"] -= state["current_bet"]
                    state["win_streak"] = 0
                    GLOBAL_STATS["total_lose"] += 1
                    GLOBAL_STATS["total_profit"] -= state["current_bet"]
                    msg += f"\n❌ <b>GÃY!</b> <code>-{state['current_bet']:,}đ</code>"
            state["waiting_for_result"] = False

        pl_sign = "+" if state["profit_loss"] >= 0 else ""
        msg += f"\n💰 <b>Ví:</b> <code>{state['balance']:,}đ</code> | <b>Lãi/Lỗ:</b> <code>{pl_sign}{state['profit_loss']:,}đ</code>"
        bot.send_message(chat_id, msg, parse_mode="HTML")

    try:
        sio.connect('https://wtxmd52.tele68.com', socketio_path='txmd5/', transports=['websocket'],
                   auth={"token": token}, headers={"User-Agent": "Mozilla/5.0"})
        sio.wait()
    except Exception as e:
        if not is_background: 
            bot.send_message(chat_id, f"⚠️ Lỗi: <code>{e}</code>", parse_mode="HTML")

def background_data_collector():
    while True:
        try:
            res = login_and_get_token(DATA_COLLECTOR_USER, DATA_COLLECTOR_PASS)
            if "token" in res:
                start_websocket("BACKGROUND_WORKER", res["token"], is_background=True)
        except: pass
        time.sleep(30)

# ==========================================
# INLINE KEYBOARDS
# ==========================================
def kb_main_inline(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎮 Bàn Tài Xỉu Thường", callback_data="nav_game"),
        InlineKeyboardButton("🎲 Bàn Tài Xỉu MD5", callback_data="nav_game_md5")
    )
    markup.add(
        InlineKeyboardButton("📊 Thống Kê AI", callback_data="nav_stats"),
        InlineKeyboardButton("💼 Hồ Sơ", callback_data="nav_profile")
    )
    markup.add(
        InlineKeyboardButton("💳 Mua Key VIP", callback_data="nav_buy_key"),
        InlineKeyboardButton("⚡ Kích Hoạt Key", callback_data="nav_activate")
    )
    markup.add(
        InlineKeyboardButton("🎁 Nhận Giftcode", callback_data="nav_giftcode"),
        InlineKeyboardButton("💎 Nạp Tiền Ví", callback_data="nav_deposit")
    )
    markup.add(
        InlineKeyboardButton("📝 Lịch Sử Giao Dịch", callback_data="nav_history"),
        InlineKeyboardButton("📝 Đóng Góp", callback_data="nav_feedback")
    )
    markup.add(
        InlineKeyboardButton("📢 Kênh Thông Tin", url=CHANNEL_LINK),
        InlineKeyboardButton("💬 Nhóm Chat", url=GROUP_LINK)
    )
    if str(user_id) == str(ADMIN_ID):
        markup.add(InlineKeyboardButton("👑⚙️ Quản Trị Admin", callback_data="nav_admin"))
    return markup

def kb_back_inline():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🏠 Quay Lại Menu Chính", callback_data="nav_main"))
    return markup

def kb_buy_key_inline():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("⚡ 1 Ngày - 40k", callback_data="buy_pkg_1"),
        InlineKeyboardButton("🔥 3 Ngày - 90k", callback_data="buy_pkg_3"),
        InlineKeyboardButton("🌟 1 Tuần - 130k", callback_data="buy_pkg_7"),
        InlineKeyboardButton("💎 1 Tháng - 170k", callback_data="buy_pkg_30"),
        InlineKeyboardButton("👑 1 Năm - 250k", callback_data="buy_pkg_365"),
        InlineKeyboardButton("🏆 Vĩnh Viễn - 300k", callback_data="buy_pkg_9999")
    )
    markup.add(InlineKeyboardButton("🏠 Quay Lại Menu Chính", callback_data="nav_main"))
    return markup

def kb_deposit_inline():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💵 50.000đ", callback_data="dep_amt_50000"),
        InlineKeyboardButton("💵 100.000đ", callback_data="dep_amt_100000"),
        InlineKeyboardButton("💵 200.000đ", callback_data="dep_amt_200000"),
        InlineKeyboardButton("💵 500.000đ", callback_data="dep_amt_500000"),
        InlineKeyboardButton("💵 1.000.000đ", callback_data="dep_amt_1000000"),
        InlineKeyboardButton("✍️ Nhập Số Tiền Khác", callback_data="dep_amt_custom")
    )
    markup.add(InlineKeyboardButton("🏠 Quay Lại Menu Chính", callback_data="nav_main"))
    return markup

def kb_admin_inline():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🔑 Tạo Key VIP", callback_data="adm_create_key"),
        InlineKeyboardButton("💰 Cộng/Trừ Tiền", callback_data="adm_change_bal"),
        InlineKeyboardButton("🎁 Tạo Giftcode", callback_data="adm_create_giftcode"),
        InlineKeyboardButton("📢 Gửi Thông Báo", callback_data="adm_broadcast"),
        InlineKeyboardButton("🔒 Khóa User", callback_data="adm_block_user"),
        InlineKeyboardButton("🔓 Mở Khóa User", callback_data="adm_unblock_user"),
        InlineKeyboardButton("🔍 Xem Hồ Sơ User", callback_data="adm_view_user"),
        InlineKeyboardButton("🔄 Reset Thuật Toán", callback_data="adm_reset_algo")
    )
    markup.add(InlineKeyboardButton("🏠 Quay Lại Menu Chính", callback_data="nav_main"))
    return markup

def render_main_text(user_id, name):
    u_info = get_user(user_id)
    status_key = "🔴 Chưa kích hoạt"
    if check_active_key(user_id):
        if str(user_id) == str(ADMIN_ID) and not u_info.get("key_expiry"):
            status_key = "🟢 Admin (Vĩnh viễn)"
        else:
            exp = datetime.fromisoformat(u_info["key_expiry"]).strftime("%d/%m/%Y %H:%M:%S")
            status_key = f"🟢 Đã kích hoạt (Hạn: {exp})"

    msg = f"🤖 <b>THÀNH NHÂN ADM {ADMIN_CONTACT}</b> 🤖\n"
    msg += f"⚡ <b>SOI CẦU & AUTO BET TÀI XỈU</b> ⚡\n"
    msg += f"═══════════════════\n\n"
    msg += f"👋 Xin chào, <b>{name}</b>!\n"
    msg += f"🆔 ID: <code>{user_id}</code>\n"
    msg += f"💳 Số dư ví: <b>{u_info['balance']:,}đ</b>\n"
    msg += f"🔴 KEY VIP: {status_key}\n"
    msg += f"👥 Tổng người dùng: <b>{len(db['users'])} người</b>\n\n"
    msg += f"🤖 <b>CÁC LỆNH LÊN TOOL:</b>\n"
    msg += f"👉 <code>/logintx tk mk</code> | <code>/loginmd5 tk mk</code>\n"
    msg += f"👉 <code>/autobettx on 10000</code> | <code>/autobetmd5 on 10000</code>\n"
    msg += f"👉 <code>/stop</code> | <code>/help</code>\n\n"
    msg += f"👇 <b>Chọn chức năng bên dưới:</b>\n"
    msg += get_footer()
    return msg

# ==========================================
# BOT HANDLERS
# ==========================================

@bot.callback_query_handler(func=lambda call: call.data == "verify_join")
def handle_verify_join(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    if str(user_id) not in db.get("joined_users", []):
        db.setdefault("joined_users", []).append(str(user_id))
        save_db()
    
    bot.edit_message_text(
        "✅ <b>XÁC NHẬN THÀNH CÔNG!</b>\n"
        "Chào mừng bạn đến với hệ thống! 🎉\n\n"
        "📌 LƯU Ý: Vui lòng tham gia kênh/nhóm để nhận thông báo mới nhất.",
        chat_id=chat_id, 
        message_id=call.message.message_id
    )
    bot.send_message(chat_id, render_main_text(user_id, call.from_user.first_name),
                    reply_markup=kb_main_inline(user_id))

@bot.message_handler(commands=['logintx'])
@require_joined
@require_vip
def handle_login_tx(message):
    parts = message.text.split()
    if len(parts) != 3: 
        return bot.reply_to(message, "👉 Cú pháp: <code>/logintx tài_khoản mật_khẩu</code>", parse_mode="HTML")
    
    msg_proc = bot.reply_to(message, "🔄 <b>ĐANG KẾT NỐI BÀN THƯỜNG…</b>", parse_mode="HTML")
    result = login_and_get_token(parts[1], parts[2])
    
    if "_error" in result: 
        return bot.edit_message_text(f"❌ <b>LỖI:</b> {result['_error']}", chat_id=message.chat.id, message_id=msg_proc.message_id, parse_mode="HTML")
    
    init_user_state(message.chat.id)
    user_states[message.chat.id]["balance"] = result['money']
    
    bot.edit_message_text(
        f"🎉 <b>ĐĂNG NHẬP BÀN THƯỜNG THÀNH CÔNG</b>\n"
        f"👤 <code>{result['nickname']}</code>\n💰 <code>{result['money']:,}đ</code>", 
        chat_id=message.chat.id, message_id=msg_proc.message_id, parse_mode="HTML"
    )
    threading.Thread(target=start_websocket, args=(message.chat.id, result['token']), daemon=True).start()

@bot.message_handler(commands=['loginmd5'])
@require_joined
@require_vip
def handle_login_md5(message):
    parts = message.text.split()
    if len(parts) != 3: 
        return bot.reply_to(message, "👉 Cú pháp: <code>/loginmd5 tài_khoản mật_khẩu</code>", parse_mode="HTML")
    
    msg_proc = bot.reply_to(message, "🔄 <b>ĐANG KẾT NỐI BÀN MD5…</b>", parse_mode="HTML")
    result = login_and_get_token(parts[1], parts[2])
    
    if "_error" in result: 
        return bot.edit_message_text(f"❌ <b>LỖI:</b> {result['_error']}", chat_id=message.chat.id, message_id=msg_proc.message_id, parse_mode="HTML")
    
    init_user_state_md5(message.chat.id)
    user_states_md5[message.chat.id]["balance"] = result['money']
    
    bot.edit_message_text(
        f"🎉 <b>ĐĂNG NHẬP BÀN MD5 THÀNH CÔNG</b>\n"
        f"👤 <code>{result['nickname']}</code>\n💰 <code>{result['money']:,}đ</code>", 
        chat_id=message.chat.id, message_id=msg_proc.message_id, parse_mode="HTML"
    )
    threading.Thread(target=start_websocket_md5, args=(message.chat.id, result['token']), daemon=True).start()

@bot.message_handler(commands=['autobettx'])
@require_joined
@require_vip
def handle_autobet_tx(message):
    parts = message.text.split()
    if message.chat.id not in user_states:
        return bot.reply_to(message, "⚠️ Vui lòng /logintx trước!")
    
    state = user_states[message.chat.id]
    if len(parts) > 1 and parts[1].lower() == "on":
        amount = int(parts[2]) if len(parts) > 2 else 10000
        state["auto_bet_enabled"] = True
        state["base_bet_amount"] = amount
        state["current_bet"] = amount
        bot.reply_to(message, f"✅ <b>AUTO BET TX: BẬT</b>\n💸 <code>{amount:,}đ</code>", parse_mode="HTML")
    else:
        state["auto_bet_enabled"] = False
        bot.reply_to(message, "🔴 <b>AUTO BET TX: TẮT</b>", parse_mode="HTML")

@bot.message_handler(commands=['autobetmd5'])
@require_joined
@require_vip
def handle_autobet_md5(message):
    parts = message.text.split()
    if message.chat.id not in user_states_md5:
        return bot.reply_to(message, "⚠️ Vui lòng /loginmd5 trước!")
    
    state = user_states_md5[message.chat.id]
    if len(parts) > 1 and parts[1].lower() == "on":
        amount = int(parts[2]) if len(parts) > 2 else 10000
        state["auto_bet_enabled"] = True
        state["base_bet_amount"] = amount
        state["current_bet"] = amount
        bot.reply_to(message, f"✅ <b>AUTO BET MD5: BẬT</b>\n💸 <code>{amount:,}đ</code>", parse_mode="HTML")
    else:
        state["auto_bet_enabled"] = False
        bot.reply_to(message, "🔴 <b>AUTO BET MD5: TẮT</b>", parse_mode="HTML")

@bot.message_handler(commands=['x2'])
@require_joined
@require_vip
def handle_x2(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id) or user_states_md5.get(chat_id)
    if not state:
        return bot.reply_to(message, "⚠️ Vui lòng đăng nhập trước!")
    parts = message.text.split()
    state["x2_mode"] = (len(parts) > 1 and parts[1].lower() == "on")
    bot.reply_to(message, f"🔥 X2: {'🟢 BẬT' if state['x2_mode'] else '🔴 TẮT'}", parse_mode="HTML")

@bot.message_handler(commands=['chotlai'])
@require_joined
@require_vip
def handle_chotlai(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id) or user_states_md5.get(chat_id)
    if not state:
        return bot.reply_to(message, "⚠️ Vui lòng đăng nhập trước!")
    try:
        state["target_profit"] = int(message.text.split()[1])
        bot.reply_to(message, f"🎯 MỤC TIÊU: <code>{state['target_profit']:,}đ</code>", parse_mode="HTML")
    except:
        bot.reply_to(message, "👉 /chotlai [số_tiền]", parse_mode="HTML")

@bot.message_handler(commands=['dudoan'])
@require_joined
@require_vip
def handle_dudoan(message):
    state = user_states.get(message.chat.id) or user_states_md5.get(message.chat.id)
    if not state:
        return bot.reply_to(message, "⚠️ Vui lòng đăng nhập trước!")
    pred = state.get("current_prediction")
    if not pred:
        return bot.reply_to(message, "⏳ AI chưa đủ dữ liệu (Cần 3 phiên)", parse_mode="HTML")
    bot.reply_to(message, f"🎯 DỰ ĐOÁN: <b>{pred}</b>", parse_mode="HTML")

@bot.message_handler(commands=['lichsu'])
@require_joined
@require_vip
def handle_lichsu(message):
    state = user_states.get(message.chat.id) or user_states_md5.get(message.chat.id)
    if not state:
        return bot.reply_to(message, "⚠️ Vui lòng đăng nhập trước!")
    history = state.get("history_15", [])
    msg = "📜 <b>LỊCH SỬ CƯỢC:</b>\n" + ("\n".join(history) if history else "Chưa có dữ liệu.")
    bot.reply_to(message, msg, parse_mode="HTML")

@bot.message_handler(commands=['stats'])
@require_joined
@require_vip
def check_stats(message):
    state = user_states.get(message.chat.id) or user_states_md5.get(message.chat.id)
    if not state:
        return bot.reply_to(message, "⚠️ Chưa có dữ liệu!", parse_mode="HTML")
    pl_sign = "+" if state.get("profit_loss", 0) >= 0 else ""
    bot.reply_to(message, f"📊 Lãi/Lỗ: <code>{pl_sign}{state.get('profit_loss', 0):,}đ</code>\n🔥 Chuỗi thắng: {state.get('win_streak', 0)} tay", parse_mode="HTML")

@bot.message_handler(commands=['thongke'])
@require_joined
@require_vip
def full_stats(message):
    g = GLOBAL_STATS
    total = g["total_win"] + g["total_lose"]
    acc = round((g["total_win"]/total*100),1) if total>0 else 0.0
    bot.reply_to(message, f"📈 <b>THỐNG KÊ TỔNG</b>\n✅ Thắng: {g['total_win']} | ❌ Thua: {g['total_lose']}\n🎯 Tỷ lệ: {acc}%", parse_mode="HTML")

@bot.message_handler(commands=['stop'])
@require_joined
@require_vip
def stop_websocket(message):
    chat_id = message.chat.id
    stopped = False
    if chat_id in active_sockets:
        try: active_sockets[chat_id].disconnect(); del active_sockets[chat_id]; stopped = True
        except: pass
    if chat_id in active_sockets_md5:
        try: active_sockets_md5[chat_id].disconnect(); del active_sockets_md5[chat_id]; stopped = True
        except: pass
    bot.reply_to(message, "🔌 <b>ĐÃ NGẮT KẾT NỐI</b>" if stopped else "⚠️ Không có kết nối nào!", parse_mode="HTML")

@bot.message_handler(commands=['help'])
def send_help(message):
    if check_and_block(message): return
    help_text = (
        "🤖 <b>HƯỚNG DẪN SỬ DỤNG</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔹 <code>/logintx tk mk</code> - Đăng nhập bàn Thường\n"
        "🔹 <code>/loginmd5 tk mk</code> - Đăng nhập bàn MD5\n"
        "🔹 <code>/autobettx on [số_tiền]</code> - Bật Auto Bet TX\n"
        "🔹 <code>/autobetmd5 on [số_tiền]</code> - Bật Auto Bet MD5\n"
        "🔹 <code>/x2 on/off</code> - Nhồi X2\n"
        "🔹 <code>/chotlai [số_tiền]</code> - Chốt lãi\n"
        "🔹 <code>/stop</code> - Ngắt kết nối\n"
        "🔹 <code>/taocode [Mã] [Số_tiền]</code> - Tạo Giftcode\n\n"
        "💳 <b>NẠP TIỀN TỰ ĐỘNG:</b>\n"
        f"🏦 {BANK_BIN} - {BANK_ACC} - {BANK_NAME}\n"
        "📝 Nội dung: <code>NAP [ID]</code> (VD: NAP 8375848425)\n"
        "✅ Bot tự động kiểm tra và duyệt trong 20-30 giây!\n\n"
        f"💬 Hỗ trợ: {ADMIN_CONTACT}"
    )
    bot.reply_to(message, help_text, parse_mode="HTML")

@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    if check_and_block(message): return
    
    if not check_user_joined(message.from_user.id):
        msg = (
            "🔔 <b>YÊU CẦU BẤT BUỘC</b>\n"
            "Để sử dụng bot, vui lòng tham gia đầy đủ các kênh và nhóm bên dưới.\n"
            "Nhấn nút <b>Xác Nhận Join</b> sau khi đã hoàn tất."
        )
        bot.send_message(message.chat.id, msg, reply_markup=kb_verify_join())
        return
    
    init_user_state(message.chat.id)
    init_user_state_md5(message.chat.id)
    bot.send_message(message.chat.id, render_main_text(message.from_user.id, message.from_user.first_name),
                    reply_markup=kb_main_inline(message.from_user.id))

# ==========================================
# CALLBACK HANDLERS
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    if check_and_block(call): return
    
    if call.data != "verify_join" and not check_user_joined(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Vui lòng tham gia kênh/nhóm trước!", show_alert=True)
        return
    
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    # ADMIN
    if call.data.startswith('adm_'):
        if str(user_id) != str(ADMIN_ID):
            return bot.answer_callback_query(call.id, "❌ Không có quyền!", show_alert=True)
        
        if call.data == "adm_reset_algo":
            db["history_md5"] = []
            db["is_reversed_mode"] = False
            with history_lock:
                GLOBAL_HISTORY.clear()
            save_db()
            bot.edit_message_text("🔄 <b>ĐÃ RESET THUẬT TOÁN!</b>", chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_admin_inline())
        elif call.data == "adm_create_key":
            sent = bot.send_message(chat_id, "🔑 <b>Nhập số ngày (1,3,7,30,365,9999):</b>")
            bot.register_next_step_handler(sent, admin_step_key)
        elif call.data == "adm_change_bal":
            sent = bot.send_message(chat_id, "💰 <b>Cú pháp:</b> <code>[ID] [Số_tiền]</code>")
            bot.register_next_step_handler(sent, admin_step_bal)
        elif call.data == "adm_create_giftcode":
            sent = bot.send_message(chat_id, "🎁 <b>Cú pháp:</b> <code>[Mã] [Giá_trị] [Số_lượt]</code>")
            bot.register_next_step_handler(sent, admin_step_create_giftcode)
        elif call.data == "adm_broadcast":
            sent = bot.send_message(chat_id, "📢 <b>Nhập nội dung thông báo:</b>")
            bot.register_next_step_handler(sent, admin_step_broadcast)
        elif call.data == "adm_block_user":
            sent = bot.send_message(chat_id, "🔒 <b>Nhập ID user muốn KHÓA:</b>")
            bot.register_next_step_handler(sent, admin_step_block_user)
        elif call.data == "adm_unblock_user":
            sent = bot.send_message(chat_id, "🔓 <b>Nhập ID user muốn MỞ KHÓA:</b>")
            bot.register_next_step_handler(sent, admin_step_unblock_user)
        elif call.data == "adm_view_user":
            sent = bot.send_message(chat_id, "🔍 <b>Nhập ID user:</b>")
            bot.register_next_step_handler(sent, admin_step_view_user)
        return

    # NAVIGATION
    if call.data == "nav_main":
        bot.edit_message_text(render_main_text(user_id, call.from_user.first_name), chat_id=chat_id,
                            message_id=call.message.message_id, reply_markup=kb_main_inline(user_id))
    elif call.data == "nav_game":
        bot.edit_message_text("🎮 <b>BÀN TÀI XỈU THƯỜNG</b>\n📌 HŨ: 111 (Xỉu) - 666 (Tài)\n🔹 /logintx tk mk", 
                            chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_back_inline())
    elif call.data == "nav_game_md5":
        bot.edit_message_text("🎲 <b>BÀN TÀI XỈU MD5</b>\n🔹 /loginmd5 tk mk\n🔹 Gửi MD5 (32 ký tự) để soi cầu", 
                            chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_back_inline())
    elif call.data == "nav_profile":
        u_info = get_user(user_id)
        exp_str = u_info.get("key_expiry", "N/A")
        msg = f"💼 <b>HỒ SƠ</b>\n🆔 <code>{user_id}</code>\n💎 <b>{u_info['balance']:,}đ</b>\n⏳ Hạn Key: {exp_str}\n" + get_footer()
        bot.edit_message_text(msg, chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_back_inline())
    elif call.data == "nav_buy_key":
        key_info_text = (
            "🔥 <b>BẢNG GIÁ KEY VIP MỚI</b>\n\n"
            "⚡ 1 Ngày: 40.000đ\n"
            "🔥 3 Ngày: 90.000đ\n"
            "🌟 1 Tuần: 130.000đ\n"
            "💎 1 Tháng: 170.000đ\n"
            "👑 1 Năm: 250.000đ\n"
            "🏆 Vĩnh Viễn: 300.000đ\n\n"
            "👇 Chọn gói:"
        )
        bot.edit_message_text(key_info_text, chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_buy_key_inline())
    elif call.data.startswith("buy_pkg_"):
        days = int(call.data.split("_")[2])
        price = KEY_PRICES.get(days, 0)
        u_info = get_user(user_id)
        if u_info["balance"] >= price:
            update_user(user_id, balance=u_info["balance"] - price)
            cur = datetime.now()
            if u_info.get("key_expiry"):
                try:
                    exp = datetime.fromisoformat(u_info["key_expiry"])
                    if exp > cur: cur = exp
                except: pass
            update_user(user_id, key_expiry=(cur + timedelta(days=days)).isoformat())
            label_days = "VĨNH VIỄN" if days >= 9999 else f"+{days} ngày"
            bot.edit_message_text(f"🎉 <b>MUA KEY THÀNH CÔNG!</b>\nĐã gia hạn {label_days} VIP.", chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_back_inline())
        else:
            bot.edit_message_text(f"❌ <b>SỐ DƯ KHÔNG ĐỦ!</b>\nCần: {price:,}đ | Có: {u_info['balance']:,}đ", chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_deposit_inline())
    elif call.data == "nav_deposit":
        bot.edit_message_text(
            "💎 <b>NẠP TIỀN VÀO VÍ</b>\n"
            f"🏦 <b>Ngân hàng:</b> {BANK_BIN}\n"
            f"📍 <b>Số TK:</b> <code>{BANK_ACC}</code>\n"
            f"👤 <b>Chủ TK:</b> {BANK_NAME}\n\n"
            "📌 <b>LƯU Ý:</b> Bot sẽ tự động kiểm tra và duyệt nạp tiền!\n"
            "💡 Gửi chuyển khoản với nội dung: <code>NAP [ID]</code>\n"
            "Ví dụ: <code>NAP 8375848425</code>\n\n"
            "⏱ Bot kiểm tra mỗi 20 giây, tự động cộng tiền!\n"
            "👇 Chọn hạn mức nạp bên dưới hoặc chuyển khoản trực tiếp:",
            chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_deposit_inline()
        )
    elif call.data == "dep_amt_custom":
        sent = bot.send_message(chat_id, "✍️ <b>Nhập số tiền bạn muốn nạp (VNĐ):</b>\n"
                                  "Ví dụ: <code>150000</code>")
        bot.register_next_step_handler(sent, process_custom_deposit)
    elif call.data.startswith("dep_amt_"):
        val = call.data.split("_")[2]
        amount = int(val)
        
        # Tạo nội dung chuyển khoản
        content = f"NAP {user_id}"
        
        msg = f"💎 <b>NẠP TIỀN</b>\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"🏦 <b>Ngân hàng:</b> {BANK_BIN}\n"
        msg += f"📍 <b>Số TK:</b> <code>{BANK_ACC}</code>\n"
        msg += f"👤 <b>Chủ TK:</b> {BANK_NAME}\n"
        msg += f"💰 <b>Số tiền:</b> <code>{amount:,}đ</code>\n"
        msg += f"📝 <b>Nội dung:</b> <code>{content}</code>\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"✅ Sau khi chuyển khoản, bot sẽ tự động duyệt trong 20-30 giây!\n"
        msg += f"📌 Quét mã QR bên dưới để chuyển khoản nhanh:"
        
        bot.send_photo(chat_id, QR_CODE_URL, caption=msg, reply_markup=kb_back_inline())
    
    elif call.data == "nav_history":
        # Lịch sử giao dịch
        user_id_str = str(user_id)
        history = db.get("transaction_history", {}).get(user_id_str, [])
        
        if not history:
            msg = "📭 <b>Bạn chưa có giao dịch nào!</b>"
        else:
            msg = "📜 <b>LỊCH SỬ GIAO DỊCH</b>\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            # Lấy 20 giao dịch gần nhất
            recent = history[-20:][::-1]
            for trans in recent:
                trans_type = "💰 Nạp tiền" if trans.get("type") == "deposit" else "💸 Rút tiền"
                amount = trans.get("amount", 0)
                balance = trans.get("balance", 0)
                time_str = datetime.fromisoformat(trans.get("time")).strftime("%d/%m/%Y %H:%M")
                
                sign = "+" if trans.get("type") == "deposit" else "-"
                msg += f"🕐 <b>{time_str}</b>\n"
                msg += f"📌 {trans_type}: <code>{sign}{amount:,}đ</code>\n"
                msg += f"💳 Số dư: <code>{balance:,}đ</code>\n"
                msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            
            msg += f"\n📊 <b>Tổng số giao dịch:</b> {len(history)}"
        
        bot.edit_message_text(msg, chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_back_inline())
    
    elif call.data == "nav_stats":
        history = db.get("history_md5", [])
        if not history:
            msg = "📊 <b>Chưa có dữ liệu MD5!</b>"
        else:
            recent = history[-50:]
            cor = sum(1 for i in recent if i["is_correct"])
            rate = round(cor/len(recent)*100,1) if recent else 0
            msg = f"📊 <b>50 PHIÊN MD5 GẦN NHẤT</b>\n🎯 Chuẩn xác: {cor}/{len(recent)} ({rate}%)\n━━━━━━━━━━━━━━━━━━━\n"
            for item in reversed(recent):
                icon = "✅" if item["is_correct"] else "❌"
                msg += f"👉 <code>{item['md5'][:4]}...{item['md5'][-4:]}</code> | AI: <b>{item['predict']}</b> | TT: <b>{item['actual']}</b> {icon}\n"
        g = GLOBAL_STATS
        total = g["total_win"] + g["total_lose"]
        acc = round((g["total_win"]/total*100),1) if total>0 else 0.0
        msg += f"\n📈 <b>BÀN THƯỜNG</b>\n✅ {g['total_win']} | ❌ {g['total_lose']} | 🎯 {acc}%"
        bot.edit_message_text(msg, chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_back_inline())
    elif call.data == "nav_activate":
        sent = bot.send_message(chat_id, "⚡ <b>Nhập mã Key VIP:</b>")
        bot.register_next_step_handler(sent, process_input_key)
    elif call.data == "nav_giftcode":
        sent = bot.send_message(chat_id, "🎁 <b>Nhập mã Giftcode:</b>")
        bot.register_next_step_handler(sent, process_input_giftcode)
    elif call.data == "nav_feedback":
        sent = bot.send_message(chat_id, "📝 <b>Nhập ý kiến đóng góp:</b>")
        bot.register_next_step_handler(sent, process_input_feedback)
    elif call.data == "nav_admin":
        if str(user_id) == str(ADMIN_ID):
            bot.edit_message_text("👑 <b>QUẢN TRỊ ADMIN</b>", chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_admin_inline())

# ==========================================
# PROCESS CUSTOM DEPOSIT
# ==========================================
def process_custom_deposit(message):
    """Xử lý nhập số tiền nạp tùy chỉnh"""
    try:
        amount = int(message.text.replace(",", "").replace(".", ""))
        if amount < 10000:
            return bot.send_message(message.chat.id, "❌ Số tiền nạp tối thiểu là <b>10.000đ</b>!", parse_mode="HTML")
        
        user_id = message.from_user.id
        
        # Tạo nội dung chuyển khoản
        content = f"NAP {user_id}"
        
        msg = f"💎 <b>NẠP TIỀN</b>\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"🏦 <b>Ngân hàng:</b> {BANK_BIN}\n"
        msg += f"📍 <b>Số TK:</b> <code>{BANK_ACC}</code>\n"
        msg += f"👤 <b>Chủ TK:</b> {BANK_NAME}\n"
        msg += f"💰 <b>Số tiền:</b> <code>{amount:,}đ</code>\n"
        msg += f"📝 <b>Nội dung:</b> <code>{content}</code>\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"✅ Sau khi chuyển khoản, bot sẽ tự động duyệt trong 20-30 giây!\n"
        msg += f"📌 Quét mã QR bên dưới để chuyển khoản nhanh:"
        
        bot.send_photo(message.chat.id, QR_CODE_URL, caption=msg, reply_markup=kb_back_inline())
        
    except ValueError:
        bot.send_message(message.chat.id, "❌ Vui lòng nhập số tiền hợp lệ!\nVí dụ: <code>150000</code>", parse_mode="HTML")

# ==========================================
# ADMIN STEP FUNCTIONS
# ==========================================
def admin_step_key(message):
    if str(message.from_user.id) != str(ADMIN_ID): return
    try:
        days = int(message.text.strip())
        key_code = "VIP-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        db.setdefault("keys", {})[key_code] = days
        save_db()
        label = "Vĩnh Viễn" if days >= 9999 else f"{days} ngày"
        bot.send_message(message.chat.id, f"✅ <b>TẠO KEY:</b> <code>{key_code}</code>\n⏳ {label}", reply_markup=kb_admin_inline())
    except:
        bot.send_message(message.chat.id, "❌ Nhập số ngày!", reply_markup=kb_admin_inline())

def admin_step_bal(message):
    if str(message.from_user.id) != str(ADMIN_ID): return
    try:
        parts = message.text.strip().split()
        uid, amt = parts[0], int(parts[1])
        user = get_user(uid)
        new_bal = user['balance'] + amt
        update_user(uid, balance=new_bal)
        
        # Lưu lịch sử giao dịch
        db.setdefault("transaction_history", {}).setdefault(uid, [])
        db["transaction_history"][uid].append({
            "type": "admin_deposit" if amt > 0 else "admin_withdraw",
            "amount": amt,
            "balance": new_bal,
            "admin_id": str(message.from_user.id),
            "time": datetime.now().isoformat()
        })
        save_db()
        
        bot.send_message(message.chat.id, f"✅ ID <code>{uid}</code> → <b>{new_bal:,}đ</b>", reply_markup=kb_admin_inline())
    except:
        bot.send_message(message.chat.id, "❌ Sai cú pháp!", reply_markup=kb_admin_inline())

def admin_step_create_giftcode(message):
    if str(message.from_user.id) != str(ADMIN_ID): return
    try:
        parts = message.text.strip().split()
        code, val, usages = parts[0].upper(), int(parts[1]), int(parts[2])
        db.setdefault("giftcodes", {})[code] = {"value": val, "usages": usages, "used_by": []}
        save_db()
        bot.send_message(message.chat.id, f"🎁 <b>TẠO GIFTCODE:</b> <code>{code}</code>\n💰 {val:,}đ | 🔢 {usages} lượt", reply_markup=kb_admin_inline())
    except:
        bot.send_message(message.chat.id, "❌ Sai cú pháp!", reply_markup=kb_admin_inline())

def admin_step_broadcast(message):
    if str(message.from_user.id) != str(ADMIN_ID): return
    text = message.text.strip()
    users = db.get("users", {})
    success = 0
    for uid in list(users.keys()):
        try:
            bot.send_message(uid, f"📢 <b>THÔNG BÁO</b>\n{text}\n\n{get_footer()}")
            success += 1
            time.sleep(0.05)
        except: pass
    bot.send_message(message.chat.id, f"✅ Đã gửi tới {success} user!", reply_markup=kb_admin_inline())

def admin_step_block_user(message):
    if str(message.from_user.id) != str(ADMIN_ID): return
    uid = message.text.strip()
    if uid in db.get("users", {}):
        update_user(uid, is_blocked=True)
        bot.send_message(message.chat.id, f"🔒 Đã KHÓA ID <code>{uid}</code>", reply_markup=kb_admin_inline())
    else:
        bot.send_message(message.chat.id, f"❌ Không tìm thấy ID", reply_markup=kb_admin_inline())

def admin_step_unblock_user(message):
    if str(message.from_user.id) != str(ADMIN_ID): return
    uid = message.text.strip()
    if uid in db.get("users", {}):
        update_user(uid, is_blocked=False)
        bot.send_message(message.chat.id, f"🔓 Đã MỞ KHÓA ID <code>{uid}</code>", reply_markup=kb_admin_inline())
    else:
        bot.send_message(message.chat.id, f"❌ Không tìm thấy ID", reply_markup=kb_admin_inline())

def admin_step_view_user(message):
    if str(message.from_user.id) != str(ADMIN_ID): return
    uid = message.text.strip()
    if uid in db.get("users", {}):
        u = db["users"][uid]
        msg = f"🔍 <b>HỒ SƠ #{uid}</b>\n"
        msg += f"💳 <b>{u.get('balance', 0):,}đ</b>\n"
        msg += f"🛡 {'🔴 Bị khóa' if u.get('is_blocked') else '🟢 Hoạt động'}\n"
        msg += f"⏳ Hạn Key: {u.get('key_expiry', 'Chưa có')}"
        bot.send_message(message.chat.id, msg, reply_markup=kb_admin_inline())
    else:
        bot.send_message(message.chat.id, f"❌ Không tìm thấy ID", reply_markup=kb_admin_inline())

# ==========================================
# USER INPUT PROCESSING
# ==========================================
def process_input_key(message):
    key_code = message.text.strip()
    keys = db.get("keys", {})
    if key_code in keys:
        days = keys[key_code]
        user = get_user(message.chat.id)
        cur = datetime.now()
        if user.get("key_expiry"):
            try:
                exp = datetime.fromisoformat(user["key_expiry"])
                if exp > cur: cur = exp
            except: pass
        update_user(message.chat.id, key_expiry=(cur + timedelta(days=days)).isoformat())
        del db["keys"][key_code]
        save_db()
        label = "VĨNH VIỄN" if days >= 9999 else f"{days} ngày"
        bot.send_message(message.chat.id, f"🎉 <b>KÍCH HOẠT THÀNH CÔNG!</b>\n+{label} VIP.", reply_markup=kb_main_inline(message.chat.id))
    else:
        bot.send_message(message.chat.id, "❌ <b>Mã Key không hợp lệ!</b>", reply_markup=kb_main_inline(message.chat.id))

def process_input_giftcode(message):
    code = message.text.strip().upper()
    if code in db.get("giftcodes", {}):
        gc = db["giftcodes"][code]
        if str(message.chat.id) in gc.get("used_by", []):
            return bot.send_message(message.chat.id, "❌ Bạn đã dùng mã này!", reply_markup=kb_main_inline(message.chat.id))
        user = get_user(message.chat.id)
        update_user(message.chat.id, balance=user["balance"] + gc["value"])
        gc.setdefault("used_by", []).append(str(message.chat.id))
        gc["usages"] -= 1
        if gc["usages"] <= 0: del db["giftcodes"][code]
        save_db()
        bot.send_message(message.chat.id, f"🎉 Nhận +{gc['value']:,}đ!", reply_markup=kb_main_inline(message.chat.id))
    else:
        bot.send_message(message.chat.id, "❌ Mã không tồn tại!", reply_markup=kb_main_inline(message.chat.id))

def process_input_feedback(message):
    fb_id = str(random.randint(100000, 999999))
    db.setdefault("pending_feedbacks", {})[fb_id] = {"uid": str(message.chat.id), "content": message.text}
    save_db()
    bot.send_message(message.chat.id, "✅ Cảm ơn đóng góp!", reply_markup=kb_main_inline(message.chat.id))

# ==========================================
# MD5 HANDLER
# ==========================================
@bot.message_handler(func=lambda msg: len(msg.text.strip()) == 32 and all(c in string.hexdigits for c in msg.text.strip()))
def handle_md5_code(message):
    if check_and_block(message): return
    
    if not check_user_joined(message.from_user.id):
        msg = "🔔 <b>YÊU CẦU BẤT BUỘC</b>\nVui lòng tham gia kênh/nhóm trước khi sử dụng!"
        bot.send_message(message.chat.id, msg, reply_markup=kb_verify_join())
        return
    
    if not is_vip(message.chat.id):
        return bot.reply_to(message, "⛔ <b>CẦN KEY VIP!</b>", parse_mode="HTML")
    
    md5_code = message.text.strip()
    res = analyze_ai_deep(md5_code)
    out = f"TÀI: {res['tai_percent']}% | XỈU: {res['xiu_percent']}%\n🔊 Kết quả: <b>{res['result']}</b>"
    if res["is_reversed"]:
        out += "\n<i>(Đang đảo cầu)</i>"
    bot.reply_to(message, out, parse_mode="HTML")

# ==========================================
# KHỞI CHẠY (CHO BOT.PY)
# ==========================================
if __name__ == '__main__':
    print("==================================================")
    print("🤖 THÀNH NHÂN ADM @nhan161019 BOT IS ONLINE!")
    print("🎯 BÀN TÀI XỈU THƯỜNG + MD5")
    print("💳 TỰ ĐỘNG NẠP TIỀN QUA WEBHOOK THUEAPI")
    print("📜 LỊCH SỬ GIAO DỊCH")
    print("📢 YÊU CẦU THAM GIA KÊNH/NHÓM (BẮT BUỘC)")
    print("==================================================")
    
    # Xóa webhook cũ để tránh conflict
    try:
        bot.remove_webhook()
        print("✅ Đã xóa webhook cũ")
    except Exception as e:
        print(f"⚠️ Không xóa được webhook: {e}")
    
    # Chạy polling
    try:
        print("🤖 Bắt đầu polling...")
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"❌ Lỗi polling: {e}")
