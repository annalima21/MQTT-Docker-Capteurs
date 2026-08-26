from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import Capteur


class Mesure(models.Model):
    """
    Valeur relevée par un capteur à un instant donné.
    C'est la table la plus volumineuse du projet : avec 50 capteurs émettant
    toutes les 10 secondes, on atteint ~13 millions de lignes en 30 jours (~1,5 Go).
    L'index composite sur (capteur, timestamp DESC) est critique pour les requêtes
    "historique d'un capteur sur les dernières heures" que l'ingestion MQTT et
    la détection d'anomalies exécuteront en boucle.
    """

    # on_delete=CASCADE : si un capteur est supprimé, ses mesures sont supprimées aussi.
    # En pratique on ne supprime jamais un capteur (suppression logique via actif=False),
    # donc cette clause ne devrait quasiment jamais se déclencher.
    capteur = models.ForeignKey(
        Capteur,
        on_delete=models.CASCADE,
        related_name="mesures",
        verbose_name="Capteur source",
    )
    # DateTimeField avec USE_TZ=True dans les settings : stocké en UTC en base,
    # converti en Europe/Paris à l'affichage. Ce n'est PAS auto_now — c'est
    # l'horodatage envoyé PAR le capteur, pas l'heure de réception serveur.
    timestamp = models.DateTimeField(
        verbose_name="Horodatage de la mesure",
    )
    # FloatField → DOUBLE PRECISION (15 chiffres significatifs).
    # Suffisant pour toutes les grandeurs physiques visées (température, pression,
    # vibration, qualité d'air) sans les erreurs d'arrondi du simple précision.
    valeur = models.FloatField(
        verbose_name="Valeur mesurée",
    )
    # qualite ∈ [0.0, 1.0] : indicateur de fiabilité fourni par le firmware du capteur.
    # 1.0 = mesure parfaite, 0.0 = mesure inutilisable (capteur en erreur ou saturé).
    qualite = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        verbose_name="Qualité de mesure",
        help_text="Score de fiabilité fourni par le capteur [0.0 – 1.0]",
    )
    # anomalie_score est facultatif : renseigné uniquement si un modèle TFLite
    # est actif et a analysé cette mesure au moment de l'ingestion.
    anomalie_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        verbose_name="Score d'anomalie ML",
        help_text="Sortie du modèle TFLite [0.0 – 1.0], null si pas de modèle actif",
    )
    # meta_json : métadonnées variables envoyées avec chaque mesure (niveau batterie,
    # signal RSSI, version firmware...). JSON parce que ces champs varient selon
    # le firmware et ne sont pas tous présents à chaque message MQTT.
    # blank=True : on autorise un dict vide {} (cf. note dans core/models.py
    # sur le comportement piège du JSONField vis-à-vis de la validation admin).
    meta_json = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Métadonnées JSON",
        help_text='Ex : {"batterie": 87, "rssi": -65, "firmware": "1.2.0"}',
    )

    class Meta:
        verbose_name = "Mesure"
        verbose_name_plural = "Mesures"
        ordering = ["-timestamp"]
        indexes = [
            # Index composite (capteur, timestamp DESC) : c'est l'index le plus important
            # du projet. Il couvre la requête critique "dernières N mesures du capteur X"
            # que l'ingestion MQTT et la détection de dérives exécuteront en boucle.
            # Le signe "-" devant timestamp demande un index décroissant à PostgreSQL.
            models.Index(
                fields=["capteur", "-timestamp"],
                name="idx_mesure_capteur_ts",
            ),
        ]

    def __str__(self):
        return (
            f"{self.capteur.identifiant} @ "
            f"{self.timestamp:%Y-%m-%d %H:%M:%S} = {self.valeur}"
        )
