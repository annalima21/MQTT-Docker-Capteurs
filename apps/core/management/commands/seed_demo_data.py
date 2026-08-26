from django.core.management.base import BaseCommand

from apps.core.models import Site, TypeCapteur, Capteur, Seuil


class Command(BaseCommand):
    help = "Crée un jeu de données de démonstration : 3 sites, 4 types, 10 capteurs, 40 seuils."

    def handle(self, *args, **kwargs):

        # ============================================================
        # 1. SITES
        # ============================================================
        # get_or_create = lookup par 'nom', si existe → retourne, sinon
        # crée avec les valeurs de 'defaults'. Rend la commande idempotente
        # (on peut la relancer sans créer de doublons).
        sites_data = [
            {
                "nom": "Bâtiment GEII",
                "latitude": 45.7640,
                "longitude": 4.8357,
                "adresse": "IUT Lyon 1 — 17 rue de France, 69100 Villeurbanne",
            },
            {
                "nom": "Atelier Électrotechnique",
                "latitude": 45.4397,
                "longitude": 4.3872,
                "adresse": "Saint-Étienne",
            },
            {
                "nom": "Salle Serveurs Lyon Tech",
                "latitude": 45.7800,
                "longitude": 4.8800,
                "adresse": "Villeurbanne",
            },
        ]

        sites = {}
        for data in sites_data:
            site, created = Site.objects.get_or_create(
                nom=data["nom"],
                defaults={
                    "latitude": data["latitude"],
                    "longitude": data["longitude"],
                    "adresse": data["adresse"],
                },
            )
            sites[data["nom"]] = site
            statut = "créé" if created else "déjà présent"
            self.stdout.write(f"  Site : {site.nom} ({statut})")

        # ============================================================
        # 2. TYPES DE CAPTEURS
        # ============================================================
        types_data = [
            {
                "code": "temperature",
                "libelle": "Capteur de température",
                "unite_si": "°C",
                "plage_min": -40,
                "plage_max": 150,
            },
            {
                "code": "pression",
                "libelle": "Capteur de pression",
                "unite_si": "Pa",
                "plage_min": 0,
                "plage_max": 10_000_000,
            },
            {
                "code": "vibration",
                "libelle": "Capteur de vibration",
                "unite_si": "m/s²",
                "plage_min": 0,
                "plage_max": 100,
            },
            {
                "code": "qualite_air",
                "libelle": "Capteur qualité de l'air",
                "unite_si": "ppm",
                "plage_min": 0,
                "plage_max": 10_000,
            },
        ]

        types = {}
        for data in types_data:
            type_capteur, created = TypeCapteur.objects.get_or_create(
                code=data["code"],
                defaults={
                    "libelle": data["libelle"],
                    "unite_si": data["unite_si"],
                    "plage_min": data["plage_min"],
                    "plage_max": data["plage_max"],
                },
            )
            types[data["code"]] = type_capteur
            statut = "créé" if created else "déjà présent"
            self.stdout.write(f"  Type : {type_capteur.code} ({statut})")

        # ============================================================
        # 3. CAPTEURS
        # ============================================================
        # On définit une liste de tuples (identifiant, nom, type, site, actif, seuils).
        # Le dict de seuils contient les 4 niveaux par capteur, adaptés au contexte.
        capteurs_data = [
            (
                "TEMP-001", "Sonde salle 101", "temperature", "Bâtiment GEII", True,
                {"bas_critique": -5, "bas_warning": 0, "haut_warning": 28, "haut_critique": 35},
            ),
            (
                "TEMP-002", "Sonde salle 102", "temperature", "Bâtiment GEII", True,
                {"bas_critique": -5, "bas_warning": 0, "haut_warning": 28, "haut_critique": 35},
            ),
            (
                "TEMP-003", "Sonde climatisation serveurs", "temperature", "Salle Serveurs Lyon Tech", True,
                {"bas_critique": 10, "bas_warning": 15, "haut_warning": 25, "haut_critique": 30},
            ),
            (
                "TEMP-OLD", "Ancien capteur retiré", "temperature", "Bâtiment GEII", False,
                {"bas_critique": -10, "bas_warning": 0, "haut_warning": 30, "haut_critique": 40},
            ),
            (
                "PRES-001", "Pression circuit hydraulique 1", "pression", "Atelier Électrotechnique", True,
                {"bas_critique": 100_000, "bas_warning": 200_000, "haut_warning": 800_000, "haut_critique": 1_000_000},
            ),
            (
                "PRES-002", "Pression circuit hydraulique 2", "pression", "Atelier Électrotechnique", True,
                {"bas_critique": 100_000, "bas_warning": 200_000, "haut_warning": 800_000, "haut_critique": 1_000_000},
            ),
            (
                "VIB-001", "Vibration moteur principal", "vibration", "Atelier Électrotechnique", True,
                {"bas_critique": 0, "bas_warning": 0.5, "haut_warning": 15, "haut_critique": 25},
            ),
            (
                "VIB-002", "Vibration moteur secondaire", "vibration", "Bâtiment GEII", True,
                {"bas_critique": 0, "bas_warning": 0.5, "haut_warning": 12, "haut_critique": 20},
            ),
            (
                "QAIR-001", "Qualité air salle TP", "qualite_air", "Bâtiment GEII", True,
                {"bas_critique": 0, "bas_warning": 0, "haut_warning": 800, "haut_critique": 1500},
            ),
            (
                "QAIR-002", "Qualité air salle serveurs", "qualite_air", "Salle Serveurs Lyon Tech", True,
                {"bas_critique": 0, "bas_warning": 0, "haut_warning": 600, "haut_critique": 1000},
            ),
        ]

        # On compte combien de capteurs/seuils ont été créés pour le résumé final.
        nb_capteurs_crees = 0
        nb_seuils_crees = 0

        for identifiant, nom, code_type, nom_site, actif, seuils_config in capteurs_data:

            capteur, created = Capteur.objects.get_or_create(
                identifiant=identifiant,
                defaults={
                    "nom": nom,
                    "site": sites[nom_site],
                    "type_capteur": types[code_type],
                    "actif": actif,
                    # Config minimale différente selon le type (juste pour l'exemple).
                    "config_json": {
                        "frequence_emission_seconds": 30,
                        "mode_sleep": "normal",
                    },
                    "firmware_version": "1.0.0",
                },
            )
            if created:
                nb_capteurs_crees += 1

            statut = "créé" if created else "déjà présent"
            self.stdout.write(f"  Capteur : {capteur.identifiant} ({statut})")

            # ----- Seuils du capteur -----
            # On crée les 4 seuils standards (bas_critique, bas_warning, haut_warning, haut_critique).
            for type_seuil, valeur in seuils_config.items():
                seuil, seuil_created = Seuil.objects.get_or_create(
                    capteur=capteur,
                    type_seuil=type_seuil,
                    defaults={
                        "valeur": valeur,
                        "actif": True,
                    },
                )
                if seuil_created:
                    nb_seuils_crees += 1

        # ============================================================
        # RÉSUMÉ
        # ============================================================
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Seed terminé."))
        self.stdout.write(f"  Sites totaux       : {Site.objects.count()}")
        self.stdout.write(f"  Types capteurs     : {TypeCapteur.objects.count()}")
        self.stdout.write(f"  Capteurs totaux    : {Capteur.objects.count()}")
        self.stdout.write(f"  Seuils totaux      : {Seuil.objects.count()}")
        self.stdout.write(f"  Capteurs créés ce run : {nb_capteurs_crees}")
        self.stdout.write(f"  Seuils créés ce run   : {nb_seuils_crees}")
