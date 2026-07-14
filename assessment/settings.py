import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

# Load environment variables from .env
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Security
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-development-key-change-me')
DEBUG = os.getenv('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'silk',                     # Section 1 – profiling
    'rest_framework',           # (optional) for API views

    # Local apps
    'apps.orders',              # Section 1
    'apps.queuee',               # Section 2
    'apps.tenants',             # Section 3
    'apps.shared',              # Shared Redis client
]

MIDDLEWARE = [
    'silk.middleware.SilkyMiddleware',          # Must come before CommonMiddleware
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    # Custom tenant middleware (Section 3) – after auth so we can use request.user if needed
    'apps.tenants.middleware.TenantMiddleware',
]

ROOT_URLCONF = 'assessment.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'assessment.wsgi.application'

# Database – default to SQLite, but you can set DATABASE_URL in .env
DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Redis (for Celery & rate limiter) ---
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# --- Celery Configuration ---
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# Critical for SIGKILL resilience (Section 2)
CELERY_TASK_ACKS_LATE = True                      # Task is acked only after completion
CELERY_TASK_REJECT_ON_WORKER_LOST = True          # Re-queue if worker dies
CELERY_TASK_TRACK_STARTED = True                  # Track started status (useful for monitoring)
CELERY_TASK_SEND_SENT_EVENT = True

# Default retry settings (can be overridden per task)
CELERY_TASK_DEFAULT_RETRY_DELAY = 30              # seconds
CELERY_TASK_MAX_RETRIES = 5

# --- django-silk (Section 1) ---
SILKY_PYTHON_PROFILER = True
SILKY_AUTHENTICATION = False        # Set to True if you want to restrict access
SILKY_AUTHORISATION = False
SILKY_INTERCEPT_FUNC = lambda request: request.path.startswith('/api/')  # Only profile API

# --- Logging (optional) ---
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
}

# --- Rest Framework (optional) ---
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
}