# Guide utilisateur — Plateforme de gestion de capteurs intelligents

> Projet 34 — BUT3 GEII, IUT Lyon 1
> Ce guide explique comment utiliser l'application, page par page, sans connaissance
> technique préalable.

---

## Sommaire

1. [À qui s'adresse l'application](#1-à-qui-sadresse-lapplication)
2. [Se connecter et naviguer](#2-se-connecter-et-naviguer)
3. [Le tableau de bord (accueil)](#3-le-tableau-de-bord-accueil)
4. [Gérer les capteurs](#4-gérer-les-capteurs)
5. [Gérer les sites](#5-gérer-les-sites)
6. [Consulter l'historique des mesures](#6-consulter-lhistorique-des-mesures)
7. [Gérer les alertes](#7-gérer-les-alertes)
8. [Analyser la dérive des capteurs](#8-analyser-la-dérive-des-capteurs)
9. [L'interface d'administration](#9-linterface-dadministration)
10. [Questions fréquentes et dépannage](#10-questions-fréquentes-et-dépannage)

---

## 1. À qui s'adresse l'application

La plateforme couvre les besoins de plusieurs profils métier :

| Profil | Usage principal |
|---|---|
| **Ingénieur IoT** | Ajouter, configurer et retirer des capteurs ; définir les seuils d'alerte |
| **Technicien** | Surveiller les alertes, les acquitter, les clôturer après intervention |
| **Responsable infrastructure / Supervision** | Suivre l'état global du parc via le tableau de bord |
| **Data Scientist** | Analyser la dérive des capteurs et consulter l'historique des mesures |

## 2. Se connecter et naviguer

L'application est accessible à l'adresse fournie par votre administrateur
(par défaut **http://localhost:8000** en environnement de démonstration).

La **barre de navigation** en haut de chaque page donne accès aux sections principales :

- **Accueil** — tableau de bord
- **Capteurs** — liste et gestion des capteurs
- **Ajouter un capteur** — formulaire de création
- **Sites** — liste des sites
- **Alertes** — suivi des alertes
- **Dérives** — analyse de la dérive statistique
- **Admin** — interface d'administration (accès restreint)

## 3. Le tableau de bord (accueil)

La page d'accueil offre une vue synthétique du parc.

### Les trois indicateurs clés

- **Capteurs actifs** — nombre de capteurs en service.
- **Sites** — nombre de sites surveillés.
- **Alertes ouvertes** — passe au rouge dès qu'une alerte est ouverte (« Action requise »),
  reste au vert si tout est nominal.

### Le tableau « Système » en temps réel

Sous les indicateurs, un tableau liste les capteurs actifs avec, pour chacun :

- la **dernière valeur** mesurée,
- son **état** (badge coloré) :
  - 🟢 **OK** — valeur dans la plage normale,
  - 🟠 **Warning** (haut ou bas) — proche d'un seuil d'avertissement,
  - 🔴 **Critique** (haut ou bas) — seuil critique franchi,
  - ⚪ **Sans mesure / Inactif**.

> Ce tableau **se met à jour automatiquement toutes les 5 secondes**, sans recharger la
> page. Inutile d'appuyer sur F5.

Chaque ligne propose trois actions : **Voir** (fiche du capteur), **Hist.** (historique
des mesures) et **Modifier**.

## 4. Gérer les capteurs

### Consulter la liste

Menu **Capteurs**. La liste affiche tous les capteurs du parc avec leur identifiant,
leur nom, leur type et leur site.

### Consulter la fiche d'un capteur

Cliquez sur un capteur pour ouvrir sa **fiche détaillée**, qui présente :

- ses caractéristiques (site, type, identifiant, état actif/inactif, configuration),
- ses **seuils actifs**,
- ses **alertes ouvertes**,
- ses **20 dernières mesures** avec un indicateur de qualité.

### Ajouter un capteur

Menu **Ajouter un capteur**. Renseignez :

| Champ | Description |
|---|---|
| **Site** | Site d'installation (doit exister au préalable) |
| **Type de capteur** | Température, pression, vibration ou qualité de l'air |
| **Identifiant** | Identifiant unique utilisé dans les messages MQTT (ex. `TEMP-004`) |
| **Nom** | Libellé lisible |
| **Actif** | Coché = capteur en service |
| **Version firmware** | Optionnel |
| **Date d'installation** | Optionnel |
| **Configuration (JSON)** | Paramètres techniques, ex. `{}` par défaut |

Validez avec **Enregistrer**. Le capteur apparaît immédiatement dans la liste.

> L'identifiant doit être **unique** : c'est lui qui permet d'associer les messages MQTT
> reçus au bon capteur.

### Modifier un capteur

Bouton **Modifier** depuis la liste ou la fiche. Mêmes champs que la création.

### Supprimer un capteur

Bouton **Supprimer** puis confirmation. **Règle importante** : un capteur qui possède
déjà des mesures **ne peut pas être supprimé** (pour préserver l'historique). Dans ce cas,
décochez plutôt **Actif** pour le retirer du parc sans perdre ses données.

## 5. Gérer les sites

Menu **Sites**. La liste affiche chaque site avec le **nombre de capteurs** qui y sont
installés. Les sites se créent et se modifient via l'interface d'administration
(voir [section 9](#9-linterface-dadministration)).

## 6. Consulter l'historique des mesures

Menu **Capteurs → Hist.**, ou directement via l'URL `/historique/`.

1. Choisissez un **capteur** dans la liste déroulante.
2. Choisissez une **période** : dernière heure, 6 h, 24 h, 7 jours, 30 jours, ou une
   **période personnalisée** (dates et heures de début/fin).
3. Cliquez sur **Charger**.

Un **graphique interactif** affiche l'évolution de la valeur sur la période :

- survolez la courbe pour lire la valeur exacte à un instant donné ;
- **cliquez sur un point** pour afficher son détail (date, valeur, qualité) dans les
  cartes situées sous le graphique.

> Le graphique est limité aux 1000 mesures les plus récentes de la période, pour rester
> fluide.

## 7. Gérer les alertes

Menu **Alertes**. Une alerte est un événement déclenché soit par un **dépassement de
seuil**, soit par une **dérive statistique**.

### Comprendre une alerte

Chaque ligne indique :

- le **niveau** : 🔵 Info, 🟠 Warning, 🔴 Critique ;
- le **capteur** concerné ;
- le **type** : dépassement de seuil, dérive, communication, batterie ;
- la **valeur déclenchante** ;
- la **date de déclenchement** ;
- le **statut**.

### Filtrer les alertes

Les boutons en haut permettent de filtrer par statut : **Toutes**, **Ouvertes**,
**Acquittées**, **Fermées**.

### Le cycle de vie d'une alerte

```
   Ouverte  ──►  Acquittée  ──►  Fermée
      │                            ▲
      └──────────── (fermeture directe) ──────────┘
```

1. **Ouverte** — l'alerte vient d'être créée automatiquement par le système.
2. **Acquitter** — le technicien prend connaissance de l'alerte. Bouton **Acquitter** :
   une page de confirmation permet d'ajouter un **commentaire** (cause, action prévue).
   L'heure d'acquittement est enregistrée.
3. **Fermer** — le problème est résolu. Bouton **Fermer** (disponible pour une alerte
   ouverte ou acquittée). L'**heure de clôture** est enregistrée, ce qui permet de
   calculer la durée de l'incident.

Une alerte **fermée** n'a plus d'action possible : elle reste consultable dans
l'historique (filtre **Fermées**).

## 8. Analyser la dérive des capteurs

Menu **Dérives** (`/analytics/derives/`).

### Qu'est-ce qu'une dérive ?

Une **dérive** est une **évolution lente et progressive** d'un capteur qui s'écarte de sa
valeur normale, **sans dépassement ponctuel d'un seuil**. Elle révèle généralement un
**besoin de calibration** ou un **vieillissement** du capteur. C'est différent d'un pic
isolé : la dérive est une *tendance* qui dure.

### Lancer une analyse

Bouton **« Lancer l'analyse maintenant »** en haut de la page. Le système analyse tous
les capteurs actifs et affiche un message récapitulatif (capteurs analysés, alertes
créées). L'analyse peut aussi être déclenchée côté serveur par la commande
`python manage.py analyse_derive`.

### Lire les résultats

Sélectionnez un capteur, puis cliquez sur **Afficher**. La page présente :

- un **graphique du score de dérive** sur les 30 derniers jours, avec :
  - une **ligne orange** = seuil *warning* (2,0),
  - une **ligne rouge** = seuil *critique* (3,5) ;
- un **tableau des dernières détections** : date, score (avec badge coloré), moyenne de
  référence, bruit (écart-type), taille de fenêtre, et le lien vers l'alerte éventuelle.

**Interprétation du score :**

| Score | Signification |
|---|---|
| < 2,0 | Comportement normal |
| 2,0 – 3,5 | Dérive modérée (à surveiller) |
| ≥ 3,5 | Dérive critique → une **alerte de dérive** est automatiquement créée |

### Bien régler la fenêtre d'analyse

Par défaut, l'analyse porte sur une **fenêtre de 24 h** : elle ne détecte donc que les
tendances **longues**. Pour réagir plus vite à une tendance récente (ou pour une
démonstration courte), utilisez une fenêtre plus petite :

```bash
python manage.py analyse_derive --fenetre 2
```

> Fenêtre courte = détecte vite les tendances récentes (mais plus sensible aux
> fluctuations) ; fenêtre longue = ne signale que les vraies dérives lentes.

## 9. L'interface d'administration

Menu **Admin** (`/admin/`). Réservée aux comptes administrateurs, elle permet de gérer
**toutes les entités** directement : utilisateurs, sites, types de capteurs, capteurs,
seuils, mesures, alertes, dérives détectées et modèles ML.

C'est notamment l'endroit pour :

- **créer ou modifier un site** ;
- **définir les seuils** d'un capteur (bas critique, bas warning, haut warning, haut critique) ;
- consulter en détail les **mesures** et **détections de dérive**.

Un compte administrateur se crée avec `python manage.py createsuperuser`.

## 10. Questions fréquentes et dépannage

**La page « Dérives » est vide.**
C'est normal tant qu'aucune analyse n'a été lancée : la page liste les *détections*, pas
les mesures. Cliquez sur **« Lancer l'analyse maintenant »** (il faut que les capteurs
aient déjà des mesures en base).

**Le tableau de bord ne se met pas à jour.**
Le rafraîchissement automatique nécessite que le navigateur autorise les requêtes vers le
serveur. Vérifiez votre connexion ; rechargez la page une fois.

**Une page affiche « too many connections » / la page ne répond pas.**
La base de données partagée a une limite de connexions simultanées. Fermez les onglets
inutiles (notamment le tableau de bord qui se rafraîchit en continu), attendez une minute,
puis réessayez. En environnement de démonstration, évitez de lancer plusieurs instances de
l'application en même temps.

**Je n'arrive pas à supprimer un capteur.**
Un capteur qui possède des mesures est protégé contre la suppression. Décochez **Actif**
pour le retirer du parc tout en conservant son historique.

**Comment voir une dérive se déclencher en démonstration ?**
La dérive est simulée sur le capteur **TEMP-003**. Laissez le simulateur tourner, puis
relancez l'analyse régulièrement : le score de TEMP-003 monte progressivement tandis que
les autres capteurs (témoins) restent bas.

---

*Projet 34 — BUT3 GEII, IUT Lyon 1. Guide utilisateur de la plateforme de gestion de capteurs intelligents.*
