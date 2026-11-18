"""Ko'riksiz zona qayta hisoblash (scheduler, emlash belgilanganda)."""
from apps.alerts.services import set_subject_color

from .engine import child_context, evaluate, mother_context


def recompute_patient(patient):
    visit = patient.visits.order_by("-visit_date", "-created_at").first()
    color, reasons = evaluate("mother", mother_context(patient, visit))
    # shifokor qo'lda yuqoriroq zona belgilagan bo'lsa, avtomatik pasaytirmaymiz
    if visit and visit.final_color != visit.computed_color:
        from .engine import COLOR_ORDER
        if COLOR_ORDER[visit.final_color] > COLOR_ORDER[color]:
            color = visit.final_color
            reasons = visit.color_reasons
    return set_subject_color(patient, color, reasons)


def recompute_child(child):
    visit = child.visits.order_by("-visit_date", "-created_at").first()
    color, reasons = evaluate("child", child_context(child, visit))
    if visit and visit.final_color != visit.computed_color:
        from .engine import COLOR_ORDER
        if COLOR_ORDER[visit.final_color] > COLOR_ORDER[color]:
            color = visit.final_color
            reasons = visit.color_reasons
    return set_subject_color(child, color, reasons, child=True)
