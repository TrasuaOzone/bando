from flask import Flask, request, jsonify
import mysql.connector
import bcrypt
import smtplib
from email.mime.text import MIMEText
import random
import string
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ===== Đọc biến môi trường =====
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")

# ===== Kết nối database =====
def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME
    )

# ===== Gửi email =====
def send_email(to_email, subject, body):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

# ===== API: Đăng ký =====
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()
    password = data.get("password", "")

    if not email or not phone or not password:
        return jsonify({"ok": False, "error": "Thiếu thông tin"}), 400

    hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (email, phone, password) VALUES (%s, %s, %s)",
            (email, phone, hashed_pw),
        )
        conn.commit()
        return jsonify({"ok": True, "message": "Đăng ký thành công"}), 201
    except mysql.connector.Error as err:
        return jsonify({"ok": False, "error": str(err)}), 400
    finally:
        cursor.close()
        conn.close()

# ===== API: Đăng nhập =====
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    phone = data.get("phone", "").strip()
    password = data.get("password", "")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE phone = %s", (phone,))
    user = cursor.fetchone()

    if user and bcrypt.checkpw(password.encode("utf-8"), user["password"].encode("utf-8")):
        return jsonify({"ok": True, "message": "Đăng nhập thành công", "user": {
            "id": user["id"],
            "email": user["email"],
            "phone": user["phone"]
        }})
    else:
        return jsonify({"ok": False, "error": "Sai SĐT hoặc mật khẩu"}), 401

# ===== API: Quên mật khẩu =====
@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json()
    email = data.get("email", "").strip()

    new_pw = "".join(random.choices(string.ascii_letters + string.digits, k=8))
    hashed_pw = bcrypt.hashpw(new_pw.encode("utf-8"), bcrypt.gensalt())

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET password = %s WHERE email = %s", (hashed_pw, email))
    conn.commit()

    if cursor.rowcount == 0:
        return jsonify({"ok": False, "error": "Email không tồn tại"}), 404

    send_email(email, "Mật khẩu mới", f"Mật khẩu mới của bạn là: {new_pw}")
    return jsonify({"ok": True, "message": "Mật khẩu mới đã được gửi qua email"})

# ===== Chạy app trên Render =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
