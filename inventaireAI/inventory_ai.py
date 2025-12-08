import os
import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image
import json
import io

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
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, csv_path)

        with open(file_path, 'r', encoding='utf-8') as f:
            categories_text = f.read()
    except Exception as e:
        print(f"Error loading categories from {csv_path}: {e}")
        return ""
    return categories_text

def analyze_image(image_path, categories_context=None):
    """
    Analyzes an image using Gemini to extract Name, Category, and Quantity.
    Returns a dictionary with these fields.
    """
    try:
        # Use a model that is available in the list
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Load categories if not provided
        if categories_context is None:
            categories_context = load_categories()

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
            
            prompt = f"""
            Analyze this image for an inventory system.
            Identify the object and look for any handwritten or printed quantity on a paper next to it.
            Also look for any other text or notes written on the paper (e.g. size, condition, specific details).
            
            Select the most appropriate category for the object from the following list (CSV format with ID,Nom):

            {categories_context}

            Return the result as a JSON object with the following keys:
            - "nom": A short, descriptive name of the object (in French), INCLUDING any specific details found on the paper (e.g. "Gants de travail - Taille 9").
            - "categorie": The Name of the category from the provided list.
            - "categorie_id": The ID of the category from the provided list.
            - "quantite": The quantity read from the paper/label. If no quantity is visible, estimate it or default to 1. Return as an integer.
            - "etat": The condition of the object. Must be either "Neuf" or "Occasion".
            - "prix_unitaire_estime": An estimated unit price in Euros based on the object type and condition. Return as a number.
            
            Example output format:
            {{
                "nom": "Assiette blanche - Ebréchée",
                "categorie": "Cuisine - Assiettes",
                "categorie_id": "categ_assiettes",
                "quantite": 6,
                "etat": "Occasion",
                "prix_unitaire_estime": 2.50
            }}
            """
            
            response = model.generate_content([prompt, image_blob])
        
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
            "prix_unitaire_estime": 0
        }
