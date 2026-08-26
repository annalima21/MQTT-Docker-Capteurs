import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.utils.text import slugify

# ============================================================
# Initialisation Django
# ============================================================
# Le simulateur tourne comme un script Python indépendant,
# mais il doit accéder aux modèles Django pour lire les capteurs
# enregistrés en base.
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
from django.db import OperationalError

django.setup()

from apps.core.models import Capteur
from publisher import MqttPublisher


# ============================================================
# Paramètres généraux du simulateur
# ============================================================

PARIS = ZoneInfo("Europe/Paris")

INTERVALLE_SECONDES = int(
    os.getenv("SIMULATOR_INTERVAL_SECONDS", "60")
)

RECHARGEMENT_CAPTEURS_SECONDES = int(
    os.getenv("SIMULATOR_RELOAD_SECONDS", "120")
)

# Variation maximale autorisée entre deux valeurs successives.
# 0.05 = 5%.
VARIATION_MAX_POURCENT = float(
    os.getenv("SIMULATOR_VARIATION_PERCENT", "0.05")
)

# Probabilité qu'un capteur normal entre en anomalie à chaque tour.
# 0.02 = 2% par capteur et par tour.
PROBABILITE_ANOMALIE = float(
    os.getenv("SIMULATOR_ANOMALY_PROBABILITY", "0.02")
)

# Durée des anomalies en nombre de tours.
# Si le simulateur publie toutes les 30 secondes :
# 4 tours = 2 minutes
# 12 tours = 6 minutes
DUREE_ANOMALIE_MIN_TOURS = int(
    os.getenv("SIMULATOR_ANOMALY_MIN_TOURS", "4")
)

DUREE_ANOMALIE_MAX_TOURS = int(
    os.getenv("SIMULATOR_ANOMALY_MAX_TOURS", "12")
)


# ============================================================
# Dérive simulée (pour démontrer la détection de dérive — F4.1)
# ============================================================
# On fait dériver volontairement UN SEUL capteur, TEMP-003 (salle serveurs),
# pour pouvoir démontrer le module de détection de dérive. Les autres capteurs
# restent sains et servent de témoins (ils ne doivent pas déclencher de fausse
# alerte de dérive).
#
# Une dérive n'est PAS une anomalie : l'anomalie de ce simulateur est un pic
# transitoire qui revient à la normale, alors que la dérive est une montée
# LENTE et permanente. On l'ajoute donc par-dessus la valeur autorégressive,
# comme un capteur qui se dérègle (la vraie température reste normale, mais le
# capteur la lit de plus en plus haut).
CAPTEUR_QUI_DERIVE = os.getenv("SIMULATOR_DRIFT_SENSOR", "TEMP-003")

# Comportement normal au début (minutes) : ces mesures servent de référence saine.
MINUTES_AVANT_DERIVE = float(os.getenv("SIMULATOR_DRIFT_DELAY_MIN", "20"))

# Vitesse de la dérive une fois lancée (unités du capteur ajoutées par heure).
# Réglée pour atteindre le seuil critique en ~1 h de démo malgré le bruit du
# modèle autorégressif ; une vraie dérive serait bien plus lente.
# Mettre 0 pour désactiver la dérive.
DERIVE_PAR_HEURE = float(os.getenv("SIMULATOR_DRIFT_PER_HOUR", "18.0"))

# Instant de démarrage du simulateur : sert à mesurer le temps écoulé.
TEMPS_DEMARRAGE = time.time()


# ============================================================
# Profils par type de capteur
# ============================================================
# Chaque type de capteur ne varie pas de la même manière.
#
# alpha :
#   coefficient autorégressif de retour vers la cible.
#   Plus alpha est grand, plus le capteur va vite vers sa cible.
#
# bruit_pourcent :
#   bruit naturel ajouté à chaque mesure.
#
# normal_min / normal_max :
#   zone normale de simulation.
#
# anomalie_haute_factor :
#   en anomalie haute, la cible dépasse la zone normale.
#
# anomalie_basse_factor :
#   en anomalie basse, la cible descend sous la zone normale.
# ============================================================

PROFILS_SIMULATION = {
    "temperature": {
        "normal_min": 19.0,
        "normal_max": 37.0,
        "unite": "celsius",
        "alpha": 0.25,
        "bruit_pourcent": 0.01,
        "anomalie_haute_factor": 1.35,
        "anomalie_basse_factor": 0.75,
        "probabilite_anomalie": 0.015,
    },
    "pression": {
        "normal_min": 300_000.0,
        "normal_max": 700_000.0,
        "unite": "Pa",
        "alpha": 0.40,
        "bruit_pourcent": 0.015,
        "anomalie_haute_factor": 1.45,
        "anomalie_basse_factor": 0.60,
        "probabilite_anomalie": 0.020,
    },
    "vibration": {
        "normal_min": 2.0,
        "normal_max": 10.0,
        "unite": "m/s²",
        "alpha": 0.65,
        "bruit_pourcent": 0.06,
        "anomalie_haute_factor": 2.80,
        "anomalie_basse_factor": 0.50,
        "probabilite_anomalie": 0.030,
    },
    "qualite_air": {
        "normal_min": 400.0,
        "normal_max": 700.0,
        "unite": "ppm",
        "alpha": 0.20,
        "bruit_pourcent": 0.02,
        "anomalie_haute_factor": 2.20,
        "anomalie_basse_factor": 0.85,
        "probabilite_anomalie": 0.025,
    },
}


# ============================================================
# Mémoire interne du simulateur
# ============================================================
# Cette variable garde l'état de chaque capteur.
# Sans cette mémoire, chaque valeur serait indépendante.
#
# Exemple :
# {
#   "TEMP-001": {
#       "valeur": 22.4,
#       "cible": 23.0,
#       "mode": "normal",
#       "anomalie_type": None,
#       "tours_anomalie_restants": 0,
#       "batterie": 91
#   }
# }
# ============================================================

etat_capteurs = {}


# ============================================================
# Accès base de données
# ============================================================

def attendre_base_donnees():
    """
    Attend que la base soit disponible.

    Utile avec Docker Compose : parfois le conteneur du simulateur
    démarre avant que PostgreSQL soit prêt.
    """

    while True:
        try:
            Capteur.objects.count()
            return

        except OperationalError as erreur:
            print(
                f"Base non disponible, nouvelle tentative dans 5 s : {erreur}"
            )
            time.sleep(5)


def charger_capteurs_actifs():
    """
    Récupère tous les capteurs actifs enregistrés en base.

    Ainsi, si on ajoute TEMP-004 dans Django Admin ou dans le CRUD,
    le simulateur le récupère automatiquement au prochain rechargement.
    """

    return list(
        Capteur.objects.filter(actif=True)
        .select_related("site", "type_capteur")
        .prefetch_related("seuils")
        .order_by("identifiant")
    )


# ============================================================
# Profil de simulation
# ============================================================

def profil_pour_capteur(capteur):
    """
    Retourne le profil de simulation adapté au type du capteur.

    Exemple :
    - capteur.type_capteur.code = "temperature"
    - le simulateur utilise le profil "temperature"

    Le champ config_json du capteur peut aussi surcharger certains paramètres.
    """

    code_type = capteur.type_capteur.code

    profil = PROFILS_SIMULATION.get(code_type, {}).copy()

    # Si le type n'a pas de profil explicite, on tente d'utiliser
    # les plages techniques du TypeCapteur.
    if not profil:
        if (
            capteur.type_capteur.plage_min is None
            or capteur.type_capteur.plage_max is None
        ):
            return None

        profil = {
            "normal_min": float(capteur.type_capteur.plage_min),
            "normal_max": float(capteur.type_capteur.plage_max),
            "unite": capteur.type_capteur.unite_si,
            "alpha": 0.30,
            "bruit_pourcent": 0.02,
            "anomalie_haute_factor": 1.30,
            "anomalie_basse_factor": 0.70,
            "probabilite_anomalie": PROBABILITE_ANOMALIE,
        }

    config = capteur.config_json or {}

    # Possibilité de personnaliser un capteur précis depuis config_json.
    # Exemple :
    # {
    #   "simulation_min": 20,
    #   "simulation_max": 24,
    #   "simulation_alpha": 0.2,
    #   "simulation_anomaly_probability": 0.05
    # }

    profil["normal_min"] = float(
        config.get("simulation_min", profil["normal_min"])
    )

    profil["normal_max"] = float(
        config.get("simulation_max", profil["normal_max"])
    )

    profil["unite"] = config.get(
        "simulation_unite",
        profil.get("unite", capteur.type_capteur.unite_si),
    )

    profil["alpha"] = float(
        config.get("simulation_alpha", profil["alpha"])
    )

    profil["bruit_pourcent"] = float(
        config.get("simulation_noise_percent", profil["bruit_pourcent"])
    )

    profil["probabilite_anomalie"] = float(
        config.get(
            "simulation_anomaly_probability",
            profil.get("probabilite_anomalie", PROBABILITE_ANOMALIE),
        )
    )

    profil["variation_max_pourcent"] = float(
        config.get("simulation_variation_percent", VARIATION_MAX_POURCENT)
    )

    profil["anomaly_min_tours"] = int(
        config.get("simulation_anomaly_min_tours", DUREE_ANOMALIE_MIN_TOURS)
    )

    profil["anomaly_max_tours"] = int(
        config.get("simulation_anomaly_max_tours", DUREE_ANOMALIE_MAX_TOURS)
    )

    return profil


# ============================================================
# Seuils
# ============================================================

def seuils_actifs(capteur):
    """
    Transforme les seuils actifs du capteur en dictionnaire.

    Exemple :
    {
        "haut_warning": 28,
        "haut_critique": 35
    }
    """

    return {
        seuil.type_seuil: seuil.valeur
        for seuil in capteur.seuils.all()
        if seuil.actif
    }


# ============================================================
# Initialisation d'un capteur
# ============================================================

def choisir_cible_normale(profil):
    """
    Choisit une valeur cible dans la zone normale du capteur.
    """

    return random.uniform(
        profil["normal_min"],
        profil["normal_max"],
    )


def initialiser_etat_capteur(capteur, profil):
    """
    Initialise l'état interne d'un capteur.

    Cette fonction est appelée une seule fois par capteur,
    lorsque le simulateur découvre ce capteur.
    """

    valeur_initiale = choisir_cible_normale(profil)

    etat_capteurs[capteur.identifiant] = {
        "valeur": valeur_initiale,
        "cible": valeur_initiale,
        "mode": "normal",
        "anomalie_type": None,
        "tours_anomalie_restants": 0,
        "batterie": random.randint(70, 100),
    }


# ============================================================
# Limites techniques
# ============================================================

def limiter_aux_plages_techniques(capteur, valeur):
    """
    Empêche une valeur de sortir de la plage technique du TypeCapteur.

    Exemple :
    si TypeCapteur.plage_max = 80 °C,
    le simulateur ne publie jamais 140 °C.
    """

    plage_min = capteur.type_capteur.plage_min
    plage_max = capteur.type_capteur.plage_max

    if plage_min is not None:
        valeur = max(float(plage_min), valeur)

    if plage_max is not None:
        valeur = min(float(plage_max), valeur)

    return valeur


# ============================================================
# Anomalies
# ============================================================

def choisir_cible_anormale(capteur, profil):
    """
    Choisit une cible anormale.

    Le simulateur privilégie les seuils configurés en base.
    Si aucun seuil n'existe, il utilise les facteurs du profil.
    """

    seuils = seuils_actifs(capteur)

    peut_monter = (
        "haut_warning" in seuils
        or "haut_critique" in seuils
    )

    peut_descendre = (
        "bas_warning" in seuils
        or "bas_critique" in seuils
    )

    if peut_monter and peut_descendre:
        anomalie_type = random.choice(["haute", "basse"])

    elif peut_monter:
        anomalie_type = "haute"

    elif peut_descendre:
        anomalie_type = "basse"

    else:
        anomalie_type = random.choice(["haute", "basse"])

    if anomalie_type == "haute":
        seuil_haut = (
            seuils.get("haut_critique")
            or seuils.get("haut_warning")
        )

        if seuil_haut is not None:
            cible = seuil_haut * random.uniform(1.03, 1.15)

        else:
            cible = profil["normal_max"] * profil["anomalie_haute_factor"]

    else:
        seuil_bas = (
            seuils.get("bas_critique")
            or seuils.get("bas_warning")
        )

        if seuil_bas is not None:
            cible = seuil_bas * random.uniform(0.85, 0.97)

        else:
            cible = profil["normal_min"] * profil["anomalie_basse_factor"]

    cible = limiter_aux_plages_techniques(
        capteur,
        cible,
    )

    return anomalie_type, cible


# ============================================================
# Machine d'états
# ============================================================

def mettre_a_jour_mode(capteur, profil):
    """
    Gère la machine d'états du capteur.

    États possibles :
    - normal
    - anomalie
    - retour_normal
    """

    etat = etat_capteurs[capteur.identifiant]

    # Si le capteur est en anomalie, on réduit la durée restante.
    if etat["mode"] == "anomalie":
        etat["tours_anomalie_restants"] -= 1

        # Quand la durée est terminée, le capteur revient vers une cible normale.
        if etat["tours_anomalie_restants"] <= 0:
            etat["mode"] = "retour_normal"
            etat["anomalie_type"] = None
            etat["cible"] = choisir_cible_normale(profil)

        return

    # Si le capteur revient au normal, on attend qu'il rentre dans la zone normale.
    if etat["mode"] == "retour_normal":
        valeur = etat["valeur"]

        if profil["normal_min"] <= valeur <= profil["normal_max"]:
            etat["mode"] = "normal"
            etat["cible"] = choisir_cible_normale(profil)

        return

    # Si le capteur est normal, il peut parfois entrer en anomalie.
    if random.random() < profil["probabilite_anomalie"]:
        anomalie_type, cible = choisir_cible_anormale(
            capteur,
            profil,
        )

        etat["mode"] = "anomalie"
        etat["anomalie_type"] = anomalie_type
        etat["tours_anomalie_restants"] = random.randint(
            profil["anomaly_min_tours"],
            profil["anomaly_max_tours"],
        )
        etat["cible"] = cible

        return

    # Même en mode normal, la cible peut changer légèrement.
    # Cela évite une courbe trop plate.
    if random.random() < 0.20:
        etat["cible"] = choisir_cible_normale(profil)


# ============================================================
# Modèle autorégressif
# ============================================================

def calculer_valeur_autoregressive(capteur, profil):
    """
    Calcule la prochaine valeur du capteur avec un modèle autorégressif.

    Principe :
    nouvelle valeur =
        ancienne valeur
        + correction vers la cible
        + bruit naturel

    Puis on limite la variation à maximum 5% par défaut.
    """

    etat = etat_capteurs[capteur.identifiant]

    ancienne_valeur = etat["valeur"]
    cible = etat["cible"]

    alpha = profil["alpha"]
    bruit_pourcent = profil["bruit_pourcent"]
    variation_max_pourcent = profil["variation_max_pourcent"]

    # Correction vers la cible.
    correction = alpha * (cible - ancienne_valeur)

    # Bruit naturel.
    # random.gauss(0, sigma) donne un bruit centré autour de 0.
    sigma = max(
        abs(ancienne_valeur) * bruit_pourcent,
        0.01,
    )

    bruit = random.gauss(
        0,
        sigma,
    )

    variation = correction + bruit

    # Limitation à 5% entre deux valeurs successives.
    variation_max = max(
        abs(ancienne_valeur) * variation_max_pourcent,
        0.01,
    )

    variation = max(
        -variation_max,
        min(variation_max, variation),
    )

    nouvelle_valeur = ancienne_valeur + variation

    nouvelle_valeur = limiter_aux_plages_techniques(
        capteur,
        nouvelle_valeur,
    )

    etat["valeur"] = nouvelle_valeur

    return round(nouvelle_valeur, 2)


# ============================================================
# Dérive simulée
# ============================================================

def appliquer_derive_simulee(capteur, valeur):
    """
    Ajoute une dérive progressive à la valeur d'UN capteur (CAPTEUR_QUI_DERIVE)
    pour démontrer la détection de dérive (F4.1).

    On n'ajoute rien tant qu'on est dans la phase normale du début
    (MINUTES_AVANT_DERIVE) : ces mesures saines servent de référence à
    l'algorithme. Ensuite, on ajoute une rampe proportionnelle au temps écoulé.

    La dérive ne modifie PAS l'état interne autorégressif (etat["valeur"]) :
    elle s'ajoute uniquement à la valeur publiée, exactement comme un capteur
    dont la lecture se décale alors que la grandeur réelle reste normale.
    """

    # Capteur non concerné, ou dérive désactivée : on ne touche à rien.
    if capteur.identifiant != CAPTEUR_QUI_DERIVE or DERIVE_PAR_HEURE == 0:
        return valeur

    minutes_ecoulees = (time.time() - TEMPS_DEMARRAGE) / 60.0

    if minutes_ecoulees <= MINUTES_AVANT_DERIVE:
        return valeur

    heures_de_derive = (minutes_ecoulees - MINUTES_AVANT_DERIVE) / 60.0
    valeur_derivee = valeur + DERIVE_PAR_HEURE * heures_de_derive

    # On reste dans les limites techniques du type de capteur.
    valeur_derivee = limiter_aux_plages_techniques(capteur, valeur_derivee)

    return round(valeur_derivee, 2)


# ============================================================
# Comportement spécifique par type
# ============================================================

def adapter_cible_selon_contexte(capteur, profil):
    """
    Ajuste la cible selon le contexte.

    Exemple :
    pour la qualité de l'air, le CO₂ a tendance à monter en journée
    et à redescendre le soir/nuit.
    """

    code_type = capteur.type_capteur.code
    etat = etat_capteurs[capteur.identifiant]

    if etat["mode"] != "normal":
        return

    if code_type == "qualite_air":
        heure = datetime.now(PARIS).hour

        # Journée de travail : plus d'occupation, donc CO₂ plus haut.
        if 8 <= heure <= 18:
            etat["cible"] = random.uniform(
                profil["normal_min"] + 100,
                profil["normal_max"],
            )

        # Nuit : moins d'occupation, donc CO₂ plus bas.
        else:
            etat["cible"] = random.uniform(
                profil["normal_min"],
                profil["normal_min"] + 120,
            )

    if code_type == "temperature":
        # La température varie lentement.
        # On évite donc de changer trop souvent la cible.
        if random.random() < 0.05:
            etat["cible"] = choisir_cible_normale(profil)

    if code_type == "vibration":
        # La vibration est plus instable.
        # On autorise donc des changements de cible plus fréquents.
        if random.random() < 0.30:
            etat["cible"] = choisir_cible_normale(profil)


# ============================================================
# Batterie
# ============================================================

def mettre_a_jour_batterie(capteur):
    """
    Simule une batterie qui descend lentement.
    """

    etat = etat_capteurs[capteur.identifiant]

    if random.random() < 0.10:
        etat["batterie"] = max(
            0,
            etat["batterie"] - 1,
        )


# ============================================================
# Payload MQTT
# ============================================================

def construire_payload(capteur, valeur, profil):
    """
    Construit le message JSON publié sur MQTT.
    """

    etat = etat_capteurs[capteur.identifiant]

    qualite = random.uniform(0.96, 1.0)

    if etat["mode"] == "anomalie":
        qualite = random.uniform(0.80, 0.95)

    return {
        "capteur_id": capteur.identifiant,
        "timestamp": datetime.now(PARIS).isoformat(),
        "type": capteur.type_capteur.code,
        "valeur": valeur,
        "unite": profil["unite"],
        "qualite": round(qualite, 2),
        "meta": {
            "simulateur": True,
            "mode_simulation": etat["mode"],
            "anomalie_active": etat["mode"] == "anomalie",
            "anomalie_type": etat["anomalie_type"],
            "tours_anomalie_restants": etat["tours_anomalie_restants"],
            "batterie": etat["batterie"],
            "site": capteur.site.nom,
            "firmware": capteur.firmware_version,
            "modele": "autoregressif_machine_etats",
        },
    }


# ============================================================
# Publication d'une mesure
# ============================================================

def publier_mesure(publisher, capteur):
    """
    Génère et publie une mesure pour un capteur.
    """

    profil = profil_pour_capteur(capteur)

    if profil is None:
        print(
            f"Capteur ignoré : {capteur.identifiant} "
            f"type={capteur.type_capteur.code} sans profil ni plage technique"
        )
        return False

    if capteur.identifiant not in etat_capteurs:
        initialiser_etat_capteur(
            capteur,
            profil,
        )

    adapter_cible_selon_contexte(
        capteur,
        profil,
    )

    mettre_a_jour_mode(
        capteur,
        profil,
    )

    valeur = calculer_valeur_autoregressive(
        capteur,
        profil,
    )

    # Dérive simulée : n'affecte que TEMP-003, sans toucher l'état interne.
    valeur = appliquer_derive_simulee(capteur, valeur)

    mettre_a_jour_batterie(capteur)

    payload = construire_payload(
        capteur,
        valeur,
        profil,
    )

    site_topic = slugify(capteur.site.nom) or "site"

    topic = f"sensors/{site_topic}/{capteur.identifiant}/telemetry"

    publisher.publish(
        topic,
        payload,
    )

    etat = etat_capteurs[capteur.identifiant]

    print(
        f"{capteur.identifiant} | "
        f"{capteur.type_capteur.code} | "
        f"{valeur} {profil['unite']} | "
        f"mode={etat['mode']} | "
        f"cible={round(etat['cible'], 2)} | "
        f"anomalie={etat['anomalie_type']}"
    )

    return True


# ============================================================
# Programme principal
# ============================================================

def main():
    """
    Boucle principale du simulateur.
    """

    publisher = MqttPublisher(
        host=os.getenv("MQTT_BROKER_HOST", "mqtt"),
        port=int(os.getenv("MQTT_BROKER_PORT", "1883")),
    )

    attendre_base_donnees()

    publisher.connect()

    print("Simulateur réaliste démarré")
    print(f"Intervalle de publication : {INTERVALLE_SECONDES} s")
    print(f"Variation maximale : {VARIATION_MAX_POURCENT * 100:.1f}%")
    print("Modèle : autorégressif + machine d'états + profils par type")

    dernier_rechargement = 0
    capteurs = []

    while True:
        maintenant = time.time()

        if maintenant - dernier_rechargement >= RECHARGEMENT_CAPTEURS_SECONDES:
            capteurs = charger_capteurs_actifs()
            dernier_rechargement = maintenant

            print(
                f"Capteurs actifs trouvés en base : {len(capteurs)}"
            )

        total_publie = 0

        for capteur in capteurs:
            if publier_mesure(
                publisher,
                capteur,
            ):
                total_publie += 1

        print(
            f"--- tour terminé ({total_publie}/{len(capteurs)} capteurs publiés) ---"
        )

        time.sleep(INTERVALLE_SECONDES)


if __name__ == "__main__":
    main()