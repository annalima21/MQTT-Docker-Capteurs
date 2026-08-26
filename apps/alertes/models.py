from django.conf import settings
from django.db import models

from apps.core.models import Capteur, Seuil


class Alerte(models.Model):
    """
    Événement d'alerte sur un capteur : dépassement de seuil, dérive statistique,
    perte de communication ou batterie faible.
    Une alerte a un cycle de vie : ouverte → acquittée → fermée.
    Elle peut référencer le seuil qui l'a déclenchée (nullable pour les alertes de dérive).
    """

    class NiveauChoices(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        CRITIQUE = "critique", "Critique"

    class TypeAlerteChoices(models.TextChoices):
        SEUIL = "seuil", "Dépassement de seuil"
        DERIVE = "derive", "Dérive statistique"
        COMMUNICATION = "communication", "Perte de communication"
        BATTERIE = "batterie", "Batterie faible"

    class StatutChoices(models.TextChoices):
        OUVERTE = "ouverte", "Ouverte"
        ACQUITTEE = "acquittee", "Acquittée"
        FERMEE = "fermee", "Fermée"

    # on_delete=CASCADE : si un capteur est supprimé, ses alertes aussi.
    # (En pratique la suppression logique actif=False évite de perdre l'historique.)
    capteur = models.ForeignKey(
        Capteur,
        on_delete=models.CASCADE,
        related_name="alertes",
        verbose_name="Capteur concerné",
    )
    # null=True : une alerte de type "derive" ou "communication" n'a pas de seuil associé.
    # on_delete=SET_NULL : si un seuil est supprimé, on garde l'alerte dans l'historique
    # mais on perd le lien vers ce seuil — on préfère conserver l'alerte plutôt que
    # de la supprimer en cascade.
    seuil = models.ForeignKey(
        Seuil,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alertes",
        verbose_name="Seuil franchi",
    )
    timestamp_declenchement = models.DateTimeField(
        verbose_name="Déclenché le",
    )
    # null=True : non renseigné tant que l'alerte est encore ouverte ou acquittée.
    timestamp_cloture = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Clôturé le",
    )
    niveau = models.CharField(
        max_length=16,
        choices=NiveauChoices.choices,
        verbose_name="Niveau de gravité",
    )
    type_alerte = models.CharField(
        max_length=32,
        choices=TypeAlerteChoices.choices,
        verbose_name="Type d'alerte",
    )
    # null=True : les alertes de dérive ou de communication n'ont pas de valeur précise.
    valeur_declenchante = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Valeur déclenchante",
    )
    statut = models.CharField(
        max_length=16,
        choices=StatutChoices.choices,
        default=StatutChoices.OUVERTE,
        verbose_name="Statut",
    )
    # On référence AUTH_USER_MODEL (et non User directement) pour rester découplé
    # du chemin exact vers le modèle User — c'est la bonne pratique Django.
    # on_delete=SET_NULL : si l'utilisateur est supprimé du système, l'alerte reste
    # avec son historique ; on perd juste le nom de celui qui a acquitté.
    acquittement_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alertes_acquittees",
        verbose_name="Acquitté par",
    )
    acquittement_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Acquitté le",
    )
    # TextField sans taille max : le technicien peut écrire un commentaire long
    # pour expliquer la cause de l'alerte et les actions correctives menées.
    commentaire = models.TextField(
        null=True,
        blank=True,
        verbose_name="Commentaire technicien",
    )

    class Meta:
        verbose_name = "Alerte"
        verbose_name_plural = "Alertes"
        ordering = ["-timestamp_declenchement"]
        indexes = [
            # Index (capteur, statut) : pour la vue "alertes ouvertes du capteur X"
            # que le dashboard affichera en temps réel.
            models.Index(
                fields=["capteur", "statut"],
                name="idx_alerte_capteur_statut",
            ),
            # Index sur timestamp décroissant : pour le tri chronologique dans l'historique.
            models.Index(
                fields=["-timestamp_declenchement"],
                name="idx_alerte_ts_desc",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_niveau_display()} / "
            f"{self.capteur.identifiant} ({self.statut})"
        )
