from flask import Flask, render_template, request, jsonify, session, redirect, url_for

from flask_sqlalchemy import SQLAlchemy

from functools import wraps

import json

from pathlib import Path

from datetime import datetime

from models import db, User, Diagnostic

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

# MOTEUR DE DIAGNOSTIC (inchangé)

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

		# Validation

		if not email or not password:

			return render_template('register.html', error='Email et mot de passe requis')

		if password != password_confirm:

			return render_template('register.html', error='Les mots de passe ne correspondent pas')

		if len(password) < 6:

			return render_template('register.html', error='Le mot de passe doit contenir au moins 6 caractères')

		# Vérifier si utilisateur existe

		if User.query.filter_by(email=email).first():

			return render_template('register.html', error='Cet email est déjà utilisé')

		# Créer nouvel utilisateur

		user = User(email=email)

		user.set_password(password)

		db.session.add(user)

		db.session.commit()

		# Connecter automatiquement

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

	return render_template('dashboard.html',

		user=user,

		diagnostics=diagnostics,

		total_diagnostics=len(diagnostics))

@app.route('/app', methods=['GET', 'POST'])

@login_required

def app_diagnostic():

	"""Application de diagnostic (réservée aux utilisateurs connectés)"""

	user = get_current_user()

	diagnosis_result = None

	decision_tree = None

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

	return render_template('app.html',

		diagnosis=diagnosis_result,

		user=user)

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

		# Sauvegarder

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

# CRÉATION BASE DE DONNÉES

# ============================================

@app.before_request

def create_tables():

	"""Créer les tables au démarrage"""

	db.create_all()

# ============================================

# LANCEMENT

# ============================================

if __name__ == '__main__':

	app.run(debug=True, host='0.0.0.0', port=5000)
