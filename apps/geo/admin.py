from django.contrib import admin

from .models import Clinic, District, Mavze


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = ["name", "district"]
    list_filter = ["district"]
    search_fields = ["name"]


@admin.register(Mavze)
class MavzeAdmin(admin.ModelAdmin):
    list_display = ["name", "clinic"]
    list_filter = ["clinic__district"]
    search_fields = ["name", "clinic__name"]
