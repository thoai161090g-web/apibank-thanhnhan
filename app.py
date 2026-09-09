from datetime import datetime
import hashlib
import hmac
import os
import re
import threading
from flask import Flask, jsonify, request
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

# ----------------------------------------------------
# 1. CẤU HÌNH THÔNG TIN CHÍNH THỨC CỦA BẠN
# ----------------------------------------------------
API_TOKEN = os.getenv('BOT_TOKEN', '8781551901:AAES4zYAz-QXJ4uCPJPkqWcHYy0e54_aF_c')

# Secret Key từ ThueAPI của bạn
THUEAPI_SECRET = os.getenv(
    'THUEAPI_SECRET', 'LqYHCWAmHmFaaRxJKx4HPfvi2dE7CMJa'
)

# Thông tin tài khoản nhận tiền
STK = '8887596710'
TEN_CTK = 'NGUYEN THANH NHAN'
NGAN_HANG = 'BIDV'  # Nếu dùng ngân hàng khác (VD: Vietcombank, Techcombank...), hãy sửa tên mã ngân hàng tại đây

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

pending_orders = {}

# ----------------------------------------------------
# 2. XỬ LÝ KHÁCH HÀNG TRÊN TELEGRAM
# ----------------------------------------------------


@bot.message_handler(commands=['start'])
def send_welcome(message):
  markup = InlineKeyboardMarkup()
  btn = InlineKeyboardButton('Mua Tool 1 Ngày (10.000đ)', callback_data='buy_1d')
  markup.add(btn)
  bot.reply_to(
      message,
      'Chào mừng bạn đến với Bot Bán Tool!\nChọn gói bên dưới để thanh toán:',
      reply_markup=markup,
  )


@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def handle_buy(call):
  chat_id = call.message.chat.id
  amount = 10000 if call.data == 'buy_1d' else 50000

  # Nội dung chuyển khoản bắt buộc có ID Telegram của khách: NAP <chat_id>
  memo = f'NAP {chat_id}'

  # Tạo Mã VietQR tự động khớp với STK và Tên của bạn
  qr_url = f'https://img.vietqr.io/image/{NGAN_HANG}-{STK}-compact2.png?amount={amount}&addInfo={memo}&accountName={TEN_CTK}'

  msg = (
      f'<b>THÔNG TIN THANH TOÁN TỰ ĐỘNG</b>\n'
      f'-----------------------------------\n'
      f'🏦 Ngân hàng: <b>{NGAN_HANG}</b>\n'
      f'💳 Số tài khoản: <code>{STK}</code>\n'
      f'👤 Chủ tài khoản: <b>{TEN_CTK}</b>\n'
      f'💰 Số tiền: <b>{amount:,} VNĐ</b>\n'
      f'📝 Nội dung CK: <code>{memo}</code>\n'
      f'-----------------------------------\n'
      f'⚠️ <i>Vui lòng giữ nguyên nội dung chuyển khoản để hệ thống duyệt tự động trong 3 giây!</i>'
  )

  bot.send_photo(chat_id, photo=qr_url, caption=msg, parse_mode='HTML')


# ----------------------------------------------------
# 3. NHẬN BÁO CÓ TỪ THUEAPI ĐỂ DUYỆT TỰ ĐỘNG
# ----------------------------------------------------


@app.route('/')
def home():
  return 'Server Webhook & Bot Telegram đang chạy ổn định!'


@app.route('/webhook', methods=['POST'])
def handle_webhook():
  signature = request.headers.get('X-Webhook-Signature')
  raw_data = request.get_data()

  # Xác thực dữ liệu từ ThueAPI bằng Secret Key
  if THUEAPI_SECRET and signature:
    expected = hmac.new(
        THUEAPI_SECRET.encode(), raw_data, hashlib.sha256
    ).hexdigest()
    if signature != expected:
      return jsonify({'error': 'Xác thực Secret Key thất bại'}), 400

  data = request.json or {}
  amount = float(data.get('amount', 0))
  content = data.get('content', '').upper()

  # Bóc tách ID Telegram khách hàng từ nội dung giao dịch (VD: NAP 12345678)
  match = re.search(r'NAP\s*(\d+)', content)
  if match:
    telegram_id = match.group(1)

    # Tạo mã Key trả về cho khách
    key_code = (
        f"KEY-VIP-{datetime.now().strftime('%Y%m%d')}-{telegram_id[-4:]}"
    )

    text_success = (
        f'✅ <b>XÁC NHẬN THANH TOÁN THÀNH CÔNG!</b>\n\n'
        f'💰 Số tiền nhận: <b>{amount:,.0f} VNĐ</b>\n'
        f'🔑 Mã Key kích hoạt: <code>{key_code}</code>\n\n'
        f'🎉 Cảm ơn bạn đã mua hàng, chúc bạn trải nghiệm vui vẻ!'
    )

    try:
      bot.send_message(telegram_id, text_success, parse_mode='HTML')
    except Exception as e:
      print(f'Lỗi gửi tin nhắn cho khách {telegram_id}: {e}')

  return jsonify({'status': 'success'}), 200


# ----------------------------------------------------
# 4. CHẠY SONG SONG BOT VÀ WEB SERVER
# ----------------------------------------------------
if __name__ == '__main__':
  threading.Thread(
      target=bot.infinity_polling, kwargs={'skip_pending': True}, daemon=True
  ).start()

  port = int(os.environ.get('PORT', 5000))
  app.run(host='0.0.0.0', port=port)