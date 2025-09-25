#!/usr/bin/env python3
"""
Webhook setup utility for the muthaker bot user interactions.
Run this once after deployment to set up the webhook.
"""

import os
import asyncio
import aiohttp
from telegram import Bot

async def setup_webhook():
    """Set up webhook for user interactions bot"""
    
    # Get tokens and URLs from environment
    user_bot_token = os.environ.get('USER_BOT_TOKEN', os.environ['TELEGRAM_BOT_TOKEN'])
    webhook_url = os.environ.get('WEBHOOK_URL')
    
    if not webhook_url:
        print("❌ WEBHOOK_URL environment variable not set")
        print("   Set it to your Heroku app URL (e.g., https://your-app.herokuapp.com)")
        return False
    
    # Create bot instance
    bot = Bot(token=user_bot_token)
    
    try:
        # Set webhook
        webhook_endpoint = f"{webhook_url}/webhook"
        print(f"🔗 Setting webhook to: {webhook_endpoint}")
        
        success = await bot.set_webhook(webhook_endpoint)
        
        if success:
            print("✅ Webhook set successfully!")
            
            # Get webhook info to verify
            webhook_info = await bot.get_webhook_info()
            print(f"📋 Webhook URL: {webhook_info.url}")
            print(f"📋 Pending updates: {webhook_info.pending_update_count}")
            
            return True
        else:
            print("❌ Failed to set webhook")
            return False
            
    except Exception as e:
        print(f"❌ Error setting webhook: {e}")
        return False
    finally:
        # Clean up
        session = await bot.get_session()
        if session:
            await session.close()

if __name__ == "__main__":
    print("🔧 Setting up webhook for user interactions...")
    success = asyncio.run(setup_webhook())
    if success:
        print("🎉 Setup complete!")
    else:
        print("💥 Setup failed!")
