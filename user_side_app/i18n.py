from typing import Literal

Lang = Literal["ar", "en"]

TEXTS: dict[str, dict[str, str]] = {
    "ar": {
        "welcome": "اهلا بك في مساعد الاذكار. اختر اللغة ثم اختر طريقة الاستخدام.",
        "choose_mode": "اختر نوع الاستخدام:",
        "mode_personal": "الاستخدام الشخصي",
        "mode_target": "النشر في مجموعة او قناة",
        "manage_targets": "ادارة الجهات المرتبطة",
        "target_none": "لا توجد جهة مرتبطة حاليا.",
        "target_list_title": "الجهات المرتبطة:",
        "target_setup": "لربط مجموعة/قناة:\n1) اضف البوت كادمن\n2) ارسل الامر /link من داخل المجموعة\n3) ارجع هنا واضغط تحديث",
        "target_linked": "تم ربط الجهة بنجاح.",
        "target_unlinked": "تم حذف الربط.",
        "target_choose_remove": "اختر الجهة التي تريد حذفها:",
        "refresh": "تحديث",
        "send_test": "ارسال رسالة اختبار",
        "test_sent": "تم ارسال الرسالة التجريبية.",
        "no_target_for_test": "لا توجد جهات مرتبطة للارسال.",
        "personal_menu": "وضع الاستخدام الشخصي جاهز. سنضيف الاعدادات المتقدمة في الخطوة التالية.",
        "back": "رجوع",
        "lang_set": "تم تغيير اللغة.",
        "lang_ar": "العربية",
        "lang_en": "English",
    },
    "en": {
        "welcome": "Welcome to Athkar Assistant. Choose language and mode.",
        "choose_mode": "Choose usage mode:",
        "mode_personal": "Personal Mode",
        "mode_target": "Post to Group/Channel",
        "manage_targets": "Manage Linked Targets",
        "target_none": "No linked targets yet.",
        "target_list_title": "Linked targets:",
        "target_setup": "To link a group/channel:\n1) Add bot as admin\n2) Send /link in that chat\n3) Return here and tap refresh",
        "target_linked": "Target linked successfully.",
        "target_unlinked": "Target unlinked.",
        "target_choose_remove": "Choose target to remove:",
        "refresh": "Refresh",
        "send_test": "Send Test Message",
        "test_sent": "Test message sent.",
        "no_target_for_test": "No linked targets to send.",
        "personal_menu": "Personal mode is ready. Advanced setup will be added next.",
        "back": "Back",
        "lang_set": "Language updated.",
        "lang_ar": "Arabic",
        "lang_en": "English",
    },
}


def tr(lang: str, key: str) -> str:
    safe = "en" if lang == "en" else "ar"
    return TEXTS[safe].get(key, key)
