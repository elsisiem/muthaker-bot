#!/usr/bin/env python3
"""Comprehensive test for prayer times API to get to the bottom of the issue"""

import requests
import json
from datetime import datetime, timedelta
import time

def test_prayer_api_comprehensive():
    print("🕌 COMPREHENSIVE PRAYER TIMES API INVESTIGATION")
    print("=" * 60)
    
    # Test multiple API endpoints
    endpoints = [
        {
            'name': 'City-based API',
            'url': 'https://api.aladhan.com/v1/timingsByCity',
            'params_base': {'city': 'Cairo', 'country': 'Egypt', 'method': 3}
        },
        {
            'name': 'Coordinates API', 
            'url': 'https://api.aladhan.com/v1/timings',
            'params_base': {'latitude': 30.0444, 'longitude': 31.2357, 'method': 3}
        }
    ]
    
    # Test dates
    today = datetime.now()
    test_dates = [
        ('Today', today.strftime('%d-%m-%Y')),
        ('Tomorrow', (today + timedelta(days=1)).strftime('%d-%m-%Y')),
        ('Next week', (today + timedelta(days=7)).strftime('%d-%m-%Y')),
        ('Next month', (today + timedelta(days=30)).strftime('%d-%m-%Y')),
        ('Yesterday', (today - timedelta(days=1)).strftime('%d-%m-%Y')),
    ]
    
    for endpoint in endpoints:
        print(f"\n🔍 Testing {endpoint['name']}")
        print("-" * 40)
        
        date_results = {}
        
        for date_desc, date_str in test_dates:
            print(f"\n📅 {date_desc} ({date_str})")
            
            params = endpoint['params_base'].copy()
            params['date'] = date_str
            
            try:
                response = requests.get(endpoint['url'], params=params, timeout=10)
                print(f"   Status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Extract key information
                    if 'data' in data:
                        date_info = data['data'].get('date', {})
                        timings = data['data'].get('timings', {})
                        
                        readable_date = date_info.get('readable', 'N/A')
                        gregorian = date_info.get('gregorian', {}).get('date', 'N/A')
                        fajr = timings.get('Fajr', 'N/A')
                        asr = timings.get('Asr', 'N/A')
                        
                        print(f"   API Date: {readable_date}")
                        print(f"   Gregorian: {gregorian}")
                        print(f"   Fajr: {fajr}")
                        print(f"   Asr: {asr}")
                        
                        date_results[date_desc] = {
                            'requested': date_str,
                            'returned_readable': readable_date,
                            'returned_gregorian': gregorian,
                            'fajr': fajr,
                            'asr': asr
                        }
                else:
                    print(f"   ❌ Failed with status {response.status_code}")
                    print(f"   Response: {response.text[:200]}...")
                    
            except Exception as e:
                print(f"   ❌ Error: {e}")
            
            time.sleep(0.5)  # Be nice to the API
        
        # Analysis for this endpoint
        print(f"\n📊 ANALYSIS for {endpoint['name']}")
        print("-" * 30)
        
        if date_results:
            # Check if API returns different dates
            returned_dates = set()
            fajr_times = set()
            asr_times = set()
            
            for result in date_results.values():
                returned_dates.add(result['returned_readable'])
                fajr_times.add(result['fajr'])
                asr_times.add(result['asr'])
            
            print(f"Unique returned dates: {len(returned_dates)}")
            print(f"Unique Fajr times: {len(fajr_times)}")
            print(f"Unique Asr times: {len(asr_times)}")
            
            if len(returned_dates) > 1:
                print("✅ API correctly returns different dates")
            else:
                print("⚠️  API returns same date for all requests")
                print(f"   Always returns: {list(returned_dates)[0] if returned_dates else 'None'}")
            
            if len(fajr_times) > 1 or len(asr_times) > 1:
                print("✅ Prayer times vary by date")
            else:
                print("⚠️  Prayer times are identical for all dates")
                print(f"   Fajr: {list(fajr_times)[0] if fajr_times else 'None'}")
                print(f"   Asr: {list(asr_times)[0] if asr_times else 'None'}")
            
            # Show detailed comparison
            print(f"\nDetailed results:")
            for desc, result in date_results.items():
                print(f"  {desc:12} | Req: {result['requested']} | Got: {result['returned_readable']} | Fajr: {result['fajr']}")

def test_api_without_date():
    """Test API without date parameter to see default behavior"""
    print(f"\n🔍 Testing API WITHOUT date parameter")
    print("-" * 40)
    
    url = 'https://api.aladhan.com/v1/timingsByCity'
    params = {'city': 'Cairo', 'country': 'Egypt', 'method': 3}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            date_info = data['data'].get('date', {})
            timings = data['data'].get('timings', {})
            
            print(f"Default date returned: {date_info.get('readable', 'N/A')}")
            print(f"Fajr: {timings.get('Fajr', 'N/A')}")
            print(f"Asr: {timings.get('Asr', 'N/A')}")
        else:
            print(f"Failed: {response.status_code}")
    except Exception as e:
        print(f"Error: {e}")

def test_edge_cases():
    """Test edge cases and different date formats"""
    print(f"\n🔍 Testing EDGE CASES")
    print("-" * 40)
    
    url = 'https://api.aladhan.com/v1/timingsByCity'
    base_params = {'city': 'Cairo', 'country': 'Egypt', 'method': 3}
    
    edge_cases = [
        ('Invalid date', '32-13-2025'),
        ('Future year', '01-01-2030'),
        ('Past year', '01-01-2020'),
        ('Different format 1', '2025-05-26'),
        ('Different format 2', '26/05/2025'),
        ('Timestamp', str(int(time.time()))),
    ]
    
    for desc, date_val in edge_cases:
        print(f"\n📅 {desc}: {date_val}")
        params = base_params.copy()
        params['date'] = date_val
        
        try:
            response = requests.get(url, params=params, timeout=10)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                date_info = data['data'].get('date', {})
                print(f"   Returned date: {date_info.get('readable', 'N/A')}")
            else:
                print(f"   Error response: {response.text[:100]}...")
        except Exception as e:
            print(f"   Exception: {e}")

if __name__ == "__main__":
    print(f"Current local time: {datetime.now()}")
    print(f"Current UTC time: {datetime.utcnow()}")
    
    test_api_without_date()
    test_prayer_api_comprehensive()
    test_edge_cases()
    
    print(f"\n{'='*60}")
    print("INVESTIGATION COMPLETE")
    print("If all APIs return the same date regardless of input,")
    print("this suggests either:")
    print("1. API server timezone issues")
    print("2. API caching problems") 
    print("3. API ignoring date parameter")
    print("4. Regional API restrictions")
