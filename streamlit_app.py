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
    "Fx": 0.0, # Fx = 0.0 (régression GPA corrigée ici si jamais Fx n'était pas traité)
    "F": 0.0
}

# Base de données des cours (Traduction + Crédits FIXES)
# CORRECTION : Ajout du tiret "-" pour UE 5.1 et UE 6.1 pour assurer le match des clés.
COURSE_INFO_DB = {
    # COURSES (avec crédits pour le calcul GPA)
    "UE 5.1 - Mathématiques pour l'ingénieur": {"en": "[S5] Mathematics for Engineers", "credits": 5, "type": "COURSE"}, 
    "UE 5.2 - Sciences pour l'ingénieur 1": {"en": "[S5] Science fundamentals 1", "credits": 7, "type": "COURSE"}, # Crédits fixes à 7
    "UE 6.1 - Mathématiques pour l'ingénieur S6": {"en": "[S6] Mathematics for Engineers S6", "credits": 2, "type": "COURSE"}, 
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
    start_index = 1 # Skip header du PDF français
    
    for row in raw_table[start_index:]:
        # Nettoyage des cellules
        clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
        
        if len(clean_row) >= 3 and clean_row[0]:
            french_name = clean_row[0].strip()
            grade_pdf = clean_row[2].strip() 
            
            # Tente de matcher la clé du PDF (avec/sans tiret)
            info = COURSE_INFO_DB.get(french_name)
            
            # Tente de matcher sans le tiret s'il est présent dans le PDF, car le DB peut être sans tiret
            if not info and " - " in french_name:
                 info = COURSE_INFO_DB.get(french_name.replace(" - ", " ").strip())

            if info:
                english_name = info['en']
                credits_val = info['credits']
                is_category = (info['type'] == "CATEGORY")
            else:
                # Cas inconnu: le français est copié dans l'anglais, crédits à 0 pour éviter de fausser le GPA
                english_name = french_name
                credits_val = 0 
                is_category = (clean_row[1] == "" and clean_row[2] == "") 

            processed_rows.append({
                "French_Course": french_name,
                "English_Course": english_name, 
                "Credits": credits_val,         
                "ECTS_Grade": grade_pdf,        
                "Is_Category": is_category
            })
            
    return pd.DataFrame(processed_rows)

def calculate_gpa_from_edited_df(df):
    """Calcule le GPA en utilisant les crédits fixes comme poids."""
    def get_gpa_points(grade):
        if not grade: return None
        return GPA_MAPPING.get(grade.upper(), 0.0)

    total_points = 0
    total_credits = 0
    
    for index, row in df.iterrows():
        if not row['Is_Category']:
            points = get_gpa_points(row['ECTS_Grade'])
            
            if points is not None:
                # Logique de calcul GPA corrigée et vérifiée : (Note GPA * Crédits FIXES)
                weight = row['Credits']
                total_points += (points * weight)
                total_credits += weight
            
            # Ajout du score GPA individuel dans le DF pour affichage
            df.at[index, 'GPA_Score_Display'] = f"{points:.1f}" if points is not None else ""
        else:
            df.at[index, 'GPA_Score_Display'] = ""
            
    final_gpa = total_points / total_credits if total_credits > 0 else 0.0
    return df, final_gpa, total_credits

def generate_pdf(metadata, df, final_gpa, total_creds, signature_img, supervisor_name):
    """Génère le PDF final avec ReportLab."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=15*mm, leftMargin=15*mm, topMargin=10*mm, bottomMargin=15*mm)
    
    styles = getSampleStyleSheet()
    elements = []
    
    # --- HEADER (Logo + Titre/Date alignés à droite) ---
    logo_img = None
    try:
        logo_img = RLImage("logo_cesi.png", width=60*mm, height=25*mm, kind='proportional')
        logo_img.hAlign = 'LEFT'
    except:
        logo_img = Paragraph("<b>[LOGO CESI]</b>", styles['Normal'])

    header_right_style = ParagraphStyle('HeaderRight', parent=styles['Normal'], alignment=TA_RIGHT, fontSize=12)
    date_str = datetime.now().strftime("%A %B %d, %Y")
    
    title_para = Paragraph("<b>STATEMENT NOTES</b>", header_right_style)
    date_para = Paragraph(date_str, header_right_style)
    
    header_data = [[logo_img, [title_para, date_para]]]
    header_table = Table(header_data, colWidths=[100*mm, 80*mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 20*mm))

    # --- INFOS ÉTUDIANT ---
    # CESI et phrase "The following table" retirées
    
    info_style = ParagraphStyle('Info', parent=styles['Normal'], leading=15, fontSize=10)
    elements.append(Paragraph(f"<b>Program:</b> {metadata['program']}", info_style))
    elements.append(Paragraph(f"<b>Degree or award:</b> Master's Degree in Embedded Systems", info_style))
    elements.append(Paragraph(f"<b>Campus:</b> {metadata['campus']}", info_style))
    elements.append(Paragraph(f"<b>Class:</b> {metadata['class_name']}", info_style))
    elements.append(Paragraph(f"<b>Name:</b> {metadata['name']}", info_style))
    elements.append(Spacer(1, 12*mm))

    # --- TABLEAU DE NOTES ---
    
    table_data = [
        [
            "Course / L.U.", 
            "Credit amount", 
            "European\nEvaluation\n(ECTS Grade)", 
            "GPA score"
        ]
    ]
    
    table_styles = [
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]
    
    row_idx = 1 
    
    for _, row in df.iterrows():
        c_name = row['English_Course']
        
        if row['Is_Category']:
            # Ligne Catégorie : fusion des cellules
            table_data.append([c_name, "", "", ""])
            table_styles.append(('SPAN', (0, row_idx), (-1, row_idx)))
            table_styles.append(('FONTNAME', (0, row_idx), (0, row_idx), 'Helvetica-Bold'))
        else:
            # Ligne Cours normal
            c_credits = str(int(row['Credits']))
            c_grade = row['ECTS_Grade']
            c_gpa = row['GPA_Score_Display']
            table_data.append([c_name, c_credits, c_grade, c_gpa])
            
        row_idx += 1
        
    # Ligne TOTAL
    # Le GPA est formaté à un chiffre après la virgule, comme dans l'exemple
    table_data.append(["TOTAL", str(int(total_creds)), "", f"{final_gpa:.1f}"])
    
    # Style ligne TOTAL: Gras, "TOTAL" aligné à droite dans sa case
    table_styles.append(('FONTNAME', (0, row_idx), (-1, row_idx), 'Helvetica-Bold'))
    table_styles.append(('ALIGN', (0, row_idx), (0, row_idx), 'RIGHT'))
    
    t = Table(table_data, colWidths=[95*mm, 25*mm, 30*mm, 25*mm])
    t.setStyle(TableStyle(table_styles))
    
    elements.append(t)
    elements.append(Spacer(1, 20*mm))
    
    # --- SIGNATURE (Alignée à droite) ---
    
    sig_content = []
    sig_content.append(Paragraph(f"<b>Program supervisor:</b> {supervisor_name}", ParagraphStyle('SigText', alignment=TA_LEFT, fontSize=10)))
    
    if signature_img:
        sig_io = BytesIO()
        signature_img.save(sig_io, format='PNG')
        sig_io.seek(0)
        rl_sig = RLImage(sig_io, width=40*mm, height=20*mm, kind='proportional')
        rl_sig.hAlign = 'LEFT'
        sig_content.append(rl_sig)
    
    # Table signature : Col1 (Vide/Spacer), Col2 (Signature) pour l'alignement à droite
    sig_table_data = [["", sig_content]]
    sig_table = Table(sig_table_data, colWidths=[100*mm, 75*mm])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
    ]))
    
    elements.append(sig_table)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- INTERFACE STREAMLIT ---

st.set_page_config(page_title="CESI Statement Notes", layout="wide")

st.title("🎓 Générateur de Statement Notes (GPA)")
st.markdown("Convertisseur de relevé de notes français vers format anglais (Statement Notes) avec calcul GPA standardisé.")

col_input, col_preview = st.columns([1, 1.5])

with col_input:
    st.subheader("1. Données d'entrée")
    uploaded_file = st.file_uploader("Relevé de notes (PDF français)", type="pdf")
    
    st.markdown("---")
    st.subheader("2. Paramètres")
    supervisor = st.text_input("Responsable de promotion", value="Jules HAMDAN")
    program = st.text_input("Programme", value="Embedded Systems engineering program")
    
    st.markdown("---")
    st.subheader("3. Signature")
    st.caption("Signez dans la zone ci-dessous :")
    canvas_result = st_canvas(
        stroke_width=2,
        stroke_color="black",
        background_color="white",
        height=120,
        width=300,
        drawing_mode="freedraw",
        key="sig_canvas",
    )

if uploaded_file:
    # 1. Parsing
    text, raw_table = extract_data_from_pdf(uploaded_file)
    meta = parse_metadata(text)
    meta['program'] = program # Override

    # 2. Préparation pour l'édition (avec traduction et crédits fixes)
    df_initial_for_edit = prepare_df_for_edit(raw_table)

    with col_preview:
        st.subheader("4. Vérification, Traduction et Calcul")
        st.info("💡 **GPA corrigé** : La traduction par défaut pour les cours de Mathématiques est rétablie et les crédits fixes sont correctement appliqués. Vous pouvez modifier la colonne **'Nom Anglais (Éditable)'** si besoin.")

        # Éditeur de données interactif
        edited_df = st.data_editor(
            df_initial_for_edit,
            column_config={
                "French_Course": st.column_config.TextColumn("Nom Français (Ref.)", disabled=True),
                "English_Course": st.column_config.TextColumn("Nom Anglais (Éditable)", width="large"),
                "Credits": st.column_config.NumberColumn("Crédits (Fixes)", disabled=True),
                "ECTS_Grade": st.column_config.TextColumn("Note ECTS", disabled=True),
                "Is_Category": st.column_config.CheckboxColumn("Est une catégorie ?", disabled=True, default=False),
            },
            use_container_width=True,
            num_rows="fixed",
            hide_index=True
        )

        # 3. Calcul GPA basé sur les données éditées
        df_final_for_pdf, gpa_val, total_creds = calculate_gpa_from_edited_df(edited_df)

        st.metric(label="Moyenne GPA Calculée", value=f"{gpa_val:.2f}")

        st.write("Générer le PDF ci-dessous pour un document conforme.")
        
        if st.button("📄 Générer et Télécharger le PDF", type="primary"):
            # Récupération image signature
            sig_img = None
            if canvas_result.image_data is not None and canvas_result.image_data.any():
                sig_img = PILImage.fromarray(canvas_result.image_data.astype('uint8'), 'RGBA')
            
            pdf_bytes = generate_pdf(meta, df_final_for_pdf, gpa_val, total_creds, sig_img, supervisor)
            
            st.success("Document généré !")
            st.download_button(
                label="⬇️ Télécharger le fichier PDF",
                data=pdf_bytes,
                file_name=f"Statement_Notes_{meta['name'].replace(' ', '_')}.pdf",
                mime="application/pdf"
            )
else:
    with col_preview:
        st.info("Attente du fichier source...")
