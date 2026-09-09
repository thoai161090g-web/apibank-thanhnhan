from flask import Flask, request
import requests
import hashlib
import hmac
import json
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# === THAY THÔNG TIN CỦA BẠN ===
BOT_TOKEN = "YOUR_BOT_TOKEN"      # Token bot Telegram
CHAT_ID = "YOUR_CHAT_ID"          # ID chat Telegram
SECRET_KEY = "YOUR_SECRET_KEY"    # Secret Key vừa sao chép từ ThueAPI
# ================================

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # 1. Lấy dữ liệu
        data = request.get_json()
        signature = request.headers.get('X-Webhook-Signature', '')
        
        # 2. Xác thực chữ ký (bảo mật)
        if SECRET_KEY != "YOUR_SECRET_KEY":
            payload = request.get_data(as_text=True)
            expected = hmac.new(
                SECRET_KEY.encode(),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(expected, signature):
                app.logger.warning("Chữ ký không hợp lệ!")
                return "Invalid signature", 401
        
        # 3. Xử lý dữ liệu giao dịch
        va = data.get('va', '')
        amount = data.get('amount', 0)
        content = data.get('content', '')
        time = data.get('time', '')
        
        app.logger.info(f"Nhận thanh toán: {amount}đ - {content}")
        
        # 4. Gửi thông báo Telegram
        message = f"✅ NHẬN THANH TOÁN\n"
        message += f"💰 Số tiền: {amount:,}đ\n"
        message += f"📝 Mã đơn: {content}\n"
        message += f"🏦 VA: {va}\n"
        message += f"⏰ Thời gian: {time}"
        
        if BOT_TOKEN != "YOUR_BOT_TOKEN":
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": CHAT_ID, "text": message})
        
        # 5. Logic duyệt đơn hàng ở đây (so khớp với database)
        # ...
        
        return "OK", 200
        
    except Exception as e:
        app.logger.error(f"Lỗi: {e}")
        return "Error", 500

@app.route('/webhook', methods=['GET'])
def webhook_get():
    return "Webhook đang hoạt động! Chỉ chấp nhận POST từ ThueAPI.", 200

@app.route('/')
def home():
    return "Webhook server đang chạy!", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)