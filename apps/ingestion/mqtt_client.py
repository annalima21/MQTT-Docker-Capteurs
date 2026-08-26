# Gestion MQTT pour réception des mesures capteurs
# Ce service reçoit les messages MQTT, valide les données et enregistre
# les mesures dans PostgreSQL via l'ORM Django. Il détecte aussi les
# dépassements de seuils et crée automatiquement des Alertes.

import json
import os

import paho.mqtt.client as mqtt
from django.db import close_old_connections
from django.utils.dateparse import parse_datetime

# Modèles Django
from apps.alertes.models import Alerte
from apps.core.models import Capteur
from apps.ingestion.models import Mesure


class MqttIngestionClient:

    def __init__(self):

        # Lecture config depuis .env
        self.host = os.getenv("MQTT_BROKER_HOST", "mqtt")
        self.port = int(os.getenv("MQTT_BROKER_PORT", "1883"))

        # Topic MQTT surveillé — "+" est un wildcard MQTT acceptant n'importe
        # quel segment (site_id ou capteur_id).
        self.topic = os.getenv("MQTT_TOPIC", "sensors/+/+/telemetry")

        # Création du client MQTT
        self.client = mqtt.Client()

        # Association des callbacks MQTT
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    # Callback connexion broker
    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        print("Connecté au broker MQTT")

        # Abonnement au topic télémétrie
        client.subscribe(self.topic)
        print(f"Abonné au topic : {self.topic}")

    # Callback réception message MQTT
    def on_message(self, client, userdata, message):
        # Ferme les anciennes connexions BDD avant de traiter le message.
        # Le worker tourne en continu : sans ça, on garderait une vieille
        # connexion qui peut être coupée par PostgreSQL après un timeout.
        close_old_connections()

        # Conversion bytes → texte
        payload = message.payload.decode("utf-8")

        print("Message reçu")
        print("Topic :", message.topic)
        print("Payload :", payload)

        # Validation JSON
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            print("Erreur : message JSON invalide")
            return

        # Extraction des données MQTT
        capteur_id = data.get("capteur_id")
        timestamp = parse_datetime(data.get("timestamp"))
        valeur = data.get("valeur")
        qualite = data.get("qualite", 1.0)
        meta = data.get("meta", {})

        # Vérifications minimales avant insertion
        if not capteur_id:
            print("Erreur : capteur_id manquant")
            return

        if timestamp is None:
            print("Erreur : timestamp invalide")
            return

        if valeur is None:
            print("Erreur : valeur manquante")
            return

        # Recherche du capteur via l'ORM
        try:
            capteur = Capteur.objects.get(
                identifiant=capteur_id,
                actif=True,
            )
        except Capteur.DoesNotExist:
            print(f"Erreur : capteur inconnu : {capteur_id}")
            return

        # Sauvegarde de la mesure en base
        mesure = Mesure.objects.create(
            capteur=capteur,
            timestamp=timestamp,
            valeur=valeur,
            qualite=qualite,
            meta_json=meta,
        )

        print(
            f"Mesure enregistrée : id={mesure.id}, "
            f"capteur={capteur.identifiant}, valeur={mesure.valeur}"
        )

        # ============================================================
        # Détection automatique des dépassements de seuils (F3.1 du CdC)
        # ============================================================
        # On parcourt les seuils ACTIFS du capteur et on regarde si la
        # valeur vient de les franchir. Si oui, on crée une Alerte —
        # sauf si une alerte pour ce même couple (capteur, seuil) est
        # déjà ouverte (anti-spam : éviter N alertes pour 1 défaut).
        seuils_actifs = capteur.seuils.filter(actif=True)

        for seuil in seuils_actifs:

            # Détermine si la valeur viole le seuil et de quel niveau.
            depassement = False
            niveau = None

            if seuil.type_seuil == "haut_critique" and valeur > seuil.valeur:
                depassement = True
                niveau = Alerte.NiveauChoices.CRITIQUE
            elif seuil.type_seuil == "haut_warning" and valeur > seuil.valeur:
                depassement = True
                niveau = Alerte.NiveauChoices.WARNING
            elif seuil.type_seuil == "bas_critique" and valeur < seuil.valeur:
                depassement = True
                niveau = Alerte.NiveauChoices.CRITIQUE
            elif seuil.type_seuil == "bas_warning" and valeur < seuil.valeur:
                depassement = True
                niveau = Alerte.NiveauChoices.WARNING

            if not depassement:
                continue  # ce seuil n'est pas violé, on passe au suivant

            # Anti-spam : on ne recrée pas une alerte si une est déjà ouverte
            # pour ce couple (capteur, seuil). L'alerte existante reste
            # valable jusqu'à acquittement par le technicien.
            alerte_existe_deja = Alerte.objects.filter(
                capteur=capteur,
                seuil=seuil,
                statut=Alerte.StatutChoices.OUVERTE,
            ).exists()

            if alerte_existe_deja:
                print(
                    f"Alerte déjà ouverte pour {capteur.identifiant} / "
                    f"{seuil.get_type_seuil_display()} — pas de doublon créé"
                )
                continue

            # Création de la nouvelle alerte
            alerte = Alerte.objects.create(
                capteur=capteur,
                seuil=seuil,
                timestamp_declenchement=timestamp,
                niveau=niveau,
                type_alerte=Alerte.TypeAlerteChoices.SEUIL,
                valeur_declenchante=valeur,
                statut=Alerte.StatutChoices.OUVERTE,
            )

            sens = ">" if "haut" in seuil.type_seuil else "<"
            print(
                f"ALERTE créée (id={alerte.id}) : {alerte.get_niveau_display()} — "
                f"{capteur.identifiant} a franchi {seuil.get_type_seuil_display()} "
                f"({valeur} {sens} {seuil.valeur})"
            )

        # ============================================================
        # Purge des anciennes mesures (limite à 1000 par capteur)
        # ============================================================
        # Évite la croissance infinie de la table Mesure pendant le dev.
        # On garde les 1000 plus récentes du capteur, on supprime le reste.
        limite_par_capteur = 1000

        ids_a_garder = Mesure.objects.filter(
            capteur=capteur,
        ).order_by("-timestamp").values_list("id", flat=True)[:limite_par_capteur]

        Mesure.objects.filter(capteur=capteur).exclude(
            id__in=list(ids_a_garder)
        ).delete()

    # Lancement du service MQTT
    def start(self):
        print("Démarrage du client MQTT...")
        print(f"Broker : {self.host}:{self.port}")

        # Connexion au broker Mosquitto (timeout keepalive = 60s)
        self.client.connect(self.host, self.port, 60)

        # Boucle d'écoute permanente — bloque le thread, c'est normal
        # pour un worker qui ne fait que ça.
        self.client.loop_forever()
