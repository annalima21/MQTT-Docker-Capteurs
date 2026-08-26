from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    # --- Dashboard ---
    path("", views.accueil, name="accueil"),

    # --- Capteurs ---
    path("capteurs/", views.liste_capteurs, name="liste_capteurs"),
    path("capteurs/nouveau/", views.capteur_create, name="capteur_create"),
    path("capteurs/<int:capteur_id>/", views.detail_capteur, name="detail_capteur"),
    path("capteurs/<int:capteur_id>/modifier/", views.capteur_update, name="capteur_update"),
    path("capteurs/<int:capteur_id>/supprimer/", views.capteur_delete, name="capteur_delete"),

    # --- Sites ---
    path("sites/", views.liste_sites, name="liste_sites"),

    # --- Historique ---
    path("historique/", views.historique_mesures, name="historique_mesures"),
    path("historique/<int:capteur_id>/", views.historique_mesures, name="historique_capteur"),

    # --- API JSON ---
    path("api/mesures-actuelles/", views.api_mesures_actuelles, name="api_mesures_actuelles"),
    path("api/historique-mesures/", views.api_historique_mesures, name="api_historique_mesures"),
]