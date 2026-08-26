from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models

from apps.alertes.models import Alerte
from apps.core.models import Capteur


class DeriveDetectee(models.Model):
    """
    Résultat d'une analyse de dérive statistique sur les mesures d'un capteur.
    Un algorithme analyse une fenêtre glissante de mesures et calcule un "score"
    qui indique à quel point le capteur s'écarte de son comportement habituel.
    Si le score dépasse un seuil configuré, une Alerte de type "derive" est créée
    et référencée ici.
    """

    # on_delete=CASCADE : si un capteur est supprimé, ses détections de dérive aussi.
    capteur = models.ForeignKey(
        Capteur,
        on_delete=models.CASCADE,
        related_name="derives",
        verbose_name="Capteur analysé",
    )
    timestamp = models.DateTimeField(
        verbose_name="Moment de l'analyse",
    )
    # FloatField : le score est un écart normé (sans unité physique).
    # Pas besoin de DECIMAL ici, c'est un résultat de calcul statistique.
    score = models.FloatField(
        verbose_name="Score de dérive",
        help_text="Écart normé à la moyenne glissante (plus élevé = comportement plus anormal)",
    )
    moyenne_ref = models.FloatField(
        verbose_name="Moyenne de référence",
        help_text="Moyenne calculée sur la fenêtre d'analyse (même unité que les mesures)",
    )
    ecart_type_ref = models.FloatField(
        verbose_name="Écart-type de référence",
        help_text="Écart-type calculé sur la fenêtre d'analyse",
    )
    # IntegerField : un nombre d'heures est toujours entier, FloatField serait surdimensionné.
    fenetre_heures = models.IntegerField(
        default=24,
        verbose_name="Taille de fenêtre (heures)",
        help_text="Nombre d'heures sur lesquelles la dérive a été calculée",
    )
    # null=True : une détection ne lève pas toujours une alerte (score sous le seuil).
    # on_delete=SET_NULL : si une alerte est supprimée on conserve la détection —
    # l'historique des analyses statistiques est indépendant des alertes.
    alerte = models.ForeignKey(
        Alerte,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derives",
        verbose_name="Alerte levée",
    )

    class Meta:
        verbose_name = "Dérive détectée"
        verbose_name_plural = "Dérives détectées"
        ordering = ["-timestamp"]
        indexes = [
            # Index (capteur, timestamp DESC) : pour les requêtes "historique des dérives
            # d'un capteur sur la dernière semaine", utilisé par le module analytics.
            models.Index(
                fields=["capteur", "-timestamp"],
                name="idx_derive_capteur_ts",
            ),
        ]

    def __str__(self):
        return (
            f"Dérive {self.capteur.identifiant} @ "
            f"{self.timestamp:%Y-%m-%d %H:%M} (score={self.score:.2f})"
        )


class ModeleML(models.Model):
    """
    Modèle TensorFlow Lite déployé pour l'inférence edge sur les capteurs.
    Le fichier .tflite est stocké sur un volume dédié (FileField → MEDIA_ROOT/modeles_ml/).
    Contrainte métier : taille < 100 KB pour tenir dans la RAM des microcontrôleurs cibles.
    Un modèle n'est pas mis en production automatiquement à l'upload (actif=False par défaut).
    """

    nom = models.CharField(
        max_length=128,
        verbose_name="Nom du modèle",
        help_text="Nom logique, ex : anomalie_temperature",
    )
    version = models.CharField(
        max_length=32,
        verbose_name="Version",
        help_text="Convention semver, ex : 1.0.3",
    )
    # FileField avec upload_to : les fichiers sont stockés dans MEDIA_ROOT/modeles_ml/.
    # On choisit FileField et pas BinaryField parce que les fichiers .tflite peuvent être
    # téléchargés et redistribués aux capteurs, et FileField gère le stockage sur disque.
    fichier_tflite = models.FileField(
        upload_to="modeles_ml/",
        verbose_name="Fichier .tflite",
    )
    # taille_octets stockée plutôt que calculée à la volée : ça permet une contrainte
    # directe via MaxValueValidator et évite de lire le fichier à chaque validation.
    taille_octets = models.IntegerField(
        validators=[MaxValueValidator(102400)],
        verbose_name="Taille (octets)",
        help_text="Doit rester < 100 KB (102 400 octets) pour tenir sur les microcontrôleurs",
    )
    # blank=True : on autorise un dict vide {} (cf. note dans core/models.py
    # sur le comportement piège du JSONField vis-à-vis de la validation admin).
    metriques_json = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Métriques d'évaluation",
        help_text='Ex : {"accuracy": 0.97, "precision": 0.95, "recall": 0.93, "f1": 0.94}',
    )
    # actif=False par défaut : un modèle uploadé n'est PAS mis en production automatiquement.
    # On demande une action explicite pour l'activer — sécurité intentionnelle.
    actif = models.BooleanField(
        default=False,
        verbose_name="Modèle actif",
        help_text="Seul le modèle actif est utilisé pour l'inférence en temps réel",
    )
    # on_delete=SET_NULL : si le data scientist qui a créé le modèle est supprimé du système,
    # on conserve le modèle ML (qui a une valeur indépendante de son auteur).
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modeles_ml",
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")

    class Meta:
        verbose_name = "Modèle ML"
        verbose_name_plural = "Modèles ML"
        ordering = ["-created_at"]
        constraints = [
            # Contrainte unique (nom, version) : on ne peut pas avoir deux fois la même
            # version d'un modèle. C'est notre système de versionnement en base de données.
            models.UniqueConstraint(
                fields=["nom", "version"],
                name="modeleml_unique_par_nom_version",
            ),
        ]

    def __str__(self):
        statut = "actif" if self.actif else "archivé"
        return f"{self.nom} v{self.version} ({statut})"
