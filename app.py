from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from PIL import Image
import re
import os
import sys
import json
from datetime import datetime
from werkzeug.utils import secure_filename
import cv2
import numpy as np

# Intégration du repository pytesseract local
# Ajouter le chemin du repository local au PYTHONPATH
pytesseract_path = os.path.join(os.path.dirname(__file__), 'pytesseract')
pytesseract_imported = False

# Essayer d'importer depuis le repository local d'abord
if os.path.exists(pytesseract_path) and pytesseract_path not in sys.path:
    sys.path.insert(0, pytesseract_path)
    try:
        import pytesseract
        pytesseract_imported = True
        print(f"✅ Utilisation de pytesseract local depuis: {pytesseract_path}")
    except ImportError:
        # Retirer le chemin si l'import échoue
        if pytesseract_path in sys.path:
            sys.path.remove(pytesseract_path)

# Fallback vers l'installation pip si le local n'est pas disponible
if not pytesseract_imported:
    try:
        import pytesseract
        print("ℹ️  Utilisation de pytesseract installé via pip")
    except ImportError:
        print("❌ ERREUR: pytesseract n'est pas disponible!")
        print("   Installez-le avec: pip install pytesseract")
        raise

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['FACTURES_FOLDER'] = 'factures_sauvegardees'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'

# Créer les dossiers nécessaires
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['FACTURES_FOLDER'], exist_ok=True)

# Configuration Tesseract - Détection automatique sur Windows
def find_tesseract():
    """Trouve automatiquement Tesseract OCR sur Windows"""
    import shutil
    
    # Vérifier si tesseract est dans le PATH (priorité)
    try:
        tesseract_path = shutil.which('tesseract')
        if tesseract_path and os.path.exists(tesseract_path):
            return tesseract_path
    except:
        pass
    
    # Chercher dans les emplacements courants
    username = os.getenv('USERNAME', '')
    project_dir = os.path.dirname(os.path.abspath(__file__))
    
    possible_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        r'C:\Tesseract-OCR\tesseract.exe',
        r'D:\Program Files\Tesseract-OCR\tesseract.exe',
        r'D:\Tesseract-OCR\tesseract.exe',
    ]
    
    # Ajouter les chemins dans le dossier du projet
    project_paths = [
        os.path.join(project_dir, 'tesseract', 'tesseract.exe'),
        os.path.join(project_dir, 'Tesseract-OCR', 'tesseract.exe'),
        os.path.join(project_dir, 'pytesseract', 'tesseract', 'tesseract.exe'),
    ]
    possible_paths.extend(project_paths)
    
    # Ajouter le chemin utilisateur si disponible
    if username:
        possible_paths.append(
            r'C:\Users\{}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'.format(username)
        )
        possible_paths.append(
            r'C:\Users\{}\AppData\Local\Tesseract-OCR\tesseract.exe'.format(username)
        )
    
    # Chercher dans les emplacements courants
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    # Chercher récursivement dans Program Files (dernier recours)
    try:
        for root, dirs, files in os.walk(r'C:\Program Files'):
            if 'tesseract.exe' in files:
                return os.path.join(root, 'tesseract.exe')
    except:
        pass
    
    return None

def verify_tesseract_installation():
    """Vérifie que Tesseract est correctement installé et accessible"""
    tesseract_path = find_tesseract()
    
    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
        # Tester si Tesseract fonctionne
        try:
            version = pytesseract.get_tesseract_version()
            print(f"✅ Tesseract OCR trouvé: {tesseract_path}")
            print(f"   Version: {version}")
            return True
        except Exception as e:
            print(f"⚠️  Tesseract trouvé mais erreur lors de la vérification: {e}")
            return False
    else:
        return False

# Vérifier l'installation de Tesseract au démarrage
TESSERACT_AVAILABLE = verify_tesseract_installation()

if not TESSERACT_AVAILABLE:
    print("\n" + "="*70)
    print("⚠️  ATTENTION: Tesseract OCR n'est pas installé ou introuvable!")
    print("="*70)
    print("\n📌 Note: Le wrapper Python 'pytesseract' est déjà intégré dans le projet.")
    print("   Mais Tesseract OCR (le programme C++) doit être installé séparément.")
    print("\n📥 Pour installer Tesseract OCR sur Windows:")
    print("\n   Méthode 1 - Installation manuelle (Recommandée):")
    print("   1. Téléchargez depuis: https://github.com/UB-Mannheim/tesseract/wiki")
    print("   2. Exécutez l'installateur (ex: tesseract-ocr-w64-setup-5.x.x.exe)")
    print("   3. ⚠️  IMPORTANT: Cochez 'Add to PATH' pendant l'installation")
    print("   4. Sélectionnez les langues: French (fra) et English (eng)")
    print("   5. Redémarrez votre terminal/IDE après l'installation")
    print("\n   Méthode 2 - Via winget (Windows 10/11):")
    print("   Ouvrez PowerShell en tant qu'administrateur et exécutez:")
    print("   winget install --id UB-Mannheim.TesseractOCR")
    print("\n   Méthode 3 - Via Chocolatey (si installé):")
    print("   choco install tesseract")
    print("\n   Méthode 4 - Script d'aide:")
    print("   Exécutez: install_tesseract.bat")
    print("\n   ⚠️  Après l'installation, REDÉMARREZ votre terminal/IDE")
    print("   puis relancez l'application Flask.")
    print("="*70 + "\n")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def save_facture(invoice_data, annotated_filename, original_filename):
    """Sauvegarde une facture dans le système"""
    facture_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    facture_info = {
        'id': facture_id,
        'date_creation': datetime.now().isoformat(),
        'date_facture': invoice_data.get('date', ''),
        'numero_facture': invoice_data.get('numero_facture', ''),
        'fournisseur': invoice_data.get('fournisseur', ''),
        'montant_ht': invoice_data.get('montant_ht', ''),
        'montant_ttc': invoice_data.get('montant_ttc', ''),
        'tva': invoice_data.get('tva', ''),
        'devise': invoice_data.get('devise', 'EUR'),
        'adresse': invoice_data.get('adresse', ''),
        'annotated_image': annotated_filename,
        'original_filename': original_filename
    }
    
    # Sauvegarder dans un fichier JSON
    factures_file = os.path.join(app.config['FACTURES_FOLDER'], 'factures.json')
    
    # Charger les factures existantes
    factures = []
    if os.path.exists(factures_file):
        try:
            with open(factures_file, 'r', encoding='utf-8') as f:
                factures = json.load(f)
        except:
            factures = []
    
    # Ajouter la nouvelle facture
    factures.append(facture_info)
    
    # Sauvegarder
    with open(factures_file, 'w', encoding='utf-8') as f:
        json.dump(factures, f, ensure_ascii=False, indent=2)
    
    # Copier l'image annotée dans le dossier factures
    source_path = os.path.join(app.config['UPLOAD_FOLDER'], annotated_filename)
    dest_path = os.path.join(app.config['FACTURES_FOLDER'], annotated_filename)
    if os.path.exists(source_path):
        import shutil
        shutil.copy2(source_path, dest_path)
    
    return facture_id

def load_all_factures():
    """Charge toutes les factures sauvegardées"""
    factures_file = os.path.join(app.config['FACTURES_FOLDER'], 'factures.json')
    
    if not os.path.exists(factures_file):
        return []
    
    try:
        with open(factures_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def delete_facture(facture_id):
    """Supprime une facture par son ID"""
    factures_file = os.path.join(app.config['FACTURES_FOLDER'], 'factures.json')
    
    if not os.path.exists(factures_file):
        return False
    
    try:
        # Charger les factures existantes
        with open(factures_file, 'r', encoding='utf-8') as f:
            factures = json.load(f)
        
        # Trouver et supprimer la facture
        facture_to_delete = None
        for facture in factures:
            if facture.get('id') == facture_id:
                facture_to_delete = facture
                break
        
        if facture_to_delete:
            # Supprimer l'image annotée si elle existe
            annotated_image = facture_to_delete.get('annotated_image')
            if annotated_image:
                image_path = os.path.join(app.config['FACTURES_FOLDER'], annotated_image)
                if os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                    except:
                        pass
            
            # Supprimer la facture de la liste
            factures.remove(facture_to_delete)
            
            # Sauvegarder
            with open(factures_file, 'w', encoding='utf-8') as f:
                json.dump(factures, f, ensure_ascii=False, indent=2)
            
            return True
        return False
    except Exception as e:
        print(f"Erreur lors de la suppression: {e}")
        return False

def extract_invoice_data(text, ocr_data=None):
    """Extrait les informations structurées d'une facture depuis le texte OCR"""
    data = {
        'fournisseur': '',
        'date': '',
        'numero_facture': '',
        'montant_ht': '',
        'montant_ttc': '',
        'tva': '',
        'devise': 'EUR',
        'adresse': '',
        'texte_complet': text,
        'bounding_boxes': {
            'fournisseur': None,
            'date': None,
            'numero_facture': None,
            'montant_ht': None,
            'montant_ttc': None,
            'tva': None,
            'adresse': None
        }
    }
    
    lines = text.split('\n')
    
    # Extraire le numéro de facture
    facture_patterns = [
        r'facture\s*[n°N]?\s*:?\s*([A-Z0-9\-]+)',
        r'invoice\s*[n°N]?\s*:?\s*([A-Z0-9\-]+)',
        r'n°\s*:?\s*([A-Z0-9\-]+)',
        r'num[ée]ro\s*:?\s*([A-Z0-9\-]+)'
    ]
    for pattern in facture_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data['numero_facture'] = match.group(1)
            # Trouver les coordonnées si disponibles
            if ocr_data is not None:
                data['bounding_boxes']['numero_facture'] = find_text_coordinates(match.group(1), ocr_data)
            break
    
    # Extraire la date
    date_patterns = [
        r'(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
        r'(\d{1,2}\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4})',
        r'(\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2})'
    ]
    for pattern in date_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            date_str = matches[0] if isinstance(matches[0], str) else ' '.join(matches[0])
            data['date'] = date_str
            if ocr_data is not None:
                data['bounding_boxes']['date'] = find_text_coordinates(date_str, ocr_data)
            break
    
    # Extraire les montants
    montant_patterns = [
        r'total\s+ttc\s*:?\s*([\d\s,\.]+)\s*([€$£]?)',
        r'ttc\s*:?\s*([\d\s,\.]+)\s*([€$£]?)',
        r'total\s*:?\s*([\d\s,\.]+)\s*([€$£]?)',
        r'montant\s+ttc\s*:?\s*([\d\s,\.]+)\s*([€$£]?)'
    ]
    for pattern in montant_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            montant = match.group(1).replace(' ', '').replace(',', '.')
            data['montant_ttc'] = montant
            if match.group(2):
                data['devise'] = match.group(2)
            if ocr_data is not None:
                data['bounding_boxes']['montant_ttc'] = find_text_coordinates(montant, ocr_data)
            break
    
    # Extraire HT
    ht_patterns = [
        r'total\s+ht\s*:?\s*([\d\s,\.]+)',
        r'ht\s*:?\s*([\d\s,\.]+)',
        r'montant\s+ht\s*:?\s*([\d\s,\.]+)'
    ]
    for pattern in ht_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            montant = match.group(1).replace(' ', '').replace(',', '.')
            data['montant_ht'] = montant
            if ocr_data is not None:
                data['bounding_boxes']['montant_ht'] = find_text_coordinates(montant, ocr_data)
            break
    
    # Extraire TVA (montant ou pourcentage)
    # Patterns pour pourcentage TVA
    tva_pct_patterns = [
        r'tva\s*:?\s*([\d\s,\.]+)\s*%',  # TVA: 20%
        r'taxe\s*:?\s*([\d\s,\.]+)\s*%',
        r't\.v\.a\.\s*:?\s*([\d\s,\.]+)\s*%',
        r't\.v\.a\s*:?\s*([\d\s,\.]+)\s*%',
        r'tva\s+([\d\s,\.]+)\s*%',  # TVA 20%
        r'([\d\s,\.]+)\s*%\s*tva',  # 20% TVA
        r'taux\s+tva\s*:?\s*([\d\s,\.]+)\s*%',
    ]
    
    # Patterns pour montant TVA
    tva_montant_patterns = [
        r'tva\s*:?\s*([\d\s,\.]+)\s*([€$£])',  # TVA: 159.05€
        r'taxe\s*:?\s*([\d\s,\.]+)\s*([€$£])',
        r't\.v\.a\.\s*:?\s*([\d\s,\.]+)\s*([€$£])',
        r'montant\s+tva\s*:?\s*([\d\s,\.]+)\s*([€$£])?',
        r'tva\s+([\d\s,\.]+)\s*([€$£])',  # TVA 159.05€
    ]
    
    tva_montant = None
    tva_pourcentage = None
    
    # Chercher d'abord un pourcentage
    for pattern in tva_pct_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            tva_val = match.group(1).replace(' ', '').replace(',', '.')
            try:
                tva_num = float(tva_val)
                if 0 <= tva_num <= 30:  # Pourcentage raisonnable
                    tva_pourcentage = tva_num
                    data['tva'] = f"{tva_num:.2f}%"
                    if ocr_data is not None:
                        data['bounding_boxes']['tva'] = find_text_coordinates(tva_val, ocr_data)
                    break
            except:
                pass
    
    # Si pas de pourcentage trouvé, chercher un montant
    if tva_pourcentage is None:
        for pattern in tva_montant_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                tva_val = match.group(1).replace(' ', '').replace(',', '.')
                try:
                    tva_num = float(tva_val)
                    tva_montant = tva_num
                    data['tva'] = f"{tva_num:.2f}"
                    if ocr_data is not None:
                        data['bounding_boxes']['tva'] = find_text_coordinates(tva_val, ocr_data)
                    break
                except:
                    pass
    
    # Si toujours rien, essayer des patterns génériques
    if tva_pourcentage is None and tva_montant is None:
        generic_patterns = [
            r'tva\s*:?\s*([\d\s,\.]+)',
            r'taxe\s*:?\s*([\d\s,\.]+)',
        ]
        for pattern in generic_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                tva_val = match.group(1).replace(' ', '').replace(',', '.')
                try:
                    tva_num = float(tva_val)
                    # Si la valeur est petite (< 30), c'est probablement un pourcentage
                    if tva_num <= 30:
                        tva_pourcentage = tva_num
                        data['tva'] = f"{tva_num:.2f}%"
                    else:
                        tva_montant = tva_num
                        data['tva'] = f"{tva_num:.2f}"
                    if ocr_data is not None:
                        data['bounding_boxes']['tva'] = find_text_coordinates(tva_val, ocr_data)
                    break
                except:
                    pass
    
    # Calculer les valeurs manquantes si possible
    try:
        ht_val = None
        ttc_val = None
        
        if data['montant_ht']:
            ht_val = float(data['montant_ht'].replace(',', '.').replace(' ', ''))
        
        if data['montant_ttc']:
            ttc_val = float(data['montant_ttc'].replace(',', '.').replace(' ', ''))
        
        # Si on a HT et TVA (pourcentage), calculer TTC = HT × (1 + TVA/100)
        if ht_val is not None and tva_pourcentage is not None and not data['montant_ttc']:
            ttc_calcule = ht_val * (1 + tva_pourcentage / 100)
            data['montant_ttc'] = f"{ttc_calcule:.2f}"
            print(f"✅ TTC calculé: HT ({ht_val:.2f}) × (1 + {tva_pourcentage}%) = {ttc_calcule:.2f}")
        
        # Si on a HT et TVA (montant), calculer TTC = HT + TVA
        elif ht_val is not None and tva_montant is not None and not data['montant_ttc']:
            ttc_calcule = ht_val + tva_montant
            data['montant_ttc'] = f"{ttc_calcule:.2f}"
            print(f"✅ TTC calculé: HT ({ht_val:.2f}) + TVA ({tva_montant:.2f}) = {ttc_calcule:.2f}")
        
        # Si TTC existe déjà mais qu'on peut le recalculer pour vérifier
        elif ht_val is not None and tva_pourcentage is not None and data['montant_ttc']:
            ttc_calcule = ht_val * (1 + tva_pourcentage / 100)
            ttc_existant = float(data['montant_ttc'].replace(',', '.').replace(' ', ''))
            # Si la différence est significative (> 1%), mettre à jour
            if abs(ttc_calcule - ttc_existant) > ttc_existant * 0.01:
                data['montant_ttc'] = f"{ttc_calcule:.2f}"
                print(f"⚠️  TTC recalculé et corrigé: {ttc_existant:.2f} → {ttc_calcule:.2f}")
        
        elif ht_val is not None and tva_montant is not None and data['montant_ttc']:
            ttc_calcule = ht_val + tva_montant
            ttc_existant = float(data['montant_ttc'].replace(',', '.').replace(' ', ''))
            # Si la différence est significative (> 1%), mettre à jour
            if abs(ttc_calcule - ttc_existant) > ttc_existant * 0.01:
                data['montant_ttc'] = f"{ttc_calcule:.2f}"
                print(f"⚠️  TTC recalculé et corrigé: {ttc_existant:.2f} → {ttc_calcule:.2f}")
        
        # Si on a TTC et HT, calculer TVA
        elif ht_val is not None and ttc_val is not None and not data['tva']:
            tva_calcule = ttc_val - ht_val
            tva_pct = (tva_calcule / ht_val) * 100 if ht_val > 0 else 0
            data['tva'] = f"{tva_pct:.2f}%"
            print(f"✅ TVA calculée: TTC ({ttc_val}) - HT ({ht_val}) = {tva_calcule:.2f} ({tva_pct:.2f}%)")
        
        # Si on a TTC et TVA (%), calculer HT
        elif ttc_val is not None and tva_pourcentage is not None and not data['montant_ht']:
            ht_calcule = ttc_val / (1 + tva_pourcentage / 100)
            data['montant_ht'] = f"{ht_calcule:.2f}"
            print(f"✅ HT calculé: TTC ({ttc_val}) / (1 + {tva_pourcentage}%) = {ht_calcule:.2f}")
        
        # Si on a TTC et TVA (montant), calculer HT
        elif ttc_val is not None and tva_montant is not None and not data['montant_ht']:
            ht_calcule = ttc_val - tva_montant
            data['montant_ht'] = f"{ht_calcule:.2f}"
            print(f"✅ HT calculé: TTC ({ttc_val}) - TVA ({tva_montant}) = {ht_calcule:.2f}")
            
    except Exception as e:
        print(f"⚠️  Erreur lors du calcul automatique: {e}")
    
    # Extraire le nom du fournisseur (généralement dans les premières lignes)
    for i, line in enumerate(lines[:10]):
        line_clean = line.strip()
        if len(line_clean) > 3 and not re.match(r'^\d+', line_clean):
            # Éviter les lignes qui sont clairement des dates ou numéros
            if not re.match(r'^\d{1,2}[\/\-\.]', line_clean):
                if not data['fournisseur']:
                    data['fournisseur'] = line_clean
                    if ocr_data is not None:
                        data['bounding_boxes']['fournisseur'] = find_text_coordinates(line_clean, ocr_data)
                break
    
    # Extraire l'adresse (lignes contenant des numéros de rue)
    adresse_lines = []
    for line in lines:
        if re.search(r'\d+\s+[a-zéèêàù]+', line, re.IGNORECASE):
            adresse_lines.append(line.strip())
    if adresse_lines:
        data['adresse'] = ' '.join(adresse_lines[:3])
    
    return data

def find_text_coordinates(search_text, ocr_data):
    """Trouve les coordonnées d'un texte dans les données OCR"""
    if ocr_data is None or not search_text:
        return None
    
    # Nettoyer le texte de recherche
    search_text_clean = re.sub(r'[^\w\s]', '', search_text.lower().strip())
    search_words = search_text_clean.split()
    
    if not search_words:
        return None
    
    # Chercher le premier mot du texte
    first_word = search_words[0]
    best_match = None
    best_score = 0
    
    for item in ocr_data:
        text = str(item.get('text', '')).strip()
        if not text:
            continue
            
        text_clean = re.sub(r'[^\w\s]', '', text.lower())
        
        # Si le texte correspond exactement ou contient le premier mot
        if first_word in text_clean or text_clean in search_text_clean:
            # Calculer un score de correspondance
            score = len(set(search_words) & set(text_clean.split()))
            if score > best_score and item.get('left') is not None:
                best_score = score
                best_match = item
    
    if best_match:
        return {
            'left': int(best_match['left']),
            'top': int(best_match['top']),
            'width': int(best_match['width']),
            'height': int(best_match['height'])
        }
    
    return None

def draw_annotations_on_image(img, invoice_data):
    """Dessine des encadrés sur l'image pour les informations détectées"""
    annotated_img = img.copy()
    h, w = annotated_img.shape[:2]
    
    # Couleurs pour chaque type d'information
    colors = {
        'fournisseur': (0, 255, 0),      # Vert
        'date': (255, 0, 0),              # Rouge
        'numero_facture': (0, 0, 255),    # Bleu
        'montant_ht': (255, 165, 0),      # Orange
        'montant_ttc': (255, 0, 255),     # Magenta
        'tva': (0, 255, 255),             # Cyan
        'adresse': (128, 0, 128)          # Violet
    }
    
    labels = {
        'fournisseur': 'Fournisseur',
        'date': 'Date',
        'numero_facture': 'N° Facture',
        'montant_ht': 'Montant HT',
        'montant_ttc': 'Montant TTC',
        'tva': 'TVA',
        'adresse': 'Adresse'
    }
    
    boxes = invoice_data.get('bounding_boxes', {})
    
    for key, box in boxes.items():
        if box is not None:
            color = colors.get(key, (255, 255, 255))
            label = labels.get(key, key)
            
            x, y, width, height = box['left'], box['top'], box['width'], box['height']
            
            # Dessiner le rectangle
            cv2.rectangle(annotated_img, (x, y), (x + width, y + height), color, 3)
            
            # Dessiner le label avec fond
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            label_y = max(y - 10, label_size[1] + 10)
            cv2.rectangle(annotated_img, 
                         (x, label_y - label_size[1] - 5), 
                         (x + label_size[0] + 10, label_y + 5), 
                         color, -1)
            cv2.putText(annotated_img, label, (x + 5, label_y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    
    return annotated_img

# Routes principales
@app.route('/')
def landing():
    """Page d'accueil / Landing page"""
    return render_template('landing.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Page de connexion"""
    if request.method == 'POST':
        # Authentification simple (à améliorer en production)
        username = request.form.get('username')
        password = request.form.get('password')
        if username and password:
            session['user'] = username
            return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """Page d'inscription"""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        if username and email and password:
            session['user'] = username
            return redirect(url_for('dashboard'))
    return render_template('signup.html')

@app.route('/logout')
def logout():
    """Déconnexion"""
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    """Tableau de bord avec statistiques"""
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # Charger les statistiques
    factures = load_all_factures()
    
    # Calculer les stats
    stats = {
        'total_factures': len(factures),
        'montant_total': 0,
        'total_fournisseurs': len(set(f.get('fournisseur', '') for f in factures if f.get('fournisseur'))),
        'factures_mois': 0
    }
    
    # Calculer le montant total et factures du mois
    mois_actuel = datetime.now().month
    annee_actuelle = datetime.now().year
    
    for facture in factures:
        try:
            montant = float(facture.get('montant_ttc', '0').replace(',', '.'))
            stats['montant_total'] += montant
        except:
            pass
        
        # Compter les factures du mois
        try:
            date_facture = facture.get('date_facture', '')
            if date_facture and '/' in date_facture:
                parts = date_facture.split('/')
                if len(parts) >= 2:
                    mois_facture = int(parts[1])
                    if len(parts) >= 3:
                        annee_facture = int(parts[2])
                        if mois_facture == mois_actuel and annee_facture == annee_actuelle:
                            stats['factures_mois'] += 1
        except:
            pass
    
    stats['montant_total'] = f"{stats['montant_total']:.2f}"
    
    # Factures récentes (5 dernières)
    recent_factures = sorted(factures, key=lambda x: x.get('date_creation', ''), reverse=True)[:5]
    
    return render_template('dashboard.html', stats=stats, recent_factures=recent_factures, active_page='dashboard')

@app.route('/import')
def import_page():
    """Page d'import de factures (ancienne page index.html)"""
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', active_page='import_page')

@app.route('/mes-factures')
def mes_factures():
    """Page listant toutes les factures sauvegardées"""
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # Charger toutes les factures
    factures = load_all_factures()
    
    # Trier par date (plus récent en premier) puis par numéro de facture
    factures.sort(key=lambda x: (
        datetime.strptime(x.get('date_facture', '1900-01-01'), '%d/%m/%Y') if x.get('date_facture') and '/' in str(x.get('date_facture')) else datetime(1900, 1, 1),
        x.get('numero_facture', '')
    ), reverse=True)
    
    return render_template('mes_factures.html', factures=factures, active_page='mes_factures')

@app.route('/fournisseurs')
def fournisseurs():
    """Page de gestion des fournisseurs"""
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # Charger toutes les factures pour extraire les fournisseurs
    factures = load_all_factures()
    
    # Grouper par fournisseur
    fournisseurs_dict = {}
    for facture in factures:
        nom = facture.get('fournisseur', 'Sans fournisseur')
        if nom and nom != '':
            if nom not in fournisseurs_dict:
                fournisseurs_dict[nom] = {
                    'nom': nom,
                    'nb_factures': 0,
                    'montant_total': 0,
                    'adresse': facture.get('adresse', ''),
                    'email': '',
                    'telephone': ''
                }
            fournisseurs_dict[nom]['nb_factures'] += 1
            try:
                montant = float(facture.get('montant_ttc', '0').replace(',', '.'))
                fournisseurs_dict[nom]['montant_total'] += montant
            except:
                pass
    
    fournisseurs_list = list(fournisseurs_dict.values())
    fournisseurs_list.sort(key=lambda x: x['montant_total'], reverse=True)
    
    # Formater les montants
    for f in fournisseurs_list:
        f['montant_total'] = f"{f['montant_total']:.2f}"
    
    return render_template('fournisseurs.html', fournisseurs=fournisseurs_list, active_page='fournisseurs')

@app.route('/settings')
def settings():
    """Page des paramètres"""
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('settings.html', active_page='settings')

@app.route('/support')
def support():
    """Page de support"""
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('support.html', active_page='support')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Route pour servir les images uploadées"""
    from flask import send_from_directory
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/factures/<filename>')
def facture_file(filename):
    """Route pour servir les images de factures sauvegardées"""
    from flask import send_from_directory
    return send_from_directory(app.config['FACTURES_FOLDER'], filename)

@app.route('/api/facture/<facture_id>', methods=['DELETE'])
def delete_facture_api(facture_id):
    """API pour supprimer une facture"""
    if 'user' not in session:
        return jsonify({'error': 'Non autorisé'}), 401
    
    if delete_facture(facture_id):
        return jsonify({'success': True, 'message': 'Facture supprimée avec succès'})
    else:
        return jsonify({'error': 'Facture non trouvée'}), 404

@app.route('/upload', methods=['POST'])
def upload_file():
    # Vérifier que Tesseract est disponible avant de traiter
    if not TESSERACT_AVAILABLE:
        return jsonify({
            'error': (
                'Tesseract OCR n\'est pas installé.\n\n'
                '📥 INSTALLATION REQUISE:\n\n'
                '1. Téléchargez depuis: https://github.com/UB-Mannheim/tesseract/wiki\n'
                '2. Installez et cochez "Add to PATH"\n'
                '3. Redémarrez l\'application\n\n'
                'Ou utilisez: winget install --id UB-Mannheim.TesseractOCR'
            )
        }), 500
    
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier fourni'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'Aucun fichier sélectionné'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            # Lire l'image avec OpenCV
            img = cv2.imread(filepath)
            if img is None:
                return jsonify({'error': "Impossible de lire l'image"}), 400
            
            # Améliorer l'image pour de meilleurs résultats OCR
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Appliquer un seuil adaptatif pour améliorer le contraste
            thresh = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY, 11, 2
            )
            
            # Convertir en PIL Image pour pytesseract
            pil_image = Image.fromarray(thresh)
            
            # Vérifier que Tesseract est disponible
            try:
                # Utiliser l'image originale pour l'OCR et les annotations
                original_pil = Image.open(filepath)
                
                # Essayer plusieurs configurations PSM pour de meilleurs résultats
                configs_to_try = [
                    ('--psm 6', 'fra+eng'),  # Bloc uniforme, français + anglais
                    ('--psm 3', 'fra+eng'),  # Automatique
                    ('--psm 11', 'fra+eng'), # Texte dense
                    ('--psm 6', 'eng'),      # Fallback anglais seulement
                ]
                
                full_text = None
                best_text = ""
                ocr_data = None
                best_config = ('--psm 6', 'fra+eng')
                
                for psm_config, lang_config in configs_to_try:
                    try:
                        text = pytesseract.image_to_string(
                            original_pil,
                            lang=lang_config,
                            config=psm_config
                        )
                        # Garder le texte le plus long (généralement le plus complet)
                        if len(text.strip()) > len(best_text.strip()):
                            best_text = text
                            full_text = text
                            best_config = (psm_config, lang_config)
                    except Exception as e:
                        # Continuer avec la configuration suivante
                        continue
                
                # Si aucune configuration n'a fonctionné, utiliser la dernière tentative
                if not full_text:
                    full_text = pytesseract.image_to_string(
                        original_pil,
                        lang='fra+eng',
                        config='--psm 6'
                    )
                    best_config = ('--psm 6', 'fra+eng')
                
                # Obtenir les données OCR avec coordonnées pour les annotations
                try:
                    ocr_data_dict = pytesseract.image_to_data(
                        original_pil,
                        lang=best_config[1],
                        config=best_config[0],
                        output_type=pytesseract.Output.DICT
                    )
                    # Convertir en liste de dictionnaires
                    ocr_data = []
                    n_boxes = len(ocr_data_dict['text'])
                    for i in range(n_boxes):
                        if int(ocr_data_dict['conf'][i]) > 0:  # Ignorer les confidences 0
                            ocr_data.append({
                                'text': ocr_data_dict['text'][i],
                                'left': ocr_data_dict['left'][i],
                                'top': ocr_data_dict['top'][i],
                                'width': ocr_data_dict['width'][i],
                                'height': ocr_data_dict['height'][i],
                                'conf': ocr_data_dict['conf'][i]
                            })
                except Exception as e:
                    print(f"Erreur lors de la récupération des coordonnées OCR: {e}")
                    ocr_data = None
                    
            except pytesseract.TesseractNotFoundError:
                error_msg = (
                    "Tesseract OCR n'est pas installé ou introuvable.\n\n"
                    "📥 INSTALLATION REQUISE:\n\n"
                    "Méthode 1 - Installation manuelle:\n"
                    "1. Téléchargez: https://github.com/UB-Mannheim/tesseract/wiki\n"
                    "2. Installez et cochez 'Add to PATH'\n"
                    "3. Sélectionnez French (fra) et English (eng)\n"
                    "4. Redémarrez l'application\n\n"
                    "Méthode 2 - Via winget:\n"
                    "winget install --id UB-Mannheim.TesseractOCR\n\n"
                    "Méthode 3 - Via Chocolatey:\n"
                    "choco install tesseract\n\n"
                    "Après installation, redémarrez l'application Flask."
                )
                if os.path.exists(filepath):
                    os.remove(filepath)
                return jsonify({'error': error_msg}), 500
            except Exception as ocr_error:
                # En cas d'erreur OCR, essayer avec l'image originale
                try:
                    original_pil = Image.open(filepath)
                    full_text = pytesseract.image_to_string(
                        original_pil,
                        lang='fra+eng',
                        config='--psm 6'
                    )
                except:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    return jsonify({'error': f'Erreur OCR: {str(ocr_error)}'}), 500
            
            # Extraire les données structurées avec coordonnées
            invoice_data = extract_invoice_data(full_text, ocr_data)
            
            # Dessiner les annotations sur l'image originale
            annotated_img = draw_annotations_on_image(img, invoice_data)
            
            # Sauvegarder l'image annotée
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            annotated_filename = f'annotated_{timestamp}_{filename}'
            annotated_filepath = os.path.join(app.config['UPLOAD_FOLDER'], annotated_filename)
            cv2.imwrite(annotated_filepath, annotated_img)
            
            # Sauvegarder la facture dans le système
            facture_id = save_facture(invoice_data, annotated_filename, filename)
            
            # Nettoyer le fichier temporaire original (garder l'annotée)
            os.remove(filepath)
            
            return jsonify({
                'success': True,
                'data': invoice_data,
                'annotated_image': f'/uploads/{annotated_filename}',
                'facture_id': facture_id
            })
            
        except Exception as e:
            # Nettoyer en cas d'erreur
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({'error': f'Erreur lors du traitement: {str(e)}'}), 500
    
    return jsonify({'error': 'Type de fichier non autorisé'}), 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

