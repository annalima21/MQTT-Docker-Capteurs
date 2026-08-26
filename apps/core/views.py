import json

# timedelta permet de calculer une période relative :
# dernière heure, 24 dernières heures, 7 derniers jours, etc.
from datetime import timedelta

# timezone permet de gérer proprement les dates Django avec le fuseau horaire.
from django.utils import timezone

# parse_datetime permet de convertir une date reçue depuis un input HTML
# en objet datetime Python.
from django.utils.dateparse import parse_datetime

from django.contrib import messages
from django.db.models import Count, OuterRef, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render


from apps.alertes.models import Alerte
from apps.core.models import Capteur, Site, Seuil
from apps.ingestion.models import Mesure
from .forms import CapteurForm


def accueil(request):
    """
    Chemin URL :
    - /

    Vue FBV — page d'accueil avec tableau de bord.
    """

    nb_capteurs_actifs = Capteur.objects.filter(actif=True).count()
    nb_sites = Site.objects.count()
    nb_alertes_ouvertes = Alerte.objects.filter(
        statut=Alerte.StatutChoices.OUVERTE
    ).count()

    # on charge seulement les capteurs actifs pour la table "Système".
    # select_related évite une requête supplémentaire par capteur pour site/type.
    capteurs = Capteur.objects.select_related(
        "site",
        "type_capteur",
    ).filter(
        actif=True
    ).order_by("identifiant")

    return render(request, "core/accueil.html", {
        "nb_capteurs_actifs": nb_capteurs_actifs,
        "nb_sites": nb_sites,
        "nb_alertes_ouvertes": nb_alertes_ouvertes,
        "capteurs": capteurs,
    })


def liste_capteurs(request):
    """
    Chemin URL :
    - /capteurs/

    Vue FBV — tableau de tous les capteurs du parc.
    Passe le queryset complet avec site et type_capteur déjà chargés.
    """

    capteurs = Capteur.objects.select_related("site", "type_capteur").all()

    return render(request, "core/liste_capteurs.html", {"capteurs": capteurs})


def detail_capteur(request, capteur_id):
    """
    Chemin URL :
    - /capteurs/<capteur_id>/

    Vue FBV — fiche détail d'un capteur.
    """

    capteur = get_object_or_404(
        Capteur.objects.select_related("site", "type_capteur"),
        pk=capteur_id,
    )

    seuils_actifs = capteur.seuils.filter(actif=True).order_by("type_seuil")

    alertes_ouvertes = capteur.alertes.filter(
        statut=Alerte.StatutChoices.OUVERTE
    ).order_by("-timestamp_declenchement")

    mesures_recentes = capteur.mesures.order_by("-timestamp")[:20]

    config_json_formate = json.dumps(
        capteur.config_json,
        indent=2,
        ensure_ascii=False,
    )

    return render(request, "core/detail_capteur.html", {
        "capteur": capteur,
        "seuils_actifs": seuils_actifs,
        "alertes_ouvertes": alertes_ouvertes,
        "mesures_recentes": mesures_recentes,
        "config_json_formate": config_json_formate,
    })


def liste_sites(request):
    """
    Chemin URL :
    - /sites/

    Vue FBV — liste des sites avec le nombre de capteurs associés.
    """
    sites = Site.objects.annotate(
        nb_capteurs=Count("capteurs")
    ).order_by("nom")

    return render(request, "core/liste_sites.html", {"sites": sites})


def capteur_create(request):
    """
    Chemin URL :
    - /capteurs/nouveau/

    Vue FBV — création d'un capteur via formulaire CapteurForm.
    """

    if request.method == "POST":
        form = CapteurForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("core:liste_capteurs")
    else:
        form = CapteurForm()

    return render(request, "capteurs/form.html", {"form": form})


def capteur_update(request, capteur_id):
    """
    Chemin URL :
    - /capteurs/<capteur_id>/modifier/

    Vue FBV — modification d'un capteur existant.
    """

    capteur = get_object_or_404(Capteur, pk=capteur_id)

    if request.method == "POST":
        form = CapteurForm(request.POST, instance=capteur)
        if form.is_valid():
            form.save()
            return redirect("core:liste_capteurs")
    else:
        form = CapteurForm(instance=capteur)

    return render(request, "capteurs/form.html", {
        "form": form,
        "capteur": capteur,
    })


def capteur_delete(request, capteur_id):
    """
    Chemin URL :
    - /capteurs/<capteur_id>/supprimer/

    Vue FBV — suppression d'un capteur avec page de confirmation.

    """

    capteur = get_object_or_404(Capteur, pk=capteur_id)

    if capteur.mesures.exists():
        messages.error(
            request,
            "Impossible : ce capteur possède des mesures enregistrées."
        )
        return redirect("core:liste_capteurs")

    if request.method == "POST":
        capteur.delete()
        return redirect("core:liste_capteurs")

    return render(request, "capteurs/confirm_delete.html", {
        "capteur": capteur,
    })


# ========================================
# API de la table "Système" sur l'accueil
# ========================================

def calculer_etat_capteur(capteur, valeur):
    """
    Fonction utilisée par :
    - api_mesures_actuelles()

    Objectif :
    - calculer l'état visuel d'un capteur à partir de sa dernière mesure
      et des seuils actifs enregistrés en base.

    États possibles :
    - OK
    - Warning haut / Warning bas
    - Critique haut / Critique bas
    - Sans mesure
    - Inactif
    """

    if not capteur.actif:
        return {
            "texte": "Inactif",
            "classe": "secondary",
        }

    if valeur is None:
        return {
            "texte": "Sans mesure",
            "classe": "secondary",
        }

    seuils = {
        seuil.type_seuil: seuil.valeur
        for seuil in capteur.seuils.all()
        if seuil.actif
    }

    bas_critique = seuils.get(Seuil.TypeSeuilChoices.BAS_CRITIQUE)
    bas_warning = seuils.get(Seuil.TypeSeuilChoices.BAS_WARNING)
    haut_warning = seuils.get(Seuil.TypeSeuilChoices.HAUT_WARNING)
    haut_critique = seuils.get(Seuil.TypeSeuilChoices.HAUT_CRITIQUE)

    if bas_critique is not None and valeur <= bas_critique:
        return {
            "texte": "Critique bas",
            "classe": "danger",
        }

    if haut_critique is not None and valeur >= haut_critique:
        return {
            "texte": "Critique haut",
            "classe": "danger",
        }

    if bas_warning is not None and valeur <= bas_warning:
        return {
            "texte": "Warning bas",
            "classe": "warning text-dark",
        }

    if haut_warning is not None and valeur >= haut_warning:
        return {
            "texte": "Warning haut",
            "classe": "warning text-dark",
        }

    return {
        "texte": "OK",
        "classe": "success",
    }


def api_mesures_actuelles(request):
    """
    Chemin URL :
    - /api/mesures-actuelles/

    - API JSON utilisée par JavaScript sur la page accueil.
    - Elle retourne la dernière mesure connue de chaque capteur actif.
    - Elle permet d'actualiser la table sans recharger toute la page.

    Bibliothèques utilisées :
    - JsonResponse : retourner du JSON.
    - OuterRef/Subquery : récupérer la dernière mesure de chaque capteur.
    - timezone : afficher la date dans le fuseau local Django.
    """

    derniere_mesure = Mesure.objects.filter(
        capteur=OuterRef("pk")
    ).order_by(
        "-timestamp"
    )

    capteurs = Capteur.objects.select_related(
        "site",
        "type_capteur"
    ).prefetch_related(
        "seuils"
    ).filter(
        actif=True
    ).annotate(
        derniere_valeur=Subquery(
            derniere_mesure.values("valeur")[:1]
        ),
        derniere_timestamp=Subquery(
            derniere_mesure.values("timestamp")[:1]
        ),
        derniere_qualite=Subquery(
            derniere_mesure.values("qualite")[:1]
        ),
    ).order_by(
        "identifiant"
    )

    donnees = []

    for capteur in capteurs:
        valeur = capteur.derniere_valeur
        unite = capteur.type_capteur.unite_si

        etat = calculer_etat_capteur(capteur, valeur)

        if valeur is None:
            valeur_affichee = "—"
        else:
            valeur_affichee = f"{valeur:.2f} {unite}"

        if capteur.derniere_timestamp:
            timestamp = capteur.derniere_timestamp.isoformat()
            timestamp_affiche = timezone.localtime(
                capteur.derniere_timestamp
            ).strftime("%d/%m/%Y %H:%M:%S")
        else:
            timestamp = None
            timestamp_affiche = "Aucune mesure"

        donnees.append({
            "id": capteur.id,
            "identifiant": capteur.identifiant,
            "nom": capteur.nom,
            "type": capteur.type_capteur.libelle,
            "unite": unite,
            "valeur": valeur,
            "valeur_affichee": valeur_affichee,
            "timestamp": timestamp,
            "timestamp_affiche": timestamp_affiche,
            "qualite": capteur.derniere_qualite,
            "etat": etat["texte"],
            "etat_classe": etat["classe"],
        })

    return JsonResponse({
        "capteurs": donnees
    })


# ============================================================
# Page historique des mesures
# ============================================================

def historique_mesures(request, capteur_id=None):
    """
    Chemins URL :
    - /historique/
    - /historique/<capteur_id>/

    - affiche la page d'historique des mesures.
    - fournit au template la liste des capteurs actifs.
    - si un capteur_id est fourni, il est sélectionné automatiquement.
    """

    capteurs = Capteur.objects.select_related(
        "site",
        "type_capteur"
    ).filter(
        actif=True
    ).order_by(
        "identifiant"
    )

    if capteur_id is not None:
        capteur_selectionne = get_object_or_404(
            capteurs,
            pk=capteur_id
        )
    else:
        capteur_selectionne = capteurs.first()

    return render(request, "core/historique_mesures.html", {
        "capteurs": capteurs,
        "capteur_selectionne": capteur_selectionne,
    })


def calculer_debut_periode(periode):
    """
    Fonction utilisée par :
    - api_historique_mesures()

    - convertit une période textuelle en date de début.

    - 1h  -> maintenant - 1 heure
    - 24h -> maintenant - 24 heures
    - 7j  -> maintenant - 7 jours
    """

    maintenant = timezone.now()

    periodes = {
        "1h": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "24h": timedelta(hours=24),
        "7j": timedelta(days=7),
        "30j": timedelta(days=30),
    }

    duree = periodes.get(periode, timedelta(hours=24))

    return maintenant - duree


def convertir_datetime_local(valeur):
    """
    Fonction utilisée par :
    - api_historique_mesures()

    - convertit une valeur venant des champs date + heure HTML
      en datetime utilisable par Django.

    Exemple reçu depuis le navigateur :
    - 2026-05-05T08:00

    Bibliothèques utilisées :
    - parse_datetime : transforme le texte en datetime Python.
    - timezone : rend la date compatible avec le fuseau horaire Django.
    """

    if not valeur:
        return None

    date_convertie = parse_datetime(valeur)

    if date_convertie is None:
        return None

    if timezone.is_naive(date_convertie):
        date_convertie = timezone.make_aware(
            date_convertie,
            timezone.get_current_timezone()
        )

    return date_convertie


def api_historique_mesures(request):
    """
    Chemin URL :
    - /api/historique-mesures/

    - API JSON utilisée par la page historique.
    - retourne les mesures d'un capteur sur une période donnée.

    Paramètres GET :
    - capteur_id
    - periode : 1h, 6h, 24h, 7j, 30j, custom
    - date_debut : utilisé seulement si periode=custom
    - date_fin : utilisé seulement si periode=custom

    Bibliothèques utilisées :
    - JsonResponse : retourner les données au format JSON.
    - timezone : gérer les dates locales.
    - parse_datetime : convertir les dates venant du formulaire.
    """

    capteur_id = request.GET.get("capteur_id")
    periode = request.GET.get("periode", "24h")

    if not capteur_id:
        return JsonResponse({
            "erreur": "Paramètre capteur_id manquant."
        }, status=400)

    capteur = get_object_or_404(
        Capteur.objects.select_related(
            "site",
            "type_capteur"
        ).filter(
            actif=True
        ),
        pk=capteur_id,
    )

    maintenant = timezone.now()

    if periode == "custom":
        date_debut = convertir_datetime_local(
            request.GET.get("date_debut")
        )
        date_fin = convertir_datetime_local(
            request.GET.get("date_fin")
        )

        if date_debut is None:
            return JsonResponse({
                "erreur": "Date de début invalide ou manquante."
            }, status=400)

        if date_fin is None:
            date_fin = maintenant

    else:
        date_debut = calculer_debut_periode(periode)
        date_fin = maintenant

    mesures_qs = Mesure.objects.filter(
        capteur=capteur,
        timestamp__gte=date_debut,
        timestamp__lte=date_fin,
    ).order_by(
        "-timestamp"
    )

    # On limite à 1000 mesures pour ne pas alourdir la page historique.
    mesures = list(mesures_qs[:1000])
    mesures.reverse()

    unite = capteur.type_capteur.unite_si
    donnees_mesures = []

    for mesure in mesures:
        timestamp_local = timezone.localtime(mesure.timestamp)

        donnees_mesures.append({
            "timestamp": timestamp_local.isoformat(),
            "timestamp_affiche": timestamp_local.strftime("%d/%m/%Y %H:%M:%S"),
            "valeur": float(mesure.valeur),
            "valeur_affichee": f"{mesure.valeur:.2f} {unite}",
            "qualite": float(mesure.qualite) if mesure.qualite is not None else None,
        })

    return JsonResponse({
        "capteur": {
            "id": capteur.id,
            "identifiant": capteur.identifiant,
            "nom": capteur.nom,
            "unite": unite,
            "type": capteur.type_capteur.libelle,
        },
        "periode": periode,
        "date_debut": timezone.localtime(date_debut).strftime("%d/%m/%Y %H:%M:%S"),
        "date_fin": timezone.localtime(date_fin).strftime("%d/%m/%Y %H:%M:%S"),
        "nombre_mesures": len(donnees_mesures),
        "mesures": donnees_mesures,
    })