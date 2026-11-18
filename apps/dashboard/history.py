"""Zonalar dinamikasi: poliklinikalarning oylik holati → tuman va shahar bo'yicha o'zgarishlar.

- snapshot_current(): joriy oy holatini jonli ma'lumotdan yozadi (scheduler har soatda chaqiradi).
- backfill_demo(): demo uchun o'tgan oylar tarixini yaratadi (haqiqiy tizimda tarix o'z-o'zidan to'planadi).
- dynamics(): tanlangan hudud birliklari bo'yicha oyma-oy seriya va o'zgarishlar.
"""
import random
from datetime import date

from apps.children.models import Child
from apps.geo.models import Clinic, District, ZoneSnapshot
from apps.patients.models import Patient
from apps.risk.engine import region_color

from . import stats

RANK = {"green": 0, "yellow": 1, "red": 2, "none": -1}


def month_start(d=None):
    d = d or date.today()
    return d.replace(day=1)


def add_months(m, k):
    y, mo = divmod(m.year * 12 + m.month - 1 + k, 12)
    return date(y, mo + 1, 1)


def snapshot_current():
    """Joriy oy uchun har bir poliklinika holatini yangilaydi."""
    m = month_start()
    g = stats.grouped(Patient.objects.all(), Child.objects.none(), "clinic")
    n = 0
    for cid in Clinic.objects.values_list("id", flat=True):
        d = g.get(cid) or {}
        ZoneSnapshot.objects.update_or_create(
            clinic_id=cid, month=m,
            defaults={"p_total": d.get("p_total", 0), "p_red": d.get("p_red", 0),
                      "p_yellow": d.get("p_yellow", 0), "demo": False})
        n += 1
    return n


def backfill_demo(months=6, seed=2026):
    """Demo tarix: har poliklinika uchun trend (yaxshilanish / yomonlashish / barqaror) bo'yicha o'tgan oylar.

    Joriy oy — jonli ma'lumot; o'tgan oylar shu nuqtaga olib keladigan tasodifiy, lekin izchil yo'l.
    """
    snapshot_current()
    rnd = random.Random(seed)
    cur = month_start()
    ZoneSnapshot.objects.filter(demo=True).delete()
    objs = []
    for s in ZoneSnapshot.objects.filter(month=cur).select_related("clinic"):
        total = max(s.p_total, 1)
        red_sh, yel_sh = s.p_red / total, s.p_yellow / total
        trend = rnd.choices(["better", "worse", "stable"], weights=[38, 24, 38])[0]
        step = {"better": rnd.uniform(0.025, 0.06), "worse": -rnd.uniform(0.015, 0.035), "stable": 0}[trend]
        for k in range(1, months + 1):
            # o'tmishga qarab: "better" — avval qizil ko'proq edi, "worse" — avval kamroq edi
            r = min(0.6, max(0.0, red_sh + step * k + rnd.gauss(0, 0.012)))
            y = min(0.8 - r, max(0.05, yel_sh + rnd.gauss(0, 0.03)))
            t = max(1, round(s.p_total * (1 + rnd.gauss(0, 0.05))))
            objs.append(ZoneSnapshot(clinic_id=s.clinic_id, month=add_months(cur, -k), p_total=t,
                                     p_red=round(t * r), p_yellow=round(t * y), demo=True))
    ZoneSnapshot.objects.bulk_create(objs)
    return len(objs)


def _pack(t, r, y):
    pct = round(r / t * 100, 1) if t else 0
    return {"t": t, "r": r, "y": y, "pct": pct, "color": region_color(r, t)}


def dynamics(clinic_ids, unit, months=7, compare=1):
    """unit: 'district' | 'clinic'. clinic_ids — ko'rish doirasidagi poliklinikalar.

    Qaytaradi: oylar ro'yxati, har birlik bo'yicha seriya + taqqoslash, umumiy (jami) seriya.
    """
    cur = month_start()
    mlist = [add_months(cur, -k) for k in range(months - 1, -1, -1)]
    base_m = add_months(cur, -compare)
    snaps = ZoneSnapshot.objects.filter(clinic_id__in=clinic_ids, month__in=mlist).select_related("clinic")
    acc, tot = {}, {m: [0, 0, 0] for m in mlist}
    names = {}
    for s in snaps:
        key = s.clinic.district_id if unit == "district" else s.clinic_id
        a = acc.setdefault(key, {m: [0, 0, 0] for m in mlist})[s.month]
        a[0] += s.p_total; a[1] += s.p_red; a[2] += s.p_yellow
        T = tot[s.month]; T[0] += s.p_total; T[1] += s.p_red; T[2] += s.p_yellow
    if unit == "district":
        names = {d.id: d for d in District.objects.filter(id__in=acc)}
    else:
        names = {c.id: c for c in Clinic.objects.filter(id__in=acc).select_related("district")}

    rows = []
    for key, ser in acc.items():
        series = [_pack(*ser[m]) for m in mlist]
        now, before = _pack(*ser[cur]), _pack(*ser[base_m]) if base_m in ser else _pack(0, 0, 0)
        if not now["t"]:
            continue
        diff = RANK[now["color"]] - RANK[before["color"]]
        change = "none" if before["color"] == "none" else ("worse" if diff > 0 else "better" if diff < 0 else "same")
        rows.append({"obj": names.get(key), "series": series, "now": now, "before": before, "change": change,
                     "delta": round(now["pct"] - before["pct"], 1)})
    order = {"worse": 0, "better": 1, "same": 2, "none": 3}
    rows.sort(key=lambda r: (order[r["change"]], -abs(r["delta"])))
    total = [_pack(*tot[m]) for m in mlist]
    i = mlist.index(base_m)
    summary = {
        "better": sum(r["change"] == "better" for r in rows),
        "worse": sum(r["change"] == "worse" for r in rows),
        "same": sum(r["change"] == "same" for r in rows),
        "now": total[-1], "before": total[i], "delta": round(total[-1]["pct"] - total[i]["pct"], 1),
        "zones_now": {z: sum(r["now"]["color"] == z for r in rows) for z in ("green", "yellow", "red")},
        "zones_before": {z: sum(r["before"]["color"] == z for r in rows) for z in ("green", "yellow", "red")},
        "demo": snaps.filter(demo=True).exists(),
    }
    by_month = [{z: sum(r["series"][k]["color"] == z for r in rows) for z in ("green", "yellow", "red")}
                for k in range(len(mlist))]
    return {"months": mlist, "base_month": base_m, "rows": rows, "total": total, "summary": summary,
            "by_month": by_month}
