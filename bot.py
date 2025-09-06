import os
import logging
import requests
from typing import List, Dict, Optional
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# ĐỌC BIẾN MÔI TRƯỜNG
# =========================
TOKEN        = os.getenv("BOT_TOKEN", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROUP_ID     = os.getenv("GROUP_ID", "").strip()

# =========================
# LOGGING
# =========================
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("tg-groq-bot")

def mask(s: str, keep: int = 6) -> str:
    return s[:keep] + "..." if s else ""

logger.info("Bot khởi động. Token: %s", mask(TOKEN))
logger.info("Groq key: %s", mask(GROQ_API_KEY))
logger.info("Group ID: %s", GROUP_ID or "Không giới hạn")

# =========================
# GROQ CONFIG
# =========================
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
GROQ_CHAT_URL   = "https://api.groq.com/openai/v1/chat/completions"
CURRENT_MODEL: Optional[str] = None

PRIORITY_KEYWORDS = ["llama-4", "llama-3", "mistral", "gemma", "openchat", "chat"]
BLACKLIST         = ["embed", "embedding", "vision", "whisper", "tts", "audio", "moderation"]
MAX_REPLY_CHARS   = 3500

def _groq_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

def fetch_available_models() -> List[str]:
    try:
        resp = requests.get(GROQ_MODELS_URL, headers=_groq_headers(), timeout=20)
        if resp.status_code != 200:
            logger.warning("Lỗi lấy models: %s - %s", resp.status_code, resp.text)
            return []
        data = resp.json()
        return [m.get("id") for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]
    except Exception as e:
        logger.error("Lỗi kết nối Groq: %s", e)
        return []

def pick_best_model(model_ids: List[str]) -> Optional[str]:
    filtered = [mid for mid in model_ids if not any(b in mid.lower() for b in BLACKLIST)]
    if not filtered:
        filtered = model_ids
    for kw in PRIORITY_KEYWORDS:
        for mid in filtered:
            if kw in mid.lower():
                return mid
    return filtered[0] if filtered else None

def ensure_model(force_refresh: bool = False) -> Optional[str]:
    global CURRENT_MODEL
    if CURRENT_MODEL is None or force_refresh:
        ids = fetch_available_models()
        CURRENT_MODEL = pick_best_model(ids)
        logger.info("Mô hình Groq: %s", CURRENT_MODEL or "Không tìm thấy")
    return CURRENT_MODEL

def call_groq_chat(messages: List[Dict[str, str]], retry: bool = True) -> str:
    model = ensure_model()
    if not model:
        return "⚠️ Không tìm thấy mô hình AI khả dụng."

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.6,
        "top_p": 0.9,
        "stream": False,
    }

    try:
        resp = requests.post(GROQ_CHAT_URL, headers=_groq_headers(), json=payload, timeout=30)
    except Exception as e:
        return f"⚠️ Không thể kết nối AI: {e}"

    if resp.status_code == 200:
        try:
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            return f"⚠️ Lỗi phân tích phản hồi AI: {e}"

    err_text = ""
    try:
        err_json = resp.json()
        err_text = err_json.get("error", {}).get("message", "") or resp.text
    except Exception:
        err_text = resp.text

    model_issue_signals = [
        "decommissioned", "no longer supported", "does not exist",
        "not found", "unknown model"
    ]
    if resp.status_code == 400 and retry and any(sig in err_text.lower() for sig in model_issue_signals):
        logger.warning("Mô hình bị ngừng: %s → refresh...", model)
        ensure_model(force_refresh=True)
        return call_groq_chat(messages, retry=False)

    if resp.status_code == 401:
        return "🔒 API key không hợp lệ hoặc đã hết hạn."
    if resp.status_code == 403:
        return "🚫 Không có quyền truy cập mô hình."
    if resp.status_code == 429:
        return "⏳ Quá giới hạn tốc độ. Vui lòng thử lại sau."
    if resp.status_code >= 500:
        return "⚠️ Lỗi hệ thống phía AI. Vui lòng thử lại sau."
    return f"❌ Lỗi không xác định: {resp.status_code}\n{err_text}"

def build_messages(user_text: str) -> List[Dict[str, str]]:
    system_prompt = (
        "Bạn là một trợ lý AI thân thiện, trả lời bằng tiếng Việt, rõ ràng, "
        "thực dụng, ngắn gọn nhưng đủ ý. Khi cần, hãy đưa ra các bước hoặc gợi ý cụ thể."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text.strip()},
    ]

# =========================
# HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    model = ensure_model()
    msg = "✅ Bot đã online."
    msg += f"\n🤖 Mô hình: {model}" if model else "\nℹ️ Không chọn được mô hình AI."
    await update.message.reply_text(msg)

async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    model = ensure_model()
    await update.message.reply_text(f"🤖 Mô hình hiện tại: {model or 'Chưa có'}")

async def cmd_refresh_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    model = ensure_model(force_refresh=True)
    await update.message.reply_text(f"🔄 Đã làm mới mô hình: {model or 'Không tìm thấy'}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if GROUP_ID and chat_id != GROUP_ID:
        return  # chỉ phản hồi trong nhóm được chỉ định

    text = (update.message.text or "").strip()
    if not text:
        return

    messages = build_messages(text)
    ai_reply = call_groq_chat(messages)
    if len(ai_reply) > MAX_REPLY_CHARS:
        ai_reply = ai_reply[:MAX_REPLY_CHARS] + "\n\n…(đã rút gọn)"
    await update.message.reply_text(ai_reply or "⚠️ Không nhận được phản hồi từ AI.")

# =========================
# MAIN
# =========================
def main():
    ensure_model(force_refresh=True)
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("refreshmodel", cmd_refresh_model))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()

if __name__ == "__main__":
    main()
