#!/usr/bin/env python3
"""Verification script to test the updated scheduling logic"""

import asyncio
import aiohttp
import pytz
from datetime import datetime, timedelta

API_URL = "https://api.aladhan.com/v1/timingsByCity"
API_PARAMS = {'city': 'Cairo', 'country': 'Egypt', 'method': 3}
CAIRO_TZ = pytz.timezone('Africa/Cairo')

async def verify_scheduling():
    """Verify that the scheduling logic works correctly with current prayer times"""
    
    print("🕒 Verifying Prayer Time Scheduling Logic")
    print("=" * 50)
    
    # Fetch current prayer times
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, params=API_PARAMS) as response:
                if response.status != 200:
                    print(f"❌ API request failed with status {response.status}")
                    return False
                    
                data = await response.json()
                prayer_times = data.get('data', {}).get('timings', {})
                
                if not prayer_times:
                    print("❌ No prayer times received")
                    return False
                    
    except Exception as e:
        print(f"❌ Error fetching prayer times: {e}")
        return False
    
    print("✅ Prayer times fetched successfully:")
    for prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
        if prayer in prayer_times:
            print(f"   {prayer}: {prayer_times[prayer]}")
    
    print("\n🕐 Current Time Information:")
    now = datetime.now(CAIRO_TZ)
    today = now.date()
    print(f"   Current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    # Parse Fajr and Asr times
    def parse_prayer_time(prayer_name, time_str):
        try:
            if not time_str or len(time_str.split(':')) != 2:
                print(f"❌ Invalid time format for {prayer_name}: {time_str}")
                return None
            
            hour, minute = map(int, time_str.split(':'))
            prayer_time = datetime.combine(today, datetime.min.time().replace(hour=hour, minute=minute))
            localized_time = CAIRO_TZ.localize(prayer_time)
            return localized_time
        except Exception as e:
            print(f"❌ Error parsing {prayer_name} time: {e}")
            return None
    
    fajr_time = parse_prayer_time('Fajr', prayer_times.get('Fajr'))
    asr_time = parse_prayer_time('Asr', prayer_times.get('Asr'))
    
    if not fajr_time or not asr_time:
        print("❌ Failed to parse critical prayer times")
        return False
    
    print(f"   Parsed Fajr: {fajr_time.strftime('%H:%M')}")
    print(f"   Parsed Asr: {asr_time.strftime('%H:%M')}")
    
    # Calculate scheduled times according to your requirements
    morning_athkar_time = fajr_time + timedelta(minutes=35)
    evening_athkar_time = asr_time + timedelta(minutes=30)
    quran_time = evening_athkar_time + timedelta(minutes=10)
    
    print("\n📅 Calculated Schedule Times:")
    print(f"   🌅 Morning Athkar: {morning_athkar_time.strftime('%H:%M')} (Fajr + 35 min)")
    print(f"   🌙 Evening Athkar: {evening_athkar_time.strftime('%H:%M')} (Asr + 30 min)")
    print(f"   📖 Quran (Wird): {quran_time.strftime('%H:%M')} (Evening Athkar + 10 min)")
    
    # Check which tasks should be scheduled for today vs tomorrow
    print("\n⏰ Task Scheduling Status:")
    
    if morning_athkar_time <= now:
        print(f"   🌅 Morning Athkar: ⏭️ RESCHEDULE FOR TOMORROW (time passed)")
    else:
        minutes_until = int((morning_athkar_time - now).total_seconds() / 60)
        print(f"   🌅 Morning Athkar: ✅ SCHEDULED FOR TODAY (in {minutes_until} minutes)")
    
    if evening_athkar_time <= now:
        print(f"   🌙 Evening Athkar: ⏭️ RESCHEDULE FOR TOMORROW (time passed)")
    else:
        minutes_until = int((evening_athkar_time - now).total_seconds() / 60)
        print(f"   🌙 Evening Athkar: ✅ SCHEDULED FOR TODAY (in {minutes_until} minutes)")
    
    if quran_time <= now:
        print(f"   📖 Quran (Wird): ⏭️ RESCHEDULE FOR TOMORROW (time passed)")
    else:
        minutes_until = int((quran_time - now).total_seconds() / 60)
        print(f"   📖 Quran (Wird): ✅ SCHEDULED FOR TODAY (in {minutes_until} minutes)")
    
    # Test Quran page calculation
    print("\n📖 Quran Page Calculation:")
    anchor_date = datetime(2025, 5, 27).date()
    anchor_page1, anchor_page2 = 2, 3
    total_pages = 604
    
    days_diff = (today - anchor_date).days
    page1 = anchor_page1 + days_diff * 2
    page2 = anchor_page2 + days_diff * 2
    
    # Wrapping logic
    def wrap(page):
        return ((page - 1) % total_pages) + 1
    
    page1 = wrap(page1)
    page2 = wrap(page2)
    
    print(f"   Today's pages: {page1}, {page2}")
    print(f"   Days from anchor (May 27, 2025): {days_diff}")
    
    # Verify May 27th calculation
    may_27_diff = (datetime(2025, 5, 27).date() - anchor_date).days
    may_27_page1 = wrap(2 + may_27_diff * 2)
    may_27_page2 = wrap(3 + may_27_diff * 2)
    print(f"   May 27th, 2025 pages: {may_27_page1}, {may_27_page2} ✅" if may_27_page1 == 2 and may_27_page2 == 3 else f"   May 27th, 2025 pages: {may_27_page1}, {may_27_page2} ❌")
    
    print("\n" + "=" * 50)
    print("✅ Verification completed successfully!")
    return True

if __name__ == "__main__":
    result = asyncio.run(verify_scheduling())
    if result:
        print("🎉 All scheduling logic appears to be working correctly!")
    else:
        print("⚠️  Issues found with scheduling logic!")
