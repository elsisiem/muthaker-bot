#!/usr/bin/env python3
"""Synchronous test for prayer times API"""

import requests
from datetime import datetime, timedelta

def test_prayer_api():
    print("Testing prayer times API with requests...")
    
    # Test coordinates API
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
        response = requests.get(url, params=params_today, timeout=10)
        if response.status_code == 200:
            data = response.json()
            date_returned = data['data']['date']['readable']
            fajr = data['data']['timings']['Fajr']
            asr = data['data']['timings']['Asr']
            print(f"Today - Date returned: {date_returned}")
            print(f"Today - Fajr: {fajr}, Asr: {asr}")
        else:
            print(f"Failed: {response.status_code}")
            print(f"Response: {response.text}")
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
        response = requests.get(url, params=params_tomorrow, timeout=10)
        if response.status_code == 200:
            data = response.json()
            date_returned = data['data']['date']['readable']
            fajr = data['data']['timings']['Fajr']
            asr = data['data']['timings']['Asr']
            print(f"Tomorrow - Date returned: {date_returned}")
            print(f"Tomorrow - Fajr: {fajr}, Asr: {asr}")
            
            # Compare with today
            if date_returned != today.strftime('%d %B %Y'):
                print("✅ API is working correctly - returns different dates")
            else:
                print("⚠️ API still returning same date")
        else:
            print(f"Failed: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_prayer_api()
