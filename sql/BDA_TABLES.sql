-- 1. Créer la base de données
CREATE DATABASE IF NOT EXISTS labomarche;
USE labomarche;



-- Table des utilisateurs (connexion à l'interface)
DROP TABLE IF EXISTS parametres_spatio_temporels;
DROP TABLE IF EXISTS parametres_cinematiques;
DROP TABLE IF EXISTS parametres_dynamiques;
DROP TABLE IF EXISTS patients;
DROP TABLE IF EXISTS users;

-- 2. Table des patients
CREATE TABLE patients (
    ID_Sujet VARCHAR(10) PRIMARY KEY,
    Age INT CHECK (Age BETWEEN 18 AND 30),
    Sexe ENUM('H', 'F'),
    Taille DECIMAL(4,2), -- en mètres, ex: 1.75
    Poids DECIMAL(5,2)   -- en kg, ex: 70.50
);

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(100) NOT NULL,
    prenom VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Table des paramètres spatio-temporels
CREATE TABLE parametres_spatio_temporels (
    ID_Mesure INT AUTO_INCREMENT PRIMARY KEY,
    ID_Sujet VARCHAR(10),
    Vitesse DECIMAL(4,3),
    Step_Length_Gauche DECIMAL(4,3),
    Step_Length_Droite DECIMAL(4,3),
    Cycle_Time_Gauche DECIMAL(4,3),
    Cycle_Time_Droite DECIMAL(4,3),
    Steps_per_min_Gauche INT,
    Steps_per_min_Droite INT,
    Double_Support_Time DECIMAL(4,3),
    FOREIGN KEY (ID_Sujet) REFERENCES patients(ID_Sujet)
);

-- 4. Table des paramètres cinématiques
CREATE TABLE parametres_cinematiques (
    ID_Mesure INT AUTO_INCREMENT PRIMARY KEY,
    ID_Sujet VARCHAR(10),
    ROM_Hanche_Gauche DECIMAL(5,2),
    ROM_Hanche_Droite DECIMAL(5,2),
    ROM_Genou_Gauche DECIMAL(5,2),
    ROM_Genou_Droite DECIMAL(5,2),
    ROM_Cheville_Gauche DECIMAL(5,2),
    ROM_Cheville_Droite DECIMAL(5,2),
    Foot_Progression_Gauche DECIMAL(5,2),
    Foot_Progression_Droite DECIMAL(5,2),
    FOREIGN KEY (ID_Sujet) REFERENCES patients(ID_Sujet)
);

-- 5. Table des paramètres dynamiques
CREATE TABLE parametres_dynamiques (
    ID_Mesure INT AUTO_INCREMENT PRIMARY KEY,
    ID_Sujet VARCHAR(10),
    Peak_Force_Verticale DECIMAL(6,2),
    Peak_Power_Knee DECIMAL(5,2),
    Peak_Power_Ankle DECIMAL(5,2),
    Peak_Moment_Hip DECIMAL(5,2),
    Peak_Moment_Knee DECIMAL(5,2),
    Peak_Moment_Ankle DECIMAL(5,2),
    FOREIGN KEY (ID_Sujet) REFERENCES patients(ID_Sujet)
);
