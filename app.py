from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
import json
from pathlib import Path
from datetime import datetime, timedelta
from models import db, User, Diagnostic
import csv
from io import StringIO, BytesIO
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
app.config['TITLE'] = 'OsteoTech'

# ✅ UTILISE RENDER_DATABASE_URL (automatique depuis Render)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///osteotech.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Pour Render PostgreSQL : remplace postgresql:// par postgresql+psycopg2://
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgresql://', 'postgresql+psycopg2://', 1)

db.init_app(app)

# Charger pathologies
def load_pathologies():
    try:
        json_path = Path(__file__).parent / 'pathologies.json'
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Erreur: pathologies.json non trouvé")
        return {}

PATHOLOGIES = load_pathologies()

SEATS_BY_LOCATION = {
    'Céphale': ['Base du crâne', 'Crâne Global', 'Front', 'Hémicrâne', 'Hémiface', 'Face postérieure du Crâne', 'Tempes', 'Orbito-frontal', 'Sous-orbitaire'],
    'Douleur Abdominale': ['Epigastre', 'F.I.D', 'Hypocondre Droit', 'Hypogastre', 'Tout l\'Abdomen', 'Latro-thoracique'],
    'Douleur Cervicale': ['Cou', 'Inter-scapulaire', 'Rachis thoracique'],
    'Douleur du Membre Supérieur': ['Bras', 'Epaule', 'Face antérieure du Poignet', 'Face latérale du Coude', 'Face médiale du Coude', 'Pouce', 'Base d\'un doigt'],
    'Douleur du Membre Inférieur': ['Membre Inférieur', 'Face externe du Genou', 'Face externe de la Cheville', 'Hallux', 'Inter-orteil', 'Mollet', 'Talon', 'T.T.A'],
    'Douleur Thoracique': ['Latro-thoracique', 'Rétrosternal'],
    'Facialgie': ['Hémiface', 'Front', 'Tempes', 'Sous-orbitaire'],
    'Lombalgie': ['Lombaire']
}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'userid' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    if 'userid' in session:
        return User.query.get(session['userid'])
    return None

def find_diagnosis(user_data):
    best_match = None
    best_score = 0
    
    for path_id, pathology in PATHOLOGIES.items():
        criteria = pathology.get('criteres', {})
        score = 0
        total_criteria = len(criteria)
        
        for key, expected_value in criteria.items():
            user_value = user_data.get(key)
            if isinstance(expected_value, list):
                if user_value in expected_value:
                    score += 1
            elif user_value == expected_value:
                score += 1
        
        match_percentage = (score / total_criteria * 100) if total_criteria > 0 else 0
        
        if match_percentage > best_score:
            best_score = match_percentage
            best_match = (path_id, pathology, match_percentage)
    
    return best_match if best_match and best_score >= 50 else None

# Routes principales
@app.route('/')
def index():
    user = get_current_user()
    return render_template('index.html', user=user)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()
        
        if not email or not password:
            return render_template('register.html', error='Email et mot de passe requis')
        
        if password != password_confirm:
            return render_template('register.html', error='Les mots de passe ne correspondent pas')
        
        if len(password) < 6:
            return render_template('register.html', error='Mot de passe trop court')
        
        if User.query.filter_by(email=email).first():
            return render_template('register.html', error='Email déjà utilisé')
        
        user = User(email=email)
        user.set_password(password)
        user.school_id = 'ifoga'
        
        db.session.add(user)
        db.session.commit()
        
        session['userid'] = user.id
        session['email'] = user.email
        
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            session['userid'] = user.id
            session['email'] = user.email
            return redirect(url_for('dashboard'))
        
        return render_template('login.html', error='Email ou mot de passe incorrect')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard simple - ANTI-CRASH"""
    try:
        user = get_current_user()
        diagnostics = []
        totaldiagnostics = 0
        
        # ✅ CORRECTION : user_id (pas userid)
        if user:
            diagnostics = Diagnostic.query.filter_by(user_id=user.id).all()
            totaldiagnostics = len(diagnostics)
        
        return render_template('dashboard.html',
                             diagnostics=diagnostics,
                             totaldiagnostics=totaldiagnostics,
                             email=session.get('email'))
    except Exception as e:
        print(f"Dashboard error: {e}")
        return render_template('dashboard.html', diagnostics=[], totaldiagnostics=0, email=session.get('email'))

@app.route('/app', methods=['GET', 'POST'])
@login_required
def app_diagnostic():
    user = get_current_user()
    diagnosis_result = None
    
    if request.method == 'POST':
        user_data = {
            'localisation_anatomique': request.form.get('localisation_anatomique'),
            'siege': request.form.get('siege'),
            'irradiations': request.form.get('irradiations'),
            'type': request.form.get('type'),
            'intensite': request.form.get('intensite'),
            'calme_par': request.form.get('calme_par'),
            'augmente_par': request.form.get('augmente_par'),
            'evolution': request.form.get('evolution'),
            'signes_associes': request.form.get('signes_associes')
        }
        
        result = find_diagnosis(user_data)
        
        if result:
            path_id, pathology, confidence = result
            diagnosis_result = {
                'nom': pathology.get('nom', 'Pathologie'),
                'description': pathology.get('description', ''),
                'confidence': round(confidence, 1)
            }
            
            # ✅ CORRECTION : noms de colonnes corrects
            diagnostic = Diagnostic(
                user_id=user.id,
                diagnosis_name=pathology.get('nom'),
                diagnosis_confidence=confidence,
                diagnosis_id=path_id,
                siege=user_data.get('siege'),
                type_douleur=user_data.get('type')
            )
            
            db.session.add(diagnostic)
            db.session.commit()
    
    return render_template('app.html', diagnosis=diagnosis_result, seats_by_location=SEATS_BY_LOCATION)

# Initialisation
@app.cli.command()
def init_db():
    db.create_all()
    print("Tables créées")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
