#!/usr/bin/env python3
"""Test alternative API endpoints and date formats"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
import pytz

CAIRO_TZ = pytz.timezone('Africa/Cairo')

async def test_alternative_api_formats():
    """Test different API endpoints and date formats"""
    
    today = datetime.now(CAIRO_TZ)
    tomorrow = today + timedelta(days=1)
    
    # Different API endpoints to try
    test_configs = [
        {
            "name": "Original API with DD-MM-YYYY",
            "url": "https://api.aladhan.com/v1/timingsByCity",
            "params": {
                'city': 'Cairo', 
                'country': 'Egypt', 
                'method': 3,
                'date': today.strftime('%d-%m-%Y')
            }
        },
        {
            "name": "Original API with YYYY-MM-DD",
            "url": "https://api.aladhan.com/v1/timingsByCity",
            "params": {
                'city': 'Cairo', 
                'country': 'Egypt', 
                'method': 3,
                'date': today.strftime('%Y-%m-%d')
            }
        },
        {
            "name": "Calendar API endpoint",
            "url": "https://api.aladhan.com/v1/calendar",
            "params": {
                'city': 'Cairo', 
                'country': 'Egypt', 
                'method': 3,
                'month': today.month,
                'year': today.year
            }
        },
        {
            "name": "Timings by coordinates",
            "url": "https://api.aladhan.com/v1/timings",
            "params": {
                'latitude': 30.0444,  # Cairo coordinates
                'longitude': 31.2357,
                'method': 3,
                'date': today.strftime('%d-%m-%Y')
            }
        }
    ]
    
    print("🕌 Testing Alternative Prayer Times API Endpoints")
    print("=" * 70)
    
    for config in test_configs:
        print(f"\n{'='*20} {config['name']} {'='*20}")
        print(f"URL: {config['url']}")
        print(f"Parameters: {config['params']}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(config['url'], params=config['params']) as response:
                    print(f"Response status: {response.status}")
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Handle different response formats
                        if config['name'] == "Calendar API endpoint":
                            # Calendar API returns array of days
                            if 'data' in data and len(data['data']) > 0:
                                today_data = data['data'][today.day - 1]  # Get today's data
                                if 'timings' in today_data:
                                    timings = today_data['timings']
                                    print(f"Prayer times for today:")
                                    for prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
                                        print(f"  {prayer}: {timings.get(prayer, 'N/A')}")
                        else:
                            # Regular timings API
                            if 'data' in data:
                                if 'date' in data['data']:
                                    date_info = data['data']['date']
                                    print(f"API returned date: {date_info.get('readable', 'N/A')}")
                                
                                if 'timings' in data['data']:
                                    timings = data['data']['timings']
                                    print(f"Prayer times:")
                                    for prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
                                        print(f"  {prayer}: {timings.get(prayer, 'N/A')}")
                    else:
                        text = await response.text()
                        print(f"❌ Request failed: {text[:200]}...")
                        
        except Exception as e:
            print(f"❌ Error: {e}")
        
        await asyncio.sleep(1)  # Be nice to the API

async def test_tomorrow_specifically():
    """Test if we can get tomorrow's prayer times with different approaches"""
    
    tomorrow = datetime.now(CAIRO_TZ) + timedelta(days=1)
    
    print(f"\n{'='*20} TESTING TOMORROW'S TIMES {'='*20}")
    print(f"Tomorrow's date: {tomorrow.strftime('%Y-%m-%d (%A)')}")
    
    # Try coordinates API with tomorrow's date
    params = {
        'latitude': 30.0444,  # Cairo coordinates
        'longitude': 31.2357,
        'method': 3,
        'date': tomorrow.strftime('%d-%m-%Y')
    }
    
    url = "https://api.aladhan.com/v1/timings"
    print(f"Testing: {url}")
    print(f"Parameters: {params}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                print(f"Response status: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    
                    if 'data' in data:
                        if 'date' in data['data']:
                            date_info = data['data']['date']
                            print(f"API returned date: {date_info.get('readable', 'N/A')}")
                            print(f"Expected date: {tomorrow.strftime('%d %B %Y')}")
                        
                        if 'timings' in data['data']:
                            timings = data['data']['timings']
                            print(f"Tomorrow's prayer times:")
                            for prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
                                print(f"  {prayer}: {timings.get(prayer, 'N/A')}")
                else:
                    text = await response.text()
                    print(f"❌ Request failed: {text}")
                    
    except Exception as e:
        print(f"❌ Error: {e}")

async def main():
    await test_alternative_api_formats()
    await test_tomorrow_specifically()

if __name__ == "__main__":
    asyncio.run(main())
