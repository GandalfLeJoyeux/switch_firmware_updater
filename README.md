# Scripts d'administration HP ProCurve / ArubaOS-Switch

## Présentation

Ce dépôt contient deux scripts Python permettant d'automatiser l'administration des switches HP ProCurve et ArubaOS-Switch :

- **save_conf_switch.py** : sauvegarde automatisée des configurations (`running-config`).
- **switch_firmware_updater.py** : vérification et déploiement des mises à jour de firmware.

## Modèles testés

- HP ProCurve 2520
- HP ProCurve 2530
- HP ProCurve 2610
- HP ProCurve 2615
- HP ProCurve 2620
- HP ProCurve 2626
- HP ProCurve 2920
- Aruba 2930F

---

# Fonctionnalités

## Sauvegarde des configurations

Le script `save_conf_switch.py` permet :

- Connexion SSH automatisée aux switches
- Activation du transfert SFTP si nécessaire
- Récupération automatique du hostname
- Téléchargement de la configuration en cours (`running-config`)
- Archivage dans un répertoire daté
- Exécution multi-threadée
- Journalisation des succès et erreurs

### Arborescence générée

```text
config/
└── 20261123/
    ├── 20261123_SW-CORE_10.1.1.1.cfg
    ├── 20261123_SW-ACCESS-01_10.1.1.2.cfg
    └── ...
```

---

## Gestion des firmwares

Le script `switch_firmware_updater.py` permet :

- Vérifier la version actuellement exécutée
- Vérifier la version chargée en mémoire flash
- Comparer la version installée avec la dernière version disponible
- Sauvegarder automatiquement la configuration avant mise à jour
- Déployer un firmware via SFTP
- Programmer un redémarrage différé
- Contrôler qu'un switch est à jour
- Traiter plusieurs équipements simultanément

---

# Prérequis

## Python

Python 3.10 ou supérieur recommandé.

## Dépendances

Installation :

```bash
pip install paramiko
```

Modules utilisés :

- paramiko
- concurrent.futures
- datetime
- csv
- os
- re
- time

---

# Authentification

Les scripts utilisent les variables d'environnement suivantes :

```text
username
password
```

## Linux

```bash
export username="admin"
export password="MonMotDePasse"
```

## PowerShell

```powershell
$env:username="admin"
$env:password="MonMotDePasse"
```

Il est également possible de renseigner les identifiants directement dans les scripts, mais cette méthode est déconseillée en production.

---

# Fichier d'inventaire

Les deux scripts utilisent un fichier texte nommé :

```text
sw_conf.txt
```

Contenant une adresse IP par ligne :

```text
10.0.0.1
10.0.0.2
10.0.0.3
```

Chaque équipement sera traité automatiquement.

---

# Structure recommandée

```text
Projet/
│
├── save_conf_switch.py
├── switch_firmware_updater.py
├── sw_conf.txt
├── rapport.txt
├── erreur.txt
│
├── config/
│
└── versions/
    ├── WC_16_11_0030.swi
    ├── WB_16_10_0025.swi
    └── YA_16_11_0024.swi
```

---

# Sauvegarde des configurations

## Exécution

```bash
python save_conf_switch.py
```

### Déroulement

1. Lecture des IP depuis `sw_conf.txt`
2. Connexion SSH
3. Activation du transfert SFTP si nécessaire
4. Récupération du hostname
5. Téléchargement de la configuration
6. Sauvegarde dans un dossier daté
7. Écriture du résultat dans `rapport.txt`

---

# Vérification des versions de firmware

Par défaut, le script peut être utilisé uniquement pour vérifier si les switches sont à jour.

Dans la fonction principale :

```python
check_update(shell, host)
```

Le script récupère :

- Le hostname
- La version actuellement exécutée
- La version présente dans la mémoire flash
- La dernière version disponible dans le dossier `versions`

Puis affiche les équipements nécessitant une mise à jour.

---

# Mise à jour des firmwares

## Préparation

Déposer les firmwares dans le dossier :

```text
versions/
```

Exemple :

```text
versions/
├── WC_16_11_0030.swi
├── WB_16_10_0025.swi
└── YA_16_11_0024.swi
```

## Paramètres à adapter

Dans la fonction `hote()` :

```python
date = "23:00 11/23"
sntp = "10.0.0.10"
```

### Description

| Paramètre | Description |
|------------|-------------|
| `date` | Date et heure du redémarrage (`HH:MM MM/DD`) |
| `sntp` | Adresse du serveur SNTP/NTP |

---

## Lancer une mise à jour

Remplacer :

```python
check_update(shell, host)
```

Par :

```python
switch_maj(shell, sftp, host, date)
```

La procédure exécutée sera :

1. Vérification de la version installée
2. Sauvegarde de la configuration
3. Téléversement du firmware
4. Sauvegarde de la configuration (`write memory`)
5. Planification du redémarrage
6. Journalisation de l'opération

---

# Journaux

## rapport.txt

Contient les opérations réussies :

```text
Mon Nov 23 18:00:00 2026 | SW-CORE(10.0.0.1)
Mon Nov 23 18:05:00 2026 | SW-ACCESS(10.0.0.2) est déjà à jour
```

## erreur.txt

Contient les erreurs rencontrées :

```text
Mon Nov 23 18:10:00 2026 | {'ip': '10.0.0.5'} : Authentication failed
```

---

# Performances

## Nombre maximal de connexions simultanées

| Script | Threads |
|----------|----------|
| save_conf_switch.py | 100 |
| switch_firmware_updater.py | 50 |

Ces valeurs peuvent être adaptées selon la capacité de la machine exécutant les scripts et la taille du parc à administrer.

---

# Limitations connues

- Compatible principalement avec HP ProCurve et ArubaOS-Switch.
- Nécessite un accès SSH.
- Nécessite le transfert SFTP.
- Le hostname doit être présent dans la configuration.
- La détection du firmware repose sur les fichiers présents dans le dossier `versions`.
- Le redémarrage différé utilise la commande `reload at`, qui n'est pas disponible sur tous les modèles.

---

# Bonnes pratiques

- Toujours exécuter un premier passage en mode vérification (`check_update`) avant toute mise à jour.
- Tester les nouveaux firmwares sur un équipement pilote avant déploiement massif.
- Conserver plusieurs générations de sauvegardes de configuration.
- Vérifier l'espace disponible en mémoire flash avant téléversement d'une nouvelle image.
- Programmer les redémarrages hors production.

---

# Auteur

**Antoine Polidori**

Sujet de stage de deuxième année de BUT Réseaux & Télécommunications

Université de Caen Normandie

---

# Licence

Usage interne.

Aucun support ni garantie. Tester les scripts dans un environnement de validation avant toute utilisation sur un réseau de production.
