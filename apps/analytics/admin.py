from django.contrib import admin

from apps.analytics.models import DeriveDetectee, ModeleML


@admin.register(DeriveDetectee)
class DeriveDetecteeAdmin(admin.ModelAdmin):
    list_display = ["capteur", "timestamp", "score", "fenetre_heures", "alerte"]
    list_filter = ["capteur", "fenetre_heures"]
    search_fields = ["capteur__identifiant"]
    ordering = ["-timestamp"]
    date_hierarchy = "timestamp"
    # Les détections de dérive sont produites par l'algorithme d'analyse,
    # on ne les modifie pas manuellement.
    readonly_fields = [
        "capteur", "timestamp", "score",
        "moyenne_ref", "ecart_type_ref", "fenetre_heures",
    ]


@admin.register(ModeleML)
class ModeleMLAdmin(admin.ModelAdmin):
    list_display = ["nom", "version", "actif", "taille_octets", "created_by", "created_at"]
    list_filter = ["actif"]
    search_fields = ["nom", "version"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at"]
