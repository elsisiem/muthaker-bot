#!/usr/bin/env python3
"""Test script to verify prayer times API is dynamic across multiple dates"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
import pytz

API_URL = "https://api.aladhan.com/v1/timingsByCity"
CAIRO_TZ = pytz.timezone('Africa/Cairo')

async def test_prayer_api_for_date(date_str):
    """Test prayer times API for a specific date"""
    try:
        # Format: DD-MM-YYYY
        params = {
            'city': 'Cairo', 
            'country': 'Egypt', 
            'method': 3,
            'date': date_str
        }
        
        print(f"\n📅 Testing for date: {date_str}")
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, params=params) as response:
                print(f"Response status: {response.status}")
                
                if response.status != 200:
                    print(f"❌ API request failed with status {response.status}")
                    return None
                    
                data = await response.json()
                
                if 'data' in data:
                    timings = data['data'].get('timings', {})
                    date_info = data['data'].get('date', {})
                    
                    print(f"✅ Prayer times for {date_info.get('readable', date_str)}:")
                    prayer_times = {}
                    for prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
                        time = timings.get(prayer, 'N/A')
                        print(f"  {prayer}: {time}")
                        prayer_times[prayer] = time
                    
                    return prayer_times
                else:
                    print("❌ No 'data' key in response")
                    return None
                    
    except Exception as e:
        print(f"❌ Error testing API for {date_str}: {e}")
        return None

async def test_multiple_dates():
    """Test prayer times for multiple dates to verify dynamism"""
    print("🔍 Testing Prayer Times API for Multiple Dates")
    print("=" * 50)
    
    today = datetime.now(CAIRO_TZ).date()
    
    # Test for today and next 5 days
    test_dates = []
    for i in range(6):
        test_date = today + timedelta(days=i)
        date_str = test_date.strftime('%d-%m-%Y')
        test_dates.append((test_date, date_str))
    
    all_results = {}
    
    for test_date, date_str in test_dates:
        result = await test_prayer_api_for_date(date_str)
        if result:
            all_results[date_str] = result
        await asyncio.sleep(0.5)  # Be nice to the API
    
    # Analyze results for dynamism
    print("\n🔍 ANALYSIS: Checking for Dynamic Times")
    print("=" * 50)
    
    if len(all_results) < 2:
        print("❌ Not enough data to compare")
        return False
    
    # Check if Fajr and Asr times are changing
    fajr_times = set()
    asr_times = set()
    
    for date_str, times in all_results.items():
        if 'Fajr' in times:
            fajr_times.add(times['Fajr'])
        if 'Asr' in times:
            asr_times.add(times['Asr'])
    
    print(f"Unique Fajr times found: {len(fajr_times)}")
    for time in sorted(fajr_times):
        print(f"  - {time}")
    
    print(f"\nUnique Asr times found: {len(asr_times)}")
    for time in sorted(asr_times):
        print(f"  - {time}")
    
    is_dynamic = len(fajr_times) > 1 or len(asr_times) > 1
    
    if is_dynamic:
        print("\n✅ API IS DYNAMIC - Prayer times change across dates")
    else:
        print("\n⚠️  API APPEARS STATIC - Same times for all dates")
        print("This might indicate an issue with the API or our request format")
    
    return is_dynamic

async def test_current_api_implementation():
    """Test the exact API call that our bot uses"""
    print("\n🤖 Testing Current Bot API Implementation")
    print("=" * 50)
    
    # This is exactly what our bot does
    API_PARAMS = {'city': 'Cairo', 'country': 'Egypt', 'method': 3}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, params=API_PARAMS) as response:
                print(f"Response status: {response.status}")
                
                if response.status != 200:
                    print(f"❌ API request failed with status {response.status}")
                    return False
                    
                data = await response.json()
                timings = data.get('data', {}).get('timings')
                date_info = data.get('data', {}).get('date', {})
                
                if not timings:
                    print("❌ No timings in response")
                    return False
                
                print(f"✅ Current API call returns:")
                print(f"Date: {date_info.get('readable', 'Unknown')}")
                print(f"Gregorian: {date_info.get('gregorian', {}).get('date', 'Unknown')}")
                
                for prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
                    time = timings.get(prayer, 'N/A')
                    print(f"  {prayer}: {time}")
                
                return True
                
    except Exception as e:
        print(f"❌ Error in current API test: {e}")
        return False

if __name__ == "__main__":
    async def main():
        print("🕌 Prayer Times API Dynamic Test")
        print("=" * 50)
        
        # Test current implementation
        current_works = await test_current_api_implementation()
        
        if not current_works:
            print("❌ Current API implementation has issues!")
            return
        
        # Test multiple dates
        is_dynamic = await test_multiple_dates()
        
        if not is_dynamic:
            print("\n💡 RECOMMENDATION:")
            print("Consider adding explicit date parameter to ensure fresh data")
            print("Current API call might be cached or always returning 'today'")
        else:
            print("\n✅ API is working correctly and returns dynamic times")
    
    asyncio.run(main())
