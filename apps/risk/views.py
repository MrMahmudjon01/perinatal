"""Forma to'ldirilayotganda zonani jonli ko'rsatish (HTMX)."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from apps.accounts import scope
from apps.children.forms import ChildVisitForm
from apps.children.models import Child
from apps.patients.forms import VisitForm
from apps.patients.models import Patient

from .engine import child_context, evaluate, mother_context


@login_required
def preview_mother(request, pk):
    patient = get_object_or_404(scope.patients_for(request.user, Patient.objects.all()), pk=pk)
    form = VisitForm(request.POST)
    form.is_valid()
    visit = form.instance  # is_valid() to'g'ri kiritilgan maydonlarni instance'ga yozadi
    color, reasons = evaluate("mother", mother_context(patient, visit))
    return render(request, "risk/_preview.html", {"color": color, "reasons": reasons, "old": patient.current_color})


@login_required
def preview_child(request, pk):
    child = get_object_or_404(scope.children_for(request.user, Child.objects.all()), pk=pk)
    form = ChildVisitForm(request.POST)
    form.is_valid()
    visit = form.instance  # is_valid() to'g'ri kiritilgan maydonlarni instance'ga yozadi
    visit.child = child
    color, reasons = evaluate("child", child_context(child, visit))
    return render(request, "risk/_preview.html", {"color": color, "reasons": reasons, "old": child.current_color})
