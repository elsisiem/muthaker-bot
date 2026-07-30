translations = {
    "welcome": (
        "Assalamu Alaikum! Welcome to Muthaker Bot - your personal Islamic reminder companion.\n\n"
        "I can help you:\n"
        "• Send regular athkar (remembrances) at your preferred intervals\n"
        "• Set daily goals for how many times you want to receive athkar\n"
        "• Deliver morning & evening athkar at prayer-based times\n"
        "• Respect your sleep schedule automatically\n\n"
        "Let's set things up step by step. It'll only take a minute!"
    ),
    "select_language": "Please select your preferred language:",
    "language_set": "Language set to English!",
    "timezone_prompt": (
        "To schedule your athkar correctly, I need to know your timezone.\n\n"
        "You can:\n"
        "• Share your location (quickest)\n"
        "• Or type your timezone/city manually (e.g., 'America/New_York' or 'London')\n\n"
        "Privacy: If you share your location, I only use it to detect your timezone - "
        "I do NOT store your exact coordinates. Only the timezone name (e.g., 'America/New_York') is saved."
    ),
    "timezone_detected": "Detected timezone: {timezone}\nIs this correct?",
    "timezone_set": "Timezone set to: {timezone}",
    "timezone_invalid": "Could not determine timezone. Please try again or type a valid timezone (e.g., 'America/New_York' or 'Europe/London').",
    "athkar_type_prompt": "What type of athkar would you like to receive?",
    "athkar_type_set": "Athkar type set to: {athkar_type}",
    "schedule_mode_prompt": "How would you like to schedule your athkar?",
    "schedule_mode_interval": "Regular Interval - Receive athkar every X minutes during waking hours",
    "schedule_mode_goal": "Daily Goal - Set a target number of athkar per day, and I'll space them evenly",
    "schedule_interval_prompt": "How often would you like to receive athkar? (in minutes)\n\nCommon options:",
    "schedule_goal_prompt": "How many athkar would you like to receive per day?\n\nCommon options:",
    "schedule_set": "Scheduled: {mode} | {value}",
    "sleep_prompt": (
        "Would you like to set quiet hours? I won't send athkar during your sleep time.\n\n"
        "Choose a preset or set custom hours:"
    ),
    "sleep_custom_prompt": (
        "Enter your sleep hours in this format:\n"
        "START_HOUR:START_MINUTE-END_HOUR:END_MINUTE\n\n"
        "Example: 23:00-6:00 means sleep from 11 PM to 6 AM"
    ),
    "sleep_set": "Sleep hours: {start}:{start_min:02d} to {end}:{end_min:02d}",
    "sleep_disabled": "Sleep hours disabled. You'll receive athkar 24/7.",
    "prayer_city_prompt": (
        "To send morning & evening athkar at the right times, I need your city for prayer time calculations.\n\n"
        "Enter your city name (e.g., 'Cairo', 'London', 'New York').\n"
        "You can also type 'skip' if you don't need morning/evening athkar."
    ),
    "prayer_city_set": "Prayer times will be calculated for: {city}",
    "prayer_city_skipped": "Morning & evening athkar skipped. You can set this up later from Settings.",
    "prayer_not_found": "Could not find prayer times for '{city}'. Please try another city.",
    "confirm_setup": (
        "Here's a summary of your settings:\n\n"
        "Language: {language}\n"
        "Timezone: {timezone}\n"
        "Athkar type: {athkar_type}\n"
        "Schedule: {schedule_summary}\n"
        "Sleep: {sleep_summary}\n"
        "Prayer city: {prayer_city}\n\n"
        "Is everything correct? Click Confirm to start receiving athkar!"
    ),
    "setup_complete": (
        "All set! You'll start receiving athkar based on your preferences.\n\n"
        "Use /settings anytime to adjust your preferences.\n"
        "Use /status to see your current settings.\n"
        "Use /pause to temporarily stop athkar.\n"
        "Use /resume to restart them.\n\n"
        "May Allah accept your remembrance!"
    ),
    "setup_cancelled": "Setup cancelled. You can restart anytime with /start.",
    "main_menu": "Main Menu - What would you like to do?",
    "settings_menu": "Settings - Manage your preferences:",
    "change_language": "Change Language",
    "change_timezone": "Change Timezone",
    "manage_schedules": "Manage Athkar Schedules",
    "edit_sleep": "Edit Sleep Hours",
    "prayer_settings": "Prayer & Morning/Evening Athkar",
    "delete_account": "Delete My Data",
    "back": "Back",
    "confirm": "Confirm",
    "cancel": "Cancel",
    "skip": "Skip",
    "yes": "Yes",
    "no": "No",
    "enable": "Enable",
    "disable": "Disable",
    "add_schedule": "Add New Schedule",
    "no_schedules": "You have no active athkar schedules. Add one to start!",
    "schedule_list": "Your Athkar Schedules:",
    "schedule_item": "• {athkar_type} - {mode}: {value}",
    "status_message": (
        "Your Current Settings:\n\n"
        "Language: {language}\n"
        "Timezone: {timezone}\n"
        "Active schedules: {schedule_count}\n"
        "Sleep: {sleep_summary}\n"
        "Prayer city: {prayer_city}\n"
        "Morning athkar: {morning_status}\n"
        "Night athkar: {night_status}"
    ),
    "paused": "Athkar paused. Use /resume to restart.",
    "resumed": "Athkar resumed!",
    "delete_confirm": "Are you sure you want to delete all your data? This cannot be undone.",
    "deleted": "All your data has been deleted. You can start fresh with /start.",
    "general_error": "Something went wrong. Please try again or use /start to restart.",
    "privacy_notice": (
        "Privacy: Your location is only used momentarily to detect your timezone. "
        "I never store your exact coordinates - only the timezone name is saved."
    ),
    "interval_options": ["1", "5", "10", "15", "30", "60", "Custom"],
    "goal_options": ["100", "200", "500", "1000", "Custom"],
    "morning_enabled": "Enabled ({offset} min after Fajr)",
    "morning_disabled": "Disabled",
    "night_enabled": "Enabled ({offset} min after Asr)",
    "night_disabled": "Disabled",
    "athkar_sent": "{athkar_text}",
    "share_location": "Share Location",
    "type_manually": "Type Manually",
    "select_new": "Select a new option:",
    "prayer_not_set": "Prayer not configured",
    "prayer_settings_menu": "Prayer Settings:",
    "custom": "Custom",
    "status": "Status",
}