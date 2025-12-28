"""
Direct Pyrogram Session Generator
Generates a Pyrogram session string directly (no conversion needed)
"""
from pyrogram import Client

API_ID = 
API_HASH = ""

print("=" * 70)
print("📱 PYROGRAM SESSION GENERATOR")
print("=" * 70)
print("\nThis will create a Pyrogram session string.")
print("\nYou'll need to enter:")
print("  1. Phone number (with country code, e.g., +919876543210)")
print("  2. Verification code from Telegram")
print("  3. 2FA password (if enabled)")
print("\n" + "=" * 70)
print("\nStarting in 3 seconds...")

import time
time.sleep(3)

try:
    # Create Pyrogram client
    app = Client(
        "my_pyrogram_session",
        api_id=API_ID,
        api_hash=API_HASH
    )
    
    print("\n🔄 Connecting to Telegram...\n")
    
    # Start the client (this will ask for phone, code, password)
    with app:
        # Export session string
        session_string = app.export_session_string()
        
        print("\n" + "=" * 70)
        print("✅ SUCCESS! PYROGRAM SESSION STRING GENERATED")
        print("=" * 70)
        print("\n📋 Your Pyrogram session string:\n")
        print(session_string)
        print("\n" + "=" * 70)
        print("\n📝 NEXT STEPS:")
        print("\n1. Copy the session string above")
        print("\n2. Update config.py line 26:")
        print(f'   TELEGRAM_SESSION_STRING = os.getenv("TELEGRAM_SESSION_STRING","{session_string}")')
        print("\n3. Restart your bot:")
        print("   python main.py")
        print("\n" + "=" * 70)
        print("\n✅ Session generated successfully!")
        print("=" * 70)
    
    # Clean up session file
    import os
    try:
        if os.path.exists("my_pyrogram_session.session"):
            os.remove("my_pyrogram_session.session")
            print("\n🧹 Cleaned up temporary files")
    except:
        pass
        
except KeyboardInterrupt:
    print("\n\n⚠️ Cancelled by user")
except Exception as e:
    print(f"\n❌ Error: {e}")
    print(f"Error type: {type(e).__name__}")
    
    import traceback
    traceback.print_exc()
    
    print("\n💡 Troubleshooting:")
    print("  - Make sure you have internet connection")
    print("  - Enter phone number with country code (+919876543210)")
    print("  - Check the verification code from Telegram")
