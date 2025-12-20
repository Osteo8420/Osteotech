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
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['TITLE'] = 'OsteoTech'

# PostgreSQL Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://osteotechdb_user:ddkPXrTe3FlfstPmaadHTTcTObt4Stc8dpg-d51vsa5actks73aagnhg-a:osteotechdb'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Charger les pathologies depuis le fichier JSON
def load_pathologies():
    try:
        json_path = Path(__file__).parent / 'pathologies.json'
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Erreur: pathologies.json non trouvé")
        return {}

PATHOLOGIES = load_pathologies()

# Siège par localisation
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

# Décorateur pour vérifier si l'utilisateur est connecté
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'userid' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Récupérer l'utilisateur connecté
def get_current_user():
    """Récupérer l'utilisateur connecté via session"""
    if 'userid' in session:
        return User.query.get(session['userid'])
    return None

# Moteur diagnostique
def find_diagnosis(user_data):
    """Trouver la pathologie qui match le mieux"""
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
@app.route('/', methods=['GET'])
def index():
    """Page d'accueil"""
    user = get_current_user()
    return render_template('index.html', user=user)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Inscription"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()
        
        if not email or not password:
            return render_template('register.html', error='Email et mot de passe requis')
        
        if password != password_confirm:
            return render_template('register.html', error='Les mots de passe ne correspondent pas')
        
        if len(password) < 6:
            return render_template('register.html', error='Le mot de passe doit contenir au moins 6 caractères')
        
        if User.query.filter_by(email=email).first():
            return render_template('register.html', error='Cet email est déjà utilisé')
        
        user = User(email=email)
        user.set_password(password)
        user.school_id = 'ifoga'  # Par défaut
        db.session.add(user)
        db.session.commit()
        
        session['userid'] = user.id
        session['email'] = user.email
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Connexion"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session['userid'] = user.id
            session['email'] = user.email
            # Redirection selon le rôle
            if user.role == 'admin':
                return redirect(url_for('dashboard_school'))
            else:
                return redirect(url_for('dashboard'))
        return render_template('login.html', error='Email ou mot de passe incorrect')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Déconnexion"""
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard utilisateur avec historique"""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))
    
    diagnostics = Diagnostic.query.filter_by(userid=user.id).order_by(Diagnostic.createdat.desc()).all()
    return render_template('dashboard.html', 
                         user=user, 
                         diagnostics=diagnostics, 
                         totaldiagnostics=len(diagnostics))

@app.route('/app', methods=['GET', 'POST'])
@login_required
def app_diagnostic():
    """Application de diagnostic"""
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
                'nom': pathology.get('nom'),
                'description': pathology.get('description'),
                'zone': pathology.get('zone'),
                'confidence': round(confidence, 1),
                'id': path_id
            }
            
            # Sauvegarder le diagnostic
            diagnostic = Diagnostic(
                userid=user.id,
                siege=user_data.get('siege'),
                irradiations=user_data.get('irradiations'),
                typedouleur=user_data.get('type'),
                intensite=user_data.get('intensite'),
                calme_par=user_data.get('calme_par'),
                augmente_par=user_data.get('augmente_par'),
                evolution=user_data.get('evolution'),
                signes_associes=user_data.get('signes_associes'),
                diagnosisname=pathology.get('nom'),
                diagnosisconfidence=confidence,
                diagnosisid=path_id
            )
            db.session.add(diagnostic)
            db.session.commit()
        else:
            diagnosis_result = {
                'nom': 'Aucun diagnostic',
                'description': 'Aucune pathologie ne correspond.',
                'confidence': 0
            }
    
    return render_template('app.html', 
                         diagnosis=diagnosis_result, 
                         user=user, 
                         seats_by_location=SEATS_BY_LOCATION)

@app.route('/diagnostic/<int:diagnostic_id>')
@login_required
def view_diagnostic(diagnostic_id):
    """Voir un diagnostic sauvegardé"""
    user = get_current_user()
    diagnostic = Diagnostic.query.get(diagnostic_id)
    if not diagnostic or diagnostic.userid != user.id:
        return redirect(url_for('dashboard'))
    return render_template('diagnostic_detail.html', diagnostic=diagnostic, user=user)

# API Routes
@app.route('/api/pathologies', methods=['GET'])
def api_pathologies():
    return jsonify(PATHOLOGIES)

@app.route('/api/diagnosis', methods=['POST'])
@login_required
def api_diagnosis():
    user = get_current_user()
    data = request.json
    result = find_diagnosis(data)
    if result:
        path_id, pathology, confidence = result
        diagnostic = Diagnostic(
            userid=user.id,
            diagnosisname=pathology.get('nom'),
            diagnosisconfidence=confidence,
            diagnosisid=path_id
        )
        db.session.add(diagnostic)
        db.session.commit()
        return jsonify({
            'success': True,
            'diagnosis': {
                'nom': pathology.get('nom'),
                'description': pathology.get('description'),
                'zone': pathology.get('zone'),
                'confidence': round(confidence, 1),
                'id': path_id
            }
        })
    return jsonify({'success': False, 'message': 'Aucune pathologie trouvée'}), 404

@app.route('/api/user-diagnostics', methods=['GET'])
@login_required
def api_user_diagnostics():
    user = get_current_user()
    diagnostics = Diagnostic.query.filter_by(userid=user.id).order_by(Diagnostic.createdat.desc()).all()
    return jsonify([d.to_dict() for d in diagnostics])

# Dashboard école (Admin)
@app.route('/dashboard-school')
@login_required
def dashboard_school():
    """Dashboard école - Stats anonymisées (Admin Only)"""
    user = get_current_user()
    if user.role != 'admin':
        return redirect(url_for('dashboard'))
    
    school_diagnostics = Diagnostic.query.join(User).filter(User.school_id == user.school_id).all()
    total_diagnostics = len(school_diagnostics)
    active_students = len(set(d.userid for d in school_diagnostics))
    
    today = datetime.utcnow()
    month_ago = today - timedelta(days=30)
    month_diagnostics = [d for d in school_diagnostics if d.createdat > month_ago]
    active_this_month = len(set(d.userid for d in month_diagnostics))
    
    pathology_counts = {}
    for diag in school_diagnostics:
        if diag.diagnosisname:
            pathology_counts[diag.diagnosisname] = pathology_counts.get(diag.diagnosisname, 0) + 1
    
    top_pathologies = sorted(pathology_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    
    confidences = [d.diagnosisconfidence for d in school_diagnostics if d.diagnosisconfidence]
    avg_confidence = round(sum(confidences) / len(confidences), 1) if confidences else 0
    
    stats = {
        'total_diagnostics': total_diagnostics,
        'active_students': active_students,
        'active_this_month': active_this_month,
        'avg_confidence': avg_confidence,
        'top_pathologies': top_pathologies,
        'school_name': user.school_id.upper()
    }
    
    return render_template('dashboard-school.html', user=user, stats=stats)

@app.route('/api/school-stats/export-csv')
@login_required
def export_school_stats_csv():
    """Export stats école en CSV"""
    user = get_current_user()
    if user.role != 'admin':
        return 'Accès refusé', 403
    
    school_diagnostics = Diagnostic.query.join(User).filter(User.school_id == user.school_id).all()
    output = StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['Date', 'Pathologie', 'Confiance (%)', 'Siège', 'Type Douleur'])
    for diag in sorted(school_diagnostics, key=lambda x: x.createdat, reverse=True):
        writer.writerow([
            diag.createdat.strftime('%Y-%m-%d %H:%M'),
            diag.diagnosisname or 'N/A',
            round(diag.diagnosisconfidence, 1) if diag.diagnosisconfidence else 'N/A',
            diag.siege or 'N/A',
            diag.typedouleur or 'N/A'
        ])
    
    csv_data = output.getvalue()
    output.close()
    
    bytes_output = BytesIO(csv_data.encode('utf-8'))
    bytes_output.seek(0)
    
    return send_file(bytes_output, mimetype='text/csv', as_attachment=True, 
                     download_name=f'osteotech-stats-{user.school_id}-{datetime.utcnow().strftime("%Y%m%d")}.csv')

# Gestion d'erreurs
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# Initialisation base de données
@app.before_request
def create_tables():
    """Créer les tables et l'admin au démarrage"""
    db.create_all()
    
    # Créer l'admin s'il n'existe pas (une seule fois)
    with app.app_context():
        if not hasattr(create_tables, 'admin_created'):
            if not User.query.filter_by(email='admin@ifoga.fr').first():
                admin = User(email='admin@ifoga.fr', role='admin', school_id='ifoga')
                admin.set_password('Admin123!')
                db.session.add(admin)
                db.session.commit()
                print("Admin créé: admin@ifoga.fr / Admin123!")
            create_tables.admin_created = True

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
