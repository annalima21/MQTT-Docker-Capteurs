from django.contrib import admin
from .models import Mesure


@admin.register(Mesure)
class MesureAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "capteur",
        "timestamp",
        "valeur",
        "qualite",
    )

    list_filter = (
        "capteur",
        "timestamp",
    )

    search_fields = (
        "capteur__identifiant",
        "capteur__nom",
    )

    readonly_fields = (
        "capteur",
        "timestamp",
        "valeur",
        "qualite",
        "meta_json",
    )