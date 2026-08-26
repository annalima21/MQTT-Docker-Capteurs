from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Utilisateur custom de la plateforme.
    On étend AbstractUser de Django plutôt que de partir de zéro, ce qui nous donne
    gratuitement la gestion des mots de passe, permissions, groupes, etc.
    Le modèle est vide pour l'instant mais on pourra ajouter des champs métier
    (rôle, site attribué, numéro de badge...) sans migration complexe plus tard.
    """

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"

    def __str__(self):
        # get_full_name() retourne "Prénom Nom" si renseigné, sinon on affiche le username.
        return self.get_full_name() or self.username


class Site(models.Model):
    """
    Site géographique qui accueille des capteurs.
    On sépare le Site du Capteur pour ne pas répéter l'adresse et les coordonnées
    GPS sur chaque ligne capteur
    """

    nom = models.CharField(
        max_length=128,
        unique=True,
        verbose_name="Nom du site",
        # unique=True : deux sites ne peuvent pas avoir le même nom.
    )
    # FloatField → DOUBLE PRECISION en PostgreSQL (15 chiffres significatifs).
    # Pour les coordonnées GPS, c'est largement suffisant (précision < 1 mm à l'équateur).
    latitude = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Latitude WGS84",
    )
    longitude = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Longitude WGS84",
    )
    adresse = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Adresse postale",
    )
    # auto_now_add=True : Django remplit ce champ à la création et ne le touche plus jamais.
    created_at = models.DateTimeField(
        auto_now_add=True, #_add pour maj que sur l'ajout
        verbose_name="Créé le")

    class Meta:
        verbose_name = "Site"
        verbose_name_plural = "Sites"
        ordering = ["nom"] # en cas Site.objects.all() resultats tries par ordre alphabéthique

    def __str__(self):
        return self.nom


class TypeCapteur(models.Model):
    """
    Catégorie de capteur avec ses règles communes : unité SI et plage de validité.
    On l'extrait du Capteur parce que 50 capteurs de température partagent la même
    unité (°C) et la même plage (-40 à +150°C). Sans cette entité on répéterait
    ces données sur chaque ligne capteur, source d'incohérence possible (3FN).
    """

    class CodeChoices(models.TextChoices):
        # TextChoices (Django 3.0+) plutôt que des tuples bruts :
        # les valeurs sont accessibles par TypeCapteur.CodeChoices.TEMPERATURE,
        # c'est plus lisible et ça évite les fautes de frappe dans le code.
        TEMPERATURE = "temperature", "Température"
        PRESSION = "pression", "Pression"
        VIBRATION = "vibration", "Vibration"
        QUALITE_AIR = "qualite_air", "Qualité de l'air"

    code = models.CharField(
        max_length=32,
        choices=CodeChoices.choices,
        unique=True,
        verbose_name="Code technique",
        # unique=True : ce code est utilisé dans les topics MQTT pour router les messages
        # (ex : "capteurs/temperature/TEMP-001"). Il doit être unique.
    )
    libelle = models.CharField(
        max_length=128,
        verbose_name="Libellé affiché",
        help_text="Nom en français pour l'interface utilisateur",
    )
    unite_si = models.CharField(
        max_length=16,
        verbose_name="Unité SI",
        help_text="Ex : °C, Pa, m/s², ppm",
    )
    # null/blank=True : la plage n'est pas toujours documentée à la création du type.
    plage_min = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Plage min technique",
    )
    plage_max = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Plage max technique",
    )

    class Meta:
        verbose_name = "Type de capteur"
        verbose_name_plural = "Types de capteurs"
        ordering = ["code"]

    def __str__(self):
        return f"{self.libelle} ({self.unite_si})"


class Capteur(models.Model):
    """
    Capteur physique individuel installé sur un site.
    C'est l'entité pivot du modèle : toutes les mesures, alertes et dérives
    lui sont rattachées via une FK. On utilise la suppression logique (actif=False)
    plutôt que physique pour conserver l'historique des mesures même après
    le retrait d'un capteur du parc.
    """

    # on_delete=RESTRICT : on interdit de supprimer un Site qui a encore des capteurs,
    # sinon on perdrait la localisation géographique — les capteurs deviendraient orphelins.
    site = models.ForeignKey(
        "Site", # reference en chaine
        on_delete=models.RESTRICT,
        related_name="capteurs",
        verbose_name="Site d'installation",
    )
    # on_delete=RESTRICT : idem — on ne peut pas supprimer un TypeCapteur encore utilisé,
    # sinon on perdrait l'unité SI et la plage de validité des mesures.
    type_capteur = models.ForeignKey(
        "TypeCapteur",
        on_delete=models.RESTRICT,
        related_name="capteurs",
        verbose_name="Type de capteur",
        # Nommé type_capteur et non type pour éviter de masquer la fonction native
        # Python type() — convention défensive recommandée.
    )
    identifiant = models.CharField(
        max_length=64,
        unique=True,
        verbose_name="Identifiant MQTT",
        help_text="Identifiant unique utilisé dans les topics MQTT (ex : TEMP-001)",
        # unique=True : l'ingestion MQTT retrouve le capteur par cet identifiant.
        # Deux capteurs avec le même identifiant créeraient une ambiguïté fatale dans le routage.
    )
    nom = models.CharField(
        max_length=128,
        verbose_name="Nom lisible",
    )
    # Suppression logique : actif=False signifie "retiré du parc" mais l'historique
    # des mesures est conservé en base — on ne supprime jamais physiquement un capteur.
    actif = models.BooleanField(
        default=True,
        verbose_name="Capteur actif",
    )
    # JSONField (models.JSONField, natif Django 3.1+ avec PostgreSQL).
    # On stocke la config en JSON parce que les paramètres (fréquence d'émission,
    # mode sleep, intervalle de calibration...) varient d'un firmware à l'autre
    # et ne sont pas figés — les colonnes typées ne conviendraient pas ici.
    # blank=True : on autorise un dict vide {} dans les formulaires d'admin.
    # Sans cette option, Django considère {} comme "vide" et refuse la création
    # tant qu'on n'a pas saisi au moins une clé — comportement piège du JSONField.
    config_json = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Configuration JSON",
        help_text="Paramètres opérationnels du capteur (fréquence, modes sleep...)",
    )
    firmware_version = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        verbose_name="Version firmware",
        help_text="Version annoncée par le capteur dans ses messages MQTT",
    )
    date_installation = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date d'installation",
    )
    date_derniere_calibration = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Dernière calibration",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    # auto_now=True : Django met à jour ce champ automatiquement à chaque save(),
    # sans qu'on ait à l'écrire dans le code métier.
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")

    class Meta:
        verbose_name = "Capteur"
        verbose_name_plural = "Capteurs"
        ordering = ["identifiant"]
        indexes = [
            # Index (site, actif) : pour afficher rapidement les capteurs actifs d'un site
            # dans le dashboard — requête très fréquente.
            models.Index(fields=["site", "actif"], name="idx_capteur_site_actif"),
            # Index sur type_capteur : pour filtrer "tous les capteurs de température".
            models.Index(fields=["type_capteur"], name="idx_capteur_type"),
        ]

    def __str__(self):
        return f"{self.identifiant} — {self.nom}"


class Seuil(models.Model):
    """
    Valeur limite associée à un capteur précis.
    Quand une mesure franchit ce seuil, le moteur d'alertes déclenche une Alerte.
    On en fait une entité séparée (plutôt que 4 colonnes sur Capteur) pour pouvoir
    activer/désactiver chaque seuil indépendamment et les faire évoluer dans le temps
    sans modifier le schéma.
    """

    class TypeSeuilChoices(models.TextChoices):
        BAS_CRITIQUE = "bas_critique", "Bas critique"
        BAS_WARNING = "bas_warning", "Bas warning"
        HAUT_WARNING = "haut_warning", "Haut warning"
        HAUT_CRITIQUE = "haut_critique", "Haut critique"

    # on_delete=CASCADE : si un capteur est supprimé, ses seuils n'ont aucun sens sans lui.
    capteur = models.ForeignKey(
        "Capteur",
        on_delete=models.CASCADE,
        related_name="seuils",
        verbose_name="Capteur associé",
    )
    type_seuil = models.CharField(
        max_length=16,
        choices=TypeSeuilChoices.choices,
        verbose_name="Type de seuil",
    )
    # FloatField → DOUBLE PRECISION : on stocke des grandeurs physiques (°C, Pa...).
    # 15 chiffres significatifs, suffisant pour la métrologie industrielle à ce niveau.
    valeur = models.FloatField(
        verbose_name="Valeur du seuil",
        help_text="Exprimée dans l'unité SI du type de capteur",
    )
    actif = models.BooleanField(
        default=True,
        verbose_name="Seuil actif",
        help_text="Permet de désactiver temporairement un seuil sans le supprimer",
    )

    class Meta:
        verbose_name = "Seuil"
        verbose_name_plural = "Seuils"
        ordering = ["capteur", "type_seuil"]
        constraints = [
            # Un capteur ne peut pas avoir deux seuils du même type (ex : deux "haut_critique").
            # Cette contrainte est appliquée au niveau base de données, pas seulement en Python.
            models.UniqueConstraint(
                fields=["capteur", "type_seuil"],
                name="seuil_unique_par_capteur_et_type",
            ),
        ]

    def __str__(self):
        return (
            f"{self.capteur.identifiant} / "
            f"{self.get_type_seuil_display()} = {self.valeur}"
        )
