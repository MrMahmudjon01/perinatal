from django.contrib import admin

from .models import Patient, Visit


class VisitInline(admin.TabularInline):
    model = Visit
    extra = 0
    fields = ["visit_date", "gestational_week", "bp_sys", "bp_dia", "hb", "urine_protein", "final_color"]


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ["full_name", "phone", "mavze", "status", "current_color", "telegram_chat_id"]
    list_filter = ["status", "current_color", "mavze__clinic__district"]
    search_fields = ["last_name", "first_name", "phone"]
    raw_id_fields = ["mavze"]
    inlines = [VisitInline]


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ["patient", "visit_date", "bp", "hb", "final_color", "source"]
    list_filter = ["final_color", "source"]
    raw_id_fields = ["patient", "doctor"]
