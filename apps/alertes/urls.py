from django.urls import path

from apps.alertes import views

# app_name permet d'utiliser {% url 'alertes:liste_alertes' %} dans les templates
# plutôt que {% url 'liste_alertes' %} tout court.
# Ça évite les conflits si deux apps ont une vue du même nom.
app_name = "alertes"

urlpatterns = [
    path("", views.liste_alertes, name="liste_alertes"),
    path("<int:alerte_id>/acquitter/", views.acquitter_alerte, name="acquitter_alerte"),
    path("<int:alerte_id>/fermer/", views.fermer_alerte, name="fermer_alerte"),
]
