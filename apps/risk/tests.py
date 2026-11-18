"""Asosiy mantiq testlari: python manage.py test"""
from datetime import date, timedelta

from django.test import TestCase

from apps.accounts.models import User
from apps.alerts.models import Alert
from apps.geo.models import Clinic, District, Mavze
from apps.patients.models import Patient
from apps.risk.engine import evaluate, region_color
from apps.voice.extractor import extract_mother
from apps.voice.numbers import words_to_numbers
from apps.voice.validate import clean


class EngineTests(TestCase):
    def test_severe_hypertension_is_red(self):
        color, reasons = evaluate("mother", {"bp_sys": 165, "bp_dia": 100, "bp_high": True})
        self.assertEqual(color, "red")
        self.assertTrue(any("160/110" in r for r in reasons))

    def test_moderate_anemia_is_yellow(self):
        self.assertEqual(evaluate("mother", {"hb": 92})[0], "yellow")

    def test_missing_values_never_risky(self):
        self.assertEqual(evaluate("mother", {"hb": None, "bp_sys": None})[0], "green")

    def test_region_thresholds(self):
        self.assertEqual(region_color(3, 10), "red")
        self.assertEqual(region_color(1, 10), "yellow")
        self.assertEqual(region_color(0, 10), "green")
        self.assertEqual(region_color(0, 0), "none")

    def test_child_overdue_vaccine_is_yellow(self):
        self.assertEqual(evaluate("child", {"overdue_vaccines": 2, "birth_weight": 3300, "age_days": 200})[0], "yellow")


class VoiceTests(TestCase):
    def test_uzbek_numbers(self):
        self.assertEqual(words_to_numbers("bir yuz oltmish besh ga bir yuz o'n"), "165 ga 110")
        self.assertEqual(words_to_numbers("o'ttiz yetti butun besh"), "37.5")

    def test_extract_does_not_guess(self):
        f, ev = extract_mother("Gemoglobin oltmish sakkiz.")
        self.assertEqual(f, {"hb": 68})
        self.assertIn("68", ev["hb"])

    def test_validation_flags_nonsense(self):
        out, warn = clean("mother", {"bp_sys": 80, "bp_dia": 120, "hb": 900})
        self.assertIn("bp_sys", warn)
        self.assertIn("hb", warn)


class AlertFlowTests(TestCase):
    def setUp(self):
        d = District.objects.create(name="Test")
        c = Clinic.objects.create(district=d, number=1, name="1-poliklinika")
        self.m = Mavze.objects.create(clinic=c, name="1-mavze")
        self.doc = User.objects.create_user("doc", password="x", role=User.CLINIC, clinic=c, district=d)
        User.objects.create_user("ov", password="x", role=User.OVABMU)
        self.p = Patient.objects.create(last_name="Test", first_name="Ona", birth_date=date(1995, 1, 1),
                                        phone="+998901112233", mavze=self.m,
                                        lmp_date=date.today() - timedelta(weeks=30))

    def test_red_visit_creates_ovabmu_alert(self):
        self.client.force_login(self.doc)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(f"/patients/{self.p.id}/visit/", {
                "visit_date": date.today().isoformat(), "bp_sys": 170, "bp_dia": 112, "hb": 66,
                "color_choice": "auto"})
        self.assertEqual(r.status_code, 302)
        self.p.refresh_from_db()
        self.assertEqual(self.p.current_color, "red")
        a = Alert.objects.get()
        self.assertEqual(a.level, Alert.OVABMU)

    def test_other_clinic_cannot_see_patient(self):
        d2 = District.objects.create(name="Boshqa")
        c2 = Clinic.objects.create(district=d2, number=2, name="2-poliklinika")
        other = User.objects.create_user("doc2", password="x", role=User.CLINIC, clinic=c2, district=d2)
        self.client.force_login(other)
        self.assertEqual(self.client.get(f"/patients/{self.p.id}/").status_code, 404)


class MotherFeedbackTests(AlertFlowTests):
    def test_visit_goes_to_mother_without_zone_and_dispute_escalates(self):
        from apps.alerts.models import MotherConfirmation, Notification
        from apps.alerts.mother import handle_response
        self.client.force_login(self.doc)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"/patients/{self.p.id}/visit/", {
                "visit_date": date.today().isoformat(), "bp_sys": 170, "bp_dia": 112, "color_choice": "auto"})
        mc = MotherConfirmation.objects.get(kind="visit")
        text = Notification.objects.filter(kind="confirm").latest("id").text.lower()
        self.assertNotIn("qizil", text)
        self.assertIn("170/112", text)
        a = Alert.objects.get()
        self.client.post(f"/alerts/{a.id}/resolve/", {"action_type": "observe", "note": "Har kuni QB nazorati"})
        self.assertIn("Har kuni QB nazorati", Notification.objects.filter(kind="confirm").latest("id").text)
        handle_response(mc, False)
        mc.refresh_from_db()
        self.assertEqual(mc.state, "no")
        self.assertFalse(handle_response(mc, True))  # javob bir marta beriladi


class VaccinationSessionTests(AlertFlowTests):
    def test_session_reminders_3_and_1_day(self):
        from datetime import timedelta
        from apps.alerts.models import Notification
        from apps.children.models import Child, Vaccine, create_vaccination_plan
        from apps.children.sessions import send_reminders
        Vaccine.objects.create(code="Penta-1", name="Pentavalent (1-doza)", disease="X", age_days=61, age_label="2 oylik")
        child = Child.objects.create(mother=self.p, first_name="Ali", sex="m", birth_date=date.today() - timedelta(days=58),
                                     birth_weight=3300)
        create_vaccination_plan(child)
        self.client.force_login(self.doc)
        d = date.today() + timedelta(days=5)
        self.client.post("/vaccination/sessions/new/", {"vaccine": Vaccine.objects.get().id, "date": d.isoformat(),
                                                        "time": "09:00", "room": "", "note": ""})
        self.assertEqual(send_reminders(d - timedelta(days=4)), 0)
        self.assertEqual(send_reminders(d - timedelta(days=3)), 1)
        self.assertIn("Esdan chiqarmang", Notification.objects.latest("id").text)
        self.assertEqual(send_reminders(d - timedelta(days=1)), 1)
        self.assertIn("Ertaga", Notification.objects.latest("id").text)
        self.assertEqual(send_reminders(d - timedelta(days=1)), 0)
