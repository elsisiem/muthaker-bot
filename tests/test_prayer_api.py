#!/usr/bin/env python3
"""Test script to verify prayer times API is working"""

import asyncio
import aiohttp
import json
from datetime import datetime
import pytz

API_URL = "https://api.aladhan.com/v1/timingsByCity"
API_PARAMS = {'city': 'Cairo', 'country': 'Egypt', 'method': 3}
CAIRO_TZ = pytz.timezone('Africa/Cairo')

async def test_prayer_api():
    try:
        print("Testing prayer times API...")
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, params=API_PARAMS) as response:
                print(f"Response status: {response.status}")
                
                if response.status != 200:
                    print(f"API request failed with status {response.status}")
                    return False
                    
                data = await response.json()
                print(f"Response data keys: {list(data.keys())}")
                
                if 'data' in data:
                    timings = data['data'].get('timings', {})
                    print(f"Prayer times for today:")
                    for prayer, time in timings.items():
                        if prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
                            print(f"  {prayer}: {time}")
                    
                    # Test parsing
                    now = datetime.now(CAIRO_TZ)
                    today = now.date()
                    
                    for prayer in ['Fajr', 'Asr']:
                        time_str = timings.get(prayer)
                        if time_str:
                            try:
                                hour, minute = map(int, time_str.split(':'))
                                prayer_time = datetime.combine(today, datetime.min.time().replace(hour=hour, minute=minute))
                                localized_time = CAIRO_TZ.localize(prayer_time)
                                print(f"  Parsed {prayer}: {localized_time}")
                            except Exception as e:
                                print(f"  Error parsing {prayer}: {e}")
                    
                    return True
                else:
                    print("No 'data' key in response")
                    print(f"Full response: {json.dumps(data, indent=2)}")
                    return False
                    
    except Exception as e:
        print(f"Error testing API: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_prayer_api())
    if result:
        print("✅ Prayer times API test passed")
    else:
        print("❌ Prayer times API test failed")
