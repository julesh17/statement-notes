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
# Cela permet de forcer les crédits même si l'étudiant a échoué (ex: Sciences pour l'ingénieur 1)
COURSE_DB = {
    "UE 5.1 Mathématiques pour l'ingénieur": {"en": "[S5] Mathematics for Engineers", "credits": 5},
    "UE 5.2 - Sciences pour l'ingénieur 1": {"en": "[S5] Science fundamentals 1", "credits": 7},
    "UE 6.1 Mathématiques pour l'ingénieur S6": {"en": "[S6] Mathematics for Engineers S6", "credits": 2},
    "UE 6.4 - Méthodes d'analyse et qualité": {"en": "[[S6] Analysis methods and quality", "credits": 2},
    "UE 5.3 - Electronique appliquée": {"en": "[S5] Applied electronics", "credits": 5},
    "UE 6.3 - Sciences du numérique 1": {"en": "[S6] Digital sciences 1", "credits": 8},
    "UE 5.5-Communication et créativité": {"en": "[S5] Communication and group creativity", "credits": 4},
    "UE 6.6-Accompagnement et suivi": {"en": "[S6] Engineer's behaviour (semester 6)", "credits": 2},
    "UE 5.6 - Evaluation entreprise": {"en": "[S5] Assessment by the company", "credits": 7},
    "UE 6.7 - Evaluation entreprise": {"en": "[S6] Assessment by the company", "credits": 8},
    "UE 5.4 - Anglais S5": {"en": "[S5] English", "credits": 2},
    "UE 6.5 - Anglais S6": {"en": "[S6] English", "credits": 2}
}

# Mapping pour les catégories (Traduction simple)
CATEGORY_MAPPING = {
    "Sciences de base": "Science Fundamentals",
    "Sciences et méthodes de l'ingénieur": "Engineering methodology",
    "Sciences et techniques de spécialité": "Industrial engineering techniques and systems",
    "Sciences humaines, économiques, juridiques et sociales": "Humanities",
    "Mission en entreprise": "Missions in company (professional experience)",
    "Langues": "Languages"
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
            table_data = max(tables, key=len) # Prend le plus grand tableau
            
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

def clean_and_process_table(raw_table):
    """Nettoie les données et applique les crédits fixes."""
    processed_rows = []
    start_index = 1 # Skip header
    
    for row in raw_table[start_index:]:
        clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
        
        if len(clean_row) >= 3:
            french_name = clean_row[0]
            grade_pdf = clean_row[2] # La note obtenue (A, B, Fx...)
            
            # 1. Vérifier si c'est un COURS connu dans la DB
            if french_name in COURSE_DB:
                info = COURSE_DB[french_name]
                english_name = info['en']
                credits_val = info['credits'] # On prend le crédit FIXE
                is_category = False
                
            # 2. Vérifier si c'est une CATÉGORIE
            elif french_name in CATEGORY_MAPPING:
                english_name = CATEGORY_MAPPING[french_name]
                credits_val = 0
                is_category = True
                
            # 3. Cas inconnu (fallback)
            else:
                english_name = french_name
                # Essayer de lire les crédits du PDF, sinon 0
                try:
                    credits_val = float(clean_row[1].replace(',', '.')) if clean_row[1] else 0
                except:
                    credits_val = 0
                is_category = (clean_row[1] == "" and clean_row[2] == "")

            processed_rows.append({
                "English_Course": english_name,
                "Credits": credits_val, # C'est le crédit MAX (dénominateur)
                "ECTS_Grade": grade_pdf,
                "Is_Category": is_category,
                "French_Ref": french_name # Pour info
            })
            
    return pd.DataFrame(processed_rows)

def calculate_gpa(df):
    """Calcule le GPA en utilisant les crédits fixes comme poids."""
    def get_gpa_points(grade):
        if not grade: return None
        return GPA_MAPPING.get(grade.upper(), 0.0)

    total_points = 0
    total_credits = 0
    
    # On itère pour calculer
    for index, row in df.iterrows():
        if not row['Is_Category']:
            points = get_gpa_points(row['ECTS_Grade'])
            
            if points is not None:
                # Calcul: (Note GPA * Crédits du module)
                weight = row['Credits']
                total_points += (points * weight)
                total_credits += weight
            
            # Ajout du score GPA individuel dans le DF pour affichage
            df.at[index, 'GPA_Score_Display'] = str(points) if points is not None else ""
        else:
            df.at[index, 'GPA_Score_Display'] = ""
            
    final_gpa = total_points / total_credits if total_credits > 0 else 0.0
    return df, final_gpa, total_credits

def generate_pdf(metadata, df, final_gpa, total_credits, signature_img, supervisor_name):
    """Génère le PDF 'Pixel Perfect'."""
    buffer = BytesIO()
    # Marges ajustées pour ressembler au doc officiel
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=15*mm, leftMargin=15*mm, topMargin=10*mm, bottomMargin=15*mm)
    
    styles = getSampleStyleSheet()
    elements = []
    
    # --- HEADER (Tableau invisible pour mise en page) ---
    # Col 1: Logo (Gauche), Col 2: Info (Droite)
    
    # Logo
    logo_img = None
    try:
        # preserveAspectRatio=True assure que le logo n'est pas aplati
        # On définit une largeur cible, la hauteur s'adapte
        logo_img = RLImage("logo_cesi.png", width=60*mm, height=25*mm, kind='proportional')
        logo_img.hAlign = 'LEFT'
    except:
        logo_img = Paragraph("<b>CESI LOGO</b>", styles['Normal'])

    # Titre et Date (Alignés à droite comme demandé)
    header_right_style = ParagraphStyle('HeaderRight', parent=styles['Normal'], alignment=TA_RIGHT, fontSize=12)
    date_str = datetime.now().strftime("%A %B %d, %Y") # ex: Tuesday December 2, 2025
    
    title_para = Paragraph("<b>STATEMENT NOTES</b>", header_right_style)
    date_para = Paragraph(date_str, header_right_style)
    
    # Construction du tableau d'en-tête
    header_data = [[logo_img, [title_para, date_para]]]
    header_table = Table(header_data, colWidths=[100*mm, 80*mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 15*mm))
    
    # --- INFOS ÉTUDIANT ---
    # CESI École d'ingénieurs (simulé du doc source)
    elements.append(Paragraph("<b>CESI</b><br/>ÉCOLE D'INGÉNIEURS", styles['Normal']))
    elements.append(Spacer(1, 5*mm))

    info_style = ParagraphStyle('Info', parent=styles['Normal'], leading=15, fontSize=10)
    elements.append(Paragraph(f"<b>Program:</b> {metadata['program']}", info_style))
    elements.append(Paragraph(f"<b>Degree or award:</b> Master's Degree in Embedded Systems", info_style))
    elements.append(Paragraph(f"<b>Campus:</b> {metadata['campus']}", info_style))
    elements.append(Paragraph(f"<b>Class:</b> {metadata['class_name']}", info_style))
    elements.append(Paragraph(f"<b>Name:</b> {metadata['name']}", info_style))
    elements.append(Spacer(1, 10*mm))
    
    elements.append(Paragraph("The following table:", styles['Normal']))
    elements.append(Spacer(1, 2*mm))

    # --- TABLEAU DE NOTES ---
    # En-têtes
    # Note: On utilise des retours à la ligne manuelles pour coller à l'aspect visuel
    table_data = [
        [
            "Course / L.U.", 
            "Credit amount", 
            "European\nEvaluation\n(ECTS Grade)", 
            "GPA score"
        ]
    ]
    
    # Styles conditionnels pour le tableau
    table_styles = [
        # Style global
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), # Header en gras
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), # Tout centré par défaut
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),    # Sauf 1ère colonne (Noms cours) à gauche
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black), # Quadrillage fin
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]
    
    row_idx = 1 # On commence après le header
    
    for _, row in df.iterrows():
        c_name = row['English_Course']
        
        if row['Is_Category']:
            # Ligne Catégorie : Cellules fusionnées
            table_data.append([c_name, "", "", ""])
            # Fusion de la ligne (span de col 0 à col 3)
            table_styles.append(('SPAN', (0, row_idx), (-1, row_idx)))
            # Gras pour la catégorie
            table_styles.append(('FONTNAME', (0, row_idx), (0, row_idx), 'Helvetica-Bold'))
            # Pas de fond spécifique demandé, mais souvent gris clair ? On laisse blanc pour 'identique'.
        else:
            # Ligne Cours normal
            c_credits = str(int(row['Credits']))
            c_grade = row['ECTS_Grade']
            c_gpa = str(row['GPA_Score_Display'])
            table_data.append([c_name, c_credits, c_grade, c_gpa])
            
        row_idx += 1
        
    # Ligne TOTAL
    # Le mot "TOTAL" est souvent dans la 1ère case, mais aligné à droite de cette case, ou fusionné ?
    # Pour faire "identique" au fichier anglais qui a souvent "TOTAL" dans la colonne 1 mais aligné droite
    table_data.append(["TOTAL", str(int(total_credits)), "", f"{final_gpa:.1f}"])
    
    # Style ligne TOTAL
    table_styles.append(('FONTNAME', (0, row_idx), (-1, row_idx), 'Helvetica-Bold'))
    table_styles.append(('ALIGN', (0, row_idx), (0, row_idx), 'RIGHT')) # "TOTAL" aligné à droite dans sa case
    
    # Création du tableau ReportLab
    # Largeurs ajustées pour ressembler à l'exemple
    t = Table(table_data, colWidths=[95*mm, 25*mm, 30*mm, 25*mm])
    t.setStyle(TableStyle(table_styles))
    
    elements.append(t)
    elements.append(Spacer(1, 20*mm))
    
    # --- SIGNATURE (Alignée à droite) ---
    
    # Conteneur pour la signature
    # On crée une table invisible de 2 colonnes pour pousser la signature à droite
    
    sig_content = []
    sig_content.append(Paragraph(f"<b>Program supervisor:</b> {supervisor_name}", ParagraphStyle('SigText', alignment=TA_LEFT)))
    
    if signature_img:
        sig_io = BytesIO()
        signature_img.save(sig_io, format='PNG')
        sig_io.seek(0)
        # Image signature
        rl_sig = RLImage(sig_io, width=40*mm, height=20*mm, kind='proportional')
        rl_sig.hAlign = 'LEFT' # Alignée à gauche DANS la cellule de droite
        sig_content.append(rl_sig)
    
    # Table signature : Col1 (Vide/Spacer), Col2 (Signature)
    sig_table_data = [["", sig_content]]
    sig_table = Table(sig_table_data, colWidths=[100*mm, 75*mm])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
    ]))
    
    elements.append(sig_table)
    
    # Génération
    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- MAIN APP ---

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
    # Traitement
    text, raw_table = extract_data_from_pdf(uploaded_file)
    meta = parse_metadata(text)
    
    # Override
    meta['program'] = program
    
    # Création du DataFrame
    df_processed = clean_and_process_table(raw_table)
    
    # Calculs
    df_calc, gpa_val, total_creds = calculate_gpa(df_processed)
    
    with col_preview:
        st.subheader("4. Aperçu des données")
        st.info(f"Moyenne GPA calculée : **{gpa_val:.2f}** (sur {int(total_creds)} crédits)")
        
        # Affichage du tableau pour vérification (non éditable ici pour garantir la structure, ou éditable si besoin)
        st.dataframe(
            df_calc[['English_Course', 'Credits', 'ECTS_Grade', 'GPA_Score_Display']],
            column_config={
                "English_Course": "Course Name",
                "Credits": "Credits (Fixed)",
                "ECTS_Grade": "Grade",
                "GPA_Score_Display": "GPA Points"
            },
            hide_index=True,
            use_container_width=True
        )
        
        st.write("Si tout semble correct, générez le PDF ci-dessous.")
        
        if st.button("📄 Générer et Télécharger le PDF", type="primary"):
            # Récupération image signature
            sig_img = None
            if canvas_result.image_data is not None:
                 # Vérifier si l'utilisateur a vraiment dessiné (pas juste un canvas blanc vide)
                if canvas_result.image_data.any():
                    sig_img = PILImage.fromarray(canvas_result.image_data.astype('uint8'), 'RGBA')
            
            pdf_bytes = generate_pdf(meta, df_calc, gpa_val, total_creds, sig_img, supervisor)
            
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
