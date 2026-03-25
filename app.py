from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime
import anthropic
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///messages.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# CORS - Allow all your frontend domains
CORS(app, supports_credentials=True, origins=[
    'http://localhost:3000',
    'http://localhost:3001',
    'https://smart-chat-frontend-rho.vercel.app',
    'https://smart-chat-frontend-beta.vercel.app',
    'https://smart-chat-frontend.vercel.app',
    'https://smart-chat-frontend-xi.vercel.app',
    'https://smart-chat-frontend-git-main.vercel.app'
])

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# Your Anthropic API key
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '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')
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ============ DATABASE MODELS ============

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email
        }

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    conversation_id = db.Column(db.String(50), nullable=False)
    sender = db.Column(db.String(50), nullable=False)
    text = db.Column(db.Text, nullable=False)
    tone = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'sender': self.sender,
            'text': self.text,
            'tone': self.tone,
            'timestamp': self.timestamp.strftime('%H:%M')
        }

# Create database tables
with app.app_context():
    db.create_all()
    print("✅ Database created!")

# ============ HELPER FUNCTIONS ============

def save_message(user_id, conversation_id, sender, text, tone=None):
    message = Message(
        user_id=user_id,
        conversation_id=conversation_id,
        sender=sender,
        text=text,
        tone=tone
    )
    db.session.add(message)
    db.session.commit()
    return message

def get_messages(user_id, conversation_id):
    messages = Message.query.filter_by(user_id=user_id, conversation_id=conversation_id).order_by(Message.timestamp).all()
    return [msg.to_dict() for msg in messages]

# ============ AUTH ROUTES ============

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.json
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username already exists'}), 400
        
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already exists'}), 400
        
        # Hash password and create user
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(username=username, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        
        # Store user in session
        session['user_id'] = new_user.id
        
        return jsonify({'user': new_user.to_dict(), 'message': 'Registration successful'}), 201
        
    except Exception as error:
        print(f"❌ Register error: {error}")
        return jsonify({'error': str(error)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if not user or not bcrypt.check_password_hash(user.password, password):
            return jsonify({'error': 'Invalid username or password'}), 401
        
        session['user_id'] = user.id
        
        return jsonify({'user': user.to_dict(), 'message': 'Login successful'}), 200
        
    except Exception as error:
        print(f"❌ Login error: {error}")
        return jsonify({'error': str(error)}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({'message': 'Logged out successfully'}), 200

@app.route('/api/me', methods=['GET'])
def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
        
    return jsonify({'user': user.to_dict()}), 200

@app.route('/api/users', methods=['GET'])
def get_all_users():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Not logged in'}), 401
        
        # Get all users except current user
        users = User.query.filter(User.id != user_id).all()
        return jsonify({'users': [user.to_dict() for user in users]})
        
    except Exception as error:
        print(f"❌ Users error: {error}")
        return jsonify({'error': str(error)}), 500

# ============ CHAT ROUTES ============

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Not logged in'}), 401
        
        data = request.json
        system_prompt = data.get('systemPrompt', '')
        user_content = data.get('userContent', '')
        max_tokens = data.get('maxTokens', 512)
        
        print(f"🤔 Thinking about: {user_content[:50]}...")
        
        response = client.messages.create(
            model="claude-3-sonnet-20241022",
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}]
        )
        
        answer = response.content[0].text
        print(f"✅ Got answer: {answer[:50]}...")
        
        return jsonify({"content": answer})
        
    except Exception as error:
        print(f"❌ Chat error: {error}")
        return jsonify({"error": str(error)}), 500

@app.route('/api/save-message', methods=['POST'])
def save_message_endpoint():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Not logged in'}), 401
        
        data = request.json
        conversation_id = data.get('conversation_id')
        sender = data.get('sender')
        text = data.get('text')
        tone = data.get('tone')
        
        message = save_message(user_id, conversation_id, sender, text, tone)
        return jsonify(message.to_dict())
        
    except Exception as error:
        print(f"❌ Error saving message: {error}")
        return jsonify({"error": str(error)}), 500

@app.route('/api/load-messages/<conversation_id>', methods=['GET'])
def load_messages_endpoint(conversation_id):
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Not logged in'}), 401
        
        messages = get_messages(user_id, conversation_id)
        return jsonify({"messages": messages})
        
    except Exception as error:
        print(f"❌ Error loading messages: {error}")
        return jsonify({"error": str(error)}), 500

# ============ HEALTH CHECK ============

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "message": "I'm alive! 🎉"})

# ============ START SERVER ============

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 SMARTCHAT BACKEND STARTING (with User Accounts!)")
    print("="*50)
    print("📍 Server at: http://localhost:3001")
    print("📝 API at: http://localhost:3001/api/chat")
    print("💚 Health: http://localhost:3001/api/health")
    print("👤 Auth: /api/register, /api/login, /api/logout")
    print("👥 Users: /api/users")
    print("💾 Database: messages.db")
    print("="*50)
    print("\n✨ Backend is ready!\n")
    app.run(port=3001, debug=True)