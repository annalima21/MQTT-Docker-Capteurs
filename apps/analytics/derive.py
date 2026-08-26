"""
Logique de détection statistique de dérive — Fonctionnalité F4.1 du CdC.

Rappel du cahier des charges :
    « Analyse périodique des mesures d'un capteur sur une fenêtre glissante
      (24 heures par défaut) pour détecter une dérive PROGRESSIVE de ses
      valeurs par rapport à la normale. »

Définition d'une dérive (glossaire du CdC) :
    Évolution LENTE et progressive d'un capteur qui s'écarte de sa valeur
    normale, SANS dépassement ponctuel d'un seuil. C'est différent d'un pic :
    une seule valeur aberrante n'est PAS une dérive, c'est une TENDANCE.

Principe de l'algorithme : LA RÉGRESSION LINÉAIRE
    Une dérive est une tendance : la valeur monte (ou descend) régulièrement
    avec le temps. On trace donc la "droite des moindres carrés" qui passe au
    mieux par le nuage de points (temps, valeur) de la fenêtre.
"""

from datetime import timedelta
from statistics import mean, pstdev

from django.utils import timezone

from apps.alertes.models import Alerte
from apps.ingestion.models import Mesure
from .models import DeriveDetectee


# ============================================================
# Paramètres de l'algorithme (réglables au même endroit)
# ============================================================

# Taille de la fenêtre d'analyse, en heures (CdC : 24 h par défaut).
FENETRE_HEURES_DEFAUT = 2

# Nombre minimum de mesures dans la fenêtre pour que la régression ait un sens
# (CdC : "nécessite un volume suffisant"). Une droite sur 5 points ne veut rien dire.
MIN_POINTS = 10

# Seuils sur le score (règle empirique des 2 sigma / 3 sigma) :
#   - une tendance de moins de 2 σ de bruit est dans le bruit normal,
#   - au-delà de 3,5 σ, c'est clairement anormal.
SCORE_WARNING = 2.0
SCORE_CRITIQUE = 3.5

# Garde-fous numériques :
#   - si le bruit (résidus) est quasi nul, le score n'a pas de sens (division /0),
#   - si la fenêtre couvre une durée quasi nulle, la pente non plus.
EPSILON = 1e-9

# Anti-doublon : on ne recrée pas une alerte de dérive si une est déjà ouverte
# pour ce capteur depuis moins de 1 heure.
ANTI_SPAM_HEURES = 1


# ============================================================
# 1) Le calcul pur (aucun accès base de données)
# ============================================================

def calculer_score_regression(points):
    """
    Cœur mathématique. Ne touche PAS à la base : on lui passe une liste de
    points (temps_en_heures, valeur), elle renvoie les indicateurs de tendance.

    Méthode des moindres carrés (formule au programme) :
        pente b = Σ (t - t̄)(y - ȳ) / Σ (t - t̄)²
        ordonnée a = ȳ - b * t̄
    puis on regarde la dispersion des points autour de la droite (les résidus).

    Retour :
        - None si on ne peut pas calculer (trop peu de points, durée nulle,
          ou bruit nul → division impossible).
        - sinon un dictionnaire :
            {
                "pente":          pente de la droite (unité / heure),
                "moyenne":        valeur moyenne sur la fenêtre,
                "sigma":          écart-type des résidus (= le bruit du capteur),
                "drift_total":    |pente| * durée  (dérive expliquée par la droite),
                "valeur_estimee": valeur prédite par la droite à la fin de la fenêtre,
                "score":          drift_total / sigma  (le score normé),
            }
    """

    n = len(points)
    if n < MIN_POINTS:
        return None

    temps = [t for t, _ in points]
    valeurs = [y for _, y in points]

    t_moyen = mean(temps)
    y_moyen = mean(valeurs)

    # Numérateur et dénominateur de la pente (covariance / variance du temps).
    numerateur = sum((t - t_moyen) * (y - y_moyen) for t, y in points)
    denominateur = sum((t - t_moyen) ** 2 for t in temps)

    # denominateur ≈ 0 : toutes les mesures ont quasiment le même horodatage,
    # impossible de tracer une tendance dans le temps.
    if denominateur < EPSILON:
        return None

    pente = numerateur / denominateur
    ordonnee = y_moyen - pente * t_moyen

    # Résidus = écart de chaque point réel à la droite. Leur écart-type mesure
    # le bruit "normal" du capteur, une fois la tendance retirée.
    residus = [y - (ordonnee + pente * t) for t, y in points]
    sigma = pstdev(residus)

    # sigma ≈ 0 : signal parfaitement aligné sans aucun bruit (irréaliste en
    # pratique), on évite la division par zéro.
    if sigma < EPSILON:
        return None

    # Durée réellement couverte par la fenêtre (en heures).
    duree = max(temps) - min(temps)

    # Dérive totale "expliquée" par la droite sur la fenêtre, en valeur absolue
    # (une dérive vers le haut OU vers le bas compte pareil).
    drift_total = abs(pente) * duree

    # Valeur estimée par la droite à l'instant le plus récent : c'est le niveau
    # "actuel" lissé du capteur, utile à afficher dans l'alerte.
    valeur_estimee = ordonnee + pente * max(temps)

    score = drift_total / sigma

    return {
        "pente": pente,
        "moyenne": y_moyen,
        "sigma": sigma,
        "drift_total": drift_total,
        "valeur_estimee": valeur_estimee,
        "score": score,
    }


def niveau_pour_score(score):
    """
    Traduit un score numérique en niveau lisible.

    Retour : "critique", "warning" ou "normal".
    """
    if score >= SCORE_CRITIQUE:
        return "critique"
    if score >= SCORE_WARNING:
        return "warning"
    return "normal"


# ============================================================
# 2) L'orchestration (va chercher les mesures + enregistre)
# ============================================================

def analyser_capteur(capteur, fenetre_heures=FENETRE_HEURES_DEFAUT):
    """
    Analyse un capteur et, si possible, enregistre une DeriveDetectee.
    Crée une Alerte de type "dérive" si le score atteint le niveau critique.

    Étapes :
        1. récupérer les mesures de la fenêtre,
        2. convertir les horodatages en "heures écoulées" (axe X de la droite),
        3. calculer la tendance via calculer_score_regression(),
        4. enregistrer la DeriveDetectee,
        5. lever une alerte si critique (avec anti-doublon).

    Retour : un dictionnaire décrivant ce qui s'est passé, pour que la commande
    puisse afficher un message clair :
        {
            "statut": "analyse" | "donnees_insuffisantes",
            "derive": l'objet DeriveDetectee créé (ou None),
            "niveau": "critique" | "warning" | "normal" (ou None),
            "score":  le score (ou None),
            "pente":  la pente de la tendance (ou None),
            "alerte_creee": True/False,
        }
    """

    maintenant = timezone.now()
    debut_fenetre = maintenant - timedelta(hours=fenetre_heures)

    # Une seule requête : on récupère (valeur, timestamp) de la fenêtre, triées.
    mesures = Mesure.objects.filter(
        capteur=capteur,
        timestamp__gte=debut_fenetre,
        timestamp__lte=maintenant,
    ).order_by("timestamp").values_list("valeur", "timestamp")

    mesures = list(mesures)

    if len(mesures) < MIN_POINTS:
        return _resultat_insuffisant()

    # On prend le premier horodatage comme origine du temps (t = 0), puis on
    # exprime chaque mesure en heures écoulées depuis cette origine. La pente de
    # la droite ne dépend pas du choix de l'origine, c'est juste plus simple.
    t0 = mesures[0][1]
    points = [
        ((ts - t0).total_seconds() / 3600.0, valeur)
        for valeur, ts in mesures
    ]

    resultat = calculer_score_regression(points)

    # Pas calculable (durée nulle, bruit nul...) : on ne crée rien.
    if resultat is None:
        return _resultat_insuffisant()

    score = resultat["score"]
    niveau = niveau_pour_score(score)

    # On enregistre TOUJOURS la détection (même si le score est normal) : la
    # page F4.2 a besoin de l'évolution du score sur 30 jours, donc de tous les
    # points, pas seulement des dérives critiques.
    #   - moyenne_ref    = niveau moyen du capteur sur la fenêtre,
    #   - ecart_type_ref = le bruit (écart-type des résidus de la droite).
    derive = DeriveDetectee.objects.create(
        capteur=capteur,
        timestamp=maintenant,
        score=score,
        moyenne_ref=resultat["moyenne"],
        ecart_type_ref=resultat["sigma"],
        fenetre_heures=fenetre_heures,
    )

    # On ne lève une alerte QUE pour une dérive critique (règle du CdC :
    # "une dérive détectée au-delà d'un seuil critique génère une alerte").
    alerte_creee = False
    if niveau == "critique":
        alerte_creee = _creer_alerte_si_besoin(
            capteur, derive, resultat["valeur_estimee"], maintenant
        )

    return {
        "statut": "analyse",
        "derive": derive,
        "niveau": niveau,
        "score": score,
        "pente": resultat["pente"],
        "alerte_creee": alerte_creee,
    }


def _resultat_insuffisant():
    """Petit raccourci pour le cas 'pas assez de données'."""
    return {
        "statut": "donnees_insuffisantes",
        "derive": None,
        "niveau": None,
        "score": None,
        "pente": None,
        "alerte_creee": False,
    }


def _creer_alerte_si_besoin(capteur, derive, valeur_estimee, maintenant):
    """
    Crée une Alerte de type dérive pour ce capteur, sauf si une alerte de
    dérive est déjà ouverte récemment (anti-doublon, comme pour les seuils).

    Le "_" devant le nom signale par convention que cette fonction est interne
    au module et n'a pas vocation à être appelée de l'extérieur.

    Retour : True si une alerte a été créée, False si on a évité un doublon.
    """

    # Anti-doublon : une alerte de dérive ouverte depuis moins de 1 h pour ce
    # capteur suffit, inutile d'en empiler une nouvelle à chaque analyse.
    limite_anti_spam = maintenant - timedelta(hours=ANTI_SPAM_HEURES)

    alerte_existe = Alerte.objects.filter(
        capteur=capteur,
        type_alerte=Alerte.TypeAlerteChoices.DERIVE,
        statut=Alerte.StatutChoices.OUVERTE,
        timestamp_declenchement__gte=limite_anti_spam,
    ).exists()

    if alerte_existe:
        return False

    # Création de l'alerte. Pas de seuil associé (seuil=None) : une dérive n'est
    # pas un dépassement de seuil. On stocke la valeur estimée par la tendance
    # comme valeur déclenchante, c'est l'information la plus parlante.
    alerte = Alerte.objects.create(
        capteur=capteur,
        seuil=None,
        timestamp_declenchement=maintenant,
        niveau=Alerte.NiveauChoices.CRITIQUE,
        type_alerte=Alerte.TypeAlerteChoices.DERIVE,
        valeur_declenchante=valeur_estimee,
        statut=Alerte.StatutChoices.OUVERTE,
    )

    # On relie la détection à l'alerte qu'elle a provoquée (champ alerte du
    # modèle DeriveDetectee), pour pouvoir naviguer de l'une à l'autre.
    derive.alerte = alerte
    derive.save(update_fields=["alerte"])

    return True
