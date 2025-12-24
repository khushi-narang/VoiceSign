import os
import logging
import time
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for

# Optional: load environment variables from .env for local development
try:
    from dotenv import load_dotenv
    _DOTENV_AVAILABLE = True
except Exception:
    _DOTENV_AVAILABLE = False

if _DOTENV_AVAILABLE:
    # Load .env file from the project directory if present
    dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
from utils.speech_to_text import convert_speech_to_text
from utils.text_to_gloss import convert_text_to_gloss
from utils.video_retrieval import get_video_paths
from utils.gratitude import is_gratitude
from models import db, SignVideo, Translation, UserFeedback

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key")

# Configure the database
# Use DATABASE_URL if provided, otherwise default to a local SQLite file
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    # Use a SQLite DB file inside the project directory for local development
    db_path = os.path.join(os.path.dirname(__file__), 'voice_sign_bridge.db')
    # Convert Windows backslashes to forward slashes for SQLAlchemy URI
    db_path_abs = os.path.abspath(db_path).replace('\\', '/')
    database_url = f"sqlite:///{db_path_abs}"

logger.info(f"Using database URL: {database_url}")
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Initialize the app with the extension
db.init_app(app)

# Ensure required directories exist
video_directory = os.path.join(app.static_folder, 'videos')
os.makedirs(video_directory, exist_ok=True)

# Create database tables if they don't exist
with app.app_context():
    db.create_all()

@app.route('/')
def index():
    """Render the main page of the application."""
    return render_template('index.html')

@app.route('/history')
def history():
    """Show translation history from the database."""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    search = request.args.get('search', '')
    
    # Get translations from database
    query = Translation.query
    if search:
        query = query.filter(Translation.original_text.ilike(f'%{search}%') | 
                             Translation.gloss_text.ilike(f'%{search}%'))
    
    # Paginate results
    paginated = query.order_by(Translation.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    translations = paginated.items
    total_pages = paginated.pages
    
    return render_template('history.html', 
                          translations=translations, 
                          page=page, 
                          total_pages=total_pages,
                          search=search)

@app.route('/translation/<int:translation_id>')
def view_translation(translation_id):
    """View details of a specific translation."""
    translation = Translation.query.get_or_404(translation_id)
    
    # Get feedback if it exists
    feedback = UserFeedback.query.filter_by(translation_id=translation_id).first()
    
    # Get related translations (with similar text)
    related_translations = []
    if translation.original_text:
        words = translation.original_text.split()
        if words:
            # Use the first word for finding related translations
            search_term = words[0]
            related_translations = Translation.query.filter(
                Translation.id != translation_id,
                Translation.original_text.ilike(f'%{search_term}%')
            ).order_by(Translation.timestamp.desc()).limit(5).all()
    
    # Get video models that match the gloss text
    videos = []
    if translation.gloss_text:
        gloss_words = translation.gloss_text.split()
        for word in gloss_words:
            video = SignVideo.query.filter_by(gloss_word=word.lower()).first()
            if video:
                videos.append(video)
    
    return render_template('view_translation.html', 
                          translation=translation,
                          feedback=feedback,
                          related_translations=related_translations,
                          videos=videos)

@app.route('/feedback/<int:translation_id>', methods=['POST'])
def submit_feedback(translation_id):
    """Save user feedback for a translation."""
    translation = Translation.query.get_or_404(translation_id)
    
    try:
        # Get form data
        rating = request.form.get('rating', type=int)
        comments = request.form.get('comments', '')
        
        if rating and 1 <= rating <= 5:
            # Check if feedback already exists
            existing_feedback = UserFeedback.query.filter_by(translation_id=translation_id).first()
            
            if existing_feedback:
                # Update existing feedback
                existing_feedback.accuracy_rating = rating
                existing_feedback.comments = comments
            else:
                # Create new feedback
                new_feedback = UserFeedback(
                    translation_id=translation_id,
                    accuracy_rating=rating,
                    comments=comments
                )
                db.session.add(new_feedback)
                
            db.session.commit()
            
            return redirect(url_for('view_translation', translation_id=translation_id))
        else:
            return "Invalid rating", 400
            
    except Exception as e:
        logger.error(f"Error submitting feedback: {str(e)}")
        db.session.rollback()
        return "Error submitting feedback", 500

@app.route('/process-audio', methods=['POST'])
def process_audio():
    """
    Process the audio file sent from the client.
    1. Convert speech to text
    2. Convert text to ISL gloss
    3. Retrieve video paths for the gloss terms
    4. Save translation to database
    """
    try:
        # Check if the post request has the file part
        if 'audio' not in request.files:
            logger.error("No audio file in request")
            return jsonify({'error': 'No audio file provided'}), 400
        
        audio_file = request.files['audio']
        logger.debug(f"Received audio file: {audio_file.filename}, "
                    f"content type: {audio_file.content_type}, "
                    f"mime type: {audio_file.mimetype}")
        
        # Measure processing time
        start_time = time.time()
        
        # Process the audio to get text
        logger.debug("Processing audio file to text")
        text = convert_speech_to_text(audio_file)
        
        if not text:
            logger.error("Speech recognition failed")
            # Save failed translation to database
            new_translation = Translation(
                original_text="Unknown",
                gloss_text="",
                is_successful=False,
                translation_time=0
            )
            db.session.add(new_translation)
            db.session.commit()
            
            return jsonify({
                'error': 'Could not recognize speech in the audio. '
                         'Please speak clearly and ensure your microphone is working.'
            }), 400
        
        # If user just said a gratitude phrase (e.g., "thank you"), treat specially
        if is_gratitude(text):
            logger.info("Detected gratitude utterance; skipping video retrieval")
            # Save translation (optional) as a short gratitude record
            new_translation = Translation(
                original_text=text,
                gloss_text='[GRATITUDE]',
                is_successful=True,
                translation_time=0
            )
            db.session.add(new_translation)
            db.session.commit()

            return jsonify({
                'text': text,
                'gloss': [],
                'videos': [],
                'translation_id': new_translation.id,
                'is_gratitude': True
            })

        # Convert text to ISL gloss
        logger.debug(f"Converting text to gloss: {text}")
        gloss = convert_text_to_gloss(text)

        # Get video paths for the gloss terms
        logger.debug(f"Retrieving videos for gloss: {gloss}")
        video_paths = get_video_paths(gloss)
        
        # Calculate processing time
        process_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        # Save successful translation to database
        gloss_text = " ".join(gloss)
        new_translation = Translation(
            original_text=text,
            gloss_text=gloss_text,
            is_successful=True,
            translation_time=process_time
        )
        db.session.add(new_translation)
        db.session.commit()
        logger.info(f"Saved translation to database with ID: {new_translation.id}")
        
        # Successful response
        logger.info(f"Successfully processed audio. Text: '{text}', "
                   f"Gloss terms: {len(gloss)}, Videos: {len(video_paths)}")
        
        return jsonify({
            'text': text,
            'gloss': gloss,
            'videos': video_paths,
            'translation_id': new_translation.id
        })
        
    except Exception as e:
        logger.error(f"Error processing audio: {str(e)}")
        try:
            # Try to save error to database
            error_translation = Translation(
                original_text=f"Error: {str(e)}",
                gloss_text="",
                is_successful=False,
                translation_time=0
            )
            db.session.add(error_translation)
            db.session.commit()
        except Exception as db_error:
            logger.error(f"Could not save error to database: {str(db_error)}")
            
        return jsonify({
            'error': f"An error occurred while processing your speech: {str(e)}"
        }), 500


# Serve the avatar viewer and its static assets under /avatar
@app.route('/avatar/')
def avatar_index():
    """Serve the avatar viewer index.html from the avatar folder."""
    avatar_dir = os.path.join(os.path.dirname(__file__), 'avatar')
    return send_from_directory(avatar_dir, 'index.html')


@app.route('/avatar/<path:filename>')
def avatar_static(filename):
    """Serve files from the avatar folder (JS, glb, etc.)."""
    avatar_dir = os.path.join(os.path.dirname(__file__), 'avatar')
    return send_from_directory(avatar_dir, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
