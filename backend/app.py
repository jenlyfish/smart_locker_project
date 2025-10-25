#!/usr/bin/env python3

"""
Smart Locker System - Main Application
Author: Alp Alpdogan
In memory of Mehmet Ugurlu and Yusuf Alpdogan

LICENSING CONDITION: These memorial dedications and author credits
must never be removed from this file or any derivative works.
This condition is binding and must be preserved in all versions.
"""

import csv
import io
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from functools import wraps

import pytz
from dateutil import parser as dateutil_parser
from flask import (Flask, Response, g, jsonify, redirect, render_template,
                   request, session, url_for)
from flask_babel import Babel
from flask_cors import CORS
from flask_jwt_extended import (JWTManager, create_access_token,
                                get_jwt_identity, jwt_required)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

from utils.export import (export_data_csv, export_data_excel, export_data_pdf,
                          export_system_report)
from utils.rs485 import (close_locker, get_locker_status, open_locker,
                         test_rs485_connection)


def parse_datetime_utc(dt_str):
    """Parse datetime string and convert to UTC, treating input as local time"""
    try:
        # Parse the datetime string
        dt = dateutil_parser.isoparse(dt_str)

        # If the datetime has timezone info, convert to UTC
        if dt.tzinfo is not None:
            return dt.astimezone(pytz.UTC).replace(tzinfo=None)
        else:
            # Treat as local time and convert to UTC
            # Get local timezone
            local_tz = pytz.timezone("America/New_York")  # Adjust for your timezone
            local_dt = local_tz.localize(dt)
            utc_dt = local_dt.astimezone(pytz.UTC)
            return utc_dt.replace(tzinfo=None)
    except Exception as e:
        logger.error(f"Error parsing datetime '{dt_str}': {e}")
        raise ValueError(f"Invalid datetime format: {dt_str}")


# Ensure logs directory exists
logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(logs_dir, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("logs/app.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# =============================================================================
# APPLICATION CONFIGURATION
# =============================================================================

# Set up base directory and database configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# PostgreSQL Database Configuration
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "smart_locker")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")

# Initialize Flask application
app = Flask(__name__)

# Configuration
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", os.urandom(32).hex())
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "smart-locker-jwt-secret-key-2024")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)


# Security headers
@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';"
    )
    return response


# Database configuration - PostgreSQL only
import sys

database_url = os.getenv("DATABASE_URL")
if not database_url:
    # Try to construct DATABASE_URL from individual components
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "smart_locker_db")
    db_user = os.getenv("DB_USER", "smart_locker_user")
    db_pass = os.getenv("DB_PASS", "smartlockerpass123")

    database_url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    print(f"INFO: Constructed DATABASE_URL from individual components: {database_url}")

if not database_url.startswith("postgresql://"):
    print("ERROR: DATABASE_URL must be a valid postgresql:// URI.")
    print(f"Current DATABASE_URL: {database_url}")
    sys.exit(1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

# Initialize extensions
db = SQLAlchemy(app)
jwt = JWTManager(app)
CORS(app)


# JWT error handlers
@jwt.invalid_token_loader
def invalid_token_callback(error_string):
    # Log invalid token attempts
    log_action(
        "auth_failed",
        details=f"Invalid JWT token attempt: {error_string}",
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    return jsonify({"error": "Invalid token"}), 401


@jwt.unauthorized_loader
def missing_token_callback(error_string):
    # Log missing token attempts
    log_action(
        "auth_failed",
        details=f"Missing JWT token: {error_string}",
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    return jsonify({"error": "Missing token"}), 401


@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    # Log expired token attempts
    user_id = jwt_payload.get('sub') if jwt_payload else None
    log_action(
        "auth_failed",
        user_id=user_id,
        details=f"Expired JWT token attempt",
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    return jsonify({"error": "Token has expired"}), 401


# Initialize Babel
babel = Babel(app)

# Babel configuration
app.config["BABEL_DEFAULT_LOCALE"] = "en"
app.config["BABEL_SUPPORTED_LOCALES"] = ["en", "fr", "es", "tr"]


def get_locale():
    """Get the locale for the current request"""
    # Try to get locale from session
    if "language" in session:
        return session["language"]
    # Try to get locale from request
    return request.accept_languages.best_match(app.config["BABEL_SUPPORTED_LOCALES"])


# Import and initialize models from models.py
from models import init_models

(
    User,
    Locker,
    Item,
    Log,
    Borrow,
    Payment,
    Reservation,
    init_db_func,
    generate_dummy_data,
) = init_models(db)

# Store models in app config for dynamic access
app.config["models"] = {
    "User": User,
    "Locker": Locker,
    "Item": Item,
    "Log": Log,
    "Borrow": Borrow,
    "Payment": Payment,
    "Reservation": Reservation,
}

# Remove the duplicate User model definition from app.py. Only use the User model from models.py via init_models(db).
# They will be imported from models.py when needed


# Helper functions
def log_action(
    action_type,
    user_id=None,
    item_id=None,
    locker_id=None,
    details=None,
    ip_address=None,
    user_agent=None,
):
    """Log an action to the database"""
    try:
        # Get IP address and user agent if not provided
        if ip_address is None:
            ip_address = request.remote_addr if request else None
        if user_agent is None:
            user_agent = request.headers.get('User-Agent') if request else None
            
        log = Log(
            user_id=user_id,
            item_id=item_id,
            locker_id=locker_id,
            action_type=action_type,
            notes=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.session.add(log)
        db.session.commit()
        logger.info(f"Action logged: {action_type} - {details}")
    except Exception as e:
        logger.error(f"Failed to log action: {e}")


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        current_user_id = get_jwt_identity()
        user = db.session.get(User, current_user_id)
        if not user or user.role != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return fn(*args, **kwargs)

    return wrapper


def common_export(data_type, query_func, data_formatter):
    """Common export function for all data types"""
    try:
        format_type = request.args.get("format", "csv").lower()
        
        # Get the data using the provided query function
        raw_data = query_func()
        
        # Format the data using the provided formatter
        formatted_data = data_formatter(raw_data)
        
        # Generate filename
        filename_base = f"{data_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        if format_type == "csv":
            csv_content = export_data_csv(formatted_data)
            return Response(
                csv_content,
                mimetype="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename_base}.csv"},
            )
        elif format_type == "excel":
            excel_content = export_data_excel(formatted_data)
            return Response(
                excel_content,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename={filename_base}.xlsx"},
            )
        elif format_type == "pdf":
            sections = [{"title": f"{data_type.title()} Report", "content": formatted_data}]
            pdf_content = export_data_pdf(f"Smart Locker {data_type.title()} Report", sections)
            return Response(
                pdf_content,
                mimetype="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={filename_base}.pdf"},
            )
        else:
            return jsonify({"error": "Unsupported format. Use csv, excel, or pdf"}), 400

    except Exception as e:
        logger.error(f"Export {data_type} error: {e}")
        return jsonify({"error": "Internal server error"}), 500


# Routes
@app.before_request
def before_request():
    """
    Set up global variables before each request.
    """
    g.locale = get_locale()


# --- Language selection ---
@app.route("/language/<language>")
def set_language(language):
    if language in app.config["BABEL_SUPPORTED_LOCALES"]:
        session["language"] = language
    return redirect(request.referrer or url_for("main_menu"))


# --- Auth routes ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            username = request.form.get("username")
            password = request.form.get("password")
            rfid_tag = request.form.get("rfid_tag")

            # Check if RFID card login
            if rfid_tag:
                if not rfid_tag.strip():
                    return jsonify({"error": "RFID tag cannot be empty"}), 400
                
                user = User.query.filter_by(rfid_tag=rfid_tag.strip()).first()
                
                if user and user.is_active:
                    access_token = create_access_token(identity=user.id)
                    
                    # Log the RFID login
                    log_action(
                        "login", 
                        user.id, 
                        details=f"User {user.username} logged in via RFID card",
                        ip_address=request.remote_addr,
                        user_agent=request.headers.get('User-Agent')
                    )
                    
                    return jsonify({
                        "access_token": access_token, 
                        "user": user.to_dict(),
                        "login_method": "rfid"
                    })
                else:
                    # Log failed RFID login attempt
                    log_action(
                        "login_failed",
                        details=f"Failed RFID login attempt with tag: {rfid_tag[:8]}...",
                        ip_address=request.remote_addr,
                        user_agent=request.headers.get('User-Agent')
                    )
                    return jsonify({"error": "Invalid RFID card or inactive user"}), 401
            
            # Traditional username/password login
            if not username or not password:
                return jsonify({"error": "Username and password required, or provide RFID tag"}), 400

            user = User.query.filter_by(username=username).first()

            if user and user.check_password(password) and user.is_active:
                access_token = create_access_token(identity=user.id)

                # Log the login
                log_action(
                    "login", 
                    user.id, 
                    details=f"User {username} logged in via username/password",
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent')
                )

                return jsonify({
                    "access_token": access_token, 
                    "user": user.to_dict(),
                    "login_method": "password"
                })
            else:
                # Log failed login attempt
                log_action(
                    "login_failed",
                    details=f"Failed login attempt for username: {username}",
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent')
                )
                return jsonify({"error": "Invalid credentials or inactive user"}), 401
        except Exception as e:
            logger.error(f"Login error: {e}")
            return jsonify({"error": "Internal server error"}), 500
    # Optionally handle GET requests here
    return jsonify({"message": "Login endpoint"})


@app.route("/api/auth/logout", methods=["POST"])
@jwt_required()
def api_logout():
    """API logout endpoint (stateless JWT, just for client to clear token)"""
    # Log the logout event
    log_action(
        "logout",
        get_jwt_identity(),
        details="User logged out",
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    return jsonify({"message": "Logged out successfully"}), 200


@app.route("/api/auth/simulate-rfid", methods=["POST"])
def simulate_rfid_login():
    """Simulate RFID card login for demo purposes - logs in as demo admin"""
    try:
        # Use the demo admin RFID tag
        demo_admin_rfid = "RFID_DEMO_ADMIN"
        
        user = User.query.filter_by(rfid_tag=demo_admin_rfid).first()
        
        if user and user.is_active:
            access_token = create_access_token(identity=user.id)
            
            # Log the simulated RFID login
            log_action(
                "login", 
                user.id, 
                details=f"User {user.username} logged in via SIMULATED RFID card (DEMO)",
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            
            return jsonify({
                "token": access_token,
                "user": user.to_dict(),
                "login_method": "rfid_simulation",
                "message": "Demo RFID login successful"
            })
        else:
            # If demo admin doesn't exist, create it with RFID tag
            if not user:
                demo_admin = User(
                    username="demo_admin",
                    email="demo_admin@ets.com",
                    first_name="Demo Admin",
                    last_name="User",
                    role="admin",
                    rfid_tag=demo_admin_rfid,
                    qr_code="QR_DEMO_ADMIN",
                    is_active=True
                )
                demo_admin.set_password("admin123")
                
                db.session.add(demo_admin)
                db.session.commit()
                
                access_token = create_access_token(identity=demo_admin.id)
                
                # Log the creation and login
                log_action(
                    "register",
                    demo_admin.id,
                    details="Demo admin user created for RFID simulation",
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent')
                )
                
                log_action(
                    "login", 
                    demo_admin.id, 
                    details=f"User {demo_admin.username} logged in via SIMULATED RFID card (DEMO - FIRST TIME)",
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent')
                )
                
                return jsonify({
                    "token": access_token,
                    "user": demo_admin.to_dict(),
                    "login_method": "rfid_simulation",
                    "message": "Demo admin created and RFID login successful"
                })
            else:
                return jsonify({
                    "error": "Demo admin account is inactive",
                    "details": "Please contact administrator"
                }), 401
                
    except Exception as e:
        logger.error(f"Simulate RFID login error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/lockers/borrow", methods=["POST"])
@jwt_required()
def api_borrow_item():
    """Alias for /api/borrows POST for legacy/frontend compatibility"""
    return create_borrow()


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    """API login endpoint for frontend"""
    try:
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"error": "Malformed JSON"}), 400
        
        username = data.get("username")
        password = data.get("password")
        rfid_tag = data.get("rfid_tag")

        # Check if RFID card login
        if rfid_tag:
            if not rfid_tag.strip():
                return jsonify({"error": "RFID tag cannot be empty"}), 400
            
            user = User.query.filter_by(rfid_tag=rfid_tag.strip()).first()
            
            if user and user.is_active:
                access_token = create_access_token(identity=user.id)
                
                # Log the RFID login
                log_action(
                    "login", 
                    user.id, 
                    details=f"User {user.username} logged in via RFID card (API)",
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent')
                )
                
                return jsonify({
                    "token": access_token,
                    "user": user.to_dict(),
                    "login_method": "rfid"
                })
            else:
                # Log failed RFID login attempt
                log_action(
                    "login_failed",
                    details=f"Failed RFID login attempt with tag: {rfid_tag[:8]}... (API)",
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent')
                )
                return jsonify({
                    "error": "Invalid RFID card or inactive user",
                    "details": "RFID card not found or user account is inactive"
                }), 401

        # Traditional username/password login
        if not username or not password:
            return jsonify({"error": "Username and password required, or provide RFID tag"}), 400

        user = User.query.filter_by(username=username).first()

        if not user:
            # Log failed login attempt - user not found
            log_action(
                "login_failed", 
                details=f"Failed login attempt for username '{username}' - User not found (API)",
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            return (
                jsonify(
                    {
                        "error": "User not found",
                        "details": "No account exists with this username",
                    }
                ),
                401,
            )

        if not user.check_password(password):
            # Log failed login attempt - wrong password
            log_action(
                "login_failed", 
                user_id=user.id,
                details=f"Failed login attempt for user '{username}' - Invalid password (API)",
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            return (
                jsonify(
                    {
                        "error": "Invalid password",
                        "details": "The password you entered is incorrect",
                    }
                ),
                401,
            )

        if not user.is_active:
            # Log failed login attempt - inactive user
            log_action(
                "login_failed", 
                user_id=user.id,
                details=f"Failed login attempt for user '{username}' - User account inactive (API)",
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            return (
                jsonify(
                    {
                        "error": "Account inactive",
                        "details": "Your account has been deactivated",
                    }
                ),
                401,
            )

        access_token = create_access_token(identity=user.id)
        # Log successful login
        log_action(
            "login", 
            user.id, 
            details=f"User '{username}' logged in successfully (API)",
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        return jsonify(
            {
                "token": access_token,  # Frontend expects 'token' not 'access_token'
                "user": user.to_dict(),
                "login_method": "password"
            }
        )
    except Exception as e:
        logger.error(f"API login error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/auth/register", methods=["POST"])
def register():
    try:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")
        email = data.get("email")
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        student_id = data.get("student_id")
        role = data.get("role", "student")

        if not username or not password:
            return jsonify({"error": "Username and password required"}), 400

        if User.query.filter_by(username=username).first():
            # Log failed registration attempt - username exists
            log_action(
                "register_failed",
                details=f"Failed registration attempt - Username '{username}' already exists",
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            return jsonify({"error": "Username already exists"}), 400

        # Check if student_id already exists
        if student_id and User.query.filter_by(student_id=student_id).first():
            # Log failed registration attempt - student ID exists
            log_action(
                "register_failed",
                details=f"Failed registration attempt - Student ID '{student_id}' already exists",
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            return jsonify({"error": "Student ID already exists"}), 400

        user = User(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            student_id=student_id,
            role=role,
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        # Log successful registration
        log_action(
            "register",
            user.id,
            details=f"New user '{username}' registered successfully with student ID '{student_id}' and role '{role}'",
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )

        return (
            jsonify(
                {"message": "User registered successfully", "user": user.to_dict()}
            ),
            201,
        )

    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/users", methods=["GET"])
@jwt_required()
def get_users():
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)

        users = User.query.paginate(page=page, per_page=per_page, error_out=False)

        return jsonify(
            {
                "users": [user.to_dict() for user in users.items],
                "total": users.total,
                "pages": users.pages,
                "current_page": page,
            }
        )
    except Exception as e:
        logger.error(f"Get users error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/users/<int:user_id>", methods=["GET"])
@jwt_required()
def get_user(user_id):
    try:
        user = User.query.get_or_404(user_id)
        return jsonify({"user": user.to_dict()})
    except Exception as e:
        logger.error(f"Get user error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/lockers", methods=["GET"])
@jwt_required()
def get_lockers():
    try:
        # Sort lockers by name to maintain consistent order
        lockers = Locker.query.order_by(Locker.name).all()
        logger.info(f"Found {len(lockers)} lockers")

        # Get current time for checking active reservations
        now = datetime.utcnow()

        for locker in lockers:
            # Check if locker has any active reservations (including future ones)
            active_reservation = Reservation.query.filter(
                Reservation.locker_id == locker.id, Reservation.status == "active"
            ).first()

            # Update locker status based on reservations
            if active_reservation:
                if locker.status != "reserved":
                    locker.status = "reserved"
            else:
                # If no active reservation but status is reserved, make it available
                if locker.status == "reserved":
                    locker.status = "active"

            logger.info(
                f"Locker: {locker.name} - {locker.number} - Status: {locker.status}"
            )

        # Commit the status changes
        db.session.commit()

        return jsonify([locker.to_dict() for locker in lockers])
    except Exception as e:
        logger.error(f"Get lockers error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/items", methods=["GET"])
@jwt_required()
def get_items():
    try:
        items = Item.query.all()
        return jsonify([item.to_dict() for item in items])
    except Exception as e:
        logger.error(f"Get items error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/borrows", methods=["GET"])
@jwt_required()
def get_borrows():
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)
        status = request.args.get("status")
        user_id = request.args.get("user_id", type=int)

        query = Borrow.query
        if user_id:
            query = query.filter_by(user_id=user_id)
        if status:
            query = query.filter_by(status=status)


        borrows = query.paginate(page=page, per_page=per_page, error_out=False)

        return jsonify(
            {
                "borrows": [borrow.to_dict() for borrow in borrows.items],
                "total": borrows.total,
                "pages": borrows.pages,
                "current_page": page,
            }
        )
    except Exception as e:
        logger.error(f"Get borrows error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/borrows", methods=["POST"])
@jwt_required()
def create_borrow():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        item_id = data.get("item_id")
        locker_id = data.get("locker_id")
        due_date = data.get("due_date")

        if not user_id or not item_id:
            return jsonify({"error": "User ID and Item ID required"}), 400

        # Check if item is available
        item = Item.query.get(item_id)
        if not item or item.status != "available":
            return jsonify({"error": "Item not available"}), 400

        # Create borrow
        borrow = Borrow(
            user_id=user_id,
            item_id=item_id,
            locker_id=item.locker_id,
            due_date=datetime.fromisoformat(due_date) if due_date else None,
            status="borrowed",  # Set status explicitly
        )

        # Update item status
        item.status = "borrowed"

        db.session.add(borrow)
        db.session.commit()

        log_action(
            "borrow", user_id, item_id, item.locker_id, f"Item {item.name} borrowed"
        )

        return (
            jsonify(
                {"message": "Item borrowed successfully", "borrow": borrow.to_dict()}
            ),
            201,
        )

    except Exception as e:
        logger.error(f"Create borrow error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/borrows/<int:borrow_id>/return", methods=["POST"])
@jwt_required()
def return_item(borrow_id):
    try:
        data = request.get_json()
        condition = data.get("condition", "good")
        notes = data.get("notes")

        borrow = Borrow.query.get(borrow_id)
        if not borrow:
            return jsonify({"error": "Borrow not found"}), 404

        if borrow.status != "borrowed":  # Check for 'borrowed' instead of 'active'
            return jsonify({"error": "Borrow is not active"}), 400

        # Update borrow status
        borrow.status = "returned"
        borrow.returned_at = datetime.utcnow()
        borrow.notes = notes

        # Update item status
        item = borrow.item
        item.status = "available"

        db.session.commit()

        log_action(
            "return",
            borrow.user_id,
            borrow.item_id,
            borrow.locker_id,
            f"Item {item.name} returned",
        )

        return jsonify(
            {"message": "Item returned successfully", "borrow": borrow.to_dict()}
        )

    except Exception as e:
        logger.error(f"Return item error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/logs", methods=["GET"])
@jwt_required()
@admin_required
def get_logs():
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 50, type=int)
        action_type = request.args.get("action_type")
        user_id = request.args.get("user_id", type=int)

        query = Log.query
        if action_type:
            query = query.filter_by(action_type=action_type)
        if user_id:
            query = query.filter_by(user_id=user_id)

        logs = query.order_by(Log.timestamp.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        return jsonify(
            {
                "logs": [log.to_dict() for log in logs.items],
                "total": logs.total,
                "pages": logs.pages,
                "current_page": page,
            }
        )
    except Exception as e:
        logger.error(f"Get logs error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/admin/stats", methods=["GET"])
@jwt_required()
@admin_required
def get_stats():
    try:
        total_users = User.query.count()
        total_lockers = Locker.query.count()
        total_items = Item.query.count()
        active_borrows = Borrow.query.filter_by(status="borrowed").count()
        available_items = Item.query.filter_by(status="available").count()
        return jsonify(
            {
                "total_users": total_users,
                "total_lockers": total_lockers,
                "total_items": total_items,
                "active_borrows": active_borrows,
                "available_items": available_items,
            }
        )
    except Exception as e:
        logger.error(f"Get stats error: {e}")
        return jsonify({"error": "Internal server error"}), 500





# Removed duplicate export_logs_alt endpoint - using the one below with common_export


# RS485 Locker Control Endpoints
@app.route("/api/lockers/<int:locker_id>/open", methods=["POST"])
@jwt_required()
@admin_required
def open_locker_endpoint(locker_id):
    """Open a locker using RS485"""
    logger.info("=== BACKEND LOCKER OPEN REQUEST ===")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info(f"Locker ID: {locker_id}")
    logger.info(f"User ID: {get_jwt_identity()}")
    logger.info(f"Request Method: {request.method}")
    logger.info(f"Request URL: {request.url}")
    logger.info(f"Request Headers: {dict(request.headers)}")
    logger.info(f"Request Remote Addr: {request.remote_addr}")
    logger.info(f"Request User Agent: {request.headers.get('User-Agent')}")
    
    try:
        # Check if locker exists
        logger.info("Checking if locker exists...")
        locker = Locker.query.get_or_404(locker_id)
        
        logger.info("=== LOCKER DETAILS ===")
        logger.info(f"Locker ID: {locker.id}")
        logger.info(f"Locker Name: {locker.name}")
        logger.info(f"Locker Number: {locker.number}")
        logger.info(f"Locker Status: {locker.status}")
        logger.info(f"RS485 Address: {locker.rs485_address}")
        logger.info(f"RS485 Locker Number: {locker.rs485_locker_number}")
        logger.info(f"Locker Location: {locker.location}")
        logger.info(f"Locker Description: {locker.description}")
        
        logger.info("=== CALLING RS485 OPEN FUNCTION ===")
        # Open locker using RS485 with locker's configuration
        result = open_locker(
            locker_id,
            address=locker.rs485_address,
            locker_number=locker.rs485_locker_number,
        )
        
        logger.info("=== RS485 RESULT ===")
        logger.info(f"Result: {result}")
        logger.info(f"Success: {result.get('success', 'Not specified')}")
        logger.info(f"Message: {result.get('message', 'Not specified')}")
        logger.info(f"Frame: {result.get('frame', 'Not specified')}")
        logger.info(f"Error: {result.get('error', 'None')}")

        # Log the action
        logger.info("=== LOGGING ACTION ===")
        log_action(
            "open_locker",
            get_jwt_identity(),
            locker_id=locker_id,
            details=f"Locker {locker.name} opened via RS485 - Result: {result.get('success', 'Unknown')}",
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )

        logger.info("=== SENDING RESPONSE ===")
        response_data = {
            "message": "Locker opening command sent",
            "locker_id": locker_id,
            "locker_name": locker.name,
            "success": result.get('success', False),
            "rs485_result": result,
        }
        logger.info(f"Response Data: {response_data}")
        
        return jsonify(response_data)

    except Exception as e:
        logger.error("=== LOCKER OPEN ERROR ===")
        logger.error(f"Error Type: {type(e).__name__}")
        logger.error(f"Error Message: {str(e)}")
        logger.error(f"Error Args: {e.args}")
        import traceback
        logger.error(f"Error Traceback: {traceback.format_exc()}")
        
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@app.route("/api/lockers/open_free", methods=["POST"])
@jwt_required()
def open_free_locker():
    try:
        free = Locker.query.filter_by(current_occupancy=0).first()
        if not free:
            return jsonify({"error": "Aucun casier libre disponible"}), 400

        # Ouvre physiquement ou simule l'ouverture :
        # rs485_controller.open_locker(free.id)

        return jsonify({"message": "Casier libre ouvert", "locker_id": free.id}), 200
    except Exception as e:
        logger.error(f"open_free_locker error: {e}")

        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/lockers/<int:locker_id>/close", methods=["POST"])
@jwt_required()
@admin_required
def close_locker_endpoint(locker_id):
    """Close a locker using RS485"""
    try:
        # Check if locker exists
        locker = Locker.query.get_or_404(locker_id)

        # Close locker using RS485 with locker's configuration
        result = close_locker(
            locker_id,
            address=locker.rs485_address,
            locker_number=locker.rs485_locker_number,
        )

        # Log the action
        log_action(
            "close_locker",
            get_jwt_identity(),
            locker_id=locker_id,
            details=f"Locker {locker.name} closed via RS485",
        )

        return jsonify(
            {
                "message": "Locker closing command sent",
                "locker_id": locker_id,
                "locker_name": locker.name,
                "rs485_result": result,
            }
        )

    except Exception as e:
        logger.error(f"Close locker error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/lockers/<int:locker_id>/confirm_presence", methods=["POST"])
@jwt_required()
def confirm_presence(locker_id):
    """Confirm presence of item in locker after opening"""
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        item_id = data.get("item_id")
        present = data.get("present")

        if user_id is None or item_id is None or present is None:
            return jsonify({"error": "Missing fields"}), 400

        locker = Locker.query.get(locker_id)
        item = Item.query.get(item_id)
        if not locker or not item:
            return jsonify({"error": "Locker or item not found"}), 404

        # If equipment is present
        if present:
            borrow = Borrow(
                user_id=user_id,
                item_id=item_id,
                locker_id=locker_id,
                borrowed_at=datetime.utcnow(),
                status="borrowed"
            )
            db.session.add(borrow)
            item.status = "borrowed"
            db.session.commit()

            log_action(
                "borrow_confirmed",
                user_id=user_id,
                item_id=item_id,
                locker_id=locker_id,
                details=f"Borrow confirmed for item {item.name}"
            )

            return jsonify({
                "message": "Borrow confirmed",
                "borrow_id": borrow.id
            }), 200
        else:
            # If the equipment is missing
            item.status = "missing"
            db.session.commit()

            log_action(
                "item_missing",
                user_id=user_id,
                item_id=item_id,
                locker_id=locker_id,
                details=f"Item {item.name} reported missing"
            )

            return jsonify({"message": "Equipment reported missing"}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in confirm_presence: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/lockers/confirm_return", methods=["POST"])
@jwt_required()
def confirm_return():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        item_id = data.get("item_id")
        condition = data.get("condition", "good")

        # Find a free locker to return the item
        free_locker = Locker.query.filter_by(current_occupancy=0).first()
        if not free_locker:
            return jsonify({"error": "Aucun casier vide disponible"}), 400

        # open the free locker
        print(f"🔓 Ouverture du casier vide {free_locker.id}")
        #rs485_controller.open_locker(free_locker.id)

        # update borrow record
        borrow = Borrow.query.filter_by(item_id=item_id, user_id=user_id, status="borrowed").first()
        if not borrow:
            return jsonify({"error": "Aucun emprunt actif trouvé"}), 400

        borrow.status = "returned"
        borrow.return_date = datetime.utcnow()

        item = Item.query.get(item_id)
        item.status = "available"
        item.condition = condition
        item.locker_id = free_locker.id  # assign item to the free locker

        free_locker.current_occupancy = 1  # locker is now occupied

        db.session.commit()

        log_action("return", user_id, item_id, free_locker.id, f"Item {item.name} returned")

        return jsonify({
            "message": f"Casier {free_locker.id} ouvert pour dépôt",
            "locker_id": free_locker.id
        }), 200

    except Exception as e:
        logger.error(f"Erreur retour : {e}")
        return jsonify({"error": "Erreur interne"}), 500

@app.route("/api/lockers/<int:locker_id>/status", methods=["GET"])
@jwt_required()
@admin_required
def get_locker_status_endpoint(locker_id):
    """Get locker status via RS485"""
    try:
        # Check if locker exists
        locker = Locker.query.get_or_404(locker_id)

        # Get locker status using RS485
        result = get_locker_status(locker_id)

        return jsonify(
            {
                "locker_id": locker_id,
                "locker_name": locker.name,
                "status": result.get("status", "unknown"),  # Add status field for tests
                "rs485_status": result,
            }
        )

    except Exception as e:
        logger.error(f"Get locker status error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/admin/rs485/test", methods=["GET"])
@jwt_required()
@admin_required
def test_rs485_endpoint():
    """Test RS485 connection"""
    try:
        result = test_rs485_connection()
        return jsonify(
            {
                "status": "success",  # Add status field for tests
                "message": "RS485 connection test completed",
                "result": result,
            }
        )

    except Exception as e:
        logger.error(f"RS485 test error: {e}")
        return jsonify({"error": "Internal server error"}), 500


# Admin Locker Management Routes
@app.route("/api/admin/lockers", methods=["POST"])
@jwt_required()
@admin_required
def create_locker():
    try:
        data = request.get_json()
        name = data.get("name")
        number = data.get("number")
        location = data.get("location")
        description = data.get("description")
        capacity = data.get("capacity", 10)
        rs485_address = data.get("rs485_address", 0)
        rs485_locker_number = data.get("rs485_locker_number", 1)

        if not name or not number:
            return jsonify({"error": "Name and number are required"}), 400

        if Locker.query.filter_by(name=name).first():
            return jsonify({"error": "Locker name already exists"}), 400

        if Locker.query.filter_by(number=number).first():
            return jsonify({"error": "Locker number already exists"}), 400

        locker = Locker(
            name=name,
            number=number,
            location=location,
            description=description,
            capacity=capacity,
            rs485_address=rs485_address,
            rs485_locker_number=rs485_locker_number,
        )

        db.session.add(locker)
        db.session.commit()

        # Log locker creation
        current_user_id = get_jwt_identity()
        log_action(
            "admin_action",
            current_user_id,
            locker_id=locker.id,
            details=f"Admin created locker '{name}' (Number: {number})",
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )

        return jsonify({"message": "Locker created successfully", "locker": locker.to_dict()}), 201

    except Exception as e:
        logger.error(f"Create locker error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/admin/lockers/<int:locker_id>", methods=["PUT"])
@jwt_required()
@admin_required
def update_locker(locker_id):
    try:
        locker = Locker.query.get_or_404(locker_id)
        data = request.get_json()

        # Store original values for logging
        original_name = locker.name
        original_number = locker.number

        if "name" in data:
            if Locker.query.filter_by(name=data["name"]).filter(Locker.id != locker_id).first():
                return jsonify({"error": "Locker name already exists"}), 400
            locker.name = data["name"]

        if "number" in data:
            if Locker.query.filter_by(number=data["number"]).filter(Locker.id != locker_id).first():
                return jsonify({"error": "Locker number already exists"}), 400
            locker.number = data["number"]

        if "location" in data:
            locker.location = data["location"]

        if "description" in data:
            locker.description = data["description"]

        if "capacity" in data:
            locker.capacity = data["capacity"]

        if "status" in data:
            locker.status = data["status"]

        if "is_active" in data:
            locker.is_active = data["is_active"]

        if "rs485_address" in data:
            locker.rs485_address = data["rs485_address"]

        if "rs485_locker_number" in data:
            locker.rs485_locker_number = data["rs485_locker_number"]

        db.session.commit()

        # Log locker update
        current_user_id = get_jwt_identity()
        log_action(
            "admin_action",
            current_user_id,
            locker_id=locker.id,
            details=f"Admin updated locker '{original_name}' (Number: {original_number}) to '{locker.name}' (Number: {locker.number})",
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )

        return jsonify({"message": "Locker updated successfully", "locker": locker.to_dict()})

    except Exception as e:
        logger.error(f"Update locker error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/admin/lockers/<int:locker_id>", methods=["DELETE"])
@jwt_required()
@admin_required
def delete_locker(locker_id):
    try:
        locker = Locker.query.get_or_404(locker_id)
        
        # Store locker info for logging before deletion
        locker_name = locker.name
        locker_number = locker.number
        
        db.session.delete(locker)
        db.session.commit()

        # Log locker deletion
        current_user_id = get_jwt_identity()
        log_action(
            "admin_action",
            current_user_id,
            details=f"Admin deleted locker '{locker_name}' (Number: {locker_number})",
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )

        return jsonify({"message": "Locker deleted successfully"})

    except Exception as e:
        logger.error(f"Delete locker error: {e}")
        return jsonify({"error": "Internal server error"}), 500


# Old export endpoints removed - using common_export function now


# Removed duplicate export_borrows endpoint - using the one below with common_export


@app.route("/api/admin/export/system", methods=["GET"])
@jwt_required()
@admin_required
def export_system_report():
    """Export comprehensive system report"""
    try:
        format_type = request.args.get("format", "pdf")
        report_type = request.args.get("type", "comprehensive")

        report_content = export_system_report(db, format_type, report_type)

        if format_type == "csv":
            return Response(
                report_content,
                mimetype="text/csv",
                headers={
                    "Content-Disposition": "attachment; filename=system_report.csv"
                },
            )
        elif format_type == "excel":
            return Response(
                report_content,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={
                    "Content-Disposition": "attachment; filename=system_report.xlsx"
                },
            )
        elif format_type == "pdf":
            return Response(
                report_content,
                mimetype="application/pdf",
                headers={
                    "Content-Disposition": "attachment; filename=system_report.pdf"
                },
            )
        else:
            return jsonify({"error": "Unsupported format"}), 400

    except Exception as e:
        logger.error(f"Export system report error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/admin/reports", methods=["GET"])
@jwt_required()
@admin_required
def get_reports():
    """Generate reports for admin dashboard"""
    try:
        report_type = request.args.get("type", "transactions")
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        date_range = request.args.get("range", "week")

        # Parse dates
        if start_date:
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
        if end_date:
            end_date = datetime.strptime(end_date, "%Y-%m-%d")

        # Generate report data based on type
        if report_type == "transactions":
            # Get all borrows that have either borrow_date or return_date within the range
            query = Borrow.query
            if start_date and end_date:
                # Include transactions where either borrow_date or return_date is within range
                query = query.filter(
                    db.or_(
                        db.and_(Borrow.borrowed_at >= start_date, Borrow.borrowed_at <= end_date),
                        db.and_(Borrow.returned_at >= start_date, Borrow.returned_at <= end_date)
                    )
                )
            elif start_date:
                query = query.filter(
                    db.or_(
                        Borrow.borrowed_at >= start_date,
                        Borrow.returned_at >= start_date
                    )
                )
            elif end_date:
                query = query.filter(
                    db.or_(
                        Borrow.borrowed_at <= end_date,
                        Borrow.returned_at <= end_date
                    )
                )
            all_transactions = query.all()
            # Separate into borrows and returns
            borrows = []
            returns = []
            for transaction in all_transactions:
                if transaction.returned_at is not None:
                    returns.append(transaction)
                else:
                    borrows.append(transaction)
            # Prepare transaction data
            transactions = []
            for borrow in borrows:
                transactions.append({
                    "id": borrow.id,
                    "user": f"{borrow.user.first_name} {borrow.user.last_name}" if borrow.user else "Unknown",
                    "item": borrow.item.name if borrow.item else "Unknown",
                    "action": "borrow",
                    "timestamp": borrow.borrowed_at.isoformat() if borrow.borrowed_at else "",
                    "locker": borrow.locker.name if borrow.locker else "Unknown"
                })
            for borrow in returns:
                transactions.append({
                    "id": borrow.id,
                    "user": f"{borrow.user.first_name} {borrow.user.last_name}" if borrow.user else "Unknown",
                    "item": borrow.item.name if borrow.item else "Unknown",
                    "action": "return",
                    "timestamp": borrow.returned_at.isoformat() if borrow.returned_at else "",
                    "locker": borrow.locker.name if borrow.locker else "Unknown"
                })
            # Sort by timestamp
            transactions.sort(key=lambda x: x["timestamp"], reverse=True)
            # Calculate summary
            summary = {
                "total_transactions": len(transactions),
                "borrows": len(borrows),
                "returns": len(returns),
                "unique_users": len(set(t["user"] for t in transactions)),
                "unique_items": len(set(t["item"] for t in transactions))
            }
            return jsonify({
                "summary": summary,
                "transactions": transactions
            })
            
        elif report_type == "users":
            # Get user statistics
            users = User.query.all()
            user_stats = []
            
            for user in users:
                borrow_count = Borrow.query.filter_by(user_id=user.id).count()
                active_borrows = Borrow.query.filter_by(user_id=user.id, return_date=None).count()
                
                user_stats.append({
                    "id": user.id,
                    "username": user.username,
                    "name": f"{user.first_name} {user.last_name}",
                    "department": user.department,
                    "total_borrows": borrow_count,
                    "active_borrows": active_borrows,
                    "last_activity": user.last_login.isoformat() if user.last_login else ""
                })
            
            return jsonify({
                "summary": {
                    "total_users": len(users),
                    "active_users": len([u for u in user_stats if u["active_borrows"] > 0])
                },
                "users": user_stats
            })
            
        elif report_type == "items":
            # Get item statistics
            items = Item.query.all()
            item_stats = []
            
            for item in items:
                borrow_count = Borrow.query.filter_by(item_id=item.id).count()
                active_borrows = Borrow.query.filter_by(item_id=item.id, return_date=None).count()
                
                item_stats.append({
                    "id": item.id,
                    "name": item.name,
                    "category": item.category,
                    "total_borrows": borrow_count,
                    "active_borrows": active_borrows,
                    "status": "Available" if active_borrows == 0 else "Borrowed"
                })
            
            return jsonify({
                "summary": {
                    "total_items": len(items),
                    "available_items": len([i for i in item_stats if i["active_borrows"] == 0]),
                    "borrowed_items": len([i for i in item_stats if i["active_borrows"] > 0])
                },
                "items": item_stats
            })
        
        else:
            return jsonify({"error": "Unsupported report type"}), 400

    except Exception as e:
        logger.error(f"Generate report error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/admin/export", methods=["GET"])
@jwt_required()
@admin_required
def export_report():
    """Export reports in various formats"""
    try:
        report_type = request.args.get("type", "transactions")
        format_type = request.args.get("format", "excel")
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        date_range = request.args.get("range", "week")

        # Parse dates
        if start_date:
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
        if end_date:
            end_date = datetime.strptime(end_date, "%Y-%m-%d")

        # Generate report data based on type
        if report_type == "transactions":
            # Get borrows and returns
            query = Borrow.query
            if start_date:
                query = query.filter(Borrow.borrowed_at >= start_date)
            if end_date:
                query = query.filter(Borrow.borrowed_at <= end_date)
            
            borrows = query.all()
            
            # Get returns
            returns_query = Borrow.query.filter(Borrow.returned_at.isnot(None))
            if start_date:
                returns_query = returns_query.filter(Borrow.returned_at >= start_date)
            if end_date:
                returns_query = returns_query.filter(Borrow.returned_at <= end_date)
            
            returns = returns_query.all()
            
            # Prepare transaction data
            transactions = []
            for borrow in borrows:
                transactions.append({
                    "ID": borrow.id,
                    "User": f"{borrow.user.first_name} {borrow.user.last_name}" if borrow.user else "Unknown",
                    "Item": borrow.item.name if borrow.item else "Unknown",
                    "Action": "Borrow",
                    "Date": borrow.borrowed_at.strftime("%Y-%m-%d %H:%M:%S") if borrow.borrowed_at else "",
                    "Locker": borrow.locker.name if borrow.locker else "Unknown"
                })
            
            for borrow in returns:
                transactions.append({
                    "ID": borrow.id,
                    "User": f"{borrow.user.first_name} {borrow.user.last_name}" if borrow.user else "Unknown",
                    "Item": borrow.item.name if borrow.item else "Unknown",
                    "Action": "Return",
                    "Date": borrow.returned_at.strftime("%Y-%m-%d %H:%M:%S") if borrow.returned_at else "",
                    "Locker": borrow.locker.name if borrow.locker else "Unknown"
                })
            
            # Sort by date
            transactions.sort(key=lambda x: x["Date"], reverse=True)
            
            # Generate filename with date range
            start_str = start_date.strftime('%Y%m%d') if start_date else 'all'
            end_str = end_date.strftime('%Y%m%d') if end_date else 'all'
            start_display = start_date.strftime('%Y-%m-%d') if start_date else 'All'
            end_display = end_date.strftime('%Y-%m-%d') if end_date else 'All'
            
            if format_type == "excel":
                return Response(
                    export_data_excel(transactions),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=transactions_report_{start_str}_{end_str}.xlsx"}
                )
            elif format_type == "pdf":
                sections = [{
                    "title": f"Transactions Report ({start_display} to {end_display})",
                    "content": transactions
                }]
                return Response(
                    export_data_pdf("Smart Locker Transactions Report", sections),
                    mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=transactions_report_{start_str}_{end_str}.pdf"}
                )
            elif format_type == "csv":
                csv_content = export_data_csv(transactions)
                return Response(
                    csv_content,
                    mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=transactions_report_{start_str}_{end_str}.csv"}
                )
            else:
                return jsonify({"error": "Unsupported format"}), 400
                
        elif report_type == "users":
            # Get user statistics
            users = User.query.all()
            user_stats = []
            
            for user in users:
                borrow_count = Borrow.query.filter_by(user_id=user.id).count()
                active_borrows = Borrow.query.filter_by(user_id=user.id, return_date=None).count()
                
                user_stats.append({
                    "ID": user.id,
                    "Username": user.username,
                    "Name": f"{user.first_name} {user.last_name}",
                    "Department": user.department,
                    "Total Borrows": borrow_count,
                    "Active Borrows": active_borrows,
                    "Last Activity": user.last_login.strftime("%Y-%m-%d %H:%M:%S") if user.last_login else ""
                })
            
            if format_type == "excel":
                return Response(
                    export_data_excel(user_stats),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=users_report.xlsx"}
                )
            elif format_type == "pdf":
                sections = [{
                    "title": "Users Report",
                    "content": user_stats
                }]
                return Response(
                    export_data_pdf("Smart Locker Users Report", sections),
                    mimetype="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=users_report.pdf"}
                )
            elif format_type == "csv":
                csv_content = export_data_csv(user_stats)
                return Response(
                    csv_content,
                    mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=users_report.csv"}
                )
            else:
                return jsonify({"error": "Unsupported format"}), 400
                
        elif report_type == "items":
            # Get item statistics
            items = Item.query.all()
            item_stats = []
            
            for item in items:
                borrow_count = Borrow.query.filter_by(item_id=item.id).count()
                active_borrows = Borrow.query.filter_by(item_id=item.id, return_date=None).count()
                
                item_stats.append({
                    "ID": item.id,
                    "Name": item.name,
                    "Category": item.category,
                    "Total Borrows": borrow_count,
                    "Active Borrows": active_borrows,
                    "Status": "Available" if active_borrows == 0 else "Borrowed"
                })
            
            if format_type == "excel":
                return Response(
                    export_data_excel(item_stats),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=items_report.xlsx"}
                )
            elif format_type == "pdf":
                sections = [{
                    "title": "Items Report",
                    "content": item_stats
                }]
                return Response(
                    export_data_pdf("Smart Locker Items Report", sections),
                    mimetype="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=items_report.pdf"}
                )
            elif format_type == "csv":
                csv_content = export_data_csv(item_stats)
                return Response(
                    csv_content,
                    mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=items_report.csv"}
                )
            else:
                return jsonify({"error": "Unsupported format"}), 400
        
        else:
            return jsonify({"error": "Unsupported report type"}), 400

    except Exception as e:
        logger.error(f"Export report error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        db.session.execute(db.text("SELECT 1"))
        return (
            jsonify(
                {
                    "status": "healthy",
                    "timestamp": datetime.now().isoformat(),
                    "database": "connected",
                }
            ),
            200,
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return (
            jsonify(
                {
                    "status": "unhealthy",
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e),
                }
            ),
            500,
        )


def create_real_lockers_with_rs485():
    """Create 62 lockers with proper RS485 mapping for real data mode"""
    # RS485 mapping for 62 lockers
    rs485_mapping = []
    
    # Lockers 1-14: RS485 Address 1, Locker Numbers 1-14
    for i in range(1, 15):
        rs485_mapping.append({
            'name': f"Locker {i}",
            'number': f"L{i}",
            'rs485_address': 1,
            'rs485_locker_number': i
        })
    
    # Lockers 15-38: RS485 Address 2, Locker Numbers 1-24
    for i in range(15, 39):
        rs485_mapping.append({
            'name': f"Locker {i}",
            'number': f"L{i}",
            'rs485_address': 2,
            'rs485_locker_number': i - 14
        })
    
    # Lockers 39-62: RS485 Address 3, Locker Numbers 1-24
    for i in range(39, 63):
        rs485_mapping.append({
            'name': f"Locker {i}",
            'number': f"L{i}",
            'rs485_address': 3,
            'rs485_locker_number': i - 38
        })
    
    # Create lockers with RS485 mapping
    for mapping in rs485_mapping:
        locker = Locker(
            name=mapping['name'],
            number=mapping['number'],
            location="Main Hall",
            description=f"Locker {mapping['number']} with RS485 Address {mapping['rs485_address']}, Locker Number {mapping['rs485_locker_number']}",
            status="active",
            is_active=True,
            rs485_address=mapping['rs485_address'],
            rs485_locker_number=mapping['rs485_locker_number']
        )
        db.session.add(locker)
    
    db.session.commit()
    logger.info(f"Created 62 lockers with RS485 mapping for real data mode")

def init_db(minimal=False):
    """Initialize the database with default data"""
    with app.app_context():
        db.create_all()

        if not minimal:
            # Generate comprehensive demo data
            generate_dummy_data()
            logger.info(
                "Database initialized with comprehensive demo data (from models.py)"
            )
        else:
            # Minimal admin only - use real tables (empty for now)
            if not User.query.filter_by(username="admin").first():
                admin = User(
                    username="admin",
                    email="admin@smartlocker.com",
                    first_name="Admin",
                    last_name="User",
                    role="admin",
                    department="IT",
                )
                admin.set_password("admin123")
                db.session.add(admin)
                db.session.commit()
                logger.info(
                    "Database initialized with minimal admin user (real tables, empty for now)"
                )


@app.route("/api/admin/active-borrows", methods=["GET"])
@jwt_required()
@admin_required
def get_active_borrows():
    """Get active borrows for admin dashboard"""
    try:
        limit = request.args.get("limit", 25, type=int)
        offset = request.args.get("offset", 0, type=int)

        # Get active borrows with pagination - use 'borrowed' status
        borrows = (
            Borrow.query.filter_by(status="borrowed").offset(offset).limit(limit).all()
        )

        return jsonify(
            {
                "borrows": [borrow.to_dict() for borrow in borrows],
                "total": Borrow.query.filter_by(status="borrowed").count(),
                "limit": limit,
                "offset": offset,
            }
        )
    except Exception as e:
        logger.error(f"Get active borrows error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/admin/users", methods=["GET"])
@jwt_required()
@admin_required
def get_admin_users():
    """Get all users for admin dashboard"""
    try:
        limit = request.args.get("limit", 25, type=int)
        offset = request.args.get("offset", 0, type=int)

        # Get all users with pagination
        users = User.query.offset(offset).limit(limit).all()

        return jsonify(
            {
                "users": [user.to_dict() for user in users],
                "total": User.query.count(),
                "limit": limit,
                "offset": offset,
            }
        )
    except Exception as e:
        logger.error(f"Get admin users error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/admin/users", methods=["POST"])
@jwt_required()
@admin_required
def create_admin_user():
    """Create a new user (admin only)"""
    try:
        data = request.get_json()
        rfid_conflict_warning = False

        # Validate required fields
        required_fields = ["username", "password", "role"]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        # Check if username already exists
        if User.query.filter_by(username=data["username"]).first():
            return jsonify({"error": "Username already exists"}), 400

        # Check if RFID tag already exists (if provided)
        if data.get("rfid_tag"):
            existing_user = User.query.filter_by(rfid_tag=data["rfid_tag"]).first()
            if existing_user:
                # For admin users, allow RFID override but inform about the conflict
                current_admin = User.query.get(get_jwt_identity())
                if current_admin and current_admin.role == "admin":
                    # Log the RFID override during creation
                    try:
                        log_action(
                            "admin_action",
                            user_id=get_jwt_identity(),
                            details=f"RFID override during creation: {data['username']} assigned existing RFID {data['rfid_tag']}",
                            ip_address=request.remote_addr,
                            user_agent=request.headers.get("User-Agent"),
                        )
                    except Exception as log_error:
                        logger.warning(f"Failed to log RFID override during creation: {log_error}")
                    # Remove RFID from previous user
                    existing_user.rfid_tag = None
                    db.session.commit()
                    # Continue with creation but will return warning
                    rfid_conflict_warning = True
                else:
                    return jsonify({"error": "RFID tag already exists"}), 400

        # Create new user
        user = User(
            username=data["username"],
            role=data["role"],
            email=data.get("email"),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            student_id=data.get("student_id"),
            department=data.get("department"),
            rfid_tag=data.get("rfid_tag"),
            qr_code=data.get("qr_code"),
        )
        user.set_password(data["password"])

        db.session.add(user)
        db.session.commit()

        # Log the user creation
        log_action(
            "admin_action",
            user_id=get_jwt_identity(),
            details=f"Created user: {user.username} with role: {user.role}",
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )

        # Return response with warning if there was an RFID conflict
        response_data = {"message": "User created successfully", "user": user.to_dict()}
        if rfid_conflict_warning:
            response_data["warning"] = "RFID tag was already assigned to another user. The override has been applied."
        
        return jsonify(response_data), 201

    except Exception as e:
        logger.error(f"Create admin user error: {e}")
        db.session.rollback()
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/admin/users/<int:user_id>", methods=["PUT"])
@jwt_required()
@admin_required
def update_admin_user(user_id):
    """Update a user (admin only)"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        data = request.get_json()

        # Check if username already exists (if being changed)
        if "username" in data and data["username"] != user.username:
            if User.query.filter(User.username == data["username"], User.id != user_id).first():
                return jsonify({"error": "Username already exists"}), 400

        # Check if RFID tag already exists (if being changed)
        if "rfid_tag" in data and data["rfid_tag"] != user.rfid_tag:
            if data["rfid_tag"] and User.query.filter(User.rfid_tag == data["rfid_tag"], User.id != user_id).first():
                # For admin users, allow RFID override but log it and inform about the conflict
                current_admin = User.query.get(get_jwt_identity())
                if current_admin and current_admin.role == "admin":
                    # Log the RFID override
                    try:
                        log_action(
                            "admin_action",
                            user_id=get_jwt_identity(),
                            details=f"RFID override: {user.username} RFID changed to {data['rfid_tag']} (was {user.rfid_tag})",
                            ip_address=request.remote_addr,
                            user_agent=request.headers.get("User-Agent"),
                        )
                    except Exception as log_error:
                        logger.warning(f"Failed to log RFID override: {log_error}")
                    
                    # Return a warning message for admin about RFID conflict
                    return jsonify({
                        "warning": "RFID tag is already assigned to another user. The override has been applied.",
                        "user": user.to_dict()
                    }), 200
                else:
                    return jsonify({"error": "RFID tag already exists"}), 400

        # Update user fields
        if "username" in data:
            user.username = data["username"]
        if "role" in data:
            user.role = data["role"]
        if "email" in data:
            user.email = data["email"]
        if "first_name" in data:
            user.first_name = data["first_name"]
        if "last_name" in data:
            user.last_name = data["last_name"]
        if "student_id" in data:
            user.student_id = data["student_id"]
        if "department" in data:
            user.department = data["department"]
        if "rfid_tag" in data:
            user.rfid_tag = data["rfid_tag"]
        if "qr_code" in data:
            user.qr_code = data["qr_code"]

        # Update password if provided
        if data.get("password"):
            user.set_password(data["password"])

        db.session.commit()

        # Log the user update
        log_action(
            "admin_action",
            user_id=get_jwt_identity(),
            details=f"Updated user: {user.username}",
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )

        return jsonify({"message": "User updated successfully", "user": user.to_dict()})

    except Exception as e:
        logger.error(f"Update admin user error: {e}")
        db.session.rollback()
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@jwt_required()
@admin_required
def delete_admin_user(user_id):
    """Delete a user (admin only)"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Prevent deletion of admin users
        if user.role == "admin":
            return jsonify({"error": "Cannot delete admin users"}), 400

        username = user.username
        db.session.delete(user)
        db.session.commit()

        # Log the user deletion
        log_action(
            "admin_action",
            user_id=get_jwt_identity(),
            details=f"Deleted user: {username}",
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )

        return jsonify({"message": "User deleted successfully"})

    except Exception as e:
        logger.error(f"Delete admin user error: {e}")
        db.session.rollback()
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/user/profile", methods=["GET"])
@jwt_required()
def get_user_profile():
    """Get current user profile"""
    try:
        current_user_id = get_jwt_identity()
        user = db.session.get(User, current_user_id)

        if not user:
            return jsonify({"error": "User not found"}), 404

        return jsonify(user.to_dict())
    except Exception as e:
        logger.error(f"Get user profile error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/admin/recent-activity", methods=["GET"])
@jwt_required()
@admin_required
def get_recent_activity():
    """Get recent activity for admin dashboard"""
    try:
        limit = request.args.get("limit", 10, type=int)

        # Get recent logs with user information
        recent_logs = (
            db.session.query(Log).order_by(Log.timestamp.desc()).limit(limit).all()
        )

        activity_data = []
        for log in recent_logs:
            user = User.query.get(log.user_id) if log.user_id else None
            activity_data.append(
                {
                    "id": log.id,
                    "action_type": log.action_type,
                    "description": log.notes,  # Use notes instead of details
                    "timestamp": log.timestamp.isoformat(),
                    "user_name": user.username if user else "Unknown",
                    "user_id": log.user_id,
                }
            )

        return jsonify(activity_data)
    except Exception as e:
        logger.error(f"Get recent activity error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/payments", methods=["GET"])
@jwt_required()
def get_payments():
    try:
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)
        Payment = app.config["models"]["Payment"]
        payments = Payment.query.offset(offset).limit(limit).all()
        return jsonify(
            {
                "payments": [p.to_dict() for p in payments],
                "total": Payment.query.count(),
                "limit": limit,
                "offset": offset,
            }
        )
    except Exception as e:
        logger.error(f"Get payments error: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# RESERVATION API ENDPOINTS
# =============================================================================


def update_locker_status_from_reservations():
    """Update locker status based on current reservations"""
    try:
        now = datetime.utcnow()

        # Auto-expire reservations whose end_time is in the past and status is still 'active'
        expired = Reservation.query.filter(
            Reservation.status == "active", Reservation.end_time < now
        ).all()
        for r in expired:
            r.status = "expired"

        # Get all lockers
        lockers = Locker.query.all()

        for locker in lockers:
            # Check if locker has any active reservations
            active_reservation = Reservation.query.filter(
                Reservation.locker_id == locker.id,
                Reservation.status == "active",
                Reservation.start_time <= now,
                Reservation.end_time >= now,
            ).first()

            # Update locker status based on reservations
            if active_reservation:
                if locker.status != "reserved":
                    locker.status = "reserved"
            else:
                # If no active reservation but status is reserved, make it available
                if locker.status == "reserved":
                    locker.status = "active"

        # Commit the status changes
        db.session.commit()

    except Exception as e:
        logger.error(f"Update locker status error: {e}")
        db.session.rollback()


@app.route("/api/reservations", methods=["GET"])
@jwt_required()
def get_reservations():
    """Get reservations with optional filtering"""
    try:
        current_user_id = get_jwt_identity()
        user = db.session.get(User, current_user_id)

        if not user:
            return jsonify({"error": "User not found"}), 404

        # Auto-expire reservations and update locker status
        update_locker_status_from_reservations()

        # Get query parameters
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)
        status_filter = request.args.get("status")

        # Admin can see all reservations, users see only their own
        if user.role == "admin":
            query = Reservation.query
        else:
            query = Reservation.query.filter_by(user_id=current_user_id)

        # Apply status filter if provided
        if status_filter:
            query = query.filter_by(status=status_filter)

        reservations = (
            query.order_by(Reservation.start_time.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return jsonify(
            {
                "reservations": [r.to_dict() for r in reservations],
                "total": query.count(),
                "limit": limit,
                "offset": offset,
            }
        )
    except Exception as e:
        logger.error(f"Get reservations error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/reservations", methods=["POST"])
@jwt_required()
def create_reservation():
    """Create a new reservation"""
    try:
        current_user_id = get_jwt_identity()
        user = db.session.get(User, current_user_id)

        if not user:
            return jsonify({"error": "User not found"}), 404

        data = request.get_json()

        # Validate required fields
        required_fields = ["locker_id", "start_time", "end_time"]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        # Parse datetime strings
        try:
            start_time = parse_datetime_utc(data["start_time"])
            end_time = parse_datetime_utc(data["end_time"])
        except ValueError:
            return jsonify({"error": "Invalid datetime format"}), 400

        # Validate time constraints - compare in UTC
        now = datetime.utcnow()
        # Allow reservations up to 1 minute in the past to account for clock drift
        if start_time < (now - timedelta(minutes=1)):
            return jsonify({"error": "Start time cannot be in the past"}), 400

        if end_time <= start_time:
            return jsonify({"error": "End time must be after start time"}), 400

        # Check maximum duration (7 days)
        duration = end_time - start_time
        if duration > timedelta(days=7):
            return jsonify({"error": "Reservation cannot exceed 7 days"}), 400

        # Check if locker is available for the requested time
        locker = Locker.query.get(data["locker_id"])
        if not locker:
            return jsonify({"error": "Locker not found"}), 404

        if locker.status != "active":
            return jsonify({"error": "Locker is not available for reservation"}), 400

        # Check for conflicts with existing reservations
        conflicting_reservations = Reservation.query.filter(
            Reservation.locker_id == data["locker_id"],
            Reservation.status == "active",
            db.or_(
                db.and_(
                    Reservation.start_time < end_time, Reservation.end_time > start_time
                )
            ),
        ).first()

        if conflicting_reservations:
            return (
                jsonify({"error": "Locker is already reserved for this time period"}),
                400,
            )

        # Create reservation
        reservation = Reservation(
            reservation_code=Reservation.generate_reservation_code(),
            user_id=current_user_id,
            locker_id=data["locker_id"],
            start_time=start_time,
            end_time=end_time,
            access_code=Reservation.generate_access_code(),
            notes=data.get("notes", ""),
            status="active",
        )

        db.session.add(reservation)

        # Update locker status to reserved
        locker.status = "reserved"

        db.session.commit()

        # Log the reservation creation
        log_action(
            "reservation_create",
            user_id=current_user_id,
            locker_id=data["locker_id"],
            details=f"Reservation {reservation.reservation_code} created for locker {locker.name}",
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )

        return (
            jsonify(
                {
                    "message": "Reservation created successfully",
                    "reservation": reservation.to_dict(),
                }
            ),
            201,
        )

    except Exception as e:
        logger.error(f"Create reservation error: {e}")
        db.session.rollback()
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/reservations/<int:reservation_id>", methods=["GET"])
@jwt_required()
def get_reservation(reservation_id):
    """Get a specific reservation"""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)

        if not user:
            return jsonify({"error": "User not found"}), 404

        reservation = Reservation.query.get(reservation_id)
        if not reservation:
            return jsonify({"error": "Reservation not found"}), 404

        # Check access: admin can see all, users can only see their own
        if user.role != "admin" and reservation.user_id != current_user_id:
            return jsonify({"error": "Access denied"}), 403

        return jsonify(reservation.to_dict())

    except Exception as e:
        logger.error(f"Get reservation error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/reservations/<int:reservation_id>", methods=["PUT"])
@jwt_required()
def update_reservation(reservation_id):
    """Update a reservation"""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)

        if not user:
            return jsonify({"error": "User not found"}), 404

        reservation = Reservation.query.get(reservation_id)
        if not reservation:
            return jsonify({"error": "Reservation not found"}), 404

        # Check access: admin can modify all, users can only modify their own
        if user.role != "admin" and reservation.user_id != current_user_id:
            return jsonify({"error": "Access denied"}), 403

        # Only active reservations can be modified
        if reservation.status != "active":
            return jsonify({"error": "Only active reservations can be modified"}), 400

        data = request.get_json()

        # Parse datetime strings if provided
        if "start_time" in data:
            try:
                start_time = parse_datetime_utc(data["start_time"])
            except ValueError:
                return jsonify({"error": "Invalid start_time format"}), 400
        else:
            start_time = reservation.start_time

        if "end_time" in data:
            try:
                end_time = parse_datetime_utc(data["end_time"])
            except ValueError:
                return jsonify({"error": "Invalid end_time format"}), 400
        else:
            end_time = reservation.end_time

        # Validate time constraints
        now = datetime.utcnow()
        # Only enforce 'start time cannot be in the past' on creation, not update
        # if start_time < (now - timedelta(minutes=1)):
        #     return jsonify({"error": "Start time cannot be in the past"}), 400
        if end_time <= start_time:
            return jsonify({"error": "End time must be after start time"}), 400

        # Check maximum duration (7 days)
        duration = end_time - start_time
        if duration > timedelta(days=7):
            return jsonify({"error": "Reservation cannot exceed 7 days"}), 400

        # Check for conflicts with existing reservations (excluding current reservation)
        conflicting_reservations = Reservation.query.filter(
            Reservation.locker_id == reservation.locker_id,
            Reservation.status == "active",
            Reservation.id != reservation_id,
            db.or_(
                db.and_(
                    Reservation.start_time < end_time, Reservation.end_time > start_time
                )
            ),
        ).first()

        if conflicting_reservations:
            return (
                jsonify({"error": "Locker is already reserved for this time period"}),
                400,
            )

        # Update reservation
        reservation.start_time = start_time
        reservation.end_time = end_time
        reservation.notes = data.get("notes", reservation.notes)
        reservation.modified_at = datetime.utcnow()
        reservation.modified_by = current_user_id

        db.session.commit()

        # Log the reservation modification
        log_action(
            "reservation_modify",
            user_id=current_user_id,
            locker_id=reservation.locker_id,
            details=f"Reservation {reservation.reservation_code} modified",
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )

        return jsonify(
            {
                "message": "Reservation updated successfully",
                "reservation": reservation.to_dict(),
            }
        )

    except Exception as e:
        logger.error(f"Update reservation error: {e}")
        db.session.rollback()
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/reservations/<int:reservation_id>/cancel", methods=["POST"])
@jwt_required()
def cancel_reservation(reservation_id):
    """Cancel a reservation"""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)

        if not user:
            return jsonify({"error": "User not found"}), 404

        reservation = Reservation.query.get(reservation_id)
        if not reservation:
            return jsonify({"error": "Reservation not found"}), 404

        # Check access: admin can cancel all, users can only cancel their own
        if user.role != "admin" and reservation.user_id != current_user_id:
            return jsonify({"error": "Access denied"}), 403

        # Only active reservations can be cancelled
        if reservation.status != "active":
            return jsonify({"error": "Only active reservations can be cancelled"}), 400

        # Cancel reservation
        reservation.status = "cancelled"
        reservation.cancelled_at = datetime.utcnow()
        reservation.cancelled_by = current_user_id

        # Update locker status back to active if no other active reservations
        other_active_reservations = Reservation.query.filter(
            Reservation.locker_id == reservation.locker_id,
            Reservation.status == "active",
            Reservation.id != reservation_id,
        ).first()

        if not other_active_reservations:
            locker = Locker.query.get(reservation.locker_id)
            if locker:
                locker.status = "active"

        db.session.commit()

        # Log the reservation cancellation
        log_action(
            "reservation_cancel",
            user_id=current_user_id,
            locker_id=reservation.locker_id,
            details=f"Reservation {reservation.reservation_code} cancelled",
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )

        return jsonify(
            {
                "message": "Reservation cancelled successfully",
                "reservation": reservation.to_dict(),
            }
        )

    except Exception as e:
        logger.error(f"Cancel reservation error: {e}")
        db.session.rollback()
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/reservations/access/<access_code>", methods=["POST"])
@jwt_required()
def access_reservation(access_code):
    """Access a reservation using access code (for RFID/RS485)"""
    try:
        reservation = Reservation.query.filter_by(access_code=access_code).first()
        if not reservation:
            return jsonify({"error": "Invalid access code"}), 404

        # Check if reservation is active
        if reservation.status != "active":
            return jsonify({"error": "Reservation is not active"}), 400

        # Check if reservation is within time window
        now = datetime.utcnow()
        if now < reservation.start_time or now > reservation.end_time:
            return (
                jsonify({"error": "Reservation is not within access time window"}),
                400,
            )

        # Log the access attempt
        log_action(
            "reservation_access",
            user_id=reservation.user_id,
            locker_id=reservation.locker_id,
            details=f"Reservation {reservation.reservation_code} accessed with code {access_code}",
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )

        return jsonify(
            {
                "message": "Access granted",
                "reservation": reservation.to_dict(),
                "locker_id": reservation.locker_id,
            }
        )

    except Exception as e:
        logger.error(f"Access reservation error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/reservations/rfid-access/<rfid_tag>", methods=["POST"])
def rfid_access_reservation(rfid_tag):
    """Access a reservation using RFID tag (no JWT required for RFID access)"""
    try:
        # Find user by RFID tag
        user = User.query.filter_by(rfid_tag=rfid_tag).first()
        if not user:
            return jsonify({"error": "Invalid RFID tag"}), 404

        # Find active reservation for this user
        reservation = (
            Reservation.query.filter_by(user_id=user.id, status="active")
            .filter(
                Reservation.start_time <= datetime.utcnow(),
                Reservation.end_time >= datetime.utcnow(),
            )
            .first()
        )

        if not reservation:
            return (
                jsonify({"error": "No active reservation found for this RFID tag"}),
                404,
            )

        # Log the RFID access attempt
        log_action(
            "reservation_rfid_access",
            user_id=user.id,
            locker_id=reservation.locker_id,
            details=f"Reservation {reservation.reservation_code} accessed with RFID {rfid_tag}",
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )

        return jsonify(
            {
                "message": "RFID access granted",
                "reservation": reservation.to_dict(),
                "user": user.to_dict(),
                "locker_id": reservation.locker_id,
            }
        )

    except Exception as e:
        logger.error(f"RFID access reservation error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/admin/export/payments", methods=["GET"])
@jwt_required()
@admin_required
def export_payments():
    """Export payments data in various formats"""
    def get_payments_data():
        return Payment.query.all()
    
    def format_payments_data(payments):
        payment_data = []
        for payment in payments:
            payment_data.append({
                "ID": payment.id,
                "User": f"{payment.user.first_name} {payment.user.last_name}" if payment.user else "Unknown",
                "Amount": f"${payment.amount:.2f}",
                "Status": payment.status,
                "Description": payment.description,
                "Date": payment.timestamp.strftime("%Y-%m-%d %H:%M:%S") if payment.timestamp else "",
                "Payment Method": payment.method or "Unknown"
            })
        return payment_data
    
    return common_export("payments", get_payments_data, format_payments_data)


@app.route("/api/admin/export/users", methods=["GET"])
@jwt_required()
@admin_required
def export_users():
    """Export users data in various formats"""
    def get_users_data():
        return User.query.all()
    
    def format_users_data(users):
        users_data = []
        for user in users:
            users_data.append({
                "ID": user.id,
                "Username": user.username,
                "Name": f"{user.first_name} {user.last_name}",
                "Email": user.email,
                "Student ID": user.student_id,
                "Role": user.role,
                "Department": user.department,
                "Balance": f"${user.balance:.2f}",
                "Status": "Active" if user.is_active else "Inactive",
                "Created": user.created_at.strftime("%Y-%m-%d %H:%M:%S") if user.created_at else "",
                "RFID Tag": user.rfid_tag or "Not assigned"
            })
        return users_data
    
    return common_export("users", get_users_data, format_users_data)


@app.route("/api/admin/export/items", methods=["GET"])
@jwt_required()
@admin_required
def export_items():
    """Export items data in various formats"""
    def get_items_data():
        return Item.query.all()
    
    def format_items_data(items):
        items_data = []
        for item in items:
            items_data.append({
                "ID": item.id,
                "Name": item.name,
                "Description": item.description,
                "Category": item.category,
                "Status": item.status,
                "Locker": item.locker.name if item.locker else "No locker",
                "Created": item.created_at.strftime("%Y-%m-%d %H:%M:%S") if item.created_at else "",
                "Active": "Yes" if item.is_active else "No"
            })
        return items_data
    
    return common_export("items", get_items_data, format_items_data)


@app.route("/api/admin/export/lockers", methods=["GET"])
@jwt_required()
@admin_required
def export_lockers():
    """Export lockers data in various formats"""
    def get_lockers_data():
        return Locker.query.all()
    
    def format_lockers_data(lockers):
        lockers_data = []
        for locker in lockers:
            lockers_data.append({
                "ID": locker.id,
                "Name": locker.name,
                "Number": locker.number,
                "Location": locker.location,
                "Status": locker.status,
                "Capacity": locker.capacity,
                "Current Occupancy": locker.current_occupancy,
                "RS485 Address": locker.rs485_address,
                "RS485 Locker Number": locker.rs485_locker_number,
                "Active": "Yes" if locker.is_active else "No",
                "Created": locker.created_at.strftime("%Y-%m-%d %H:%M:%S") if locker.created_at else ""
            })
        return lockers_data
    
    return common_export("lockers", get_lockers_data, format_lockers_data)


@app.route("/api/admin/export/borrows", methods=["GET"])
@jwt_required()
@admin_required
def export_borrows():
    """Export borrows data in various formats"""
    def get_borrows_data():
        return Borrow.query.all()
    
    def format_borrows_data(borrows):
        borrows_data = []
        for borrow in borrows:
            borrows_data.append({
                "ID": borrow.id,
                "User": f"{borrow.user.first_name} {borrow.user.last_name}" if borrow.user else "Unknown",
                "Item": borrow.item.name if borrow.item else "Unknown",
                "Locker": borrow.locker.name if borrow.locker else "Unknown",
                "Status": borrow.status,
                "Borrowed At": borrow.borrowed_at.strftime("%Y-%m-%d %H:%M:%S") if borrow.borrowed_at else "",
                "Due Date": borrow.due_date.strftime("%Y-%m-%d %H:%M:%S") if borrow.due_date else "",
                "Returned At": borrow.returned_at.strftime("%Y-%m-%d %H:%M:%S") if borrow.returned_at else "",
                "Notes": borrow.notes or ""
            })
        return borrows_data
    
    return common_export("borrows", get_borrows_data, format_borrows_data)


@app.route("/api/admin/export/reservations", methods=["GET"])
@jwt_required()
@admin_required
def export_reservations():
    """Export reservations data in various formats"""
    def get_reservations_data():
        status_filter = request.args.get("status", None)
        query = Reservation.query
        if status_filter:
            query = query.filter_by(status=status_filter)
        return query.all()
    
    def format_reservations_data(reservations):
        reservations_data = []
        for reservation in reservations:
            reservations_data.append({
                "ID": reservation.id,
                "User": f"{reservation.user.first_name} {reservation.user.last_name}" if reservation.user else "Unknown",
                "Locker": reservation.locker.name if reservation.locker else "Unknown",
                "Status": reservation.status,
                "Start Time": reservation.start_time.strftime("%Y-%m-%d %H:%M:%S") if reservation.start_time else "",
                "End Time": reservation.end_time.strftime("%Y-%m-%d %H:%M:%S") if reservation.end_time else "",
                "Notes": reservation.notes or "",
                "Created": reservation.created_at.strftime("%Y-%m-%d %H:%M:%S") if reservation.created_at else "",
                "Modified By": f"{reservation.modified_by_user.first_name} {reservation.modified_by_user.last_name}" if reservation.modified_by_user else "",
                "Cancelled By": f"{reservation.cancelled_by_user.first_name} {reservation.cancelled_by_user.last_name}" if reservation.cancelled_by_user else ""
            })
        return reservations_data
    
    return common_export("reservations", get_reservations_data, format_reservations_data)


@app.route("/api/admin/export/logs", methods=["GET"])
@jwt_required()
@admin_required
def export_logs_new():
    """Export logs data in various formats using common function"""
    def get_logs_data():
        return Log.query.order_by(Log.timestamp.desc()).all()
    
    def format_logs_data(logs):
        logs_data = []
        for log in logs:
            logs_data.append({
                "ID": log.id,
                "User": f"{log.user.first_name} {log.user.last_name}" if log.user else "",
                "Item": log.item.name if log.item else "",
                "Locker": log.locker.name if log.locker else "",
                "Action": log.action_type,
                "Details": log.notes,
                "IP Address": log.ip_address,
                "User Agent": log.user_agent,
                "Timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S") if log.timestamp else ""
            })
        return logs_data
    
    return common_export("logs", get_logs_data, format_logs_data)





if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Smart Locker System")
    parser.add_argument("--port", type=int, default=5050, help="Port to run on")
    parser.add_argument("--host", default="0.0.0.0", help="Host to run on")
    parser.add_argument("--init-db", action="store_true", help="Initialize database")
    parser.add_argument(
        "--minimal",
        action="store_true",
        help="Run in minimal mode (no demo data, only admin user and empty lockers)",
    )
    parser.add_argument(
        "--demo", action="store_true", help="Load demo data (not minimal)"
    )
    parser.add_argument(
        "--reset-db", action="store_true", help="Drop and recreate all tables"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable verbose (DEBUG) logging"
    )
    parser.add_argument(
        "--rs485-real", action="store_true", help="Enable real RS485 hardware mode (disable mock mode)"
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        for handler in logger.handlers:
            handler.setLevel(logging.DEBUG)
        logging.getLogger().setLevel(logging.DEBUG)

    # Set RS485 mode - default is real hardware
    if args.rs485_real:
        os.environ['RS485_MOCK_MODE'] = 'false'
        logger.info("RS485 real hardware mode enabled")
    else:
        # Default to real hardware mode
        os.environ['RS485_MOCK_MODE'] = 'false'
        logger.info("RS485 real hardware mode enabled (default)")

    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)

    # Only reset database if explicitly requested with --reset-db
    if "--reset-db" in sys.argv:
        with app.app_context():
            db.drop_all()
            db.create_all()
            logger.info("Dropped and recreated all tables to match latest models.")
    # Handle --reset-db or --init-db
    if args.reset_db or args.init_db:
        print("Initializing database...")
        minimal = args.minimal or not args.demo
        with app.app_context():
            db.create_all()
            if not User.query.filter_by(username="admin").first():
                admin = User(
                    username="admin",
                    email="admin@smartlocker.com",
                    first_name="Admin",
                    last_name="User",
                    role="admin",
                    department="IT",
                )
                admin.set_password("admin123")
                db.session.add(admin)
                db.session.commit()
                print("Created admin user")

            if minimal:
                # Create 62 lockers with RS485 mapping for real data mode
                create_real_lockers_with_rs485()
                print(f"Created 62 lockers with RS485 mapping for real data mode")
            else:
                generate_dummy_data(force_regenerate=args.reset_db)
        print("Database initialization complete!")
    elif args.demo:
        print("Loading demo data...")
        with app.app_context():
            db.create_all()
            if not User.query.filter_by(username="admin").first():
                admin = User(
                    username="admin",
                    email="admin@smartlocker.com",
                    first_name="Admin",
                    last_name="User",
                    role="admin",
                    department="IT",
                )
                admin.set_password("admin123")
                db.session.add(admin)
                db.session.commit()
                print("Created admin user")
            generate_dummy_data(force_regenerate=False)
        print("Demo data loaded!")
    elif args.minimal:
        print("Minimal mode: admin user and 62 lockers with RS485 mapping.")
        with app.app_context():
            db.create_all()
            if not User.query.filter_by(username="admin").first():
                admin = User(
                    username="admin",
                    email="admin@smartlocker.com",
                    first_name="Admin",
                    last_name="User",
                    role="admin",
                    department="IT",
                )
                admin.set_password("admin123")
                db.session.add(admin)
                db.session.commit()
                print("Created admin user")

            # Create 62 lockers with RS485 mapping
            create_real_lockers_with_rs485()
            print(f"Created 62 lockers with RS485 mapping for minimal mode")
        print("Minimal DB initialized!")
    else:
        # Default mode: real data with 62 lockers and RS485 mapping
        print("Real data mode: initializing with 62 lockers and RS485 mapping...")
        with app.app_context():
            db.create_all()
            if not User.query.filter_by(username="admin").first():
                admin = User(
                    username="admin",
                    email="admin@smartlocker.com",
                    first_name="Admin",
                    last_name="User",
                    role="admin",
                    department="IT",
                )
                admin.set_password("admin123")
                db.session.add(admin)
                db.session.commit()
                print("Created admin user")
            
            # Check if lockers already exist
            if Locker.query.count() == 0:
                create_real_lockers_with_rs485()
                print("Created 62 lockers with RS485 mapping for real data mode")
            else:
                print(f"Database already contains {Locker.query.count()} lockers")
        print("Real data mode initialized!")

    print(f"Starting Smart Locker System on {args.host}:{args.port}")
    if args.minimal:
        print("Running in minimal mode (admin user, 62 lockers with RS485 mapping)")
    elif args.demo:
        print("Loading comprehensive demo data")
    else:
        print("Running in real data mode (62 lockers with RS485 mapping)")
    app.run(host=args.host, port=args.port, debug=True)
