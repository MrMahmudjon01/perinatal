from django.contrib import admin

from .models import Child, ChildVaccination, ChildVisit, Vaccine


class VaccInline(admin.TabularInline):
    model = ChildVaccination
    extra = 0


@admin.register(Child)
class ChildAdmin(admin.ModelAdmin):
    list_display = ["full_name", "mother", "birth_date", "current_color"]
    list_filter = ["current_color", "sex"]
    raw_id_fields = ["mother"]
    inlines = [VaccInline]


@admin.register(ChildVisit)
class ChildVisitAdmin(admin.ModelAdmin):
    list_display = ["child", "visit_date", "weight", "final_color"]
    raw_id_fields = ["child", "doctor"]


@admin.register(Vaccine)
class VaccineAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "age_label", "age_days"]
