# 🎬 Narratives Media - Lead Icebreaker Generator

An AI-powered lead research tool that generates personalized icebreakers for sales outreach.

## Features

- 🤖 **Multiple AI Providers**: Gemini, OpenAI GPT-4, Claude
- 🔍 **Lead Research**: Automated website scraping & analysis
- 📊 **Social Media Analysis**: Detects YouTube, LinkedIn, Facebook presence
- 🎯 **Content Gap Detection**: Identifies video/blog opportunities
- 💾 **Database Storage**: Saves API keys & lead history
- 📤 **Export Options**: CSV, Excel, Google Sheets

---

## 🚀 Deploy to Streamlit Cloud (FREE - 24/7 Online)

### Step 1: Create GitHub Repository

1. Go to [GitHub](https://github.com) and create a new repository
2. Name it: `narratives-lead-generator`
3. Make it **Private** (recommended)

### Step 2: Push Code to GitHub

```bash
# Initialize git
git init
git add app.py requirements.txt README.md .streamlit/

# Commit
git commit -m "Initial commit"

# Add your GitHub repo (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/narratives-lead-generator.git
git branch -M main
git push -u origin main
```

### Step 3: Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Click **"New app"**
4. Select your repository
5. Main file: `app.py`
6. Click **Deploy!**

### Step 4: Add Secrets (API Keys)

After deployment, click ⚙️ **Settings** → **Secrets** and add:

```toml
APIFY_TOKEN = "your_apify_token"
GEMINI_API_KEY = "your_gemini_key"
```

Your app URL: `https://your-app-name.streamlit.app`

---

## 🔄 এই App কি করে?

```
Step 1: Apify থেকে Apollo leads নিয়ে আসে
           ↓
Step 2: Invalid leads filter করে (email/website নেই)
           ↓
Step 3: Website scrape + Social media analysis
           ↓
Step 4: AI দিয়ে personalized icebreaker বানায়
           ↓
Step 5: Export (CSV/Excel/Google Sheets)
```

---

## 📋 তোমার যা লাগবে (একবারই সেটআপ)

| Item | কোথায় পাবে |
|------|------------|
| Apify API Token | https://console.apify.com → Settings → API tokens |
| Gemini API Key | https://makersuite.google.com/app/apikey |
| Google Sheet ID | Sheet এর URL থেকে |
| Service Account JSON | Google Cloud Console থেকে (নিচে বলছি) |

---

## 🚀 কিভাবে চালাবে (Step by Step)

### প্রথমবার Setup (একবারই করতে হবে)

#### Step 1: এই folder টা download করে extract করো
- যেকোনো জায়গায় রাখতে পারো (যেমন Downloads folder এ)

#### Step 2: Terminal খোলো
- `Cmd + Space` চাপো
- "Terminal" লেখো
- Enter চাপো

#### Step 3: Folder এ যাও
Terminal এ এই command লেখো (তোমার folder এর location অনুযায়ী):
```bash
cd ~/Downloads/narratives_app
```

#### Step 4: Permission দাও (একবারই)
```bash
chmod +x start.sh
```

#### Step 5: App চালাও
```bash
./start.sh
```

#### Step 6: Browser এ যাও
```
http://localhost:8501
```

---

### পরের বার থেকে (শুধু 3টা command)

```bash
cd ~/Downloads/narratives_app
./start.sh
```
তারপর browser এ `http://localhost:8501`

---

## 🔑 API Keys কিভাবে পাবে

### 1. Apify API Token

1. যাও: https://console.apify.com
2. Login করো
3. উপরে ডানদিকে তোমার নাম → Settings
4. "Integrations" tab এ যাও
5. "Personal API tokens" section এ token টা copy করো

### 2. Gemini API Key

1. যাও: https://makersuite.google.com/app/apikey
2. Google account দিয়ে login করো
3. "Create API Key" button এ click করো
4. Key টা copy করে রাখো

### 3. Google Sheet ID

তোমার Google Sheet এর URL দেখো:
```
https://docs.google.com/spreadsheets/d/1XxZRHwqu4AfTPLUtBmJcPlh6Ku3ADGXuIgs9P2TcZ78/edit
                                        ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑
                                        এটাই Sheet ID
```

### 4. Google Service Account JSON (একটু জটিল, কিন্তু একবারই করতে হবে)

#### Step A: Google Cloud Project তৈরি করো
1. যাও: https://console.cloud.google.com
2. উপরে "Select a project" → "New Project"
3. নাম দাও: "Narratives Automation"
4. "Create" করো

#### Step B: Google Sheets API চালু করো
1. বামদিকে menu → "APIs & Services" → "Library"
2. Search করো: "Google Sheets API"
3. Click করো এবং "Enable" করো

#### Step C: Service Account তৈরি করো
1. বামদিকে menu → "APIs & Services" → "Credentials"
2. উপরে "+ CREATE CREDENTIALS" → "Service account"
3. নাম দাও: "narratives-sheets"
4. "Create and Continue" করো
5. Role: "Editor" select করো
6. "Done" করো

#### Step D: JSON Key Download করো
1. তৈরি হওয়া Service Account এ click করো
2. "Keys" tab এ যাও
3. "Add Key" → "Create new key"
4. "JSON" select করো
5. "Create" করো
6. একটা file download হবে - এটাই তোমার credentials file

#### Step E: Google Sheet এ Access দাও
1. Download করা JSON file টা open করো (যেকোনো text editor দিয়ে)
2. `"client_email":` এর পাশে যে email আছে সেটা copy করো
   (যেমন: `narratives-sheets@narratives-automation.iam.gserviceaccount.com`)
3. তোমার Google Sheet এ যাও
4. "Share" button এ click করো
5. সেই email টা paste করো
6. "Editor" access দাও
7. "Send" করো

---

## 📱 App ব্যবহার করা (4টা Step)

### Step 1: Data Load করো
- **Option A:** Existing Dataset ID দিয়ে
  - তোমার Apify dataset ID দাও
  - "Fetch Dataset" click করো
  
- **Option B:** Apify Task Run করো
  - তোমার Task ID দাও (default দেওয়া আছে)
  - "Run Task" click করো (কয়েক মিনিট লাগবে)

### Step 2: Filter করো
- "Filter Leads" button এ click করো
- Invalid email/website নেই এমন leads বাদ যাবে

### Step 3: Process করো
- কতগুলো lead process করবে সেটা select করো
- "Start Processing" click করো
- Real-time progress দেখতে পাবে

### Step 4: Save করো
- "Save to Google Sheets" click করো
- অথবা CSV download করো

---

## ⏱️ কতক্ষণ লাগবে?

| Leads | Estimated Time |
|-------|---------------|
| 100 | ~10-15 মিনিট |
| 500 | ~45-60 মিনিট |
| 1,000 | ~2 ঘন্টা |
| 14,000 | ~12-15 ঘন্টা |

**Tip:** বড় batch এ কাজ করলে 500-1000 করে process করো।

---

## ❓ Common Problems

### "command not found: python3"
**Solution:** Python install করো:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python3
```

### "Permission denied"
**Solution:**
```bash
chmod +x start.sh
```

### "Google Sheets error"
**Solution:** 
- Service Account email টা Sheet এ share করেছো কিনা check করো
- "Editor" access দিয়েছো কিনা check করো

### App বন্ধ করতে চাইলে
Terminal এ `Ctrl + C` চাপো

---

## 📁 Files

```
narratives_app/
├── app.py           ← Main app
├── requirements.txt ← Dependencies
├── start.sh         ← Startup script
└── README.md        ← এই file
```

---

## 💬 Help দরকার?

কোনো সমস্যা হলে আমাকে জানাও, আমি সাহায্য করবো!

---

🎬 Happy Prospecting!
