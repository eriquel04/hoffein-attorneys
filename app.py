from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    send_from_directory,
    flash
)

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import mysql.connector
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

try:
    from authlib.integrations.flask_client import OAuth
except ImportError:
    OAuth = None


# =========================================================
# APPLICATION
# =========================================================

app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET_KEY")

if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY must be configured in .env")

oauth = OAuth(app) if OAuth else None
google = None

if oauth:
    google = oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url=(
            "https://accounts.google.com/.well-known/openid-configuration"
        ),
        client_kwargs={"scope": "openid email profile"}
    )


# =========================================================
# MYSQL DATABASE
# =========================================================

DB_CONFIG = {
    "host": os.getenv("DB_HOST") or os.getenv("MYSQLHOST", "localhost"),
    "user": os.getenv("DB_USER") or os.getenv("MYSQLUSER", "root"),
    "password": os.getenv("DB_PASSWORD") or os.getenv("MYSQLPASSWORD", ""),
    "database": os.getenv("DB_NAME") or os.getenv("MYSQLDATABASE", "hoffein_attorneys"),
    "port": int(os.getenv("DB_PORT") or os.getenv("MYSQLPORT", "3306"))
}


def get_db_connection():

    return mysql.connector.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        port=DB_CONFIG["port"]
    )


def ensure_organization_tables():

    db = get_db_connection()
    cursor = db.cursor()

    cursor.execute("SHOW COLUMNS FROM users")
    user_columns = {row[0] for row in cursor.fetchall()}

    if "client_id" not in user_columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN client_id VARCHAR(24) NULL UNIQUE AFTER id"
        )

    cursor.execute(
        "SELECT id FROM users WHERE role = 'client' AND (client_id IS NULL OR client_id = '')"
    )
    clients_without_id = cursor.fetchall()

    for client in clients_without_id:
        cursor.execute(
            "UPDATE users SET client_id = %s WHERE id = %s",
            (generate_client_id(), client[0])
        )

    cursor.execute("SHOW COLUMNS FROM appointments")
    appointment_columns = {row[0] for row in cursor.fetchall()}

    if "case_id" not in appointment_columns:
        cursor.execute(
            "ALTER TABLE appointments ADD COLUMN case_id INT NULL AFTER id"
        )

    if "requested_by" not in appointment_columns:
        cursor.execute(
            "ALTER TABLE appointments ADD COLUMN requested_by INT NULL AFTER lawyer_id"
        )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            case_id INT NOT NULL,
            sender_id INT NOT NULL,
            recipient_id INT NOT NULL,
            body TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            read_at DATETIME NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS document_requests (
            id INT AUTO_INCREMENT PRIMARY KEY,
            case_id INT NOT NULL,
            client_id INT NOT NULL,
            requested_by INT NOT NULL,
            title VARCHAR(160) NOT NULL,
            instructions TEXT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'Pending',
            fulfilled_document_id INT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS legal_service_requests (
            id INT AUTO_INCREMENT PRIMARY KEY,
            client_id INT NOT NULL,
            problem TEXT NOT NULL,
            practice_area VARCHAR(100) NOT NULL,
            urgency VARCHAR(30) NOT NULL DEFAULT 'Normal',
            attachment_name VARCHAR(255) NULL,
            attachment_path VARCHAR(255) NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'Submitted',
            reviewed_by INT NULL,
            case_id INT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at DATETIME NULL
        )
        """
    )

    db.commit()
    cursor.close()
    db.close()


def generate_client_id():

    return f"HOF-CL-{uuid.uuid4().hex[:8].upper()}"


# =========================================================
# FILE UPLOAD SETTINGS
# =========================================================

UPLOAD_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "uploads"
)

ALLOWED_EXTENSIONS = {
    "pdf",
    "png",
    "jpg",
    "jpeg",
    "doc",
    "docx"
}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

app.config["MAX_CONTENT_LENGTH"] = (
    10 * 1024 * 1024
)

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


# =========================================================
# CREATE TEST ACCOUNTS
# =========================================================

def create_test_accounts():

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    test_accounts = [
        {
            "full_name": "Test Lawyer",
            "email": os.getenv("TEST_LAWYER_EMAIL", "lawyer@hoffein.com"),
            "password": os.getenv("TEST_LAWYER_PASSWORD", ""),
            "role": "lawyer"
        },
        {
            "full_name": "Test Client",
            "email": os.getenv("TEST_CLIENT_EMAIL", "client@hoffein.com"),
            "password": os.getenv("TEST_CLIENT_PASSWORD", ""),
            "role": "client"
        }
    ]

    test_accounts = [
        account for account in test_accounts
        if account["password"]
    ]

    for account in test_accounts:

        cursor.execute(
            """
            SELECT id
            FROM users
            WHERE email = %s
            """,
            (account["email"],)
        )

        existing = cursor.fetchone()

        if not existing:

            password_hash = generate_password_hash(
                account["password"]
            )

            client_id = generate_client_id() if account["role"] == "client" else None

            cursor.execute(
                """
                INSERT INTO users
                (
                    full_name,
                    email,
                    password_hash,
                    role,
                    client_id
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    account["full_name"],
                    account["email"],
                    password_hash,
                    account["role"],
                    client_id
                )
            )

    db.commit()

    cursor.close()
    db.close()


# =========================================================
# CREATE LAWYER PROFILE
# =========================================================

def create_lawyer_profile():

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT id
        FROM users
        WHERE email = %s
        """,
        (os.getenv("TEST_LAWYER_EMAIL", "lawyer@hoffein.com"),)
    )

    lawyer_user = cursor.fetchone()

    if lawyer_user:

        cursor.execute(
            """
            SELECT id
            FROM lawyers
            WHERE user_id = %s
            """,
            (lawyer_user["id"],)
        )

        lawyer_profile = cursor.fetchone()

        if not lawyer_profile:

            cursor.execute(
                """
                INSERT INTO lawyers
                (
                    user_id
                )
                VALUES
                (
                    %s
                )
                """,
                (lawyer_user["id"],)
            )

    db.commit()

    cursor.close()
    db.close()


# =========================================================
# GET LAWYERS
# =========================================================

def get_all_lawyers():

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            l.id,
            l.user_id,
            u.full_name,
            u.email,
            l.specialization

        FROM lawyers l

        INNER JOIN users u
            ON l.user_id = u.id

        WHERE u.role = 'lawyer'

        ORDER BY u.full_name ASC
        """
    )

    lawyers = cursor.fetchall()

    cursor.close()
    db.close()

    return lawyers


def get_lawyer_by_search(search_value):

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            l.id,
            l.user_id,
            u.full_name,
            u.email,
            u.phone,
            l.specialization,
            COUNT(c.id) AS assigned_cases
        FROM lawyers l
        INNER JOIN users u ON l.user_id = u.id
        LEFT JOIN cases c ON c.lawyer_id = l.id
          WHERE CAST(l.id AS CHAR) = %s
              OR u.full_name LIKE %s
              OR LOWER(u.email) = LOWER(%s)
          AND u.role = 'lawyer'
        GROUP BY l.id, l.user_id, u.full_name, u.email, u.phone, l.specialization
        LIMIT 1
        """,
        (search_value, f"%{search_value}%", search_value)
    )
    lawyer = cursor.fetchone()
    cursor.close()
    db.close()
    return lawyer


# =========================================================
# GET CLIENTS
# =========================================================

def get_all_clients():

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            id,
            client_id,
            full_name,
            email
        FROM users
        WHERE role = 'client'
        ORDER BY full_name ASC
        """
    )

    clients = cursor.fetchall()

    cursor.close()
    db.close()

    return clients


def get_client_by_public_id(client_id):

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            id,
            client_id,
            full_name,
            email,
            phone,
            created_at
        FROM users
        WHERE client_id = %s
          AND role = 'client'
        LIMIT 1
        """,
        (client_id,)
    )

    client = cursor.fetchone()
    cursor.close()
    db.close()

    if client:
        client["cases"] = get_client_cases(client["id"])

    return client


def get_case_by_id(case_id):

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            c.id,
            c.case_number,
            c.title,
            c.description,
            c.client_id,
            c.lawyer_id,
            c.status,
            c.created_at,
            cu.full_name AS client_name,
            cu.client_id AS client_public_id,
            lu.full_name AS lawyer_name
        FROM cases c
        INNER JOIN users cu ON c.client_id = cu.id
        LEFT JOIN lawyers l ON c.lawyer_id = l.id
        LEFT JOIN users lu ON l.user_id = lu.id
        WHERE c.id = %s
        LIMIT 1
        """,
        (case_id,)
    )

    case = cursor.fetchone()
    cursor.close()
    db.close()
    return case


def get_documents_for_client_public_id(client_id):

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            d.id,
            d.case_id,
            d.original_filename,
            d.document_type,
            d.status,
            d.uploaded_at,
            c.case_number,
            c.title AS case_title,
            cu.full_name AS client_name,
            u.full_name AS uploader_name
        FROM documents d
        INNER JOIN cases c ON d.case_id = c.id
        INNER JOIN users cu ON c.client_id = cu.id
        INNER JOIN users u ON d.uploaded_by = u.id
        WHERE cu.client_id = %s
        ORDER BY d.uploaded_at DESC
        """,
        (client_id,)
    )
    documents = cursor.fetchall()
    cursor.close()
    db.close()
    return documents


def get_document_requests_for_user(user):

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    query = """
        SELECT
            r.id,
            r.case_id,
            r.client_id,
            r.title,
            r.instructions,
            r.status,
            r.created_at,
            c.case_number,
            c.title AS case_title
        FROM document_requests r
        INNER JOIN cases c ON r.case_id = c.id
        WHERE r.client_id = %s
        ORDER BY r.created_at DESC
    """
    cursor.execute(query, (user["id"],))
    requests = cursor.fetchall()
    cursor.close()
    db.close()
    return requests


def get_legal_service_requests_for_user(user):

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT id, problem, practice_area, urgency, attachment_name,
               status, case_id, created_at, reviewed_at
        FROM legal_service_requests
        WHERE client_id = %s
        ORDER BY created_at DESC
        """,
        (user["id"],)
    )
    requests = cursor.fetchall()
    cursor.close()
    db.close()
    return requests

def get_legal_service_request(request_id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT r.*, u.full_name AS client_name, u.email AS client_email,
               u.client_id AS client_public_id
        FROM legal_service_requests r
        INNER JOIN users u ON r.client_id = u.id
        WHERE r.id = %s
        LIMIT 1
        """,
        (request_id,)
    )
    service_request = cursor.fetchone()
    cursor.close()
    db.close()
    return service_request


@app.route("/client/request-service", methods=["POST"])
def request_legal_service():

    if not role_required("client"):
        return redirect(url_for("login"))

    user = get_current_user()
    problem = request.form.get("problem", "").strip()
    practice_area = request.form.get("practice_area", "").strip()
    urgency = request.form.get("urgency", "Normal").strip()
    attachment = request.files.get("attachment")

    if not problem or not practice_area:
        flash("Describe your legal issue and select a practice area.")
        return redirect(url_for("client_dashboard"))

    attachment_name = None
    attachment_path = None
    if attachment and attachment.filename:
        if not allowed_file(attachment.filename):
            flash("The intake attachment type is not allowed.")
            return redirect(url_for("client_dashboard"))
        attachment_name = secure_filename(attachment.filename)
        attachment_path = f"{uuid.uuid4()}.{attachment_name.rsplit('.', 1)[1].lower()}"
        attachment.save(os.path.join(app.config["UPLOAD_FOLDER"], attachment_path))

    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute(
        """
        INSERT INTO legal_service_requests
        (client_id, problem, practice_area, urgency, attachment_name, attachment_path)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (user["id"], problem, practice_area, urgency, attachment_name, attachment_path)
    )
    db.commit()
    cursor.close()
    db.close()
    flash("Your legal service request was submitted for firm review.")
    return redirect(url_for("client_dashboard"))


def get_appointment_by_id(appointment_id):

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            a.id,
            a.appointment_date AS scheduled_at,
            a.status,
            a.notes,
            a.subject,
            c.case_number,
            c.title AS case_title,
            cu.full_name AS client_name,
            cu.client_id AS client_public_id,
            lu.full_name AS lawyer_name
        FROM appointments a
        LEFT JOIN cases c ON a.case_id = c.id
        INNER JOIN users cu ON a.client_id = cu.id
        INNER JOIN lawyers l ON a.lawyer_id = l.id
        INNER JOIN users lu ON l.user_id = lu.id
        WHERE a.id = %s
        LIMIT 1
        """,
        (appointment_id,)
    )
    appointment = cursor.fetchone()
    cursor.close()
    db.close()
    return appointment


# =========================================================
# GET USER BY EMAIL OR PHONE
# =========================================================

def get_user_by_identifier(identifier):

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            id,
            client_id,
            full_name,
            email,
            phone,
            password_hash,
            role
        FROM users
        WHERE email = %s
           OR phone = %s
              OR client_id = %s
        LIMIT 1
        """,
        (
            identifier,
            identifier,
            identifier
        )
    )

    user = cursor.fetchone()

    cursor.close()
    db.close()

    return user


# =========================================================
# LOGIN STATUS
# =========================================================

def logged_in():

    return "user" in session


# =========================================================
# ROLE CHECK
# =========================================================

def role_required(role):

    return (
        logged_in()
        and session["user"]["role"] == role
    )


# =========================================================
# ALLOWED FILE
# =========================================================

def allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(
            ".",
            1
        )[1].lower() in ALLOWED_EXTENSIONS
    )


# =========================================================
# CURRENT USER
# =========================================================

def get_current_user():

    if not logged_in():

        return None

    return session["user"]


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        identifier = request.form.get(
            "identifier",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        if not identifier or not password:

            return render_template(
                "login.html",
                error="Please enter your email/phone and password."
            )

        user = get_user_by_identifier(
            identifier
        )

        if user:

            password_hash = user.get(
                "password_hash"
            )

            if password_hash:

                try:

                    password_correct = (
                        check_password_hash(
                            password_hash,
                            password
                        )
                    )

                except ValueError:

                    password_correct = False

                if password_correct:

                    session["user"] = {
                        "id": user["id"],
                        "client_id": user.get("client_id"),
                        "name": user["full_name"],
                        "email": user["email"],
                        "role": user["role"]
                    }

                    if user["role"] == "admin":

                        return redirect(
                            url_for(
                                "admin_dashboard"
                            )
                        )

                    elif user["role"] == "lawyer":

                        return redirect(
                            url_for(
                                "lawyer_dashboard"
                            )
                        )

                    elif user["role"] == "client":

                        return redirect(
                            url_for(
                                "client_dashboard"
                            )
                        )

        return render_template(
            "login.html",
            error="Invalid email/phone or password."
        )

    return render_template(
        "login.html",
        success=request.args.get("success")
    )


@app.route("/auth/google")
def google_login():

    if not google or not os.getenv("GOOGLE_CLIENT_ID") or not os.getenv("GOOGLE_CLIENT_SECRET"):

        return render_template(
            "login.html",
            error="Google sign-in is not configured yet. Please use your email and password."
        )

    redirect_uri = url_for(
        "google_callback",
        _external=True
    )

    return google.authorize_redirect(redirect_uri)


@app.route("/auth/google/callback")
def google_callback():

    if not google:

        return redirect(url_for("login"))

    try:
        token = google.authorize_access_token()
        profile = token.get("userinfo")

        if not profile or not profile.get("email"):

            return render_template(
                "login.html",
                error="Google did not return a usable email address."
            )

        email = profile["email"].strip().lower()
        user = get_user_by_identifier(email)

        if not user:

            db = get_db_connection()
            cursor = db.cursor()
            client_id = generate_client_id()

            cursor.execute(
                """
                INSERT INTO users
                (full_name, email, password_hash, role, client_id)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    profile.get("name") or email.split("@")[0],
                    email,
                    generate_password_hash(uuid.uuid4().hex),
                    "client",
                    client_id
                )
            )

            db.commit()
            user_id = cursor.lastrowid
            cursor.close()
            db.close()

            user = {
                "id": user_id,
                "client_id": client_id,
                "full_name": profile.get("name") or email.split("@")[0],
                "email": email,
                "role": "client"
            }

        session["user"] = {
            "id": user["id"],
            "client_id": user.get("client_id"),
            "name": user["full_name"],
            "email": user["email"],
            "role": user["role"]
        }

        return redirect(url_for("client_dashboard"))

    except Exception as error:

        app.logger.exception("Google sign-in callback failed: %s", error)

        return render_template(
            "login.html",
            error="Google sign-in could not be completed. Please try again."
        )


# =========================================================
# REGISTRATION
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if not name or not email or not password:

            return render_template(
                "register.html",
                error="Please complete all fields."
            )

        existing_user = get_user_by_identifier(
            email
        )

        if existing_user:

            return render_template(
                "register.html",
                error="An account with this email already exists."
            )

        password_hash = generate_password_hash(
            password
        )
        client_id = generate_client_id()

        db = get_db_connection()
        cursor = db.cursor()

        try:

            cursor.execute(
                """
                INSERT INTO users
                (
                    full_name,
                    email,
                    phone,
                    password_hash,
                    role,
                    client_id
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    name,
                    email,
                    phone,
                    password_hash,
                    "client",
                    client_id
                )
            )

            db.commit()

        except mysql.connector.Error as error:

            db.rollback()

            cursor.close()
            db.close()

            return render_template(
                "register.html",
                error=f"Registration failed: {error}"
            )

        cursor.close()
        db.close()

        return redirect(
            url_for(
                "login",
                success=f"Account created. Your Client ID is {client_id}."
            )
        )

    return render_template(
        "register.html"
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("home")
    )


@app.route("/profile", methods=["GET", "POST"])
def profile():

    if not logged_in():
        return redirect(url_for("login"))

    user = get_current_user()
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()

        if not full_name:
            cursor.close()
            db.close()
            return render_template(
                "profile.html",
                user=user,
                error="Full name is required."
            )

        cursor.execute(
            """
            UPDATE users
            SET full_name = %s, phone = %s
            WHERE id = %s
            """,
            (full_name, phone, user["id"])
        )
        db.commit()
        user["name"] = full_name
        session["user"] = user
        cursor.close()
        db.close()
        flash("Profile updated successfully.")
        return redirect(url_for("profile"))

    cursor.execute(
        """
        SELECT id, full_name, email, phone, role, created_at
        FROM users
        WHERE id = %s
        """,
        (user["id"],)
    )
    profile_user = cursor.fetchone()
    cursor.close()
    db.close()

    return render_template(
        "profile.html",
        user=user,
        profile_user=profile_user
    )


# =========================================================
# GET CLIENT CASES
# =========================================================

def get_client_cases(client_id):

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            c.id,
            c.case_number,
            c.title,
            c.description,
            c.client_id,
            c.lawyer_id,
            c.status,
            c.created_at,

            u.full_name AS client_name,

            lu.full_name AS lawyer_name

        FROM cases c

        INNER JOIN users u
            ON c.client_id = u.id

        LEFT JOIN lawyers l
            ON c.lawyer_id = l.id

        LEFT JOIN users lu
            ON l.user_id = lu.id

        WHERE c.client_id = %s

        ORDER BY c.created_at DESC
        """,
        (client_id,)
    )

    cases = cursor.fetchall()

    cursor.close()
    db.close()

    return cases


# =========================================================
# GET LAWYER CASES
# =========================================================

def get_lawyer_cases(user_id):

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            c.id,
            c.case_number,
            c.title,
            c.description,
            c.client_id,
            c.lawyer_id,
            c.status,
            c.created_at,

            cu.full_name AS client_name,

            lu.full_name AS lawyer_name

        FROM cases c

        INNER JOIN users cu
            ON c.client_id = cu.id

        INNER JOIN lawyers l
            ON c.lawyer_id = l.id

        INNER JOIN users lu
            ON l.user_id = lu.id

        WHERE l.user_id = %s

        ORDER BY c.created_at DESC
        """,
        (user_id,)
    )

    cases = cursor.fetchall()

    cursor.close()
    db.close()

    return cases


# =========================================================
# GET ALL CASES
# =========================================================

def get_all_cases():

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            c.id,
            c.case_number,
            c.title,
            c.description,
            c.client_id,
            c.lawyer_id,
            c.status,
            c.created_at,

            cu.full_name AS client_name,

            lu.full_name AS lawyer_name

        FROM cases c

        INNER JOIN users cu
            ON c.client_id = cu.id

        LEFT JOIN lawyers l
            ON c.lawyer_id = l.id

        LEFT JOIN users lu
            ON l.user_id = lu.id

        ORDER BY c.created_at DESC
        """
    )

    cases = cursor.fetchall()

    cursor.close()
    db.close()

    return cases


# =========================================================
# GET DOCUMENTS
# =========================================================

def get_documents_for_user(user):

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if user["role"] == "admin":

        cursor.execute(
            """
            SELECT
                d.id,
                d.case_id,
                d.uploaded_by,
                d.original_filename,
                d.stored_filename,
                d.document_type,
                d.status,
                d.uploaded_at,

                c.case_number,
                c.title AS case_title,

                cu.full_name AS client_name,

                u.full_name AS uploader_name

            FROM documents d

            INNER JOIN cases c
                ON d.case_id = c.id

            INNER JOIN users cu
                ON c.client_id = cu.id

            INNER JOIN users u
                ON d.uploaded_by = u.id

            ORDER BY d.uploaded_at DESC
            """
        )

    elif user["role"] == "lawyer":

        cursor.execute(
            """
            SELECT
                d.id,
                d.case_id,
                d.uploaded_by,
                d.original_filename,
                d.stored_filename,
                d.document_type,
                d.status,
                d.uploaded_at,

                c.case_number,
                c.title AS case_title,

                cu.full_name AS client_name,

                u.full_name AS uploader_name

            FROM documents d

            INNER JOIN cases c
                ON d.case_id = c.id

            INNER JOIN users cu
                ON c.client_id = cu.id

            INNER JOIN users u
                ON d.uploaded_by = u.id

            INNER JOIN lawyers l
                ON c.lawyer_id = l.id

            WHERE l.user_id = %s

            ORDER BY d.uploaded_at DESC
            """,
            (user["id"],)
        )

    else:

        cursor.execute(
            """
            SELECT
                d.id,
                d.case_id,
                d.uploaded_by,
                d.original_filename,
                d.stored_filename,
                d.document_type,
                d.status,
                d.uploaded_at,

                c.case_number,
                c.title AS case_title,

                cu.full_name AS client_name,

                u.full_name AS uploader_name

            FROM documents d

            INNER JOIN cases c
                ON d.case_id = c.id

            INNER JOIN users cu
                ON c.client_id = cu.id

            INNER JOIN users u
                ON d.uploaded_by = u.id

            WHERE c.client_id = %s

            ORDER BY d.uploaded_at DESC
            """,
            (user["id"],)
        )

    documents = cursor.fetchall()

    cursor.close()
    db.close()

    return documents


def get_appointments_for_user(user):

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    query = """
         SELECT a.*, a.appointment_date AS scheduled_at,
             c.case_number, c.title AS case_title,
               cu.full_name AS client_name, lu.full_name AS lawyer_name
        FROM appointments a
         LEFT JOIN cases c ON a.case_id = c.id
        INNER JOIN users cu ON a.client_id = cu.id
        INNER JOIN lawyers l ON a.lawyer_id = l.id
        INNER JOIN users lu ON l.user_id = lu.id
        WHERE 1 = 1
    """
    parameters = []

    if user["role"] == "client":
        query += " AND a.client_id = %s"
        parameters.append(user["id"])
    elif user["role"] == "lawyer":
        query += " AND l.user_id = %s"
        parameters.append(user["id"])

    query += " ORDER BY a.appointment_date ASC"
    cursor.execute(query, parameters)
    appointments = cursor.fetchall()
    cursor.close()
    db.close()
    return appointments


def get_messages_for_user(user):

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    query = """
         SELECT m.*, m.receiver_id AS recipient_id, m.message AS body,
             c.case_number, c.title AS case_title,
               su.full_name AS sender_name, ru.full_name AS recipient_name
        FROM messages m
         LEFT JOIN cases c ON m.case_id = c.id
        INNER JOIN users su ON m.sender_id = su.id
         INNER JOIN users ru ON m.receiver_id = ru.id
    """
    parameters = []
    if user["role"] != "admin":
        query += " WHERE m.sender_id = %s OR m.receiver_id = %s"
        parameters = [user["id"], user["id"]]
    query += " ORDER BY m.created_at DESC"
    cursor.execute(query, parameters)
    messages = cursor.fetchall()
    cursor.close()
    db.close()
    return messages


def get_client_recent_activity(documents, messages, appointments):

    activity = []

    for document in documents[:5]:
        activity.append({
            "type": "document",
            "label": "Document activity",
            "text": f"{document['original_filename']} is now {document['status'].lower()}.",
            "created_at": document["uploaded_at"]
        })

    for message in messages[:5]:
        activity.append({
            "type": "message",
            "label": "Message",
            "text": f"New message from {message['sender_name']}.",
            "created_at": message["created_at"]
        })

    for appointment in appointments[:5]:
        activity.append({
            "type": "appointment",
            "label": "Appointment",
            "text": f"Appointment with {appointment['lawyer_name']} is {appointment['status'].lower()}.",
            "created_at": appointment["scheduled_at"]
        })

    return sorted(
        activity,
        key=lambda item: str(item["created_at"] or ""),
        reverse=True
    )[:5]


# =========================================================
# CLIENT DASHBOARD
# =========================================================

@app.route("/client/dashboard")
def client_dashboard():

    if not role_required("client"):

        return redirect(
            url_for("login")
        )

    user = get_current_user()
    service_requests = get_legal_service_requests_for_user(user)

    cases = get_client_cases(
        user["id"]
    )

    documents = get_documents_for_user(
        user
    )
    document_requests = get_document_requests_for_user(user)

    appointments = get_appointments_for_user(user)
    messages = get_messages_for_user(user)
    lawyers = get_all_lawyers()
    pending_requests = [
        document_request
        for document_request in document_requests
        if document_request["status"] == "Pending"
    ]
    recent_activity = get_client_recent_activity(
        documents,
        messages,
        appointments
    )
    next_appointment = appointments[0] if appointments else None
    primary_case = cases[0] if cases else None

    return render_template(
        "client_dashboard.html",
        user=user,
        cases=cases,
        documents=documents,
        document_requests=document_requests,
        appointments=appointments,
        messages=messages,
        lawyers=lawyers,
        pending_requests=pending_requests,
        recent_activity=recent_activity,
        next_appointment=next_appointment,
        primary_case=primary_case
        ,service_requests=service_requests
    )


# =========================================================
# LAWYER DASHBOARD
# =========================================================

@app.route("/lawyer/dashboard")
def lawyer_dashboard():

    if not role_required("lawyer"):

        return redirect(
            url_for("login")
        )

    user = get_current_user()

    cases = get_lawyer_cases(
        user["id"]
    )

    documents = get_documents_for_user(
        user
    )

    appointments = get_appointments_for_user(user)
    messages = get_messages_for_user(user)

    return render_template(
        "lawyer_dashboard.html",
        user=user,
        cases=cases,
        documents=documents,
        appointments=appointments,
        messages=messages
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin/dashboard")
def admin_dashboard():

    if not role_required("admin"):

        return redirect(
            url_for("login")
        )

    user = get_current_user()
    client_search = request.args.get("client_id", "").strip().upper()
    client_result = None
    client_search_error = None
    case_search = request.args.get("case_id", "").strip()
    case_result = None
    case_search_error = None
    document_search = request.args.get("document_client_id", "").strip().upper()
    document_results = []
    document_search_error = None
    lawyer_search = request.args.get("lawyer_id", "").strip()
    lawyer_result = None
    lawyer_search_error = None
    appointment_search = request.args.get("appointment_id", "").strip()
    appointment_result = None
    appointment_search_error = None
    intake_search = request.args.get("intake_id", "").strip()
    intake_result = get_legal_service_request(intake_search) if intake_search.isdigit() else None
    intake_search_error = None
    if intake_search and not intake_result:
        intake_search_error = "No legal service request was found with that ID."

    if client_search:
        client_result = get_client_by_public_id(client_search)
        if not client_result:
            client_search_error = "No client was found with that Client ID."

    if case_search:
        if not case_search.isdigit():
            case_search_error = "Case ID must be a number."
        else:
            case_result = get_case_by_id(int(case_search))
            if not case_result:
                case_search_error = "No case was found with that Case ID."

    if document_search:
        document_results = get_documents_for_client_public_id(document_search)
        if not document_results:
            document_search_error = "No documents were found for that Client ID."

    if lawyer_search:
        lawyer_result = get_lawyer_by_search(lawyer_search)
        if not lawyer_result:
            lawyer_search_error = "No lawyer was found with that ID, name, or email."

    if appointment_search:
        if not appointment_search.isdigit():
            appointment_search_error = "Appointment ID must be a number."
        else:
            appointment_result = get_appointment_by_id(int(appointment_search))
            if not appointment_result:
                appointment_search_error = "No appointment was found with that Appointment ID."

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.close()
    db.close()

    clients = get_all_clients()

    lawyers = get_all_lawyers()

    cases = get_all_cases()
    management_cases = [case_result] if case_result else []

    documents = get_documents_for_user(
        user
    )

    appointments = get_appointments_for_user(user)
    messages = get_messages_for_user(user)

    return render_template(
        "admin_dashboard.html",
        user=user,
        clients=clients,
        lawyers=lawyers,
        cases=cases,
        documents=documents,
        document_requests=[],
        appointments=appointments,
        messages=messages,
        client_result=client_result,
        client_search=client_search,
        client_search_error=client_search_error,
        case_result=case_result,
        case_search=case_search,
        case_search_error=case_search_error,
        management_cases=management_cases,
        document_search=document_search,
        document_results=document_results,
        document_search_error=document_search_error,
        lawyer_search=lawyer_search,
        lawyer_result=lawyer_result,
        lawyer_search_error=lawyer_search_error,
        appointment_search=appointment_search,
        appointment_result=appointment_result,
        appointment_search_error=appointment_search_error
        ,intake_search=intake_search
        ,intake_result=intake_result
        ,intake_search_error=intake_search_error
    )

@app.route("/admin/intake/<int:request_id>/approve", methods=["POST"])
def approve_legal_service_request(request_id):

    if not role_required("admin"):
        return redirect(url_for("login"))

    service_request = get_legal_service_request(request_id)
    if not service_request or service_request["status"] == "Approved":
        flash("That intake request is unavailable.")
        return redirect(url_for("admin_dashboard"))

    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute(
        """
        INSERT INTO cases (case_number, title, description, client_id, status)
        VALUES (%s, %s, %s, %s, 'Pending')
        """,
        (
            f"INTAKE-{datetime.now().year}-{request_id:04d}",
            service_request["practice_area"],
            service_request["problem"],
            service_request["client_id"]
        )
    )
    case_id = cursor.lastrowid
    cursor.execute(
        """
        UPDATE legal_service_requests
        SET status = 'Approved', reviewed_by = %s, case_id = %s, reviewed_at = NOW()
        WHERE id = %s
        """,
        (get_current_user()["id"], case_id, request_id)
    )
    db.commit()
    cursor.close()
    db.close()
    flash("Intake approved and official matter created.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/document-request", methods=["POST"])
def create_document_request():

    if not role_required("admin"):
        return redirect(url_for("login"))

    case_id = request.form.get("request_case_id", "").strip()
    title = request.form.get("request_title", "").strip()
    instructions = request.form.get("request_instructions", "").strip()

    if not case_id or not title:
        flash("Select a case and describe the requested document.")
        return redirect(url_for("admin_dashboard"))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT client_id FROM cases WHERE id = %s", (case_id,))
    case = cursor.fetchone()

    if not case:
        cursor.close()
        db.close()
        flash("Selected case does not exist.")
        return redirect(url_for("admin_dashboard"))

    cursor.execute(
        """
        INSERT INTO document_requests
        (case_id, client_id, requested_by, title, instructions)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (case_id, case["client_id"], get_current_user()["id"], title, instructions)
    )
    db.commit()
    cursor.close()
    db.close()
    flash("Document request sent to the client.")
    return redirect(url_for("admin_dashboard"))


# =========================================================
# ADD LAWYER - ADMIN
# =========================================================

@app.route(
    "/admin/add-lawyer",
    methods=["POST"]
)
def add_lawyer():

    if not role_required("admin"):

        return redirect(
            url_for("login")
        )

    full_name = request.form.get(
        "full_name",
        ""
    ).strip()

    email = request.form.get(
        "email",
        ""
    ).strip().lower()

    password = request.form.get(
        "password",
        ""
    )

    specialization = request.form.get(
        "specialization",
        ""
    ).strip()

    if not full_name or not email or not password:

        flash(
            "Full name, email and password are required."
        )

        return redirect(
            url_for("admin_dashboard")
        )

    existing_user = get_user_by_identifier(
        email
    )

    if existing_user:

        flash(
            "A user with this email already exists."
        )

        return redirect(
            url_for("admin_dashboard")
        )

    password_hash = generate_password_hash(
        password
    )

    db = get_db_connection()
    cursor = db.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO users
            (
                full_name,
                email,
                password_hash,
                role
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                full_name,
                email,
                password_hash,
                "lawyer"
            )
        )

        lawyer_user_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO lawyers
            (
                user_id,
                specialization
            )
            VALUES
            (
                %s,
                %s
            )
            """,
            (
                lawyer_user_id,
                specialization
            )
        )

        db.commit()

        flash(
            "Lawyer account created successfully."
        )

    except mysql.connector.Error as error:

        db.rollback()

        flash(
            f"Could not create lawyer: {error}"
        )

    finally:

        cursor.close()
        db.close()

    return redirect(
        url_for("admin_dashboard")
    )


# =========================================================
# CREATE CASE - ADMIN
# =========================================================

@app.route(
    "/admin/create-case",
    methods=["POST"]
)
def create_case():

    if not role_required("admin"):

        return redirect(
            url_for("login")
        )

    case_number = request.form.get(
        "case_number",
        ""
    ).strip()

    title = request.form.get(
        "title",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    client_public_id = request.form.get(
        "client_public_id",
        ""
    ).strip()

    lawyer_id = request.form.get(
        "lawyer_id",
        ""
    ).strip()

    if not case_number or not title or not client_public_id:

        flash(
            "Case number, title and client are required."
        )

        return redirect(
            url_for("admin_dashboard")
        )

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT id
        FROM users
        WHERE client_id = %s
        AND role = 'client'
        """,
        (client_public_id.upper(),)
    )

    client = cursor.fetchone()

    if not client:

        cursor.close()
        db.close()

        flash(
            "Selected client does not exist."
        )

        return redirect(
            url_for("admin_dashboard")
        )

    if lawyer_id == "":

        lawyer_id = None

    else:

        cursor.execute(
            """
            SELECT id
            FROM lawyers
            WHERE id = %s
            """,
            (lawyer_id,)
        )

        lawyer = cursor.fetchone()

        if not lawyer:

            cursor.close()
            db.close()

            flash(
                "Selected lawyer does not exist."
            )

            return redirect(
                url_for("admin_dashboard")
            )

    try:

        cursor.execute(
            """
            INSERT INTO cases
            (
                case_number,
                title,
                description,
                client_id,
                lawyer_id,
                status
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                case_number,
                title,
                description,
                client["id"],
                lawyer_id,
                "Pending"
            )
        )

        db.commit()

        flash(
            "Case created successfully."
        )

    except mysql.connector.Error as error:

        db.rollback()

        flash(
            f"Could not create case: {error}"
        )

    finally:

        cursor.close()
        db.close()

    return redirect(
        url_for("admin_dashboard")
    )


# =========================================================
# UPDATE CASE STATUS - ADMIN
# =========================================================

@app.route(
    "/admin/case/<int:case_id>/status",
    methods=["POST"]
)
def update_case_status(case_id):

    if not role_required("admin"):

        return redirect(
            url_for("login")
        )

    status_value = request.form.get(
        "status",
        ""
    )

    allowed_statuses = {
        "Pending",
        "Active",
        "In Progress",
        "Completed",
        "Closed"
    }

    if status_value not in allowed_statuses:

        flash(
            "Invalid case status."
        )

        return redirect(
            url_for("admin_dashboard")
        )

    db = get_db_connection()
    cursor = db.cursor()

    cursor.execute(
        """
        UPDATE cases
        SET status = %s
        WHERE id = %s
        """,
        (
            status_value,
            case_id
        )
    )

    db.commit()

    cursor.close()
    db.close()

    flash(
        "Case status updated."
    )

    return redirect(
        url_for("admin_dashboard")
    )


@app.route(
    "/admin/case/<int:case_id>/assign",
    methods=["POST"]
)
def assign_case_lawyer(case_id):

    if not role_required("admin"):
        return redirect(url_for("login"))

    lawyer_id = request.form.get("lawyer_id", "").strip()
    lawyer_id = lawyer_id or None

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if lawyer_id:
        cursor.execute(
            "SELECT id FROM lawyers WHERE id = %s",
            (lawyer_id,)
        )
        if not cursor.fetchone():
            cursor.close()
            db.close()
            flash("Selected lawyer does not exist.")
            return redirect(url_for("admin_dashboard"))

    cursor.execute(
        "UPDATE cases SET lawyer_id = %s WHERE id = %s",
        (lawyer_id, case_id)
    )
    db.commit()
    cursor.close()
    db.close()

    flash("Case assignment updated.")
    return redirect(url_for("admin_dashboard"))


# =========================================================
# UPLOAD DOCUMENT
# =========================================================

@app.route(
    "/upload-document",
    methods=["POST"]
)
def upload_document():

    if not logged_in():

        return jsonify({
            "error": "Login required"
        }), 401

    user = get_current_user()

    case_id = request.form.get(
        "case_id",
        ""
    ).strip()
    request_id = request.form.get("request_id", "").strip()

    if not case_id:

        return jsonify({
            "error": "Please select a case."
        }), 400

    if "document" not in request.files:

        return jsonify({
            "error": "No document selected"
        }), 400

    file = request.files["document"]

    if file.filename == "":

        return jsonify({
            "error": "No document selected"
        }), 400

    if not allowed_file(file.filename):

        return jsonify({
            "error": "File type is not allowed"
        }), 400

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            c.id,
            c.client_id,
            c.lawyer_id,
            l.user_id AS lawyer_user_id

        FROM cases c

        LEFT JOIN lawyers l
            ON c.lawyer_id = l.id

        WHERE c.id = %s
        """,
        (case_id,)
    )

    case = cursor.fetchone()

    if not case:

        cursor.close()
        db.close()

        return jsonify({
            "error": "Case not found."
        }), 404

    has_access = False

    if user["role"] == "admin":

        has_access = True

    elif user["role"] == "client":

        has_access = (
            case["client_id"]
            == user["id"]
        )

    elif user["role"] == "lawyer":

        has_access = (
            case["lawyer_user_id"]
            == user["id"]
        )

    if not has_access:

        cursor.close()
        db.close()

        return jsonify({
            "error": "You do not have access to this case."
        }), 403

    document_request = None
    if request_id:
        cursor.execute(
            """
            SELECT id, case_id, client_id, title, status
            FROM document_requests
            WHERE id = %s
              AND case_id = %s
              AND client_id = %s
              AND status = 'Pending'
            """,
            (request_id, case_id, user["id"])
        )
        document_request = cursor.fetchone()

        if not document_request:
            cursor.close()
            db.close()
            return jsonify({"error": "That document request is no longer available."}), 400

    original_name = secure_filename(
        file.filename
    )

    if not original_name or "." not in original_name:

        cursor.close()
        db.close()

        return jsonify({
            "error": "Invalid filename."
        }), 400

    extension = original_name.rsplit(
        ".",
        1
    )[1].lower()

    new_filename = (
        f"{uuid.uuid4()}.{extension}"
    )

    filepath = os.path.join(
        app.config["UPLOAD_FOLDER"],
        new_filename
    )

    try:

        file.save(filepath)

        document_type = request.form.get(
            "document_type",
            extension.upper()
        )

        cursor.execute(
            """
            INSERT INTO documents
            (
                case_id,
                uploaded_by,
                original_filename,
                stored_filename,
                document_type,
                status
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                case_id,
                user["id"],
                original_name,
                new_filename,
                document_type,
                "Pending"
            )
        )

        if document_request:
            cursor.execute(
                """
                UPDATE document_requests
                SET status = 'Fulfilled', fulfilled_document_id = %s
                WHERE id = %s
                """,
                (cursor.lastrowid, document_request["id"])
            )

        db.commit()

    except Exception as error:

        db.rollback()

        if os.path.exists(filepath):

            os.remove(filepath)

        cursor.close()
        db.close()

        return jsonify({
            "error": f"Upload failed: {error}"
        }), 500

    cursor.close()
    db.close()

    if request.form.get(
        "browser_upload"
    ) == "true":

        flash(
            "Document uploaded successfully."
        )

        if user["role"] == "admin":

            return redirect(
                url_for("admin_dashboard")
            )

        elif user["role"] == "lawyer":

            return redirect(
                url_for("lawyer_dashboard")
            )

        else:

            return redirect(
                url_for("client_dashboard")
            )

    if request.headers.get(
        "Accept",
        ""
    ).startswith("text/html"):

        flash(
            "Document uploaded successfully."
        )

        if user["role"] == "admin":

            return redirect(
                url_for("admin_dashboard")
            )

        elif user["role"] == "lawyer":

            return redirect(
                url_for("lawyer_dashboard")
            )

        else:

            return redirect(
                url_for("client_dashboard")
            )

    return jsonify({
        "success": True,
        "message": "Document uploaded successfully.",
        "filename": original_name
    })


# =========================================================
# DOWNLOAD DOCUMENT
# =========================================================

@app.route(
    "/download-document/<int:document_id>"
)
def download_document(document_id):

    if not logged_in():

        return redirect(
            url_for("login")
        )

    user = get_current_user()

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            d.*,

            c.client_id,
            c.lawyer_id,

            l.user_id AS lawyer_user_id

        FROM documents d

        INNER JOIN cases c
            ON d.case_id = c.id

        LEFT JOIN lawyers l
            ON c.lawyer_id = l.id

        WHERE d.id = %s
        """,
        (document_id,)
    )

    document = cursor.fetchone()

    cursor.close()
    db.close()

    if not document:

        return "Document not found.", 404

    allowed = False

    if user["role"] == "admin":

        allowed = True

    elif user["role"] == "lawyer":

        allowed = (
            document["lawyer_user_id"]
            == user["id"]
        )

    elif user["role"] == "client":

        allowed = (
            document["client_id"]
            == user["id"]
            and document["status"]
            == "Approved"
        )

    if not allowed:

        return (
            "You are not authorized to download this document.",
            403
        )

    filepath = os.path.join(
        app.config["UPLOAD_FOLDER"],
        document["stored_filename"]
    )

    if not os.path.exists(filepath):

        return "File not found on server.", 404

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        document["stored_filename"],
        as_attachment=True,
        download_name=document["original_filename"]
    )


# =========================================================
# APPROVE DOCUMENT - ADMIN
# =========================================================

@app.route(
    "/admin/document/<int:document_id>/approve",
    methods=["POST"]
)
def approve_document(document_id):

    if not role_required("admin"):

        return redirect(
            url_for("login")
        )

    db = get_db_connection()
    cursor = db.cursor()

    cursor.execute(
        """
        UPDATE documents
        SET status = 'Approved'
        WHERE id = %s
        """,
        (document_id,)
    )

    db.commit()

    cursor.close()
    db.close()

    flash(
        "Document approved successfully."
    )

    return redirect(
        url_for("admin_dashboard")
    )


# =========================================================
# REJECT DOCUMENT - ADMIN
# =========================================================

@app.route(
    "/admin/document/<int:document_id>/reject",
    methods=["POST"]
)
def reject_document(document_id):

    if not role_required("admin"):

        return redirect(
            url_for("login")
        )

    db = get_db_connection()
    cursor = db.cursor()

    cursor.execute(
        """
        UPDATE documents
        SET status = 'Rejected'
        WHERE id = %s
        """,
        (document_id,)
    )

    db.commit()

    cursor.close()
    db.close()

    flash(
        "Document rejected."
    )

    return redirect(
        url_for("admin_dashboard")
    )


@app.route("/appointments/request", methods=["POST"])
def request_appointment():

    if not role_required("client"):
        return redirect(url_for("login"))

    user = get_current_user()
    case_id = request.form.get("case_id", "").strip()
    lawyer_id = request.form.get("lawyer_id", "").strip()
    scheduled_at = request.form.get("scheduled_at", "").strip()
    notes = request.form.get("notes", "").strip()

    if not case_id or not lawyer_id or not scheduled_at:
        flash("Select a case, lawyer and proposed appointment time.")
        return redirect(url_for("client_dashboard"))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT c.id, c.client_id
        FROM cases c
        WHERE c.id = %s AND c.client_id = %s
        """,
        (case_id, user["id"])
    )
    case = cursor.fetchone()

    if not case:
        cursor.close()
        db.close()
        flash("This case is not available for appointment requests.")
        return redirect(url_for("client_dashboard"))

    cursor.execute(
        "SELECT id FROM lawyers WHERE id = %s",
        (lawyer_id,)
    )
    lawyer = cursor.fetchone()

    if not lawyer:
        cursor.close()
        db.close()
        flash("Selected lawyer does not exist.")
        return redirect(url_for("client_dashboard"))

    cursor.execute(
        """
        INSERT INTO appointments
        (case_id, client_id, lawyer_id, requested_by, appointment_date, notes, subject)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (case_id, user["id"], lawyer_id, user["id"], scheduled_at, notes, "Case consultation")
    )
    db.commit()
    cursor.close()
    db.close()

    flash("Appointment request submitted.")
    return redirect(url_for("client_dashboard"))


@app.route("/appointments/<int:appointment_id>/status", methods=["POST"])
def update_appointment_status(appointment_id):

    if not logged_in():
        return redirect(url_for("login"))

    user = get_current_user()
    if user["role"] not in {"lawyer", "admin"}:
        return redirect(url_for("client_dashboard"))

    status_value = request.form.get("status", "")
    if status_value not in {"Requested", "Confirmed", "Cancelled", "Completed"}:
        flash("Invalid appointment status.")
        return redirect(url_for(
            "admin_dashboard" if user["role"] == "admin" else "lawyer_dashboard"
        ))

    db = get_db_connection()
    cursor = db.cursor()
    if user["role"] == "lawyer":
        cursor.execute(
            """
            UPDATE appointments a
            INNER JOIN lawyers l ON a.lawyer_id = l.id
            SET a.status = %s
            WHERE a.id = %s AND l.user_id = %s
            """,
            (status_value, appointment_id, user["id"])
        )
    else:
        cursor.execute(
            "UPDATE appointments SET status = %s WHERE id = %s",
            (status_value, appointment_id)
        )
    db.commit()
    cursor.close()
    db.close()

    flash("Appointment status updated.")
    return redirect(url_for(
        "admin_dashboard" if user["role"] == "admin" else "lawyer_dashboard"
    ))


@app.route("/messages/send", methods=["POST"])
def send_message():

    if not logged_in():
        return redirect(url_for("login"))

    user = get_current_user()
    case_id = request.form.get("case_id", "").strip()
    body = request.form.get("body", "").strip()

    if not case_id or not body:
        flash("Select a case and write a message.")
        return redirect(url_for(f"{user['role']}_dashboard"))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT c.client_id, l.user_id AS lawyer_user_id
        FROM cases c
        LEFT JOIN lawyers l ON c.lawyer_id = l.id
        WHERE c.id = %s
        """,
        (case_id,)
    )
    case = cursor.fetchone()

    if not case or user["id"] not in {case["client_id"], case["lawyer_user_id"]}:
        cursor.close()
        db.close()
        flash("You do not have access to this case.")
        return redirect(url_for(f"{user['role']}_dashboard"))

    recipient_id = (
        case["lawyer_user_id"]
        if user["id"] == case["client_id"]
        else case["client_id"]
    )
    cursor.execute(
        """
        INSERT INTO messages (case_id, sender_id, receiver_id, message)
        VALUES (%s, %s, %s, %s)
        """,
        (case_id, user["id"], recipient_id, body)
    )
    db.commit()
    cursor.close()
    db.close()

    flash("Message sent.")
    return redirect(url_for(f"{user['role']}_dashboard"))


# =========================================================
# API - CASES
# =========================================================

@app.route("/api/cases")
def get_cases():

    if not logged_in():

        return jsonify({
            "error": "Authentication required"
        }), 401

    user = get_current_user()

    if user["role"] == "admin":

        cases = get_all_cases()

    elif user["role"] == "lawyer":

        cases = get_lawyer_cases(
            user["id"]
        )

    else:

        cases = get_client_cases(
            user["id"]
        )

    return jsonify(cases)


# =========================================================
# API - CASE DETAILS
# =========================================================

@app.route(
    "/api/cases/<int:case_id>"
)
def case_details(case_id):

    if not logged_in():

        return jsonify({
            "error": "Authentication required"
        }), 401

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            c.id,
            c.case_number,
            c.title,
            c.description,
            c.client_id,
            c.lawyer_id,
            c.status,
            c.created_at,

            cu.full_name AS client_name,

            lu.full_name AS lawyer_name

        FROM cases c

        INNER JOIN users cu
            ON c.client_id = cu.id

        LEFT JOIN lawyers l
            ON c.lawyer_id = l.id

        LEFT JOIN users lu
            ON l.user_id = lu.id

        WHERE c.id = %s
        """,
        (case_id,)
    )

    case = cursor.fetchone()

    cursor.close()
    db.close()

    if not case:

        return jsonify({
            "error": "Case not found"
        }), 404

    user = get_current_user()

    allowed = False

    if user["role"] == "admin":

        allowed = True

    elif user["role"] == "client":

        allowed = (
            case["client_id"]
            == user["id"]
        )

    elif user["role"] == "lawyer":

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT user_id
            FROM lawyers
            WHERE id = %s
            """,
            (case["lawyer_id"],)
        )

        lawyer = cursor.fetchone()

        cursor.close()
        db.close()

        if lawyer:

            allowed = (
                lawyer["user_id"]
                == user["id"]
            )

    if not allowed:

        return jsonify({
            "error": "You do not have access to this case."
        }), 403

    return jsonify(case)


# =========================================================
# SYSTEM STATUS
# =========================================================

@app.route("/api/status")
def status():

    return jsonify({
        "system": "HOFFEIN ATTORNEYS",
        "status": "online",
        "backend": "Flask"
    })


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    try:

        ensure_organization_tables()
        create_test_accounts()

        create_lawyer_profile()

    except mysql.connector.Error as error:

        print("")
        print("ERROR CREATING TEST ACCOUNTS:")
        print(error)
        print("")

    app.run(
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
        host="127.0.0.1",
        port=int(os.getenv("PORT", "5000"))
    )
