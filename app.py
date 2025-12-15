from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file

from flask_sqlalchemy import SQLAlchemy

from functools import wraps

import json

from pathlib import Path

from datetime import datetime, timedelta

from models import db, User, Diagnostic

import csv

from io import StringIO

app = Flask(__name__)

# ============================================

# CONFIGURATION

# ============================================

app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///osteotech.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialiser la base de données

db.init_app(app)

# ============================================

# CHARGEMENT DES PATHOLOGIES

# ============================================

def load_pathologies():

    """Charger les pathologies depuis le fichier JSON"""

    try:

        json_path = Path(__file__).parent / 'pathologies.json'

        with open(json_path, 'r', encoding='utf-8') as f:

            return json.load(f)

    except FileNotFoundError:

        print("❌ Erreur: pathologies.json non trouvé")

        return {}

PATHOLOGIES = load_pathologies()

# ============================================

# CONFIG LOCALISATION → SIÈGES

# ============================================

SEATS_BY_LOCATION = {

    "Céphalée": ["Base du crâne", "Crâne Global", "Front", "Hémicrâne", "Hémiface", "Face postérieure du Crâne", "Tempes", "Orbito-frontal", "Sous-orbitaire"],

    "Douleur Abdominale": ["Epigastre", "F.I.D", "Hypocondre Droit", "Hypogastre", "Tout l'Abdomen", "Latéro-thoracique"],

    "Douleur Cervicale": ["Cou", "Inter-scapulaire", "Rachis thoracique"],

    "Douleur du Membre Supérieur": ["Bras", "Epaule", "Face antérieure du Poignet", "Face latérale du Coude", "Face médiale du Coude", "Pouce", "Base d'un doigt"],

    "Douleur du Membre Inférieur": ["Membre Inférieur", "Face externe du Genou", "Face externe de la Cheville", "Hallux", "Inter-orteil", "Mollet", "Talon", "T.T.A"],

    "Douleur Thoracique": ["Latéro-thoracique", "Rétrosternal"],

    "Facialgie": ["Hémiface", "Front", "Tempes", "Sous-orbitaire"],

    "Lombalgie": ["Lombaire"]

}

# ============================================

# DÉCORATEURS

# ============================================

def login_required(f):

    """Décorateur pour vérifier si l'utilisateur est connecté"""

    @wraps(f)

    def decorated_function(*args, **kwargs):

        if 'user_id' not in session:

            return redirect(url_for('login'))

        return f(*args, **kwargs)

    return decorated_function

def get_current_user():

    """Récupérer l'utilisateur connecté"""

    if 'user_id' in session:

        return User.query.get(session['user_id'])

    return None

# ============================================

# MOTEUR DE DIAGNOSTIC

# ============================================

def find_diagnosis(user_data):

    """Moteur diagnostique : trouver la pathologie qui match"""

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

        match_percentage = (score / total_criteria) * 100 if total_criteria > 0 else 0

        if match_percentage > best_score:

            best_score = match_percentage

            best_match = (path_id, pathology, match_percentage)

    return best_match if best_match and best_score > 50 else None

# ============================================

# ROUTES AUTHENTIFICATION

# ============================================

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

        user.school_id = 'ifoga'  # ← LIGNE AJOUTÉE POUR AUTO-ASSIGNEMENT

        db.session.add(user)

        db.session.commit()

        session['user_id'] = user.id

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

            session['user_id'] = user.id

            session['email'] = user.email

            # Si admin, aller au dashboard école

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

# ============================================

# ROUTES PRINCIPALES

# ============================================

@app.route('/')

def index():

    """Page d'accueil"""

    user = get_current_user()

    return render_template('index.html', user=user)

@app.route('/dashboard')

@login_required

def dashboard():

    """Dashboard utilisateur avec historique"""

    user = get_current_user()

    diagnostics = Diagnostic.query.filter_by(user_id=user.id).order_by(Diagnostic.created_at.desc()).all()

    return render_template('dashboard.html', user=user, diagnostics=diagnostics, total_diagnostics=len(diagnostics))

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

            'type_douleur': request.form.get('type'),

            'intensite': request.form.get('intensite'),

            'calmee_par': request.form.get('calmee_par'),

            'augmentee_par': request.form.get('augmentee_par'),

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

                user_id=user.id,

                siege=user_data.get('siege'),

                irradiations=user_data.get('irradiations'),

                type_douleur=user_data.get('type_douleur'),

                intensite=user_data.get('intensite'),

                calmee_par=user_data.get('calmee_par'),

                augmentee_par=user_data.get('augmentee_par'),

                evolution=user_data.get('evolution'),

                signes_associes=user_data.get('signes_associes'),

                diagnosis_name=pathology.get('nom'),

                diagnosis_confidence=confidence,

                diagnosis_id=path_id

            )

            db.session.add(diagnostic)

            db.session.commit()

        else:

            diagnosis_result = {

                'nom': 'Aucun diagnostic',

                'description': 'Aucune pathologie ne correspond.',

                'confidence': 0

            }

    return render_template('app.html', diagnosis=diagnosis_result, user=user, seats_by_location=SEATS_BY_LOCATION)

@app.route('/diagnostic/<int:diagnostic_id>')

@login_required

def view_diagnostic(diagnostic_id):

    """Voir un diagnostic sauvegardé"""

    user = get_current_user()

    diagnostic = Diagnostic.query.get(diagnostic_id)

    if not diagnostic or diagnostic.user_id != user.id:

        return redirect(url_for('dashboard'))

    return render_template('diagnostic_detail.html', diagnostic=diagnostic, user=user)

# ============================================

# ROUTES API

# ============================================

@app.route('/api/pathologies', methods=['GET'])

def api_pathologies():

    """API pour récupérer toutes les pathologies"""

    return jsonify(PATHOLOGIES)

@app.route('/api/diagnosis', methods=['POST'])

@login_required

def api_diagnosis():

    """API pour obtenir un diagnostic"""

    user = get_current_user()

    data = request.json

    result = find_diagnosis(data)

    if result:

        path_id, pathology, confidence = result

        diagnostic = Diagnostic(

            user_id=user.id,

            diagnosis_name=pathology.get('nom'),

            diagnosis_confidence=confidence,

            diagnosis_id=path_id

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

@app.route('/api/user/diagnostics', methods=['GET'])

@login_required

def api_user_diagnostics():

    """API : historique diagnostics de l'utilisateur"""

    user = get_current_user()

    diagnostics = Diagnostic.query.filter_by(user_id=user.id).order_by(Diagnostic.created_at.desc()).all()

    return jsonify([d.to_dict() for d in diagnostics])

# ============================================

# GESTION ERREURS

# ============================================

@app.errorhandler(404)

def not_found(error):

    return {"error": "Page non trouvée"}, 404

@app.errorhandler(500)

def internal_error(error):

    db.session.rollback()

    return {"error": "Erreur serveur"}, 500

# ============================================

# CRÉATION BASE DE DONNÉES & INITIALIZATION

# ============================================

@app.before_request

def create_tables():

    """Créer les tables au démarrage"""

    db.create_all()

@app.before_first_request

def init_admin():

     # Créer l'admin s'il n'existe pas (une seule fois)
    if not hasattr(create_tables, '_admin_created'):
        with app.app_context():
            if not User.query.filter_by(email='admin@ifoga.fr').first():
                admin = User(email='admin@ifoga.fr', role='admin', school_id='ifoga')
                admin.set_password('Admin123!')
                db.session.add(admin)
                db.session.commit()
                print("✅ Admin créé: admin@ifoga.fr / Admin123!")
        create_tables._admin_created = True

# ============================================

# ROUTES DASHBOARD ÉCOLE (Admin Only)

# ============================================

@app.route('/dashboard-school')

@login_required

def dashboard_school():

    """Dashboard école - Stats anonymisées (Admin Only)"""

    user = get_current_user()

    if user.role != 'admin':

        return redirect(url_for('dashboard'))

    school_diagnostics = Diagnostic.query.join(User).filter(

        User.school_id == user.school_id

    ).all()

    total_diagnostics = len(school_diagnostics)

    active_students = len(set(d.user_id for d in school_diagnostics))

    today = datetime.utcnow()

    month_ago = today - timedelta(days=30)

    month_diagnostics = [d for d in school_diagnostics if d.created_at >= month_ago]

    active_this_month = len(set(d.user_id for d in month_diagnostics))

    pathology_counts = {}

    for diag in school_diagnostics:

        if diag.diagnosis_name:

            pathology_counts[diag.diagnosis_name] = pathology_counts.get(diag.diagnosis_name, 0) + 1

    top_pathologies = sorted(pathology_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    confidences = [d.diagnosis_confidence for d in school_diagnostics if d.diagnosis_confidence]

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

        return {"error": "Accès refusé"}, 403

    school_diagnostics = Diagnostic.query.join(User).filter(

        User.school_id == user.school_id

    ).all()

    output = StringIO()

    writer = csv.writer(output)

    writer.writerow(['Date', 'Pathologie', 'Confiance (%)', 'Siège', 'Type Douleur'])

    for diag in sorted(school_diagnostics, key=lambda x: x.created_at, reverse=True):

        writer.writerow([

            diag.created_at.strftime('%Y-%m-%d %H:%M'),

            diag.diagnosis_name or 'N/A',

            round(diag.diagnosis_confidence, 1) if diag.diagnosis_confidence else 'N/A',

            diag.siege or 'N/A',

            diag.type_douleur or 'N/A'

        ])

    # Récupérer le contenu et créer un BytesIO

    csv_data = output.getvalue()

    output.close()

    from io import BytesIO

    bytes_output = BytesIO(csv_data.encode('utf-8'))

    bytes_output.seek(0)

    return send_file(

        bytes_output,

        mimetype='text/csv',

        as_attachment=True,

        download_name=f"osteotech_stats_{user.school_id}_{datetime.utcnow().strftime('%Y%m%d')}.csv"

    )

if __name__ == '__main__':

    app.run(debug=True, host='0.0.0.0', port=5000)
