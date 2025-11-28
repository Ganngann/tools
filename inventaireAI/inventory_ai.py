import os
import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image
import json

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not found in environment variables. Please check your .env file.")

genai.configure(api_key=api_key)

def analyze_image(image_path):
    """
    Analyzes an image using Gemini to extract Name, Category, and Quantity.
    Returns a dictionary with these fields.
    """
    try:
        # Use a model that is available in the list
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Use context manager to ensure file is closed after reading
        with Image.open(image_path) as img:
            # Force load image data so we can close the file
            img.load()
            
            prompt = """
            Analyze this image for an inventory system.
            Identify the object and look for any handwritten or printed quantity on a paper next to it.
            Also look for any other text or notes written on the paper (e.g. size, condition, specific details).
            
            Return the result as a JSON object with the following keys:
            - "nom": A short, descriptive name of the object (in French), INCLUDING any specific details found on the paper (e.g. "Gants de travail - Taille 9").
            - "categorie": A general category for the object (in French).
            - "quantite": The quantity read from the paper/label. If no quantity is visible, estimate it or default to 1. Return as an integer.
            
            Example output format:
            {
                "nom": "Stylo bille bleu - Boite abimée",
                "categorie": "Fournitures de bureau",
                "quantite": 5
            }
            """
            
            response = model.generate_content([prompt, img])
        
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
            "quantite": 0
        }
