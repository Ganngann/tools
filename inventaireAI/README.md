# Outil d'Inventaire Automatisé par IA

Ce projet permet de générer automatiquement un inventaire Excel (CSV) à partir d'un dossier de photos. Il utilise l'intelligence artificielle (Google Gemini) pour analyser chaque image, identifier l'objet, sa catégorie et la quantité (si indiquée sur un post-it/note).

## Fonctionnalités

1.  **Analyse d'image** : Identifie l'objet, la catégorie et la quantité.
2.  **Renommage** : Renomme les fichiers images séquentiellement (1.jpg, 2.jpg, etc.) pour correspondre à leur ordre dans l'inventaire.
3.  **Export CSV** : Génère un fichier `.csv` contenant toutes les données, prêt à être ouvert dans Excel.

## Prérequis

*   **Python** (si vous exécutez le script directement) : [Télécharger Python](https://www.python.org/downloads/)
*   **Clé API Google Gemini** : Nécessaire pour l'analyse d'images.

## Installation

1.  **Préparation** :
    *   Assurez-vous d'avoir installé [Python](https://www.python.org/downloads/).
    *   Double-cliquez sur le fichier **`setup.bat`**. Cela va installer automatiquement tout ce qui est nécessaire.

2.  **Configuration** :
    *   Renommez le fichier `.env.example` en `.env`.
    *   Ouvrez le fichier `.env` avec un éditeur de texte.
    *   Remplacez `VOTRE_CLE_API_ICI` par votre véritable clé API Google.

## Utilisation

Il y a deux façons de lancer l'inventaire :

**Méthode 1 (La plus simple) :**
*   Glissez-déposez votre dossier de photos directement sur le fichier **`start.bat`**.

**Méthode 2 :**
*   Double-cliquez sur **`start.bat`**.
*   Le programme vous demandera de glisser le dossier dans la fenêtre noire. Faites-le et appuyez sur Entrée.

Le script va alors :
1.  Scanner toutes les images du dossier.
2.  Les analyser une par une.
3.  Les renommer (1.jpg, 2.jpg...).
4.  Créer un fichier CSV (Excel) dans le dossier.

## Créer un Exécutable (.exe)

Pour utiliser ce programme sur un ordinateur sans Python (Windows), vous pouvez créer un fichier `.exe` autonome.

1.  Installez PyInstaller :
    ```bash
    pip install pyinstaller
    ```
2.  Générez l'exécutable :
    ```bash
    pyinstaller --onefile --name "InventaireIA" main.py
    ```
3.  Le fichier `InventaireIA.exe` se trouvera dans le dossier `dist`.
    *   Vous pouvez copier ce fichier sur une clé USB.
    *   **Important** : Le fichier `.env` (avec votre clé API) doit toujours être placé dans le même dossier que le `.exe` pour qu'il fonctionne.
