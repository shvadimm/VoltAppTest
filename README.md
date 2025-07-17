# VaultAppTest

Application Flask avec authentification double facteur (TOTP), captcha, gestion des comptes obsolètes et stockage sécurisé du chemin de la base dans Vault.

---

## Prérequis

- Python 3.7+
- `pip`
- [HashiCorp Vault](https://developer.hashicorp.com/vault/downloads)
- (Optionnel) [sqlite3](https://www.sqlite.org/download.html) pour manipuler la base à la main

---

## Installation

> ⚠️ **Important** : Si tu as cloné le projet et qu’il y a un dossier `venv/` (inclus par erreur dans le repo), il faut le supprimer avant de créer ton propre environnement virtuel :
>
> ```bash
> rm -rf venv
> ```
>
> Ensuite, crée ton venv local comme indiqué ci-dessous.

1. **Cloner le projet**
   ```bash
   git clone <url-du-repo>
   cd VoltAppTest
   ```

2. **Créer et activer un environnement virtuel**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
   > **N’oublie pas d’activer le venv** (`source venv/bin/activate`) **avant d’installer les requirements !**

3. **Installer les dépendances**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurer le fichier `.env`**
   Crée un fichier `.env` à la racine avec :
   ```env
   VAULT_URL=http://127.0.0.1:8200
   VAULT_TOKEN=<ton_token_vault>
   ```

5. **Démarrer Vault en mode dev**
   ```bash
   vault server -dev
   ```
   Note le token affiché au démarrage et mets-le dans `.env`.

6. **Initialiser le secret du chemin de la base dans Vault**
   ```bash
   export VAULT_ADDR=http://127.0.0.1:8200
   export VAULT_TOKEN=<ton_token_vault>
   vault kv put secret/db db_path="ma_base.db"
   ```

7. **Initialiser la base SQLite**
   (Optionnel, mais recommandé pour la première fois)
   ```bash
   sqlite3 ma_base.db < init_db.sql
   ```
   Sinon, la base et les colonnes seront créées automatiquement au lancement de l'app.

---

## Lancement de l'application

```bash
python testvault.py
```

- Accède à [http://localhost:5000](http://localhost:5000)
- Tu seras redirigé vers la page de connexion.

---

## Fonctionnalités principales

- **Inscription** : Génère un secret TOTP et un QR code à scanner dans Google Authenticator/FreeOTP.
- **Connexion** : Mot de passe + code TOTP + captcha.
- **Déconnexion** : Bouton sur le dashboard.
- **Comptes obsolètes** : Bouton sur le dashboard pour voir les comptes inactifs depuis plus de 6 mois.
- **Migration automatique** : Les colonnes manquantes sont ajoutées à la base au lancement.

---

## Conseils

- En production, stocke le secret TOTP dans Vault ou chiffre-le.
- Pour réinitialiser la base, supprime `ma_base.db` et relance l'init.

---

## Dépendances principales
- Flask
- pyotp
- qrcode[pil]
- hvac
- python-dotenv

---

## Aide

Si tu rencontres un problème, vérifie :
- Que Vault est bien lancé et accessible
- Que le token Vault est correct
- Que le venv est activé
- Que les dépendances sont installées
