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

## Outil de Révision (Correction Manuelle)

Une interface graphique est incluse pour vérifier et corriger l'inventaire facilement.

1.  **Lancement** :
    *   Glissez-déposez votre fichier `inventaire_final_....csv` sur le fichier **`review.bat`**.
2.  **Fonctionnalités** :
    *   **Visualisation** : Affiche l'image de l'objet à côté des données extraites.
    *   **Correction** : Modifiez n'importe quel champ (Nom, Quantité, Prix, etc.).
    *   **Rotation** : Si une image est mal orientée, cliquez sur "Pivoter" (sauvegarde immédiate).
    *   **Rescan IA** : Si l'IA s'est trompée, cliquez sur "Rescan", donnez un indice (ex: "C'est une lampe"), et l'IA réanalysera l'image.
    *   **Scan Multi** : Si une image contient plusieurs objets, utilisez "Scan Multi" pour les détecter et créer des lignes séparées.
    *   **À Refaire** : Marque l'image pour être reprise plus tard (déplace le fichier dans `a_refaire` et le retire du CSV).
    *   **Valider** : Confirme que la ligne est correcte (passe sa fiabilité à 100%).

## Créer un Exécutable (.exe)

Pour utiliser ce programme sur un ordinateur sans Python, utilisez le script de construction automatique :

1.  Double-cliquez sur **`build_exe.bat`**.
2.  Attendez que la console indique "CONSTRUCTION REUSSIE".
3.  Le dossier **`dist`** contiendra votre application `InventaireIA.exe` prête à l'emploi.
    *   Le script copie automatiquement votre fichier `.env` actuel et `categories.csv` dans le dossier `dist`.
    *   Vous pouvez déplacer le dossier `dist` (renommez-le si vous voulez) sur un autre PC.

## Utilisation de l'Application Portable (.exe)

Une fois l'exécutable généré (voir ci-dessus), vous pouvez l'utiliser sur n'importe quel PC Windows, même sans Python installé.

1.  **Structure du dossier** :
    Assurez-vous que le fichier `.exe` est toujours accompagné des fichiers suivants dans le même dossier :
    *   `.env` (Votre clé API)
    *   `categories.csv` (Vos catégories)

2.  **Lancement** :
    Double-cliquez sur `InventaireIA.exe` pour ouvrir le **Launcher**.

3.  **Fonctionnalités** :
    *   **🆕 Nouvel Inventaire** : Cliquez sur ce bouton pour sélectionner un dossier de photos. Une barre de progression s'affichera pendant que l'IA analyse vos images.
    *   **🛠️ Réviser / Corriger** : Cliquez sur ce bouton pour ouvrir un fichier CSV existant et lancer l'interface de correction (voir section "Outil de Révision").
