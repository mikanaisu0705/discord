import os
import json
import requests
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'super_secret_key_for_flask_session')

# RenderなどのHTTPS/プロキシ環境でセッション(Cookie)を正常に機能させる設定
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.config['SESSION_COOKIE_SECURE'] = True      # HTTPS通信でのみCookieを保持
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'   # 外部サイト(Discord)からのリダイレクト時にCookieを維持

CONFIG_FILE = 'config.json'

CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')

def load_config():
    default_config = {
        "spam_interval": 3,
        "spam_threshold": 5,
        "account_age_days": 7,
        "check_default_avatar": True,
        "banned_words": "荒らし, たかし, test_bad_word",
        "log_channel_id": "",
        "auto_punish": "timeout",
        "timeout_minutes": 10
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return {**default_config, **json.load(f)}
        except Exception:
            pass
    return default_config

def save_config(data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

@app.route('/')
def index():
    user = session.get('user')
    guilds = session.get('guilds', [])
    
    # 管理者権限(8)またはサーバー管理権限(32)を持つサーバーのみ抽出
    admin_guilds = []
    if isinstance(guilds, list):
        for g in guilds:
            permissions = int(g.get('permissions', 0))
            if (permissions & 0x8) == 0x8 or (permissions & 0x20) == 0x20:
                admin_guilds.append(g)

    config = load_config()
    return render_template('dashboard.html', user=user, guilds=admin_guilds, config=config, saved=request.args.get('saved'))

@app.route('/login')
def login():
    discord_login_url = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds"
    return redirect(discord_login_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return redirect(url_for('index'))

    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    r = requests.post('https://discord.com/api/oauth2/token', data=data, headers=headers)
    token_data = r.json()
    access_token = token_data.get('access_token')

    if access_token:
        headers_auth = {'Authorization': f'Bearer {access_token}'}
        
        # ユーザー情報の取得
        user_r = requests.get('https://discord.com/api/users/@me', headers=headers_auth)
        if user_r.status_code == 200:
            session['user'] = user_r.json()
        
        # 参加サーバー一覧の取得
        guilds_r = requests.get('https://discord.com/api/users/@me/guilds', headers=headers_auth)
        if guilds_r.status_code == 200:
            session['guilds'] = guilds_r.json()

        # セッションの保存を明示的に指定
        session.modified = True

    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    session.pop('guilds', None)
    return redirect(url_for('index'))

@app.route('/save', methods=['POST'])
def save_settings():
    try:
        new_config = {
            "spam_interval": int(request.form.get('spam_interval', 3)),
            "spam_threshold": int(request.form.get('spam_threshold', 5)),
            "account_age_days": int(request.form.get('account_age_days', 7)),
            "check_default_avatar": 'check_default_avatar' in request.form,
            "banned_words": request.form.get('banned_words', ''),
            "log_channel_id": request.form.get('log_channel_id', '').strip(),
            "auto_punish": request.form.get('auto_punish', 'timeout'),
            "timeout_minutes": int(request.form.get('timeout_minutes', 10))
        }
        save_config(new_config)
    except Exception as e:
        print(f"❌ 保存エラー: {e}")
        
    return redirect(url_for('index', saved='true'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
