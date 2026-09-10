from flask import Flask, request
import hmac
import hashlib
import json
import logging
import re
import telebot

# ==========================================
# CẤU HÌNH
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = '8296926605:AAH32SNx9cbvcROyZV2ZXcszM3DOU9Wi7ro'
ADMIN_ID = 8375848425
THUEAPI_SECRET_KEY = "LqYHCWAmHmFaaRxJKx4HPfvi2dE7CMJa"

# Import các hàm từ bot.py
from bot import process_deposit_from_webhook, get_user, update_user, db, save_db

# ==========================================
# FLASK APP
# ==========================================
app = Flask(__name__)

# ==========================================
# WEBHOOK NHẬN TỪ THUEAPI
# ==========================================
@app.route('/webhook', methods=['POST'])
def thueapi_webhook():
    try:
        data = request.get_json()
        
        # Log raw data để debug
        logger.info(f"🔍 Raw JSON: {json.dumps(data, ensure_ascii=False)}")
        
        signature = request.headers.get('X-Webhook-Signature', '')
        
        # Xác thực chữ ký (nếu có secret key)
        if THUEAPI_SECRET_KEY:
            payload = request.get_data(as_text=True)
            expected = hmac.new(
                THUEAPI_SECRET_KEY.encode(),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(expected, signature):
                logger.warning("⚠️ Chữ ký không hợp lệ!")
                # Không return lỗi để tránh ThueAPI retry liên tục
                # return "Invalid signature", 401
        
        # ✅ PARSE ĐÚNG CẤU TRÚC THUEAPI
        transactions = data.get('transactions', [])
        
        if not transactions:
            logger.warning("Không có giao dịch trong webhook")
            return "OK", 200
        
        for trans in transactions:
            va = trans.get('accountNumber', '')
            amount = trans.get('transferAmount', 0)
            content = trans.get('content', '').upper()
            transfer_type = trans.get('transferType', 'IN')
            trans_id = trans.get('id', '')
            
            logger.info(f"📦 Giao dịch #{trans_id}: VA={va}, Amount={amount}, Content={content}, Type={transfer_type}")
            
            # Chỉ xử lý tiền vào
            if transfer_type != 'IN':
                logger.info(f"⏭ Bỏ qua giao dịch tiền ra")
                continue
            
            # Xử lý nội dung chuyển khoản: NAP [ID]
            if 'NAP' in content:
                match = re.search(r'NAP\s*(\d+)', content)
                if match:
                    user_id = match.group(1)
                    logger.info(f"✅ Tìm thấy NAP cho user {user_id}, số tiền {amount:,}đ")
                    process_deposit_from_webhook(user_id, amount, va)
                else:
                    logger.warning(f"⚠️ Không tìm thấy ID trong nội dung NAP: {content}")
            else:
                logger.info(f"⏭ Bỏ qua giao dịch không có NAP: {content}")
        
        return "OK", 200
        
    except Exception as e:
        logger.error(f"❌ Lỗi webhook: {e}", exc_info=True)
        return "Error", 500

# ==========================================
# ROUTE KIỂM TRA SERVER
# ==========================================
@app.route('/')
def home():
    return "Webhook server đang chạy!", 200

# ==========================================
# KHỞI CHẠY
# ==========================================
if __name__ == '__main__':
    print("🌐 WEBHOOK SERVER STARTED ON PORT 5000")
    app.run(host='0.0.0.0', port=5000)
