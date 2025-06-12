from flask import Flask, render_template_string
import sqlite3
import hvac
import os
from dotenv import load_dotenv

app = Flask(__name__)

def get_db_secrets():
    load_dotenv()
    client = hvac.Client(
        url='http://127.0.0.1:8200',
        token=os.getenv("VAULT_TOKEN")
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
        print(f"Erreur de connexion : {e}")
        return None

# Le reste de votre code template HTML reste identique...

@app.route('/')
def index():
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
    </style>
</head>
<body>
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

    # Le reste de votre code d'initialisation DB...
    app.run(debug=True)