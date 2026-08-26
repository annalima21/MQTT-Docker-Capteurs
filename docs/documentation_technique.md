# Documentation technique — Plateforme de gestion de capteurs intelligents

> Projet 34 — BUT3 GEII, IUT Lyon 1
> Architecture, modèle de données, flux d'ingestion, algorithmes et API.

---

## Sommaire

1. [Vue d'ensemble](#1-vue-densemble)
2. [Stack et organisation du code](#2-stack-et-organisation-du-code)
3. [Modèle de données](#3-modèle-de-données)
4. [Flux d'ingestion MQTT](#4-flux-dingestion-mqtt)
5. [Le simulateur de capteurs](#5-le-simulateur-de-capteurs)
6. [Détection de dérive (analytics)](#6-détection-de-dérive-analytics)
7. [API et routes](#7-api-et-routes)
8. [Commandes d'administration](#8-commandes-dadministration)
9. [Configuration et déploiement](#9-configuration-et-déploiement)
10. [Sécurité et bonnes pratiques](#10-sécurité-et-bonnes-pratiques)
11. [Limites connues et perspectives](#11-limites-connues-et-perspectives)

---

## 1. Vue d'ensemble

La plateforme suit une architecture **microservices légère** orchestrée par Docker
Compose. Les services communiquent via **MQTT** (télémétrie) et partagent une base
**PostgreSQL**.

```
 sensor_sim ──publish──►  mqtt (Mosquitto)  ──subscribe──►  mqtt_worker
   (Django)                                                    (Django)
       │                                                          │
       │ lecture des capteurs (ORM)                               │ INSERT mesures
       │                                                          │ + détection seuils
       ▼                                                          ▼
                          ┌──────────────────────┐
                          │   PostgreSQL          │◄──── web (Django) : pages, API, admin
                          │   (Clever Cloud)      │
                          └──────────────────────┘
```

**Cycle d'une donnée** :

1. `sensor_sim` lit les capteurs actifs en base et **publie** une mesure par capteur sur
   un topic MQTT.
2. `mqtt_worker` est **abonné** au topic, valide le message et **enregistre** la mesure
   via l'ORM Django.
3. Lors de l'enregistrement, le worker vérifie les **seuils** du capteur et **crée une
   alerte** si un seuil est franchi.
4. Le service `web` expose l'interface, les endpoints JSON et l'admin.
5. À la demande, la commande `analyse_derive` analyse l'historique et crée des
   **détections de dérive** (et des alertes de dérive si nécessaire).

## 2. Stack et organisation du code

### Stack

| Couche | Technologie |
|---|---|
| Langage | Python 3.12 |
| Framework web | Django 6.0.5 |
| API | Endpoints internes en `JsonResponse` (Django REST Framework installé pour évolutions futures) |
| Base de données | PostgreSQL (prod/intégration) · SQLite (dev local) |
| Messagerie | MQTT — broker Eclipse Mosquitto 2, client `paho-mqtt` |
| Frontend | Templates Django, Bootstrap 5.3, Chart.js (CDN) |
| Conteneurisation | Docker, Docker Compose |
| Configuration | `python-decouple` (fichier `.env`) |

### Organisation des applications Django

Le code métier est réparti en **4 applications**, sous `apps/` :

| App | Responsabilité | Modèles |
|---|---|---|
| **core** | Référentiel et interface principale | `User`, `Site`, `TypeCapteur`, `Capteur`, `Seuil` |
| **ingestion** | Réception et stockage de la télémétrie | `Mesure` |
| **alertes** | Cycle de vie des alertes | `Alerte` |
| **analytics** | Analyse statistique et ML | `DeriveDetectee`, `ModeleML` |

Conventions du projet :

- **Vues fonctionnelles (FBV)** uniquement (pas de Class-Based Views).
- `select_related()` / `prefetch_related()` sur les relations affichées en boucle (anti N+1).
- `get_object_or_404()` pour les accès par clé primaire.
- Énumérations via `models.TextChoices` (pas de chaînes magiques).
- Commentaires en français.

## 3. Modèle de données

Le schéma comporte **9 entités métier** (+ `User`). La conception détaillée (démarche,
normalisation 3FN, cardinalités) est documentée dans
[`03_modele_de_donnees.md`](03_modele_de_donnees.md). Résumé des entités :

```
        Site 1───N Capteur N───1 TypeCapteur
                      │ 1
          ┌───────────┼───────────────┐
          │ N         │ N             │ N
        Seuil       Mesure          Alerte ◄──0/1── DeriveDetectee
                                       │ N
                                       │ 0/1 (acquittement)
                                      User ──0/N── ModeleML
```

### Entités principales

| Entité | Rôle | Champs notables |
|---|---|---|
| **Site** | Lieu d'installation | `nom` (unique), `latitude`, `longitude`, `adresse` |
| **TypeCapteur** | Catégorie (règles communes) | `code` (unique), `libelle`, `unite_si`, `plage_min/max` |
| **Capteur** | Capteur physique | `identifiant` (unique, clé MQTT), `site` (FK), `type_capteur` (FK), `actif`, `config_json` |
| **Seuil** | Limite déclenchant une alerte | `type_seuil` (bas/haut × warning/critique), `valeur`, `actif` ; unique par (capteur, type) |
| **Mesure** | Relevé horodaté | `capteur` (FK), `timestamp`, `valeur`, `qualite` ∈ [0,1], `anomalie_score`, `meta_json` |
| **Alerte** | Événement (seuil ou dérive) | `niveau`, `type_alerte`, `statut`, `valeur_declenchante`, `timestamp_declenchement/cloture`, `acquittement_user` |
| **DeriveDetectee** | Résultat d'une analyse de dérive | `score`, `moyenne_ref`, `ecart_type_ref`, `fenetre_heures`, `alerte` (FK) |
| **ModeleML** | Modèle TensorFlow Lite (ambition) | `nom`, `version`, `fichier_tflite`, `taille_octets`, `actif` |

### Énumérations

- `Capteur.type_capteur` → `TypeCapteur.CodeChoices` : `temperature`, `pression`, `vibration`, `qualite_air`.
- `Seuil.TypeSeuilChoices` : `bas_critique`, `bas_warning`, `haut_warning`, `haut_critique`.
- `Alerte.NiveauChoices` : `info`, `warning`, `critique`.
- `Alerte.TypeAlerteChoices` : `seuil`, `derive`, `communication`, `batterie`.
- `Alerte.StatutChoices` : `ouverte`, `acquittee`, `fermee`.

### Index

- `Mesure(capteur, -timestamp)` — requête « historique d'un capteur ».
- `Alerte(capteur, statut)` et `Alerte(-timestamp_declenchement)`.
- `DeriveDetectee(capteur, -timestamp)`.

### Comportements `on_delete`

- `Site`/`TypeCapteur` → `Capteur` : **RESTRICT** (pas de suppression si capteurs liés).
- `Capteur` → `Seuil`/`Mesure`/`Alerte` : **CASCADE**.
- `Seuil` → `Alerte` et `User` → `Alerte`/`ModeleML` : **SET_NULL**.

## 4. Flux d'ingestion MQTT

### Topic et format de message

- **Topic publié** : `sensors/<site>/<capteur_id>/telemetry`
- **Topic souscrit par le worker** : `sensors/+/+/telemetry` (les `+` acceptent tout segment)

**Payload JSON** d'une mesure :

```json
{
  "capteur_id": "TEMP-001",
  "timestamp": "2026-06-11T10:24:16+02:00",
  "type": "temperature",
  "valeur": 22.4,
  "unite": "celsius",
  "qualite": 0.98,
  "meta": { "batterie": 91, "mode_simulation": "normal", "...": "..." }
}
```

### Le worker d'ingestion

Implémenté dans [`apps/ingestion/mqtt_client.py`](../apps/ingestion/mqtt_client.py),
lancé par la commande `mqtt_worker`. À chaque message reçu (`on_message`) :

1. `close_old_connections()` (le worker tourne en continu).
2. Décodage et validation du JSON (présence de `capteur_id`, `timestamp`, `valeur`).
3. Recherche du capteur **actif** par son `identifiant` ; message ignoré si inconnu.
4. **Création de la `Mesure`** via l'ORM.
5. **Détection de dépassement de seuil** : pour chaque seuil actif du capteur, comparaison
   de la valeur ; création d'une **`Alerte`** de type `seuil` si franchi.
6. **Anti-doublon** : aucune nouvelle alerte si une alerte est déjà *ouverte* pour le même
   couple (capteur, seuil).
7. **Purge** : conservation des **1000 mesures** les plus récentes par capteur (limite la
   croissance de la table en développement).

### Règle de déclenchement des seuils

| Type de seuil | Condition | Niveau d'alerte |
|---|---|---|
| `haut_critique` | valeur > seuil | critique |
| `haut_warning` | valeur > seuil | warning |
| `bas_critique` | valeur < seuil | critique |
| `bas_warning` | valeur < seuil | warning |

## 5. Le simulateur de capteurs

[`sensor_simulators/simulator.py`](../sensor_simulators/simulator.py) génère une
télémétrie **réaliste**. Il s'initialise avec Django (`django.setup()`) pour lire les
capteurs actifs en base, puis publie sur MQTT à intervalle régulier.

### Modèle de génération

Pour chaque capteur, la valeur suit un **modèle autorégressif** piloté par une **machine
d'états** :

- **Profil par type** (`PROFILS_SIMULATION`) : plage normale, coefficient de retour
  `alpha`, bruit gaussien, facteurs d'anomalie. Surchargable par capteur via `config_json`
  (clés `simulation_min`, `simulation_max`, `simulation_alpha`, etc.).
- **Modèle autorégressif** : `valeur(t) = valeur(t-1) + alpha·(cible − valeur(t-1)) + bruit`,
  avec une variation bornée (5 % par pas par défaut) et un cap aux plages techniques.
- **Machine d'états** : `normal → anomalie → retour_normal`. Une **anomalie** est une
  excursion *transitoire* (quelques tours puis retour), à ne pas confondre avec une dérive.

### Dérive simulée (démonstration)

Pour démontrer le module de détection de dérive (F4.1), une **dérive progressive** est
injectée volontairement sur **un seul capteur** (`TEMP-003`), les autres servant de
témoins. La fonction `appliquer_derive_simulee()` ajoute une **rampe additive** à la
valeur publiée, sans modifier l'état autorégressif interne (analogie d'un capteur qui se
dérègle). Réglable par variables d'environnement :

| Variable | Défaut | Rôle |
|---|---|---|
| `SIMULATOR_DRIFT_SENSOR` | `TEMP-003` | Capteur qui dérive |
| `SIMULATOR_DRIFT_DELAY_MIN` | `20` | Minutes de comportement normal avant la dérive |
| `SIMULATOR_DRIFT_PER_HOUR` | `18.0` | Vitesse de la dérive (unités/heure ; `0` = désactivée) |

## 6. Détection de dérive (analytics)

Le module implémente les fonctionnalités **F4.1** (détection) et **F4.2** (visualisation)
du cahier des charges.

### Définition

Une dérive est une **évolution lente et progressive** d'un capteur, *sans dépassement
ponctuel de seuil*. C'est une **tendance** dans le temps, pas un pic.

### Algorithme : régression linéaire

Implémenté dans [`apps/analytics/derive.py`](../apps/analytics/derive.py). Sur une
fenêtre glissante (24 h par défaut), on ajuste la **droite des moindres carrés** au nuage
de points `(temps, valeur)`, puis on compare la **tendance** au **bruit** :

```
pente b = Σ(tᵢ − t̄)(yᵢ − ȳ) / Σ(tᵢ − t̄)²
résidus = yᵢ − (a + b·tᵢ)        →     σ = écart-type des résidus

score = (|b| × durée_fenêtre) / σ
```

Le score représente **« de combien de fois le bruit normal la valeur a glissé sur la
fenêtre »**. Cette approche a été retenue plutôt qu'une comparaison de moyennes parce que
la droite **absorbe la tendance** : le bruit (les résidus) reste stable même quand la
dérive grandit, donc le score ne sature pas — ce qui correspond exactement à une dérive
progressive.

Les champs stockés dans `DeriveDetectee` : `score`, `moyenne_ref` (niveau moyen sur la
fenêtre), `ecart_type_ref` (σ des résidus = bruit du capteur), `fenetre_heures`.

### Seuils et alertes

| Score | Niveau | Action |
|---|---|---|
| < 2,0 | normal | détection enregistrée (pour le graphe sur 30 j) |
| 2,0 – 3,5 | warning | détection enregistrée |
| ≥ 3,5 | critique | détection + **alerte de type `derive`** (niveau critique) |

Garde-fous : volume minimal de points exigé, protection contre la division par zéro
(durée ou bruit quasi nuls), et **anti-doublon** d'alerte (pas de nouvelle alerte de dérive
ouverte depuis moins d'1 h pour le même capteur).

### Effet de la taille de fenêtre

La fenêtre est le **levier de sensibilité** : une fenêtre courte réagit vite aux tendances
récentes (mais est plus sensible au bruit), une fenêtre longue ne signale que les dérives
lentes et durables. Réglable via `analyse_derive --fenetre <heures>`.

## 7. API et routes

### Carte des URL

| Méthode | URL | Vue | Description |
|---|---|---|---|
| GET | `/` | `core.accueil` | Tableau de bord |
| GET | `/capteurs/` | `core.liste_capteurs` | Liste des capteurs |
| GET | `/capteurs/<id>/` | `core.detail_capteur` | Fiche capteur |
| GET/POST | `/capteurs/nouveau/` | `core.capteur_create` | Création |
| GET/POST | `/capteurs/<id>/modifier/` | `core.capteur_update` | Modification |
| GET/POST | `/capteurs/<id>/supprimer/` | `core.capteur_delete` | Suppression |
| GET | `/sites/` | `core.liste_sites` | Liste des sites |
| GET | `/historique/`, `/historique/<id>/` | `core.historique_mesures` | Page historique |
| GET | `/alertes/` | `alertes.liste_alertes` | Liste des alertes (filtre `?statut=`) |
| GET/POST | `/alertes/<id>/acquitter/` | `alertes.acquitter_alerte` | Acquittement |
| GET/POST | `/alertes/<id>/fermer/` | `alertes.fermer_alerte` | Clôture |
| GET | `/analytics/derives/` | `analytics.liste_derives` | Page dérive (`?capteur_id=`) |
| POST | `/analytics/derives/analyser/` | `analytics.lancer_analyse` | Déclenche l'analyse |
| GET | `/admin/` | Django admin | Administration |

### Endpoints JSON (consommés par le frontend)

Ces deux endpoints renvoient du JSON (`JsonResponse`) et alimentent le JavaScript des
pages d'accueil et d'historique.

#### `GET /api/mesures-actuelles/`

Dernière mesure et état calculé de chaque capteur actif. Utilisé par le rafraîchissement
automatique (5 s) du tableau de bord.

```json
{
  "capteurs": [
    {
      "id": 1,
      "identifiant": "TEMP-001",
      "nom": "Sonde salle 101",
      "type": "Capteur de température",
      "unite": "°C",
      "valeur": 22.4,
      "valeur_affichee": "22.40 °C",
      "timestamp": "2026-06-11T10:24:16+02:00",
      "timestamp_affiche": "11/06/2026 10:24:16",
      "qualite": 0.98,
      "etat": "OK",
      "etat_classe": "success"
    }
  ]
}
```

#### `GET /api/historique-mesures/`

Mesures d'un capteur sur une période. **Paramètres** :

| Paramètre | Obligatoire | Valeurs |
|---|---|---|
| `capteur_id` | oui | identifiant numérique du capteur |
| `periode` | non (défaut `24h`) | `1h`, `6h`, `24h`, `7j`, `30j`, `custom` |
| `date_debut`, `date_fin` | si `periode=custom` | ISO 8601 (ex. `2026-06-11T08:00`) |

```json
{
  "capteur": { "id": 1, "identifiant": "TEMP-001", "nom": "...", "unite": "°C", "type": "..." },
  "periode": "24h",
  "date_debut": "10/06/2026 10:24:16",
  "date_fin": "11/06/2026 10:24:16",
  "nombre_mesures": 240,
  "mesures": [
    { "timestamp": "2026-06-11T10:24:16+02:00", "timestamp_affiche": "11/06/2026 10:24:16",
      "valeur": 22.4, "valeur_affichee": "22.40 °C", "qualite": 0.98 }
  ]
}
```

Réponse limitée à **1000 mesures** ; codes d'erreur `400` (paramètre manquant/invalide),
`404` (capteur inexistant ou inactif).

## 8. Commandes d'administration

| Commande | Description |
|---|---|
| `python manage.py mqtt_worker` | Démarre le worker d'ingestion MQTT (boucle infinie) |
| `python manage.py analyse_derive` | Analyse la dérive de tous les capteurs actifs (une passe) |
| `python manage.py analyse_derive --continu [--intervalle 300]` | Analyse en boucle (toutes les N secondes) |
| `python manage.py analyse_derive --fenetre 2` | Analyse sur une fenêtre de N heures (défaut 24) |
| `python manage.py seed_demo_data` | Crée 3 sites, 4 types, 10 capteurs et leurs seuils (idempotent) |
| `python manage.py migrate` | Applique les migrations |
| `python manage.py createsuperuser` | Crée un compte administrateur |

## 9. Configuration et déploiement

### Fichiers de settings

- **`config/settings.py`** — configuration de référence : PostgreSQL (variables `POSTGRES_*`
  du `.env`), apps installées, middlewares, fuseau `Europe/Paris`, modèle utilisateur
  personnalisé `core.User`.
- **`config/settings_dev.py`** — hérite de `settings.py` et **remplace uniquement la base
  par SQLite** (`db_dev.sqlite3`) pour le développement local sans Docker.

Le module actif se choisit via `DJANGO_SETTINGS_MODULE` (défaut `config.settings`).

### Services Docker Compose

| Service | Image / Build | Commande |
|---|---|---|
| `mqtt` | `eclipse-mosquitto:2` | broker MQTT (port 1883) |
| `web` | build local | `python manage.py runserver 0.0.0.0:8000` |
| `mqtt_worker` | build local | `python manage.py mqtt_worker` |
| `sensor_sim` | build local | `python sensor_simulators/simulator.py` |

Le `Dockerfile` est basé sur `python:3.12-slim` et installe `requirements.txt`. Le broker
Mosquitto est configuré en accès anonyme et persistance locale
([`mqtt_broker/mosquitto.conf`](../mqtt_broker/mosquitto.conf)).

### Mise en route (première fois)

```bash
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo_data
docker compose exec web python manage.py createsuperuser
```

## 10. Sécurité et bonnes pratiques

- **Secrets** : la configuration sensible (clé Django, identifiants PostgreSQL) est
  externalisée dans `.env`. Ce fichier **ne doit pas être versionné** ; il convient de
  l'ajouter à `.gitignore` et de **faire tourner les identifiants** s'ils ont été exposés.
- **`DEBUG`** : à passer à `False` en production, avec un `ALLOWED_HOSTS` restreint.
- **Limite de connexions PostgreSQL** : l'offre de base Clever Cloud limite le nombre de
  connexions simultanées. Éviter de cumuler trop de services et d'onglets ouverts (le
  tableau de bord interroge le serveur toutes les 5 s) ; pour le développement courant,
  privilégier `settings_dev` (SQLite).
- **Intégrité** : les contraintes d'unicité et les `on_delete` sont appliqués au niveau
  base ; la suppression d'un capteur ayant des mesures est interdite côté applicatif.

## 11. Limites connues et perspectives

| Sujet | État | Perspective |
|---|---|---|
| Gestion des modèles ML (`ModeleML`) | Modèle et admin en place ; pas d'interface d'upload | Écran d'upload/activation `.tflite`, inférence edge |
| Entraînement ML (`train_model.py`) | Stub | Implémenter le pipeline d'entraînement |
| Tests automatisés | Squelettes présents | Tests unitaires (ingestion, dérive, alertes) |
| API REST publique | DRF installé, endpoints internes en JSON | Exposer une API REST versionnée si besoin |
| Détection de dérive en continu | Disponible via `--continu` (manuel) | Service dédié / tâche planifiée |
| Volumétrie `Mesure` | Purge à 1000 mesures/capteur (dev) | Partitionnement / rétention en production |

---

*Projet 34 — BUT3 GEII, IUT Lyon 1. Documentation technique de la plateforme de gestion de capteurs intelligents.*
