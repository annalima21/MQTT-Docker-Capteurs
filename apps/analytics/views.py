"""
Vues du module analytics — Fonctionnalité F4.2 du CdC.

F4.2 — Visualisation des dérives détectées :
    « Affiche pour chaque capteur l'évolution de son indicateur de dérive sur
      les 30 derniers jours. »

Maquette 6 — Page d'analyse de la dérive :
    - graphique de l'évolution du score (ligne rouge = seuil critique),
    - tableau des dernières détections (timestamp, score, moyenne de référence,
      écart-type, lien vers l'alerte associée).

On reste en FBV. Les données du graphique sont injectées directement dans le
template (pas d'API JSON séparée) : c'est plus simple et suffisant ici.
"""

from datetime import timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.core.models import Capteur
from apps.analytics.models import DeriveDetectee
from apps.analytics import derive


def liste_derives(request):
    """
    Chemin URL :
    - /analytics/derives/                  (premier capteur ayant des détections)
    - /analytics/derives/?capteur_id=<id>  (capteur choisi)

    Affiche, pour un capteur, l'évolution de son score de dérive sur 30 jours
    (graphique) et le tableau de ses dernières détections.
    """

    # Liste des capteurs qui ont AU MOINS une détection : inutile de proposer
    # dans le sélecteur des capteurs sans aucune donnée de dérive.
    # distinct() évite les doublons dus à la jointure sur la table des dérives.
    capteurs = Capteur.objects.filter(
        derives__isnull=False
    ).distinct().order_by("identifiant")

    # Capteur sélectionné via le paramètre GET, sinon le premier de la liste.
    capteur_id = request.GET.get("capteur_id")
    if capteur_id:
        capteur_selectionne = get_object_or_404(Capteur, pk=capteur_id)
    else:
        capteur_selectionne = capteurs.first()

    # Fenêtre d'affichage : 30 derniers jours (exigence F4.2).
    depuis = timezone.now() - timedelta(days=30)

    derives = []
    points_graphe = []

    if capteur_selectionne is not None:
        # select_related("alerte") : on affiche le lien vers l'alerte dans le
        # tableau, on charge donc l'alerte dans la même requête (évite le N+1).
        derives = DeriveDetectee.objects.filter(
            capteur=capteur_selectionne,
            timestamp__gte=depuis,
        ).select_related("alerte").order_by("-timestamp")

        # Points pour le graphique, en ordre CHRONOLOGIQUE (ancien → récent).
        # On prépare des dictionnaires simples que le template passera à Chart.js.
        points_graphe = [
            {
                "t": timezone.localtime(d.timestamp).strftime("%d/%m %H:%M"),
                "score": round(d.score, 2),
            }
            for d in derives.order_by("timestamp")
        ]

    return render(request, "analytics/derive.html", {
        "capteurs": capteurs,
        "capteur_selectionne": capteur_selectionne,
        "derives": derives,
        "points_graphe": points_graphe,
        "seuil_warning": derive.SCORE_WARNING,
        "seuil_critique": derive.SCORE_CRITIQUE,
    })


def lancer_analyse(request):
    """
    Chemin URL :
    - /analytics/derives/analyser/  (POST uniquement)

    Déclenche l'analyse de dérive sur tous les capteurs actifs, directement
    depuis l'interface web (équivalent du bouton "à la demande" du CdC F4.1).
    C'est la même logique que la commande analyse_derive, mais appelée depuis
    un bouton plutôt que depuis le terminal.

    On n'accepte que POST : lancer une analyse MODIFIE la base (crée des
    détections et parfois des alertes), donc ce n'est pas une simple lecture.
    """

    # Un accès direct en GET (ex. recharger l'URL) ne doit rien déclencher.
    if request.method != "POST":
        return redirect("analytics:liste_derives")

    capteurs = Capteur.objects.filter(actif=True).order_by("identifiant")

    nb_analyses = 0
    nb_alertes = 0
    nb_ignores = 0

    for capteur in capteurs:
        resultat = derive.analyser_capteur(capteur)

        if resultat["statut"] == "donnees_insuffisantes":
            nb_ignores += 1
            continue

        nb_analyses += 1
        if resultat["alerte_creee"]:
            nb_alertes += 1

    # Message flash affiché en haut de la page après la redirection.
    messages.success(
        request,
        f"Analyse terminée : {nb_analyses} capteur(s) analysé(s), "
        f"{nb_alertes} alerte(s) de dérive créée(s), "
        f"{nb_ignores} ignoré(s) (pas assez de données)."
    )

    return redirect("analytics:liste_derives")
