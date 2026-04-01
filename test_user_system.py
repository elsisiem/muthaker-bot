"""
Test script to verify the user preferences system is working
Run this after deploying to Heroku to ensure database connection works
"""

import asyncio
import os
import sys

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from user_side import init_db, UserPreferences, async_session
from sqlalchemy import select

async def test_db_connection():
    """Test database connection"""
    print("🔧 Testing user preferences database connection...")

    try:
        # Initialize database
        print("  📦 Initializing database...")
        await init_db()
        print("  ✅ Database initialized")

        # Test query
        print("  🔍 Testing query...")
        async with async_session() as session:
            result = await session.execute(select(UserPreferences))
            users = result.scalars().all()
            print(f"  ✅ Query successful. Found {len(users)} users")

        print("\n✅ Database connection test PASSED!")
        return True

    except Exception as e:
        print(f"\n❌ Database connection test FAILED: {e}")
        return False

async def test_athkar_options():
    """Test that Athkar options are properly defined"""
    print("\n🎯 Testing Athkar options...")

    from user_side import ATHKAR_OPTIONS

    if not ATHKAR_OPTIONS or len(ATHKAR_OPTIONS) == 0:
        print("  ❌ No Athkar options defined!")
        return False

    print(f"  ✅ Found {len(ATHKAR_OPTIONS)} Athkar options:")
    for athkar in ATHKAR_OPTIONS:
        print(f"     • {athkar['ar']} ({athkar['en']})")

    return True

async def test_frequency_options():
    """Test that frequency options are properly defined"""
    print("\n⏰ Testing frequency options...")

    from user_side import FREQUENCY_OPTIONS

    if not FREQUENCY_OPTIONS or len(FREQUENCY_OPTIONS) == 0:
        print("  ❌ No frequency options defined!")
        return False

    print(f"  ✅ Found {len(FREQUENCY_OPTIONS)} frequency options:")
    for freq in FREQUENCY_OPTIONS:
        print(f"     • {freq['ar']} ({freq['en']})")

    return True

async def main():
    """Run all tests"""
    print("=" * 60)
    print("🧪 MUTHAKER BOT - USER PREFERENCES SYSTEM TEST")
    print("=" * 60)
    print()

    tests = [
        test_db_connection(),
        test_athkar_options(),
        test_frequency_options(),
    ]

    results = await asyncio.gather(*tests)

    print("\n" + "=" * 60)
    if all(results):
        print("🎉 ALL TESTS PASSED!")
    else:
        print("❌ SOME TESTS FAILED!")
    print("=" * 60)

    return all(results)

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
