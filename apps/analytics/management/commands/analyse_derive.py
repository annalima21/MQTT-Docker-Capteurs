"""
Commande d'analyse de dérive — Fonctionnalité F4.1 du CdC.

Le CdC précise : « déclenchement à la demande dans la version initiale,
automatique dans les évolutions futures ». Cette commande couvre les deux :
    - une seule passe (à la demande) :   python manage.py analyse_derive
    - en boucle (le "worker" futur)  :   python manage.py analyse_derive --continu

Elle ne contient AUCUN calcul : elle se contente de parcourir les capteurs
actifs et d'appeler la logique de apps/analytics/derive.py.
"""

import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.core.models import Capteur
from apps.analytics import derive


class Command(BaseCommand):
    help = "Analyse la dérive statistique des capteurs actifs (F4.1)."

    def add_arguments(self, parser):
        # action="store_true" => l'option est un simple drapeau (présent ou non).
        parser.add_argument(
            "--continu",
            action="store_true",
            help="Boucle en continu au lieu d'une seule passe.",
        )
        parser.add_argument(
            "--intervalle",
            type=int,
            default=300,
            help="Secondes entre deux passes en mode --continu (défaut 300 = 5 min).",
        )
        parser.add_argument(
            "--fenetre",
            type=int,
            default=derive.FENETRE_HEURES_DEFAUT,
            help="Taille de la fenêtre d'analyse en heures (défaut 24).",
        )

    def handle(self, *args, **options):
        continu = options["continu"]
        intervalle = options["intervalle"]
        fenetre = options["fenetre"]

        if not continu:
            # Mode à la demande : une seule passe et on rend la main.
            self._une_passe(fenetre)
            return

        # Mode continu : on relance une passe toutes les `intervalle` secondes.
        self.stdout.write(self.style.SUCCESS(
            f"Analyse de dérive en continu (toutes les {intervalle}s, "
            f"fenêtre {fenetre}h). Ctrl+C pour arrêter."
        ))
        try:
            while True:
                self._une_passe(fenetre)
                time.sleep(intervalle)
        except KeyboardInterrupt:
            self.stdout.write("\nArrêt demandé, fin de l'analyse.")

    def _une_passe(self, fenetre):
        """Analyse une fois tous les capteurs actifs et affiche un compte-rendu."""

        # Le worker peut tourner longtemps : on ferme les connexions BDD trop
        # vieilles avant chaque passe (même précaution que le worker MQTT).
        close_old_connections()

        capteurs = Capteur.objects.filter(actif=True).order_by("identifiant")

        nb_analyses = 0
        nb_alertes = 0

        for capteur in capteurs:
            resultat = derive.analyser_capteur(capteur, fenetre_heures=fenetre)

            if resultat["statut"] == "donnees_insuffisantes":
                self.stdout.write(
                    f"  {capteur.identifiant} : pas assez de données, ignoré."
                )
                continue

            nb_analyses += 1
            score = resultat["score"]
            niveau = resultat["niveau"]
            pente = resultat["pente"]

            ligne = (
                f"  {capteur.identifiant} : score={score:.2f} ({niveau}), "
                f"pente={pente:+.2f}/h"
            )

            if niveau == "critique" and resultat["alerte_creee"]:
                nb_alertes += 1
                self.stdout.write(self.style.ERROR(ligne + " → ALERTE de dérive créée"))
            elif niveau == "critique":
                # Critique mais une alerte est déjà ouverte (anti-doublon).
                self.stdout.write(self.style.WARNING(
                    ligne + " → critique (alerte déjà ouverte, pas de doublon)"
                ))
            elif niveau == "warning":
                self.stdout.write(self.style.WARNING(ligne))
            else:
                self.stdout.write(ligne)

        self.stdout.write(self.style.SUCCESS(
            f"Passe terminée : {nb_analyses} capteur(s) analysé(s), "
            f"{nb_alertes} alerte(s) de dérive créée(s)."
        ))
