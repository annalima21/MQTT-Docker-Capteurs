from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.core.models import Capteur, Seuil, Site, TypeCapteur, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin pour le User custom.
    On étend BaseUserAdmin (l'admin Django natif) pour garder toutes les
    fonctionnalités : changement de mot de passe, gestion des permissions,
    groupes, etc. Pas besoin de tout réécrire.
    """
    pass


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ["nom", "adresse", "latitude", "longitude", "created_at"]
    search_fields = ["nom", "adresse"]
    ordering = ["nom"]
    readonly_fields = ["created_at"]


@admin.register(TypeCapteur)
class TypeCapteurAdmin(admin.ModelAdmin):
    list_display = ["code", "libelle", "unite_si", "plage_min", "plage_max"]
    search_fields = ["code", "libelle"]
    ordering = ["code"]


@admin.register(Capteur)
class CapteurAdmin(admin.ModelAdmin):
    list_display = [
        "identifiant", "nom", "site", "type_capteur",
        "actif", "firmware_version", "date_installation",
    ]
    list_filter = ["actif", "site", "type_capteur"]
    search_fields = ["identifiant", "nom"]
    ordering = ["identifiant"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Seuil)
class SeuilAdmin(admin.ModelAdmin):
    list_display = ["capteur", "type_seuil", "valeur", "actif"]
    list_filter = ["type_seuil", "actif"]
    # search sur les champs du capteur lié via le double underscore Django ORM.
    search_fields = ["capteur__identifiant", "capteur__nom"]
    ordering = ["capteur", "type_seuil"]
