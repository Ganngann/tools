import os
import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image
import json
import io

import sys

# Load .env correctly if frozen
if getattr(sys, 'frozen', False):
    base_path = os.path.dirname(sys.executable)
    load_dotenv(os.path.join(base_path, ".env"))
else:
    load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not found in environment variables. Please check your .env file.")

genai.configure(api_key=api_key)

def load_categories(csv_path="categories.csv"):
    """
    Loads categories from a CSV file.
    Expected format: id,nom
    Returns a string representation of the categories for the prompt.
    """
    categories_text = ""
    try:
        # Determine absolute path relative to this script
        # Determine absolute path relative to this script or exe
        if getattr(sys, 'frozen', False):
             # If frozen, "categories.csv" should be next to the exe, or inside internal folder if bundled?
             # Assuming user wants to edit it, we look next to exe.
             script_dir = os.path.dirname(sys.executable)
        else:
             script_dir = os.path.dirname(os.path.abspath(__file__))
             
        file_path = os.path.join(script_dir, csv_path)

        with open(file_path, 'r', encoding='utf-8') as f:
            categories_text = f.read()
    except Exception as e:
        print(f"Error loading categories from {csv_path}: {e}")
        return ""
    return categories_text

def analyze_image(image_path, categories_context=None, user_hint=None, folder_context=None, previous_data=None, status_callback=None):
    """
    Analyzes an image using Gemini to extract Name, Category, and Quantity.
    Returns a dictionary with these fields.
    """
    try:
        if status_callback:
            status_callback("Initialisation de l'IA (Gemini 2.0 Flash)...")

        # Use a model that is available in the list
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Load categories if not provided
        if categories_context is None:
            categories_context = load_categories()

        if status_callback:
            status_callback("Préparation et compression de l'image...")

        # Use context manager to ensure file is closed after reading
        with Image.open(image_path) as img:
            # Force load image data so we can close the file
            img.load()

            # Resize image to max 800x800 for API efficiency (lightest possible)
            max_width = int(os.getenv("GEMINI_MAX_WIDTH", 800))
            max_height = int(os.getenv("GEMINI_MAX_HEIGHT", 800))
            img.thumbnail((max_width, max_height))

            # Convert to compressed JPEG bytes to minimize upload size
            img_byte_arr = io.BytesIO()
            # Convert RGBA/P to RGB for JPEG compatibility
            if img.mode in ("RGBA", "P"):
                 img = img.convert("RGB")

            # Compress aggressively (quality=60)
            quality = int(os.getenv("GEMINI_JPEG_QUALITY", 60))
            img.save(img_byte_arr, format='JPEG', quality=quality, optimize=True)
            img_byte_arr.seek(0)

            # Create a blob for the API
            image_blob = {
                'mime_type': 'image/jpeg',
                'data': img_byte_arr.getvalue()
            }
            
            hint_text = ""
            if user_hint:
                hint_text = f"USER REMARK/CORRECTION: The user reviewed the previous result and provided this correction/remark: '{user_hint}'. Pay special attention to this."
            
            context_text = ""
            if folder_context:
                context_text = f"GLOBAL CONTEXT/INSTRUCTIONS: '{folder_context}'. ALWAYS apply these instructions."

            previous_info_text = ""
            if previous_data:
                previous_info_text = f"PREVIOUS ANALYSIS RESULT: {previous_data}. The user wants to correct or verify this based on the remark."

            prompt = f"""
            Analyze this image for an inventory system.
            {context_text}
            {previous_info_text}
            {hint_text}
            Identify the object and look for any handwritten or printed quantity on a post-it note or paper placed ON or NEXT TO the object.
            Also look for any other text or notes written on the paper (e.g. size, condition, specific details).
            
            PRIORITY RULE (QUANTITY): If a post-it note (often yellow/neon/white) or paper with a handwritten number/quantity is visible ON or NEXT TO the object, YOU MUST USE THAT NUMBER as the quantity.
            - Even if the visual count differs, TRUST THE WRITTEN NOTE.
            - The note overrides any other quantity indication.

            EXCLUSION RULE (OBJECTS): Do NOT list the post-it note, paper, or label itself as an object. It is only context. Exception: if the post-it note is the ONLY thing in the entire image, then you may list it as the object.
            TRUNCATION RULE: Ignore objects that are significantly cut off by the edge of the image. Only list objects that are fully or mostly visible. Do not infer an object if only a small part (like a wheel or a shoe) is visible at the border.
            
            IMPORTANT: Pay special attention to the quantity. For a box of items (e.g., 900 screws), you have two valid choices:
            1. Unit logic: Quantity = 900, Name = 'Vis' (Screw)
            2. Box logic: Quantity = 1, Name = 'Boite de 900 vis' (Box of 900 screws)
            NEVER mix these logics (e.g., Quantity = 900, Name = 'Boite de 900 vis' is FORBIDDEN).

            Select the most appropriate category for the object from the following list (CSV format with ID,Nom):

            {categories_context}

            Return the result as a JSON object with the following keys:
            - "nom": A short, descriptive name of the object (in French), INCLUDING any specific details found on the paper (e.g. "Gants de travail - Taille 9").
            - "categorie": The Name of the category from the provided list.
            - "categorie_id": The ID of the category from the provided list.
            - "quantite": The quantity read from the paper/label. If no quantity is visible, estimate it or default to 1. Return as an integer.
            - "etat": The condition of the object. Must be either "Neuf" or "Occasion".
            - "prix_unitaire_estime": An estimated unit price in Euros. IMPORTANT: Always use the PRICE AS NEW (replacement value), even if the object is used/broken. Support decimals for small items (e.g. 0.05).
            - "prix_neuf_estime": Same as above. Return as a number (decimals allowed).
            - "fiabilite": A confidence score (0-100) indicating how reliable this identification and detail extraction is. Return as an integer.
            - "box_2d": The bounding box of the object in the image. Return as a list of 4 integers [ymin, xmin, ymax, xmax] normalized to 1000 (0-1000).
            
            Example output format:
            {{
                "nom": "Assiette blanche - Ebréchée",
                "categorie": "Cuisine - Assiettes",
                "categorie_id": "categ_assiettes",
                "quantite": 6,
                "etat": "Occasion",
                "prix_unitaire_estime": 2,
                "prix_neuf_estime": 5,
                "fiabilite": 95,
                "box_2d": [100, 200, 500, 600]
            }}
            """
            
            if status_callback:
                status_callback("Envoi à l'API Gemini (Analyse en cours)...")

            response = model.generate_content([prompt, image_blob])
        
        if status_callback:
            status_callback("Réception et traitement de la réponse...")

        # Clean up response text to ensure it's valid JSON
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:-3]
        elif text.startswith("```"):
            text = text[3:-3]
            
        return json.loads(text)
        
    except Exception as e:
        print(f"Error analyzing {image_path}: {e}")
        return {
            "nom": "Erreur",
            "categorie": "Inconnu",
            "categorie_id": "unknown",
            "quantite": 0,
            "etat": "Inconnu",
            "prix_unitaire_estime": 0,
            "prix_neuf_estime": 0,
            "fiabilite": 0
        }

def analyze_image_multiple(image_path, target_element=None, categories_context=None, high_quality=False, user_hint=None, status_callback=None):
    """
    Analyzes an image using Gemini to extract a list of objects (Name, Category, Quantity, etc.).
    Returns a list of dictionaries.
    """
    try:
        if status_callback:
            status_callback("Initialisation de l'IA (Multi-Objets)...")

        # Use a model that is available in the list
        model = genai.GenerativeModel('gemini-2.0-flash')

        # Load categories if not provided
        if categories_context is None:
            categories_context = load_categories()

        if status_callback:
            status_callback("Préparation de l'image (Mode Haute Qualité)..." if high_quality else "Préparation de l'image...")

        # Use context manager to ensure file is closed after reading
        with Image.open(image_path) as img:
            # Force load image data so we can close the file
            img.load()

            img_byte_arr = io.BytesIO()

            if high_quality:
                # High quality mode: Try to use original resolution, but keep under 10MB
                # User constraint: "taille maximale de 10Mo", "original format", "barely compressed"

                # Convert RGBA/P to RGB for JPEG compatibility if needed
                if img.mode in ("RGBA", "P"):
                     img = img.convert("RGB")

                # Initial attempt: save with high quality (e.g., 95)
                quality = 95
                img.save(img_byte_arr, format='JPEG', quality=quality, optimize=True)

                # Check size (10MB = 10 * 1024 * 1024 bytes)
                max_size_bytes = 10 * 1024 * 1024

                # Iterative compression if too large
                while img_byte_arr.tell() > max_size_bytes and quality > 10:
                    quality -= 5
                    img_byte_arr = io.BytesIO()
                    img.save(img_byte_arr, format='JPEG', quality=quality, optimize=True)

                # If still too large after lowering quality, resize iteratively
                if img_byte_arr.tell() > max_size_bytes:
                    width, height = img.size
                    ratio = 0.9
                    while img_byte_arr.tell() > max_size_bytes and width > 300:
                        width = int(width * ratio)
                        height = int(height * ratio)
                        resized_img = img.resize((width, height), Image.Resampling.LANCZOS)

                        img_byte_arr = io.BytesIO()
                        # Reset quality to something reasonable for resized
                        quality = 85
                        resized_img.save(img_byte_arr, format='JPEG', quality=quality, optimize=True)
                        ratio *= 0.9

                img_byte_arr.seek(0)

            else:
                # Standard mode: Resize to max 800x800 for API efficiency
                max_width = int(os.getenv("GEMINI_MAX_WIDTH", 800))
                max_height = int(os.getenv("GEMINI_MAX_HEIGHT", 800))
                img.thumbnail((max_width, max_height))

                # Convert RGBA/P to RGB for JPEG compatibility
                if img.mode in ("RGBA", "P"):
                     img = img.convert("RGB")

                # Compress aggressively (quality=60)
                quality = int(os.getenv("GEMINI_JPEG_QUALITY", 60))
                img.save(img_byte_arr, format='JPEG', quality=quality, optimize=True)
                img_byte_arr.seek(0)

            # Create a blob for the API
            image_blob = {
                'mime_type': 'image/jpeg',
                'data': img_byte_arr.getvalue()
            }

            if target_element:
                focus_instruction = f"Focus specifically on counting and listing: {target_element}."
            else:
                focus_instruction = "List and count all distinct types of objects visible in the image."

            hint_text = ""
            if user_hint:
                hint_text = f"USER HINT: The user provided this hint to help identification: '{user_hint}'. Use this to improve accuracy."

            prompt = f"""
            Analyze this image for an inventory system.
            {focus_instruction}
            {hint_text}
            Look for any handwritten or printed quantity on a post-it note or paper placed ON or NEXT TO objects.
            Also look for any other text or notes written on the paper (e.g. size, condition, specific details).

            PRIORITY RULE (QUANTITY): For each object, if a post-it note (often yellow/neon) or paper with a handwritten number/quantity is associated with it (placed ON it or NEXT TO it), YOU MUST USE THAT QUANTITY.
            - Even if the visual count differs, TRUST THE WRITTEN NOTE.
            - The note overrides any other quantity indication.

            EXCLUSION RULE (OBJECTS): Do NOT count the post-it notes, papers, or labels as separate objects. They are context/labels only.
            TRUNCATION RULE: Ignore objects that are significantly cut off by the edge of the image. Only list objects that are fully or mostly visible. Do not infer an object if only a small part (like a wheel or a shoe) is visible at the border.

            IMPORTANT: Pay special attention to the quantity. For a box of items (e.g., 900 screws), you have two valid choices:
            1. Unit logic: Quantity = 900, Name = 'Vis' (Screw)
            2. Box logic: Quantity = 1, Name = 'Boite de 900 vis' (Box of 900 screws)
            NEVER mix these logics (e.g., Quantity = 900, Name = 'Boite de 900 vis' is FORBIDDEN).

            Select the most appropriate category for each object from the following list (CSV format with ID,Nom):

            {categories_context}

            Return the result as a JSON LIST of objects, where each object has the following keys:
            - "nom": A short, descriptive name of the object type (in French), INCLUDING any specific details found on the paper.
            - "categorie": The Name of the category from the provided list.
            - "categorie_id": The ID of the category from the provided list.
            - "quantite": The quantity of this object type visible or read from label. Return as an integer.
            - "etat": The condition of the objects. Must be either "Neuf" or "Occasion".
            - "prix_unitaire_estime": An estimated unit price in Euros. IMPORTANT: Always use the PRICE AS NEW (replacement value). Return as a number (decimals allowed e.g. 0.05).
            - "prix_neuf_estime": Same as above. Return as a number (decimals allowed).
            - "fiabilite": A confidence score (0-100) indicating how reliable this identification and detail extraction is for this specific object. Return as an integer.
            - "box_2d": The bounding box of the object in the image. Return as a list of 4 integers [ymin, xmin, ymax, xmax] normalized to 1000 (0-1000).

            Example output format:
            [
                {{
                    "nom": "Marteau",
                    "categorie": "Outils",
                    "categorie_id": "categ_outils",
                    "quantite": 3,
                    "etat": "Occasion",
                    "prix_unitaire_estime": 5,
                    "prix_neuf_estime": 15,
                    "fiabilite": 90,
                    "box_2d": [150, 250, 450, 550]
                }},
                {{
                    "nom": "Tournevis",
                    "categorie": "Outils",
                    "categorie_id": "categ_outils",
                    "quantite": 2,
                    "etat": "Occasion",
                    "prix_unitaire_estime": 2,
                    "prix_neuf_estime": 5,
                    "fiabilite": 85,
                    "box_2d": [600, 100, 800, 300]
                }}
            ]
            """

            if status_callback:
                status_callback("Envoi à l'API Gemini (Scan Multi en cours)...")

            response = model.generate_content([prompt, image_blob])

        if status_callback:
            status_callback("Réception et traitement des résultats...")

        # Clean up response text to ensure it's valid JSON
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:-3]
        elif text.startswith("```"):
            text = text[3:-3]

        return json.loads(text)

    except Exception as e:
        print(f"Error analyzing {image_path}: {e}")
        return [{
            "nom": "Erreur",
            "categorie": "Inconnu",
            "categorie_id": "unknown",
            "quantite": 0,
            "etat": "Inconnu",
            "prix_unitaire_estime": 0,
            "prix_neuf_estime": 0,
            "fiabilite": 0
        }]
