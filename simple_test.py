#!/usr/bin/env python3
"""Simple test for prayer times API with different date formats"""

import asyncio
import aiohttp
from datetime import datetime, timedelta
import pytz

async def test_simple():
    print("Testing prayer times API...")
    
    # Test coordinates API which might be more reliable
    url = "https://api.aladhan.com/v1/timings"
    today = datetime.now()
    tomorrow = today + timedelta(days=1)
    
    # Test today
    params_today = {
        'latitude': 30.0444,  # Cairo
        'longitude': 31.2357,
        'method': 3,
        'date': today.strftime('%d-%m-%Y')
    }
    
    print(f"Testing today ({today.strftime('%d-%m-%Y')})...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params_today) as response:
                if response.status == 200:
                    data = await response.json()
                    date_returned = data['data']['date']['readable']
                    fajr = data['data']['timings']['Fajr']
                    asr = data['data']['timings']['Asr']
                    print(f"Today - Date returned: {date_returned}")
                    print(f"Today - Fajr: {fajr}, Asr: {asr}")
                else:
                    print(f"Failed: {response.status}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test tomorrow
    params_tomorrow = {
        'latitude': 30.0444,  # Cairo
        'longitude': 31.2357,
        'method': 3,
        'date': tomorrow.strftime('%d-%m-%Y')
    }
    
    print(f"\nTesting tomorrow ({tomorrow.strftime('%d-%m-%Y')})...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params_tomorrow) as response:
                if response.status == 200:
                    data = await response.json()
                    date_returned = data['data']['date']['readable']
                    fajr = data['data']['timings']['Fajr']
                    asr = data['data']['timings']['Asr']
                    print(f"Tomorrow - Date returned: {date_returned}")
                    print(f"Tomorrow - Fajr: {fajr}, Asr: {asr}")
                else:
                    print(f"Failed: {response.status}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_simple())
