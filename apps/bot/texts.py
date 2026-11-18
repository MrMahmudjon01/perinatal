"""Onalar uchun bot matnlari (sinxron, ORM). Onaga zona rangi ko'rsatilmaydi — shifokor tavsiyasi ko'rsatiladi."""
import html
from datetime import date

from apps.children.models import Child, ChildVaccination
from apps.patients.models import Patient
from apps.patients.schedule import anc_plan

def e(s):
    return html.escape(str(s), quote=False)


def _d(d):
    return d.strftime("%d.%m.%Y") if d else "—"


def mother_profile(p: Patient):
    lines = [f"🤰 <b>{e(p.full_name)}</b>", f"🏥 {e(p.mavze.clinic.name)}, {e(p.mavze.name)}"]
    if p.status == Patient.PREGNANT:
        lines += [f"Homiladorlik muddati: <b>{p.gestational_weeks} hafta</b>",
                  f"Taxminiy tug'ruq sanasi: <b>{_d(p.edd)}</b>"]
    elif p.delivered_at:
        lines.append(f"Tug'ruq sanasi: {_d(p.delivered_at)}")
    lines.append(f"Qon guruhi: {e(p.blood_group or '—')}")
    if p.chronic_conditions:
        lines.append(f"Surunkali kasalliklar: {e(p.chronic_conditions)}")
    if p.previous_complications:
        lines.append(f"Oldingi asoratlar: {e(p.previous_complications)}")
    last = p.visits.first()
    if last:
        lines += ["", f"<b>Oxirgi ko'rik ({_d(last.visit_date)})</b>"]
        if last.diagnosis:
            lines.append(f"Xulosa: {e(last.diagnosis)}")
        if last.recommendation:
            lines.append(f"Tavsiya: {e(last.recommendation)}")
    if p.status == Patient.PREGNANT:
        plan = anc_plan(p)
        done = sum(1 for x in plan if x["status"] == "done")
        lines.append(f"\n🗓 Antenatal reja: <b>{done}/8</b> tashrif bajarildi")
        nxt = next((x for x in plan if x["status"] in ("due", "upcoming")), None)
        if nxt:
            lines.append(f"Keyingi rejali tashrif: {nxt['week']}-hafta ({_d(nxt['date'])})"
                         + (f" — {e(nxt['screening'])}" if nxt["screening"] else ""))
    if p.next_visit_date and p.status == Patient.PREGNANT:
        flag = " ❗️ (o'tib ketgan — iltimos, poliklinikaga keling)" if p.next_visit_date < date.today() else ""
        lines.append(f"\n📅 Keyingi ko'rik: <b>{_d(p.next_visit_date)}</b>{flag}")
    return "\n".join(lines)


def mother_history(p: Patient):
    visits = list(p.visits.select_related("doctor").order_by("-visit_date"))
    if not visits:
        return "Hali ko'rik qayd etilmagan."
    lines = [f"📋 <b>Ko'riklar va tahlillar tarixi</b> ({len(visits)} ta)\n"]
    for v in visits:
        row = [f"🗓 <b>{_d(v.visit_date)}</b>" + (f" · {v.gestational_week}-hafta" if v.gestational_week else "")]
        vals = []
        if v.bp:
            vals.append(f"QB {v.bp}")
        if v.hb:
            vals.append(f"Hb {v.hb}")
        if v.urine_protein:
            vals.append(f"siydikda oqsil: {v.get_urine_protein_display()}")
        if v.weight:
            vals.append(f"vazn {v.weight} kg")
        if vals:
            row.append("   " + ", ".join(vals))
        if v.complaints:
            row.append(f"   Shikoyat: {e(v.complaints)}")
        if v.diagnosis:
            row.append(f"   Xulosa: {e(v.diagnosis)}")
        if v.recommendation:
            row.append(f"   Tavsiya: {e(v.recommendation)}")
        if v.doctor:
            row.append(f"   👩‍⚕️ {e(str(v.doctor))}")
        lines.append("\n".join(row))
    return "\n\n".join(lines)


def children_list_text(p: Patient):
    kids = list(p.children.all())
    if not kids:
        return "Farzand ma'lumoti hali kiritilmagan.", []
    return "👶 <b>Farzandlaringiz</b> — birini tanlang:", [(f"{c.first_name} ({c.age_label})", c.id) for c in kids]


def child_card(c: Child):
    lines = [f"👶 <b>{e(c.full_name)}</b> — {c.get_sex_display().lower()}, {c.age_label}",
             f"Tug'ilgan: {_d(c.birth_date)}, vazn {c.birth_weight} g" + (f", bo'y {c.birth_height} sm" if c.birth_height else "")]
    last = c.visits.first()
    if last:
        lines += ["", f"<b>Oxirgi ko'rik ({_d(last.visit_date)})</b>"]
        if last.weight:
            lines.append(f"Vazn: {last.weight} g" + (f", bo'y {last.height} sm" if last.height else "")
                         + (f", bosh aylanasi {last.head_circ} sm" if last.head_circ else ""))
        if last.diagnosis:
            lines.append(f"Xulosa: {e(last.diagnosis)}")
        if last.recommendation:
            lines.append(f"Tavsiya: {e(last.recommendation)}")
    done = c.vaccinations.filter(status=ChildVaccination.DONE).count()
    total_due = c.vaccinations.filter(due_date__lte=date.today()).count()
    lines.append(f"\n💉 Emlashlar: {done} ta bajarilgan (muddati kelgan {total_due} tadan)")
    overdue = c.vaccinations.filter(status=ChildVaccination.OVERDUE).count()
    if overdue:
        lines.append(f"❗️ <b>{overdue} ta emlash kechikkan</b> — poliklinikaga murojaat qiling")
    nxt = c.vaccinations.filter(status=ChildVaccination.PLANNED).select_related("vaccine").first()
    if nxt:
        lines.append(f"Keyingi emlash: <b>{e(nxt.vaccine.name)}</b> — {_d(nxt.due_date)}")
    if c.next_visit_date:
        lines.append(f"📅 Keyingi ko'rik: <b>{_d(c.next_visit_date)}</b>")
    return "\n".join(lines)


def child_vaccinations(c: Child):
    lines = [f"💉 <b>{e(c.first_name)} — emlash kalendari</b>\n"]
    for v in c.vaccinations.select_related("vaccine"):
        if v.status == ChildVaccination.DONE:
            mark = f"✅ {_d(v.done_date)}"
        elif v.status == ChildVaccination.OVERDUE:
            mark = f"❗️ kechikdi (reja {_d(v.due_date)})"
        else:
            mark = f"🕒 reja: {_d(v.due_date)}"
        lines.append(f"<b>{e(v.vaccine.code)}</b> · {e(v.vaccine.age_label)} — {mark}\n   <i>{e(v.vaccine.disease)}</i>")
    return "\n".join(lines)


def child_history(c: Child):
    visits = list(c.visits.select_related("doctor"))
    if not visits:
        return "Ko'rik hali qayd etilmagan."
    lines = [f"📋 <b>{e(c.first_name)} — ko'riklar va kasallik tarixi</b>\n"]
    for v in visits:
        row = [f"🗓 <b>{_d(v.visit_date)}</b>"]
        vals = []
        if v.weight:
            vals.append(f"vazn {v.weight} g")
        if v.height:
            vals.append(f"bo'y {v.height} sm")
        if v.temperature:
            vals.append(f"t° {v.temperature}")
        if vals:
            row.append("   " + ", ".join(vals))
        if getattr(v, "specialists", None):
            row.append(f"   Mutaxassislar: {e('; '.join(v.specialists))}")
        if v.complaints:
            row.append(f"   Shikoyat: {e(v.complaints)}")
        if v.diagnosis:
            row.append(f"   Xulosa: {e(v.diagnosis)}")
        if v.recommendation:
            row.append(f"   Tavsiya: {e(v.recommendation)}")
        lines.append("\n".join(row))
    return "\n\n".join(lines)


def upcoming(p: Patient):
    today = date.today()
    lines = ["📅 <b>Yaqin qabullar va emlashlar</b>\n"]
    if p.status == Patient.PREGNANT and p.next_visit_date:
        lines.append(f"🤰 Sizning ko'rigingiz: <b>{_d(p.next_visit_date)}</b>"
                     + (" ❗️ o'tib ketgan" if p.next_visit_date < today else ""))
    from apps.children.models import SessionInvite
    for inv in SessionInvite.objects.filter(child__mother=p, attended=False, session__status="planned",
                                            session__date__gte=today).select_related("session__vaccine", "session__clinic", "child"):
        s = inv.session
        lines.append(f"💉 {e(inv.child.first_name)}: <b>{e(s.vaccine.name)}</b> — <b>{_d(s.date)} soat {s.time:%H:%M}</b>, {e(s.clinic.name)}")
    for c in p.children.all():
        if c.next_visit_date and c.next_visit_date >= today:
            lines.append(f"👶 {e(c.first_name)} ko'rigi: <b>{_d(c.next_visit_date)}</b>")
        for v in c.vaccinations.filter(status__in=["planned", "overdue"]).select_related("vaccine")[:3]:
            tag = "❗️ kechikkan" if v.status == "overdue" else _d(v.due_date)
            lines.append(f"💉 {e(c.first_name)}: {e(v.vaccine.name)} — <b>{tag}</b>")
    if len(lines) == 1:
        lines.append("Rejalashtirilgan qabul yo'q.")
    lines.append(f"\n🏥 {e(p.mavze.clinic.name)}")
    return "\n".join(lines)


HELP = ("ℹ️ Bu bot orqali siz:\n• o'z ko'riklaringiz va tahlillaringiz tarixini,\n• farzandingizning ko'riklari, "
        "kasallik tarixi va emlashlarini,\n• keyingi qabul va emlash sanalarini ko'rasiz.\n"
        "• 🤖 AI yordamchi — homiladorlik va chaqaloq parvarishi bo'yicha savolingizni oddiy yozing.\n"
        "• 🚨 «Xavf belgilari» tugmasi — o'zingizda yoki farzandingizda xavfli belgi bo'lsa, shifokorga darhol xabar beradi.\n\n"
        "Bot qabul va emlash kuni haqida oldindan eslatadi, shifokoringiz xabarlarini yetkazadi.\n"
        "Savollar bo'lsa, oilaviy poliklinikangizga murojaat qiling. Shoshilinch holatda — 103.")
