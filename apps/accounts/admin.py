from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ["username", "full_name", "role", "clinic", "district", "telegram_chat_id"]
    list_filter = ["role", "district"]
    fieldsets = UserAdmin.fieldsets + (
        ("Rol va hudud", {"fields": ("role", "full_name", "position", "phone", "clinic", "district",
                                     "telegram_chat_id", "link_code")}),
    )
