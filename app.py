import os
import re
from datetime import datetime, timezone
from functools import wraps
from uuid import uuid4

from flask import (
    Flask,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from supabase_db import (
    create_capture,
    create_dashboard_user,
    create_location,
    create_photo,
    delete_capture_records,
    download_photo,
    get_capture,
    get_capture_by_device,
    get_captures,
    get_dashboard_user,
    get_location_count,
    get_photo_by_filename,
    get_photo_count,
    get_photo_filenames,
    get_photo_page,
    get_recent_locations,
    list_dashboard_users,
    remove_photo_files,
    rename_capture,
    upload_photo,
)


ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")
SECRET_KEY = os.environ.get("SECRET_KEY")
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() not in {"0", "false", "no"}

if not ADMIN_USERNAME:
    raise RuntimeError("Variável ADMIN_USERNAME não configurada.")
if not ADMIN_PASSWORD_HASH:
    raise RuntimeError("Variável ADMIN_PASSWORD_HASH não configurada.")
if not SECRET_KEY:
    raise RuntimeError("Variável SECRET_KEY não configurada.")


app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_SECURE=SESSION_COOKIE_SECURE,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=3600,
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
)

DEVICE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 2
PAGE_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")
RESERVED_PAGE_KEYS = {"api", "dashboard", "login", "logout", "uploads", "static"}


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def normalize_page_key(value):
    page_key = (value or "index").strip().lower()
    if not PAGE_KEY_PATTERN.fullmatch(page_key) or page_key in RESERVED_PAGE_KEYS:
        raise ValueError("Identificador de página inválido.")
    return page_key


def capture_page_key(capture):
    """Registros antigos sem escopo pertencem à página padrão."""
    return capture.get("page_key") or "index"


def device_cookie_name(page_key):
    return f"sentinela_device_{page_key}"


def get_device_id(page_key):
    return request.cookies.get(device_cookie_name(page_key))


def set_device_cookie(response, page_key, device_id):
    response.set_cookie(
        device_cookie_name(page_key),
        device_id,
        max_age=DEVICE_COOKIE_MAX_AGE,
        secure=True,
        httponly=True,
        samesite="Lax",
    )
    return response


def make_maps_url(latitude, longitude):
    return f"https://www.google.com/maps?z=20&t=k&q=loc:{latitude}+{longitude}"


def ensure_capture(capture_id, user_agent, device_id, page_key):
    existing = get_capture(capture_id)
    if existing:
        if capture_page_key(existing) != page_key:
            raise ValueError("A sessão não pertence a esta página.")
        return existing
    return create_capture(
        capture_id=capture_id,
        created_at=now_utc(),
        user_agent=user_agent,
        device_id=device_id,
        page_key=page_key,
    )


def resolve_capture_id(requested_capture_id, page_key):
    device_id = get_device_id(page_key)
    if device_id:
        existing = get_capture_by_device(device_id, page_key)
        if existing:
            return existing["capture_id"], device_id

    if requested_capture_id:
        existing = get_capture(requested_capture_id)
        if existing and capture_page_key(existing) != page_key:
            raise ValueError("A sessão não pertence a esta página.")
        return requested_capture_id, device_id

    return uuid4().hex, device_id


# ---------------------------------------------------------------------------
# Autenticação e escopo
# ---------------------------------------------------------------------------

def login_required(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return function(*args, **kwargs)
    return decorated_function


def api_login_required(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not session.get("authenticated"):
            return jsonify(success=False, error="Não autenticado."), 401
        return function(*args, **kwargs)
    return decorated_function


def api_admin_required(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not session.get("authenticated"):
            return jsonify(success=False, error="Não autenticado."), 401
        if not session.get("is_admin"):
            return jsonify(success=False, error="Acesso restrito ao administrador."), 403
        return function(*args, **kwargs)
    return decorated_function


def current_capture_scope():
    return None if session.get("is_admin") else session.get("page_key")


def can_access_capture(capture):
    return session.get("is_admin") or capture_page_key(capture) == session.get("page_key")


def accessible_capture_or_error(capture_id):
    capture = get_capture(capture_id)
    if not capture:
        return None, (jsonify(success=False, error="Captura não encontrada."), 404)
    if not can_access_capture(capture):
        # Mantém o mesmo resultado de "não encontrado" para não revelar dados de outra página.
        return None, (jsonify(success=False, error="Captura não encontrada."), 404)
    return capture, None


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        authenticated_user = None

        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            authenticated_user = {
                "username": ADMIN_USERNAME,
                "is_admin": True,
                "page_key": None,
            }
        else:
            dashboard_user = get_dashboard_user(username.lower())
            if (
                dashboard_user
                and dashboard_user.get("active")
                and check_password_hash(dashboard_user["password_hash"], password)
            ):
                authenticated_user = {
                    "username": dashboard_user["username"],
                    "is_admin": bool(dashboard_user.get("is_admin")),
                    "page_key": dashboard_user.get("page_key"),
                }

        if authenticated_user:
            session.clear()
            session["authenticated"] = True
            session["username"] = authenticated_user["username"]
            session["is_admin"] = authenticated_user["is_admin"]
            session["page_key"] = authenticated_user["page_key"]
            session.permanent = True
            return redirect(url_for("dashboard"))

        error = "Usuário ou senha inválidos."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/api/me")
@api_login_required
def api_me():
    return jsonify(
        success=True,
        user={
            "username": session.get("username"),
            "is_admin": bool(session.get("is_admin")),
            "page_key": session.get("page_key"),
        },
    )


# ---------------------------------------------------------------------------
# Páginas públicas de demonstração
# ---------------------------------------------------------------------------

def render_capture_page(page_key):
    device_id = get_device_id(page_key)
    existing_capture = get_capture_by_device(device_id, page_key) if device_id else None
    response = make_response(
        render_template(
            "index.html",
            capture_id=existing_capture["capture_id"] if existing_capture else None,
            page_key=page_key,
        )
    )
    if device_id:
        set_device_cookie(response, page_key, device_id)
    return response


@app.get("/")
def index():
    return render_capture_page("index")


@app.get("/<page_key>.html")
def named_index(page_key):
    try:
        return render_capture_page(normalize_page_key(page_key))
    except ValueError:
        return "Página não encontrada.", 404


@app.get("/api/session")
def api_session():
    try:
        page_key = normalize_page_key(request.args.get("page_key"))
        device_id = get_device_id(page_key)
        existing_capture = get_capture_by_device(device_id, page_key) if device_id else None

        if existing_capture:
            capture_id = existing_capture["capture_id"]
            is_new = False
        else:
            device_id = uuid4().hex
            capture_id = uuid4().hex
            create_capture(
                capture_id=capture_id,
                created_at=now_utc(),
                user_agent=request.headers.get("User-Agent", ""),
                device_id=device_id,
                page_key=page_key,
            )
            is_new = True

        response = make_response(jsonify(
            success=True,
            capture_id=capture_id,
            page_key=page_key,
            new_user=is_new,
        ))
        return set_device_cookie(response, page_key, device_id)
    except (ValueError, RuntimeError) as error:
        return jsonify(success=False, error=str(error)), 400
    except Exception:
        app.logger.exception("Erro ao criar sessão pública")
        return jsonify(success=False, error="Não foi possível iniciar a sessão."), 500


# ---------------------------------------------------------------------------
# Recebimento de dados autorizados pelo usuário
# ---------------------------------------------------------------------------

def page_key_from_request(data=None):
    source = data if data is not None else request.form
    return normalize_page_key(source.get("page_key"))


@app.post("/upload")
def upload():
    photo = request.files.get("photo")
    if photo is None:
        return jsonify(success=False, error="Nenhuma foto recebida."), 400
    if photo.mimetype not in {"image/jpeg", "image/jpg", "image/webp"}:
        return jsonify(success=False, error="Formato de imagem não permitido."), 400

    try:
        page_key = page_key_from_request()
        capture_id, device_id = resolve_capture_id(request.form.get("capture_id"), page_key)
        ensure_capture(capture_id, request.headers.get("User-Agent", ""), device_id, page_key)

        file_data = photo.read()
        if not file_data:
            return jsonify(success=False, error="A foto está vazia."), 400

        location_id = request.form.get("location_id", type=int)
        filename = f"{uuid4().hex}.jpg"
        upload_photo(file_data, filename, photo.mimetype or "image/jpeg")
        record = create_photo(capture_id, location_id, filename, now_utc())
        return jsonify(success=True, photo_id=record["id"], capture_id=capture_id, filename=filename)
    except ValueError as error:
        return jsonify(success=False, error=str(error)), 400
    except Exception:
        app.logger.exception("Erro ao salvar foto")
        return jsonify(success=False, error="Não foi possível salvar a foto."), 500


@app.post("/location")
def location():
    data = request.get_json(silent=True) or {}
    try:
        page_key = page_key_from_request(data)
        latitude = float(data["latitude"])
        longitude = float(data["longitude"])
        accuracy = float(data["accuracy"]) if data.get("accuracy") is not None else None
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("Coordenadas inválidas.")

        capture_id, device_id = resolve_capture_id(data.get("capture_id"), page_key)
        ensure_capture(capture_id, request.headers.get("User-Agent", ""), device_id, page_key)
        record = create_location(capture_id, latitude, longitude, accuracy, now_utc())
        return jsonify(
            success=True,
            location_id=record["id"],
            capture_id=capture_id,
            latitude=latitude,
            longitude=longitude,
            accuracy=accuracy,
            maps_url=make_maps_url(latitude, longitude),
        )
    except (KeyError, TypeError, ValueError) as error:
        return jsonify(success=False, error=str(error) or "Coordenadas inválidas."), 400
    except Exception:
        app.logger.exception("Erro ao salvar localização")
        return jsonify(success=False, error="Não foi possível salvar a localização."), 500


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/dashboard")
@login_required
def dashboard():
    return render_template(
        "dashboard.html",
        current_user={
            "username": session.get("username"),
            "is_admin": bool(session.get("is_admin")),
            "page_key": session.get("page_key"),
        },
    )


def serialize_photo(row):
    return {
        "id": row["id"],
        "capture_id": row["capture_id"],
        "location_id": row.get("location_id"),
        "filename": row["filename"],
        "created_at": row["created_at"],
        "photo_url": url_for("uploaded_file", filename=row["filename"]),
    }


def serialize_location(row):
    return {
        "id": row["id"],
        "capture_id": row["capture_id"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "accuracy": row.get("accuracy"),
        "created_at": row["created_at"],
    }


@app.get("/api/captures")
@api_login_required
def api_captures():
    try:
        rows = get_captures(current_capture_scope())
        captures = [{
            "capture_id": row["capture_id"],
            "created_at": row["created_at"],
            "display_name": row.get("display_name"),
            "page_key": capture_page_key(row),
        } for row in rows]
        return jsonify(success=True, captures=captures)
    except Exception:
        app.logger.exception("Erro ao listar capturas")
        return jsonify(success=False, error="Não foi possível carregar as capturas."), 500


@app.get("/api/captures/<capture_id>")
@api_login_required
def api_capture(capture_id):
    capture, error = accessible_capture_or_error(capture_id)
    if error:
        return error

    try:
        photo_limit = min(max(request.args.get("photo_limit", 24, type=int), 1), 50)
        location_limit = min(max(request.args.get("location_limit", 200, type=int), 1), 300)
        photo_rows, has_more_photos = get_photo_page(capture_id, limit=photo_limit)
        location_rows = get_recent_locations(capture_id, location_limit)
        last_location = location_rows[-1] if location_rows else None

        capture_data = {
            "capture_id": capture["capture_id"],
            "created_at": capture["created_at"],
            "display_name": capture.get("display_name"),
            "page_key": capture_page_key(capture),
            "photo_total": get_photo_count(capture_id),
            "location_total": get_location_count(capture_id),
            "latitude": last_location["latitude"] if last_location else None,
            "longitude": last_location["longitude"] if last_location else None,
            "accuracy": last_location.get("accuracy") if last_location else None,
            "updated_at": last_location["created_at"] if last_location else capture["created_at"],
        }
        if last_location:
            capture_data["maps_url"] = make_maps_url(last_location["latitude"], last_location["longitude"])
        else:
            capture_data["maps_url"] = None

        return jsonify(
            success=True,
            capture=capture_data,
            locations=[serialize_location(row) for row in location_rows],
            photos=[serialize_photo(row) for row in photo_rows],
            has_more_photos=has_more_photos,
        )
    except Exception:
        app.logger.exception("Erro ao carregar captura")
        return jsonify(success=False, error="Não foi possível carregar a captura."), 500


@app.get("/api/captures/<capture_id>/photos")
@api_login_required
def api_capture_photos(capture_id):
    _, error = accessible_capture_or_error(capture_id)
    if error:
        return error
    try:
        before_id = request.args.get("before_id", type=int)
        limit = min(max(request.args.get("limit", 24, type=int), 1), 50)
        rows, has_more = get_photo_page(capture_id, before_id=before_id, limit=limit)
        return jsonify(success=True, photos=[serialize_photo(row) for row in rows], has_more_photos=has_more)
    except Exception:
        app.logger.exception("Erro ao carregar mais fotos")
        return jsonify(success=False, error="Não foi possível carregar mais fotos."), 500


@app.patch("/api/captures/<capture_id>")
@api_login_required
def api_rename_capture(capture_id):
    _, error = accessible_capture_or_error(capture_id)
    if error:
        return error
    data = request.get_json(silent=True) or {}
    display_name = (data.get("display_name") or "").strip()
    if len(display_name) > 80:
        return jsonify(success=False, error="O nome pode ter no máximo 80 caracteres."), 400
    try:
        updated = rename_capture(capture_id, display_name or None)
        return jsonify(success=True, capture={
            "capture_id": updated["capture_id"],
            "display_name": updated.get("display_name"),
        })
    except Exception:
        app.logger.exception("Erro ao renomear captura")
        return jsonify(success=False, error="Não foi possível renomear a captura."), 500


@app.delete("/api/captures/<capture_id>")
@api_login_required
def api_delete_capture(capture_id):
    _, error = accessible_capture_or_error(capture_id)
    if error:
        return error
    try:
        # Remove arquivos antes dos registros para evitar objetos órfãos no Storage.
        remove_photo_files(get_photo_filenames(capture_id))
        delete_capture_records(capture_id)
        return jsonify(success=True)
    except Exception:
        app.logger.exception("Erro ao apagar captura")
        return jsonify(success=False, error="Não foi possível apagar a captura."), 500


@app.get("/uploads/<filename>")
@api_login_required
def uploaded_file(filename):
    photo = get_photo_by_filename(filename)
    if not photo:
        return jsonify(success=False, error="Imagem não encontrada."), 404
    capture, error = accessible_capture_or_error(photo["capture_id"])
    if error:
        return error
    try:
        response = make_response(download_photo(filename))
        response.headers["Content-Type"] = "image/jpeg"
        # O nome do arquivo é único e imutável: assim miniaturas não são baixadas a cada atualização.
        response.headers["Cache-Control"] = "private, max-age=86400, immutable"
        return response
    except Exception:
        app.logger.exception("Erro ao baixar imagem")
        return jsonify(success=False, error="Imagem não encontrada."), 404


# ---------------------------------------------------------------------------
# Administração de usuários
# ---------------------------------------------------------------------------

@app.get("/api/users")
@api_admin_required
def api_users():
    try:
        return jsonify(success=True, users=list_dashboard_users())
    except Exception:
        app.logger.exception("Erro ao listar usuários")
        return jsonify(success=False, error="Não foi possível carregar os usuários."), 500


@app.post("/api/users")
@api_admin_required
def api_create_user():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    try:
        page_key = normalize_page_key(data.get("page_key"))
    except ValueError as error:
        return jsonify(success=False, error=str(error)), 400

    if not USERNAME_PATTERN.fullmatch(username):
        return jsonify(success=False, error="Use 3 a 32 caracteres: letras, números, ponto, hífen ou _."), 400
    if username == ADMIN_USERNAME.lower():
        return jsonify(success=False, error="Este nome de usuário é reservado."), 400
    if len(password) < 8:
        return jsonify(success=False, error="A senha deve ter ao menos 8 caracteres."), 400

    try:
        if get_dashboard_user(username):
            return jsonify(success=False, error="Esse usuário já existe."), 409
        user = create_dashboard_user(username, generate_password_hash(password), page_key)
        return jsonify(success=True, user=user), 201
    except Exception:
        app.logger.exception("Erro ao criar usuário")
        return jsonify(success=False, error="Não foi possível criar o usuário."), 500


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify(success=False, error="A imagem excede o limite de 5 MB."), 413


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
