from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
import jwt
import anthropic
import os
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///messages.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Updated CORS configuration
CORS(
    app,
    supports_credentials=True,
    origins=[
        'http://localhost:3000',
        'http://localhost:3001',
        'https://smart-chat-frontend-rho.vercel.app',
        'https://smart-chat-frontend-beta.vercel.app',
        'https://smart-chat-frontend.vercel.app',
        'https://smart-chat-frontend-xi.vercel.app'
    ],
    allow_headers=["Content-Type", "Authorization"]
)

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
    receiver = db.Column(db.String(50), nullable=False)
    text = db.Column(db.Text, nullable=False)
    tone = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'sender': self.sender,
            'receiver': self.receiver,
            'text': self.text,
            'tone': self.tone,
            'timestamp': self.timestamp.strftime('%H:%M')
        }

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'created_by': self.created_by,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M')
        }

class GroupMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'group_id': self.group_id,
            'user_id': self.user_id,
            'joined_at': self.joined_at.strftime('%Y-%m-%d %H:%M')
        }

# Create database tables
with app.app_context():
    db.create_all()
    print("✅ Database created!")

# ============ JWT HELPER ============

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token.split(' ')[1]
            
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = User.query.get(data['user_id'])
            if not current_user:
                return jsonify({'error': 'User not found'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated

# ============ HELPER FUNCTIONS ============

def save_message(user_id, sender, receiver, text, tone=None):
    conversation_id = receiver
    message = Message(
        user_id=user_id,
        conversation_id=conversation_id,
        sender=sender,
        receiver=receiver,
        text=text,
        tone=tone
    )
    db.session.add(message)
    db.session.commit()
    return message

def get_messages(user_id, other_user_id):
    messages = Message.query.filter(
        ((Message.sender == str(user_id)) & (Message.receiver == str(other_user_id))) |
        ((Message.sender == str(other_user_id)) & (Message.receiver == str(user_id)))
    ).order_by(Message.timestamp).all()
    return [msg.to_dict() for msg in messages]

# ============ AUTH ROUTES ============

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.json
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username already exists'}), 400
        
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already exists'}), 400
        
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(username=username, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        
        token = jwt.encode({
            'user_id': new_user.id,
            'exp': datetime.utcnow() + timedelta(days=7)
        }, app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'user': new_user.to_dict(),
            'token': token,
            'message': 'Registration successful'
        }), 201
        
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
        
        token = jwt.encode({
            'user_id': user.id,
            'exp': datetime.utcnow() + timedelta(days=7)
        }, app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'user': user.to_dict(),
            'token': token,
            'message': 'Login successful'
        }), 200
        
    except Exception as error:
        print(f"❌ Login error: {error}")
        return jsonify({'error': str(error)}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    return jsonify({'message': 'Logged out successfully'}), 200

@app.route('/api/me', methods=['GET'])
@token_required
def get_current_user(current_user):
    return jsonify({'user': current_user.to_dict()}), 200

@app.route('/api/users', methods=['GET'])
@token_required
def get_all_users(current_user):
    try:
        users = User.query.filter(User.id != current_user.id).all()
        return jsonify({'users': [user.to_dict() for user in users]})
        
    except Exception as error:
        print(f"❌ Users error: {error}")
        return jsonify({'error': str(error)}), 500

# ============ CHAT ROUTES ============

@app.route('/api/chat', methods=['POST'])
@token_required
def chat(current_user):
    try:
        data = request.json
        system_prompt = data.get('systemPrompt', '')
        user_content = data.get('userContent', '')
        max_tokens = data.get('maxTokens', 512)
        
        print(f"🤔 Thinking about: {user_content[:50]}...")
        print(f"API Key exists: {bool(ANTHROPIC_API_KEY)}")
        
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
@token_required
def save_message_endpoint(current_user):
    try:
        data = request.json
        sender = data.get('sender')
        receiver = data.get('receiver')
        text = data.get('text')
        tone = data.get('tone')
        
        print(f"💾 Saving message - Sender: {sender}, Receiver: {receiver}, Text: {text[:50]}...")
        
        message = save_message(current_user.id, sender, receiver, text, tone)
        
        print(f"✅ Message saved with ID: {message.id}")
        
        return jsonify(message.to_dict())
        
    except Exception as error:
        print(f"❌ Error saving message: {error}")
        return jsonify({"error": str(error)}), 500

@app.route('/api/load-messages/<other_user_id>', methods=['GET'])
@token_required
def load_messages_endpoint(current_user, other_user_id):
    try:
        print(f"📖 Loading messages between user {current_user.id} and {other_user_id}")
        
        messages = get_messages(current_user.id, other_user_id)
        
        print(f"✅ Found {len(messages)} messages")
        
        return jsonify({"messages": messages})
        
    except Exception as error:
        print(f"❌ Error loading messages: {error}")
        return jsonify({"error": str(error)}), 500

# ============ GROUP ROUTES ============

@app.route('/api/groups', methods=['GET'])
@token_required
def get_groups(current_user):
    try:
        # Get groups where user is a member
        groups = Group.query.join(GroupMember).filter(GroupMember.user_id == current_user.id).all()
        return jsonify({'groups': [group.to_dict() for group in groups]})
    except Exception as error:
        print(f"❌ Groups error: {error}")
        return jsonify({'error': str(error)}), 500

@app.route('/api/groups', methods=['POST'])
@token_required
def create_group(current_user):
    try:
        data = request.json
        name = data.get('name')
        description = data.get('description', '')
        
        if not name:
            return jsonify({'error': 'Group name is required'}), 400
        
        # Create group
        new_group = Group(name=name, description=description, created_by=current_user.id)
        db.session.add(new_group)
        db.session.flush()
        
        # Add creator as member
        member = GroupMember(group_id=new_group.id, user_id=current_user.id)
        db.session.add(member)
        db.session.commit()
        
        return jsonify({'group': new_group.to_dict(), 'message': 'Group created successfully'}), 201
        
    except Exception as error:
        print(f"❌ Create group error: {error}")
        return jsonify({'error': str(error)}), 500

@app.route('/api/groups/<int:group_id>/join', methods=['POST'])
@token_required
def join_group(current_user, group_id):
    try:
        # Check if group exists
        group = Group.query.get(group_id)
        if not group:
            return jsonify({'error': 'Group not found'}), 404
        
        # Check if already a member
        existing = GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first()
        if existing:
            return jsonify({'error': 'Already a member'}), 400
        
        # Add member
        member = GroupMember(group_id=group_id, user_id=current_user.id)
        db.session.add(member)
        db.session.commit()
        
        return jsonify({'message': 'Joined group successfully'}), 200
        
    except Exception as error:
        print(f"❌ Join group error: {error}")
        return jsonify({'error': str(error)}), 500

@app.route('/api/groups/<int:group_id>/members', methods=['GET'])
@token_required
def get_group_members(current_user, group_id):
    try:
        # Check if user is a member
        member = GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first()
        if not member:
            return jsonify({'error': 'Not a member of this group'}), 403
        
        # Get all members
        members = db.session.query(User).join(GroupMember).filter(GroupMember.group_id == group_id).all()
        return jsonify({'members': [user.to_dict() for user in members]})
        
    except Exception as error:
        print(f"❌ Get members error: {error}")
        return jsonify({'error': str(error)}), 500

@app.route('/api/groups/<int:group_id>/members', methods=['POST'])
@token_required
def add_group_member(current_user, group_id):
    try:
        data = request.json
        user_id = data.get('user_id')
        
        # Check if group exists
        group = Group.query.get(group_id)
        if not group:
            return jsonify({'error': 'Group not found'}), 404
        
        # Check if current user is the creator
        if group.created_by != current_user.id:
            return jsonify({'error': 'Only group creator can add members'}), 403
        
        # Check if user exists
        user_to_add = User.query.get(user_id)
        if not user_to_add:
            return jsonify({'error': 'User not found'}), 404
        
        # Check if already a member
        existing = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
        if existing:
            return jsonify({'error': 'User is already a member'}), 400
        
        # Add member
        member = GroupMember(group_id=group_id, user_id=user_id)
        db.session.add(member)
        db.session.commit()
        
        return jsonify({'message': f'{user_to_add.username} added to group successfully'}), 200
        
    except Exception as error:
        print(f"❌ Add member error: {error}")
        return jsonify({'error': str(error)}), 500

@app.route('/api/groups/<int:group_id>/messages', methods=['GET'])
@token_required
def get_group_messages(current_user, group_id):
    try:
        # Check if user is a member
        member = GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first()
        if not member:
            print(f"❌ User {current_user.id} is not a member of group {group_id}")
            return jsonify({'error': 'Not a member of this group'}), 403
        
        # Get messages for this group
        messages = Message.query.filter_by(conversation_id=f"group_{group_id}").order_by(Message.timestamp).all()
        print(f"📖 Found {len(messages)} messages for group {group_id}")
        return jsonify({'messages': [msg.to_dict() for msg in messages]})
        
    except Exception as error:
        print(f"❌ Get group messages error: {error}")
        return jsonify({'error': str(error)}), 500

@app.route('/api/groups/<int:group_id>/messages', methods=['POST'])
@token_required
def send_group_message(current_user, group_id):
    try:
        # Check if user is a member
        member = GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first()
        if not member:
            print(f"❌ User {current_user.id} is not a member of group {group_id}")
            return jsonify({'error': 'Not a member of this group'}), 403
        
        data = request.json
        text = data.get('text')
        
        if not text:
            return jsonify({'error': 'Message text is required'}), 400
        
        print(f"💾 Saving group message - Group: {group_id}, User: {current_user.username}, Text: {text[:50]}...")
        
        # Save group message
        message = Message(
            user_id=current_user.id,
            conversation_id=f"group_{group_id}",
            sender=str(current_user.id),
            receiver=f"group_{group_id}",
            text=text
        )
        db.session.add(message)
        db.session.commit()
        
        print(f"✅ Group message saved with ID: {message.id}")
        
        return jsonify(message.to_dict()), 201
        
    except Exception as error:
        print(f"❌ Send group message error: {error}")
        return jsonify({'error': str(error)}), 500

# ============ HEALTH CHECK ============

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "message": "I'm alive! 🎉"})

# ============ START SERVER ============

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 SMARTCHAT BACKEND STARTING (with Groups & Members!)")
    print("="*50)
    print("📍 Server at: http://localhost:3001")
    print("📝 Chat API: http://localhost:3001/api/chat")
    print("💚 Health: http://localhost:3001/api/health")
    print("👤 Auth: /api/register, /api/login, /api/logout")
    print("👥 Users: /api/users")
    print("👥 Groups: /api/groups")
    print("👥 Group Members: /api/groups/<id>/members")
    print("💬 Group Messages: /api/groups/<id>/messages")
    print("💾 Database: messages.db")
    print("="*50)
    print("\n✨ Backend is ready!\n")
    app.run(port=3001, debug=True)