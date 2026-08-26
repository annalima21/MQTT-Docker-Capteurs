from django.urls import path

from apps.analytics import views

app_name = "analytics"

urlpatterns = [
    path("derives/", views.liste_derives, name="liste_derives"),
    path("derives/analyser/", views.lancer_analyse, name="lancer_analyse"),
]
