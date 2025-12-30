"""
🎬 Narratives Media - Lead Icebreaker Generator v7
===================================================
Created by Habibur

🚀 NEW in v7:
- 🤖 Multiple AI Models (Gemini, OpenAI GPT-4, Claude)
- 🎯 Better Prompts - More personalized icebreakers
- 😊 Sentiment Analysis - Website tone detection
- 🎨 Industry-specific icebreaker templates
- 💾 Database - Save API keys, leads history, settings
- All v6 features (Dark/Light Mode, Dashboard, Export)

Flow: Apify → Filter → Scrape → Sentiment Analysis → AI Icebreaker → Google Sheets
"""

import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
import time
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
import io
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import sqlite3
import os
from pathlib import Path
import base64
from cryptography.fernet import Fernet

# ═══════════════════════════════════════════════════════════════
# 💾 DATABASE SYSTEM
# ═══════════════════════════════════════════════════════════════
DB_PATH = Path(__file__).parent / "narratives_data.db"
ENCRYPTION_KEY_FILE = Path(__file__).parent / ".encryption_key"

def get_encryption_key():
    """Get or create encryption key for API keys"""
    if ENCRYPTION_KEY_FILE.exists():
        return ENCRYPTION_KEY_FILE.read_bytes()
    else:
        key = Fernet.generate_key()
        ENCRYPTION_KEY_FILE.write_bytes(key)
        return key

def encrypt_value(value):
    """Encrypt sensitive data"""
    if not value:
        return ""
    try:
        f = Fernet(get_encryption_key())
        return f.encrypt(value.encode()).decode()
    except:
        return value

def decrypt_value(encrypted_value):
    """Decrypt sensitive data"""
    if not encrypted_value:
        return ""
    try:
        f = Fernet(get_encryption_key())
        return f.decrypt(encrypted_value.encode()).decode()
    except:
        return ""

def init_database():
    """Initialize SQLite database with all tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Settings table - stores API keys and preferences
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_name TEXT UNIQUE DEFAULT 'default',
            apify_token TEXT,
            gemini_key TEXT,
            openai_key TEXT,
            claude_key TEXT,
            sheet_id TEXT,
            default_provider TEXT DEFAULT 'Gemini (Google)',
            default_model TEXT DEFAULT 'Gemini 2.0 Flash (Recommended)',
            parallel_workers INTEGER DEFAULT 3,
            dark_mode INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Leads history table - stores processed leads
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            first_name TEXT,
            last_name TEXT,
            email TEXT,
            company_name TEXT,
            company_website TEXT,
            title TEXT,
            linkedin_url TEXT,
            icebreaker TEXT,
            sentiment TEXT,
            industry TEXT,
            status TEXT,
            error TEXT,
            ai_provider TEXT,
            ai_model TEXT,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Sessions table - track processing sessions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            name TEXT,
            total_leads INTEGER,
            success_count INTEGER,
            fail_count INTEGER,
            ai_provider TEXT,
            ai_model TEXT,
            duration_seconds REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create default profile if not exists
    cursor.execute('''
        INSERT OR IGNORE INTO settings (profile_name) VALUES ('default')
    ''')
    
    conn.commit()
    conn.close()

def save_settings(profile_name, apify_token="", gemini_key="", openai_key="", claude_key="", 
                  sheet_id="", default_provider="", default_model="", parallel_workers=3, dark_mode=True):
    """Save settings to database (API keys are encrypted)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO settings (profile_name, apify_token, gemini_key, openai_key, claude_key, 
                              sheet_id, default_provider, default_model, parallel_workers, dark_mode, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(profile_name) DO UPDATE SET
            apify_token = excluded.apify_token,
            gemini_key = excluded.gemini_key,
            openai_key = excluded.openai_key,
            claude_key = excluded.claude_key,
            sheet_id = excluded.sheet_id,
            default_provider = excluded.default_provider,
            default_model = excluded.default_model,
            parallel_workers = excluded.parallel_workers,
            dark_mode = excluded.dark_mode,
            updated_at = CURRENT_TIMESTAMP
    ''', (profile_name, encrypt_value(apify_token), encrypt_value(gemini_key), 
          encrypt_value(openai_key), encrypt_value(claude_key), sheet_id,
          default_provider, default_model, parallel_workers, 1 if dark_mode else 0))
    
    conn.commit()
    conn.close()

def load_settings(profile_name="default"):
    """Load settings from database (API keys are decrypted)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM settings WHERE profile_name = ?', (profile_name,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'profile_name': row[1],
            'apify_token': decrypt_value(row[2]),
            'gemini_key': decrypt_value(row[3]),
            'openai_key': decrypt_value(row[4]),
            'claude_key': decrypt_value(row[5]),
            'sheet_id': row[6],
            'default_provider': row[7],
            'default_model': row[8],
            'parallel_workers': row[9],
            'dark_mode': bool(row[10])
        }
    return None

def get_all_profiles():
    """Get list of all saved profiles"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT profile_name FROM settings ORDER BY profile_name')
    profiles = [row[0] for row in cursor.fetchall()]
    conn.close()
    return profiles

def delete_profile(profile_name):
    """Delete a profile"""
    if profile_name == 'default':
        return False
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM settings WHERE profile_name = ?', (profile_name,))
    conn.commit()
    conn.close()
    return True

def save_leads_to_history(leads, session_id, ai_provider, ai_model):
    """Save processed leads to history"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for lead in leads:
        cursor.execute('''
            INSERT INTO leads_history 
            (session_id, first_name, last_name, email, company_name, company_website, 
             title, linkedin_url, icebreaker, sentiment, industry, status, error, ai_provider, ai_model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            session_id,
            lead.get('first_name', ''),
            lead.get('last_name', ''),
            lead.get('email', ''),
            lead.get('company_name', ''),
            lead.get('company_website', ''),
            lead.get('title', ''),
            lead.get('linkedin_url', ''),
            lead.get('icebreaker', ''),
            lead.get('sentiment', ''),
            lead.get('industry', ''),
            lead.get('status', ''),
            lead.get('error', ''),
            ai_provider,
            ai_model
        ))
    
    conn.commit()
    conn.close()

def save_session(session_id, name, total_leads, success_count, fail_count, ai_provider, ai_model, duration):
    """Save session info"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO sessions (id, name, total_leads, success_count, fail_count, ai_provider, ai_model, duration_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (session_id, name, total_leads, success_count, fail_count, ai_provider, ai_model, duration))
    
    conn.commit()
    conn.close()

def get_all_sessions():
    """Get all processing sessions"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sessions ORDER BY created_at DESC LIMIT 50')
    rows = cursor.fetchall()
    conn.close()
    
    sessions = []
    for row in rows:
        sessions.append({
            'id': row[0],
            'name': row[1],
            'total_leads': row[2],
            'success_count': row[3],
            'fail_count': row[4],
            'ai_provider': row[5],
            'ai_model': row[6],
            'duration': row[7],
            'created_at': row[8]
        })
    return sessions

def get_session_leads(session_id):
    """Get leads from a specific session"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM leads_history WHERE session_id = ? ORDER BY id', (session_id,))
    rows = cursor.fetchall()
    conn.close()
    
    leads = []
    for row in rows:
        leads.append({
            'first_name': row[2],
            'last_name': row[3],
            'email': row[4],
            'company_name': row[5],
            'company_website': row[6],
            'title': row[7],
            'linkedin_url': row[8],
            'icebreaker': row[9],
            'sentiment': row[10],
            'industry': row[11],
            'status': row[12],
            'error': row[13]
        })
    return leads

def get_leads_stats():
    """Get overall statistics"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM leads_history')
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM leads_history WHERE status = 'success'")
    success = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(DISTINCT session_id) FROM leads_history')
    sessions = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total_leads': total,
        'success_leads': success,
        'total_sessions': sessions,
        'success_rate': (success / total * 100) if total > 0 else 0
    }

# Initialize database on import
init_database()

# ═══════════════════════════════════════════════════════════════
# PAGE CONFIG
# ═══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Narratives Media - Icebreaker Generator v7",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ═══════════════════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════════════════
if 'leads_data' not in st.session_state:
    st.session_state.leads_data = None
if 'filtered_leads' not in st.session_state:
    st.session_state.filtered_leads = None
if 'processed_results' not in st.session_state:
    st.session_state.processed_results = []
if 'stop_processing' not in st.session_state:
    st.session_state.stop_processing = False
# scrape_cache is now global thread-safe (see _scrape_cache)
if 'show_settings' not in st.session_state:
    st.session_state.show_settings = False
if 'processing_stats' not in st.session_state:
    st.session_state.processing_stats = {
        'total_processed': 0,
        'success_count': 0,
        'fail_count': 0,
        'avg_time': 0,
        'start_time': None
    }
if 'current_profile' not in st.session_state:
    st.session_state.current_profile = 'default'
if 'db_settings_loaded' not in st.session_state:
    st.session_state.db_settings_loaded = False

# Load settings from database on first run or profile change
if not st.session_state.db_settings_loaded:
    saved_settings = load_settings(st.session_state.current_profile)
    if saved_settings:
        st.session_state.dark_mode = saved_settings.get('dark_mode', True)
        st.session_state.saved_apify = saved_settings.get('apify_token', '')
        st.session_state.saved_gemini = saved_settings.get('gemini_key', '')
        st.session_state.saved_openai = saved_settings.get('openai_key', '')
        st.session_state.saved_claude = saved_settings.get('claude_key', '')
        st.session_state.saved_sheet_id = saved_settings.get('sheet_id', '')
        st.session_state.saved_provider = saved_settings.get('default_provider', 'Gemini (Google)')
        st.session_state.saved_model = saved_settings.get('default_model', 'Gemini 2.0 Flash (Recommended)')
        st.session_state.saved_workers = saved_settings.get('parallel_workers', 3)
        
        # Set widget keys directly for auto-population
        st.session_state.main_apify = saved_settings.get('apify_token', '')
        st.session_state.main_gemini = saved_settings.get('gemini_key', '')
        st.session_state.main_openai = saved_settings.get('openai_key', '')
        st.session_state.main_claude = saved_settings.get('claude_key', '')
        st.session_state.main_sheet = saved_settings.get('sheet_id', '')
        st.session_state.side_apify = saved_settings.get('apify_token', '')
        st.session_state.side_gemini = saved_settings.get('gemini_key', '')
        st.session_state.side_openai = saved_settings.get('openai_key', '')
        st.session_state.side_claude = saved_settings.get('claude_key', '')
        st.session_state.side_sheet = saved_settings.get('sheet_id', '')
    else:
        st.session_state.dark_mode = True
        st.session_state.saved_apify = ''
        st.session_state.saved_gemini = ''
        st.session_state.saved_openai = ''
        st.session_state.saved_claude = ''
        st.session_state.saved_sheet_id = ''
        st.session_state.saved_provider = 'Gemini (Google)'
        st.session_state.saved_model = 'Gemini 2.0 Flash (Recommended)'
        st.session_state.saved_workers = 3
        
        # Clear widget keys
        st.session_state.main_apify = ''
        st.session_state.main_gemini = ''
        st.session_state.main_openai = ''
        st.session_state.main_claude = ''
        st.session_state.main_sheet = ''
    st.session_state.db_settings_loaded = True

# ═══════════════════════════════════════════════════════════════
# 🌓 THEME SYSTEM - DARK/LIGHT MODE
# ═══════════════════════════════════════════════════════════════
def get_theme_css():
    if st.session_state.dark_mode:
        return """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
            
            .stApp {
                background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #16213e 100%);
                font-family: 'Inter', sans-serif;
            }
            
            .main-title {
                font-size: 3rem;
                font-weight: 700;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                text-align: center;
                margin-bottom: 0.5rem;
                animation: glow 2s ease-in-out infinite alternate;
            }
            
            @keyframes glow {
                from { filter: drop-shadow(0 0 5px rgba(102, 126, 234, 0.5)); }
                to { filter: drop-shadow(0 0 20px rgba(102, 126, 234, 0.8)); }
            }
            
            .sub-title {
                text-align: center;
                color: #a0a0a0;
                font-size: 1.1rem;
                margin-bottom: 2rem;
            }
            
            .glass-card {
                background: rgba(255, 255, 255, 0.05);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 0.1);
                padding: 1.5rem;
                margin: 1rem 0;
                box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
            }
            
            .glass-card-purple {
                background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
                border-radius: 20px;
                border: 1px solid rgba(102, 126, 234, 0.3);
                padding: 1.5rem;
                margin: 1rem 0;
            }
            
            .success-card {
                background: linear-gradient(135deg, rgba(40, 167, 69, 0.15) 0%, rgba(32, 201, 151, 0.15) 100%);
                border-radius: 15px;
                border: 1px solid rgba(40, 167, 69, 0.3);
                padding: 1rem;
                margin: 0.5rem 0;
            }
            
            .error-card {
                background: linear-gradient(135deg, rgba(220, 53, 69, 0.15) 0%, rgba(255, 107, 107, 0.15) 100%);
                border-radius: 15px;
                border: 1px solid rgba(220, 53, 69, 0.3);
                padding: 1rem;
                margin: 0.5rem 0;
            }
            
            .step-header {
                font-size: 1.5rem;
                font-weight: 600;
                color: #ffffff;
                margin-bottom: 1rem;
            }
            
            .step-number {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                width: 35px;
                height: 35px;
                border-radius: 50%;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-weight: 700;
            }
            
            .metric-card {
                background: rgba(255, 255, 255, 0.05);
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 0.1);
                padding: 1.5rem;
                text-align: center;
            }
            
            .metric-value {
                font-size: 2.5rem;
                font-weight: 700;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            
            .metric-label {
                color: #a0a0a0;
                font-size: 0.9rem;
            }
            
            .stButton > button {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
                color: white !important;
                border: none !important;
                border-radius: 12px !important;
                padding: 0.75rem 2rem !important;
                font-weight: 600 !important;
            }
            
            .model-badge {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 0.25rem 0.75rem;
                border-radius: 20px;
                font-size: 0.8rem;
            }
            
            .speed-badge {
                background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
                color: white;
                padding: 0.25rem 0.75rem;
                border-radius: 20px;
                font-size: 0.8rem;
            }
            
            /* Dashboard Stats */
            .stats-dashboard {
                background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
                border-radius: 20px;
                border: 1px solid rgba(102, 126, 234, 0.3);
                padding: 1.5rem;
                margin: 1rem 0;
            }
            
            .stat-item {
                text-align: center;
                padding: 1rem;
            }
            
            .stat-value {
                font-size: 2rem;
                font-weight: 700;
                color: #667eea;
            }
            
            .stat-label {
                color: #a0a0a0;
                font-size: 0.85rem;
                margin-top: 0.25rem;
            }
            
            /* Progress Animation */
            @keyframes pulse {
                0% { opacity: 1; }
                50% { opacity: 0.5; }
                100% { opacity: 1; }
            }
            
            .processing-indicator {
                animation: pulse 1.5s ease-in-out infinite;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 0.5rem 1rem;
                border-radius: 10px;
                display: inline-block;
            }
            
            .credit-footer {
                text-align: center;
                padding: 2rem;
                margin-top: 2rem;
            }
            
            .credit-footer .brand {
                font-size: 1.5rem;
                font-weight: 700;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            
            /* Fix sidebar collapse - always show toggle */
            [data-testid="collapsedControl"] {
                display: flex !important;
                visibility: visible !important;
            }
            
            section[data-testid="stSidebar"] > div {
                padding-top: 1rem;
            }
            
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
        </style>
        """
    else:
        # Light Mode
        return """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
            
            .stApp {
                background: linear-gradient(135deg, #f0f2f6 0%, #e8eaed 50%, #dfe3e8 100%);
                font-family: 'Inter', sans-serif;
                color: #1a1a2e !important;
            }
            
            /* Force dark text in light mode */
            .stApp p, .stApp span, .stApp label, .stApp div {
                color: #1a1a2e !important;
            }
            
            .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {
                color: #1a1a2e !important;
            }
            
            /* Input fields */
            .stTextInput > div > div > input {
                background: white !important;
                color: #1a1a2e !important;
                border: 2px solid #667eea !important;
            }
            
            .stSelectbox > div > div {
                background: white !important;
                color: #1a1a2e !important;
                border: 2px solid #667eea !important;
            }
            
            /* Expander */
            .streamlit-expanderHeader {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
                color: white !important;
                border-radius: 10px !important;
            }
            
            .streamlit-expanderContent {
                background: white !important;
                border: 2px solid #667eea !important;
                border-radius: 0 0 10px 10px !important;
            }
            
            .main-title {
                font-size: 3rem;
                font-weight: 700;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                text-align: center;
                margin-bottom: 0.5rem;
            }
            
            .sub-title {
                text-align: center;
                color: #444 !important;
                font-size: 1.1rem;
                margin-bottom: 2rem;
            }
            
            .glass-card {
                background: white;
                backdrop-filter: blur(10px);
                border-radius: 20px;
                border: 2px solid #667eea;
                padding: 1.5rem;
                margin: 1rem 0;
                box-shadow: 0 8px 32px 0 rgba(102, 126, 234, 0.2);
            }
            
            .glass-card-purple {
                background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
                border-radius: 20px;
                border: 2px solid rgba(102, 126, 234, 0.5);
                padding: 1.5rem;
                margin: 1rem 0;
            }
            
            .success-card {
                background: #d4edda;
                border-radius: 15px;
                border: 2px solid #28a745;
                padding: 1rem;
                margin: 0.5rem 0;
                color: #155724 !important;
            }
            
            .error-card {
                background: #f8d7da;
                border-radius: 15px;
                border: 2px solid #dc3545;
                padding: 1rem;
                margin: 0.5rem 0;
                color: #721c24 !important;
            }
            
            .step-header {
                font-size: 1.5rem;
                font-weight: 600;
                color: #1a1a2e !important;
                margin-bottom: 1rem;
            }
            
            .step-number {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white !important;
                width: 35px;
                height: 35px;
                border-radius: 50%;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-weight: 700;
            }
            
            .metric-card {
                background: white;
                border-radius: 15px;
                border: 2px solid #667eea;
                padding: 1.5rem;
                text-align: center;
            }
            
            .metric-value {
                font-size: 2.5rem;
                font-weight: 700;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            
            .metric-label {
                color: #444 !important;
                font-size: 0.9rem;
            }
            
            .stButton > button {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
                color: white !important;
                border: none !important;
                border-radius: 12px !important;
                padding: 0.75rem 2rem !important;
                font-weight: 600 !important;
            }
            
            .model-badge, .speed-badge {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white !important;
                padding: 0.25rem 0.75rem;
                border-radius: 20px;
                font-size: 0.8rem;
            }
            
            .stats-dashboard {
                background: white;
                border-radius: 20px;
                border: 2px solid #667eea;
                padding: 1.5rem;
                margin: 1rem 0;
                box-shadow: 0 4px 20px rgba(102, 126, 234, 0.15);
            }
            
            .stat-value {
                font-size: 2rem;
                font-weight: 700;
                color: #667eea !important;
            }
            
            .stat-label {
                color: #444 !important;
                font-size: 0.85rem;
            }
            
            /* Slider */
            .stSlider > div > div > div {
                background: #667eea !important;
            }
            
            /* File uploader */
            .stFileUploader > div {
                background: white !important;
                border: 2px dashed #667eea !important;
            }
            
            /* Metrics */
            [data-testid="stMetricValue"] {
                color: #667eea !important;
            }
            
            [data-testid="stMetricLabel"] {
                color: #444 !important;
            }
            
            /* Info boxes */
            .stAlert {
                background: #e8f4fd !important;
                color: #1a1a2e !important;
                border: 1px solid #667eea !important;
            }
            
            @keyframes pulse {
                0% { opacity: 1; }
                50% { opacity: 0.5; }
                100% { opacity: 1; }
            }
            
            .processing-indicator {
                animation: pulse 1.5s ease-in-out infinite;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white !important;
                padding: 0.5rem 1rem;
                border-radius: 10px;
            }
            
            .credit-footer {
                text-align: center;
                padding: 2rem;
                margin-top: 2rem;
                background: white;
                border-radius: 20px;
                border: 2px solid #667eea;
            }
            
            .credit-footer .brand {
                font-size: 1.5rem;
                font-weight: 700;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            
            .credit-footer div {
                color: #444 !important;
            }
            
            /* Sidebar styling for light mode */
            section[data-testid="stSidebar"] {
                background: white !important;
                border-right: 2px solid #667eea !important;
            }
            
            section[data-testid="stSidebar"] * {
                color: #1a1a2e !important;
            }
            
            /* Fix sidebar collapse - always show toggle */
            [data-testid="collapsedControl"] {
                display: flex !important;
                visibility: visible !important;
            }
            
            section[data-testid="stSidebar"] > div {
                padding-top: 1rem;
            }
            
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
        </style>
        """
# Apply theme
st.markdown(get_theme_css(), unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# 🤖 AI MODELS CONFIGURATION (Gemini, OpenAI, Claude)
# ═══════════════════════════════════════════════════════════════
AI_PROVIDERS = {
    "Gemini (Google)": {
        "models": {
            # 🔥 Gemini 3 Series (Newest - Dec 2025)
            "⭐ Gemini 3 Pro (Most Intelligent)": "gemini-3-pro-preview",
            "⚡ Gemini 3 Flash (Best Balance)": "gemini-3-flash-preview",
            # Gemini 2.5 Series (Stable)
            "Gemini 2.5 Pro (Advanced Thinking)": "gemini-2.5-pro",
            "Gemini 2.5 Flash (Price-Performance)": "gemini-2.5-flash",
            "Gemini 2.5 Flash-Lite (Ultra Fast)": "gemini-2.5-flash-lite",
            # Gemini 2.0 Series (Legacy Stable)
            "Gemini 2.0 Flash (Workhorse)": "gemini-2.0-flash",
            "Gemini 2.0 Flash-Lite (Budget)": "gemini-2.0-flash-lite"
        }
    },
    "OpenAI (GPT)": {
        "models": {
            "GPT-4o (Best Quality)": "gpt-4o",
            "GPT-4o Mini (Fast & Cheap)": "gpt-4o-mini",
            "GPT-4 Turbo": "gpt-4-turbo",
            "GPT-3.5 Turbo (Budget)": "gpt-3.5-turbo"
        }
    },
    "Claude (Anthropic)": {
        "models": {
            "Claude 3.5 Sonnet (Best)": "claude-3-5-sonnet-20241022",
            "Claude 3 Haiku (Fast)": "claude-3-haiku-20240307",
            "Claude 3 Opus (Premium)": "claude-3-opus-20240229"
        }
    }
}

# Legacy support
GEMINI_MODELS = AI_PROVIDERS["Gemini (Google)"]["models"]

# ═══════════════════════════════════════════════════════════════
# 😊 SENTIMENT ANALYSIS - Website Tone Detection
# ═══════════════════════════════════════════════════════════════
SENTIMENT_KEYWORDS = {
    "professional": ["enterprise", "solutions", "corporate", "professional", "business", "b2b", "consulting"],
    "innovative": ["ai", "machine learning", "cutting-edge", "revolutionary", "disruptive", "startup", "tech"],
    "friendly": ["community", "together", "family", "welcome", "friendly", "approachable", "casual"],
    "luxury": ["premium", "exclusive", "luxury", "elite", "high-end", "bespoke", "sophisticated"],
    "growth": ["scale", "growth", "accelerate", "momentum", "expand", "results", "roi"]
}

TONE_ADJUSTMENTS = {
    "professional": "Use formal, business-focused language. Reference industry standards and measurable outcomes.",
    "innovative": "Use forward-thinking language. Reference cutting-edge trends and disruption.",
    "friendly": "Use warm, conversational language. Reference community and shared values.",
    "luxury": "Use sophisticated, exclusive language. Reference premium positioning and prestige.",
    "growth": "Use results-oriented language. Reference metrics, scaling, and ROI."
}

def analyze_sentiment(content):
    """Analyze website content to detect tone/sentiment"""
    content_lower = content.lower()
    scores = {}
    
    for sentiment, keywords in SENTIMENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in content_lower)
        scores[sentiment] = score
    
    # Get dominant sentiment
    if max(scores.values()) == 0:
        return "professional", "neutral"  # default
    
    dominant = max(scores, key=scores.get)
    confidence = "high" if scores[dominant] >= 3 else "medium" if scores[dominant] >= 2 else "low"
    
    return dominant, confidence

# ═══════════════════════════════════════════════════════════════
# 🎯 INDUSTRY-SPECIFIC TEMPLATES
# ═══════════════════════════════════════════════════════════════
INDUSTRY_TEMPLATES = {
    "saas": {
        "keywords": ["software", "saas", "platform", "dashboard", "subscription", "cloud"],
        "angle": "Focus on how video content can reduce churn and improve user onboarding."
    },
    "agency": {
        "keywords": ["agency", "marketing", "creative", "clients", "campaigns", "branding"],
        "angle": "Position video as a way to showcase case studies and differentiate from competitors."
    },
    "consulting": {
        "keywords": ["consulting", "advisory", "strategy", "transformation", "implementation"],
        "angle": "Emphasize thought leadership video content to establish market authority."
    },
    "ecommerce": {
        "keywords": ["shop", "store", "products", "buy", "cart", "shipping", "ecommerce"],
        "angle": "Highlight product videos and founder story content for brand trust."
    },
    "fintech": {
        "keywords": ["fintech", "finance", "banking", "payments", "investment", "crypto"],
        "angle": "Focus on trust-building content and regulatory expertise positioning."
    },
    "healthcare": {
        "keywords": ["health", "medical", "patient", "care", "clinic", "wellness"],
        "angle": "Emphasize educational content and practitioner credibility videos."
    },
    "education": {
        "keywords": ["learning", "course", "training", "education", "students", "academy"],
        "angle": "Position founder as educator with authority-building video series."
    }
}

def detect_industry(content):
    """Detect industry from website content"""
    content_lower = content.lower()
    
    for industry, data in INDUSTRY_TEMPLATES.items():
        matches = sum(1 for kw in data["keywords"] if kw in content_lower)
        if matches >= 2:
            return industry, data["angle"]
    
    return "general", "Focus on founder-led storytelling and market positioning through video."

# ═══════════════════════════════════════════════════════════════
# 🎯 ENHANCED PROMPTS SYSTEM
# ═══════════════════════════════════════════════════════════════
def get_enhanced_research_prompt():
    return """You are a Lead Intelligence Analyst for 'Narratives Media', a premium video branding partner.

ANALYZE this website deeply and return a JSON with:

{
    "company_overview": "(What they do in 1 sentence)",
    "target_audience": "(Who they serve)",
    "unique_value_prop": "(What makes them different)",
    "content_presence": {
        "has_blog": true/false,
        "has_video": true/false,
        "has_podcast": true/false,
        "youtube_channel": true/false
    },
    "authority_signals": "(Awards, press, client logos, testimonials)",
    "content_topics": ["topic1", "topic2", "topic3"],
    "founder_visibility": "(Is founder prominent on site?)",
    "pain_points": "(Potential content gaps we can help with)",
    "tone": "(professional/innovative/friendly/luxury/growth)"
}

Be specific and insightful. This will be used to craft a personalized outreach.

WEBSITE CONTENT:
"""

def get_enhanced_icebreaker_prompt(sentiment, industry_angle, content_signals):
    base_prompt = f"""You are the Founder of Narratives Media - we help ambitious founders build market authority through premium video content and podcasts.

CONTEXT:
- Website Sentiment/Tone: {sentiment}
- Industry Insight: {industry_angle}
- Content Signals: {content_signals}

YOUR TASK: Write a hyper-personalized 2-sentence icebreaker (max 45 words).

ADVANCED RULES:
1. NEVER use names (no "Hey John" or "Hi Sarah")
2. NEVER ask questions - make confident statements ending with periods
3. Reference SPECIFIC details from their website (topics, products, achievements)
4. Match their website's tone ({sentiment})
5. Position yourself as a Strategic Partner, not a vendor
6. Create curiosity without being salesy

PERSONALIZATION ANGLES (choose based on signals):

📝 **Authority Gap** (Has blog, no video):
"Your written content on [SPECIFIC TOPIC] demonstrates deep expertise. Translating that authority into founder-led video would position you to own the conversation in your space."

📹 **Video Upgrade** (Has video, can improve):
"The video content around [TOPIC] shows you understand the medium's power. A consistent founder-led narrative could amplify that into true market leadership."

🚀 **Founder Visibility** (No founder content):
"Your [SPECIFIC ACHIEVEMENT/APPROACH] stands out in the market. The missing piece is putting a face and voice to that expertise through strategic video presence."

💡 **Thought Leadership** (Strong blog, industry expert):
"Your perspective on [SPECIFIC TOPIC] cuts through the noise. A video series expanding on those insights would cement your position as the go-to authority."

🎯 **Growth Signal** (Scaling company):
"The momentum you're building with [PRODUCT/SERVICE] is impressive. Founder-driven content is typically what separates companies that scale from those that plateau."

OUTPUT: Just the 2-sentence icebreaker, nothing else. Be specific, confident, and value-driven."""

    return base_prompt

# Legacy prompts for backward compatibility
GEMINI_RESEARCH_PROMPT = get_enhanced_research_prompt()

GEMINI_ICEBREAKER_SYSTEM = """You are the Founder of Narratives Media - premium branding through Video & Podcasts.

Write a 2-sentence icebreaker (max 45 words):
- NO names (never "Hey John")
- NO questions (end with period)
- Executive tone
- Be specific about their business

Choose angle based on their content:
1. Authority Gap (blog but no video) - compliment writing, suggest video
2. Visionary Compliment (has video) - praise their video strategy
3. Founder-Led Growth (general) - focus on their methodology"""

# ═══════════════════════════════════════════════════════════════
# 💾 CACHING SYSTEM (Thread-Safe)
# ═══════════════════════════════════════════════════════════════
# Global thread-safe cache (not session_state for thread safety)
_scrape_cache = {}
_cache_lock = threading.Lock()

def get_cache_key(url):
    url = str(url).lower().strip().rstrip('/')
    url = re.sub(r'^https?://(www\.)?', '', url)
    return hashlib.md5(url.encode()).hexdigest()

def get_cached_scrape(url):
    key = get_cache_key(url)
    with _cache_lock:
        return _scrape_cache.get(key)

def set_cached_scrape(url, data):
    key = get_cache_key(url)
    with _cache_lock:
        _scrape_cache[key] = data

def get_cache_size():
    with _cache_lock:
        return len(_scrape_cache)

def clear_cache():
    global _scrape_cache
    with _cache_lock:
        _scrape_cache = {}

# ═══════════════════════════════════════════════════════════════
# ⏱️ RATE LIMITER
# ═══════════════════════════════════════════════════════════════
class RateLimiter:
    def __init__(self, calls_per_minute=60):
        self.calls_per_minute = calls_per_minute
        self.calls = []
        self.lock = threading.Lock()
    
    def wait_if_needed(self):
        with self.lock:
            now = time.time()
            self.calls = [c for c in self.calls if now - c < 60]
            if len(self.calls) >= self.calls_per_minute:
                sleep_time = 60 - (now - self.calls[0]) + 0.1
                if sleep_time > 0:
                    time.sleep(sleep_time)
            self.calls.append(time.time())

# Rate limits - with staggered delays, we can use higher limits
gemini_limiter = RateLimiter(calls_per_minute=60)  # Back to normal since we have delays
scrape_limiter = RateLimiter(calls_per_minute=120)  # Faster scraping

# ═══════════════════════════════════════════════════════════════
# 🤖 MULTI-PROVIDER AI CALLING FUNCTIONS
# ═══════════════════════════════════════════════════════════════
def call_openai(api_key, model_id, prompt, system_instruction=None, max_retries=3):
    """Call OpenAI API (GPT models)"""
    url = "https://api.openai.com/v1/chat/completions"
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                time.sleep(2 ** attempt)
            
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": model_id,
                "messages": messages,
                "temperature": 0.4,
                "max_tokens": 300
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            
            response.raise_for_status()
            result = response.json()
            
            if 'choices' in result and len(result['choices']) > 0:
                return result['choices'][0]['message']['content'].strip(), None
            return None, "No response"
            
        except Exception as e:
            if attempt == max_retries - 1:
                return None, str(e)
    
    return None, "Max retries"


def call_claude(api_key, model_id, prompt, system_instruction=None, max_retries=3):
    """Call Anthropic Claude API"""
    url = "https://api.anthropic.com/v1/messages"
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                time.sleep(2 ** attempt)
            
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": model_id,
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}]
            }
            
            if system_instruction:
                payload["system"] = system_instruction
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            
            response.raise_for_status()
            result = response.json()
            
            if 'content' in result and len(result['content']) > 0:
                return result['content'][0]['text'].strip(), None
            return None, "No response"
            
        except Exception as e:
            if attempt == max_retries - 1:
                return None, str(e)
    
    return None, "Max retries"


def call_gemini(api_key, model_id, prompt, system_instruction=None, max_retries=3):
    """Call Google Gemini API"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
    
    gemini_limiter.wait_if_needed()
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                time.sleep(2 ** attempt)
            
            payload = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.4, "maxOutputTokens": 2048}
            }
            
            if system_instruction:
                payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
            
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            
            if response.status_code == 503:
                time.sleep(3)
                continue
            
            response.raise_for_status()
            result = response.json()
            
            # Better error handling for different response formats
            if 'candidates' in result and len(result['candidates']) > 0:
                candidate = result['candidates'][0]
                
                # Check for MAX_TOKENS finish reason - this means rate limit or token issue
                finish_reason = candidate.get('finishReason', '')
                if finish_reason == 'MAX_TOKENS':
                    # Wait and retry
                    if attempt < max_retries - 1:
                        time.sleep(3 * (attempt + 1))
                        continue
                
                # Check for content->parts structure
                if 'content' in candidate and 'parts' in candidate['content']:
                    text = candidate['content']['parts'][0]['text'].strip()
                    return text, None
                # Some models may have different structure
                elif 'text' in candidate:
                    return candidate['text'].strip(), None
                # Check for blocked content
                elif 'finishReason' in candidate:
                    if finish_reason in ['SAFETY', 'RECITATION', 'OTHER']:
                        return None, f"Blocked: {finish_reason}"
                    # For other finish reasons, try to get partial content
                    if 'content' in candidate and 'parts' in candidate.get('content', {}):
                        text = candidate['content']['parts'][0].get('text', '').strip()
                        if text:
                            return text, None
                    return None, f"Blocked: {finish_reason}"
                else:
                    return None, f"Unexpected response format: {list(candidate.keys())}"
            
            # Check for prompt feedback (safety blocks)
            if 'promptFeedback' in result:
                feedback = result['promptFeedback']
                if 'blockReason' in feedback:
                    return None, f"Blocked: {feedback['blockReason']}"
            
            return None, f"No candidates in response: {list(result.keys())}"
            
        except requests.exceptions.HTTPError as e:
            error_msg = str(e)
            try:
                error_detail = response.json()
                if 'error' in error_detail:
                    error_msg = error_detail['error'].get('message', str(e))
            except:
                pass
            if attempt == max_retries - 1:
                return None, error_msg
                
        except Exception as e:
            if attempt == max_retries - 1:
                return None, str(e)
    
    return None, "Max retries"


def call_ai(provider, api_key, model_id, prompt, system_instruction=None):
    """Universal AI caller - routes to appropriate provider"""
    if provider == "Gemini (Google)":
        return call_gemini(api_key, model_id, prompt, system_instruction)
    elif provider == "OpenAI (GPT)":
        return call_openai(api_key, model_id, prompt, system_instruction)
    elif provider == "Claude (Anthropic)":
        return call_claude(api_key, model_id, prompt, system_instruction)
    else:
        return None, f"Unknown provider: {provider}"

# ═══════════════════════════════════════════════════════════════
# CORE FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def fetch_apify_data(api_token, dataset_id):
    try:
        url = f"https://api.apify.com/v2/datasets/{dataset_id}/items"
        headers = {"Authorization": f"Bearer {api_token}"}
        response = requests.get(url, headers=headers, params={"format": "json"}, timeout=60)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.Timeout:
        return None, "Request timed out"
    except requests.exceptions.HTTPError as e:
        return None, f"HTTP Error: {e.response.status_code}"
    except Exception as e:
        return None, str(e)


def run_apify_task(api_token, task_id):
    try:
        run_url = f"https://api.apify.com/v2/actor-tasks/{task_id}/runs"
        headers = {"Authorization": f"Bearer {api_token}"}
        
        response = requests.post(run_url, headers=headers, timeout=30)
        response.raise_for_status()
        run_data = response.json()
        run_id = run_data['data']['id']
        
        status_url = f"https://api.apify.com/v2/actor-runs/{run_id}"
        max_wait = 600
        waited = 0
        
        while waited < max_wait:
            status_response = requests.get(status_url, headers=headers)
            status = status_response.json()['data']['status']
            
            if status == 'SUCCEEDED':
                dataset_id = run_data['data']['defaultDatasetId']
                return fetch_apify_data(api_token, dataset_id)
            elif status in ['FAILED', 'ABORTED', 'TIMED-OUT']:
                return None, f"Task failed: {status}"
            
            time.sleep(10)
            waited += 10
        
        return None, "Task timed out"
    except Exception as e:
        return None, str(e)


def filter_leads(leads):
    filtered = []
    removed = []
    
    for lead in leads:
        email = lead.get('email', '')
        website = lead.get('company_website', '') or lead.get('website_url', '')
        
        email_valid = bool(email and re.match(r'^[^@]+@[^@]+\.[^@]+$', str(email)))
        website_valid = bool(website and str(website).lower() not in ['', 'nan', 'none', 'n/a'])
        
        if email_valid and website_valid:
            filtered.append(lead)
        else:
            removed.append(lead)
    
    return filtered, removed


# Free US Proxy list (rotates through these)
US_PROXIES = [
    None,  # First try without proxy (fastest)
]

def get_random_us_proxy():
    """Get a random US proxy or None for direct connection"""
    import random
    return None  # Direct connection for speed


def analyze_social_media_presence(soup, website_url):
    """Extract social media links and analyze content presence"""
    social_data = {
        'youtube_url': None,
        'youtube_status': 'Not found',
        'linkedin_url': None,
        'linkedin_status': 'Not found',
        'facebook_url': None,
        'instagram_url': None,
        'twitter_url': None,
        'has_video_content': False,
        'has_blog': False,
        'has_podcast': False,
        'content_quality': 'unknown',
        'content_gaps': [],
        'social_count': 0
    }
    
    # Find all links
    for link in soup.find_all('a', href=True):
        href = link['href'].lower()
        
        # YouTube
        if 'youtube.com' in href or 'youtu.be' in href:
            social_data['youtube_url'] = link['href']
            social_data['youtube_status'] = 'Found'
            social_data['has_video_content'] = True
            social_data['social_count'] += 1
        
        # LinkedIn
        elif 'linkedin.com' in href:
            social_data['linkedin_url'] = link['href']
            social_data['linkedin_status'] = 'Found'
            social_data['social_count'] += 1
        
        # Facebook
        elif 'facebook.com' in href or 'fb.com' in href:
            social_data['facebook_url'] = link['href']
            social_data['social_count'] += 1
        
        # Instagram
        elif 'instagram.com' in href:
            social_data['instagram_url'] = link['href']
            social_data['social_count'] += 1
        
        # Twitter/X
        elif 'twitter.com' in href or 'x.com' in href:
            social_data['twitter_url'] = link['href']
            social_data['social_count'] += 1
        
        # Blog detection
        if any(x in href for x in ['/blog', '/news', '/articles', '/insights', '/resources']):
            social_data['has_blog'] = True
        
        # Podcast detection
        if any(x in href for x in ['spotify.com', 'podcasts.apple', 'anchor.fm', '/podcast']):
            social_data['has_podcast'] = True
    
    # Check for embedded videos
    for iframe in soup.find_all('iframe'):
        src = iframe.get('src', '').lower()
        if 'youtube' in src or 'vimeo' in src or 'wistia' in src:
            social_data['has_video_content'] = True
            if not social_data['youtube_url'] and 'youtube' in src:
                social_data['youtube_url'] = src
                social_data['youtube_status'] = 'Embedded'
    
    # Check for video tags
    if soup.find_all('video'):
        social_data['has_video_content'] = True
    
    # Analyze content gaps (opportunities for your service!)
    if not social_data['has_video_content']:
        social_data['content_gaps'].append('NO VIDEO CONTENT - Great opportunity!')
    if not social_data['has_blog']:
        social_data['content_gaps'].append('No blog - content marketing opportunity')
    if social_data['social_count'] < 3:
        social_data['content_gaps'].append('Limited social presence')
    if not social_data['youtube_url']:
        social_data['content_gaps'].append('No YouTube - video marketing opportunity!')
    
    # Content quality assessment
    if social_data['has_video_content'] and social_data['has_blog'] and social_data['social_count'] >= 3:
        social_data['content_quality'] = 'Strong'
    elif social_data['has_video_content'] or social_data['has_blog']:
        social_data['content_quality'] = 'Moderate'
    else:
        social_data['content_quality'] = 'Weak - HIGH OPPORTUNITY!'
    
    return social_data


def check_youtube_channel(youtube_url):
    """Quick check of YouTube channel/video"""
    if not youtube_url:
        return {'status': 'No YouTube', 'opportunity': 'HIGH - No video presence!'}
    
    try:
        # Extract channel/video info from URL
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1)'}
        response = requests.get(youtube_url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            # Check for subscriber count, video count hints
            text = response.text.lower()
            if 'subscriber' in text:
                return {'status': 'Active channel', 'opportunity': 'Medium - Has YouTube'}
            else:
                return {'status': 'Has videos', 'opportunity': 'Medium - Could improve'}
        else:
            return {'status': 'Link broken', 'opportunity': 'HIGH - Broken YouTube!'}
    except:
        return {'status': 'Could not check', 'opportunity': 'Unknown'}
    # 70% chance of no proxy (faster), 30% chance of proxy
    if random.random() < 0.7:
        return None
    return random.choice([p for p in US_PROXIES if p is not None]) if len(US_PROXIES) > 1 else None


def scrape_website_with_retry(url, max_retries=2):
    """Fast scraping with optional US proxy support"""
    cached = get_cached_scrape(url)
    if cached:
        return cached
    
    result = {
        'success': False,
        'home_content': '',
        'social_links': [],
        'has_youtube': False,
        'has_blog': False,
        'has_podcast': False,
        'topics': [],
        'error': None
    }
    
    if not url or str(url).lower() in ['nan', 'none', '']:
        result['error'] = "No URL"
        return result
    
    url = str(url).strip()
    if not url.startswith('http'):
        url = 'https://' + url
    url = url.rstrip('/')
    
    # Optimized headers - only 2 variants for speed
    headers_list = [
        {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        },
        {
            'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
            'Accept': '*/*',
        },
    ]
    
    scrape_limiter.wait_if_needed()
    
    # Fast retry loop - max 2 attempts
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                time.sleep(0.5)  # Minimal delay between retries
            
            headers = headers_list[attempt % len(headers_list)]
            
            # Try with shorter timeout for speed
            response = requests.get(
                url, 
                headers=headers, 
                timeout=8,  # Reduced from 20 to 8 seconds
                allow_redirects=True,
                verify=True
            )
            
            # Handle different status codes - fail fast
            if response.status_code == 403:
                continue  # Try next attempt
            if response.status_code == 404:
                result['error'] = "Not found"
                set_cached_scrape(url, result)  # Cache the failure
                return result
            if response.status_code >= 500:
                continue
            
            # Quick Cloudflare check
            if 'cloudflare' in response.text[:1000].lower():
                if attempt < max_retries - 1:
                    continue
                result['error'] = "Blocked"
                set_cached_scrape(url, result)
                return result
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove unwanted elements (but keep links for social analysis)
            soup_for_social = BeautifulSoup(response.text, 'html.parser')  # Fresh copy for social
            for tag in soup(['script', 'style', 'noscript']):
                tag.decompose()
            
            title = soup.find('title')
            title_text = title.text.strip() if title else ""
            
            # Try multiple meta description sources
            meta_text = ""
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                meta_text = meta_desc['content']
            if not meta_text:
                og_desc = soup.find('meta', attrs={'property': 'og:description'})
                if og_desc and og_desc.get('content'):
                    meta_text = og_desc['content']
            
            # 🔥 NEW: Analyze social media and content presence
            social_data = analyze_social_media_presence(soup_for_social, url)
            
            # Store social data in result
            result['has_youtube'] = social_data['has_video_content']
            result['has_blog'] = social_data['has_blog']
            result['has_podcast'] = social_data['has_podcast']
            result['youtube_url'] = social_data['youtube_url']
            result['linkedin_url'] = social_data['linkedin_url']
            result['social_count'] = social_data['social_count']
            result['content_quality'] = social_data['content_quality']
            result['content_gaps'] = social_data['content_gaps']
            result['social_links'] = {
                'youtube': social_data['youtube_url'],
                'linkedin': social_data['linkedin_url'],
                'facebook': social_data['facebook_url'],
                'instagram': social_data['instagram_url'],
                'twitter': social_data['twitter_url']
            }
            
            # Get headings as topics
            headings = []
            for h in soup.find_all(['h1', 'h2', 'h3']):
                text = h.get_text(strip=True)
                if 5 < len(text) < 150:
                    headings.append(text)
            result['topics'] = headings[:10]
            
            # Get main content - try multiple methods
            main_content = ""
            
            # Method 1: Try main/article tags first (faster)
            main_tag = soup.find('main') or soup.find('article')
            if main_tag:
                main_content = main_tag.get_text(separator=' ', strip=True)
            
            # Method 2: Fallback to body
            if len(main_content) < 100:
                main_content = soup.get_text(separator=' ', strip=True)
            
            # Clean up content - limit to 5000 chars for speed
            main_content = re.sub(r'\s+', ' ', main_content)[:5000]
            
            # If we got very little content
            if len(main_content) < 30:
                result['error'] = "No content"
                if len(title_text) > 3 or len(meta_text) > 5:
                    result['home_content'] = f"Title: {title_text}\nDesc: {meta_text}"
                    result['success'] = True
                set_cached_scrape(url, result)
                return result
            
            result['home_content'] = f"Title: {title_text}\nDesc: {meta_text}\nTopics: {', '.join(headings[:3])}\nContent: {main_content}"
            result['success'] = True
            
            set_cached_scrape(url, result)
            return result
            
        except requests.exceptions.Timeout:
            result['error'] = "Timeout"
        except requests.exceptions.SSLError:
            result['error'] = "SSL"
        except requests.exceptions.ConnectionError:
            result['error'] = "No connection"
        except Exception as e:
            result['error'] = str(e)[:30]
    
    # Cache failures too to avoid re-trying
    set_cached_scrape(url, result)
    return result


def call_gemini_with_retry(api_key, model_id, prompt, system_instruction=None, max_retries=3):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
    
    gemini_limiter.wait_if_needed()
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                time.sleep(2 ** attempt)
            
            payload = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.4, "maxOutputTokens": 2048}
            }
            
            if system_instruction:
                payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
            
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            
            if response.status_code == 503:
                time.sleep(3)
                continue
            
            response.raise_for_status()
            result = response.json()
            
            # Better error handling for different response formats
            if 'candidates' in result and len(result['candidates']) > 0:
                candidate = result['candidates'][0]
                # Check for content->parts structure
                if 'content' in candidate and 'parts' in candidate['content']:
                    text = candidate['content']['parts'][0]['text'].strip()
                    return text, None
                # Some models may have different structure
                elif 'text' in candidate:
                    return candidate['text'].strip(), None
                # Check for blocked content
                elif 'finishReason' in candidate:
                    return None, f"Blocked: {candidate.get('finishReason', 'unknown')}"
                else:
                    return None, f"Unexpected format: {list(candidate.keys())}"
            
            # Check for prompt feedback (safety blocks)
            if 'promptFeedback' in result:
                feedback = result['promptFeedback']
                if 'blockReason' in feedback:
                    return None, f"Blocked: {feedback['blockReason']}"
            
            return None, f"No candidates: {list(result.keys())}"
                
        except requests.exceptions.HTTPError as e:
            error_msg = str(e)
            try:
                error_detail = response.json()
                if 'error' in error_detail:
                    error_msg = error_detail['error'].get('message', str(e))
            except:
                pass
            if attempt == max_retries - 1:
                return None, error_msg
                
        except Exception as e:
            if attempt == max_retries - 1:
                return None, str(e)
    
    return None, "Max retries"


def is_valid_icebreaker(icebreaker):
    if not icebreaker or len(icebreaker) < 20:
        return False
    
    bad_phrases = [
        "unable to", "cannot access", "cloudflare", "blocked",
        "need more", "insufficient", "error", "hey ", "hi ", "dear "
    ]
    
    icebreaker_lower = icebreaker.lower()
    for phrase in bad_phrases:
        if phrase in icebreaker_lower:
            return False
    
    if '?' in icebreaker:
        return False
    
    return True


def clean_icebreaker(icebreaker):
    if not icebreaker:
        return ""
    
    icebreaker = icebreaker.strip('"\'')
    icebreaker = re.sub(r'^(Hi|Hello|Hey|Dear)\s+\w+[,!]?\s*', '', icebreaker, flags=re.I)
    icebreaker = re.sub(r'\s+', ' ', icebreaker).strip()
    icebreaker = icebreaker.rstrip('?')
    
    if icebreaker and not icebreaker.endswith('.'):
        icebreaker = icebreaker.rstrip('!,') + '.'
    
    return icebreaker


def process_single_lead(lead, ai_key, model_id, ai_provider="Gemini (Google)"):
    """Process a single lead with sentiment analysis and enhanced prompts"""
    result = lead.copy()
    result['status'] = 'processing'
    result['icebreaker'] = ''
    result['error'] = ''
    result['sentiment'] = ''
    result['industry'] = ''
    
    try:
        website = lead.get('company_website', '')
        company_name = lead.get('company_name', '')
        
        scraped = scrape_website_with_retry(website)
        
        if not scraped['success']:
            if company_name:
                fallback = f"Company: {company_name}\nWebsite: {website}\n\nWrite a Founder-Led Growth icebreaker."
                icebreaker, _ = call_ai(ai_provider, ai_key, model_id, fallback, GEMINI_ICEBREAKER_SYSTEM)
                if icebreaker:
                    icebreaker = clean_icebreaker(icebreaker)
                    if is_valid_icebreaker(icebreaker):
                        result['icebreaker'] = icebreaker
                        result['status'] = 'success'
                        return result
            
            result['status'] = 'failed'
            result['error'] = f"Scrape: {scraped.get('error', 'Unknown')}"
            return result
        
        # 🔥 NEW: Sentiment Analysis
        content_for_analysis = scraped['home_content'][:5000]
        sentiment, confidence = analyze_sentiment(content_for_analysis)
        result['sentiment'] = f"{sentiment} ({confidence})"
        
        # 🔥 NEW: Industry Detection
        industry, industry_angle = detect_industry(content_for_analysis)
        result['industry'] = industry
        
        # Enhanced research with new prompt
        research, _ = call_ai(ai_provider, ai_key, model_id, 
            get_enhanced_research_prompt() + scraped['home_content'][:8000])
        
        if not research:
            research = f"Company: {company_name}"
        
        # Build content signals
        signals = []
        content_signals = {}
        if scraped['has_blog']:
            signals.append("HAS BLOG")
            content_signals['has_blog'] = True
        else:
            content_signals['has_blog'] = False
            
        if scraped['has_youtube']:
            signals.append("HAS YOUTUBE")
            content_signals['has_video'] = True
        else:
            content_signals['has_video'] = False
            
        if not signals:
            signals.append("NO CLEAR CONTENT")
        
        content_signals['topics'] = scraped.get('topics', [])[:3]
        
        # 🔥 NEW: Get enhanced icebreaker prompt with sentiment
        tone_adjustment = TONE_ADJUSTMENTS.get(sentiment, "")
        enhanced_prompt = get_enhanced_icebreaker_prompt(
            sentiment=sentiment,
            industry_angle=industry_angle,
            content_signals=str(content_signals)
        )
        
        prospect_data = f"""COMPANY: {company_name}
SIGNALS: {', '.join(signals)}
HAS YOUTUBE: {'Yes' if scraped['has_youtube'] else 'No'}
HAS BLOG: {'Yes' if scraped['has_blog'] else 'No'}
DETECTED TONE: {sentiment}
INDUSTRY: {industry}
TONE ADJUSTMENT: {tone_adjustment}
TOPICS: {', '.join(scraped.get('topics', [])[:5])}
SUMMARY: {scraped['home_content'][:2000]}
RESEARCH: {research}

Write the icebreaker:"""
        
        icebreaker, err = call_ai(ai_provider, ai_key, model_id, prospect_data, enhanced_prompt)
        
        if err:
            result['status'] = 'failed'
            result['error'] = f"{ai_provider}: {err}"
            return result
        
        icebreaker = clean_icebreaker(icebreaker)
        
        if not is_valid_icebreaker(icebreaker):
            result['status'] = 'failed'
            result['error'] = 'Invalid output'
            return result
        
        result['icebreaker'] = icebreaker
        result['status'] = 'success'
        
    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)[:50]
    
    return result


def process_single_lead_with_delay(args):
    """Wrapper to add small delay only before AI calls to stagger requests"""
    lead, ai_key, model_id, ai_provider, delay_seconds = args
    
    # Start scraping immediately (no delay for scraping)
    result = lead.copy()
    result['status'] = 'pending'
    result['error'] = None
    
    try:
        company_name = result.get('company_name', '') or result.get('company', '')
        website = result.get('website', '') or result.get('company_website', '')
        first_name = result.get('first_name', '')
        last_name = result.get('last_name', '')
        job_title = result.get('job_title', '') or result.get('title', '')
        
        if not website or str(website).lower() in ['nan', 'none', '']:
            result['status'] = 'failed'
            result['error'] = 'No website'
            return result
        
        # Scrape immediately - no delay
        scraped = scrape_website_with_retry(website)
        
        # FALLBACK MODE: If scrape fails, try to generate icebreaker with available info
        if not scraped['success']:
            # Check if we have enough info to generate without website content
            if company_name and (first_name or job_title):
                # Try to generate a generic but personalized icebreaker
                if delay_seconds > 0:
                    time.sleep(delay_seconds)
                
                fallback_prompt = f"""Generate a brief, professional icebreaker for cold outreach.

PERSON: {first_name} {last_name}
TITLE: {job_title}
COMPANY: {company_name}
WEBSITE: {website} (could not access)

Write a 1-2 sentence icebreaker that:
- References their company name naturally
- Is professional but friendly
- Does NOT mention that you couldn't access their website
- Focuses on general business value

Just write the icebreaker, nothing else:"""
                
                icebreaker, err = call_ai(ai_provider, ai_key, model_id, fallback_prompt)
                
                if icebreaker and not err:
                    icebreaker = clean_icebreaker(icebreaker)
                    if is_valid_icebreaker(icebreaker):
                        result['icebreaker'] = icebreaker
                        result['status'] = 'success'
                        result['sentiment'] = 'fallback'
                        result['industry'] = 'unknown'
                        return result
            
            # If fallback also fails
            result['status'] = 'failed'
            result['error'] = f"Scrape: {scraped.get('error', 'Failed')}"
            return result
        
        # Normal flow with scraped content
        content_for_analysis = scraped['home_content'][:5000]
        sentiment, confidence = analyze_sentiment(content_for_analysis)
        result['sentiment'] = f"{sentiment} ({confidence})"
        
        industry, industry_angle = detect_industry(content_for_analysis)
        result['industry'] = industry
        
        # NOW apply delay before AI calls (stagger the API requests)
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        
        # Research AI call
        research, _ = call_ai(ai_provider, ai_key, model_id, 
            get_enhanced_research_prompt() + scraped['home_content'][:8000])
        
        if not research:
            research = f"Company: {company_name}"
        
        # Build content signals
        signals = []
        content_signals = {}
        if scraped['has_blog']:
            signals.append("HAS BLOG")
            content_signals['has_blog'] = True
        else:
            content_signals['has_blog'] = False
            
        if scraped['has_youtube']:
            signals.append("HAS YOUTUBE")
            content_signals['has_video'] = True
        else:
            content_signals['has_video'] = False
            
        if not signals:
            signals.append("NO CLEAR CONTENT")
        
        content_signals['topics'] = scraped.get('topics', [])[:3]
        
        # 🔥 NEW: Get content gaps and opportunity info
        content_gaps = scraped.get('content_gaps', [])
        content_quality = scraped.get('content_quality', 'unknown')
        youtube_url = scraped.get('youtube_url', '')
        linkedin_url = scraped.get('linkedin_url', '')
        social_count = scraped.get('social_count', 0)
        
        # Store extra data in result for export
        result['content_quality'] = content_quality
        result['content_gaps'] = ', '.join(content_gaps) if content_gaps else 'None detected'
        result['youtube_url'] = youtube_url or ''
        result['linkedin_url'] = linkedin_url or ''
        result['social_count'] = social_count
        
        tone_adjustment = TONE_ADJUSTMENTS.get(sentiment, "")
        enhanced_prompt = get_enhanced_icebreaker_prompt(
            sentiment=sentiment,
            industry_angle=industry_angle,
            content_signals=str(content_signals)
        )
        
        # 🔥 ENHANCED prospect data with content opportunities
        prospect_data = f"""COMPANY: {company_name}
PERSON: {first_name} {last_name} - {job_title}

=== CONTENT STATUS ===
HAS VIDEO CONTENT: {'Yes' if scraped['has_youtube'] else 'NO - Great video opportunity!'}
HAS BLOG: {'Yes' if scraped['has_blog'] else 'No'}
HAS PODCAST: {'Yes' if scraped['has_podcast'] else 'No'}
YOUTUBE: {youtube_url if youtube_url else 'NOT FOUND - They need video!'}
LINKEDIN: {linkedin_url if linkedin_url else 'Not found'}
SOCIAL MEDIA PRESENCE: {social_count} platforms
CONTENT QUALITY: {content_quality}
CONTENT GAPS: {', '.join(content_gaps) if content_gaps else 'Good coverage'}

=== COMPANY INFO ===
INDUSTRY: {industry}
DETECTED TONE: {sentiment}
TOPICS: {', '.join(scraped.get('topics', [])[:5])}
SUMMARY: {scraped['home_content'][:1500]}
RESEARCH: {research}

=== YOUR TASK ===
Write a personalized icebreaker that:
1. References their company/content naturally
2. If they lack video content, subtly hint at video marketing benefits
3. Shows you understand their industry
4. Is conversational, not salesy

Write the icebreaker:"""
        
        icebreaker, err = call_ai(ai_provider, ai_key, model_id, prospect_data, enhanced_prompt)
        
        if err:
            result['status'] = 'failed'
            result['error'] = f"{ai_provider}: {err}"
            return result
        
        icebreaker = clean_icebreaker(icebreaker)
        
        if not is_valid_icebreaker(icebreaker):
            result['status'] = 'failed'
            result['error'] = 'Invalid output'
            return result
        
        result['icebreaker'] = icebreaker
        result['status'] = 'success'
        
    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)[:50]
    
    return result


def process_leads_parallel(leads, ai_key, model_id, max_workers=3, ai_provider="Gemini (Google)", delay_per_worker=2):
    """Process leads in parallel with staggered AI calls
    
    Args:
        delay_per_worker: Seconds to stagger AI calls between workers (default 2s)
    """
    results = []
    
    # Stagger only for AI calls, scraping runs immediately for all
    lead_args = []
    for i, lead in enumerate(leads):
        # Small stagger delay: 0s, 2s, 4s for 3 workers
        worker_id = i % max_workers
        initial_delay = worker_id * delay_per_worker
        lead_args.append((lead, ai_key, model_id, ai_provider, initial_delay))
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(process_single_lead_with_delay, args): i 
            for i, args in enumerate(lead_args)
        }
        
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                result = future.result()
                results.append((idx, result))
            except Exception as e:
                lead = leads[idx].copy()
                lead['status'] = 'failed'
                lead['error'] = str(e)[:50]
                results.append((idx, lead))
    
    results.sort(key=lambda x: x[0])
    return [r[1] for r in results]


def process_leads_sequential(leads, ai_key, model_id, ai_provider="Gemini (Google)", delay_between=0.5, progress_callback=None):
    """Process leads one by one with minimal delay - often faster than parallel for API calls
    
    Args:
        delay_between: Seconds to wait between each lead (default 0.5s)
        progress_callback: Function to call after each lead (for UI updates)
    """
    results = []
    
    for i, lead in enumerate(leads):
        # Process this lead
        args = (lead, ai_key, model_id, ai_provider, 0)  # No initial delay
        result = process_single_lead_with_delay(args)
        results.append(result)
        
        # Small delay between leads
        if i < len(leads) - 1 and delay_between > 0:
            time.sleep(delay_between)
        
        # Callback for progress updates
        if progress_callback:
            progress_callback(i + 1, len(leads), result)
    
    return results


def save_to_google_sheets_custom(credentials_json, sheet_id, leads_data, selected_columns):
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        creds = Credentials.from_service_account_info(credentials_json, scopes=SCOPES)
        service = build('sheets', 'v4', credentials=creds)
        
        spreadsheet = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        first_sheet = spreadsheet['sheets'][0]['properties']['title']
        
        num_cols = len(selected_columns)
        end_col = chr(ord('A') + num_cols - 1) if num_cols <= 26 else 'Z'
        
        try:
            service.spreadsheets().values().clear(
                spreadsheetId=sheet_id,
                range=f"'{first_sheet}'!A:{end_col}"
            ).execute()
        except:
            pass
        
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"'{first_sheet}'!A1:{end_col}1",
            valueInputOption='RAW',
            body={'values': [selected_columns]}
        ).execute()
        
        rows = []
        for lead in leads_data:
            row = []
            for col in selected_columns:
                if col == 'location':
                    parts = []
                    for f in ['company_city', 'company_state', 'company_country']:
                        val = lead.get(f, '')
                        if val and str(val).lower() not in ['none', 'nan', '']:
                            parts.append(str(val))
                    row.append(', '.join(parts))
                else:
                    val = lead.get(col, '')
                    if str(val).lower() in ['none', 'nan']:
                        val = ''
                    row.append(str(val) if val else '')
            rows.append(row)
        
        if rows:
            service.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range=f"'{first_sheet}'!A:{end_col}",
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': rows}
            ).execute()
        
        return len(rows), None
    except Exception as e:
        return 0, str(e)


# ═══════════════════════════════════════════════════════════════
# 📥 EXPORT FUNCTIONS (Excel, CSV, JSON)
# ═══════════════════════════════════════════════════════════════
def prepare_export_data(leads, columns):
    """Prepare data for export"""
    export_data = []
    for lead in leads:
        row = {}
        for col in columns:
            if col == 'location':
                parts = [str(lead.get(f, '')) for f in ['company_city', 'company_state', 'company_country'] 
                        if lead.get(f) and str(lead.get(f)).lower() not in ['none', 'nan', '']]
                row[col] = ', '.join(parts)
            else:
                val = lead.get(col, '')
                row[col] = '' if str(val).lower() in ['none', 'nan'] else str(val)
        export_data.append(row)
    return export_data


def export_to_csv(data):
    """Export to CSV"""
    df = pd.DataFrame(data)
    return df.to_csv(index=False)


def export_to_json(data):
    """Export to JSON"""
    return json.dumps(data, indent=2, ensure_ascii=False)


def export_to_excel(data):
    """Export to Excel"""
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Icebreakers')
    return output.getvalue()


# ═══════════════════════════════════════════════════════════════
# MAIN UI
# ═══════════════════════════════════════════════════════════════

# Top bar with theme toggle
top_col1, top_col2, top_col3 = st.columns([1, 6, 1])
with top_col3:
    theme_icon = "🌙" if st.session_state.dark_mode else "☀️"
    if st.button(theme_icon, help="Toggle Dark/Light Mode"):
        st.session_state.dark_mode = not st.session_state.dark_mode
        st.rerun()

st.markdown('<h1 class="main-title">🎬 Narratives Media</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">Lead Icebreaker Generator v6 | ⚡ Parallel Processing | 🌓 Dark/Light Mode</p>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# 🔧 QUICK SETTINGS (Expander - Alternative to Sidebar)
# ═══════════════════════════════════════════════════════════════
with st.expander("⚙️ Quick Settings (Click to expand - API Keys, Model, etc.)", expanded=False):
    # Profile selection
    profile_col1, profile_col2, profile_col3 = st.columns([2, 1, 1])
    with profile_col1:
        all_profiles = get_all_profiles()
        selected_profile = st.selectbox("📁 Profile", options=all_profiles, 
                                        index=all_profiles.index(st.session_state.current_profile) if st.session_state.current_profile in all_profiles else 0,
                                        key="profile_select")
        if selected_profile != st.session_state.current_profile:
            st.session_state.current_profile = selected_profile
            st.session_state.db_settings_loaded = False
            st.rerun()
    with profile_col2:
        new_profile_name = st.text_input("New Profile", placeholder="my_project", key="new_profile")
    with profile_col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ Create", key="create_profile"):
            if new_profile_name and new_profile_name not in all_profiles:
                save_settings(new_profile_name)
                st.session_state.current_profile = new_profile_name
                st.session_state.db_settings_loaded = False
                st.rerun()
    
    st.markdown("---")
    
    settings_col1, settings_col2, settings_col3 = st.columns(3)
    
    with settings_col1:
        st.markdown("##### 🔑 API Keys")
        main_apify_token = st.text_input("Apify Token", type="password", key="main_apify", placeholder="apify_api_xxx...")
        # AI Provider Selection
        provider_index = list(AI_PROVIDERS.keys()).index(st.session_state.get('saved_provider', 'Gemini (Google)')) if st.session_state.get('saved_provider') in AI_PROVIDERS else 0
        main_ai_provider = st.selectbox("🤖 AI Provider", options=list(AI_PROVIDERS.keys()), index=provider_index, key="main_provider")
        
        # Dynamic API Key based on provider
        if main_ai_provider == "Gemini (Google)":
            main_ai_key = st.text_input("Gemini API Key", type="password", key="main_gemini", placeholder="AIzaSy...")
        elif main_ai_provider == "OpenAI (GPT)":
            main_ai_key = st.text_input("OpenAI API Key", type="password", key="main_openai", placeholder="sk-...")
        elif main_ai_provider == "Claude (Anthropic)":
            main_ai_key = st.text_input("Claude API Key", type="password", key="main_claude", placeholder="sk-ant-...")
    
    with settings_col2:
        st.markdown("##### 📊 Google Sheets")
        main_sheet_id = st.text_input("Sheet ID", key="main_sheet", placeholder="1XxZRHwqu4AfTPL...")
        main_credentials_file = st.file_uploader("Service Account JSON", type=['json'], key="main_creds")
    
    with settings_col3:
        st.markdown("##### ⚡ AI Model & Performance")
        # Dynamic model selection based on provider
        main_model_options = list(AI_PROVIDERS[main_ai_provider]["models"].keys())
        saved_model = st.session_state.get('saved_model', main_model_options[0])
        model_index = main_model_options.index(saved_model) if saved_model in main_model_options else 0
        main_selected_model = st.selectbox("AI Model", options=main_model_options, index=model_index, key="main_model")
        
        # Processing mode selection
        processing_mode = st.radio("🔄 Processing Mode", 
                                   ["⚡ Sequential (Faster)", "🔀 Parallel"], 
                                   index=0, 
                                   horizontal=True,
                                   help="Sequential is often faster for API calls")
        
        if processing_mode == "⚡ Sequential (Faster)":
            main_parallel_workers = 1
            main_request_delay = st.slider("⏱️ Delay Between Leads (sec)", 0.0, 2.0, 0.5, 0.1, key="main_delay",
                                           help="Small delay between each lead")
        else:
            # Parallel mode settings
            model_id = AI_PROVIDERS[main_ai_provider]["models"][main_selected_model]
            if 'preview' in model_id.lower() or 'gemini-3' in model_id.lower():
                max_workers = 3
            else:
                max_workers = 5
            
            main_parallel_workers = st.slider("⚡ Workers", 2, max_workers, 3, key="main_workers")
            main_request_delay = st.slider("⏱️ Stagger (sec)", 0, 5, 2, key="main_delay",
                                           help="Delay between workers")
        
        st.info(f"🗄️ Cached: {get_cache_size()} sites")
    
    # Save Settings Button
    st.markdown("---")
    save_col1, save_col2, save_col3 = st.columns([2, 1, 1])
    with save_col1:
        if st.button("💾 Save Settings to Database", type="primary", width="stretch"):
            # Get the appropriate API key based on provider
            gemini_key = main_ai_key if main_ai_provider == "Gemini (Google)" else st.session_state.get('saved_gemini', '')
            openai_key = main_ai_key if main_ai_provider == "OpenAI (GPT)" else st.session_state.get('saved_openai', '')
            claude_key = main_ai_key if main_ai_provider == "Claude (Anthropic)" else st.session_state.get('saved_claude', '')
            
            save_settings(
                profile_name=st.session_state.current_profile,
                apify_token=main_apify_token,
                gemini_key=gemini_key,
                openai_key=openai_key,
                claude_key=claude_key,
                sheet_id=main_sheet_id,
                default_provider=main_ai_provider,
                default_model=main_selected_model,
                parallel_workers=main_parallel_workers,
                dark_mode=st.session_state.dark_mode
            )
            st.success("✅ Settings saved!")
            st.session_state.db_settings_loaded = False
            st.rerun()
    with save_col2:
        # Database Stats
        db_stats = get_leads_stats()
        st.metric("📊 Total Leads", db_stats['total_leads'])
    with save_col3:
        st.metric("✅ Success Rate", f"{db_stats['success_rate']:.1f}%")

# ═══════════════════════════════════════════════════════════════
# SIDEBAR (Still available if user can access it)
# ═══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    st.info("💡 Settings also available in main page expander above!")
    
    st.markdown("---")
    
    # Theme Toggle
    st.markdown("### 🌓 Theme")
    theme_col1, theme_col2 = st.columns(2)
    with theme_col1:
        if st.button("🌙 Dark", width="stretch", type="primary" if st.session_state.dark_mode else "secondary"):
            st.session_state.dark_mode = True
            st.rerun()
    with theme_col2:
        if st.button("☀️ Light", width="stretch", type="primary" if not st.session_state.dark_mode else "secondary"):
            st.session_state.dark_mode = False
            st.rerun()
    
    st.markdown("---")
    
    # API Keys
    st.markdown("### 🔑 API Keys")
    side_apify_token = st.text_input("Apify API Token", type="password", placeholder="apify_api_xxx...", key="side_apify")
    
    # AI Provider Selection
    st.markdown("### 🤖 AI Provider")
    side_ai_provider = st.selectbox("Select Provider", options=list(AI_PROVIDERS.keys()), index=0, key="side_provider")
    
    # Dynamic API Key based on provider
    if side_ai_provider == "Gemini (Google)":
        side_ai_key = st.text_input("Gemini API Key", type="password", placeholder="AIzaSy...", key="side_gemini")
    elif side_ai_provider == "OpenAI (GPT)":
        side_ai_key = st.text_input("OpenAI API Key", type="password", placeholder="sk-...", key="side_openai")
    elif side_ai_provider == "Claude (Anthropic)":
        side_ai_key = st.text_input("Claude API Key", type="password", placeholder="sk-ant-...", key="side_claude")
    
    st.markdown("---")
    
    # Google Sheets
    st.markdown("### 📊 Google Sheets")
    sheet_id = st.text_input("Sheet ID", placeholder="1XxZRHwqu4AfTPL...", key="side_sheet")
    credentials_file = st.file_uploader("Service Account JSON", type=['json'], key="side_creds")
    
    st.markdown("---")
    
    # AI Model (Dynamic based on provider)
    st.markdown("### 🧠 AI Model")
    side_model_options = list(AI_PROVIDERS[side_ai_provider]["models"].keys())
    selected_model = st.selectbox("Select Model", options=side_model_options, index=0, key="side_model")
    model_id = AI_PROVIDERS[side_ai_provider]["models"][selected_model]
    st.markdown(f'<span class="model-badge">{model_id}</span>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Performance
    st.markdown("### ⚡ Performance")
    parallel_workers = st.slider("Parallel Workers", 1, 5, 3, key="side_workers")
    st.markdown(f'<span class="speed-badge">~{parallel_workers}x faster</span>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Cache Stats
    st.markdown("### 🗄️ Cache")
    st.info(f"Cached: {get_cache_size()} sites")
    if st.button("🗑️ Clear Cache"):
        clear_cache()
        st.rerun()

# ═══════════════════════════════════════════════════════════════
# GET VALUES FROM EITHER MAIN OR SIDEBAR
# ═══════════════════════════════════════════════════════════════
# Use main page settings if filled, otherwise use sidebar
apify_token = main_apify_token or side_apify_token
ai_key = main_ai_key if main_ai_key else side_ai_key  # AI Key (unified)
ai_provider = main_ai_provider  # AI Provider
sheet_id = main_sheet_id or sheet_id
credentials_file = main_credentials_file or credentials_file
selected_model = main_selected_model
model_id = AI_PROVIDERS[ai_provider]["models"][selected_model]
parallel_workers = main_parallel_workers
request_delay = main_request_delay  # Delay between requests
is_sequential = (processing_mode == "⚡ Sequential (Faster)")

# ═══════════════════════════════════════════════════════════════
# 📊 REAL-TIME STATS DASHBOARD
# ═══════════════════════════════════════════════════════════════
st.markdown("""
<div class="stats-dashboard">
    <h3 style="margin-bottom: 1rem; color: inherit;">📊 Real-Time Dashboard</h3>
</div>
""", unsafe_allow_html=True)

dash_col1, dash_col2, dash_col3, dash_col4, dash_col5 = st.columns(5)

with dash_col1:
    total_loaded = len(st.session_state.leads_data) if st.session_state.leads_data else 0
    st.metric("📥 Loaded", total_loaded)

with dash_col2:
    total_filtered = len(st.session_state.filtered_leads) if st.session_state.filtered_leads else 0
    st.metric("🔍 Filtered", total_filtered)

with dash_col3:
    total_processed = len(st.session_state.processed_results)
    st.metric("⚙️ Processed", total_processed)

with dash_col4:
    success_count = len([r for r in st.session_state.processed_results if r.get('status') == 'success'])
    st.metric("✅ Success", success_count)

with dash_col5:
    fail_count = len([r for r in st.session_state.processed_results if r.get('status') == 'failed'])
    st.metric("❌ Failed", fail_count)

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# 📑 MAIN TABS - Processing & History
# ═══════════════════════════════════════════════════════════════
main_tab1, main_tab2 = st.tabs(["🚀 Process Leads", "📜 History"])

with main_tab1:
    # ═══════════════════════════════════════════════════════════════
    # STEP 1: GET LEADS
    # ═══════════════════════════════════════════════════════════════
    st.markdown("""
    <div class="glass-card">
        <div class="step-header"><span class="step-number">1</span> Get Leads from Apify</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### 📦 From Dataset")
        dataset_id = st.text_input("Dataset ID", placeholder="MQvZgNeNFS2BG69rW", label_visibility="collapsed")
        fetch_btn = st.button("📥 Fetch Dataset", width="stretch", type="primary")

    with col2:
        st.markdown("##### 🚀 Run Task")
        task_id = st.text_input("Task ID", value="jwocmha1QeTkoi3NE", label_visibility="collapsed")
        run_btn = st.button("🚀 Run Apify Task", width="stretch")

    if fetch_btn and apify_token and dataset_id:
        with st.spinner("⏳ Fetching..."):
            data, err = fetch_apify_data(apify_token, dataset_id)
            if err:
                st.error(f"❌ {err}")
            else:
                st.session_state.leads_data = data
                st.success(f"✅ {len(data)} leads loaded!")
                st.rerun()

    if run_btn and apify_token:
        with st.spinner("⏳ Running Apify task..."):
            data, err = run_apify_task(apify_token, task_id)
            if err:
                st.error(f"❌ {err}")
            else:
                st.session_state.leads_data = data
                st.success(f"✅ {len(data)} leads loaded!")
                st.rerun()

    if st.session_state.leads_data:
        with st.expander(f"👁️ Preview Leads ({len(st.session_state.leads_data)} total)"):
            df = pd.DataFrame(st.session_state.leads_data)
            cols = ['first_name', 'last_name', 'email', 'company_website', 'company_name']
            cols = [c for c in cols if c in df.columns]
            st.dataframe(df[cols].head(10), width="stretch")

    st.markdown("---")

    # ═══════════════════════════════════════════════════════════════
    # STEP 2: FILTER
    # ═══════════════════════════════════════════════════════════════
    st.markdown("""
    <div class="glass-card">
        <div class="step-header"><span class="step-number">2</span> Filter Leads</div>
    </div>
    """, unsafe_allow_html=True)

    if not st.session_state.leads_data:
        st.info("⬆️ প্রথমে Step 1 এ data load করো")
    else:
        if st.button("🔍 Filter (Valid Email + Website)", width="stretch", type="primary"):
            filtered, removed = filter_leads(st.session_state.leads_data)
            st.session_state.filtered_leads = filtered
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Total", len(st.session_state.leads_data))
            col2.metric("✅ Valid", len(filtered), delta=f"{len(filtered)/len(st.session_state.leads_data)*100:.0f}%")
            col3.metric("❌ Removed", len(removed))
            st.rerun()
        
        if st.session_state.filtered_leads:
            st.success(f"✅ {len(st.session_state.filtered_leads)} leads ready for processing!")

    st.markdown("---")

    # ═══════════════════════════════════════════════════════════════
    # STEP 3: PROCESS
    # ═══════════════════════════════════════════════════════════════
    mode_text = "Sequential" if is_sequential else "Parallel"
    st.markdown(f"""
    <div class="glass-card">
        <div class="step-header"><span class="step-number">3</span> Process Leads (⚡ {mode_text})</div>
    </div>
    """, unsafe_allow_html=True)

    if not st.session_state.filtered_leads:
        st.info("⬆️ প্রথমে Step 2 এ filter করো")
    else:
        total_leads = len(st.session_state.filtered_leads)
        
        col1, col2 = st.columns(2)
        start_idx = col1.number_input("Start #", 1, total_leads, 1)
        end_idx = col2.number_input("End #", 1, total_leads, min(50, total_leads))
        
        leads_count = end_idx - start_idx + 1
        
        # Estimated time calculation
        if is_sequential:
            # Sequential: ~15 sec per lead (scrape + 2 AI calls) + small delay
            est_time = leads_count * (15 + request_delay)
            mode_display = "Sequential (1 by 1)"
        else:
            # Parallel: divide by workers but add stagger time
            time_per_batch = 15 + (request_delay * (parallel_workers - 1))
            est_time = (leads_count / parallel_workers) * time_per_batch
            mode_display = f"Parallel ({parallel_workers} workers)"
        
        st.markdown(f"""
        <div class="glass-card-purple">
            <strong>📊 Processing Info:</strong><br>
            • Leads: <strong>{leads_count}</strong><br>
            • Mode: <strong>{mode_display}</strong><br>
            • Delay: <strong>{request_delay}s</strong><br>
            • Model: <strong>{model_id}</strong><br>
            • Est. Time: <strong>~{est_time/60:.1f} min</strong>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        start_btn = col1.button("🚀 Start Processing", type="primary", width="stretch")
        stop_btn = col2.button("⏹️ Stop", width="stretch")
        
        if stop_btn:
            st.session_state.stop_processing = True
        
        if start_btn:
            if not ai_key:
                st.error(f"❌ {ai_provider} API Key দাও - Quick Settings এ")
            else:
                st.session_state.stop_processing = False
                st.session_state.processed_results = []
                st.session_state.processing_stats['start_time'] = time.time()
                
                # Progress indicators
                progress_container = st.container()
                with progress_container:
                    progress_bar = st.progress(0)
                    status_col1, status_col2, status_col3 = st.columns(3)
                    status_text = status_col1.empty()
                    time_text = status_col2.empty()
                    speed_text = status_col3.empty()
                
                results_container = st.container()
                
                leads_to_process = st.session_state.filtered_leads[start_idx-1:end_idx]
                total = len(leads_to_process)
                
                all_results = []
                start_time = time.time()
                
                # Show AI info
                mode_info = "Sequential (1 by 1)" if is_sequential else f"Parallel ({parallel_workers} workers)"
                st.info(f"🤖 Using **{ai_provider}** | Model: **{model_id}** | Mode: **{mode_info}**")
                
                if is_sequential:
                    # ═══════════════════════════════════════════════════════════════
                    # SEQUENTIAL MODE - Process one by one
                    # ═══════════════════════════════════════════════════════════════
                    for i, lead in enumerate(leads_to_process):
                        if st.session_state.stop_processing:
                            st.warning("⏹️ Processing stopped!")
                            break
                        
                        # Update progress
                        progress = (i + 1) / total
                        progress_bar.progress(progress)
                        
                        elapsed = time.time() - start_time
                        speed = (i + 1) / elapsed if elapsed > 0 else 0
                        remaining = (total - i - 1) / speed if speed > 0 else 0
                        
                        status_text.markdown(f'<div class="processing-indicator">⚡ {i+1}/{total}</div>', unsafe_allow_html=True)
                        time_text.markdown(f"⏱️ Elapsed: **{elapsed:.0f}s** | Remaining: **~{remaining:.0f}s**")
                        speed_text.markdown(f"🚀 Speed: **{speed:.2f}** leads/sec")
                        
                        # Process single lead
                        args = (lead, ai_key, model_id, ai_provider, 0)
                        result = process_single_lead_with_delay(args)
                        all_results.append(result)
                        
                        # Show result immediately
                        name = f"{result.get('first_name', '')} {result.get('last_name', '')}"
                        sentiment = result.get('sentiment', '')
                        sentiment_badge = f" [{sentiment}]" if sentiment else ""
                        
                        if result['status'] == 'success':
                            with results_container:
                                st.markdown(f'<div class="success-card">✅ <strong>{name}</strong>{sentiment_badge}: {result["icebreaker"][:120]}...</div>', unsafe_allow_html=True)
                        else:
                            with results_container:
                                st.markdown(f'<div class="error-card">❌ <strong>{name}</strong>: {result.get("error", "Error")}</div>', unsafe_allow_html=True)
                        
                        # Small delay between leads
                        if i < total - 1 and request_delay > 0:
                            time.sleep(request_delay)
                else:
                    # ═══════════════════════════════════════════════════════════════
                    # PARALLEL MODE - Process in batches
                    # ═══════════════════════════════════════════════════════════════
                    batch_size = parallel_workers
                    
                    for batch_start in range(0, total, batch_size):
                        if st.session_state.stop_processing:
                            st.warning("⏹️ Processing stopped!")
                            break
                        
                        batch_end = min(batch_start + batch_size, total)
                        batch = leads_to_process[batch_start:batch_end]
                        
                        # Update progress
                        progress = len(all_results) / total
                        progress_bar.progress(progress)
                        
                        elapsed = time.time() - start_time
                        speed = len(all_results) / elapsed if elapsed > 0 else 0
                        remaining = (total - len(all_results)) / speed if speed > 0 else 0
                        
                        status_text.markdown(f'<div class="processing-indicator">⚡ {batch_start+1}-{batch_end}/{total}</div>', unsafe_allow_html=True)
                        time_text.markdown(f"⏱️ Elapsed: **{elapsed:.0f}s** | Remaining: **~{remaining:.0f}s**")
                        speed_text.markdown(f"🚀 Speed: **{speed:.1f}** leads/sec")
                        
                        # Process batch with staggered delays
                        batch_results = process_leads_parallel(batch, ai_key, model_id, parallel_workers, ai_provider, request_delay)
                        all_results.extend(batch_results)
                        
                        # Show results
                        for result in batch_results:
                            name = f"{result.get('first_name', '')} {result.get('last_name', '')}"
                            sentiment = result.get('sentiment', '')
                            sentiment_badge = f" [{sentiment}]" if sentiment else ""
                            
                            if result['status'] == 'success':
                                with results_container:
                                    st.markdown(f'<div class="success-card">✅ <strong>{name}</strong>{sentiment_badge}: {result["icebreaker"][:120]}...</div>', unsafe_allow_html=True)
                            else:
                                with results_container:
                                    st.markdown(f'<div class="error-card">❌ <strong>{name}</strong>: {result.get("error", "Error")}</div>', unsafe_allow_html=True)
                
                st.session_state.processed_results = all_results
                progress_bar.progress(1.0)
                
                # Final stats
                total_time = time.time() - start_time
                success = len([r for r in all_results if r['status'] == 'success'])
                failed = len(all_results) - success
                
                # 💾 Save to Database
                session_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"
                session_name = f"Batch_{len(all_results)}_leads"
                
                try:
                    save_leads_to_history(all_results, session_id, ai_provider, model_id)
                    save_session(session_id, session_name, len(all_results), success, failed, ai_provider, model_id, total_time)
                    st.success("💾 Results saved to database!")
                except Exception as e:
                    st.warning(f"⚠️ Could not save to database: {e}")
                
                st.balloons()
                
                status_text.markdown("✅ **Complete!**")
                time_text.markdown(f"⏱️ Total: **{total_time:.0f}s**")
                speed_text.markdown(f"📊 Rate: **{success/(total_time/60):.1f}** success/min")
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total", len(all_results))
                col2.metric("✅ Success", success, delta=f"{success/len(all_results)*100:.0f}%")
                col3.metric("❌ Failed", failed)
                col4.metric("⏱️ Time", f"{total_time:.0f}s")

    st.markdown("---")

    # ═══════════════════════════════════════════════════════════════
    # STEP 4: EXPORT
    # ═══════════════════════════════════════════════════════════════
    st.markdown("""
    <div class="glass-card">
        <div class="step-header"><span class="step-number">4</span> Export Results</div>
    </div>
    """, unsafe_allow_html=True)

    if not st.session_state.processed_results:
        st.info("⬆️ প্রথমে Step 3 এ process করো")
    else:
        success_leads = [l for l in st.session_state.processed_results if l.get('status') == 'success']
        failed_leads = [l for l in st.session_state.processed_results if l.get('status') == 'failed']
        
        col1, col2 = st.columns(2)
        col1.success(f"✅ {len(success_leads)} successful leads")
        col2.warning(f"❌ {len(failed_leads)} failed leads")
        
        if success_leads:
            # Column selector
            st.markdown("#### 📋 Select Export Columns")
            
            COLUMNS = {
                'first_name': 'First Name', 
                'last_name': 'Last Name', 
                'email': 'Email',
                'company_website': 'Website', 
                'company_name': 'Company', 
                'job_title': 'Job Title',
                'location': 'Location',
                'company_phone': 'Phone', 
                'icebreaker': 'Icebreaker', 
                'status': 'Status',
                # 🔥 NEW: Content analysis columns
                'content_quality': '📊 Content Quality',
                'content_gaps': '🎯 Content Gaps (Opportunities)',
                'youtube_url': '📺 YouTube URL',
                'linkedin_url': '💼 LinkedIn URL',
                'social_count': '📱 Social Platforms',
                'sentiment': '😊 Sentiment',
                'industry': '🏢 Industry'
            }
            
            DEFAULT = ['first_name', 'last_name', 'email', 'company_website', 'icebreaker', 'content_quality', 'content_gaps']
            
            selected_names = st.multiselect(
                "Columns to export:",
                options=[COLUMNS[k] for k in COLUMNS.keys()],
                default=[COLUMNS[c] for c in DEFAULT if c in COLUMNS]
            )
            
            selected_cols = [k for k, v in COLUMNS.items() if v in selected_names]
            
            # Preview
            if selected_cols:
                with st.expander("👁️ Preview Export Data"):
                    preview_data = prepare_export_data(success_leads[:5], selected_cols)
                    st.dataframe(pd.DataFrame(preview_data), width="stretch")
            
            st.markdown("---")
            
            # Export Options
            st.markdown("#### 📥 Export Options")
            
            export_col1, export_col2, export_col3, export_col4 = st.columns(4)
            
            export_data = prepare_export_data(success_leads, selected_cols)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M')
            
            # CSV Export
            with export_col1:
                csv_data = export_to_csv(export_data)
                st.download_button(
                    "📄 CSV",
                    data=csv_data,
                    file_name=f"icebreakers_{timestamp}.csv",
                    mime="text/csv",
                    width="stretch"
                )
            
            # JSON Export
            with export_col2:
                json_data = export_to_json(export_data)
                st.download_button(
                    "📋 JSON",
                    data=json_data,
                    file_name=f"icebreakers_{timestamp}.json",
                    mime="application/json",
                    width="stretch"
                )
            
            # Excel Export
            with export_col3:
                try:
                    excel_data = export_to_excel(export_data)
                    st.download_button(
                        "📊 Excel",
                        data=excel_data,
                        file_name=f"icebreakers_{timestamp}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        width="stretch"
                    )
                except Exception as e:
                    st.button("📊 Excel (Need openpyxl)", disabled=True, width="stretch")
            
            # Google Sheets
            with export_col4:
                if st.button("📤 Google Sheets", type="primary", width="stretch"):
                    if not sheet_id or not credentials_file:
                        st.error("❌ Sheet ID ও JSON দাও sidebar এ")
                    else:
                        with st.spinner("💾 Saving to Google Sheets..."):
                            try:
                                creds = json.load(credentials_file)
                                count, err = save_to_google_sheets_custom(creds, sheet_id, success_leads, selected_cols)
                                if err:
                                    st.error(f"❌ {err}")
                                else:
                                    st.success(f"✅ {count} leads saved!")
                                    st.markdown(f"[🔗 Open Google Sheet](https://docs.google.com/spreadsheets/d/{sheet_id})")
                            except Exception as e:
                                st.error(f"❌ {e}")
            
            # Failed leads export (optional)
            if failed_leads:
                st.markdown("---")
                with st.expander("📥 Export Failed Leads (for retry)"):
                    failed_data = prepare_export_data(failed_leads, ['first_name', 'last_name', 'email', 'company_website', 'error'])
                    failed_csv = export_to_csv(failed_data)
                    st.download_button(
                        "📄 Download Failed Leads CSV",
                        data=failed_csv,
                        file_name=f"failed_leads_{timestamp}.csv",
                        mime="text/csv"
                    )

# ═══════════════════════════════════════════════════════════════
# 📜 HISTORY TAB - View Past Sessions
# ═══════════════════════════════════════════════════════════════
with main_tab2:
    st.markdown("""
    <div class="glass-card">
        <div class="step-header">📜 Processing History</div>
        <p style="opacity: 0.7;">View and reload past processing sessions</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Get all sessions
    all_sessions = get_all_sessions()
    
    if not all_sessions:
        st.info("📭 No processing history yet. Process some leads first!")
    else:
        # Overall stats
        db_stats = get_leads_stats()
        hist_col1, hist_col2, hist_col3, hist_col4 = st.columns(4)
        with hist_col1:
            st.metric("📊 Total Leads Processed", db_stats['total_leads'])
        with hist_col2:
            st.metric("✅ Successful", db_stats['success_leads'])
        with hist_col3:
            st.metric("📁 Total Sessions", db_stats['total_sessions'])
        with hist_col4:
            st.metric("📈 Success Rate", f"{db_stats['success_rate']:.1f}%")
        
        st.markdown("---")
        
        # Sessions list
        st.markdown("### 📁 Past Sessions")
        
        for session in all_sessions:
            with st.expander(f"🗓️ {session['created_at'][:16]} | {session['name']} | {session['total_leads']} leads ({session['success_count']} ✅)"):
                session_col1, session_col2 = st.columns([3, 1])
                
                with session_col1:
                    st.markdown(f"""
                    - **Session ID:** `{session['id'][:8]}...`
                    - **AI Provider:** {session['ai_provider']}
                    - **Model:** {session['ai_model']}
                    - **Duration:** {session['duration']:.1f} seconds
                    - **Success Rate:** {(session['success_count']/session['total_leads']*100):.1f}%
                    """)
                
                with session_col2:
                    if st.button("📥 Load", key=f"load_{session['id']}"):
                        # Load leads from this session
                        session_leads = get_session_leads(session['id'])
                        if session_leads:
                            st.session_state.processed_results = session_leads
                            st.success(f"✅ Loaded {len(session_leads)} leads!")
                            st.rerun()
                    
                    # Export this session
                    session_leads = get_session_leads(session['id'])
                    if session_leads:
                        export_data = prepare_export_data(session_leads, 
                            ['first_name', 'last_name', 'email', 'company_name', 'icebreaker', 'sentiment', 'status'])
                        csv_data = export_to_csv(export_data)
                        st.download_button(
                            "📄 CSV",
                            data=csv_data,
                            file_name=f"session_{session['id'][:8]}.csv",
                            mime="text/csv",
                            key=f"csv_{session['id']}"
                        )

# ═══════════════════════════════════════════════════════════════
# FOOTER
# ═══════════════════════════════════════════════════════════════
st.markdown("""
<div class="credit-footer">
    <div class="brand">🎬 Narratives Media v7</div>
    <div style="color: inherit; opacity: 0.7;">💾 Database | 🤖 Multi-AI | 😊 Sentiment | 🌓 Dark/Light</div>
    <div style="opacity: 0.5; font-size: 0.8rem; margin-top: 0.5rem;">Created by Habibur</div>
</div>
""", unsafe_allow_html=True)
