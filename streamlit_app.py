import streamlit as st
import pandas as pd
import pdfplumber
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from streamlit_drawable_canvas import st_canvas
from io import BytesIO
from datetime import datetime
import numpy as np
from PIL import Image as PILImage

# --- CONFIGURATION ET DONNÉES STATIQUES ---

# Mapping des notes ECTS vers GPA (Source: Image fournie)
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

# Dictionnaire de traduction initial (basé sur tes fichiers)
# Clé = Nom français, Valeur = Nom anglais
TRANSLATION_DICT = {
    "Sciences de base": "Science Fundamentals",
    "UE 5.1 Mathématiques pour l'ingénieur": "[S5] Mathematics for Engineers",
    "UE 5.2 - Sciences pour l'ingénieur 1": "[S5] Science fundamentals 1",
    "UE 6.1 Mathématiques pour l'ingénieur S6": "[S6] Mathematics for Engineers S6",
    "Sciences et méthodes de l'ingénieur": "Engineering methodology",
    "UE 6.4 - Méthodes d'analyse et qualité": "[[S6] Analysis methods and quality",
    "Sciences et techniques de spécialité": "Industrial engineering techniques and systems",
    "UE 5.3 - Electronique appliquée": "[S5] Applied electronics",
    "UE 6.3 - Sciences du numérique 1": "[S6] Digital sciences 1",
    "Sciences humaines, économiques, juridiques et sociales": "Humanities",
    "UE 5.5-Communication et créativité": "[S5] Communication and group creativity",
    "UE 6.6-Accompagnement et suivi": "[S6] Engineer's behaviour (semester 6)",
    "Mission en entreprise": "Missions in company (professional experience)",
    "UE 5.6 - Evaluation entreprise": "[S5] Assessment by the company",
    "UE 6.7 - Evaluation entreprise": "[S6] Assessment by the company",
    "Langues": "Languages",
    "UE 5.4 - Anglais S5": "[S5] English",
    "UE 6.5 - Anglais S6": "[S6] English"
}

# --- FONCTIONS UTILITAIRES ---

def extract_data_from_pdf(uploaded_file):
    """Extrait les informations brutes du PDF français."""
    text_content = ""
    table_data = []
    
    with pdfplumber.open(uploaded_file) as pdf:
        # Extraction du texte pour les métadonnées (Page 1)
        page1 = pdf.pages[0]
        text_content = page1.extract_text()
        
        # Extraction du tableau
        # On suppose que le tableau principal est le plus grand sur la page
        tables = page1.extract_tables()
        if tables:
            # On prend le tableau qui a le plus de lignes
            table_data = max(tables, key=len)
            
    return text_content, table_data

def parse_metadata(text):
    """Cherche le nom, la promo, etc. dans le texte brut."""
    lines = text.split('\n')
    metadata = {
        "name": "UNKNOWN",
        "class_name": "UNKNOWN",
        "program": "Embedded Systems engineering program", # Valeur par défaut
        "campus": "Toulouse" # Valeur par défaut
    }
    
    for line in lines:
        if "Nom, Prénom" in line or "Nom :" in line:
            metadata["name"] = line.split(":")[-1].strip()
        if "Promotion" in line:
            metadata["class_name"] = line.split(":")[-1].strip()
        if "Etablissement de" in line:
            metadata["campus"] = line.split("de")[-1].strip()
            
    return metadata

def clean_table_data(raw_table):
    """Nettoie et structure les données du tableau pour le DataFrame."""
    cleaned_rows = []
    
    # On saute l'en-tête (souvent la première ligne)
    start_index = 1
    
    for row in raw_table[start_index:]:
        # Nettoyage des None et des sauts de ligne
        clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
        
        # Structure attendue dans le PDF français : [Matière, Credits, Note]
        # Parfois pdfplumber extrait des colonnes vides, on essaie de détecter
        if len(clean_row) >= 3:
            subject = clean_row[0]
            credits = clean_row[1]
            grade = clean_row[2]
            
            # Détection si c'est une catégorie (souvent pas de note ni crédits, ou crédits vides)
            is_category = (credits == "" or credits is None) and (grade == "" or grade is None)
            
            cleaned_rows.append({
                "French_Course": subject,
                "English_Course": TRANSLATION_DICT.get(subject, subject), # Traduction auto ou copie
                "Credits": credits,
                "ECTS_Grade": grade,
                "Is_Category": is_category
            })
            
    return pd.DataFrame(cleaned_rows)

def calculate_gpa(df):
    """Calcule le GPA pour chaque ligne et le total."""
    def get_points(row):
        if row['Is_Category'] or row['ECTS_Grade'] == "":
            return None
        grade = row['ECTS_Grade'].upper()
        return GPA_MAPPING.get(grade, 0.0)

    df['GPA_Score'] = df.apply(get_points, axis=1)
    
    # Calcul du GPA Moyen Pondéré
    total_points = 0
    total_credits = 0
    
    for index, row in df.iterrows():
        if not row['Is_Category'] and pd.notnull(row['GPA_Score']) and row['Credits'].isdigit():
            cred = float(row['Credits'])
            score = float(row['GPA_Score'])
            total_points += (cred * score)
            total_credits += cred
            
    final_gpa = total_points / total_credits if total_credits > 0 else 0
    return df, final_gpa, total_credits

def generate_pdf(metadata, df, final_gpa, total_credits, signature_img, supervisor_name):
    """Génère le PDF final avec ReportLab."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=15*mm, leftMargin=15*mm, topMargin=15*mm, bottomMargin=15*mm)
    
    styles = getSampleStyleSheet()
    elements = []
    
    # --- HEADER ---
    # Logo (placeholder si pas d'image fournie, sinon utiliser l'image)
    try:
        # On essaie de charger le logo s'il existe dans le dossier courant
        logo = RLImage("logo_cesi.png", width=50*mm, height=20*mm)
        logo.hAlign = 'LEFT'
        elements.append(logo)
    except:
        elements.append(Paragraph("[LOGO CESI]", styles['Heading1']))

    elements.append(Spacer(1, 10))
    
    # Titre
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], alignment=1, fontSize=16, spaceAfter=20)
    elements.append(Paragraph("STATEMENT NOTES", title_style))
    
    # Date
    date_str = datetime.now().strftime("%A %B %d, %Y")
    elements.append(Paragraph(f"{date_str}", styles['Normal']))
    elements.append(Spacer(1, 10))
    
    # Infos Étudiant
    info_style = ParagraphStyle('Info', parent=styles['Normal'], leading=14)
    elements.append(Paragraph(f"<b>Program:</b> {metadata['program']}", info_style))
    elements.append(Paragraph(f"<b>Degree or award:</b> Master's Degree in Embedded Systems", info_style)) # En dur ou dynamique si besoin
    elements.append(Paragraph(f"<b>Campus:</b> {metadata['campus']}", info_style))
    elements.append(Paragraph(f"<b>Class:</b> {metadata['class_name']}", info_style))
    elements.append(Paragraph(f"<b>Name:</b> {metadata['name']}", info_style))
    elements.append(Spacer(1, 20))
    
    # --- TABLEAU ---
    # Préparation des données pour ReportLab
    table_data = [["Course / L.U.", "Credit amount", "European Evaluation\n(ECTS Grade)", "GPA score"]]
    
    for _, row in df.iterrows():
        course_name = row['English_Course']
        if row['Is_Category']:
            # Ligne de catégorie
            table_data.append([course_name, "", "", ""])
        else:
            # Ligne de cours
            gpa_str = str(row['GPA_Score']) if pd.notnull(row['GPA_Score']) else ""
            table_data.append([
                course_name,
                row['Credits'],
                row['ECTS_Grade'],
                gpa_str
            ])
            
    # Ligne TOTAL
    table_data.append(["TOTAL", str(int(total_credits)), "", f"{final_gpa:.1f}"])
    
    # Style du tableau
    t = Table(table_data, colWidths=[90*mm, 30*mm, 40*mm, 25*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.white),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'), # Alignement cours à gauche
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        # Style spécifique pour les catégories (Gras, pas de bordure interne si voulu, ici simple)
        # On pourrait ajouter du style conditionnel ici si nécessaire
    ]))
    elements.append(t)
    
    elements.append(Spacer(1, 30))
    
    # --- FOOTER / SIGNATURE ---
    elements.append(Paragraph(f"Program supervisor: {supervisor_name}", styles['Normal']))
    
    if signature_img:
        # Sauvegarde temporaire de l'image signature
        sig_io = BytesIO()
        signature_img.save(sig_io, format='PNG')
        sig_io.seek(0)
        rl_sig = RLImage(sig_io, width=40*mm, height=20*mm)
        rl_sig.hAlign = 'LEFT'
        elements.append(rl_sig)
    
    # Génération
    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- INTERFACE STREAMLIT ---

st.set_page_config(page_title="CESI GPA Converter", layout="wide")

st.title("📄 Convertisseur Relevé de Notes -> Statement Notes (GPA)")
st.markdown("""
Cette application permet de générer un 'Statement Notes' en anglais avec calcul automatique du GPA 
à partir d'un relevé de notes français du CESI.
""")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("1. Importation")
    uploaded_file = st.file_uploader("Chargez le relevé de notes (PDF)", type="pdf")
    
    st.subheader("2. Paramètres Globaux")
    supervisor_name = st.text_input("Program Supervisor", value="Jules HAMDAN")
    program_name = st.text_input("Program Name", value="Embedded Systems engineering program")

if uploaded_file:
    # 1. Parsing
    text_content, raw_table_data = extract_data_from_pdf(uploaded_file)
    metadata = parse_metadata(text_content)
    
    # Override metadata avec les inputs utilisateurs si nécessaire
    metadata['program'] = program_name
    
    # Nettoyage initial
    df_initial = clean_table_data(raw_table_data)
    
    with col2:
        st.subheader("3. Vérification et Édition des données")
        st.info("💡 Vérifiez les traductions. Si une matière est nouvelle ou mal traduite, modifiez la colonne 'English_Course'.")
        
        # Éditeur de données interactif
        edited_df = st.data_editor(
            df_initial,
            column_config={
                "French_Course": "Matière (FR)",
                "English_Course": "Matière (EN) - À éditer",
                "Credits": "Crédits",
                "ECTS_Grade": "Note ECTS",
                "Is_Category": "Est une catégorie ?"
            },
            use_container_width=True,
            num_rows="dynamic",
            height=500
        )
        
        # Recalculer le GPA en temps réel basé sur les données éditées
        df_processed, final_gpa, total_credits = calculate_gpa(edited_df)
        
        st.metric(label="GPA Score Moyen Calculé", value=f"{final_gpa:.2f}")

    st.divider()
    
    st.subheader("4. Signature du Responsable")
    st.write("Signez dans la case ci-dessous :")
    
    # Canvas pour la signature
    canvas_result = st_canvas(
        stroke_width=2,
        stroke_color="#000000",
        background_color="#ffffff",
        height=150,
        width=400,
        drawing_mode="freedraw",
        key="canvas",
    )

    if st.button("Générer le Statement Notes (PDF)", type="primary"):
        if canvas_result.image_data is not None:
            # Conversion de la signature numpy array en image PIL
            signature_img = PILImage.fromarray(canvas_result.image_data.astype('uint8'), 'RGBA')
        else:
            signature_img = None
            
        # Génération du PDF
        pdf_buffer = generate_pdf(
            metadata, 
            df_processed, 
            final_gpa, 
            total_credits, 
            signature_img, 
            supervisor_name
        )
        
        st.success("PDF généré avec succès !")
        
        # Bouton de téléchargement
        st.download_button(
            label="⬇️ Télécharger le Statement Notes",
            data=pdf_buffer,
            file_name=f"Statement_notes_{metadata['name'].replace(' ', '_')}.pdf",
            mime="application/pdf"
        )

else:
    with col2:
        st.info("Veuillez charger un fichier PDF pour commencer.")
