import os
import re
from datetime import datetime
import fitz
import cv2
import numpy as np
import pymysql
import csv
from io import StringIO
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT, SECRET_KEY


from extraction_insertion import process_pdf_and_insert


app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def get_db_connection():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME, port=DB_PORT,
        cursorclass=pymysql.cursors.DictCursor
    )


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            flash('Veuillez vous connecter pour accéder à cette page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function



@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['logged_in'] = True
            session['email'] = user['email']
            session['username'] = f"{user['prenom']} {user['nom']}"
            flash(f'Connexion réussie ! Bienvenue {session["username"]}.', 'success')
            return redirect(url_for('index'))
        else:
            flash('Email ou mot de passe incorrect.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('email', None)
    session.pop('username', None)
    flash('Vous avez été déconnecté.', 'success')
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        nom = request.form['nom']
        prenom = request.form['prenom']
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            flash('Cet email est déjà utilisé. Veuillez vous connecter ou en utiliser un autre.', 'error')
        else:
            password_hash = generate_password_hash(password)
            try:
                cursor.execute("INSERT INTO users (nom, prenom, email, password_hash) VALUES (%s, %s, %s, %s)", (nom, prenom, email, password_hash))
                conn.commit()
                flash('Inscription réussie ! Vous pouvez maintenant vous connecter.', 'success')
                return redirect(url_for('login'))
            except Exception as e:
                flash(f'Erreur lors de l\'inscription: {str(e)}', 'error')
        
        conn.close()
    return render_template('signup.html')

@app.route('/index')
@login_required
def index():
    """
    Affiche la page d'accueil avec le formulaire d'upload et la liste des patients.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM patients")
    patients = cursor.fetchall()
    conn.close()
    return render_template('index.html', patients=patients)

@app.route('/import_pdf', methods=['POST'])
@login_required
def import_pdf():
    """
    Gère l'envoi du formulaire d'importation de PDF.
    """
    if 'pdf_file' not in request.files:
        flash('Aucun fichier PDF n\'a été sélectionné.', 'error')
        return redirect(url_for('index'))
    file = request.files['pdf_file']
    patient_id = request.form['patient_id']

    if file.filename == '' or patient_id == '':
        flash('Veuillez sélectionner un fichier et entrer un ID de patient.', 'error')
        return redirect(url_for('index'))
    
    if file and file.filename.endswith('.pdf'):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            success, message = process_pdf_and_insert(filepath, patient_id)
            flash(message, 'success' if success else 'error')
        except pymysql.err.IntegrityError as e:
            if e.args[0] == 1062:
                flash(f"Erreur : Un patient avec l'ID '{patient_id}' existe déjà. Veuillez choisir un ID unique.", 'error')
            else:
                flash(f"Erreur lors de l'insertion dans la base de données: {str(e)}", 'error')
        except Exception as e:
            flash(f"Erreur lors du traitement du PDF : {str(e)}", 'error')
        finally:
            os.remove(filepath)
    else:
        flash('Le fichier doit être un PDF.', 'error')
    
    return redirect(url_for('index'))


@app.route('/delete/<patient_id>', methods=['POST'])
@login_required
def delete_patient(patient_id):
    """
    Supprime un patient et toutes ses données associées.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
 
        cursor.execute("DELETE FROM parametres_spatio_temporels WHERE ID_Sujet = %s", (patient_id,))
        cursor.execute("DELETE FROM parametres_cinematiques WHERE ID_Sujet = %s", (patient_id,))
        cursor.execute("DELETE FROM parametres_dynamiques WHERE ID_Sujet = %s", (patient_id,))
        
 
        cursor.execute("DELETE FROM patients WHERE ID_Sujet = %s", (patient_id,))
        
        conn.commit()
        flash(f'Patient {patient_id} et toutes ses données ont été supprimés avec succès.', 'success')
    except pymysql.err.OperationalError as e:
        if e.args[0] == 1205:
            conn.rollback()
            flash(f'Erreur : Échec de la suppression. Une autre opération sur la base de données est en cours. Veuillez réessayer dans quelques instants.', 'error')
        else:
            conn.rollback()
            flash(f'Erreur lors de la suppression du patient: {str(e)}', 'error')
    except Exception as e:
        conn.rollback()
        flash(f'Erreur lors de la suppression du patient: {str(e)}', 'error')
    finally:
        conn.close()
    return redirect(url_for('index'))

@app.route('/export_data')
@login_required
def export_data():
    """
    Exporte toutes les données combinées des 4 tables en un fichier CSV.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
    SELECT
        p.ID_Sujet, p.Age, p.Sexe, p.Taille, p.Poids,
        s.Vitesse, s.Step_Length_Gauche, s.Step_Length_Droite,
        s.Cycle_Time_Gauche, s.Cycle_Time_Droite,
        s.Steps_per_min_Gauche, s.Steps_per_min_Droite, s.Double_Support_Time,
        c.ROM_Hanche_Gauche, c.ROM_Hanche_Droite,
        c.ROM_Genou_Gauche, c.ROM_Genou_Droite,
        c.ROM_Cheville_Gauche, c.ROM_Cheville_Droite,
        c.Foot_Progression_Gauche, c.Foot_Progression_Droite,
        d.Peak_Force_Verticale, d.Peak_Power_Knee, d.Peak_Power_Ankle,
        d.Peak_Moment_Hip, d.Peak_Moment_Knee, d.Peak_Moment_Ankle
    FROM patients p
    LEFT JOIN parametres_spatio_temporels s ON p.ID_Sujet = s.ID_Sujet
    LEFT JOIN parametres_cinematiques c ON p.ID_Sujet = c.ID_Sujet
    LEFT JOIN parametres_dynamiques d ON p.ID_Sujet = d.ID_Sujet;
    """
    
    cursor.execute(query)
    data = cursor.fetchall()
    conn.close()
    
    if not data:
        flash('Aucune donnée à exporter.', 'error')
        return redirect(url_for('index'))

    si = StringIO()
    cw = csv.writer(si, delimiter=';')
    
    headers = [key for key in data[0].keys()]
    cw.writerow(headers)
    
    for row in data:
        cw.writerow(row.values())
    
    output = si.getvalue()
    si.close()

    response = Response(output, mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=donnees_patients.csv"
    return response

if __name__ == '__main__':
    app.run(debug=True)
