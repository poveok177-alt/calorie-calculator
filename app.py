from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
from collections import OrderedDict
import json
import os
import uuid
import hashlib
import time
from dotenv import load_dotenv

load_dotenv()

try:
    from yookassa import Configuration, Payment
    Configuration.account_id = os.getenv('YOOKASSA_SHOP_ID')
    Configuration.secret_key = os.getenv('YOOKASSA_SECRET_KEY')
except ImportError:
    Payment = None

app = Flask(__name__)

@app.route("/health")
def health():
    return "OK", 200

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'mojasupertajnayastrokakotoruyaniktonevzlomaet123')
app.config['SESSION_TYPE'] = 'filesystem'

database_url = os.environ.get('DATABASE_URL', 'sqlite:///calories.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ===================== DB MODELS =====================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    language = db.Column(db.String(10), default='ru')
    is_premium = db.Column(db.Boolean, default=False)
    is_superuser = db.Column(db.Boolean, default=False)
    premium_ends = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    current_weight = db.Column(db.Float, nullable=True)
    goal_weight = db.Column(db.Float, nullable=True)
    height = db.Column(db.Float, nullable=True)
    daily_calorie_goal = db.Column(db.Integer, default=2000)
    water_goal = db.Column(db.Integer, default=8)
    protein_goal = db.Column(db.Integer, default=150)
    fat_goal = db.Column(db.Integer, default=70)
    carbs_goal = db.Column(db.Integer, default=250)
    age = db.Column(db.Integer, default=25)
    gender = db.Column(db.String(10), default='male')
    activity = db.Column(db.String(20), default='moderate')
    trial_used = db.Column(db.Boolean, default=False)
    trial_ends = db.Column(db.DateTime, nullable=True)
    email_reminders = db.Column(db.Boolean, default=True)
    favorites = db.Column(db.Text, default='[]')
    entries = db.relationship('FoodEntry', backref='user', lazy=True)

class Food(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name_ru = db.Column(db.String(200), nullable=False)
    name_en = db.Column(db.String(200), nullable=False)
    name_uk = db.Column(db.String(200), nullable=True)
    name_kk = db.Column(db.String(200), nullable=True)
    calories = db.Column(db.Float, nullable=False)
    protein = db.Column(db.Float, default=0)
    fat = db.Column(db.Float, default=0)
    carbs = db.Column(db.Float, default=0)
    category = db.Column(db.String(50), nullable=False)

class FoodEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    food_id = db.Column(db.Integer, db.ForeignKey('food.id'), nullable=False)
    food_name = db.Column(db.String(200))
    grams = db.Column(db.Float, nullable=False)
    calories = db.Column(db.Float, nullable=False)
    protein = db.Column(db.Float, default=0)
    fat = db.Column(db.Float, default=0)
    carbs = db.Column(db.Float, default=0)
    date = db.Column(db.Date, default=date.today)
    meal_type = db.Column(db.String(20), default='other')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    food = db.relationship('Food')

class CustomFood(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    calories = db.Column(db.Float, nullable=False)
    protein = db.Column(db.Float, default=0)
    fat = db.Column(db.Float, default=0)
    carbs = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class WeightLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, default=date.today, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ===================== DB INIT =====================

def init_db():
    with app.app_context():
        try:
            inspector = db.inspect(db.engine)
            if 'user' not in inspector.get_table_names():
                return
            user_columns = [col['name'] for col in inspector.get_columns('user')]
            new_columns = [
                ('favorites', "TEXT DEFAULT '[]'"),
                ('trial_used', 'BOOLEAN DEFAULT FALSE'),
                ('trial_ends', 'TIMESTAMP'),
                ('email_reminders', 'BOOLEAN DEFAULT TRUE'),
                ('is_premium', 'BOOLEAN DEFAULT FALSE'),
                ('is_superuser', 'BOOLEAN DEFAULT FALSE'),
                ('premium_ends', 'TIMESTAMP'),
                ('current_weight', 'FLOAT'),
                ('goal_weight', 'FLOAT'),
                ('height', 'FLOAT'),
                ('daily_calorie_goal', 'INTEGER DEFAULT 2000'),
                ('water_goal', 'INTEGER DEFAULT 8'),
                ('protein_goal', 'INTEGER DEFAULT 150'),
                ('fat_goal', 'INTEGER DEFAULT 70'),
                ('carbs_goal', 'INTEGER DEFAULT 250'),
                ('age', 'INTEGER DEFAULT 25'),
                ('gender', "VARCHAR(10) DEFAULT 'male'"),
                ('activity', "VARCHAR(20) DEFAULT 'moderate'"),
                ('language', "VARCHAR(10) DEFAULT 'ru'"),
            ]
            with db.engine.connect() as conn:
                for col_name, col_def in new_columns:
                    if col_name not in user_columns:
                        try:
                            conn.execute(db.text(f'ALTER TABLE "user" ADD COLUMN {col_name} {col_def}'))
                            conn.commit()
                        except Exception as e:
                            conn.rollback()
        except Exception as e:
            pass

# ===================== TRANSLATIONS =====================

TRANSLATIONS = {
    'ru': {
        'app_name': 'CaloriMint',
        'tagline': 'Ваше тело - ваша забота',
        'login': 'Вход',
        'register': 'Регистрация',
        'email': 'Email',
        'password': 'Пароль',
        'username': 'Имя пользователя',
        'no_account': 'Нет аккаунта?',
        'have_account': 'Есть аккаунт?',
        'today': 'Сегодня',
        'history': 'История',
        'goals': 'Цели',
        'premium': 'Premium',
        'logout': 'Выход',
        'calories': 'Калории',
        'protein': 'Белки',
        'fat': 'Жиры',
        'carbs': 'Углеводы',
        'kcal': 'ккал',
        'g': 'г',
        'ml': 'мл',
        'of': 'из',
        'water': 'Вода',
        'cups': 'чашек',
        'breakfast': 'Завтрак',
        'lunch': 'Обед',
        'dinner': 'Ужин',
        'snack': 'Перекус',
        'search_placeholder': 'Ищите продукты...',
        'all': 'Все',
        'categories': 'Категории',
        'clear': 'Очистить',
        'clear_day': 'Очистить день',
        'delete_entry_confirm': 'Удалить этот продукт?',
        'clear_meal_confirm': 'Очистить этот приём пищи?',
        'clear_day_confirm': 'Очистить весь день?',
        'quick_loading': 'Загрузка...',
        'not_found': 'Ничего не найдено',
        'load_error': 'Ошибка загрузки',
        'weight_label': 'Вес (г)',
        'volume_label': 'Объём (мл)',
        'total': 'Итого',
        'confirm_add': 'Добавить',
        'cancel': 'Отмена',
    },
    'en': {
        'app_name': 'CaloriMint',
        'tagline': 'Your body, your care',
        'login': 'Login',
        'register': 'Register',
        'email': 'Email',
        'password': 'Password',
        'username': 'Username',
        'no_account': 'No account?',
        'have_account': 'Have an account?',
        'today': 'Today',
        'history': 'History',
        'goals': 'Goals',
        'premium': 'Premium',
        'logout': 'Logout',
        'calories': 'Calories',
        'protein': 'Protein',
        'fat': 'Fat',
        'carbs': 'Carbs',
        'kcal': 'kcal',
        'g': 'g',
        'ml': 'ml',
        'of': 'of',
        'water': 'Water',
        'cups': 'cups',
        'breakfast': 'Breakfast',
        'lunch': 'Lunch',
        'dinner': 'Dinner',
        'snack': 'Snack',
        'search_placeholder': 'Search products...',
        'all': 'All',
        'categories': 'Categories',
        'clear': 'Clear',
        'clear_day': 'Clear day',
        'delete_entry_confirm': 'Delete this product?',
        'clear_meal_confirm': 'Clear this meal?',
        'clear_day_confirm': 'Clear entire day?',
        'quick_loading': 'Loading...',
        'not_found': 'Nothing found',
        'load_error': 'Load error',
        'weight_label': 'Weight (g)',
        'volume_label': 'Volume (ml)',
        'total': 'Total',
        'confirm_add': 'Add',
        'cancel': 'Cancel',
    }
}

def get_lang():
    if current_user.is_authenticated:
        return current_user.language or 'ru'
    return session.get('lang', 'ru')

# ===================== OPEN FOOD FACTS API =====================

_off_cache = {}
_cache_timestamps = {}
_cache_ttl = 3600

def _get_cache_key(query, lang):
    raw = f"{query.lower().strip()}:{lang}"
    return hashlib.md5(raw.encode()).hexdigest()

def _is_cache_valid(cache_key):
    if cache_key not in _cache_timestamps:
        return False
    return (time.time() - _cache_timestamps[cache_key]) < _cache_ttl

def search_openfoodfacts(query, lang='ru', page_size=50):
    import requests as req
    
    cache_key = _get_cache_key(query, lang)
    if cache_key in _off_cache and _is_cache_valid(cache_key):
        return _off_cache[cache_key]

    lang_map = {'ru': 'ru', 'en': 'en', 'uk': 'uk', 'kk': 'kk'}
    search_lc = lang_map.get(lang, 'en')
    name_fields_by_lang = {
        'ru': ['product_name_ru', 'product_name_en', 'product_name'],
        'en': ['product_name_en', 'product_name', 'product_name_ru'],
        'uk': ['product_name_uk', 'product_name_ru', 'product_name_en', 'product_name'],
        'kk': ['product_name_kk', 'product_name_ru', 'product_name_en', 'product_name'],
    }
    preferred_fields = name_fields_by_lang.get(lang, name_fields_by_lang['en'])

    try:
        url = 'https://world.openfoodfacts.org/cgi/search.pl'
        params = {
            'search_terms': query,
            'search_simple': 1,
            'action': 'process',
            'json': 1,
            'page_size': page_size,
            'lc': search_lc,
            'fields': 'code,product_name,product_name_ru,product_name_en,product_name_uk,product_name_kk,nutriments,categories_tags,brands,quantity,image_front_small_url'
        }
        resp = req.get(url, params=params, timeout=8, headers={'User-Agent': 'CaloriMint/2.0'})
        
        if resp.status_code != 200:
            return []

        data = resp.json()
        results = []
        seen_names = set()

        for p in data.get('products', []):
            n = p.get('nutriments', {})
            cal = n.get('energy-kcal_100g') or n.get('energy-kcal') or (n.get('energy_100g', 0) / 4.184 if n.get('energy_100g') else 0)
            
            if not cal or cal <= 0:
                continue

            protein = float(n.get('proteins_100g') or n.get('proteins') or 0)
            fat = float(n.get('fat_100g') or n.get('fat') or 0)
            carbs = float(n.get('carbohydrates_100g') or n.get('carbohydrates') or 0)

            display_name = ''
            for field in preferred_fields:
                v = p.get(field, '').strip()
                if v:
                    display_name = v
                    break
            
            if not display_name:
                continue

            name_key = display_name.lower()
            if name_key in seen_names:
                continue
            seen_names.add(name_key)

            barcode = str(p.get('code', ''))[:13]
            off_id = f'off_{barcode}' if barcode else f'off_nob_{len(results)}'

            results.append({
                'id': off_id,
                'name_ru': display_name,
                'name_en': p.get('product_name_en') or p.get('product_name') or display_name,
                'calories': round(float(cal), 1),
                'protein': round(protein, 1),
                'fat': round(fat, 1),
                'carbs': round(carbs, 1),
                'category': 'other',
                'source': 'off',
            })

        _off_cache[cache_key] = results
        _cache_timestamps[cache_key] = time.time()
        return results
    except Exception as e:
        return []

# ===================== ROUTES =====================

@app.before_request
def before_request():
    try:
        if current_user.is_authenticated:
            session['lang'] = current_user.language or 'ru'
        elif 'lang' not in session:
            session['lang'] = 'ru'
    except:
        pass
    try:
        if current_user.is_authenticated and current_user.is_premium:
            if current_user.premium_ends and current_user.premium_ends < datetime.utcnow():
                current_user.is_premium = False
                current_user.premium_ends = None
                db.session.commit()
    except:
        pass

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    lang = current_user.language or 'ru'
    today = date.today()
    entries = FoodEntry.query.filter_by(user_id=current_user.id, date=today).all()
    meals = {
        'breakfast': {'name': 'Завтрак', 'icon': '🌅', 'total': 0, 'entries': []},
        'lunch': {'name': 'Обед', 'icon': '☀️', 'total': 0, 'entries': []},
        'dinner': {'name': 'Ужин', 'icon': '🌙', 'total': 0, 'entries': []},
        'snack': {'name': 'Перекус', 'icon': '🍿', 'total': 0, 'entries': []},
    }
    total_calories = total_protein = total_fat = total_carbs = 0
    for entry in entries:
        meal_type = entry.meal_type or 'snack'
        if meal_type in meals:
            meals[meal_type]['entries'].append({'id': entry.id, 'name': entry.food_name, 'grams': entry.grams, 'calories': entry.calories})
            meals[meal_type]['total'] += entry.calories
        total_calories += entry.calories
        total_protein += entry.protein
        total_fat += entry.fat
        total_carbs += entry.carbs
    streak = 0
    check = today
    while True:
        has_entry = FoodEntry.query.filter_by(user_id=current_user.id, date=check).first()
        if has_entry:
            streak += 1
            check = check - timedelta(days=1)
        else:
            break
    
    t = TRANSLATIONS.get(lang, TRANSLATIONS['ru'])
    return render_template('index.html', meals=meals, total_calories=int(total_calories), total_protein=int(total_protein), total_fat=int(total_fat), total_carbs=int(total_carbs), lang=lang, streak=streak, t=t, current_user=current_user)

@app.route('/api/search', methods=['GET'])
@login_required
def search_foods():
    query = request.args.get('q', '').strip().lower()
    category = request.args.get('category', '').strip()
    show_all = request.args.get('show_all', '')
    lang = current_user.language or 'ru'
    if not query and not category and not show_all:
        return jsonify([])
    from food_data import food_data
    results = []
    if category or show_all:
        for idx, food in enumerate(food_data):
            if category and food.get('category') != category:
                continue
            if query:
                haystack = ' '.join([food.get('name_ru', ''), food.get('name_en', ''), food.get('name_uk', ''), food.get('name_kk', '')]).lower()
                if query not in haystack:
                    continue
            results.append({'id': idx, 'name_ru': food['name_ru'], 'name_en': food.get('name_en', food['name_ru']), 'calories': food['calories'], 'protein': food.get('protein', 0), 'fat': food.get('fat', 0), 'carbs': food.get('carbs', 0), 'category': food.get('category', 'other'), 'source': 'local'})
    if query:
        off_results = search_openfoodfacts(query, lang, page_size=50)
        local_names = {r['name_ru'].lower() for r in results}
        for item in off_results:
            if item['name_ru'].lower() not in local_names:
                results.append(item)
                local_names.add(item['name_ru'].lower())
    elif show_all:
        off_results = search_openfoodfacts('bread milk cheese', lang, page_size=30)
        local_names = {r['name_ru'].lower() for r in results[:100]}
        for item in off_results:
            if item['name_ru'].lower() not in local_names and len(results) < 200:
                results.append(item)
                local_names.add(item['name_ru'].lower())
    local_items = [r for r in results if r['source'] == 'local']
    off_items = [r for r in results if r['source'] != 'local']
    final_results = local_items + off_items
    return jsonify(final_results[:50])

@app.route('/api/search-off', methods=['GET'])
@login_required
def search_foods_off():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])
    lang = current_user.language or 'ru'
    results = search_openfoodfacts(query, lang, page_size=50)
    return jsonify(results[:50])

@app.route('/api/add-entry', methods=['POST'])
@login_required
def add_entry():
    data = request.get_json()
    food_id = data.get('food_id')
    grams = float(data.get('grams', 100))
    meal_type = data.get('meal_type', 'snack')
    if isinstance(food_id, str) and (food_id.startswith('off_') or food_id.startswith('custom_')):
        cal_per_100 = float(data.get('calories', 0))
        protein_per_100 = float(data.get('protein', 0))
        fat_per_100 = float(data.get('fat', 0))
        carbs_per_100 = float(data.get('carbs', 0))
        food_name = data.get('food_name', 'Unknown')
        multiplier = grams / 100
        entry = FoodEntry(user_id=current_user.id, food_id=0, food_name=food_name, grams=grams, calories=cal_per_100 * multiplier, protein=protein_per_100 * multiplier, fat=fat_per_100 * multiplier, carbs=carbs_per_100 * multiplier, meal_type=meal_type, date=date.today())
        db.session.add(entry)
        db.session.commit()
        return jsonify({'success': True})
    from food_data import food_data
    food_id = int(food_id)
    if food_id < 0 or food_id >= len(food_data):
        return jsonify({'error': 'Invalid food'}), 400
    food = food_data[food_id]
    multiplier = grams / 100
    entry = FoodEntry(user_id=current_user.id, food_id=food_id, food_name=food['name_ru'], grams=grams, calories=food['calories'] * multiplier, protein=food.get('protein', 0) * multiplier, fat=food.get('fat', 0) * multiplier, carbs=food.get('carbs', 0) * multiplier, meal_type=meal_type, date=date.today())
    db.session.add(entry)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/delete-entry/<int:entry_id>', methods=['DELETE'])
@login_required
def delete_entry(entry_id):
    entry = FoodEntry.query.filter_by(id=entry_id, user_id=current_user.id).first()
    if not entry:
        return jsonify({'error': 'Not found'}), 404
    db.session.delete(entry)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/clear-meal', methods=['POST'])
@login_required
def clear_meal():
    data = request.get_json()
    meal_type = data.get('meal_type')
    entries = FoodEntry.query.filter_by(user_id=current_user.id, meal_type=meal_type, date=date.today()).all()
    for entry in entries:
        db.session.delete(entry)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/clear-day', methods=['DELETE'])
@login_required
def clear_day():
    entries = FoodEntry.query.filter_by(user_id=current_user.id, date=date.today()).all()
    for entry in entries:
        db.session.delete(entry)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/recent', methods=['GET'])
@login_required
def get_recent():
    from food_data import food_data
    entries = FoodEntry.query.filter_by(user_id=current_user.id).order_by(FoodEntry.created_at.desc()).limit(50).all()
    seen = set()
    results = []
    for entry in entries:
        if entry.food_id == 0 or entry.food_id in seen or entry.food_id >= len(food_data):
            continue
        seen.add(entry.food_id)
        food = food_data[entry.food_id]
        results.append({'id': entry.food_id, 'name_ru': food['name_ru'], 'calories': food['calories'], 'protein': food.get('protein', 0), 'fat': food.get('fat', 0), 'carbs': food.get('carbs', 0)})
        if len(results) >= 10:
            break
    return jsonify(results)

@app.route('/api/favorites', methods=['GET'])
@login_required
def get_favorites():
    from food_data import food_data
    fav_ids = json.loads(current_user.favorites or '[]')
    results = []
    for fid in fav_ids:
        if isinstance(fid, int) and 0 <= fid < len(food_data):
            food = food_data[fid]
            results.append({'id': fid, 'name_ru': food['name_ru'], 'calories': food['calories'], 'protein': food.get('protein', 0), 'fat': food.get('fat', 0), 'carbs': food.get('carbs', 0)})
    return jsonify(results)

@app.route('/api/favorites', methods=['POST'])
@login_required
def add_favorite():
    data = request.get_json()
    food_id = data.get('food_id')
    fav_ids = json.loads(current_user.favorites or '[]')
    if food_id not in fav_ids:
        fav_ids.append(food_id)
    current_user.favorites = json.dumps(fav_ids)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/favorites/<int:food_id>', methods=['DELETE'])
@login_required
def remove_favorite(food_id):
    fav_ids = json.loads(current_user.favorites or '[]')
    if food_id in fav_ids:
        fav_ids.remove(food_id)
    current_user.favorites = json.dumps(fav_ids)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/custom-foods', methods=['GET'])
@login_required
def get_custom_foods():
    foods = CustomFood.query.filter_by(user_id=current_user.id).order_by(CustomFood.created_at.desc()).all()
    return jsonify([{'id': f'custom_{f.id}', 'name_ru': f.name, 'calories': f.calories, 'protein': f.protein, 'fat': f.fat, 'carbs': f.carbs, 'source': 'custom'} for f in foods])

@app.route('/api/custom-foods', methods=['POST'])
@login_required
def create_custom_food():
    if not current_user.is_premium:
        count = CustomFood.query.filter_by(user_id=current_user.id).count()
        if count >= 3:
            return jsonify({'error': 'limit_reached', 'limit': 3}), 403
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400
    f = CustomFood(user_id=current_user.id, name=name, calories=float(data.get('calories', 0)), protein=float(data.get('protein', 0)), fat=float(data.get('fat', 0)), carbs=float(data.get('carbs', 0)))
    db.session.add(f)
    db.session.commit()
    return jsonify({'success': True, 'id': f'custom_{f.id}'})

@app.route('/api/custom-foods/<int:food_id>', methods=['DELETE'])
@login_required
def delete_custom_food(food_id):
    f = CustomFood.query.filter_by(id=food_id, user_id=current_user.id).first()
    if not f:
        return jsonify({'error': 'Not found'}), 404
    db.session.delete(f)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/weight-log', methods=['GET'])
@login_required
def get_weight_log():
    days = int(request.args.get('days', 30))
    since = date.today() - timedelta(days=days)
    logs = WeightLog.query.filter(WeightLog.user_id == current_user.id, WeightLog.date >= since).order_by(WeightLog.date.asc()).all()
    return jsonify([{'date': l.date.strftime('%Y-%m-%d'), 'weight': l.weight} for l in logs])

@app.route('/api/weight-log', methods=['POST'])
@login_required
def add_weight_log():
    data = request.get_json()
    weight = float(data.get('weight', 0))
    if not weight:
        return jsonify({'error': 'Weight required'}), 400
    log_date = date.today()
    existing = WeightLog.query.filter_by(user_id=current_user.id, date=log_date).first()
    if existing:
        existing.weight = weight
    else:
        existing = WeightLog(user_id=current_user.id, weight=weight, date=log_date)
        db.session.add(existing)
    current_user.current_weight = weight
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/last-weight', methods=['GET'])
@login_required
def get_last_weight():
    last = WeightLog.query.filter_by(user_id=current_user.id).order_by(WeightLog.date.desc()).first()
    return jsonify({'weight': last.weight if last else (current_user.current_weight or ''), 'date': last.date.strftime('%Y-%m-%d') if last else None})

@app.route('/api/history-data', methods=['GET'])
@login_required
def history_data():
    days = int(request.args.get('days', 30))
    since = date.today() - timedelta(days=days)
    entries = FoodEntry.query.filter(FoodEntry.user_id == current_user.id, FoodEntry.date >= since).all()
    day_map = {}
    for e in entries:
        ds = e.date.strftime('%Y-%m-%d')
        if ds not in day_map:
            day_map[ds] = {'calories': 0, 'protein': 0, 'fat': 0, 'carbs': 0, 'foods': []}
        day_map[ds]['calories'] += e.calories
        day_map[ds]['protein'] += e.protein
        day_map[ds]['fat'] += e.fat
        day_map[ds]['carbs'] += e.carbs
        day_map[ds]['foods'].append({'name': e.food_name, 'grams': e.grams, 'calories': e.calories, 'meal': e.meal_type})
    return jsonify({'days': day_map, 'goal': current_user.daily_calorie_goal or 2000})

@app.route('/api/streak', methods=['GET'])
@login_required
def get_streak():
    today = date.today()
    streak = 0
    check = today
    while True:
        has_entry = FoodEntry.query.filter_by(user_id=current_user.id, date=check).first()
        if has_entry:
            streak += 1
            check = check - timedelta(days=1)
        else:
            break
    return jsonify({'streak': streak})

@app.route('/api/weekly-summary', methods=['GET'])
@login_required
def weekly_summary():
    today = date.today()
    since = today - timedelta(days=6)
    entries = FoodEntry.query.filter(FoodEntry.user_id == current_user.id, FoodEntry.date >= since).all()
    goal = current_user.daily_calorie_goal or 2000
    day_map = {}
    for e in entries:
        ds = e.date.strftime('%Y-%m-%d')
        if ds not in day_map:
            day_map[ds] = {'cal': 0, 'protein': 0, 'fat': 0, 'carbs': 0}
        day_map[ds]['cal'] += e.calories
        day_map[ds]['protein'] += e.protein
        day_map[ds]['fat'] += e.fat
        day_map[ds]['carbs'] += e.carbs
    days_logged = len(day_map)
    days_on_goal = sum(1 for d in day_map.values() if d['cal'] <= goal)
    avg_cal = round(sum(d['cal'] for d in day_map.values()) / max(days_logged, 1))
    avg_protein = round(sum(d['protein'] for d in day_map.values()) / max(days_logged, 1))
    avg_fat = round(sum(d['fat'] for d in day_map.values()) / max(days_logged, 1))
    avg_carbs = round(sum(d['carbs'] for d in day_map.values()) / max(days_logged, 1))
    return jsonify({'days_logged': days_logged, 'days_on_goal': days_on_goal, 'avg_cal': avg_cal, 'avg_protein': avg_protein, 'avg_fat': avg_fat, 'avg_carbs': avg_carbs, 'goal': goal})

@app.route('/history')
@login_required
def history():
    lang = current_user.language or 'ru'
    is_premium = current_user.is_premium
    if is_premium:
        entries = FoodEntry.query.filter_by(user_id=current_user.id).order_by(FoodEntry.date.desc()).all()
    else:
        since = date.today() - timedelta(days=6)
        entries = FoodEntry.query.filter(FoodEntry.user_id == current_user.id, FoodEntry.date >= since).order_by(FoodEntry.date.desc()).all()
    days = OrderedDict()
    for e in entries:
        ds = e.date.strftime('%d.%m.%Y')
        if ds not in days:
            days[ds] = {'entries': [], 'total_cal': 0, 'total_protein': 0, 'total_fat': 0, 'total_carbs': 0}
        days[ds]['entries'].append({'food_name': e.food_name, 'grams': e.grams, 'calories': e.calories, 'meal_type': e.meal_type or 'other'})
        days[ds]['total_cal'] += e.calories
        days[ds]['total_protein'] += e.protein
        days[ds]['total_fat'] += e.fat
        days[ds]['total_carbs'] += e.carbs
    t = TRANSLATIONS.get(lang, TRANSLATIONS['ru'])
    now = datetime.utcnow()
    return render_template('history.html', days=days, lang=lang, is_premium=is_premium, goal=current_user.daily_calorie_goal or 2000, t=t, current_user=current_user, now=now)

@app.route('/goals', methods=['GET', 'POST'])
@login_required
def goals():
    lang = current_user.language or 'ru'
    if request.method == 'POST':
        current_user.daily_calorie_goal = int(request.form.get('daily_calorie_goal', 2000))
        current_user.protein_goal = int(request.form.get('protein_goal', 150))
        current_user.fat_goal = int(request.form.get('fat_goal', 70))
        current_user.carbs_goal = int(request.form.get('carbs_goal', 250))
        current_user.age = int(request.form.get('age', 25))
        current_user.gender = request.form.get('gender', 'male')
        current_user.activity = request.form.get('activity', 'moderate')
        current_user.height = float(request.form.get('height', 170))
        current_user.current_weight = float(request.form.get('current_weight', 70))
        current_user.goal_weight = float(request.form.get('goal_weight', 70))
        current_user.water_goal = int(request.form.get('water_goal', 8))
        db.session.commit()
        flash('Goals updated!', 'success')
        return redirect(url_for('goals'))
    t = TRANSLATIONS.get(lang, TRANSLATIONS['ru'])
    last_weight = None
    return render_template('goals.html', user=current_user, lang=lang, t=t, last_weight=last_weight, current_user=current_user, now=datetime.utcnow())

@app.route('/categories')
@login_required
def categories():
    lang = current_user.language or 'ru'
    from food_data import food_data
    cats = {}
    for idx, food in enumerate(food_data):
        cat = food.get('category', 'other')
        if cat not in cats:
            cats[cat] = []
        cats[cat].append({'id': idx, 'name': food['name_ru'], 'calories': food['calories'], 'protein': food.get('protein', 0), 'fat': food.get('fat', 0), 'carbs': food.get('carbs', 0)})
    cat_labels = {
        'fruits': '🍎 Фрукты', 'vegetables': '🥦 Овощи', 'meat': '🥩 Мясо',
        'dairy': '🥛 Молочное', 'grains': '🌾 Злаки', 'nuts': '🌰 Орехи',
        'fish': '🐟 Рыба', 'sweets': '🍫 Сладкое', 'drinks': '🥤 Напитки',
        'supplements': '💊 Витамины', 'sports_nutrition': '💪 Спортпит'
    }
    category_keys = [k for k in cat_labels if k in cats]
    current_cat = request.args.get('cat', category_keys[0] if category_keys else 'fruits')
    foods = sorted(cats.get(current_cat, []), key=lambda x: x['name'])
    t = TRANSLATIONS.get(lang, TRANSLATIONS['ru'])
    return render_template('categories.html', categories=cats, category_keys=category_keys, cat_labels=cat_labels, current_cat=current_cat, foods=foods, lang=lang, t=t, current_user=current_user)

@app.route('/premium')
@login_required
def premium():
    lang = current_user.language or 'ru'
    trial_available = not current_user.trial_used and not current_user.is_premium
    trial_active = bool(current_user.trial_ends and current_user.trial_ends > datetime.utcnow())
    t = TRANSLATIONS.get(lang, TRANSLATIONS['ru'])
    now = datetime.utcnow()
    return render_template('premium.html', lang=lang, trial_available=trial_available, trial_active=trial_active, t=t, current_user=current_user, now=now)

@app.route('/start-trial')
@login_required
def start_trial():
    if current_user.trial_used or current_user.is_premium:
        return redirect(url_for('premium'))
    current_user.trial_used = True
    current_user.is_premium = True
    current_user.trial_ends = datetime.utcnow() + timedelta(days=7)
    db.session.commit()
    flash('Trial activated!', 'success')
    return redirect(url_for('index'))

@app.route('/buy-premium', methods=['POST'])
@login_required
def buy_premium():
    if not Payment:
        return jsonify({'error': 'Payment unavailable'}), 500
    try:
        idempotency_key = str(uuid.uuid4())
        payment = Payment.create({"amount": {"value": "129.00", "currency": "RUB"}, "confirmation": {"type": "redirect", "return_url": request.url_root + "premium-success"}, "description": f"Premium subscription for {current_user.username}"}, idempotency_key)
        current_user.is_premium = True
        current_user.premium_ends = datetime.utcnow() + timedelta(days=30)
        db.session.commit()
        return jsonify({'confirmation_url': payment.confirmation.confirmation_url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid credentials', 'error')
    lang = session.get('lang', 'ru')
    t = TRANSLATIONS.get(lang, TRANSLATIONS['ru'])
    return render_template('login.html', t=t)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if not username or not email or not password:
            flash('All fields required', 'error')
            return redirect(url_for('register'))
        if password != confirm:
            flash('Passwords do not match', 'error')
            return redirect(url_for('register'))
        if User.query.filter_by(username=username).first():
            flash('Username taken', 'error')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email taken', 'error')
            return redirect(url_for('register'))
        user = User(username=username, email=email, password_hash=generate_password_hash(password), language='ru')
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    lang = session.get('lang', 'ru')
    t = TRANSLATIONS.get(lang, TRANSLATIONS['ru'])
    return render_template('register.html', t=t)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/admin')
@login_required
def admin():
    if not current_user.is_superuser:
        return 'Forbidden', 403
    users = User.query.all()
    return render_template('admin.html', users=users, now=datetime.utcnow())

@app.route('/set-language/<lang>')
def set_language(lang):
    if lang in ['ru', 'en', 'uk', 'kk']:
        if current_user.is_authenticated:
            current_user.language = lang
            db.session.commit()
        session['lang'] = lang
    return redirect(request.referrer or url_for('index'))

@app.route('/language', methods=['POST'])
def change_language():
    lang = request.form.get('lang', 'ru')
    if lang in ['ru', 'en', 'uk', 'kk']:
        if current_user.is_authenticated:
            current_user.language = lang
            db.session.commit()
        session['lang'] = lang
    return redirect(request.referrer or url_for('index'))

@app.errorhandler(404)
def not_found(e):
    return 'Not found', 404

@app.errorhandler(500)
def server_error(e):
    return 'Server error', 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
