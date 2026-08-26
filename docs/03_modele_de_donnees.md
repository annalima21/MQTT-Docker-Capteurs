# Modèle de données

**Projet** : Plateforme de gestion de capteurs intelligents
**Livrable** : J1+J2 — séance 7
**Version** : 1.0
**Date** : 2026-04-20
**Auteur (partie modèle de données)** : Badice
**SGBD cible** : PostgreSQL 16

---

## 1. Démarche de modélisation

La conception du modèle de données a suivi la démarche en 7 étapes recommandée dans le guide de modélisation :

```
1. Analyse fonctionnelle
   ↓
2. Identification des entités
   ↓
3. Identification des attributs
   ↓
4. Identification des relations
   ↓
5. Normalisation (3FN)
   ↓
6. Diagramme ERD
   ↓
7. Modèles Django
```

**Entrée** : les spécifications fonctionnelles (`01_specifications_fonctionnelles.md`) et l'architecture technique (`02_architecture_technique.md`).

**Sortie** : un modèle relationnel en 3e forme normale, traduit en modèles Django prêts à être implémentés.

**Choix structurants justifiés dans ce document** :

- Séparation référentiel (Site, TypeCapteur, Capteur, Seuil) et flux événementiel (Mesure, Alerte, DeriveDetectee).
- Usage ponctuel du type `JSON` pour deux champs techniques (`config_json`, `meta_json`), tout le reste en colonnes typées.
- Suppression logique (champ `actif`) plutôt que physique pour le Capteur, afin de préserver l'historique des mesures.

---

## 2. Identification des entités

### 2.1 Méthode

À partir des spécifications fonctionnelles, les substantifs importants ont été extraits : *capteur, site, type (de capteur), mesure, seuil, alerte, utilisateur, configuration, modèle ML, firmware, dérive*.

Chaque candidat a été validé par les trois questions :

- **Q1** : a-t-il plusieurs occurrences ?
- **Q2** : a-t-il des propriétés propres ?
- **Q3** : est-il indépendant, ou bien faut-il le rattacher à une autre entité (entité faible) ?

### 2.2 Tableau de validation

| Candidat | Q1 plusieurs ? | Q2 propriétés ? | Q3 indépendant ? | Verdict |
|---|---|---|---|---|
| **Site** | Oui | Oui | Oui |  Entité |
| **TypeCapteur** | Oui | Oui | Oui |  Entité |
| **Capteur** | Oui | Oui | Oui |  Entité |
| **Seuil** | Oui | Oui | Non, lié à un Capteur |  Entité faible |
| **Mesure** | Oui | Oui | Non, lié à un Capteur |  Entité faible |
| **Alerte** | Oui | Oui | Non, lié à un Capteur |  Entité faible |
| **DeriveDetectee** | Oui | Oui | Non, lié à un Capteur |  Entité faible |
| **ModeleML** | Oui | Oui | Oui |  Entité |
| **Utilisateur** | Oui | Oui | Oui |  Entité (fournie par Django) |
| Configuration | Quelques-unes par capteur | Quelques-unes | Dépend du Capteur |  Devient un attribut `config_json` |
| Firmware | Non (c'est un numéro de version) | Non | Non |  Devient un attribut du Capteur |

### 2.3 Entités retenues

La base comportera **9 entités métier** (+ `User` fourni par Django) :

| # | Entité | Nature | Owner de l'app Django |
|---|---|---|---|
| 1 | Site | Référentiel | `core` |
| 2 | TypeCapteur | Référentiel | `core` |
| 3 | Capteur | Référentiel | `core` |
| 4 | Seuil | Référentiel (faible) | `core` |
| 5 | Mesure | Flux événementiel (faible) | `ingestion` |
| 6 | Alerte | Flux événementiel (faible) | `alertes` |
| 7 | DeriveDetectee | Flux événementiel (faible) | `analytics` |
| 8 | ModeleML | Artefact | `analytics` |
| 9 | User | Authentification | `auth` (Django natif) |

### 2.4 Justifications des choix

- **Site séparé du Capteur** : un site accueille plusieurs capteurs (relation 1-N). Fusionner les deux en un seul champ texte "lieu" sur le Capteur entraînerait une duplication massive (toutes les infos du site répétées sur chaque capteur) et rendrait impossible l'agrégation par site.
- **TypeCapteur séparé du Capteur** : un type définit des règles communes (unité SI, plage de validité). Plusieurs capteurs partagent un même type. Répéter ces règles sur chaque capteur créerait une redondance et des incohérences possibles (un type de capteur avec deux unités différentes selon le capteur).
- **Seuil séparé du Capteur** : un capteur possède jusqu'à 4 seuils (`bas_critique`, `bas_warning`, `haut_warning`, `haut_critique`). Créer 4 colonnes dédiées sur le Capteur marcherait mais :
  - ne permet pas d'ajouter de nouveaux types de seuils sans modifier le schéma ;
  - complique l'historisation future des changements de seuils.
- **Configuration n'est pas une entité** : les paramètres de configuration (fréquence d'émission, mode sleep, etc.) sont regroupés dans un champ `config_json` sur le Capteur. Cela se justifie parce que ces paramètres n'existent pas indépendamment du capteur et n'ont pas besoin d'être requêtés individuellement.
- **AlerteEvenement (journal d'actions) écartée** : pour rester simple au niveau BUT3, les commentaires d'acquittement sont stockés dans un champ `commentaire` sur `Alerte`. En production, on passerait à une table journal dédiée.

---

## 3. Identification des attributs

Pour chaque entité retenue, on liste les attributs en les classant par nature (simple / technique / relation). Les attributs calculables (durée entre deux dates par exemple) ne sont PAS stockés : ils sont reconstitués dans le code.

### 3.1 Entité `Site`

| Attribut | Nature | Type | Obligatoire | Description |
|---|---|---|---|---|
| `id` | Clé primaire | Auto (BigInt) | Oui | Identifiant technique (généré par Django). |
| `nom` | Simple | VARCHAR(128) | Oui | Nom lisible du site. Unique. |
| `latitude` | Simple | DOUBLE PRECISION | Non | Latitude WGS84. |
| `longitude` | Simple | DOUBLE PRECISION | Non | Longitude WGS84. |
| `adresse` | Simple | VARCHAR(255) | Non | Adresse textuelle optionnelle. |
| `created_at` | Technique | DATETIME | Oui | Date de création auto. |

### 3.2 Entité `TypeCapteur`

| Attribut | Nature | Type | Obligatoire | Description |
|---|---|---|---|---|
| `id` | Clé primaire | Auto (BigInt) | Oui | |
| `code` | Simple | VARCHAR(32) | Oui | Code court unique : `temperature`, `pression`, `vibration`, `qualite_air`. |
| `libelle` | Simple | VARCHAR(128) | Oui | Libellé affichable en français. |
| `unite_si` | Simple | VARCHAR(16) | Oui | Unité SI (°C, Pa, m/s², ppm). |
| `plage_min` | Simple | DOUBLE PRECISION | Non | Plage technique min du type de capteur. |
| `plage_max` | Simple | DOUBLE PRECISION | Non | Plage technique max. |

### 3.3 Entité `Capteur`

| Attribut | Nature | Type | Obligatoire | Description |
|---|---|---|---|---|
| `id` | Clé primaire | Auto (BigInt) | Oui | |
| `site` | Relation | FK → Site | Oui | Site d'installation. |
| `type` | Relation | FK → TypeCapteur | Oui | Type de capteur. |
| `identifiant` | Simple | VARCHAR(64) | Oui | Identifiant externe unique utilisé dans les topics MQTT (ex : `TEMP-001`). |
| `nom` | Simple | VARCHAR(128) | Oui | Libellé humain. |
| `actif` | Simple | BOOLEAN | Oui | Suppression logique (`False` = retiré du parc, historique conservé). |
| `config_json` | Technique | JSON | Oui | Paramètres courants (fréquence émission, mode sleep). `{}` par défaut. |
| `firmware_version` | Simple | VARCHAR(32) | Non | Version firmware déclarée par le capteur. |
| `date_installation` | Simple | DATE | Non | Date de mise en service. |
| `date_derniere_calibration` | Simple | DATETIME | Non | Dernière calibration effective. |
| `created_at` | Technique | DATETIME | Oui | |
| `updated_at` | Technique | DATETIME | Oui | Auto-maintenu. |

### 3.4 Entité `Seuil`

| Attribut | Nature | Type | Obligatoire | Description |
|---|---|---|---|---|
| `id` | Clé primaire | Auto (BigInt) | Oui | |
| `capteur` | Relation | FK → Capteur | Oui | |
| `type_seuil` | Simple | VARCHAR(16) | Oui | Parmi `bas_critique`, `bas_warning`, `haut_warning`, `haut_critique`. |
| `valeur` | Simple | DOUBLE PRECISION | Oui | Valeur du seuil exprimée dans l'unité SI du type de capteur. |
| `actif` | Simple | BOOLEAN | Oui | Permet de désactiver temporairement un seuil sans le supprimer. |

Contrainte unique : un capteur ne peut avoir qu'un seul seuil de chaque type.

### 3.5 Entité `Mesure`

| Attribut | Nature | Type | Obligatoire | Description |
|---|---|---|---|---|
| `id` | Clé primaire | Auto (BigInt) | Oui | |
| `capteur` | Relation | FK → Capteur | Oui | |
| `timestamp` | Simple | DATETIME (précision ms) | Oui | Horodatage de la mesure. |
| `valeur` | Simple | DOUBLE PRECISION | Oui | Grandeur mesurée. |
| `qualite` | Simple | DOUBLE PRECISION | Oui | Qualité de la mesure ∈ [0, 1]. |
| `anomalie_score` | Simple | DOUBLE PRECISION | Non | Sortie du modèle TFLite si disponible ∈ [0, 1]. |
| `meta_json` | Technique | JSON | Oui | Métadonnées (batterie, rssi, firmware). `{}` par défaut. |

### 3.6 Entité `Alerte`

| Attribut | Nature | Type | Obligatoire | Description |
|---|---|---|---|---|
| `id` | Clé primaire | Auto (BigInt) | Oui | |
| `capteur` | Relation | FK → Capteur | Oui | |
| `seuil` | Relation | FK → Seuil | Non | NULL pour les alertes de dérive (pas de seuil franchi). |
| `timestamp_declenchement` | Simple | DATETIME | Oui | |
| `timestamp_cloture` | Simple | DATETIME | Non | Renseignée à la clôture. |
| `niveau` | Simple | VARCHAR(16) | Oui | `info`, `warning`, `critique`. |
| `type_alerte` | Simple | VARCHAR(32) | Oui | `seuil`, `derive`, `communication`, `batterie`. |
| `valeur_declenchante` | Simple | DOUBLE PRECISION | Non | Valeur qui a déclenché (ou NULL pour dérive). |
| `statut` | Simple | VARCHAR(16) | Oui | `ouverte`, `acquittee`, `fermee`. |
| `acquittement_user` | Relation | FK → User | Non | Utilisateur ayant acquitté. |
| `acquittement_at` | Simple | DATETIME | Non | Timestamp d'acquittement. |
| `commentaire` | Simple | TEXT | Non | Commentaire libre laissé par le technicien. |

### 3.7 Entité `DeriveDetectee` (ambition S1)

| Attribut | Nature | Type | Obligatoire | Description |
|---|---|---|---|---|
| `id` | Clé primaire | Auto (BigInt) | Oui | |
| `capteur` | Relation | FK → Capteur | Oui | |
| `timestamp` | Simple | DATETIME | Oui | Moment de l'analyse. |
| `score` | Simple | DOUBLE PRECISION | Oui | Indicateur de dérive (écart normé à la moyenne glissante). |
| `moyenne_ref` | Simple | DOUBLE PRECISION | Oui | Moyenne sur la fenêtre d'analyse. |
| `ecart_type_ref` | Simple | DOUBLE PRECISION | Oui | Écart-type sur la fenêtre. |
| `fenetre_heures` | Simple | INT | Oui | Taille de la fenêtre en heures (ex. 24). |
| `alerte` | Relation | FK → Alerte | Non | Alerte éventuellement levée à partir de cette détection. |

### 3.8 Entité `ModeleML` (ambition S3)

| Attribut | Nature | Type | Obligatoire | Description |
|---|---|---|---|---|
| `id` | Clé primaire | Auto (BigInt) | Oui | |
| `nom` | Simple | VARCHAR(128) | Oui | Nom logique du modèle. |
| `version` | Simple | VARCHAR(32) | Oui | Convention semver (ex. `1.0.3`). |
| `fichier_tflite` | Simple | FileField | Oui | Fichier binaire stocké sur un volume dédié. |
| `taille_octets` | Simple | INT | Oui | Contrôlée pour rester < 100 KB. |
| `metriques_json` | Technique | JSON | Oui | Précision, rappel, F1, etc. |
| `actif` | Simple | BOOLEAN | Oui | Modèle actif ou archivé. |
| `created_by` | Relation | FK → User | Non | Data scientist auteur. |
| `created_at` | Technique | DATETIME | Oui | |

Contrainte unique : (`nom`, `version`).

---

## 4. Identification des relations

### 4.1 Vue synthétique des relations

| Relation | Cardinalité | Justification |
|---|---|---|
| Site — Capteur | (1,1) ↔ (0,N) | Un site accueille 0 à N capteurs ; un capteur est installé sur exactement 1 site. |
| TypeCapteur — Capteur | (1,1) ↔ (0,N) | Un type est partagé par plusieurs capteurs ; un capteur a exactement 1 type. |
| Capteur — Seuil | (1,1) ↔ (0,N) | Un capteur peut avoir 0 à 4 seuils (un par type de seuil) ; un seuil appartient à 1 seul capteur. |
| Capteur — Mesure | (1,1) ↔ (0,N) | Un capteur émet 0 à N mesures ; une mesure provient d'un seul capteur. |
| Capteur — Alerte | (1,1) ↔ (0,N) | Un capteur peut avoir plusieurs alertes dans le temps ; une alerte concerne exactement 1 capteur. |
| Seuil — Alerte | (0,1) ↔ (0,N) | Une alerte de dépassement référence le seuil franchi ; une alerte de dérive n'a pas de seuil (FK nullable). |
| User — Alerte (acquittement) | (0,1) ↔ (0,N) | Un utilisateur peut acquitter plusieurs alertes ; une alerte a au plus un auteur d'acquittement. |
| Capteur — DeriveDetectee | (1,1) ↔ (0,N) | Un capteur produit plusieurs détections dans le temps. |
| DeriveDetectee — Alerte | (0,1) ↔ (0,1) | Une détection peut lever une alerte ; une alerte de dérive vient d'une détection. |
| User — ModeleML | (0,1) ↔ (0,N) | Un utilisateur peut créer plusieurs modèles. |

### 4.2 Aucune relation N-N

Le modèle ne comporte **aucune relation Many-to-Many**. Toutes les associations sont 1-N (ou 1-1 pour DeriveDetectee ↔ Alerte).

**Pourquoi c'est un bon signe** : les relations N-N sont plus complexes à implémenter (table de liaison) et plus coûteuses à requêter. Leur absence dans ce modèle reflète le domaine : un capteur ne peut pas être partagé entre sites, une mesure ne peut pas venir de plusieurs capteurs, etc.

### 4.3 Comportement `ON DELETE`

| Lien | Comportement | Raison |
|---|---|---|
| Site → Capteur | RESTRICT | Interdit de supprimer un site qui a encore des capteurs. Évite les capteurs orphelins. |
| TypeCapteur → Capteur | RESTRICT | Idem. |
| Capteur → Seuil | CASCADE | Si un capteur est supprimé, ses seuils n'ont plus de sens. |
| Capteur → Mesure | CASCADE | Si un capteur est supprimé, ses mesures sont purgées. En pratique on fera de la suppression logique (`actif=False`) pour préserver l'historique. |
| Capteur → Alerte | CASCADE | Idem. |
| Seuil → Alerte | SET NULL | Si un seuil est modifié/supprimé, on garde l'alerte mais on perd le lien au seuil. |
| User → Alerte.acquittement_user | SET NULL | Si un utilisateur est supprimé, l'alerte reste mais sans auteur d'acquittement. |
| User → ModeleML.created_by | SET NULL | Idem. |

---

## 5. Normalisation

Le modèle est en **3e forme normale (3FN)**. Vérification étape par étape :

### 5.1 1FN — Atomicité

**Règle** : tous les attributs sont atomiques (indivisibles).

- Aucune liste ou énumération stockée dans une colonne (pas de champ "techniciens : Jean, Marc, Sophie").
- Les champs `config_json` et `meta_json` sont des JSON, ce qui pourrait être considéré comme une violation stricte. **Justification acceptée** : ces champs contiennent des paires clé-valeur techniques (batterie, rssi, firmware) dont le nombre et le nom ne sont pas fixes. Les stocker en colonnes dédiées créerait un schéma rigide difficile à faire évoluer. Cette exception est courante dans les bases modernes et restreinte à 2 champs bien identifiés.

 **1FN respectée.**

### 5.2 2FN — Dépendance complète

**Règle** : 1FN + chaque attribut non-clé dépend de la totalité de la clé primaire.

Toutes les tables ont une clé primaire simple (`id` auto-incrémenté), donc la 2FN est automatiquement respectée. On n'a pas de clé composite.

 **2FN respectée.**

### 5.3 3FN — Pas de dépendance transitive

**Règle** : 2FN + aucun attribut non-clé ne dépend d'un autre attribut non-clé.

Vérification par table :

- **Capteur** : ne stocke **pas** le nom du site ni le libellé du type de capteur. Ces informations sont récupérées via les FK. 
- **Mesure** : ne stocke **pas** le nom du capteur ni l'unité SI. Passage par FK. 
- **Alerte** : ne duplique **pas** le seuil franchi (référencé par FK), ni les infos du capteur.
- **DeriveDetectee** : ne stocke **pas** le nom du capteur. 

Aucun champ dérivé n'est stocké (pas d'`age`, pas de `duree_minutes`, pas de `nom_complet`). Les valeurs calculables sont reconstituées dans le code Python (méthodes de modèle ou propriétés).

 **3FN respectée.**

### 5.4 Exceptions assumées

- **`taille_octets`** sur `ModeleML` est calculable à partir du fichier. Elle est stockée pour pouvoir la contrôler par contrainte SQL (`CHECK <= 102400`) et éviter de lire le fichier à chaque vérification.
- **`firmware_version`** sur `Capteur` est déclaratif : c'est la version annoncée par le capteur dans ses messages. Pas un calcul, pas de dépendance transitive.

---

## 6. Diagramme entité-relation (ERD)

### 6.1 Syntaxe dbdiagram.io

Le diagramme suivant peut être collé sur [dbdiagram.io](https://dbdiagram.io) pour générer le schéma visuel exploitable dans le livrable final.

```
Table Site {
  id int [pk, increment]
  nom varchar(128) [unique, not null]
  latitude double
  longitude double
  adresse varchar(255)
  created_at datetime [not null]
}

Table TypeCapteur {
  id int [pk, increment]
  code varchar(32) [unique, not null]
  libelle varchar(128) [not null]
  unite_si varchar(16) [not null]
  plage_min double
  plage_max double
}

Table Capteur {
  id int [pk, increment]
  site_id int [ref: > Site.id, not null]
  type_id int [ref: > TypeCapteur.id, not null]
  identifiant varchar(64) [unique, not null]
  nom varchar(128) [not null]
  actif boolean [not null, default: true]
  config_json json [not null]
  firmware_version varchar(32)
  date_installation date
  date_derniere_calibration datetime
  created_at datetime [not null]
  updated_at datetime [not null]
}

Table Seuil {
  id int [pk, increment]
  capteur_id int [ref: > Capteur.id, not null]
  type_seuil varchar(16) [not null]
  valeur double [not null]
  actif boolean [not null, default: true]

  indexes {
    (capteur_id, type_seuil) [unique]
  }
}

Table Mesure {
  id int [pk, increment]
  capteur_id int [ref: > Capteur.id, not null]
  timestamp datetime [not null]
  valeur double [not null]
  qualite double [not null]
  anomalie_score double
  meta_json json [not null]

  indexes {
    (capteur_id, timestamp) [name: 'idx_mesure_capteur_ts']
  }
}

Table Alerte {
  id int [pk, increment]
  capteur_id int [ref: > Capteur.id, not null]
  seuil_id int [ref: > Seuil.id]
  timestamp_declenchement datetime [not null]
  timestamp_cloture datetime
  niveau varchar(16) [not null]
  type_alerte varchar(32) [not null]
  valeur_declenchante double
  statut varchar(16) [not null]
  acquittement_user_id int [ref: > User.id]
  acquittement_at datetime
  commentaire text
}

Table DeriveDetectee {
  id int [pk, increment]
  capteur_id int [ref: > Capteur.id, not null]
  timestamp datetime [not null]
  score double [not null]
  moyenne_ref double [not null]
  ecart_type_ref double [not null]
  fenetre_heures int [not null]
  alerte_id int [ref: > Alerte.id]
}

Table ModeleML {
  id int [pk, increment]
  nom varchar(128) [not null]
  version varchar(32) [not null]
  fichier_tflite varchar(512) [not null]
  taille_octets int [not null]
  metriques_json json [not null]
  actif boolean [not null, default: false]
  created_by_id int [ref: > User.id]
  created_at datetime [not null]

  indexes {
    (nom, version) [unique]
  }
}

Table User {
  id int [pk, increment]
  username varchar(150) [unique, not null]
  email varchar(254)
  is_active boolean [not null]
}
```

### 6.2 Vue schématique ASCII (résumé)

```
              ┌─────────────┐
              │    Site     │
              └──────┬──────┘
                     │ 1
                     │
                     │ N
┌─────────────┐     ┌▼────────────┐     ┌──────────────┐
│ TypeCapteur │────►│   Capteur   │◄────│    Seuil     │
└─────────────┘  1  └──────┬──────┘  N  └──────────────┘
                   N       │           1
                           │
            ┌──────────────┼──────────────┐
            │              │              │
         1  │ N         1  │ N         1  │ N
            ▼              ▼              ▼
      ┌─────────┐   ┌───────────┐   ┌────────────────┐
      │ Mesure  │   │  Alerte   │   │ DeriveDetectee │
      └─────────┘   └─────┬─────┘   └────────┬───────┘
                          │                  │
                          │◄─────────────────┘ (0,1)
                          │
                          │ N (acquittement)
                          │ 0,1
                    ┌─────▼─────┐
                    │   User    │
                    └─────┬─────┘
                          │ 1
                          │ 0,N (created_by)
                          ▼
                    ┌───────────┐
                    │ ModeleML  │
                    └───────────┘
```

### 6.3 Convention utilisée

Notation Crow's Foot (patte de corbeau) : `||` pour exactement un, `|{` pour zéro ou plusieurs, `|o` pour zéro ou un.

---

## 7. Traduction en modèles Django

Les modèles sont répartis en 3 apps Django : `core`, `ingestion`, `alertes`, `analytics`. Chaque app a son `models.py` dédié. L'utilisateur est géré par `django.contrib.auth`.

### 7.1 App `core` — référentiel

```python
# core/models.py
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class Site(models.Model):
    """Site géographique accueillant des capteurs."""

    nom = models.CharField(
        max_length=128,
        unique=True,
        verbose_name="Nom du site",
    )
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    adresse = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Site"
        verbose_name_plural = "Sites"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class TypeCapteur(models.Model):
    """Catégorie de capteur avec ses caractéristiques communes."""

    CODE_CHOICES = [
        ("temperature", "Température"),
        ("pression", "Pression"),
        ("vibration", "Vibration"),
        ("qualite_air", "Qualité de l'air"),
    ]

    code = models.CharField(max_length=32, choices=CODE_CHOICES, unique=True)
    libelle = models.CharField(max_length=128)
    unite_si = models.CharField(max_length=16, help_text="Unité SI (°C, Pa, m/s², ppm)")
    plage_min = models.FloatField(null=True, blank=True)
    plage_max = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = "Type de capteur"
        verbose_name_plural = "Types de capteurs"

    def __str__(self):
        return f"{self.libelle} ({self.unite_si})"


class Capteur(models.Model):
    """Capteur individuel installé sur un site."""

    site = models.ForeignKey(
        Site,
        on_delete=models.RESTRICT,
        related_name="capteurs",
    )
    type = models.ForeignKey(
        TypeCapteur,
        on_delete=models.RESTRICT,
        related_name="capteurs",
    )
    identifiant = models.CharField(
        max_length=64,
        unique=True,
        help_text="Identifiant externe utilisé dans les topics MQTT",
    )
    nom = models.CharField(max_length=128)
    actif = models.BooleanField(default=True)
    config_json = models.JSONField(
        default=dict,
        help_text="Configuration courante (fréquence, seuils, modes)",
    )
    firmware_version = models.CharField(max_length=32, null=True, blank=True)
    date_installation = models.DateField(null=True, blank=True)
    date_derniere_calibration = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Capteur"
        verbose_name_plural = "Capteurs"
        ordering = ["identifiant"]
        indexes = [
            models.Index(fields=["site", "actif"]),
            models.Index(fields=["type"]),
        ]

    def __str__(self):
        return f"{self.identifiant} — {self.nom}"

    @property
    def derniere_mesure(self):
        """Retourne la dernière mesure (None si aucune)."""
        return self.mesures.order_by("-timestamp").first()


class Seuil(models.Model):
    """Valeur limite associée à un capteur, qui déclenche une alerte si franchie."""

    TYPE_CHOICES = [
        ("bas_critique", "Bas critique"),
        ("bas_warning", "Bas warning"),
        ("haut_warning", "Haut warning"),
        ("haut_critique", "Haut critique"),
    ]

    capteur = models.ForeignKey(
        Capteur,
        on_delete=models.CASCADE,
        related_name="seuils",
    )
    type_seuil = models.CharField(max_length=16, choices=TYPE_CHOICES)
    valeur = models.FloatField()
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Seuil"
        verbose_name_plural = "Seuils"
        constraints = [
            models.UniqueConstraint(
                fields=["capteur", "type_seuil"],
                name="seuil_unique_par_capteur_et_type",
            ),
        ]

    def __str__(self):
        return f"{self.capteur.identifiant} / {self.get_type_seuil_display()} = {self.valeur}"
```

### 7.2 App `ingestion` — flux de mesures

```python
# ingestion/models.py
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

from core.models import Capteur


class Mesure(models.Model):
    """Valeur relevée par un capteur à un instant donné."""

    capteur = models.ForeignKey(
        Capteur,
        on_delete=models.CASCADE,
        related_name="mesures",
    )
    timestamp = models.DateTimeField(db_index=True)
    valeur = models.FloatField()
    qualite = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        default=1.0,
    )
    anomalie_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Score d'anomalie issu du modèle TFLite (si disponible)",
    )
    meta_json = models.JSONField(default=dict)

    class Meta:
        verbose_name = "Mesure"
        verbose_name_plural = "Mesures"
        ordering = ["-timestamp"]
        indexes = [
            # Index composite pour la requête « historique d'un capteur »
            models.Index(fields=["capteur", "-timestamp"], name="idx_mesure_capteur_ts"),
        ]

    def __str__(self):
        return f"{self.capteur.identifiant} @ {self.timestamp:%Y-%m-%d %H:%M:%S} = {self.valeur}"
```

### 7.3 App `alertes` — détection et suivi

```python
# alertes/models.py
from django.conf import settings
from django.db import models

from core.models import Capteur, Seuil


class Alerte(models.Model):
    """Événement d'alerte sur un capteur (dépassement de seuil ou dérive)."""

    NIVEAU_CHOICES = [
        ("info", "Info"),
        ("warning", "Warning"),
        ("critique", "Critique"),
    ]

    TYPE_CHOICES = [
        ("seuil", "Dépassement de seuil"),
        ("derive", "Dérive statistique"),
        ("communication", "Perte de communication"),
        ("batterie", "Batterie faible"),
    ]

    STATUT_CHOICES = [
        ("ouverte", "Ouverte"),
        ("acquittee", "Acquittée"),
        ("fermee", "Fermée"),
    ]

    capteur = models.ForeignKey(
        Capteur,
        on_delete=models.CASCADE,
        related_name="alertes",
    )
    seuil = models.ForeignKey(
        Seuil,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alertes",
    )
    timestamp_declenchement = models.DateTimeField()
    timestamp_cloture = models.DateTimeField(null=True, blank=True)
    niveau = models.CharField(max_length=16, choices=NIVEAU_CHOICES)
    type_alerte = models.CharField(max_length=32, choices=TYPE_CHOICES)
    valeur_declenchante = models.FloatField(null=True, blank=True)
    statut = models.CharField(
        max_length=16, choices=STATUT_CHOICES, default="ouverte"
    )
    acquittement_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alertes_acquittees",
    )
    acquittement_at = models.DateTimeField(null=True, blank=True)
    commentaire = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = "Alerte"
        verbose_name_plural = "Alertes"
        ordering = ["-timestamp_declenchement"]
        indexes = [
            models.Index(fields=["capteur", "statut"]),
            models.Index(fields=["-timestamp_declenchement"]),
        ]

    def __str__(self):
        return f"{self.get_niveau_display()} / {self.capteur.identifiant} ({self.statut})"
```

### 7.4 App `analytics` — dérive et modèles ML

```python
# analytics/models.py
from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models

from alertes.models import Alerte
from core.models import Capteur


class DeriveDetectee(models.Model):
    """Détection statistique de dérive sur les mesures d'un capteur."""

    capteur = models.ForeignKey(
        Capteur,
        on_delete=models.CASCADE,
        related_name="derives",
    )
    timestamp = models.DateTimeField()
    score = models.FloatField(help_text="Écart normé à la moyenne glissante")
    moyenne_ref = models.FloatField()
    ecart_type_ref = models.FloatField()
    fenetre_heures = models.IntegerField(default=24)
    alerte = models.ForeignKey(
        Alerte,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derives",
    )

    class Meta:
        verbose_name = "Dérive détectée"
        verbose_name_plural = "Dérives détectées"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["capteur", "-timestamp"]),
        ]

    def __str__(self):
        return f"Dérive {self.capteur.identifiant} @ {self.timestamp} (score={self.score:.2f})"


class ModeleML(models.Model):
    """Modèle TensorFlow Lite uploadé pour inférence edge."""

    nom = models.CharField(max_length=128)
    version = models.CharField(max_length=32, help_text="Convention semver")
    fichier_tflite = models.FileField(upload_to="modeles/")
    taille_octets = models.IntegerField(
        validators=[MaxValueValidator(102400)],  # 100 KB
        help_text="Taille du fichier (contrainte métier < 100 KB)",
    )
    metriques_json = models.JSONField(
        default=dict,
        help_text="Accuracy, precision, recall, F1, etc.",
    )
    actif = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modeles",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Modèle ML"
        verbose_name_plural = "Modèles ML"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["nom", "version"],
                name="modele_unique_par_nom_version",
            ),
        ]

    def __str__(self):
        return f"{self.nom} v{self.version} ({'actif' if self.actif else 'archivé'})"
```

---

## 8. Contraintes et validation

### 8.1 Contraintes au niveau base

- **UNIQUE** : `Site.nom`, `TypeCapteur.code`, `Capteur.identifiant`, `Seuil(capteur, type_seuil)`, `ModeleML(nom, version)`.
- **NOT NULL** : toutes les colonnes de référence (FK) sauf celles explicitement `null=True, blank=True`.
- **CHECK** : `taille_octets ≤ 102400` sur `ModeleML`, `qualite ∈ [0, 1]` et `anomalie_score ∈ [0, 1]` sur `Mesure`.

### 8.2 Validation au niveau Django

Au-delà des validators de champs, on ajoutera dans une prochaine itération des méthodes `clean()` pour les règles métier :

- `timestamp_cloture ≥ timestamp_declenchement` sur `Alerte`.
- Un seuil `haut_warning` doit avoir une valeur strictement inférieure à un seuil `haut_critique` du même capteur.
- `anomalie_score` ne peut être défini que si un `ModeleML.actif = True` existe.

### 8.3 Intégrité référentielle

Les comportements `on_delete` définis en § 4.3 sont appliqués par l'ORM Django et se traduisent en contraintes FK PostgreSQL natives.

---

## 9. Performance et volumétrie

### 9.1 Volumétrie attendue

| Table | Volumétrie (30 j, 50 capteurs, 1 msg / 10 s) |
|---|---|
| `core_site` | < 10 lignes |
| `core_typecapteur` | 4 lignes |
| `core_capteur` | 50 lignes |
| `core_seuil` | ~200 lignes |
| `ingestion_mesure` | **~13 millions de lignes (~1,5 Go)** |
| `alertes_alerte` | ~1 000 lignes |
| `analytics_derivedetectee` | ~150 000 lignes |
| `analytics_modeleml` | < 10 lignes |

### 9.2 Stratégie d'indexation

Index définis dans les `Meta.indexes` :

- `idx_mesure_capteur_ts` sur `Mesure(capteur, timestamp DESC)` — requête critique « historique d'un capteur ».
- `Alerte(capteur, statut)` — liste des alertes ouvertes par capteur.
- `DeriveDetectee(capteur, timestamp DESC)`.

### 9.3 Évolutions prévues (non livrées dans le prototype)

Pour un passage à l'échelle au-delà de 500 capteurs ou plusieurs années d'historique :

- **Partitionnement natif PostgreSQL** de la table `Mesure` par `RANGE(timestamp)` avec un chunk par mois.
- **Extension TimescaleDB** pour basculer `Mesure` en hypertable avec compression automatique des chunks > 7 jours.
- **Politique de rétention** : purge des mesures > 1 an (ou archivage vers S3).

Ces évolutions ne sont pas implémentées dans le livrable de prototype mais sont documentées pour montrer que l'architecture est extensible.

---

## 10. Données de référence initiales (fixtures)

Une fixture Django chargée au premier déploiement initialise :

- **4 types de capteurs** : `temperature`, `pression`, `vibration`, `qualite_air`.
- **2 sites** : `Site A - Bâtiment industriel`, `Site B - Atelier`.
- **8 capteurs** de démonstration (2 par type, répartis sur les 2 sites).
- **1 utilisateur** super-admin.
- **4 groupes** d'utilisateurs : `Ingenieur`, `Technicien`, `DataScientist`, `Supervision`.

Chargement par :

```bash
python manage.py loaddata initial_data.json
```

---

## 11. Glossaire

| Terme | Définition |
|---|---|
| **Entité** | Concept métier qui a une existence propre, représenté par une table. |
| **Entité faible** | Entité qui n'existe que rattachée à une autre (ex. Seuil sans Capteur n'a aucun sens). |
| **Attribut** | Propriété d'une entité, représentée par une colonne. |
| **Clé primaire (PK)** | Identifiant unique d'une ligne. Ici toujours `id` auto-incrémenté. |
| **Clé étrangère (FK)** | Référence à la PK d'une autre table, matérialisant une relation. |
| **Cardinalité** | Nombre minimum et maximum d'associations entre deux entités. |
| **Normalisation** | Processus d'élimination des redondances dans un schéma relationnel. |
| **3FN** | Troisième forme normale : aucune dépendance transitive entre attributs. |
| **ERD** | Entity-Relationship Diagram : schéma visuel des entités et relations. |
| **MQTT** | Message Queuing Telemetry Transport : protocole pub/sub léger pour l'IoT. |
| **TFLite** | TensorFlow Lite : format compact de modèle ML pour inférence embarquée. |

