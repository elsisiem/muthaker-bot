from .start import register_start_handlers
from .onboarding import register_onboarding_handlers
from .settings import register_settings_handlers
from .channel_setup import register_channel_handlers


def register_all_handlers(application):
    register_start_handlers(application)
    register_onboarding_handlers(application)
    register_settings_handlers(application)
    register_channel_handlers(application)