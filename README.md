# Plateforme de gestion de capteurs intelligents

> Projet 34 — BUT3 GEII, IUT Lyon 1
> Plateforme web de supervision d'un parc de capteurs IoT industriels : inventaire,
> ingestion temps réel via MQTT, tableau de bord, alertes automatiques et détection
> statistique de dérive.

---

## Sommaire

- [1. Présentation](#1-présentation)
- [2. Fonctionnalités](#2-fonctionnalités)
- [3. Stack technique](#3-stack-technique)
- [4. Architecture](#4-architecture)
- [5. Démarrage rapide](#5-démarrage-rapide)
- [6. Variables d'environnement](#6-variables-denvironnement)
- [7. Commandes utiles](#7-commandes-utiles)
- [8. Structure du projet](#8-structure-du-projet)
- [9. Documentation](#9-documentation)

---

## 1. Présentation

La plateforme centralise la gestion d'un parc de capteurs intelligents (température,
pression, vibration, qualité de l'air). Elle reçoit les mesures en temps réel par le
protocole **MQTT**, les enregistre en base, supervise l'état du parc via un tableau de
bord, **déclenche automatiquement des alertes** en cas de dépassement de seuil, et
**analyse l'historique pour détecter les dérives progressives** des capteurs
(vieillissement, besoin de calibration).

Le projet est développé dans le cadre du BUT3 GEII. Il couvre l'ensemble de la chaîne :
référentiel des équipements, ingestion de la télémétrie, traitement des alertes,
visualisation et analyse statistique.

## 2. Fonctionnalités

| Module | Fonctionnalités |
|---|---|
| **Référentiel** | CRUD des capteurs, des sites et des seuils ; activation/désactivation logique |
| **Ingestion** | Worker MQTT, validation et enregistrement des mesures en base |
| **Tableau de bord** | KPIs (capteurs actifs, sites, alertes ouvertes) + tableau temps réel auto-rafraîchi |
| **Historique** | Graphique interactif (Chart.js) des mesures par capteur et par période |
| **Alertes** | Détection automatique de dépassement de seuil ; cycle de vie *ouverte → acquittée → fermée* |
| **Dérive** | Détection statistique par régression linéaire ; page d'analyse + déclenchement à la demande |
| **Administration** | Interface d'administration Django sur l'ensemble des entités |

## 3. Stack technique

- **Backend** : Python 3.12, Django 6.0.5, Django REST Framework 3.17 (présent, endpoints internes en JSON)
- **Base de données** : PostgreSQL (hébergement Clever Cloud) ; SQLite en développement local
- **Messagerie** : MQTT (broker Eclipse Mosquitto)
- **Frontend** : templates Django, Bootstrap 5.3, Chart.js (via CDN)
- **Conteneurisation** : Docker & Docker Compose
- **Client MQTT** : paho-mqtt

## 4. Architecture

L'application est découpée en **4 services** orchestrés par Docker Compose :

```
                         ┌─────────────────────────┐
                         │   Navigateur (Bootstrap  │
                         │    + Chart.js)           │
                         └────────────┬────────────┘
                                      │ HTTP
                         ┌────────────▼────────────┐         ┌──────────────────┐
   ┌──────────────┐      │   web (Django)          │────────▶│   PostgreSQL     │
   │  sensor_sim  │      │   - pages & API JSON     │  ORM    │  (Clever Cloud)  │
   │  (capteurs   │      │   - admin               │◀────────│                  │
   │   simulés)   │      └────────────▲────────────┘         └────────▲─────────┘
   └──────┬───────┘                   │                               │ ORM
          │ publish MQTT              │ lecture capteurs              │
          ▼                          (sensor_sim)                     │
   ┌──────────────┐      ┌────────────┴────────────┐                  │
   │     mqtt      │─────▶│   mqtt_worker (Django)  │──────────────────┘
   │  (Mosquitto)  │ sub  │   - ingestion mesures    │   INSERT mesures + alertes
   └──────────────┘      │   - détection de seuils  │
                         └─────────────────────────┘
```

- **mqtt** : broker Mosquitto (port 1883).
- **sensor_sim** : simulateur multi-capteurs, publie la télémétrie sur MQTT.
- **mqtt_worker** : consomme les messages MQTT, enregistre les mesures et crée les alertes de seuil.
- **web** : serveur Django (interface, API JSON, admin).

Voir la [documentation technique](docs/documentation_technique.md) pour le détail des flux.

## 5. Démarrage rapide

### Option A — Docker (recommandé, environnement complet)

Prérequis : Docker et Docker Compose installés.

```bash
# 1. Créer un fichier .env à la racine et le renseigner (voir section 6)

# 2. Construire et lancer les 4 services
docker compose up -d --build

# 3. (Première fois) appliquer les migrations et charger les données de démo
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo_data
docker compose exec web python manage.py createsuperuser
```

Application disponible sur **http://localhost:8000**.

### Option B — Local sans Docker (base SQLite)

Pour développer l'interface sans dépendre de PostgreSQL ni du broker MQTT :

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt

# On force les settings de développement (SQLite)
set DJANGO_SETTINGS_MODULE=config.settings_dev   # Windows (cmd)
# $env:DJANGO_SETTINGS_MODULE="config.settings_dev"   # Windows (PowerShell)

python manage.py migrate
python manage.py seed_demo_data
python manage.py runserver
```

> En mode local SQLite, il n'y a pas d'ingestion MQTT : on travaille sur les données
> de démonstration ou sur des mesures importées.

## 6. Variables d'environnement

Le projet lit sa configuration depuis un fichier **`.env`** à la racine
(via `python-decouple`). Modèle à recopier dans `.env` :

```env
# Django
DJANGO_SECRET_KEY=<chaîne aléatoire : python -c "import secrets; print(secrets.token_urlsafe(50))">
DEBUG=True

# PostgreSQL (Clever Cloud ou autre)
POSTGRES_DB=<nom_base>
POSTGRES_USER=<utilisateur>
POSTGRES_PASSWORD=<mot_de_passe>
POSTGRES_HOST=<hôte>
POSTGRES_PORT=<port>

# MQTT
MQTT_BROKER_HOST=mqtt
MQTT_BROKER_PORT=1883
MQTT_TOPIC=sensors/+/+/telemetry
```

> ⚠️ Le fichier `.env` contient des secrets : il ne doit **pas** être versionné.
> Voir la note de sécurité dans la [documentation technique](docs/documentation_technique.md#9-sécurité-et-bonnes-pratiques).

## 7. Commandes utiles

```bash
# Vérifier la configuration du projet
python manage.py check

# Lancer le worker d'ingestion MQTT
python manage.py mqtt_worker

# Analyser la dérive de tous les capteurs (une passe)
python manage.py analyse_derive

# Analyser en continu (toutes les 5 min) ou sur une fenêtre courte
python manage.py analyse_derive --continu
python manage.py analyse_derive --fenetre 2

# Charger le jeu de données de démonstration (sites, types, capteurs, seuils)
python manage.py seed_demo_data
```

Avec Docker, préfixer par `docker compose exec web `.

## 8. Structure du projet

```
projet-34-gestion-de-capteurs-intelligents/
├── apps/
│   ├── core/         # Référentiel : User, Site, TypeCapteur, Capteur, Seuil + CRUD
│   ├── ingestion/    # Mesure + worker MQTT (mqtt_client.py)
│   ├── alertes/      # Alerte + cycle de vie (acquitter / fermer)
│   └── analytics/    # DeriveDetectee, ModeleML + détection de dérive
├── config/           # settings.py (PostgreSQL), settings_dev.py (SQLite), urls.py
├── templates/        # Templates Django (Bootstrap)
├── static/           # CSS / JS
├── sensor_simulators/# Simulateur de capteurs (publie sur MQTT)
├── mqtt_broker/      # Configuration Mosquitto
├── docs/             # Documentation (specs, modèle de données, guides)
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── manage.py
```

## 9. Documentation

- 📘 [**Guide utilisateur**](docs/guide_utilisateur.md) — prise en main pas à pas de l'application.
- 🔧 [**Documentation technique**](docs/documentation_technique.md) — architecture, modèle de données, API, algorithmes.
- 📐 [Modèle de données](docs/03_modele_de_donnees.md) — conception détaillée (entités, relations, 3FN).
- 📄 Spécifications fonctionnelles et cahier des charges : dossier [`docs/`](docs/).

---

*Projet 34 — BUT3 GEII, IUT Lyon 1. Plateforme de gestion de capteurs intelligents.*
