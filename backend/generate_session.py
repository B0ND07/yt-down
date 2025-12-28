import asyncio
import os
import sys

# Add current directory to path to allow imports if run from backend/
sys.path.append(os.getcwd())

# Attempt to load config - assuming script is run from project root or backend/
try:
    from app.config import TELEGRAM_API_ID, TELEGRAM_API_HASH
except ImportError:
    # Try adding parent dir if run from backend/
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from app.config import TELEGRAM_API_ID, TELEGRAM_API_HASH
    except ImportError:
        print("❌ Could not import config. Please run this script from the project root.")
        sys.exit(1)

from pyrogram import Client

async def main():
    print("🚀 Starting Session Generator...")
    
    # Allow manual input if config is missing
    api_id = TELEGRAM_API_ID
    api_hash = TELEGRAM_API_HASH
    
    if not api_id:
        api_id = input("Enter API ID: ")
    if not api_hash:
        api_hash = input("Enter API HASH: ")

    print(f"🔹 Using API ID: {api_id}")
    
    # Initialize client (interactive)
    # in_memory=True to avoid creating .session file
    app = Client(
        "temp_session_gen",
        api_id=int(api_id),
        api_hash=api_hash,
        in_memory=True
    )

    print("\n👉 You will be asked to enter your phone number and OTP.")
    
    try:
        await app.start()
        
        # Export
        session_str = await app.export_session_string()
        
        print("\n" + "="*50)
        print("✅ NEW SESSION STRING:")
        print("="*50)
        print(session_str)
        print("="*50 + "\n")
        
        print("📋 Copy the string above and update your .env file or config:")
        print(f"TELEGRAM_SESSION_STRING={session_str}\n")
        
        await app.stop()
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
