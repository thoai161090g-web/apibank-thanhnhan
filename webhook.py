from flask import Flask, request
import hmac
import hashlib
import json
import logging
import re
from datetime import datetime
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
# FLASK WEBHOOK
# ==========================================
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

@app.route('/webhook', methods=['POST'])
def thueapi_webhook():
    try:
        data = request.get_json()
        signature = request.headers.get('X-Webhook-Signature', '')
        
        # Xác thực chữ ký
        if THUEAPI_SECRET_KEY:
            payload = request.get_data(as_text=True)
            expected = hmac.new(
                THUEAPI_SECRET_KEY.encode(),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(expected, signature):
                logger.warning("Chữ ký không hợp lệ!")
                return "Invalid signature", 401
        
        # Lấy thông tin giao dịch
        va = data.get('va', '')
        amount = data.get('amount', 0)
        content = data.get('content', '').upper()
        
        logger.info(f"Nhận webhook: VA={va}, Amount={amount}, Content={content}")
        
        # Xử lý nội dung chuyển khoản: NAP [ID]
        if 'NAP' in content:
            match = re.search(r'NAP\s*(\d+)', content)
            if match:
                user_id = match.group(1)
                process_deposit_from_webhook(user_id, amount, va)
            else:
                logger.warning(f"Nội dung NAP không có ID: {content}")
        else:
            logger.info(f"Bỏ qua giao dịch không có NAP: {content}")
        
        return "OK", 200
        
    except Exception as e:
        logger.error(f"Lỗi webhook: {e}")
        return "Error", 500

@app.route('/')
def home():
    return "Webhook server đang chạy!", 200

if __name__ == '__main__':
    print("🌐 WEBHOOK SERVER STARTED ON PORT 5000")
    app.run(host='0.0.0.0', port=5000)