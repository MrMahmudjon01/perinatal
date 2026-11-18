from django.contrib import admin

from .models import Alert, MotherConfirmation, Notification, Referral


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ["__str__", "level", "status", "escalated", "created_at"]
    list_filter = ["level", "status", "to_color"]
    raw_id_fields = ["patient", "child"]


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ["subject_name", "to_level", "status", "created_at"]
    raw_id_fields = ["patient", "child"]


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["recipient_label", "kind", "status", "created_at"]
    list_filter = ["kind", "status"]


@admin.register(MotherConfirmation)
class MotherConfirmationAdmin(admin.ModelAdmin):
    list_display = ["patient", "kind", "summary", "delivered", "confirmed", "created_at"]
    list_filter = ["kind", "confirmed", "delivered"]
    raw_id_fields = ["patient"]
