# Outil d'Inventaire Automatisé par IA

Ce projet permet de générer automatiquement un inventaire Excel (CSV) à partir d'un dossier de photos. Il utilise l'intelligence artificielle (Google Gemini) pour analyser chaque image, identifier l'objet, sa catégorie et la quantité (si indiquée sur un post-it/note).

## Fonctionnalités

1.  **Analyse d'image** : Identifie l'objet, la catégorie (basée sur `categories.csv`) et la quantité.
2.  **Renommage** : Renomme les fichiers images séquentiellement (ex: `1.jpg`, `2.jpg`...) pour correspondre à leur ordre dans l'inventaire.
3.  **Export CSV** : Génère un fichier `.csv` à l'intérieur du dossier traité. Ce fichier contient :
    *   **ID** : Numéro séquentiel.
    *   **Fichier Original** : Nom d'origine du fichier.
    *   **Image** : Aperçu de l'image encodé en Base64 (pour affichage direct dans certains outils ou reconversion).
    *   **Nom** : Nom descriptif de l'objet.
    *   **Categorie** : Nom de la catégorie (selon `categories.csv`).
    *   **Categorie ID** : Identifiant unique de la catégorie.
    *   **Quantite** : Quantité détectée ou estimée.

## Prérequis

*   **Python 3.12** : [Télécharger Python 3.12](https://www.python.org/downloads/release/python-3120/) (Requis pour `setup.bat`).
*   **Clé API Google Gemini** : Nécessaire pour l'analyse d'images.

## Installation

1.  **Préparation** :
    *   Assurez-vous d'avoir installé **Python 3.12**.
    *   Double-cliquez sur le fichier **`setup.bat`**. Cela va installer automatiquement toutes les dépendances nécessaires (`requirements.txt`).

2.  **Configuration** :
    *   Renommez le fichier `.env.example` en `.env`.
    *   Ouvrez le fichier `.env` avec un éditeur de texte.
    *   Remplacez `VOTRE_CLE_API_ICI` par votre véritable clé API Google.
    *   (Optionnel) Le fichier `categories.csv` contient la liste des catégories valides. Vous pouvez le modifier si nécessaire.

## Utilisation

Il y a deux façons de lancer l'inventaire :

**Méthode 1 (La plus simple) :**
*   Glissez-déposez votre dossier de photos directement sur le fichier **`start.bat`**.

**Méthode 2 :**
*   Double-cliquez sur **`start.bat`**.
*   Le programme vous demandera de glisser le dossier dans la fenêtre noire. Faites-le et appuyez sur Entrée.

**Déroulement :**
1.  Le script scanne toutes les images du dossier (`.jpg`, `.jpeg`, `.png`, `.webp`).
2.  Il les analyse une par une avec l'IA.
3.  Il renomme les fichiers numériquement (`1.jpg`, `2.jpg`...).
4.  Il crée un fichier CSV (portant le nom du dossier) **à l'intérieur** du dossier photo.

## Créer un Exécutable (.exe)

Pour utiliser ce programme sur un ordinateur sans Python (Windows), vous pouvez créer un fichier `.exe` autonome via PyInstaller.

1.  Installez PyInstaller :
    ```bash
    pip install pyinstaller
    ```
2.  Générez l'exécutable :
    ```bash
    pyinstaller --onefile --name "InventaireIA" main.py
    ```
3.  Le fichier `InventaireIA.exe` se trouvera dans le dossier `dist`.
    *   **Attention** : Pour que l'exécutable fonctionne, il doit avoir accès au fichier `.env` (pour la clé API) et au fichier `categories.csv`. Selon la méthode de compilation, ces fichiers devront peut-être être placés dans le même dossier que l'exécutable ou inclus dans le paquet.
