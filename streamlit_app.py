import streamlit as st
import pandas as pd
import pdfplumber
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
from streamlit_drawable_canvas import st_canvas
from io import BytesIO
from datetime import datetime
from PIL import Image as PILImage

# --- CONFIGURATION ET DONNÉES STATIQUES ---

# Mapping des notes ECTS vers GPA
GPA_MAPPING = {
    "A": 4.0,
    "B": 3.0,
    "C": 2.0,
    "D": 1.7,
    "E": 1.0,
    "FX": 0.0,
    "Fx": 0.0, 
    "F": 0.0
}

# Base de données des cours (Traduction + Crédits FIXES)
# CORRECTION DÉFINITIVE DES CLÉS pour match avec l'extraction du PDF (UE 5.1 et UE 6.1 sans tiret)
COURSE_INFO_DB = {
    # COURSES (avec crédits pour le calcul GPA)
    "UE 5.1 Mathématiques pour l'ingénieur": {"en": "[S5] Mathematics for Engineers", "credits": 5, "type": "COURSE"}, 
    "UE 5.2 - Sciences pour l'ingénieur 1": {"en": "[S5] Science fundamentals 1", "credits": 7, "type": "COURSE"}, # Crédits fixes à 7 pour ce module
    "UE 6.1 Mathématiques pour l'ingénieur S6": {"en": "[S6] Mathematics for Engineers S6", "credits": 2, "type": "COURSE"}, 
    "UE 6.4 - Méthodes d'analyse et qualité": {"en": "[[S6] Analysis methods and quality", "credits": 2, "type": "COURSE"},
    "UE 5.3 - Electronique appliquée": {"en": "[S5] Applied electronics", "credits": 5, "type": "COURSE"},
    "UE 6.3 - Sciences du numérique 1": {"en": "[S6] Digital sciences 1", "credits": 8, "type": "COURSE"},
    "UE 5.5-Communication et créativité": {"en": "[S5] Communication and group creativity", "credits": 4, "type": "COURSE"},
    "UE 6.6-Accompagnement et suivi": {"en": "[S6] Engineer's behaviour (semester 6)", "credits": 2, "type": "COURSE"},
    "UE 5.6 - Evaluation entreprise": {"en": "[S5] Assessment by the company", "credits": 7, "type": "COURSE"},
    "UE 6.7 - Evaluation entreprise": {"en": "[S6] Assessment by the company", "credits": 8, "type": "COURSE"},
    "UE 5.4 - Anglais S5": {"en": "[S5] English", "credits": 2, "type": "COURSE"},
    "UE 6.5 - Anglais S6": {"en": "[S6] English", "credits": 2, "type": "COURSE"},

    # CATEGORIES (avec crédits à 0, pour la mise en forme du tableau)
    "Sciences de base": {"en": "Science Fundamentals", "credits": 0, "type": "CATEGORY"},
    "Sciences et méthodes de l'ingénieur": {"en": "Engineering methodology", "credits": 0, "type": "CATEGORY"},
    "Sciences et techniques de spécialité": {"en": "Industrial engineering techniques and systems", "credits": 0, "type": "CATEGORY"},
    "Sciences humaines, économiques, juridiques et sociales": {"en": "Humanities", "credits": 0, "type": "CATEGORY"},
    "Mission en entreprise": {"en": "Missions in company (professional experience)", "credits": 0, "type": "CATEGORY"},
    "Langues": {"en": "Languages", "credits": 0, "type": "CATEGORY"}
}

# --- FONCTIONS UTILITAIRES ---

def extract_data_from_pdf(uploaded_file):
    """Extrait le texte et le tableau brut du PDF."""
    text_content = ""
    table_data = []
    
    with pdfplumber.open(uploaded_file) as pdf:
        page1 = pdf.pages[0]
        text_content = page1.extract_text()
        tables = page1.extract_tables()
        if tables:
            table_data = max(tables, key=len) 
            
    return text_content, table_data

def parse_metadata(text):
    """Récupère les infos de l'étudiant."""
    lines = text.split('\n')
    metadata = {
        "name": "UNKNOWN",
        "class_name": "UNKNOWN",
        "program": "Embedded Systems engineering program",
        "campus": "Toulouse"
    }
    
    for line in lines:
        if "Nom, Prénom" in line or "Nom :" in line:
            metadata["name"] = line.split(":")[-1].strip()
        if "Promotion" in line:
            metadata["class_name"] = line.split(":")[-1].strip()
        if "Etablissement de" in line:
            metadata["campus"] = line.split("de")[-1].strip()
            
    return metadata

def prepare_df_for_edit(raw_table):
    """Prépare le DataFrame avec les crédits fixes et la traduction initiale pour édition."""
    processed_rows = []
    start_index = 1
