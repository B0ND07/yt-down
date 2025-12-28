"""Telegram bot webhook routes (optional - for webhook mode)"""
from fastapi import APIRouter, Request, HTTPException
from telegram import Update
from app.services.telegram_service import TelegramService
from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_ENABLED

router = APIRouter(prefix="/telegram", tags=["telegram"])

# Initialize bot service if enabled
bot_service = None
if TELEGRAM_BOT_ENABLED and TELEGRAM_BOT_TOKEN:
    bot_service = TelegramService(TELEGRAM_BOT_TOKEN)


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """Webhook endpoint for Telegram bot (if using webhook mode instead of polling)"""
    if not bot_service or not bot_service.application:
        raise HTTPException(status_code=503, detail="Telegram bot not initialized")
    
    try:
        update = Update.de_json(await request.json(), bot_service.application.bot)
        await bot_service.application.process_update(update)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/status")
async def telegram_status():
    """Get Telegram bot status"""
    return {
        "enabled": TELEGRAM_BOT_ENABLED,
        "initialized": bot_service is not None and bot_service.application is not None
    }
