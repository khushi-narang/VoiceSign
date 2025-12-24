from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class SignVideo(db.Model):
    """
    Model representing a sign language video
    """
    id = db.Column(db.Integer, primary_key=True)
    gloss_word = db.Column(db.String(50), nullable=False, unique=True, index=True)
    file_path = db.Column(db.String(255), nullable=False)
    duration = db.Column(db.Float, nullable=True)  # Duration in seconds
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Translation(db.Model):
    """
    Model representing a translation from speech to ISL
    """
    id = db.Column(db.Integer, primary_key=True)
    original_text = db.Column(db.Text, nullable=False)
    gloss_text = db.Column(db.Text, nullable=False)
    audio_path = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_successful = db.Column(db.Boolean, default=True)
    
    # Fields to store metrics
    recognition_confidence = db.Column(db.Float, nullable=True)
    translation_time = db.Column(db.Float, nullable=True)  # Time taken to process in ms


class UserFeedback(db.Model):
    """
    Model for storing user feedback on translations
    """
    id = db.Column(db.Integer, primary_key=True)
    translation_id = db.Column(db.Integer, db.ForeignKey('translation.id'), nullable=False)
    accuracy_rating = db.Column(db.Integer)  # 1-5 star rating
    comments = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    translation = db.relationship('Translation', backref=db.backref('feedback', lazy=True))