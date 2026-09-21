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
import urllib3

urllib3.disable_warnings()

# ==========================================
# CẤU HÌNH HỆ THỐNG
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger('engineio').setLevel(logging.WARNING)
logging.getLogger('socketio').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

BOT_TOKEN = '8545966200:AAFWHF2rZppjoMX27bGichmeaRgoqUWCzds'
ADMIN_ID = 8375848425
ADMIN_CONTACT = '@nhan161019'
BOT_USERNAME = '@taixiuvipallgame_bot'

# KÊNH / NHÓM
REQUIRED_CHANNELS = [
    {"name": "📢 Kênh Thông Tin", "url": "https://t.me/thongbaotoolgamevip"},
    {"name": "💬 Nhóm Chat", "url": "https://t.me/nhomgiaolmd5"},
]
CHANNEL_LINK = 'https://t.me/thongbaotoolgamevip'
GROUP_LINK = 'https://t.me/nhomgiaolmd5'

DATA_COLLECTOR_USER = "acc_clone_soi_cau"
DATA_COLLECTOR_PASS = "matkhau123"

# ==========================================
# ENDPOINT API
# ==========================================
BETVIP_API_HU = "https://betvip2x.hacksieucap.pro/huddd"
BETVIP_API_MD5 = "https://betvip2x.hacksieucap.pro/md5dd"

RENDER_API_URL = "https://cocailon-8a8a.onrender.com/api/data"
RENDER_GAMES = {
    "SUNWIN": 1,
    "LC79-MD5": 2,
    "MAX789": 3,
    "HITCLUB": 4,
    "68GB": 5,
    "SUMCLUB": 6,
    "RIKVIP": 7,
    "SICSUN": 8,
    "LC79-HU": 9
}

# ==========================================
# CẤU HÌNH BANK & QR (DUYỆT TAY)
# ==========================================
BANK_BIN = 'BIDV'
BANK_ACC = '8887596710'
BANK_NAME = 'NGUYEN THANH NHAN'

def generate_qr_url(amount, memo):
    return f"https://img.vietqr.io/image/{BANK_BIN}-{BANK_ACC}-compact.png?amount={amount}&addInfo={memo}&accountName={BANK_NAME.replace(' ', '%20')}"

# ==========================================
# KHỞI TẠO BOT & DATABASE
# ==========================================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')
DB_FILE = 'database.json'

KEY_PRICES = {
    1: 40000,      # 1 Ngày
    3: 70000,      # 3 Ngày
    7: 110000,     # 1 Tuần
    30: 220000,    # 1 Tháng
    60: 300000,    # 2 Tháng
    90: 450000     # 3 Tháng
}

def load_db():
    default = {
        "users": {}, "keys": {}, "giftcodes": {}, "pending_deposits": {}, 
        "pending_feedbacks": {}, "history_md5": [], "is_reversed_mode": False,
        "joined_users": [], "processed_trans": [], "transaction_history": {},
        "deposit_order_count": 100
    }
    if not os.path.exists(DB_FILE): 
        return default
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for k in default: 
                data.setdefault(k, default[k])
            return data
    except Exception as e:
        logger.error(f"Lỗi load DB: {e}")
        return default

def save_db(): 
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f: 
            json.dump(db, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Lỗi save DB: {e}")

def refresh_db():
    global db
    db = load_db()

db = load_db()

# ==========================================
# BIẾN TOÀN CỤC
# ==========================================
active_sockets = {}
active_sockets_md5 = {}
user_states = {}
user_states_md5 = {}
history_lock = threading.Lock()
AUTO_VIP_ENABLED = False
GLOBAL_HISTORY = []
MAX_GLOBAL_HISTORY = 2000
GLOBAL_STATS = {
    "total_win": 0, "total_lose": 0, "total_draw": 0, "total_profit": 0,
    "current_streak_win": 0, "max_streak_win": 0,
    "current_streak_lose": 0, "max_streak_lose": 0
}
SPAM_TRACKER = {}

# ==========================================
# QUẢN LÝ NGƯỜI DÙNG & BẢO MẬT
# ==========================================
def check_user_joined(user_id):
    if str(user_id) == str(ADMIN_ID):
        return True
    return str(user_id) in db.get("joined_users", [])

def require_joined(func):
    @wraps(func)
    def wrapper(message):
        user_id = message.from_user.id
        if not check_user_joined(user_id):
            msg = (
                "🔔 <b>YÊU CẦU BẮT BUỘC</b>\n"
                "Để sử dụng bot, vui lòng tham gia đầy đủ các kênh và nhóm bên dưới.\n"
                "Nhấn nút <b>Xác Nhận Join</b> sau khi hoàn tất."
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

def get_user(user_id, username="", full_name=""):
    refresh_db()
    user_id = str(user_id)
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    if user_id not in db["users"]:
        db["users"][user_id] = {
            "username": username or "",
            "full_name": full_name or f"User_{user_id}",
            "balance": 0, 
            "key_expiry": None, 
            "is_blocked": False,
            "created_at": now_str
        }
        save_db()
    else:
        # Cập nhật username/tên nếu có thay đổi
        updated = False
        if username and db["users"][user_id].get("username") != username:
            db["users"][user_id]["username"] = username
            updated = True
        if full_name and db["users"][user_id].get("full_name") != full_name:
            db["users"][user_id]["full_name"] = full_name
            updated = True
        if "created_at" not in db["users"][user_id]:
            db["users"][user_id]["created_at"] = now_str
            updated = True
        if updated:
            save_db()
            
    return db["users"][user_id]

def update_user(user_id, **kwargs):
    refresh_db()
    user = get_user(user_id)
    user.update(kwargs)
    db["users"][str(user_id)] = user
    save_db()

def check_active_key(user_id):
    if AUTO_VIP_ENABLED or str(user_id) == str(ADMIN_ID):
        return True
    refresh_db()
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

def is_user_blocked(user_id):
    if str(user_id) == str(ADMIN_ID): 
        return False
    refresh_db()
    return get_user(user_id).get("is_blocked", False)

def check_anti_spam(user_id, chat_id):
    if str(user_id) == str(ADMIN_ID): 
        return False
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
            rem = 3 - user_data["count"]
            bot.send_message(chat_id, f"⚠️ <b>CẢNH BÁO SPAM!</b> Còn {rem} lần sẽ bị KHÓA!")
            return True
    else:
        user_data["count"] = 1
        user_data["last_time"] = now
        SPAM_TRACKER[user_id] = user_data
    return False

def check_and_block(call_or_msg):
    user_id = call_or_msg.from_user.id
    chat_id = call_or_msg.message.chat.id if isinstance(call_or_msg, telebot.types.CallbackQuery) else call_or_msg.chat.id
    if is_user_blocked(user_id):
        msg = f"🚫 <b>TÀI KHOẢN BỊ KHÓA</b>\nLiên hệ {ADMIN_CONTACT}"
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
        user_states[chat_id] = {
            "profit_loss": 0, "auto_bet_enabled": False, "x2_mode": False,
            "win_streak": 0, "base_bet_amount": 10000, "current_bet": 10000,
            "target_profit": None, "current_prediction": None,
            "waiting_for_result": False, "has_bet_this_session": False,
            "session_id": None, "balance": 0, "history_15": []
        }

def init_user_state_md5(chat_id):
    if chat_id not in user_states_md5:
        user_states_md5[chat_id] = {
            "profit_loss": 0, "auto_bet_enabled": False, "x2_mode": False,
            "win_streak": 0, "base_bet_amount": 10000, "current_bet": 10000,
            "target_profit": None, "current_prediction": None,
            "waiting_for_result": False, "has_bet_this_session": False,
            "session_id": None, "balance": 0, "history_15": []
        }

def require_vip(func):
    @wraps(func)
    def wrapper(message):
        if not is_vip(message.chat.id):
            return bot.reply_to(message, "⛔ <b>BẠN CHƯA KÍCH HOẠT VIP!</b> Vui lòng mua Key để dùng chức năng.")
        return func(message)
    return wrapper

def parse_amount_str(val_str):
    """Chuyển đổi các chuỗi số như 50k, 100k, 50000 thành số nguyên."""
    s = val_str.strip().lower().replace(",", "").replace(".", "")
    if s.endswith("k"):
        try:
            return int(float(s[:-1]) * 1000)
        except:
            return None
    try:
        return int(s)
    except:
        return None

# ==========================================
# THUẬT TOÁN SOI CẦU & RENDER API
# ==========================================
def get_render_game_data(api_id):
    try:
        headers = {"Content-Type": "application/json"}
        payload = {"apiId": api_id}
        res = requests.post(RENDER_API_URL, json=payload, headers=headers, timeout=8)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        logger.error(f"Lỗi Render API (ID {api_id}): {e}")
    return None

def format_render_game_msg(game_name, api_id):
    data = get_render_game_data(api_id)
    if not data or "rows" not in data or len(data["rows"]) == 0:
        return f"❌ <b>Không lấy được dữ liệu Game {game_name}!</b>\nServer API Render hiện không phản hồi."

    rows = data["rows"]
    latest = rows[0]

    msg = f"🎮 <b>DỮ LIỆU GAME: {game_name}</b>\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    phien = latest.get("phien", "N/A")
    time_str = latest.get("time", "N/A")
    prediction = latest.get("prediction", "N/A")
    result = latest.get("result", "N/A")

    pred_emoji = "🔵 TÀI" if prediction in ["TAI", "Tài"] else "🔴 XỈU"
    res_emoji = "🔵 TÀI" if result in ["TAI", "Tài"] else ("🔴 XỈU" if result in ["XIU", "Xỉu"] else f"🎲 {result}")

    msg += f"📌 <b>Phiên mới nhất:</b> <code>#{phien}</code>\n"
    msg += f"🕒 <b>Thời gian:</b> {time_str}\n"
    msg += f"💎 <b>Dự đoán AI:</b> <b>{pred_emoji}</b>\n"
    msg += f"🎲 <b>Kết quả phiên:</b> <b>{res_emoji}</b>\n\n"

    msg += f"📜 <b>5 Phiên gần nhất:</b>\n"
    for r in rows[:5]:
        r_phien = r.get("phien", "N/A")
        r_pred = r.get("prediction", "N/A")
        r_res = r.get("result", "N/A")
        msg += f"• <code>#{r_phien}</code> | Dự đoán: <b>{r_pred}</b> | Kết quả: <b>{r_res}</b>\n"

    return msg

def make_prediction_smart(chat_id):
    with history_lock:
        history = list(GLOBAL_HISTORY)
    if len(history) < 3: 
        return None
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
# SOCKET GAME ENGINE
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
            bot.send_message(chat_id, "💎 <b>KẾT NỐI BÀN TÀI XỈU THƯỜNG THÀNH CÔNG</b>\n🎯 HŨ: 111 (Xỉu) - 666 (Tài)")

    @sio.on('new-session', namespace='/tx')
    def on_new_session(data):
        if is_background: return
        state = user_states[chat_id]
        state["session_id"] = data.get('id', 'N/A')
        state["has_bet_this_session"] = False
        
        if state["auto_bet_enabled"] and state["target_profit"] is not None:
            if state["profit_loss"] >= state["target_profit"]:
                state["auto_bet_enabled"] = False
                bot.send_message(chat_id, f"🏆 <b>ĐẠT MỤC TIÊU!</b> Lãi: <code>+{state['profit_loss']:,}đ</code>")

        prediction = make_prediction_smart(chat_id)
        state["current_prediction"] = prediction
        state["current_bet"] = state["base_bet_amount"] * 2 if (state["x2_mode"] and state["win_streak"] >= 1) else state["base_bet_amount"]

        msg = f"🔮 <b>PHIÊN MỚI:</b> <code>#{state['session_id']}</code>\n"
        if prediction:
            pred_emoji = "🔵 TÀI" if prediction == "TAI" else "🔴 XỈU"
            msg += f"💎 <b>AI CHỐT CẦU:</b> {pred_emoji}\n"
            if state["auto_bet_enabled"]:
                msg += f"✅ <b>Auto Bet:</b> Chuẩn bị VÀO <code>{state['current_bet']:,}đ</code>"
            else:
                msg += "⏸ Auto Bet đang tắt → Dùng /autobettx on"
        bot.send_message(chat_id, msg)

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
        
        result_emoji = "🔵 TÀI" if result == "TAI" else ("🔴 XỈU" if result == "XIU" else "⚪ HOÀN")
        msg = f"🎲 <b>KẾT QUẢ:</b> {result_emoji} • <b>{dices[0]} + {dices[1]} + {dices[2]} = {total_point}</b>"
        
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
        bot.send_message(chat_id, msg)

    try:
        sio.connect('https://wtx.tele68.com', socketio_path='tx/', transports=['websocket'],
                   auth={"token": token}, headers={"User-Agent": "Mozilla/5.0"})
        sio.wait()
    except Exception as e:
        if not is_background: 
            bot.send_message(chat_id, f"⚠️ Lỗi: <code>{e}</code>")

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
            bot.send_message(chat_id, "💎 <b>KẾT NỐI MD5 THÀNH CÔNG</b>")

    @sio.on('new-session', namespace='/txmd5')
    def on_new_session(data):
        if is_background: return
        state = user_states_md5[chat_id]
        state["session_id"] = data.get('id', 'N/A')
        state["has_bet_this_session"] = False

        prediction = make_prediction_smart(chat_id)
        state["current_prediction"] = prediction
        state["current_bet"] = state["base_bet_amount"] * 2 if (state["x2_mode"] and state["win_streak"] >= 1) else state["base_bet_amount"]

        msg = f"🔮 <b>PHIÊN MỚI (MD5):</b> <code>#{state['session_id']}</code>\n"
        if prediction:
            pred_emoji = "🔵 TÀI" if prediction == "TAI" else "🔴 XỈU"
            msg += f"💎 <b>AI CHỐT CẦU:</b> {pred_emoji}\n"
        bot.send_message(chat_id, msg)

    try:
        sio.connect('https://wtxmd52.tele68.com', socketio_path='txmd5/', transports=['websocket'],
                   auth={"token": token}, headers={"User-Agent": "Mozilla/5.0"})
        sio.wait()
    except Exception as e:
        if not is_background: 
            bot.send_message(chat_id, f"⚠️ Lỗi: <code>{e}</code>")

def background_data_collector():
    while True:
        try:
            res = login_and_get_token(DATA_COLLECTOR_USER, DATA_COLLECTOR_PASS)
            if "token" in res:
                start_websocket("BACKGROUND_WORKER", res["token"], is_background=True)
        except: pass
        time.sleep(30)

# ==========================================
# BETVIP FUNCTIONS
# ==========================================
def get_betvip_prediction(api_url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36', 'Accept': 'application/json'}
        r = requests.get(api_url, headers=headers, timeout=10, verify=False)
        if r.status_code == 200: return r.json()
        return None
    except Exception as e:
        logger.error(f"Lỗi API BetVip: {e}")
        return None

def format_betvip_message(data, game_name):
    if not data:
        return f"❌ <b>Không lấy được dữ liệu {game_name}!</b>\nVui lòng thử lại sau."
    
    ket_qua = data.get('Ket_qua', 'N/A')
    phien = data.get('Phien', 'N/A')
    tong = data.get('Tong', 0)
    x1, x2, x3 = data.get('Xuc_xac_1', 0), data.get('Xuc_xac_2', 0), data.get('Xuc_xac_3', 0)
    du_doan = data.get('du_doan', 'N/A')
    phien_dd = data.get('phiendudoan', 'N/A')
    ty_le = data.get('ty_le_dd', 'N/A')
    
    ket_qua_emoji = "🔵 TÀI" if ket_qua == "Tài" else "🔴 XỈU"
    du_doan_emoji = "🔵 TÀI" if du_doan == "Tài" else "🔴 XỈU"
    
    msg = f"🎲 <b>{game_name} - DỰ ĐOÁN</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += f"📌 <b>Phiên hiện tại:</b> <code>#{phien}</code>\n"
    msg += f"🎯 <b>Kết quả:</b> {ket_qua_emoji}\n"
    msg += f"🎲 <b>Xúc xắc:</b> {x1} + {x2} + {x3} = <b>{tong}</b>\n\n"
    msg += f"🔮 <b>DỰ ĐOÁN PHIÊN:</b> <code>#{phien_dd}</code>\n"
    msg += f"💎 <b>Chốt:</b> {du_doan_emoji}\n"
    msg += f"📊 <b>Tỉ lệ:</b> <code>{ty_le}</code>\n"
    return msg

# ==========================================
# GIAO DIỆN MENU INLINE
# ==========================================
def kb_main_inline(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎮 KHU VỰC GAME", callback_data="nav_game_zone"),
        InlineKeyboardButton("🎲 TOOL MD5 FREE", callback_data="nav_tool_md5_free")
    )
    markup.add(
        InlineKeyboardButton("💳 MUA GÓI KEY", callback_data="nav_buy_key"),
        InlineKeyboardButton("💎 NẠP TIỀN VÍ", callback_data="nav_deposit")
    )
    markup.add(
        InlineKeyboardButton("⚡ KÍCH HOẠT KEY", callback_data="nav_activate"),
        InlineKeyboardButton("🎁 GIFTCODE", callback_data="nav_giftcode")
    )
    markup.add(
        InlineKeyboardButton("👤 HỒ SƠ", callback_data="nav_profile"),
        InlineKeyboardButton("⭐ FEEDBACK", callback_data="nav_feedback")
    )
    markup.add(
        InlineKeyboardButton("📢 Kênh Tin Tức", url=CHANNEL_LINK),
        InlineKeyboardButton("💬 Hỗ Trợ", url=f"https://t.me/{ADMIN_CONTACT.replace('@', '')}")
    )
    if str(user_id) == str(ADMIN_ID):
        markup.add(InlineKeyboardButton("👑⚙️ Quản Trị Admin", callback_data="nav_admin"))
    return markup

def kb_game_zone_inline():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎮 Bàn Thường Portal", callback_data="nav_game"),
        InlineKeyboardButton("🎲 Bàn MD5 Portal", callback_data="nav_game_md5")
    )
    markup.add(
        InlineKeyboardButton("🎰 BetVip Hũ", callback_data="nav_betvip_hu"),
        InlineKeyboardButton("🎲 BetVip MD5", callback_data="nav_betvip_md5")
    )
    buttons = [InlineKeyboardButton(f"🕹 {g_name}", callback_data=f"rdgame_{g_id}") for g_name, g_id in RENDER_GAMES.items()]
    markup.add(*buttons)
    markup.add(InlineKeyboardButton("🏠 Quay Lại Menu Chính", callback_data="nav_main"))
    return markup

def kb_back_inline():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🏠 Quay Lại Menu Chính", callback_data="nav_main"))
    return markup

def kb_back_game_zone_inline():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎮 Khu Vực Game", callback_data="nav_game_zone"))
    markup.add(InlineKeyboardButton("🏠 Quay Lại Menu Chính", callback_data="nav_main"))
    return markup

def kb_buy_key_inline():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🔥 1 Ngày - 40k", callback_data="buy_pkg_1"),
        InlineKeyboardButton("⭐️ 3 Ngày - 70k", callback_data="buy_pkg_3"),
        InlineKeyboardButton("💎 1 Tuần - 110k", callback_data="buy_pkg_7"),
        InlineKeyboardButton("👑 1 Tháng - 220k", callback_data="buy_pkg_30"),
        InlineKeyboardButton("🎉 2 Tháng - 300k", callback_data="buy_pkg_60"),
        InlineKeyboardButton("🏆 3 Tháng - 450k", callback_data="buy_pkg_90")
    )
    markup.add(InlineKeyboardButton("🏠 Quay Lại Menu Chính", callback_data="nav_main"))
    return markup

def kb_deposit_presets_inline():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💵 50.000đ (50k)", callback_data="dep_amt_50000"),
        InlineKeyboardButton("💵 100.000đ (100k)", callback_data="dep_amt_100000"),
        InlineKeyboardButton("💵 200.000đ (200k)", callback_data="dep_amt_200000"),
        InlineKeyboardButton("💵 500.000đ (500k)", callback_data="dep_amt_500000")
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
        InlineKeyboardButton("🔍 Xem Hồ Sơ User", callback_data="adm_view_user")
    )
    markup.add(InlineKeyboardButton("🏠 Quay Lại Menu Chính", callback_data="nav_main"))
    return markup

# ==========================================
# GIAO DIỆN CHÍNH (YÊU CẦU 1)
# ==========================================
def render_main_text(user_id, name, username=""):
    refresh_db()
    u_info = get_user(user_id, username=username, full_name=name)
    
    vip_status = "🔴 Chưa kích hoạt"
    if check_active_key(user_id):
        if str(user_id) == str(ADMIN_ID) and not u_info.get("key_expiry"):
            vip_status = "🟢 Admin (Vĩnh viễn)"
        else:
            exp = datetime.fromisoformat(u_info["key_expiry"]).strftime("%d/%m/%Y %H:%M")
            vip_status = f"🟢 Đã kích hoạt (Đến: {exp})"

    nick_str = f"@{username}" if username else f"ID_{user_id}"

    msg = (
        "👑 ⚜️CYBER CHAT⚜️ 𝗩𝗜𝗣 𝗔𝗜 𝟮𝟬𝟮𝟲 👑\n"
        "━━━━━━━━━━━\n"
        f"👤 Khách hàng: <b>{name}</b>\n"
        f"🆔 ID: <code>{user_id}</code> | Nick: {nick_str}\n"
        f"💳 Số dư ví: <b>{u_info['balance']:,}đ</b>\n"
        f"🔴 VIP Status: <b>{vip_status}</b>\n"
        "━━━━━━━━━━━\n"
        "🚀 HƯỚNG DẪN 3 BƯỚC SỬ DỤNG:\n"
        "1️⃣ Bấm 💎 NẠP TIỀN VÍ để nạp số dư tự động\n"
        "2️⃣ Bấm 💳 MUA GÓI KEY chọn thời hạn phù hợp\n"
        "3️⃣ Bấm 🎮 KHU VỰC GAME để nhận dự đoán chuẩn xác!\n"
        "━━━━━━━━━━━\n"
        f"📢 Kênh tin tức: {CHANNEL_LINK} | 💬 Hỗ trợ: {ADMIN_CONTACT}"
    )
    return msg

# ==========================================
# LỆNH VÀ CÁC HANDLER BẮT ĐẦU
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data == "verify_join")
def handle_verify_join(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    refresh_db()
    if str(user_id) not in db.get("joined_users", []):
        db.setdefault("joined_users", []).append(str(user_id))
        save_db()
    bot.edit_message_text(
        "✅ <b>XÁC NHẬN THÀNH CÔNG!</b>\nChào mừng bạn! 🎉",
        chat_id=chat_id, message_id=call.message.message_id)
    bot.send_message(chat_id, render_main_text(user_id, call.from_user.first_name, call.from_user.username),
                    reply_markup=kb_main_inline(user_id))

@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    if check_and_block(message): return
    if not check_user_joined(message.from_user.id):
        msg = "🔔 <b>YÊU CẦU BẮT BUỘC</b>\nVui lòng tham gia kênh/nhóm trước!"
        bot.send_message(message.chat.id, msg, reply_markup=kb_verify_join())
        return
    init_user_state(message.chat.id)
    init_user_state_md5(message.chat.id)
    bot.send_message(
        message.chat.id, 
        render_main_text(message.from_user.id, message.from_user.first_name, message.from_user.username),
        reply_markup=kb_main_inline(message.from_user.id)
    )

# ==========================================
# XỬ LÝ NẠP TIỀN DUYỆT TAY (YÊU CẦU 4, 8, 9, 10)
# ==========================================
def render_deposit_instruction():
    return (
        "🏦 CỔNG NẠP TIỀN QUA BIDV\n"
        "━━━━━━━━━━━\n"
        "💰 Vui lòng nhập số tiền bạn muốn nạp:\n"
        "• Ví dụ: 50000 hoặc 50k\n"
        "• Ví dụ: 100000 hoặc 100k\n"
        "───────────\n"
        "ℹ️ Tối thiểu: 10.000đ | Tối đa: 100.000.000đ\n"
        "📸 Lưu ý: Hệ thống tự động sinh mã QR BIDV chuẩn xác."
    )

def process_deposit_amount_input(message):
    if check_and_block(message): return
    raw = message.text.strip()
    amt = parse_amount_str(raw)
    
    if amt is None or amt < 10000 or amt > 100000000:
        return bot.send_message(
            message.chat.id, 
            "❌ <b>Số tiền nhập không hợp lệ!</b>\nVui lòng nhập lại số tiền từ 10.000đ đến 100.000.000đ (VD: 50k hoặc 50000):"
        )
    
    user_id = message.from_user.id
    refresh_db()
    db["deposit_order_count"] = db.get("deposit_order_count", 100) + 1
    order_id = db["deposit_order_count"]
    memo = f"NAP {user_id} MD{order_id}"
    
    db.setdefault("pending_deposits", {})[str(order_id)] = {
        "order_id": order_id,
        "user_id": user_id,
        "amount": amt,
        "memo": memo,
        "status": "pending",
        "created_at": datetime.now().strftime("%H:%M:%S • %d/%m/%Y")
    }
    save_db()
    
    qr_url = generate_qr_url(amt, memo)
    
    caption_msg = (
        "🏦💳 THÔNG TIN CHUYỂN KHOẢN 💳🏦\n\n"
        f"👤 Tên: <b>{BANK_NAME}</b>\n"
        f"💳 STK: <code>{BANK_ACC}</code>\n"
        f"💵 Số tiền: <b>{amt:,} VNĐ</b>\n"
        f"📌 Nội dung CK: <code>{memo}</code>\n\n"
        "📌 Chuyển khoản đúng số tiền.\n"
        "⚠️ Chỉ bấm 'TÔI ĐÃ CHUYỂN KHOẢN' sau khi đã chuyển tiền.\n\n"
        f"🧾 Mã đơn: #{order_id}"
    )
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ TÔI ĐÃ CHUYỂN KHOẢN", callback_data=f"confirm_deposit_{order_id}"))
    markup.add(InlineKeyboardButton("❌ Hủy Đơn Nạp", callback_data="nav_main"))
    
    bot.send_photo(message.chat.id, qr_url, caption=caption_msg, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_deposit_"))
def handle_user_confirm_deposit(call):
    order_id = call.data.split("_")[2]
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    refresh_db()
    
    deposit = db.get("pending_deposits", {}).get(str(order_id))
    if not deposit:
        return bot.answer_callback_query(call.id, "❌ Đơn nạp không tồn tại hoặc đã bị hủy!", show_alert=True)
    
    bot.answer_callback_query(call.id)
    
    # Sửa tin nhắn người dùng
    user_confirm_msg = (
        "💎✨ ĐÃ GỬI YÊU CẦU NẠP CHO ADMIN ✨💎\n\n"
        "🔔📨 VUI LÒNG CHỜ ĐỢI ADMIN KIỂM TRA VÀ DUYỆT\n\n"
        f"🧾🔎 CHECK BILL CỦA BẠN TẠI {CHANNEL_LINK}\n\n"
        "⚡️💰 HỆ THỐNG ĐÃ GHI NHẬN YÊU CẦU CỦA BẠN\n"
        "👑🛡️ ADMIN SẼ KIỂM TRA VÀ XỬ LÝ THỦ CÔNG\n"
        "🍀💎 VUI LÒNG KIÊN NHẪN CHỜ THÔNG BÁO XÁC NHẬN"
    )
    bot.edit_message_caption(caption=user_confirm_msg, chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_back_inline())
    
    # Gửi thông báo cho Admin duyệt
    u_info = get_user(user_id)
    admin_alert = (
        "📥 <b>YÊU CẦU NẠP TIỀN MỚI #DUYET_TAY</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🧾 Mã đơn: <b>#{order_id}</b>\n"
        f"👤 Người nạp: {u_info['full_name']} (@{u_info.get('username', 'N/A')})\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"💰 Số tiền: <b>{deposit['amount']:,}đ</b>\n"
        f"📌 Nội dung: <code>{deposit['memo']}</code>\n"
        f"⏱️ Thời gian: {deposit['created_at']}"
    )
    
    adm_markup = InlineKeyboardMarkup(row_width=2)
    adm_markup.add(
        InlineKeyboardButton("✅ Duyệt Nạp", callback_data=f"adm_approve_dep_{order_id}"),
        InlineKeyboardButton("❌ Hủy Yêu Cầu", callback_data=f"adm_reject_dep_{order_id}")
    )
    bot.send_message(ADMIN_ID, admin_alert, reply_markup=adm_markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_approve_dep_") or call.data.startswith("adm_reject_dep_"))
def handle_admin_deposit_approval(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        return bot.answer_callback_query(call.id, "❌ Bạn không phải Admin!", show_alert=True)
    
    parts = call.data.split("_")
    action = parts[1] # approve / reject
    order_id = parts[3]
    
    refresh_db()
    deposit = db.get("pending_deposits", {}).get(str(order_id))
    if not deposit or deposit.get("status") != "pending":
        return bot.answer_callback_query(call.id, "⚠️ Đơn này đã được xử lý trước đó!", show_alert=True)
    
    target_user_id = deposit["user_id"]
    amt = deposit["amount"]
    u_info = get_user(target_user_id)
    
    if action == "approve":
        deposit["status"] = "approved"
        new_bal = u_info["balance"] + amt
        update_user(target_user_id, balance=new_bal)
        
        # Ghi lịch sử
        db.setdefault("transaction_history", {}).setdefault(str(target_user_id), [])
        db["transaction_history"][str(target_user_id)].append({
            "type": "deposit", "amount": amt, "balance": new_bal,
            "trans_id": f"MD{order_id}", "time": datetime.now().isoformat()
        })
        save_db()
        
        bot.answer_callback_query(call.id, f"✅ Đã duyệt +{amt:,}đ cho ID {target_user_id}")
        bot.edit_message_text(
            f"✅ <b>ĐÃ DUYỆT ĐƠN NẠP #{order_id}</b>\n👤 User: <code>{target_user_id}</code> | 💰 +{amt:,}đ",
            chat_id=call.message.chat.id, message_id=call.message.message_id
        )
        
        # Gửi thông báo duyệt thành công cho User (Mẫu 9)
        now_str = datetime.now().strftime("%H:%M:%S • %d/%m/%Y")
        user_success_msg = (
            "🎉 𝗡𝗔𝗣 𝗧𝗜𝗘𝗡 𝗧𝗛𝗔𝗡𝗛 𝗖𝗢𝗡𝗚 🎉\n"
            "━━━━━━━━━━━\n"
            f"💰 Số tiền nạp: +{amt:,}đ\n"
            f"🎁 Thực nhận: +{amt:,}đ\n"
            f"👤 Người nạp: {u_info['full_name']}\n"
            f"🔖 Mã giao dịch: {order_id}\n"
            f"⏱️ Thời gian duyệt: {now_str}\n"
            "📊 Trạng thái: 🟢 Đã cộng vào ví thành công\n"
            "━━━━━━━━━━━\n"
            "🚀 Giao dịch đã được hệ thống xác nhận thành công!\n"
            "💡 Chúc bạn trải nghiệm dịch vụ may mắn & thắng lớn!\n"
            "━━━━━━━━━━━\n"
            f"Cskh {ADMIN_CONTACT}\n"
            f"Kênh @{CHANNEL_LINK.replace('https://t.me/', '')}\n"
            f"Link Tool {BOT_USERNAME}"
        )
        try:
            bot.send_message(target_user_id, user_success_msg)
        except Exception as e:
            logger.error(f"Không gửi được thông báo cho user: {e}")
            
    else: # reject
        deposit["status"] = "rejected"
        save_db()
        bot.answer_callback_query(call.id, f"❌ Đã hủy đơn #{order_id}")
        bot.edit_message_text(
            f"❌ <b>ĐÃ HỦY ĐƠN NẠP #{order_id}</b>\n👤 User: <code>{target_user_id}</code>",
            chat_id=call.message.chat.id, message_id=call.message.message_id
        )
        try:
            bot.send_message(target_user_id, f"❌ <b>ĐƠN NẠP #{order_id} CỦA BẠN ĐÃ BỊ TỪ CHỐI!</b>\nLiên hệ CSKH {ADMIN_CONTACT} để hỗ trợ.")
        except: pass

# ==========================================
# CALLBACK HANDLER CHÍNH
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    if check_and_block(call): return
    if call.data != "verify_join" and not check_user_joined(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Vui lòng tham gia kênh/nhóm trước!", show_alert=True)
        return
    
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    bot.answer_callback_query(call.id)

    if call.data == "nav_main":
        bot.edit_message_text(
            render_main_text(user_id, call.from_user.first_name, call.from_user.username),
            chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_main_inline(user_id)
        )

    # 1. KHU VỰC GAME (YÊU CẦU 2)
    elif call.data == "nav_game_zone":
        if not is_vip(user_id):
            return bot.send_message(chat_id, "⛔ <b>BẠN CHƯA KÍCH HOẠT VIP!</b> Vui lòng mua Key để sử dụng.")
        msg = "🎮 <b>KHU VỰC GAME DỰ ĐOÁN</b>\nChọn game bạn muốn soi cầu/dự đoán bên dưới:"
        bot.edit_message_text(msg, chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_game_zone_inline())

    # 2. TOOL MD5 FREE (YÊU CẦU 2)
    elif call.data == "nav_tool_md5_free":
        msg = (
            "🎲 <b>TOOL PHÂN TÍCH MÃ MD5 FREE</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👉 Vui lòng gửi mã MD5 (chuỗi 32 ký tự) trực tiếp vào ô chat để AI phân tích ngay!\n"
            "Ví dụ: <code>c4ca4238a0b923820dcc509a6f75849b</code>"
        )
        bot.edit_message_text(msg, chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_back_inline())

    # 3. HỒ SƠ TÀI KHOẢN (YÊU CẦU 3)
    elif call.data == "nav_profile":
        refresh_db()
        u_info = get_user(user_id, username=call.from_user.username, full_name=call.from_user.first_name)
        key_status = "Chưa có"
        if u_info.get("key_expiry"):
            try:
                exp = datetime.fromisoformat(u_info["key_expiry"]).strftime("%d/%m/%Y %H:%M")
                key_status = f"🟢 Đến {exp}"
            except: pass
        
        join_date = u_info.get("created_at", "30/07/2026 01:04")

        msg = (
            "👤 HỒ SƠ TÀI KHOẢN\n"
            "━━━━━━━━━━━\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"👤 Tên: <b>{u_info['full_name']}</b>\n"
            f"💳 Số dư ví: <b>{u_info['balance']:,}đ</b>\n"
            f"🔑 Key VIP: {key_status}\n"
            f"📅 Ngày tham gia: {join_date}\n"
            "━━━━━━━━━━━\n"
            f"🏦 Cổng nạp hiện tại: {BANK_BIN} ({BANK_ACC} -{BANK_NAME})"
        )
        bot.edit_message_text(msg, chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_back_inline())

    # 4. NẠP TIỀN VÍ (YÊU CẦU 4)
    elif call.data == "nav_deposit":
        sent = bot.send_message(chat_id, render_deposit_instruction(), reply_markup=kb_deposit_presets_inline())
        bot.register_next_step_handler(sent, process_deposit_amount_input)

    elif call.data.startswith("dep_amt_"):
        val = call.data.split("_")[2]
        amt = int(val)
        refresh_db()
        db["deposit_order_count"] = db.get("deposit_order_count", 100) + 1
        order_id = db["deposit_order_count"]
        memo = f"NAP {user_id} MD{order_id}"
        
        db.setdefault("pending_deposits", {})[str(order_id)] = {
            "order_id": order_id, "user_id": user_id, "amount": amt,
            "memo": memo, "status": "pending",
            "created_at": datetime.now().strftime("%H:%M:%S • %d/%m/%Y")
        }
        save_db()
        
        qr_url = generate_qr_url(amt, memo)
        caption_msg = (
            "🏦💳 THÔNG TIN CHUYỂN KHOẢN 💳🏦\n\n"
            f"👤 Tên: <b>{BANK_NAME}</b>\n"
            f"💳 STK: <code>{BANK_ACC}</code>\n"
            f"💵 Số tiền: <b>{amt:,} VNĐ</b>\n"
            f"📌 Nội dung CK: <code>{memo}</code>\n\n"
            "📌 Chuyển khoản đúng số tiền.\n"
            "⚠️ Chỉ bấm 'TÔI ĐÃ CHUYỂN KHOẢN' sau khi đã chuyển tiền.\n\n"
            f"🧾 Mã đơn: #{order_id}"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("✅ TÔI ĐÃ CHUYỂN KHOẢN", callback_data=f"confirm_deposit_{order_id}"))
        markup.add(InlineKeyboardButton("❌ Hủy Đơn Nạp", callback_data="nav_main"))
        
        bot.send_photo(chat_id, qr_url, caption=caption_msg, reply_markup=markup)

    # 5. MUA BẢNG GIÁ KEY VIP (YÊU CẦU 5)
    elif call.data == "nav_buy_key":
        msg = (
            "💳 𝗕𝗔𝗡𝗚 𝗚𝗜𝗔 𝗚𝗢𝗜 𝗞𝗘𝗬 𝗩𝗜𝗣\n"
            "━━━━━━━━━━━\n"
            "🔥 𝟭 𝗡𝗴à𝘆: 40.000đ (24h)\n"
            "⭐️ 𝟯 𝗡𝗴à𝘆: 70.000đ (72h)\n"
            "💎 𝟭 𝗧𝘂ầ𝗻: 110.000đ (168h)\n"
            "👑 𝟭 𝗧𝗵á𝗻𝗴: 220.000đ (720h)\n"
            "🎉 𝟮 𝗧𝗵á𝗻𝗴: 300.000đ (1440h)\n"
            "🏆 𝟯 𝗧𝗵á𝗻𝗴: 450.000đ (2160h)\n"
            "━━━━━━━━━━━\n"
            "⚡ Thanh toán tự động trừ từ số dư ví!\n"
            "💎 Nạp tiền nhanh qua BIDV để có số dư ngay lập tức."
        )
        bot.edit_message_text(msg, chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_buy_key_inline())

    elif call.data.startswith("buy_pkg_"):
        days = int(call.data.split("_")[2])
        price = KEY_PRICES.get(days, 0)
        refresh_db()
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
            bot.edit_message_text(f"🎉 <b>MUA KEY THÀNH CÔNG!</b>\nĐã cộng +{days} ngày VIP vào tài khoản.", chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_back_inline())
        else:
            bot.edit_message_text(f"❌ <b>SỐ DƯ KHÔNG ĐỦ!</b>\nCần: <b>{price:,}đ</b> | Số dư ví: <b>{u_info['balance']:,}đ</b>\nVui lòng nạp tiền thêm!", chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_deposit_presets_inline())

    # 6. KÍCH HOẠT KEY (YÊU CẦU 6)
    elif call.data == "nav_activate":
        msg = (
            "⚡ KÍCH HOẠT KEY VIP\n"
            "━━━━━━━━━━━\n"
            "Vui lòng nhập mã KEY VIP của bạn vào ô chat bên dưới:\n"
            "(Nếu chưa có key, hãy vào mục Mua Key hoặc nạp tiền ví)"
        )
        sent = bot.send_message(chat_id, msg)
        bot.register_next_step_handler(sent, process_input_key)

    # 7. GIFTCODE (YÊU CẦU 7)
    elif call.data == "nav_giftcode":
        msg = (
            "🎁 NHẬN THƯỞNG GIFTCODE\n"
            "━━━━━━━━━━━\n"
            "Vui lòng nhập mã Giftcode bạn nhận được vào ô chat bên dưới:"
        )
        sent = bot.send_message(chat_id, msg)
        bot.register_next_step_handler(sent, process_input_giftcode)

    # 8. FEEDBACK & ĐÁNH GIÁ (YÊU CẦU 8)
    elif call.data == "nav_feedback":
        msg = (
            "⭐ ĐÁNH GIÁ DỊCH VỤ & GỬI FEEDBACK\n"
            "━━━━━━━━━━━\n"
            "Cảm ơn bạn đã tin tưởng và sử dụng Tool ⚜️CYBER CHAT⚜️!\n"
            "Xin vui lòng cho chúng tôi biết mức độ hài lòng của bạn:\n\n"
            "👉 Chọn mức đánh giá từ 1 đến 5 sao bên dưới:\n"
            "━━━━━━━━━━━\n"
            "🎁 Feedback hợp lệ kèm ảnh bill thắng lớn được duyệt tặng +5.000đ vào ví!"
        )
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("⭐⭐⭐⭐⭐ : Rất hài lòng, soi rất chuẩn", callback_data="rate_5"),
            InlineKeyboardButton("⭐⭐⭐⭐ : Hài lòng, dịch vụ tốt", callback_data="rate_4"),
            InlineKeyboardButton("⭐⭐⭐ : Bình thường, tạm ổn", callback_data="rate_3"),
            InlineKeyboardButton("⭐⭐ : Cần cải thiện", callback_data="rate_2"),
            InlineKeyboardButton("⭐ : Kém, chưa hài lòng", callback_data="rate_1")
        )
        markup.add(InlineKeyboardButton("🏠 Quay Lại Menu Chính", callback_data="nav_main"))
        bot.edit_message_text(msg, chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)

    elif call.data.startswith("rate_"):
        stars = call.data.split("_")[1]
        sent = bot.send_message(chat_id, f"🌟 Bạn đã chọn {stars} sao! Vui lòng nhập nhận xét/feedback của bạn vào ô chat:")
        bot.register_next_step_handler(sent, lambda m: process_user_rating(m, stars))

    # XỬ LÝ SUB-GAME TRONG KHU VỰC GAME
    elif call.data == "nav_game":
        bot.edit_message_text("🎮 <b>BÀN TÀI XỈU THƯỜNG PORTAL</b>\n🔹 Cú pháp: <code>/logintx tk mk</code>", 
                            chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_back_game_zone_inline())
    elif call.data == "nav_game_md5":
        bot.edit_message_text("🎲 <b>BÀN TÀI XỈU MD5 PORTAL</b>\n🔹 Cú pháp: <code>/loginmd5 tk mk</code>", 
                            chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_back_game_zone_inline())
    elif call.data == "nav_betvip_hu":
        data = get_betvip_prediction(BETVIP_API_HU)
        msg = format_betvip_message(data, "🎰 BÀN HŨ")
        bot.edit_message_text(msg, chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_back_game_zone_inline())
    elif call.data == "nav_betvip_md5":
        data = get_betvip_prediction(BETVIP_API_MD5)
        msg = format_betvip_message(data, "🎲 BÀN MD5")
        bot.edit_message_text(msg, chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_back_game_zone_inline())

    elif call.data.startswith("rdgame_"):
        target = call.data.split("_")[1]
        g_id = int(target)
        g_name = [k for k, v in RENDER_GAMES.items() if v == g_id][0]
        bot.edit_message_text(f"🔄 <b>Đang lấy dữ liệu Game {g_name}...</b>", chat_id=chat_id, message_id=call.message.message_id)
        result_msg = format_render_game_msg(g_name, g_id)
        bot.edit_message_text(result_msg, chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_back_game_zone_inline())

    # MENU ADMIN
    elif call.data == "nav_admin":
        if str(user_id) == str(ADMIN_ID):
            bot.edit_message_text("👑 <b>QUẢN TRỊ ADMIN</b>", chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb_admin_inline())

    elif call.data.startswith("adm_"):
        if str(user_id) != str(ADMIN_ID): return
        if call.data == "adm_create_key":
            sent = bot.send_message(chat_id, "🔑 <b>Nhập số ngày (1,3,7,30,60,90):</b>")
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

# ==========================================
# CÁC HÀM NHẬP DỮ LIỆU BỔ TRỢ
# ==========================================
def process_user_rating(message, stars):
    fb_id = str(random.randint(100000, 999999))
    refresh_db()
    db.setdefault("pending_feedbacks", {})[fb_id] = {
        "uid": str(message.chat.id), "stars": stars, "content": message.text
    }
    save_db()
    bot.send_message(
        message.chat.id, 
        f"✅ <b>CẢM ƠN BẠN ĐÃ ĐÁNH GIÁ {stars} STAR!</b>\nFeedback của bạn đã được gửi tới Admin.", 
        reply_markup=kb_main_inline(message.chat.id)
    )

def process_input_key(message):
    key_code = message.text.strip()
    refresh_db()
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
        refresh_db()
        del db["keys"][key_code]
        save_db()
        bot.send_message(message.chat.id, f"🎉 <b>KÍCH HOẠT THÀNH CÔNG!</b>\nĐã cộng +{days} ngày VIP.", reply_markup=kb_main_inline(message.chat.id))
    else:
        bot.send_message(message.chat.id, "❌ <b>Mã Key không hợp lệ!</b>", reply_markup=kb_main_inline(message.chat.id))

def process_input_giftcode(message):
    code = message.text.strip().upper()
    refresh_db()
    if code in db.get("giftcodes", {}):
        gc = db["giftcodes"][code]
        if str(message.chat.id) in gc.get("used_by", []):
            return bot.send_message(message.chat.id, "❌ Bạn đã sử dụng mã này rồi!", reply_markup=kb_main_inline(message.chat.id))
        user = get_user(message.chat.id)
        update_user(message.chat.id, balance=user["balance"] + gc["value"])
        refresh_db()
        gc.setdefault("used_by", []).append(str(message.chat.id))
        gc["usages"] -= 1
        if gc["usages"] <= 0: del db["giftcodes"][code]
        save_db()
        bot.send_message(message.chat.id, f"🎉 <b>NHẬN THƯỞNG THÀNH CÔNG!</b>\n+<code>{gc['value']:,}đ</code> vào ví.", reply_markup=kb_main_inline(message.chat.id))
    else:
        bot.send_message(message.chat.id, "❌ <b>Mã Giftcode không tồn tại hoặc đã hết hạn!</b>", reply_markup=kb_main_inline(message.chat.id))

def admin_step_key(message):
    if str(message.from_user.id) != str(ADMIN_ID): return
    try:
        days = int(message.text.strip())
        key_code = "VIP-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        refresh_db()
        db.setdefault("keys", {})[key_code] = days
        save_db()
        bot.send_message(message.chat.id, f"✅ <b>TẠO KEY:</b> <code>{key_code}</code>\n⏳ Hạn: {days} ngày", reply_markup=kb_admin_inline())
    except:
        bot.send_message(message.chat.id, "❌ Nhập số ngày hợp lệ!", reply_markup=kb_admin_inline())

def admin_step_bal(message):
    if str(message.from_user.id) != str(ADMIN_ID): return
    try:
        parts = message.text.strip().split()
        uid, amt = parts[0], int(parts[1])
        refresh_db()
        user = get_user(uid)
        new_bal = user['balance'] + amt
        update_user(uid, balance=new_bal)
        save_db()
        bot.send_message(message.chat.id, f"✅ ID <code>{uid}</code> → Số dư mới: <b>{new_bal:,}đ</b>", reply_markup=kb_admin_inline())
    except:
        bot.send_message(message.chat.id, "❌ Sai cú pháp!", reply_markup=kb_admin_inline())

def admin_step_create_giftcode(message):
    if str(message.from_user.id) != str(ADMIN_ID): return
    try:
        parts = message.text.strip().split()
        code, val, usages = parts[0].upper(), int(parts[1]), int(parts[2])
        refresh_db()
        db.setdefault("giftcodes", {})[code] = {"value": val, "usages": usages, "used_by": []}
        save_db()
        bot.send_message(message.chat.id, f"🎁 <b>GIFTCODE:</b> <code>{code}</code>\n💰 {val:,}đ | 🔢 {usages} lượt", reply_markup=kb_admin_inline())
    except:
        bot.send_message(message.chat.id, "❌ Sai cú pháp!", reply_markup=kb_admin_inline())

def admin_step_broadcast(message):
    if str(message.from_user.id) != str(ADMIN_ID): return
    text = message.text.strip()
    refresh_db()
    users = db.get("users", {})
    success = 0
    for uid in list(users.keys()):
        try:
            bot.send_message(uid, f"📢 <b>THÔNG BÁO</b>\n{text}")
            success += 1
            time.sleep(0.05)
        except: pass
    bot.send_message(message.chat.id, f"✅ Đã gửi tới {success} user!", reply_markup=kb_admin_inline())

# ==========================================
# SOI CẦU MÃ MD5 DỰA TRÊN TEXT
# ==========================================
@bot.message_handler(func=lambda msg: len(msg.text.strip()) == 32 and all(c in string.hexdigits for c in msg.text.strip()))
def handle_md5_code(message):
    if check_and_block(message): return
    if not check_user_joined(message.from_user.id):
        msg = "🔔 <b>YÊU CẦU BẮT BUỘC</b>\nVui lòng tham gia kênh/nhóm trước!"
        bot.send_message(message.chat.id, msg, reply_markup=kb_verify_join())
        return
    
    md5_code = message.text.strip()
    res = analyze_ai_deep(md5_code)
    out = (
        f"🎲 <b>KẾT QUẢ PHÂN TÍCH MD5</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 Mã MD5: <code>{md5_code}</code>\n"
        f"📊 Tỉ lệ AI: TÀI {res['tai_percent']}% | XỈU {res['xiu_percent']}%\n"
        f"🎯 Dự đoán cửa: <b>{res['result']}</b>"
    )
    if res["is_reversed"]:
        out += "\n<i>(Thuật toán đang trạng thái đảo cầu)</i>"
    bot.reply_to(message, out)

# ==========================================
# RUN BOT
# ==========================================
if __name__ == '__main__':
    print("==================================================")
    print("🤖 CYBER CHAT VIP AI BOT IS ONLINE!")
    print("==================================================")
    try:
        bot.remove_webhook()
    except Exception as e:
        pass
    try:
        bot.set_my_commands([
            BotCommand("start", "Khởi Động Bot / Menu"),
            BotCommand("menu", "Hiện Menu Chính"),
            BotCommand("help", "Hướng Dẫn Sử Dụng")
        ])
    except: pass
    threading.Thread(target=background_data_collector, daemon=True).start()
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"❌ Lỗi Polling: {e}")
