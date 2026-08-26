from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.alertes.models import Alerte


def liste_alertes(request):
    """
    Vue FBV — affiche toutes les alertes avec un filtre optionnel par statut.

    On peut filtrer via l'URL : /alertes/?statut=ouverte
    Si pas de filtre dans l'URL, on affiche toutes les alertes.
    """
    # On récupère le paramètre ?statut= dans l'URL (GET param).
    # S'il n'existe pas, on met une chaîne vide = pas de filtre.
    statut_filtre = request.GET.get("statut", "")

    # select_related charge d'un coup capteur, seuil et acquittement_user
    # dans la même requête SQL via JOIN.
    # Sans ça on aurait 1 requête SQL supplémentaire par alerte pour
    # accéder à alerte.capteur.identifiant dans le template (N+1).
    alertes = Alerte.objects.select_related(
        "capteur",
        "seuil",
        "acquittement_user",
    ).order_by("-timestamp_declenchement")

    # Si le filtre est valide (une des 3 valeurs possibles), on l'applique.
    # On vérifie que c'est une valeur connue pour éviter les injections
    # via le paramètre GET (ex : ?statut=<script>).
    if statut_filtre in [
        Alerte.StatutChoices.OUVERTE,
        Alerte.StatutChoices.ACQUITTEE,
        Alerte.StatutChoices.FERMEE,
    ]:
        alertes = alertes.filter(statut=statut_filtre)

    # On compte les alertes ouvertes pour afficher un badge dans les boutons.
    nb_ouvertes = Alerte.objects.filter(statut=Alerte.StatutChoices.OUVERTE).count()

    return render(request, "alertes/list.html", {
        "alertes": alertes,
        "statut_filtre": statut_filtre,
        "nb_ouvertes": nb_ouvertes,
    })


def acquitter_alerte(request, alerte_id):
    """
    Vue FBV — acquitter une alerte (la passer de 'ouverte' à 'acquittee').

    GET  : affiche la page de confirmation avec un champ commentaire.
    POST : enregistre l'acquittement et redirige vers la liste.

    On ne peut acquitter qu'une alerte 'ouverte'. Si elle est déjà
    acquittée ou fermée, on renvoie directement vers la liste.
    """
    alerte = get_object_or_404(Alerte, pk=alerte_id)

    # Sécurité : on ne peut pas acquitter une alerte déjà acquittée ou fermée.
    # Ça évite de traiter deux fois la même alerte si quelqu'un recharge la page.
    if alerte.statut != Alerte.StatutChoices.OUVERTE:
        return redirect("alertes:liste_alertes")

    if request.method == "POST":
        # On récupère le commentaire du formulaire.
        # .strip() enlève les espaces en début/fin — propre.
        commentaire = request.POST.get("commentaire", "").strip()

        # On met à jour les champs d'acquittement directement sur l'objet.
        alerte.statut = Alerte.StatutChoices.ACQUITTEE
        # timezone.now() donne l'heure actuelle avec le fuseau horaire
        # configuré dans settings.py (Europe/Paris ici).
        alerte.acquittement_at = timezone.now()

        # On ne sauvegarde le commentaire que s'il n'est pas vide.
        # Pas la peine de stocker une chaîne vide en base.
        if commentaire:
            alerte.commentaire = commentaire

        # .save() envoie un UPDATE SQL uniquement sur cet objet.
        alerte.save()

        return redirect("alertes:liste_alertes")

    # Requête GET : on affiche la page de confirmation.
    return render(request, "alertes/acquitter.html", {"alerte": alerte})


def fermer_alerte(request, alerte_id):
    """
    Vue FBV — fermer une alerte (la passer en 'fermee' : le problème est résolu).

    GET  : affiche la page de confirmation fermer.html.
    POST : enregistre la clôture (statut + timestamp_cloture) et redirige.

    On peut fermer une alerte 'ouverte' OU 'acquittee'. Une alerte déjà 'fermee'
    est renvoyée directement vers la liste : il n'y a plus rien à faire, et ça
    évite d'écraser timestamp_cloture si quelqu'un recharge la page.
    """
    alerte = get_object_or_404(Alerte, pk=alerte_id)

    if alerte.statut == Alerte.StatutChoices.FERMEE:
        return redirect("alertes:liste_alertes")

    if request.method == "POST":
        alerte.statut = Alerte.StatutChoices.FERMEE
        # timestamp_cloture : l'heure de résolution. Permet de calculer la durée
        # de l'incident (clôture − déclenchement).
        alerte.timestamp_cloture = timezone.now()
        alerte.save()

        return redirect("alertes:liste_alertes")

    # Requête GET : on affiche la page de confirmation.
    return render(request, "alertes/fermer.html", {"alerte": alerte})
