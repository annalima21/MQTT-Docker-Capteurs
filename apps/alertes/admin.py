from django.contrib import admin

from apps.alertes.models import Alerte


@admin.register(Alerte)
class AlerteAdmin(admin.ModelAdmin):
    list_display = [
        "capteur", "niveau", "type_alerte", "statut",
        "timestamp_declenchement", "acquittement_user",
    ]
    list_filter = ["niveau", "type_alerte", "statut"]
    search_fields = ["capteur__identifiant", "commentaire"]
    ordering = ["-timestamp_declenchement"]
    date_hierarchy = "timestamp_declenchement"
    # timestamp_declenchement en lecture seule : c'est la date de déclenchement réelle,
    # elle ne doit pas être modifiée après création.
    readonly_fields = ["timestamp_declenchement"]
