from os.path import isfile, isdir, join
from flask import Flask, render_template, request, redirect, url_for, session, abort, jsonify  
from flask import send_from_directory
import sqlite3
import pyotp
import qrcode
import hashlib
import shutil
import tempfile
import zipfile
from werkzeug.utils import secure_filename
import datetime
import os

UPLOAD_FOLDER = "/media/kasper/server/Drev"  # Her er siten til vores SSD harddisk
app = Flask(__name__)
app.secret_key = b'_5#y2L"F4Q8z\n\xec]/' 

# Her opretter vi forbindelse til vores file_viewer.db (Database)
conn = sqlite3.connect('file_viewer.db', check_same_thread=False)
cursor = conn.cursor()

# Der oprette en brugertabel med id, username, password, totp_key
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    totp_key TEXT
);
''')
conn.commit()


# Her har vi en funktion til at logge login tidspunktet og gemme det i en database
def log_login(username):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") # Her henter vi hvad tiden er nu
    cursor.execute("INSERT INTO login_logs (username, login_time) VALUES (?, ?)", (username, timestamp)) 
    conn.commit()


# Her har vi en funktion som indsætter den nye bruger i databsen
def create_user(username, password):
    totp_key = pyotp.random_base32() # Her laver vi en tilfældig 2FA kode til brugeren
    hashed_password = hash_password(password) # Her hasher vi passwordet på den nye bruger
    cursor.execute("INSERT INTO users (username, password, totp_key) VALUES (?, ?, ?)", (username, hashed_password, totp_key))
    conn.commit()
    return totp_key

# Her har vi en funktion der hasher vores password med SHA256
def hash_password(password):
    salt = b'73a2b5f9c8e4d7a1'
    return hashlib.sha256(salt + password.encode()).hexdigest()

# Her har vi en Funktion til at lave en qr kode og så gemme qr koden til 2FA
def generate_and_save_qr(username, totp_key):
    totp_auth_uri = pyotp.totp.TOTP(totp_key).provisioning_uri(name=username, issuer_name='4-semester')
    img_path = f"static/{username}_qr.png" # Stien til hvor vores qr billede skal gemmes
    qrcode.make(totp_auth_uri).save(img_path)
    return img_path

# Funktion til at bekæfte om adgangskoden stemmer
def verify_password(username, password):
    cursor.execute("SELECT password FROM users WHERE username=?", (username,))
    stored_password = cursor.fetchone()
    if stored_password:
        hashed_password = hash_password(password)
        return hashed_password == stored_password[0]
    return False

# Funktion til at bekæfte om 2FA koden stemmer
def verify_totp(username, code):
    cursor.execute("SELECT totp_key FROM users WHERE username=?", (username,))
    totp_key = cursor.fetchone()
    if totp_key:
        return pyotp.TOTP(totp_key[0]).verify(code)
    return False

# Her har vi en funktion som vi bruger til at hente de mapper og filer som ligger på stien (SSD harddisken)
def get_desktop_content(username):
    desktop_path = "/media/kasper/server/Drev"  # Stien til vores SSD harddisk
    folders = []
    files = []
    
    allowed_folders = ["Filer", "Interne"]  # Her vælger vi de mapper som kun "test1" må se. 
    
    for item in os.listdir(desktop_path):
        item_path = join(desktop_path, item)
        if isdir(item_path):
            if username == "test" or (username == "test1" and item in allowed_folders):
                folders.append(item)
        elif isfile(item_path):
            if username == "test" or (username == "test1" and any(folder in item_path for folder in allowed_folders)):
                files.append(item)
    return folders, files

# Vores funktion til at udpakke zip filerne
def extract_zip(zip_file, destination):
    with zipfile.ZipFile(zip_file, 'r') as zip_ref:
        zip_ref.extractall(destination)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['POST'])
def signup():
    username = request.form['username']
    password = request.form['password']
    if not (username and password):
        return "Both username and password are required."
    try:
        totp_key = create_user(username, password)
        img_path = generate_and_save_qr(username, totp_key)
        return render_template('signup_success.html', username=username, img_path=img_path)
    except sqlite3.IntegrityError:
        error = "Bruger findes allerede"
        return render_template('index.html', error_signup=error)  

@app.route('/get_tfa_code', methods=['GET'])
def get_tfa_code():
    username = "test"
    cursor.execute("SELECT totp_key FROM users WHERE username=?", (username,))
    totp_key = cursor.fetchone()
    if totp_key:
        totp = pyotp.TOTP(totp_key[0])
        tfa_code = totp.now()
        return jsonify({"tfa_code": tfa_code})
    else:
        return jsonify({"error": "2FA kode ikke fundet"}), 404

@app.route('/get_tfa_code1', methods=['GET'])
def get_tfa_code1():
    username = "test1"
    cursor.execute("SELECT totp_key FROM users WHERE username=?", (username,))
    totp_key = cursor.fetchone()
    if totp_key:
        totp = pyotp.TOTP(totp_key[0])
        tfa_code = totp.now()
        return jsonify({"tfa_code": tfa_code})
    else:
        return jsonify({"error": "2FA kode ikke fundet"}), 404


@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    
    # Tjekker brugernavn og adgangskode
    if verify_password(username, password):
        # Gem brugernavn i session, så man kan se på hjemmesiden, hvem der er logget ind
        session['username'] = username
        
        return render_template('2fa.html')
    
    # Hvis adgangskoden er forkert, kommer der en fejlbesked
    error_login = "Brugernavn eller kodeord er forkert, prøv igen"
    return render_template('index.html', error_login=error_login)  


@app.route('/verify_2fa', methods=['POST'])
def verify_2fa():
    code = request.form['code']
    username = session.get('username')
    
    # Her tjekker vi om 2FA koden er gyldig
    if verify_totp(username, code):
        # Her logger vi brugerens login i vores log_db.db 
        log_login(username)
        
        session['logged_in'] = True  
        return redirect(url_for('loggedin'))  # Her vidersender vi brugeren til vores loggedin side.
    
    # Hvis 2FA-koden er forkert, kommer der en fejlbesked
    error = "Forkert 2FA kode."
    return render_template('2fa.html', error=error)

def log_login(username):

    # Vi opretter forbindelse til vores log_db
    log_conn = sqlite3.connect('log_db.db')
    log_cursor = log_conn.cursor()

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Oplysninger bliver logget når en bruger logger ind. 
    log_cursor.execute("INSERT INTO login_logs (username, login_time) VALUES (?, ?)", (username, timestamp))
    log_conn.commit()

    log_conn.close()


@app.route('/loggedin')
def loggedin():
    if session.get('logged_in'):
        folders, files = get_desktop_content(session['username'])
        return render_template('loggedin.html', username=session['username'], folders=folders, files=files)
    else:
        return redirect(url_for('index'))  

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    return redirect(url_for('index'))  # Man kommer tilbage til forsiden ved tryk på logud

@app.route('/download/<path:filename>')
def download_file(filename):
    directory = "/media/kasper/server/Drev"  
    return send_from_directory(directory, filename, as_attachment=True)

@app.route('/folder/<path:folder_name>')
def show_folder_content(folder_name):
    directory = "/media/kasper/server/Drev"  
    folder_path = join(directory, folder_name)
    if isdir(folder_path):
        folders = [f for f in os.listdir(folder_path) if isdir(join(folder_path, f))]
        files = [f for f in os.listdir(folder_path) if isfile(join(folder_path, f))]
        return render_template('folder_content.html', username=session['username'], current_folder=folder_name, folders=folders, files=files)
    else:
        abort(404)

@app.route('/upload/<path:folder_name>', methods=['POST'])
def upload_file(folder_name):
    folder_path = join(UPLOAD_FOLDER, folder_name)
    if not isdir(folder_path):
        abort(404)
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    if file:
        filename = secure_filename(file.filename)
        file.save(join(folder_path, filename))
        return redirect(url_for('show_folder_content', folder_name=folder_name))

@app.route('/upload_folder/<path:folder_name>', methods=['POST'])
def upload_folder(folder_name):
    folder_path = os.path.join(UPLOAD_FOLDER, folder_name)
    if not os.path.isdir(folder_path):
        os.makedirs(folder_path)

    files = request.files.getlist('files[]')
    for file in files:
        if file.filename == '':
            continue
        file.save(os.path.join(folder_path, secure_filename(file.filename)))

    return {'message': 'Mappe er blevet uploaded'}

@app.route('/upload_zip/<path:folder_name>', methods=['POST'])
def upload_zip(folder_name):
    folder_path = join(UPLOAD_FOLDER, folder_name)
    if not isdir(folder_path):
        abort(404)
    if 'zip_file' not in request.files:
        return redirect(request.url)
    zip_file = request.files['zip_file']
    if zip_file.filename == '':
        return redirect(request.url)
    if zip_file:
        zip_filename = secure_filename(zip_file.filename)
        zip_file_path = join(folder_path, zip_filename)
        zip_file.save(zip_file_path)
        extract_zip(zip_file_path, folder_path)
        os.remove(zip_file_path)
        return redirect(url_for('show_folder_content', folder_name=folder_name))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
