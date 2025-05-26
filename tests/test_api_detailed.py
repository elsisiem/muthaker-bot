#!/usr/bin/env python3
"""Detailed test script to investigate prayer times API behavior"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
import pytz

API_URL = "https://api.aladhan.com/v1/timingsByCity"
CAIRO_TZ = pytz.timezone('Africa/Cairo')

async def test_api_with_date(date_str):
    """Test API with explicit date parameter"""
    params = {
        'city': 'Cairo', 
        'country': 'Egypt', 
        'method': 3,
        'date': date_str
    }
    
    print(f"\n🔍 Testing with date parameter: {date_str}")
    print(f"Request URL: {API_URL}")
    print(f"Parameters: {params}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, params=params) as response:
                print(f"Response status: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    
                    # Print the full date information from API
                    if 'data' in data and 'date' in data['data']:
                        date_info = data['data']['date']
                        print(f"API returned date info:")
                        print(f"  Readable: {date_info.get('readable', 'N/A')}")
                        print(f"  Timestamp: {date_info.get('timestamp', 'N/A')}")
                        print(f"  Gregorian: {date_info.get('gregorian', {}).get('date', 'N/A')}")
                        print(f"  Hijri: {date_info.get('hijri', {}).get('date', 'N/A')}")
                    
                    # Print prayer times
                    if 'data' in data and 'timings' in data['data']:
                        timings = data['data']['timings']
                        print(f"Prayer times:")
                        for prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
                            print(f"  {prayer}: {timings.get(prayer, 'N/A')}")
                    
                    return data
                else:
                    print(f"❌ Request failed with status {response.status}")
                    text = await response.text()
                    print(f"Response: {text}")
                    return None
                    
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

async def test_different_date_formats():
    """Test different date formats to see if API responds differently"""
    
    today = datetime.now(CAIRO_TZ)
    tomorrow = today + timedelta(days=1)
    yesterday = today - timedelta(days=1)
    
    # Test multiple date formats
    test_dates = [
        ("Today", today.strftime('%d-%m-%Y')),
        ("Tomorrow", tomorrow.strftime('%d-%m-%Y')), 
        ("Yesterday", yesterday.strftime('%d-%m-%Y')),
        ("Future date", (today + timedelta(days=30)).strftime('%d-%m-%Y')),
        ("Past date", (today - timedelta(days=30)).strftime('%d-%m-%Y'))
    ]
    
    print("🕌 Prayer Times API Detailed Test")
    print("=" * 60)
    
    results = {}
    
    for description, date_str in test_dates:
        print(f"\n{'='*20} {description} {'='*20}")
        result = await test_api_with_date(date_str)
        if result:
            results[description] = result
        await asyncio.sleep(1)  # Be nice to the API
    
    # Analyze results
    print(f"\n{'='*20} ANALYSIS {'='*20}")
    
    all_fajr_times = {}
    all_asr_times = {}
    
    for desc, data in results.items():
        if 'data' in data and 'timings' in data['data']:
            timings = data['data']['timings']
            fajr = timings.get('Fajr')
            asr = timings.get('Asr')
            
            if fajr:
                all_fajr_times[desc] = fajr
            if asr:
                all_asr_times[desc] = asr
    
    print(f"\nFajr times by date:")
    for desc, time in all_fajr_times.items():
        print(f"  {desc}: {time}")
    
    print(f"\nAsr times by date:")
    for desc, time in all_asr_times.items():
        print(f"  {desc}: {time}")
    
    unique_fajr = len(set(all_fajr_times.values()))
    unique_asr = len(set(all_asr_times.values()))
    
    print(f"\nUnique Fajr times: {unique_fajr}")
    print(f"Unique Asr times: {unique_asr}")
    
    if unique_fajr > 1 or unique_asr > 1:
        print("✅ API is dynamic - returns different times for different dates")
    else:
        print("⚠️  API appears to return same times regardless of date parameter")
        print("This could indicate:")
        print("  1. API caching issues")
        print("  2. API ignoring date parameter") 
        print("  3. Date format issues")
        print("  4. API server timezone confusion")

if __name__ == "__main__":
    asyncio.run(test_different_date_formats())
