from flask import Flask, request
import requests
import json
import logging

app = Flask(__name__)

# Cấu hình logging để xem log trên Render
logging.basicConfig(level=logging.INFO)

# === THAY THÔNG TIN BOT CỦA BẠN VÀO ĐÂY ===
BOT_TOKEN = "YOUR_BOT_TOKEN"  # Thay bằng token của bot Telegram
CHAT_ID = "YOUR_CHAT_ID"      # Thay bằng ID chat cần gửi thông báo
# ===========================================

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        app.logger.info(f"Nhận dữ liệu: {data}")
        
        # Lấy thông tin từ ThueAPI gửi sang
        va = data.get('va', '')
        amount = data.get('amount', 0)
        content = data.get('content', '')
        time = data.get('time', '')
        
        # Xử lý logic ở đây:
        # - Lấy mã đơn hàng từ content (nội dung chuyển khoản)
        # - So khớp với database đơn hàng
        # - Nếu khớp số tiền -> duyệt đơn
        
        # Gửi thông báo về Telegram
        message = f"✅ NHẬN THANH TOÁN\n"
        message += f"💰 Số tiền: {amount:,}đ\n"
        message += f"📝 Mã đơn: {content}\n"
        message += f"🏦 VA: {va}\n"
        message += f"⏰ Thời gian: {time}"
        
        if BOT_TOKEN != "YOUR_BOT_TOKEN":
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(url, json={
                "chat_id": CHAT_ID,
                "text": message
            })
        
        return "OK", 200
        
    except Exception as e:
        app.logger.error(f"Lỗi: {e}")
        return "Error", 500

@app.route('/')
def home():
    return "Webhook server đang chạy!", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)