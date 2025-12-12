# Outil d'Inventaire Automatisé par IA

Ce projet permet de générer automatiquement un inventaire Excel (CSV) à partir d'un dossier de photos. Il utilise l'intelligence artificielle (Google Gemini) pour analyser chaque image, identifier l'objet, sa catégorie et la quantité (si indiquée sur un post-it/note).

## Fonctionnalités

1.  **Analyse d'image** : Identifie l'objet, la catégorie (basée sur `categories.csv`) et la quantité.
2.  **Gestion du Contexte** : Permet de donner des instructions globales à l'IA pour tout un dossier (ex: "Ce sont des antiquités du 19ème siècle").
3.  **Traitement Interruptible** :
    *   Les images traitées sont déplacées dans un sous-dossier `traitees`.
    *   L'inventaire CSV est mis à jour en temps réel après chaque image.
    *   Vous pouvez arrêter et reprendre le traitement à tout moment sans perte de données.
4.  **Renommage Intelligent** : Renomme les fichiers images avec la quantité et le nom de l'objet (ex: `1_Chaise_Bois.jpg`).

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

### Déroulement du traitement

1.  **Contexte** : Le script cherche un fichier `context.txt` ou `instructions.txt` dans le dossier. S'il n'existe pas, il vous demandera si vous souhaitez saisir des instructions manuelles (qui seront alors sauvegardées pour la prochaine fois).
2.  **Analyse** : Les images sont analysées une par une.
3.  **Traitement** :
    *   L'image est renommée et déplacée dans le sous-dossier **`traitees`**.
    *   Une ligne est ajoutée immédiatement au fichier CSV (créé dans le dossier racine des images).
4.  **Interruption** : Vous pouvez arrêter le script (Ctrl+C) à tout moment. Pour reprendre, relancez simplement le script sur le même dossier : il ignorera les images déjà dans `traitees` et continuera le travail.

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
    *   **Attention** : Pour que l'exécutable fonctionne, il doit avoir accès au fichier `.env` (pour la clé API) et au fichier `categories.csv`.
