"""Toshkent shahri misolida real ma'lumotga yaqin demo ma'lumot.

Haqiqiy manbalar (apps/geo/data/tashkent.json):
  • 12 tuman aholisi — Toshkent shahar statistika boshqarmasi, 2025-yil 1-oktabr holati
  • Tug'ilish — 2025-yil yanvar-sentabr: 47,7 ming (yillik ≈ 63,6 ming), o'g'il bolalar 51,6%
  • Oilaviy poliklinikalar nomi va joylashuvi — OpenStreetMap (ODbL); yetishmaganlari "taxminiy"
  • Tuman chegaralari — OpenStreetMap
  • Antenatal reja — SSV bazaviy paketi (8 tashrif); 31,1% kech ro'yxatga olish (SamDTU so'rovi)
  • Emlash — Milliy profilaktik emlash kalendari
  • O'sish egri chiziqlari — JSST (WHO) o'g'il/qiz bolalar medianlari

Sun'iy (bemorlar shaxsi, tahlil qiymatlari, tumanlar bo'yicha xavf farqi) — real shaxslarga aloqasi yo'q.

python manage.py seed_demo                # 10% masshtab (≈3,7 ming homilador, ≈12,7 ming bola)
python manage.py seed_demo --scale 0.05   # tezroq
"""
import json
import os
import random
from datetime import date, timedelta
from pathlib import Path

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.alerts.models import Alert, Notification, Referral
from apps.children.models import Child, ChildVaccination, ChildVisit, Vaccine
from apps.children.schedule import SPECIALIST_MONTHS, SPECIALISTS, month_date
from apps.geo.models import Clinic, District, Mavze
from apps.patients.models import Patient, Visit
from apps.patients.schedule import ANC_VISITS
from apps.risk.engine import evaluate

TODAY = date.today()
PASSWORD = "demo12345"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PEOPLE_PER_CLINIC = 40_000          # ≈ bitta oilaviy poliklinika xizmat ko'rsatadigan aholi (taxminiy)
PREGNANT_PER_BIRTH = 0.58           # ro'yxatda turgan homiladorlar ≈ yillik tug'ilish × (30 hafta / 52)
CHILD_YEARS = 2
LATE_REGISTRATION = 0.311           # 12 haftadan keyin ro'yxatga olinganlar ulushi

# Tumanlar bo'yicha xavf koeffitsiyenti — SUN'IY (demo uchun farq ko'rinsin)
RISK = {"Yangihayot": 2.7, "Sergeli": 2.2, "Bektemir": 1.6, "Uchtepa": 1.1, "Yashnobod": 1.05, "Olmazor": 1.0,
        "Shayxontohur": 0.95, "Chilonzor": 0.9, "Yunusobod": 0.85, "Mirzo Ulug'bek": 0.85, "Mirobod": 0.8,
        "Yakkasaroy": 0.7}
SLUG = {"Mirzo Ulug'bek": "mirzoulugbek"}

VACCINES = [  # (kod, nomi, kasallik, yosh kunda, yosh matni)
    ("VGB-1", "Gepatit B (1-doza)", "Virusli gepatit B", 0, "1-sutka (tug'ruqxonada)"),
    ("BSJ-1", "BSJ (BCG)", "Sil (tuberkulyoz)", 3, "2–5-kun (tug'ruqxonada)"),
    ("Penta-1", "Pentavalent (1-doza)", "Ko'kyo'tal, difteriya, qoqshol, gepatit B, XIB", 61, "2 oylik"),
    ("OPV-1", "Poliomiyelit, og'iz orqali (1-doza)", "Poliomiyelit", 61, "2 oylik"),
    ("Rota-1", "Rotavirus (1-doza)", "Rotavirus infeksiyasi", 61, "2 oylik"),
    ("Pnevmo-1", "Pnevmokokk (1-doza)", "Pnevmokokk infeksiyasi", 61, "2 oylik"),
    ("Penta-2", "Pentavalent (2-doza)", "Ko'kyo'tal, difteriya, qoqshol, gepatit B, XIB", 91, "3 oylik"),
    ("OPV-2", "Poliomiyelit, og'iz orqali (2-doza)", "Poliomiyelit", 91, "3 oylik"),
    ("Rota-2", "Rotavirus (2-doza)", "Rotavirus infeksiyasi", 91, "3 oylik"),
    ("Pnevmo-2", "Pnevmokokk (2-doza)", "Pnevmokokk infeksiyasi", 91, "3 oylik"),
    ("Penta-3", "Pentavalent (3-doza)", "Ko'kyo'tal, difteriya, qoqshol, gepatit B, XIB", 122, "4 oylik"),
    ("OPV-3", "Poliomiyelit, og'iz orqali (3-doza)", "Poliomiyelit", 122, "4 oylik"),
    ("Rota-3", "Rotavirus (3-doza)", "Rotavirus infeksiyasi", 122, "4 oylik"),
    ("IPV-1", "Inaktivatsiyalangan polio vaksinasi (1-doza)", "Poliomiyelit", 122, "4 oylik"),
    ("IPV-2", "Inaktivatsiyalangan polio vaksinasi (2-doza)", "Poliomiyelit", 274, "9 oylik"),
    ("KPK-1", "KPK (1-doza)", "Qizamiq, epidemik parotit (tepki), qizilcha", 365, "12 oylik"),
    ("Pnevmo-3", "Pnevmokokk (3-doza)", "Pnevmokokk infeksiyasi", 365, "12 oylik"),
    ("AKDS-4", "AKDS (revaksinatsiya)", "Ko'kyo'tal, difteriya, qoqshol", 487, "16 oylik"),
    ("OPV-4", "Poliomiyelit, og'iz orqali (4-doza)", "Poliomiyelit", 487, "16 oylik"),
]

# JSST medianlari: oy → (vazn kg, bo'y sm, bosh aylanasi sm); o'g'il / qiz
WHO = {
    "m": {0: (3.3, 49.9, 34.5), 1: (4.5, 54.7, 37.3), 2: (5.6, 58.4, 39.1), 3: (6.4, 61.4, 40.5), 4: (7.0, 63.9, 41.6),
          6: (7.9, 67.6, 43.3), 9: (8.9, 72.0, 45.0), 12: (9.6, 75.7, 46.1), 18: (10.9, 82.3, 47.4),
          24: (12.2, 87.8, 48.3)},
    "f": {0: (3.2, 49.1, 33.9), 1: (4.2, 53.7, 36.5), 2: (5.1, 57.1, 38.3), 3: (5.8, 59.8, 39.5), 4: (6.4, 62.1, 40.6),
          6: (7.3, 65.7, 42.2), 9: (8.2, 70.1, 43.8), 12: (8.9, 74.0, 44.9), 18: (10.2, 80.7, 46.2),
          24: (11.5, 86.4, 47.2)},
}

SURNAMES = ["Karimov", "Rahimov", "Aliyev", "Yusupov", "Tursunov", "Abdullayev", "Mirzayev", "Saidov", "Qodirov",
            "Ergashev", "Nazarov", "Usmonov", "Xolmatov", "Ismoilov", "Hasanov", "Sobirov", "Jo'rayev", "Islomov",
            "Normatov", "Sharipov", "Toshmatov", "Umarov", "Zokirov", "Rasulov", "Azimov", "Fayzullayev",
            "Haydarov", "Mahmudov", "Nurmatov", "Qosimov", "Salimov", "Valiyev", "Raximov", "Yo'ldoshev",
            "Sultonov", "Bakirov", "Komilov", "Xudoyberdiyev", "Ahmedov", "Murodov"]
FEMALE = ["Dilnoza", "Madina", "Nilufar", "Gulnora", "Shahnoza", "Malika", "Zarina", "Feruza", "Mohira", "Sevara",
          "Kamola", "Nodira", "Dildora", "Munisa", "Sabina", "Gulruh", "Mavluda", "Zuhra", "Yulduz", "Barno", "Lola",
          "Charos", "Maftuna", "Aziza", "Nargiza", "Ozoda", "Sitora", "Umida", "Hilola", "Durdona", "Mehribon",
          "Shoira", "Diyora", "Marjona", "Ruxsora", "Gulshan", "Nozima", "Shaxlo", "Iroda", "Kumush"]
FATHERS = ["Rustam", "Akmal", "Baxtiyor", "Shuhrat", "Anvar", "Olim", "Farhod", "Ulug'bek", "Jamshid", "Sherzod",
           "Botir", "Alisher", "Davron", "Erkin", "Ilhom", "Murod", "Nodir", "Rashid", "Sanjar", "Tohir"]
BOYS = ["Muhammad", "Abdulloh", "Umar", "Ali", "Sardor", "Temur", "Bobur", "Islom", "Yusuf", "Ibrohim", "Asadbek",
        "Samandar", "Mirzo", "Aziz", "Muhammadali", "Abubakr", "Usmon", "Ismoil", "Doniyor", "Amir"]
GIRLS = ["Oisha", "Asal", "Mohinur", "Robiya", "Soliha", "Zahro", "Shahzoda", "Muslima", "Fotima", "Imona",
         "Mubina", "Laylo", "Sumayya", "Hadicha", "Maryam", "Ruqiya", "Zaynab", "Sevinch"]
DOCTORS = ["Ahmedova Nodira", "Saidova Gulchehra", "Qodirova Malika", "Ergasheva Dilfuza", "Nazarova Zulfiya",
           "Tursunova Mavjuda", "Islomova Shaxnoza", "Umarova Feruza", "Rasulova Nigora", "Azimova Muhabbat",
           "Saidov Bekzod", "Qodirov Farrux", "Ergashev Otabek", "Nazarov Ravshan", "Ahmedov Jahongir"]
CHRONIC = ["Surunkali pielonefrit", "Gipotireoz", "Surunkali gastrit", "Miopiya", "Varikoz kengayish",
           "Qandli diabet (2-tip)", "Surunkali anemiya", "Bronxial astma"]
PREV_COMPL = ["Oldingi homiladorlikda preeklampsiya", "Kesarcha kesish", "Muddatidan oldin tug'ruq (34 hafta)",
              "Homila tushishi (1 marta)", "Gestatsion diabet"]
CHILD_ILLNESS = [  # (tashxis, tavsiya, shikoyat)
    ("O'RVI", "Ko'p suyuqlik, isitma tushiruvchi (paratsetamol), 5 kundan keyin nazorat", "Burun bitishi, yo'tal, harorat"),
    ("Atopik dermatit", "Gipoallergen parhez, namlantiruvchi krem", "Yuz va qo'llarda toshma, qichishish"),
    ("O'tkir bronxit", "Ingalyatsiya, mutaxassis nazorati", "Yo'tal, xirillash"),
    ("Temir tanqisligi anemiyasi (yengil)", "Temir preparati 1 oy, ovqatlanishni boyitish", "Rangparlik, ishtaha pasaygan"),
    ("Ichak infeksiyasi", "Regidratatsiya, ko'krak sutini davom ettirish", "Ich ketishi, qusish"),
]


def interp(sex, months):
    table = WHO[sex]
    keys = sorted(table)
    for a, b in zip(keys, keys[1:]):
        if a <= months <= b:
            t = (months - a) / (b - a)
            return tuple(x + (y - x) * t for x, y in zip(table[a], table[b]))
    return table[keys[-1]]


def point_in_ring(x, y, ring):
    c = False
    for i in range(len(ring)):
        x1, y1 = ring[i]
        x2, y2 = ring[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def random_point(feature):
    polys = feature["geometry"]["coordinates"]
    outer = max(polys, key=lambda p: len(p[0]))[0]
    xs, ys = [p[0] for p in outer], [p[1] for p in outer]
    for _ in range(500):
        x, y = random.uniform(min(xs), max(xs)), random.uniform(min(ys), max(ys))
        if point_in_ring(x, y, outer):
            return round(y, 6), round(x, 6)
    return sum(ys) / len(ys), sum(xs) / len(xs)


def rnd_phone(used):
    while True:
        p = f"+998{random.choice(['90', '91', '93', '94', '97', '99', '88', '33'])}{random.randint(1000000, 9999999)}"
        if p not in used:
            used.add(p)
            return p


def mother_age():
    a = int(random.gauss(27.5, 5))
    if random.random() < 0.004:
        a = 17
    return max(18 if a != 17 else 17, min(45, a))


def mother_values(target, week):
    hb_base = 128 - max(0, week - 12) * 0.35
    v = dict(bp_sys=random.randint(104, 128), bp_dia=random.randint(64, 82), hb=int(random.gauss(hb_base, 6)),
             urine_protein=random.choice(["none"] * 8 + ["trace"]),
             fetal_movement="normal" if week >= 20 else "na",
             fetal_heart_rate=random.randint(128, 158) if week >= 12 else None,
             weight=round(random.gauss(62, 9) + week * 0.3, 1), temperature=round(random.uniform(36.3, 36.9), 1),
             edema=False, bleeding=False, headache_vision=False, complaints="", diagnosis="Homiladorlik me'yorida",
             recommendation="Foliy kislota, yod, temir preparati profilaktik")
    v["hb"] = max(100, v["hb"])
    if target == "yellow":
        kind = random.choices(["anemia", "bp", "protein", "edema"], [55, 20, 12, 13])[0]
        if kind == "anemia":
            v.update(hb=random.randint(82, 99), complaints="Holsizlik, bosh aylanishi", diagnosis="O'rtacha anemiya",
                     recommendation="Temir preparati davolash dozasida, 2 haftadan keyin Hb nazorati")
        elif kind == "bp":
            v.update(bp_sys=random.randint(140, 152), bp_dia=random.randint(88, 98), complaints="Bosh og'rig'i",
                     diagnosis="Gestatsion gipertenziya", recommendation="QB kunlik o'lchash, 1 haftadan keyin ko'rik")
        elif kind == "protein":
            v.update(urine_protein="+", diagnosis="Proteinuriya", recommendation="Siydik tahlilini takrorlash")
        else:
            v.update(edema=True, complaints="Oyoqlarda shish", diagnosis="Shish, nazorat",
                     recommendation="Tuz cheklash, QB va siydik nazorati")
    elif target == "red":
        kind = random.choices(["preecl", "severe_anemia", "severe_bp", "movement", "bleeding"], [35, 25, 20, 12, 8])[0]
        if kind == "preecl" and week >= 20:
            v.update(bp_sys=random.randint(145, 158), bp_dia=random.randint(92, 105), urine_protein="++",
                     edema=True, headache_vision=True, diagnosis="Preeklampsiya",
                     complaints="Kuchli bosh og'rig'i, ko'z oldi qorong'ilashishi")
        elif kind in ("severe_anemia", "preecl"):
            v.update(hb=random.randint(55, 69), complaints="Kuchli holsizlik, hansirash", diagnosis="Og'ir anemiya")
        elif kind == "severe_bp":
            v.update(bp_sys=random.randint(160, 175), bp_dia=random.randint(105, 115),
                     complaints="Bosh og'rig'i, ko'ngil aynishi", diagnosis="Og'ir gipertenziya")
        elif kind == "movement" and week >= 20:
            v.update(fetal_movement="decreased", fetal_heart_rate=random.choice([102, 105, 168, 172]),
                     complaints="Homila harakati kamaygan", diagnosis="Homila holati buzilishi shubhasi")
        else:
            v.update(bleeding=True, complaints="Qonli ajralma", diagnosis="Qon ketish, sababi aniqlanmoqda")
        v["recommendation"] = "Zudlik bilan perinatal markazga yo'llash"
    return v


class Command(BaseCommand):
    help = "Toshkent shahri misolida real ma'lumotga yaqin demo ma'lumot yaratadi (mavjud ma'lumot o'chiriladi)"

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--scale", type=float, default=0.10, help="Real hajmga nisbatan ulush (0.10 = 10%%)")

    @transaction.atomic
    def handle(self, *args, **opts):
        random.seed(opts["seed"])
        self.scale = opts["scale"]
        data = json.load(open(DATA_DIR / "tashkent.json", encoding="utf-8"))
        geo = {f["properties"]["name"]: f for f in json.load(open(DATA_DIR / "districts.geojson", encoding="utf-8"))["features"]}
        osm = json.load(open(DATA_DIR / "clinics_osm.json", encoding="utf-8"))

        self.stdout.write("Eski ma'lumot o'chirilmoqda...")
        # Botga ulangan onalar qayta ulanishi shart bo'lmasin: telefon → chat_id saqlab qolinadi
        tg_links = dict(Patient.objects.exclude(telegram_chat_id=None).values_list("phone", "telegram_chat_id"))
        from apps.alerts.models import MotherConfirmation
        for m in [MotherConfirmation, Notification, Alert, Referral, ChildVaccination, ChildVisit, Child, Visit, Patient]:
            m.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        Mavze.objects.all().delete()
        Clinic.objects.all().delete()
        District.objects.all().delete()
        Vaccine.objects.all().delete()

        self.vaccines = Vaccine.objects.bulk_create([Vaccine(code=c, name=n, disease=d, age_days=a, age_label=l)
                                                     for c, n, d, a, l in VACCINES])
        from django.conf import settings as dj
        strong = {k: v for k, v in dj.DEMO_PASSWORDS.items() if v and k != "admin"}
        # .env da kuchli parollar bo'lsa: asosiy 3 rolga o'sha parol, qolgan demo hisoblarga kirish yopiq
        pwd = make_password(None) if strong else make_password(PASSWORD)
        births_year = data["births_jan_sep_2025"] / 0.75
        total_pop = sum(v[1] for v in data["districts"].values()) * 1000
        self.boys_share = data["boys_share"]

        # --- Tumanlar va poliklinikalar
        users = [User(username="ovabmu", password=pwd, role=User.OVABMU, full_name="Rahimova Sayyora Akmalovna",
                      position="OvaBMU bosh mutaxassisi"),
                 User(username="ovabmu2", password=pwd, role=User.OVABMU, full_name="Xolmatov Dilshod Erkinovich",
                      position="OvaBMU navbatchi akusher-ginekolog")]
        districts, clinics = [], []
        used_numbers = {r["number"] for r in osm}
        free_numbers = [n for n in range(1, 100) if n not in used_numbers]
        for name, (_, p25) in sorted(data["districts"].items()):
            d = District.objects.create(name=name, population=int(p25 * 1000), osm_id=geo[name]["properties"]["osm_id"])
            d.risk = RISK.get(name, 1.0)
            districts.append(d)
            slug = SLUG.get(name, name.lower().replace("'", ""))
            users.append(User(username=f"tuman_{slug}", password=pwd, role=User.DISTRICT, district=d,
                              full_name=random.choice(DOCTORS), position=f"{name} tumani bosh akusher-ginekologi"))
            rows = [r for r in osm if r["district"] == name]
            target = max(2, round(d.population / PEOPLE_PER_CLINIC))
            for r in rows:
                clinics.append(Clinic(district=d, number=r["number"], name=f"{r['number']}-oilaviy poliklinika",
                                      address=r["address"] or f"{name} tumani", lat=r["lat"], lon=r["lon"],
                                      source="osm", osm_name=r["osm_name"]))
            for _ in range(max(0, target - len(rows))):
                n = free_numbers.pop(0)
                lat, lon = random_point(geo[name])
                clinics.append(Clinic(district=d, number=n, name=f"{n}-oilaviy poliklinika", address=f"{name} tumani",
                                      lat=lat, lon=lon, source="synthetic"))
        Clinic.objects.bulk_create(clinics)
        clinics = list(Clinic.objects.select_related("district"))
        dmap = {d.id: d for d in districts}
        for c in clinics:
            c.district = dmap[c.district_id]
            c.risk = c.district.risk
        yh = sorted([c for c in clinics if c.district.name == "Yangihayot"], key=lambda c: c.number)
        if len(yh) > 1:
            yh[1].risk = 8.0  # bitta "qizil" poliklinika — demo uchun
        Mavze.objects.bulk_create([Mavze(clinic=c, name=f"{i + 1}-mavze") for c in clinics
                                   for i in range(random.randint(4, 6))])
        mavzes = list(Mavze.objects.all())
        cmap = {c.id: c for c in clinics}
        by_district = {d.id: [] for d in districts}
        for m in mavzes:
            m.clinic = cmap[m.clinic_id]
            by_district[m.clinic.district_id].append(m)

        chil = sorted([c for c in clinics if c.district.name == "Chilonzor"],
                      key=lambda c: (c.source != "osm", c.number))
        demo_clinic = chil[0]
        demo_mavze = sorted([m for m in mavzes if m.clinic_id == demo_clinic.id], key=lambda m: m.name)[0]
        for c in clinics:
            users.append(User(username="poliklinika_demo" if c.id == demo_clinic.id else f"pol_{c.number}",
                              password=pwd, role=User.CLINIC, clinic=c, district=c.district,
                              full_name=random.choice(DOCTORS), position="Oilaviy shifokor / akusher-ginekolog"))
        User.objects.bulk_create(users)
        self.doctors = {u.clinic_id: u for u in User.objects.filter(role=User.CLINIC)}
        for uname, raw in strong.items():
            User.objects.filter(username=uname).update(password=make_password(raw))
        demo_doc = self.doctors[demo_clinic.id]
        demo_doc.full_name = "Ahmedova Nodira Shuhratovna"
        demo_doc.save(update_fields=["full_name"])  # parolni qayta yozib yubormaslik uchun

        # --- Bemorlar va bolalar
        self.demo_phone = os.environ.get("DEMO_MOTHER_PHONE") or "+998901234567"
        self.used_phones = {self.demo_phone, "+998907654321"}
        self.patients, self.visits, self.children = [], [], []
        self.stdout.write("Homiladorlar va bolalar yaratilmoqda...")
        for d in districts:
            share = d.population / total_pop
            n_preg = round(births_year * share * PREGNANT_PER_BIRTH * self.scale)
            n_child = round(births_year * share * CHILD_YEARS * self.scale)
            pool = [m for m in by_district[d.id] if m.id != demo_mavze.id]
            for _ in range(n_preg):
                m = random.choice(pool)
                self._pregnant(m, m.clinic.risk)
            for _ in range(n_child):
                m = random.choice(pool)
                self._child_with_mother(m, m.clinic.risk, days=random.randint(0, CHILD_YEARS * 365 - 1))
        self._demo(demo_mavze)

        self._finalize_patients()
        self.stdout.write("Ko'riklar va emlashlar yozilmoqda...")
        self._finalize_children()
        self._history_alerts()
        from django.db.models import F
        Patient.objects.update(consent=True, consent_at=F("registered_at"))  # ro'yxatga olishda rozilik olingan
        from apps.dashboard.history import backfill_demo
        backfill_demo()  # Dinamika sahifasi uchun o'tgan 6 oy
        from django.core.management import call_command
        call_command("assign_test_phones")  # .env TEST_PHONES → demo onalar
        call_command("create_clinic_team")  # ginekolog, pediatr, patronaj hamshira
        for phone, chat_id in tg_links.items():
            Patient.objects.filter(phone=phone).update(telegram_chat_id=chat_id)

        n_p = Patient.objects.filter(status="pregnant").count()
        self.stdout.write(self.style.SUCCESS(
            f"Tayyor (masshtab {self.scale:.0%}): {District.objects.count()} tuman, {len(clinics)} poliklinika "
            f"({sum(c.source == 'osm' for c in clinics)} tasi OpenStreetMap'dan), {len(mavzes)} mavze, "
            f"{n_p} homilador, {Child.objects.count()} bola (0–2 yosh), {Visit.objects.count()} antenatal ko'rik, "
            f"{ChildVisit.objects.count()} bola ko'rigi, {ChildVaccination.objects.count()} emlash yozuvi.\n"
            f"Loginlar ({'parollar .env faylida (PASS_*)' if strong else 'parol: ' + PASSWORD}): ovabmu | tuman_chilonzor | poliklinika_demo "
            f"({demo_clinic.name}, {demo_mavze.name})"))

    # ------------------------------------------------------------------ onalar
    def _new_mother(self, m, age=None, **kw):
        age = age or mother_age()
        g = kw.pop("gravidity", None) or random.choices([1, 2, 3, 4, 5], [34, 32, 21, 9, 4])[0]
        parity = kw.pop("parity", None)
        p = Patient(last_name=random.choice(SURNAMES) + "a", first_name=random.choice(FEMALE),
                    middle_name=random.choice(FATHERS) + "ovna",
                    birth_date=date(TODAY.year - age, random.randint(1, 12), random.randint(1, 28)),
                    phone=rnd_phone(self.used_phones), address=f"{m.clinic.district.name} tumani, {m.name}",
                    mavze=m, gravidity=g, parity=parity if parity is not None else max(0, g - 1 - random.choice([0, 0, 0, 1])),
                    blood_group=random.choices([b for b, _ in Patient.BLOOD_CHOICES], [30, 3, 33, 4, 21, 2, 6, 1])[0],
                    chronic_conditions=random.choice(CHRONIC) if random.random() < 0.15 else "",
                    previous_complications=random.choice(PREV_COMPL) if g > 1 and random.random() < 0.12 else "",
                    **kw)
        self.patients.append(p)
        return p

    def _pregnant(self, m, risk, force=None, mother=None):
        late = random.random() < LATE_REGISTRATION
        reg_week = random.randint(13, 24) if late else random.randint(6, 12)
        week = random.randint(reg_week, 40)
        lmp = TODAY - timedelta(days=week * 7 + random.randint(0, 6))
        p = mother or self._new_mother(m, lmp_date=lmp, registered_at=lmp + timedelta(weeks=reg_week))
        r = random.random()
        target = force or ("red" if r < 0.045 * risk else "yellow" if r < (0.045 + 0.17) * risk else "green")
        missed = force is None and random.random() < 0.035 * risk
        weeks = [reg_week] + [wk for wk, *_ in ANC_VISITS if wk > reg_week + 2 and wk <= week]
        if missed and len(weeks) > 1:
            weeks = weeks[:-1]
        else:
            weeks = [w for i, w in enumerate(weeks) if i in (0, len(weeks) - 1) or random.random() < 0.93]
        vs = []
        for i, wk in enumerate(weeks):
            vdate = min(TODAY, lmp + timedelta(weeks=wk, days=random.randint(-3, 3)))
            is_last = i == len(weeks) - 1
            vals = mother_values(target if is_last and not missed else "green", wk)
            nxt = next((lmp + timedelta(weeks=w) for w, *_ in ANC_VISITS if w > wk), lmp + timedelta(weeks=41))
            if target == "red" and is_last:
                nxt = vdate + timedelta(days=3)
            elif target == "yellow" and is_last:
                nxt = min(nxt, vdate + timedelta(days=14))
            vals.update(visit_date=vdate, gestational_week=wk, next_visit_date=nxt)
            vs.append(vals)
        if missed:
            missed_wk = next((w for w, *_ in ANC_VISITS if w > weeks[-1]), None)
            if missed_wk:
                vs[-1]["next_visit_date"] = lmp + timedelta(weeks=missed_wk)
        elif vs and vs[-1]["next_visit_date"] < TODAY:
            vs[-1]["next_visit_date"] = TODAY + timedelta(days=random.randint(1, 10))
        p._visits = vs
        p.next_visit_date = vs[-1]["next_visit_date"] if vs else TODAY
        return p

    def _finalize_patients(self):
        for p in self.patients:
            vs = getattr(p, "_visits", [])
            last = vs[-1] if vs and p.status == Patient.PREGNANT else None
            ctx = {"age": p.age, "has_prev_complications": bool(p.previous_complications), "missed_visit": p.missed_visit}
            if last:
                ctx.update(last)
                ctx["bp_high"] = last["bp_sys"] >= 140 or last["bp_dia"] >= 90
            color, reasons = evaluate("mother", ctx) if p.status == Patient.PREGNANT else ("green", [])
            p.current_color, p.color_reasons, p.color_updated_at = color, reasons, timezone.now()
        Patient.objects.bulk_create(self.patients, batch_size=2000)
        visits = []
        for p in self.patients:
            vs = getattr(p, "_visits", [])
            doc = self.doctors[p.mavze.clinic_id]
            for i, v in enumerate(vs):
                last = i == len(vs) - 1
                color = p.current_color if last else "green"
                visits.append(Visit(patient=p, doctor=doc, computed_color=color, final_color=color,
                                    color_reasons=p.color_reasons if last else [],
                                    source=random.choice(["manual", "manual", "voice"]), **v))
        Visit.objects.bulk_create(visits, batch_size=5000)

    # ------------------------------------------------------------------ bolalar
    def _child_with_mother(self, m, risk, days, **child_kw):
        birth = TODAY - timedelta(days=days)
        mother = child_kw.pop("mother", None) or self._new_mother(
            m, lmp_date=birth - timedelta(days=random.randint(266, 287)), status=Patient.DELIVERED,
            delivered_at=birth, registered_at=birth - timedelta(days=200))
        sex = child_kw.pop("sex", None) or ("m" if random.random() < self.boys_share else "f")
        ga = random.choices([33, 35, 36, 37, 38, 39, 40, 41], [1, 2, 3, 8, 20, 30, 28, 8])[0]
        med_w = WHO[sex][0][0] * 1000
        bw = int(random.gauss(med_w + (ga - 39.5) * 150, 340))
        c = Child(mother=mother, first_name=random.choice(BOYS if sex == "m" else GIRLS), sex=sex, birth_date=birth,
                  birth_weight=max(1100, bw), birth_height=int(random.gauss(WHO[sex][0][1], 1.8)),
                  apgar_1=random.choices([5, 6, 7, 8, 9], [2, 5, 18, 50, 25])[0],
                  apgar_5=random.choices([6, 7, 8, 9, 10], [2, 6, 30, 55, 7])[0], gestational_age_at_birth=ga)
        for k, v in child_kw.items():
            setattr(c, k, v)
        c._risk = risk
        self.children.append(c)
        return c

    def _finalize_children(self):
        Child.objects.bulk_create(self.children, batch_size=2000)
        visits, vaccs = [], []
        for c in self.children:
            risk = c._risk
            special = getattr(c, "_special", None)
            age = (TODAY - c.birth_date).days
            doc = self.doctors[c.mother.mavze.clinic_id]
            delayer = special is None and random.random() < 0.035 * risk
            overdue = 0
            for v in self.vaccines:
                due = c.birth_date + timedelta(days=v.age_days)
                if due > TODAY - timedelta(days=7):
                    vaccs.append(ChildVaccination(child=c, vaccine=v, due_date=due, status="planned"))
                elif special or not (delayer and v.age_days >= 61 and random.random() < 0.6):
                    vaccs.append(ChildVaccination(child=c, vaccine=v, due_date=due, status="done", done_by=doc,
                                                  done_date=due + timedelta(days=random.randint(0, 9) if v.age_days >= 61 else 0),
                                                  batch=f"{v.code[:2].upper()}{random.randint(10000, 99999)}"))
                else:
                    vaccs.append(ChildVaccination(child=c, vaccine=v, due_date=due, status="overdue"))
                    overdue += 1

            plan = [(3, "patronage", 0)] + [(round(m * 30.44), "monthly", m) for m in range(1, 13)] + \
                   [(round(m * 30.44), "monthly", m) for m in (15, 18, 21, 24)]
            sick_now = special is None and random.random() < 0.015 * risk
            missed = special is None and random.random() < 0.03 * risk
            last_visit, next_due = None, None
            done_plan = [x for x in plan if x[0] + 3 <= age]
            if missed and len(done_plan) > 1:
                next_due = c.birth_date + timedelta(days=done_plan[-1][0])
                done_plan = done_plan[:-1]
            for i, (d, vtype, months) in enumerate(done_plan):
                if vtype == "monthly" and special is None and random.random() < 0.06 and i != len(done_plan) - 1:
                    continue
                vdate = c.birth_date + timedelta(days=d + random.randint(-4, 4) if d > 3 else d)
                vdate = min(vdate, TODAY)
                mm = max(0.0, (vdate - c.birth_date).days / 30.44)
                w, h, hc = interp(c.sex, mm)
                factor = c.birth_weight / (WHO[c.sex][0][0] * 1000)
                factor = 1 + (factor - 1) * max(0.2, 1 - mm / 12)
                weight = int(w * 1000 * factor * random.uniform(0.96, 1.04))
                if vtype == "patronage":
                    weight = int(c.birth_weight * random.uniform(0.93, 0.98))
                is_last = i == len(done_plan) - 1
                illness = None
                if special == "aziz" and months == 9:
                    illness = CHILD_ILLNESS[0]
                elif special == "aziz" and months == 18:
                    illness = CHILD_ILLNESS[3]
                elif special is None and months and random.random() < 0.09:
                    illness = random.choice(CHILD_ILLNESS)
                severe = sick_now and is_last
                specs = [f"{s}: me'yor" for s in SPECIALISTS] if months in SPECIALIST_MONTHS else []
                if specs and special is None and random.random() < 0.04:
                    specs[random.randint(0, 3)] = random.choice(["Ortoped-jarroh: chanoq-son bo'g'imi displaziyasi shubhasi, UTT",
                                                                 "Nevropatolog: mushak tonusi oshgan, massaj",
                                                                 "LOR: adenoid gipertrofiyasi"])
                cv = ChildVisit(
                    child=c, doctor=doc, visit_date=vdate, visit_type=vtype, weight=weight,
                    height=int(h * random.uniform(0.98, 1.02)), head_circ=round(hc * random.uniform(0.98, 1.02), 1),
                    chest_circ=round((hc - 1.5 + min(mm, 6) * 0.35 + max(0, mm - 6) * 0.2) * random.uniform(0.98, 1.02), 1),
                    temperature=38.4 if severe else (37.3 if illness else round(random.uniform(36.4, 36.9), 1)),
                    feeding="poor" if severe else ("breast" if mm < 6 and random.random() < 0.7 else
                                                   random.choice(["breast", "mixed", "mixed", "formula"])),
                    jaundice=severe or (vtype == "patronage" and random.random() < 0.12),
                    breathing_problem=severe and random.random() < 0.6, specialists=specs,
                    complaints=("Isitma, yomon emadi, terisi sarg'aygan" if severe else illness[2] if illness else ""),
                    diagnosis=("Neonatal/o'tkir infeksiya shubhasi" if severe else illness[0] if illness
                               else ("Kindik yarasi bitgan, emizish yo'lga qo'yilgan" if vtype == "patronage"
                                     else "Sog'lom, jismoniy va psixomotor rivojlanishi yoshiga mos")),
                    recommendation=("Zudlik bilan bolalar shifoxonasiga yo'llash" if severe else illness[1] if illness
                                    else "Ko'krak suti, kun tartibi, keyingi oylik ko'rik"))
                nxt = next((c.birth_date + timedelta(days=x[0]) for x in plan if x[0] > d + 3), vdate + timedelta(days=90))
                cv.next_visit_date = nxt
                visits.append(cv)
                last_visit = cv
            if next_due:
                c.next_visit_date = next_due
            elif last_visit:
                c.next_visit_date = max(last_visit.next_visit_date, TODAY + timedelta(days=random.randint(1, 20))) \
                    if last_visit.next_visit_date < TODAY else last_visit.next_visit_date
                last_visit.next_visit_date = c.next_visit_date
            else:
                c.next_visit_date = c.birth_date + timedelta(days=3)
            if special == "sevara":
                c.next_visit_date = TODAY + timedelta(days=1)
            ctx = {"birth_weight": c.birth_weight, "gestational_age_at_birth": c.gestational_age_at_birth,
                   "apgar_5": c.apgar_5, "age_days": age, "overdue_vaccines": overdue,
                   "missed_visit": c.next_visit_date < TODAY}
            if last_visit:
                ctx.update(feeding=last_visit.feeding, jaundice=last_visit.jaundice, convulsions=False,
                           breathing_problem=last_visit.breathing_problem, temperature=float(last_visit.temperature))
                if (last_visit.visit_date - c.birth_date).days <= 14:
                    ctx["weight_loss_pct"] = round((c.birth_weight - last_visit.weight) / c.birth_weight * 100, 1)
            color, reasons = evaluate("child", ctx)
            c.current_color, c.color_reasons, c.color_updated_at = color, reasons, timezone.now()
            if last_visit:
                last_visit.computed_color = last_visit.final_color = color
                last_visit.color_reasons = reasons
        Child.objects.bulk_update(self.children, ["current_color", "color_reasons", "color_updated_at",
                                                  "next_visit_date"], batch_size=2000)
        ChildVisit.objects.bulk_create(visits, batch_size=5000)
        ChildVaccination.objects.bulk_create(vaccs, batch_size=10000)

    # ------------------------------------------------------------------ demo
    def _demo(self, m):
        """Demo mavze: 7 homilador. Hozir 2 qizil (28,6% — sariq). Dilnoza qizilga o'tsa 3/7 = 42,9% → qizil."""
        for t in ["red", "red", "yellow", "green", "green", "green"]:
            self._pregnant(m, 1.0, force=t)
        dil = self._new_mother(m, age=31, lmp_date=TODAY - timedelta(days=32 * 7 + 2), gravidity=2, parity=1,
                               registered_at=TODAY - timedelta(weeks=22))
        dil.last_name, dil.first_name, dil.middle_name = "Karimova", "Dilnoza", "Rustamovna"
        dil.phone, dil.blood_group = self.demo_phone, "A(II) Rh+"
        dil.chronic_conditions = dil.previous_complications = ""
        dil.address = "Chilonzor tumani, 9-kvartal, 12-uy"
        vs = []
        for wk, hb, s, dd in [(10, 124, 112, 72), (20, 120, 115, 74), (26, 118, 116, 76), (30, 112, 118, 76)]:
            v = mother_values("green", wk)
            v.update(visit_date=dil.lmp_date + timedelta(weeks=wk), gestational_week=wk, hb=hb, bp_sys=s, bp_dia=dd,
                     urine_protein="none", edema=False, next_visit_date=TODAY if wk == 30 else
                     dil.lmp_date + timedelta(weeks=next(w for w, *_ in ANC_VISITS if w > wk)))
            vs.append(v)
        dil._visits, dil.next_visit_date = vs, TODAY
        aziz = self._child_with_mother(m, 1.0, days=610, mother=dil, sex="m", first_name="Aziz", birth_weight=3350,
                                       birth_height=51, apgar_1=8, apgar_5=9, gestational_age_at_birth=39)
        aziz._special = "aziz"
        mad = self._new_mother(m, age=26, lmp_date=TODAY - timedelta(days=60 + 278), gravidity=1, parity=1,
                               status=Patient.DELIVERED, delivered_at=TODAY - timedelta(days=60),
                               registered_at=TODAY - timedelta(days=300))
        mad.last_name, mad.first_name, mad.middle_name, mad.phone = "Yusupova", "Madina", "Olimovna", "+998907654321"
        mad.chronic_conditions = mad.previous_complications = ""
        sev = self._child_with_mother(m, 1.0, days=60, mother=mad, sex="f", first_name="Sevara", birth_weight=3100,
                                      birth_height=50, apgar_1=8, apgar_5=9, gestational_age_at_birth=39)
        sev._special = "sevara"
        extra = self._child_with_mother(m, 1.0, days=200, apgar_5=9, gestational_age_at_birth=39, birth_weight=3400)
        extra._special = "extra"

    def _history_alerts(self):
        now = timezone.now()
        ov = User.objects.get(username="ovabmu")
        reds = list(Patient.objects.filter(status="pregnant", current_color="red").select_related("mavze__clinic__district"))
        random.shuffle(reds)
        alerts = []
        actions = [("hospital", "Perinatal markazga yotqizildi"), ("order", "Respublika perinatal markaziga order berildi"),
                   ("consult", "Ertaga 09:00 da konsultatsiyaga chaqirildi"), ("call", "Oilaviy shifokor bilan gaplashildi, QB nazorati"),
                   ("observe", "Tahlillar qayta topshiriladi, 3 kun kuzatuv")]
        for i, p in enumerate(reds[:45]):
            created = now - timedelta(minutes=random.randint(30, 6 * 24 * 60))
            st = "resolved" if i >= 8 else random.choice(["new", "seen"])
            if created > now - timedelta(minutes=40) and st == "resolved":
                st = "seen"
            seen = created + timedelta(minutes=random.choice([4, 7, 9, 12, 15, 18, 25, 33, 47, 70]))
            esc = st != "new" and random.random() < 0.12
            act, note = random.choices(actions, [34, 20, 22, 14, 10])[0] if st == "resolved" else ("", "")
            alerts.append(Alert(patient=p, district=p.mavze.clinic.district, clinic=p.mavze.clinic,
                                from_color=random.choice(["green", "yellow"]), to_color="red", reasons=p.color_reasons,
                                level="ovabmu", status=st, escalated=esc, escalated_at=created + timedelta(minutes=30) if esc else None,
                                seen_by=ov if st != "new" else None, seen_at=seen if st != "new" else None,
                                resolved_by=ov if st == "resolved" else None,
                                resolved_at=seen + timedelta(minutes=random.randint(20, 300)) if st == "resolved" else None,
                                action_type=act, action_note=note))
            alerts[-1]._created = created
        Alert.objects.bulk_create(alerts)
        for a in alerts:
            Alert.objects.filter(pk=a.pk).update(created_at=a._created)
        # Ona tasdig'i tarixi: chora onaga botda yuborilgan, ko'pchilik tasdiqlagan, ayrimlari rad etgan
        from apps.alerts.models import MotherConfirmation
        from apps.alerts.mother import ACTION_TEXT
        mcs = []
        for a in alerts:
            if a.status != "resolved":
                continue
            ans = random.choices([True, False, None], [78, 8, 14])[0]
            mcs.append(MotherConfirmation(kind="alert", object_id=a.pk, patient=a.patient, author=ov, delivered=True,
                                          summary=ACTION_TEXT[a.action_type], confirmed=ans,
                                          responded_at=a.resolved_at + timedelta(minutes=random.randint(3, 180)) if ans is not None else None))
        MotherConfirmation.objects.bulk_create(mcs)
        refs = []
        for p in reds[:30]:
            st = random.choice(["issued", "accepted", "acted", "acted"])
            refs.append(Referral(patient=p, district=p.mavze.clinic.district, clinic=p.mavze.clinic,
                                 from_user=self.doctors[p.mavze.clinic_id], to_level=random.choice(["district", "ovabmu"]),
                                 reason="; ".join(p.color_reasons[:2]), status=st,
                                 accepted_at=now - timedelta(hours=5) if st != "issued" else None,
                                 acted_at=now - timedelta(hours=2) if st == "acted" else None,
                                 action_note="Statsionarga yotqizildi" if st == "acted" else ""))
        Referral.objects.bulk_create(refs)
