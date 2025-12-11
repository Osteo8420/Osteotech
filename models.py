from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    """Modèle utilisateur"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relation avec diagnostics
    diagnostics = db.relationship('Diagnostic', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        """Hasher et stocker le mot de passe"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Vérifier le mot de passe"""
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        """Convertir en dictionnaire"""
        return {
            'id': self.id,
            'email': self.email,
            'created_at': self.created_at.isoformat(),
            'diagnostic_count': len(self.diagnostics)
        }


class Diagnostic(db.Model):
    """Modèle diagnostic sauvegardé"""
    __tablename__ = 'diagnostics'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Données S.I.T.I.C.E
    siege = db.Column(db.String(100))
    irradiations = db.Column(db.String(100))
    type_douleur = db.Column(db.String(100))
    intensite = db.Column(db.String(50))
    calmee_par = db.Column(db.String(100))
    augmentee_par = db.Column(db.String(100))
    evolution = db.Column(db.String(100))
    signes_associes = db.Column(db.String(200))

    # Résultat diagnostic
    diagnosis_name = db.Column(db.String(200))
    diagnosis_confidence = db.Column(db.Float)
    diagnosis_id = db.Column(db.String(100))

    # Métadonnées
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    notes = db.Column(db.Text)  # Notes utilisateur

    def to_dict(self):
        """Convertir en dictionnaire"""
        return {
            'id': self.id,
            'siege': self.siege,
            'type_douleur': self.type_douleur,
            'diagnosis_name': self.diagnosis_name,
            'diagnosis_confidence': self.diagnosis_confidence,
            'created_at': self.created_at.isoformat(),
            'notes': self.notes
        }
