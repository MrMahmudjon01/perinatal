from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from apps.accounts import staff
from apps.accounts import views as acc
from apps.alerts import views as al
from apps.children import views as ch
from apps.dashboard import views as dash
from apps.patients import views as pt
from apps.risk import views as risk
from apps.voice import views as voice

urlpatterns = [
    path("admin/", admin.site.urls),
    path("robots.txt", __import__("apps.accounts.security", fromlist=["x"]).robots_txt),
    path("login/", acc.login_view, name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("profile/", acc.profile, name="profile"),
    path("lang/<str:code>/", acc.set_lang, name="set_lang"),
    path("view-district/<int:pk>/", acc.set_view_district, name="set_view_district"),
    path("view-clinic/<int:pk>/", acc.set_view_clinic, name="set_view_clinic"),
    path("staff/", staff.staff_list, name="staff_list"),
    path("staff/new/", staff.staff_create, name="staff_create"),
    path("staff/<int:pk>/edit/", staff.staff_edit, name="staff_edit"),
    path("staff/<int:pk>/toggle/", staff.staff_toggle, name="staff_toggle"),
    path("staff/<int:pk>/reset/", staff.staff_reset, name="staff_reset"),

    path("", dash.home, name="home"),
    path("overview/live/", dash.overview_live, name="overview_live"),
    path("regions/", dash.regions, name="regions"),
    path("regions/district/<int:pk>/", dash.district_dashboard, name="district_dashboard"),
    path("regions/clinic/<int:pk>/", dash.clinic_dashboard, name="clinic_dashboard"),
    path("map/", dash.map_page, name="map_page"),
    path("map/data/", dash.map_data, name="map_data"),
    path("vaccination/", dash.vaccination_page, name="vaccination_page"),
    path("patronage/", dash.patronage_page, name="patronage_page"),
    path("stats/", dash.stats_page, name="stats_page"),
    path("dynamics/", dash.dynamics_page, name="dynamics_page"),
    path("project/", dash.project_page, name="project_page"),
    path("remind-missed/", dash.remind_missed, name="remind_missed"),
    path("about/", dash.about, name="about"),

    path("patients/", pt.patient_list, name="patient_list"),
    path("patients/new/", pt.patient_create, name="patient_create"),
    path("patients/<int:pk>/", pt.patient_detail, name="patient_detail"),
    path("patients/<int:pk>/ai-summary/", pt.ai_summary, name="ai_summary"),
    path("patients/<int:pk>/ai-summary/send/", pt.ai_summary_send, name="ai_summary_send"),
    path("patients/<int:pk>/edit/", pt.patient_edit, name="patient_edit"),
    path("patients/<int:pk>/visit/", pt.visit_create, name="visit_create"),
    path("patients/<int:pk>/message/", pt.message_mother, name="message_mother"),
    path("patients/<int:mother_pk>/child/new/", ch.child_create, name="child_create"),

    path("children/", ch.child_list, name="child_list"),
    path("children/<int:pk>/", ch.child_detail, name="child_detail"),
    path("children/<int:pk>/visit/", ch.child_visit_create, name="child_visit_create"),
    path("vaccinations/<int:pk>/done/", ch.vaccination_done, name="vaccination_done"),
    path("vaccination/sessions/", ch.session_list, name="session_list"),
    path("vaccination/sessions/new/", ch.session_create, name="session_create"),
    path("vaccination/sessions/<int:pk>/", ch.session_detail, name="session_detail"),
    path("vaccination/sessions/<int:pk>/attend/", ch.session_attend, name="session_attend"),
    path("vaccination/sessions/<int:pk>/cancel/", ch.session_cancel, name="session_cancel"),

    path("alerts/", al.alert_list, name="alert_list"),
    path("alerts/panel/", al.alert_panel, name="alert_panel"),
    path("alerts/feed/", al.alert_feed, name="alert_feed"),
    path("alerts/<int:pk>/seen/", al.alert_seen, name="alert_seen"),
    path("alerts/<int:pk>/resolve/", al.alert_resolve, name="alert_resolve"),
    path("referrals/", al.referral_list, name="referral_list"),
    path("referrals/new/", al.referral_create, name="referral_create"),
    path("referrals/<int:pk>/status/", al.referral_status, name="referral_status"),
    path("telegram-log/", al.notification_log, name="notification_log"),

    path("risk/preview/mother/<int:pk>/", risk.preview_mother, name="preview_mother"),
    path("risk/preview/child/<int:pk>/", risk.preview_child, name="preview_child"),
    path("voice/extract/", voice.extract, name="voice_extract"),
]

admin.site.site_header = "Perinatal registr — administrator"
admin.site.site_title = "Perinatal registr"
admin.site.index_title = "Ma'lumotlarni boshqarish"
