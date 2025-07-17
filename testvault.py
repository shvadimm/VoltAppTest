from flask import Flask, render_template_string, request, redirect, url_for, session
import sqlite3
import hvac
import os
from dotenv import load_dotenv
import pyotp
import random
from datetime import datetime, timedelta
import qrcode
import io
import base64

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret")

def get_db_secrets():
    load_dotenv()
    vault_url = os.getenv("VAULT_URL")
    vault_token = os.getenv("VAULT_TOKEN")
    if not vault_url or not vault_token:
        raise RuntimeError("VAULT_URL ou VAULT_TOKEN manquant dans le .env")
    client = hvac.Client(
        url=vault_url,
        token=vault_token
    )
    secret = client.secrets.kv.read_secret_version(path='db')
    data = secret['data']['data']
    return data

def connect_to_database():
    try:
        secrets = get_db_secrets()
        conn = sqlite3.connect(secrets.get('db_path', 'ma_base.db'))
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"Erreur de connexion à Vault ou à la base : {e}")
        # Optionnel : tu peux lever l'exception pour la remonter à Flask
        raise

# --- DB Migration: Ajout des colonnes si besoin ---
def migrate_db():
    conn = connect_to_database()
    if conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(utilisateurs)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'password' not in columns:
            try:
                cursor.execute("ALTER TABLE utilisateurs ADD COLUMN password TEXT")
            except Exception as e:
                print("Erreur migration password:", e)
        if 'totp_secret' not in columns:
            cursor.execute("ALTER TABLE utilisateurs ADD COLUMN totp_secret TEXT")
        if 'last_login' not in columns:
            cursor.execute("ALTER TABLE utilisateurs ADD COLUMN last_login TIMESTAMP")
        conn.commit()
        conn.close()

# --- Captcha utils ---
def generate_captcha():
    a, b = random.randint(1, 10), random.randint(1, 10)
    session['captcha_answer'] = a + b
    return f"{a} + {b} = ?"

def check_captcha(user_answer):
    try:
        return int(user_answer) == session.get('captcha_answer')
    except Exception:
        return False

# --- Login form ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        totp_code = request.form['totp']
        captcha = request.form['captcha']
        conn = connect_to_database()
        if conn:
            cursor = conn.cursor()
            user = cursor.execute("SELECT * FROM utilisateurs WHERE nom = ?", (username,)).fetchone()
            if not user:
                error = "Utilisateur inconnu."
            elif user['totp_secret'] is None:
                secret = pyotp.random_base32()
                cursor.execute("UPDATE utilisateurs SET totp_secret = ? WHERE id = ?", (secret, user['id']))
                conn.commit()
                error = f"Votre secret TOTP (à scanner dans Google Authenticator) : {secret}"
            elif user['password'] != password:
                error = "Mot de passe incorrect."
            elif not check_captcha(captcha):
                error = "Captcha incorrect."
            else:
                totp = pyotp.TOTP(user['totp_secret'])
                if not totp.verify(totp_code):
                    error = "Code TOTP invalide."
                else:
                    # Connexion OK, on met à jour last_login
                    cursor.execute("UPDATE utilisateurs SET last_login = ? WHERE id = ?", (datetime.now(), user['id']))
                    conn.commit()
                    conn.close()
                    session['user'] = username
                    return redirect(url_for('index'))
            conn.close()
        # --> Ajoute cette ligne pour régénérer le captcha après une erreur POST
        captcha_question = generate_captcha()
    else:
        captcha_question = generate_captcha()
    return render_template_string(login_template, error=error, captcha_question=captcha_question)

login_template = """
<!DOCTYPE html>
<html>
<head>
    <title>Login</title>
    <style>
        body { background: #f7f7f7; font-family: Arial, sans-serif; }
        .login-container {
            background: #fff;
            max-width: 400px;
            margin: 60px auto;
            padding: 30px 40px;
            border-radius: 10px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.08);
        }
        h2 { text-align: center; color: #333; }
        label { display: block; margin: 15px 0 5px; color: #444; }
        input { width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
        button { width: 100%; background: #007bff; color: #fff; border: none; padding: 10px; border-radius: 4px; margin-top: 20px; font-size: 16px; cursor: pointer; }
        button:hover { background: #0056b3; }
        .error { color: #c00; text-align: center; margin-bottom: 10px; }
        .register-link { text-align: center; margin-top: 15px; }
        .register-link a { color: #007bff; text-decoration: none; }
        .register-link a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="login-container">
        <h2>Connexion</h2>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="post">
            <label>Nom d'utilisateur:</label>
            <input name="username" required>
            <label>Mot de passe:</label>
            <input name="password" type="password" required>
            <label>Code TOTP:</label>
            <input name="totp" required>
            <label>Captcha: {{ captcha_question }}</label>
            <input name="captcha" required>
            <button type="submit">Connexion</button>
        </form>
        <div class="register-link">
            Pas de compte ? <a href="{{ url_for('register') }}">Créer un compte</a>
        </div>
    </div>
</body>
</html>
"""

# --- Gestion des comptes obsolètes ---
# À chaque connexion réussie, on met à jour le champ last_login de l'utilisateur avec la date/heure actuelle.
# Une route /obsolete permet d'afficher tous les comptes dont last_login est NULL (jamais connecté)
# ou plus ancien que 6 mois, afin d'identifier les comptes inactifs (obsolètes).

# --- Comptes obsolètes ---
@app.route('/obsolete')
def obsolete():
    conn = connect_to_database()
    if not conn:
        return "Erreur de connexion à la base de données"
    cursor = conn.cursor()
    # On calcule la date il y a 6 mois
    six_months_ago = datetime.now() - timedelta(days=180)
    # On sélectionne les utilisateurs inactifs depuis plus de 6 mois ou jamais connectés
    users = cursor.execute(
        "SELECT * FROM utilisateurs WHERE last_login IS NULL OR last_login < ?",
        (six_months_ago,)
    ).fetchall()
    conn.close()
    return render_template_string(obsolete_template, users=users)

obsolete_template = """
<!DOCTYPE html>
<html>
<head><title>Comptes obsolètes</title></head>
<body>
    <h2>Comptes obsolètes (inactifs depuis > 6 mois)</h2>
    <table border="1">
        <tr><th>ID</th><th>Nom</th><th>Dernière connexion</th></tr>
        {% for user in users %}
        <tr><td>{{ user['id'] }}</td><td>{{ user['nom'] }}</td><td>{{ user['last_login'] }}</td></tr>
        {% endfor %}
    </table>
</body>
</html>
"""

# --- Register form ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    qr_img = None
    secret = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = connect_to_database()
        if conn:
            cursor = conn.cursor()
            # Vérifie si l'utilisateur existe déjà
            user = cursor.execute("SELECT * FROM utilisateurs WHERE nom = ?", (username,)).fetchone()
            if user:
                error = "Utilisateur déjà existant."
            else:
                # Génère le secret TOTP
                secret = pyotp.random_base32()
                cursor.execute("INSERT INTO utilisateurs (nom, password, totp_secret) VALUES (?, ?, ?)", (username, password, secret))
                conn.commit()
                # Génère l'URI pour Google Authenticator
                totp = pyotp.TOTP(secret)
                uri = totp.provisioning_uri(name=username, issuer_name="VoltAppTest")
                # Génère le QR code
                img = qrcode.make(uri)
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                qr_img = base64.b64encode(buf.getvalue()).decode('utf-8')
            conn.close()
    return render_template_string(register_template, error=error, qr_img=qr_img, secret=secret)

register_template = """
<!DOCTYPE html>
<html>
<head>
    <title>Register</title>
    <style>
        body { background: #f7f7f7; font-family: Arial, sans-serif; }
        .register-container {
            background: #fff;
            max-width: 400px;
            margin: 60px auto;
            padding: 30px 40px;
            border-radius: 10px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.08);
        }
        h2 { text-align: center; color: #333; }
        label { display: block; margin: 15px 0 5px; color: #444; }
        input { width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
        button { width: 100%; background: #28a745; color: #fff; border: none; padding: 10px; border-radius: 4px; margin-top: 20px; font-size: 16px; cursor: pointer; }
        button:hover { background: #218838; }
        .error { color: #c00; text-align: center; margin-bottom: 10px; }
        .qr-section { text-align: center; margin-top: 20px; }
        .login-link { text-align: center; margin-top: 15px; }
        .login-link a { color: #007bff; text-decoration: none; }
        .login-link a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="register-container">
        <h2>Créer un compte</h2>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="post">
            <label>Nom d'utilisateur:</label>
            <input name="username" required>
            <label>Mot de passe:</label>
            <input name="password" type="password" required>
            <button type="submit">Créer le compte</button>
        </form>
        {% if qr_img %}
            <div class="qr-section">
                <h3>Scanne ce QR code avec Google Authenticator ou FreeOTP</h3>
                <img src="data:image/png;base64,{{ qr_img }}">
                <p>Ou entre ce secret manuellement : <b>{{ secret }}</b></p>
            </div>
        {% endif %}
        <div class="login-link">
            Déjà un compte ? <a href="{{ url_for('login') }}">Se connecter</a>
        </div>
    </div>
</body>
</html>
"""

# --- Index: migration auto au démarrage ---
@app.before_request
def before_request():
    if not hasattr(app, '_db_migrated'):
        migrate_db()
        app._db_migrated = True


@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = connect_to_database()
    if conn:
        try:
            cursor = conn.cursor()
            users = cursor.execute("SELECT * FROM utilisateurs").fetchall()
            books = cursor.execute("SELECT * FROM books").fetchall()
            return render_template_string(template, users=users, books=books)
        except Exception as e:
            return f"Erreur : {str(e)}"
        finally:
            conn.close()
    return "Erreur de connexion à la base de données"

template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Bibliothèque</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        .container {
            display: flex;
            gap: 40px;
        }
        .section {
            flex: 1;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 10px;
            border: 1px solid #ddd;
            text-align: left;
        }
        th {
            background-color: #f4f4f4;
        }
        h2 {
            color: #333;
        }
        .logout-btn {
            position: absolute;
            top: 20px;
            right: 30px;
            background: #dc3545;
            color: #fff;
            border: none;
            padding: 8px 18px;
            border-radius: 5px;
            font-size: 15px;
            cursor: pointer;
        }
        .logout-btn:hover {
            background: #b52a37;
        }
    </style>
</head>
<body>
    <form action="{{ url_for('logout') }}" method="get" style="display:inline;">
        <button class="logout-btn" type="submit">Déconnexion</button>
    </form>
    <form action="{{ url_for('obsolete') }}" method="get" style="display:inline; position:absolute; top:20px; right:170px;">
        <button style="background:#ffc107; color:#333; border:none; padding:8px 18px; border-radius:5px; font-size:15px; cursor:pointer;" type="submit">Comptes obsolètes</button>
    </form>
    <h1>Bibliothèque</h1>
    
    <div class="container">
        <div class="section">
            <h2>Liste des Utilisateurs</h2>
            <table>
                <tr>
                    <th>ID</th>
                    <th>Nom</th>
                </tr>
                {% for user in users %}
                <tr>
                    <td>{{ user[0] }}</td>
                    <td>{{ user[1] }}</td>
                </tr>
                {% endfor %}
            </table>
        </div>

        <div class="section">
            <h2>Liste des Livres</h2>
            <table>
                <tr>
                    <th>ID</th>
                    <th>Titre</th>
                    <th>Auteur</th>
                </tr>
                {% for book in books %}
                <tr>
                    <td>{{ book[0] }}</td>
                    <td>{{ book[1] }}</td>
                    <td>{{ book[2] }}</td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>
</body>
</html>
"""

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    # Configuration initiale de Vault
    try:
        client = hvac.Client(
            url='http://127.0.0.1:8200',
            token=os.getenv("VAULT_TOKEN")
        )
        
        # Créer ou mettre à jour le secret
        client.secrets.kv.v2.create_or_update_secret(
            path='db',
            secret=dict(
                db_path='ma_base.db'
            )
        )
    except Exception as e:
        print(f"Erreur lors de la configuration de Vault : {e}")

    app.run(debug=True)