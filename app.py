from flask import Flask, request
import telebot
import requests
import json
import logging
import threading
import time
import socketio
import hmac
import hashlib
import re
from datetime import datetime, timedelta
from functools import wraps
import random
import string
import os

# ==========================================
# CẤU HÌNH
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Flask
flask_app = Flask(__name__)

# Telegram Bot
BOT_TOKEN = '8296926605:AAH32SNx9cbvcROyZV2ZXcszM3DOU9Wi7ro'
ADMIN_ID = '8375848425'
THUEAPI_SECRET_KEY = "LqYHCWAmHmFaaRxJKx4HPfvi2dE7CMJa"

# ==========================================
# FLASK WEBHOOK - NHẬN DỮ LIỆU TỪ THUEAPI
# ==========================================
@flask_app.route('/webhook', methods=['POST'])
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
        time_str = data.get('time', '')
        
        logger.info(f"Nhận webhook: VA={va}, Amount={amount}, Content={content}")
        
        # Xử lý nội dung chuyển khoản: NAP [ID]
        if 'NAP' in content:
            match = re.search(r'NAP\s*(\d+)', content)
            if match:
                user_id = match.group(1)
                logger.info(f"✅ Tự động nạp {amount:,}đ cho user {user_id}")
                
                # Gửi thông báo cho user
                try:
                    bot = telebot.TeleBot(BOT_TOKEN)
                    bot.send_message(
                        user_id,
                        f"🎉 <b>NẠP TIỀN TỰ ĐỘNG THÀNH CÔNG!</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"💰 Số tiền: <code>+{amount:,}đ</code>\n"
                        f"📅 Lúc: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"✅ <b>GIAO DỊCH ĐÃ ĐƯỢC TỰ ĐỘNG DUYỆT!</b>",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Không thể gửi tin: {e}")
            else:
                logger.warning(f"Nội dung NAP không có ID: {content}")
        else:
            logger.info(f"Bỏ qua giao dịch không có NAP: {content}")
        
        return "OK", 200
        
    except Exception as e:
        logger.error(f"Lỗi webhook: {e}")
        return "Error", 500

@flask_app.route('/')
def home():
    return "Webhook server đang chạy!", 200

def run_flask():
    flask_app.run(host='0.0.0.0', port=5000)

# ==========================================
# KHỞI CHẠY
# ==========================================
if __name__ == '__main__':
    print("==================================================")
    print("🤖 WEBHOOK BOT STARTED!")
    print("==================================================")
    
    # Khởi chạy Flask
    run_flask()