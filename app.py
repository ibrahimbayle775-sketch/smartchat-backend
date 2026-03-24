from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import anthropic
import os

app = Flask(__name__)
CORS(app)

# Database setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///messages.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Your Anthropic API key - REPLACE WITH YOUR REAL KEY!
ANTHROPIC_API_KEY = "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"

# Create the AI client
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Database Models
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
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

# Save message to database
def save_message(conversation_id, sender, text, tone=None):
    message = Message(
        conversation_id=conversation_id,
        sender=sender,
        text=text,
        tone=tone
    )
    db.session.add(message)
    db.session.commit()
    return message

# Get messages from database
def get_messages(conversation_id):
    messages = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.timestamp).all()
    return [msg.to_dict() for msg in messages]

# API Routes
@app.route('/api/chat', methods=['POST'])
def chat():
    try:
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
        print(f"❌ Error: {error}")
        return jsonify({"error": str(error)}), 500

# Save message endpoint
@app.route('/api/save-message', methods=['POST'])
def save_message_endpoint():
    try:
        data = request.json
        conversation_id = data.get('conversation_id')
        sender = data.get('sender')
        text = data.get('text')
        tone = data.get('tone')
        
        message = save_message(conversation_id, sender, text, tone)
        return jsonify(message.to_dict())
    except Exception as error:
        print(f"❌ Error saving message: {error}")
        return jsonify({"error": str(error)}), 500

# Load messages endpoint
@app.route('/api/load-messages/<conversation_id>', methods=['GET'])
def load_messages_endpoint(conversation_id):
    try:
        messages = get_messages(conversation_id)
        return jsonify({"messages": messages})
    except Exception as error:
        print(f"❌ Error loading messages: {error}")
        return jsonify({"error": str(error)}), 500

# Health check
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "message": "I'm alive! 🎉"})

# Start the server
if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 SMARTCHAT BACKEND STARTING (with Database!)")
    print("="*50)
    print("📍 Server at: http://localhost:3001")
    print("📝 API at: http://localhost:3001/api/chat")
    print("💚 Health: http://localhost:3001/api/health")
    print("💾 Database: messages.db")
    print("="*50)
    print("\n✨ Backend is ready!\n")
    app.run(port=3001, debug=True)