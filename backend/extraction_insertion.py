import pdfplumber
import re
from datetime import datetime
import fitz
import cv2
import numpy as np
import pymysql



# KINEMATICS (cinématiques, ROM)
ECHELLE_PIX2DEGRE = 0.5
CROPS_CINEMATIQUE = {
    "ROM_Hanche_Gauche":   (637, 1275, 0, 1100),
    "ROM_Hanche_Droite":   (637, 1275, 0, 1100),
    "ROM_Genou_Gauche":    (1275, 1912, 0, 1100),
    "ROM_Genou_Droite":    (1275, 1912, 0, 1100),
    "ROM_Cheville_Gauche": (1912, 2550, 0, 1100),
    "ROM_Cheville_Droite": (1912, 2550, 0, 1100),
    "Foot_Progression_Gauche": (0, 2550, 0, 1650),
    "Foot_Progression_Droite": (0, 2550, 0, 1650),
}
COLOR_MAP_CINEMATIQUE = {
    "ROM_Hanche_Gauche": "red",
    "ROM_Hanche_Droite": "blue",
    "ROM_Genou_Gauche": "red",
    "ROM_Genou_Droite": "blue",
    "ROM_Cheville_Gauche": "red",
    "ROM_Cheville_Droite": "blue",
    "Foot_Progression_Gauche": "red",
    "Foot_Progression_Droite": "blue",
}

# DYNAMIQUES
ECHELLE_PIX2UNIT = 0.008
CROPS_DYNAMIQUES = {
    "Peak_Force_Verticale":   {"page": 5, "crop": (0, 2550, 1650, 3300), "color": "blue"},
    "Peak_Power_Knee":        {"page": 6, "crop": (850, 1700, 2200, 3300), "color": "blue"},
    "Peak_Power_Ankle":       {"page": 6, "crop": (1700, 2550, 2200, 3300), "color": "blue"},
    "Peak_Moment_Hip":        {"page": 6, "crop": (0, 850, 1100, 2200), "color": "blue"},
    "Peak_Moment_Knee":       {"page": 6, "crop": (850, 1700, 1100, 2200), "color": "blue"},
    "Peak_Moment_Ankle":      {"page": 6, "crop": (1700, 2550, 1100, 2200), "color": "blue"},
}



def extract_with_regex(text, pattern, cast=float):
    match = re.search(pattern, text, re.DOTALL | re.MULTILINE)
    try:
        return cast(match.group(1)) if match else None
    except:
        return None

def calculate_age(dob_str, test_date_str):
    try:
        dob = datetime.strptime(dob_str, "%m/%d/%Y")
        test_date = datetime.strptime(test_date_str, "%m/%d/%Y")
        return test_date.year - dob.year - ((test_date.month, test_date.day) < (dob.month, dob.day))
    except:
        return None

def courbe_rom_from_crop(img, color):
    if img is None or img.shape[0] == 0 or img.shape[1] == 0:
        return None
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    if color == "red":
        mask = cv2.inRange(hsv, (0, 70, 50), (10, 255, 255)) | cv2.inRange(hsv, (160, 70, 50), (180, 255, 255))
    elif color == "blue":
        mask = cv2.inRange(hsv, (90, 70, 50), (130, 255, 255))
    else:
        raise ValueError("Color must be 'red' or 'blue'")
    pts = np.where(mask > 0)
    if len(pts[0]) > 0:
        min_y, max_y = np.min(pts[0]), np.max(pts[0])
        rom_pixels = abs(max_y - min_y)
        return round(rom_pixels * ECHELLE_PIX2DEGRE, 2)
    else:
        return None

def extract_peak_from_crop(img, color, abs_max=False):
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    if color == "blue":
        mask = cv2.inRange(hsv, (90, 70, 50), (130, 255, 255))
    elif color == "red":
        mask = cv2.inRange(hsv, (0, 70, 50), (10, 255, 255)) | cv2.inRange(hsv, (160, 70, 50), (180, 255, 255))
    else:
        raise ValueError("Color must be 'red' or 'blue'")
    points = np.where(mask > 0)
    if len(points[0]) == 0 or len(points[1]) == 0:
        return None
    signal = []
    for x in range(mask.shape[1]):
        y_points = points[0][points[1] == x]
        if len(y_points) > 0:
            signal.append(np.mean(y_points))
        else:
            signal.append(np.nan)
    signal = np.array(signal)
    signal = signal[~np.isnan(signal)]
    if abs_max:
        minval = np.nanmin(signal)
        maxval = np.nanmax(signal)
        if abs(mask.shape[0] - minval) > abs(mask.shape[0] - maxval):
            pixel_peak = minval
        else:
            pixel_peak = maxval
        peak_value = abs(mask.shape[0] - pixel_peak) * ECHELLE_PIX2UNIT
    else:
        pixel_peak = np.nanmin(signal)
        peak_value = (mask.shape[0] - pixel_peak) * ECHELLE_PIX2UNIT
    return round(peak_value, 2)


def process_pdf_and_insert(pdf_path, patient_id):
    """
    Traite le PDF et insère les données dans la base MySQL.
    """
    try:
        
        with pdfplumber.open(pdf_path) as pdf:
            text = ''
            for i in range(2, 6):
                if i < len(pdf.pages):
                    page_text = pdf.pages[i].extract_text()
                    if page_text:
                        text += page_text + '\n'

        dob_match = re.search(r"Date of Birth \(mm/dd/yyyy\)\s*:\s*(\d{2}/\d{2}/\d{4})", text)
        test_date_match = re.search(r"Test Date \(mm/dd/yyyy\)\s*:\s*(\d{2}/\d{2}/\d{4})", text)
        age = calculate_age(dob_match.group(1), test_date_match.group(1)) if dob_match and test_date_match else None
        sexe_raw = extract_with_regex(text, r"Sex\s*:\s*(Male|Female)", str)
        sexe = "H" if sexe_raw == "Male" else "F"
        taille = extract_with_regex(text, r"Height\s*:\s*([\d.]+)m")
        poids = extract_with_regex(text, r"Weight\s*:\s*([\d.]+)Kg")
        spatio = {
            'Vitesse': extract_with_regex(text, r"Speed\s*([\d.]+)"),
            'Step_Length_Gauche': extract_with_regex(text, r"Step Length.*?Left\s*:\s*([\d.]+)"),
            'Step_Length_Droite': extract_with_regex(text, r"Step Length.*?Right\s*:\s*([\d.]+)"),
            'Cycle_Time_Gauche': extract_with_regex(text, r"Cycle Time.*?Left\s*:\s*([\d.]+)"),
            'Cycle_Time_Droite': extract_with_regex(text, r"Cycle Time.*?Right\s*:\s*([\d.]+)"),
            'Steps_per_min_Gauche': extract_with_regex(text, r"Steps\s*/\s*Minute.*?Left\s*:\s*([\d.]+)"),
            'Steps_per_min_Droite': extract_with_regex(text, r"Steps\s*/\s*Minute.*?Right\s*:\s*([\d.]+)"),
            'Double_Support_Time': extract_with_regex(text, r"Dbl Limb Support.*?([0-9]+\.[0-9]+)")
        }

        
        doc = fitz.open(pdf_path)
        page_kin = doc.load_page(4)
        page_foot = doc.load_page(5)
        pix_kin = page_kin.get_pixmap(dpi=300)
        img_kin = np.frombuffer(pix_kin.samples, dtype=np.uint8).reshape((pix_kin.height, pix_kin.width, pix_kin.n))
        if pix_kin.n == 4:
            img_kin = img_kin[..., :3]
        pix_foot = page_foot.get_pixmap(dpi=300)
        img_foot = np.frombuffer(pix_foot.samples, dtype=np.uint8).reshape((pix_foot.height, pix_foot.width, pix_foot.n))
        if pix_foot.n == 4:
            img_foot = img_foot[..., :3]
        roms = {}
        for var, (y1, y2, x1, x2) in CROPS_CINEMATIQUE.items():
            if "Foot_Progression" in var:
                img = img_foot
            else:
                img = img_kin
            crop = img[y1:y2, x1:x2]
            color = COLOR_MAP_CINEMATIQUE[var]
            roms[var] = courbe_rom_from_crop(crop, color)

        
        dyn_values = {}
        for var, params in CROPS_DYNAMIQUES.items():
            page_index = params["page"] - 1
            page = doc.load_page(page_index)
            pix = page.get_pixmap(dpi=300)
            img_np = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, pix.n))
            if pix.n == 4:
                img_np = img_np[..., :3]
            y1, y2, x1, x2 = params["crop"]
            crop = img_np[y1:y2, x1:x2]
            abs_max = var.startswith("Peak_Moment")
            dyn_values[var] = extract_peak_from_crop(crop, params["color"], abs_max=abs_max)
        
        doc.close()

        
        conn = pymysql.connect(
            host="localhost", user="root", password="Zayd2004@", database="labomarche", port=3308
        )
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO patients (ID_Sujet, Age, Sexe, Taille, Poids)
            VALUES (%s, %s, %s, %s, %s)
            """, (patient_id, age, sexe, taille, poids))

        cursor.execute("""
            INSERT INTO parametres_spatio_temporels (
                ID_Sujet, Vitesse, Step_Length_Gauche, Step_Length_Droite,
                Cycle_Time_Gauche, Cycle_Time_Droite,
                Steps_per_min_Gauche, Steps_per_min_Droite,
                Double_Support_Time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            patient_id, spatio['Vitesse'], spatio['Step_Length_Gauche'], spatio['Step_Length_Droite'],
            spatio['Cycle_Time_Gauche'], spatio['Cycle_Time_Droite'],
            spatio['Steps_per_min_Gauche'], spatio['Steps_per_min_Droite'], spatio['Double_Support_Time']
        ))

        cursor.execute("""
            INSERT INTO parametres_cinematiques (
                ID_Sujet, ROM_Hanche_Gauche, ROM_Hanche_Droite,
                ROM_Genou_Gauche, ROM_Genou_Droite,
                ROM_Cheville_Gauche, ROM_Cheville_Droite,
                Foot_Progression_Gauche, Foot_Progression_Droite
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            patient_id, roms["ROM_Hanche_Gauche"], roms["ROM_Hanche_Droite"],
            roms["ROM_Genou_Gauche"], roms["ROM_Genou_Droite"],
            roms["ROM_Cheville_Gauche"], roms["ROM_Cheville_Droite"],
            roms["Foot_Progression_Gauche"], roms["Foot_Progression_Droite"]
        ))

        cursor.execute("""
            INSERT INTO parametres_dynamiques (
                ID_Sujet, Peak_Force_Verticale, Peak_Power_Knee, Peak_Power_Ankle,
                Peak_Moment_Hip, Peak_Moment_Knee, Peak_Moment_Ankle
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            patient_id,
            dyn_values["Peak_Force_Verticale"], dyn_values["Peak_Power_Knee"], dyn_values["Peak_Power_Ankle"],
            dyn_values["Peak_Moment_Hip"], dyn_values["Peak_Moment_Knee"], dyn_values["Peak_Moment_Ankle"]
        ))
        
        conn.commit()
        conn.close()
        return True, "✅ Insertion réussie dans les 4 tables pour le patient " + patient_id
    
    except Exception as e:
        return False, "❌ Erreur lors du traitement du PDF ou de l'insertion dans la base de données : " + str(e)