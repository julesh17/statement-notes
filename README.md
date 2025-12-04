# 🎓 Générateur de Statement Notes et Calculateur de GPA (CESI)

## 🚀 Accès à l'Application

Vous pouvez accéder et utiliser l'application directement via ce lien :

[**Lien vers l'application Streamlit**](https://statement-notes.streamlit.app/)

***

## 🎯 Objectif de l'Application

Cet outil Streamlit est conçu pour les étudiants CESI (École d'Ingénieurs) ayant besoin de convertir leur **Relevé de Notes officiel français** en un document standard international appelé **"Statement Notes"**.

L'application réalise les opérations suivantes :

1.  **Extraction de données** : Analyse du PDF français pour récupérer les noms de cours, les notes ECTS et les informations de l'étudiant.
2.  **Traduction par défaut** : Application des traductions anglaises par défaut pour les cours reconnus.
3.  **Calcul du GPA** : Utilisation d'une base de données interne de crédits fixes pour calculer la moyenne **GPA (Grade Point Average)** selon le standard américain, basé sur l'échelle ECTS (A=4.0, B=3.0, etc.). Ce calcul est essentiel pour les candidatures à l'étranger.
4.  **Génération de document** : Création d'un fichier PDF au format "Statement Notes", sans les mentions administratives françaises superflues, avec les informations et la signature du responsable de promotion.

***

## 📝 Mode d'Emploi

L'interface est divisée en deux colonnes : **Données d'entrée** et **Vérification**.

### 1. Préparation (Colonne de gauche : Données d'entrée)

| Section | Action | Description |
| :--- | :--- | :--- |
| **1. Données d'entrée** | Téléversement du PDF | Chargez votre **Relevé de Notes officiel CESI au format PDF français**. |
| **2. Paramètres** | Entrée de texte | Vérifiez ou modifiez le nom du **Responsable de promotion** et le **Programme** (la valeur par défaut devrait être correcte). |
| **3. Signature** | Dessin | Utilisez la zone de dessin pour apposer une signature numérique (celle du responsable ou une autre) qui sera intégrée au PDF final. |

### 2. Vérification et Ajustements (Colonne de droite : Vérification)

Une fois le PDF chargé, un tableau interactif (`st.data_editor`) apparaît :

* **Vérification de la Traduction** : L'application remplit la colonne **"Nom Anglais (Éditable)"** avec les traductions par défaut. Si un cours est inconnu ou si vous souhaitez ajuster la formulation, **vous pouvez modifier cette colonne directement dans le tableau**.
* **Calcul GPA** : L'application affiche la **"Moyenne GPA Calculée"** en temps réel. Ce calcul se base sur la grille de conversion GPA/ECTS et sur les crédits fixes associés à chaque module d'enseignement (ces crédits sont bloqués et ne sont pas modifiables).

### 3. Génération du PDF

1.  Après avoir vérifié les traductions et le GPA, cliquez sur le bouton **📄 Générer et Télécharger le PDF**.
2.  Un bouton **⬇️ Télécharger le fichier PDF** apparaîtra, vous permettant de sauvegarder votre document "Statement Notes" final.

***

## 💡 Logique de Calcul du GPA

Le GPA est calculé selon la formule standard, en utilisant les crédits ECTS comme poids, après conversion de la note ECTS (A, B, C, D, E, Fx) en point GPA (4.0 à 0.0) :

$$\text{GPA} = \frac{\sum (\text{Crédits du Cours} \times \text{Points GPA de la Note})}{\sum (\text{Crédits du Cours})}$$

* **A** : 4.0
* **B** : 3.0
* **C** : 2.0
* **D** : 1.7
* **E** : 1.0
* **FX/Fx/F** : 0.0
