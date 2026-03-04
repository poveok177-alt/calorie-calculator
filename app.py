from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import json
import os
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

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'super-secret-key-12345')
database_url = os.environ.get('DATABASE_URL', 'sqlite:///calories.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ===================== МОДЕЛИ =====================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    language = db.Column(db.String(10), default='ru')
    is_premium = db.Column(db.Boolean, default=False)
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
    food_id = db.Column(db.Integer, nullable=False)
    food_name = db.Column(db.String(200))
    grams = db.Column(db.Float, nullable=False)
    calories = db.Column(db.Float, nullable=False)
    protein = db.Column(db.Float, default=0)
    fat = db.Column(db.Float, default=0)
    carbs = db.Column(db.Float, default=0)
    date = db.Column(db.Date, default=date.today)
    meal_type = db.Column(db.String(20), default='other')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ===================== ПЕРЕВОДЫ =====================

translations = {
    'ru': {
        'app_name': 'CaloriMint',
        'home': 'Главная', 'history': 'История', 'goals': 'Цели',
        'categories': 'Категории', 'premium': 'Премиум',
        'login': 'Вход', 'register': 'Регистрация', 'logout': 'Выход',
        'profile': 'Профиль', 'search': 'Поиск продуктов...', 'add': 'Добавить',
        'calories': 'Калории', 'protein': 'Белки', 'fat': 'Жиры', 'carbs': 'Углеводы',
        'breakfast': 'Завтрак', 'lunch': 'Обед', 'dinner': 'Ужин', 'snack': 'Перекус',
        'today': 'Сегодня', 'delete': 'Удалить', 'clear': 'Очистить', 'all': 'Всё',
        'g': 'г', 'kcal': 'ккал', 'recent': 'Недавние', 'favorites': 'Избранное',
        'no_account': 'Нет аккаунта?', 'have_account': 'Уже есть аккаунт?',
        'tagline': 'Следите за питанием легко и красиво',
        'email': 'Email', 'password': 'Пароль', 'username': 'Имя пользователя',
        'month_history': 'История за 30 дней', 'bju_counter': 'Счётчик БЖУ',
        'weight_goal': 'Цель по весу', 'no_ads': 'Без рекламы',
        'premium_desc': 'Разблокируйте все возможности CaloriMint',
        # категории
        'fruits': '🍎 Фрукты', 'vegetables': '🥦 Овощи', 'meat': '🥩 Мясо',
        'fish': '🐟 Рыба', 'dairy': '🥛 Молочное', 'grains': '🌾 Злаки',
        'nuts': '🥜 Орехи', 'drinks': '🥤 Напитки', 'sweets': '🍫 Сладкое',
        'supplements': '💊 Витамины', 'sports_nutrition': '💪 Спортпит', 'other': '🍽️ Другое',
        'grams_label': 'Количество (грамм)',
    },
    'en': {
        'app_name': 'CaloriMint',
        'home': 'Home', 'history': 'History', 'goals': 'Goals',
        'categories': 'Categories', 'premium': 'Premium',
        'login': 'Login', 'register': 'Sign Up', 'logout': 'Logout',
        'profile': 'Profile', 'search': 'Search products...', 'add': 'Add',
        'calories': 'Calories', 'protein': 'Protein', 'fat': 'Fat', 'carbs': 'Carbs',
        'breakfast': 'Breakfast', 'lunch': 'Lunch', 'dinner': 'Dinner', 'snack': 'Snack',
        'today': 'Today', 'delete': 'Delete', 'clear': 'Clear', 'all': 'All',
        'g': 'g', 'kcal': 'kcal', 'recent': 'Recent', 'favorites': 'Favorites',
        'no_account': 'No account?', 'have_account': 'Already have an account?',
        'tagline': 'Track your nutrition easily and beautifully',
        'email': 'Email', 'password': 'Password', 'username': 'Username',
        'month_history': '30-Day History', 'bju_counter': 'Macro Tracker',
        'weight_goal': 'Weight Goal', 'no_ads': 'No Ads',
        'premium_desc': 'Unlock all CaloriMint features',
        'fruits': '🍎 Fruits', 'vegetables': '🥦 Vegetables', 'meat': '🥩 Meat',
        'fish': '🐟 Fish', 'dairy': '🥛 Dairy', 'grains': '🌾 Grains',
        'nuts': '🥜 Nuts', 'drinks': '🥤 Drinks', 'sweets': '🍫 Sweets',
        'supplements': '💊 Supplements', 'sports_nutrition': '💪 Sports Nutrition', 'other': '🍽️ Other',
        'grams_label': 'Amount (grams)',
    },
    'uk': {
        'app_name': 'CaloriMint',
        'home': 'Головна', 'history': 'Історія', 'goals': 'Цілі',
        'categories': 'Категорії', 'premium': 'Преміум',
        'login': 'Вхід', 'register': 'Реєстрація', 'logout': 'Вихід',
        'profile': 'Профіль', 'search': 'Пошук продуктів...', 'add': 'Додати',
        'calories': 'Калорії', 'protein': 'Білки', 'fat': 'Жири', 'carbs': 'Вуглеводи',
        'breakfast': 'Сніданок', 'lunch': 'Обід', 'dinner': 'Вечеря', 'snack': 'Закуска',
        'today': 'Сьогодні', 'delete': 'Видалити', 'clear': 'Очистити', 'all': 'Все',
        'g': 'г', 'kcal': 'ккал', 'recent': 'Недавні', 'favorites': 'Улюблені',
        'no_account': 'Немає акаунту?', 'have_account': 'Вже є акаунт?',
        'tagline': 'Стежте за харчуванням легко і красиво',
        'email': 'Email', 'password': 'Пароль', 'username': "Ім'я користувача",
        'month_history': 'Історія за 30 днів', 'bju_counter': 'Лічильник БЖВ',
        'weight_goal': 'Ціль по вазі', 'no_ads': 'Без реклами',
        'premium_desc': 'Розблокуйте всі можливості CaloriMint',
        'fruits': '🍎 Фрукти', 'vegetables': '🥦 Овочі', 'meat': '🥩 М\'ясо',
        'fish': '🐟 Риба', 'dairy': '🥛 Молочне', 'grains': '🌾 Злаки',
        'nuts': '🥜 Горіхи', 'drinks': '🥤 Напої', 'sweets': '🍫 Солодке',
        'supplements': '💊 Вітаміни', 'sports_nutrition': '💪 Спортхарч', 'other': '🍽️ Інше',
        'grams_label': 'Кількість (грам)',
    },
    'kk': {
        'app_name': 'CaloriMint',
        'home': 'Басты бет', 'history': 'Тарихы', 'goals': 'Мақсаттар',
        'categories': 'Санаттар', 'premium': 'Премиум',
        'login': 'Кіру', 'register': 'Тіркелу', 'logout': 'Шығу',
        'profile': 'Профиль', 'search': 'Өнімдерді іздеу...', 'add': 'Қосу',
        'calories': 'Калориялар', 'protein': 'Ақуыз', 'fat': 'Май', 'carbs': 'Көмірсулар',
        'breakfast': 'Таңғы ас', 'lunch': 'Түскі ас', 'dinner': 'Кешкі ас', 'snack': 'Тәттілер',
        'today': 'Бүгін', 'delete': 'Өшіру', 'clear': 'Тазарту', 'all': 'Барлығы',
        'g': 'г', 'kcal': 'ккал', 'recent': 'Соңғы', 'favorites': 'Таңдамалар',
        'no_account': 'Акаунт жоқ па?', 'have_account': 'Акаунт бар ма?',
        'tagline': 'Тамақтануды оңай және әдемі бақылаңыз',
        'email': 'Email', 'password': 'Құпия сөз', 'username': 'Пайдаланушы аты',
        'month_history': '30 күндік тарих', 'bju_counter': 'БЖК есептегіші',
        'weight_goal': 'Салмақ мақсаты', 'no_ads': 'Жарнамасыз',
        'premium_desc': 'CaloriMint мүмкіндіктерін ашыңыз',
        'fruits': '🍎 Жемістер', 'vegetables': '🥦 Көкөністер', 'meat': '🥩 Ет',
        'fish': '🐟 Балық', 'dairy': '🥛 Сүт өнімдері', 'grains': '🌾 Дәндер',
        'nuts': '🥜 Жаңғақтар', 'drinks': '🥤 Сусындар', 'sweets': '🍫 Тәттілер',
        'supplements': '💊 Витаминдер', 'sports_nutrition': '💪 Спорт тамағы', 'other': '🍽️ Басқа',
        'grams_label': 'Мөлшер (грамм)',
    }
}

CATEGORY_ORDER = ['fruits', 'vegetables', 'meat', 'fish', 'dairy', 'grains', 'nuts', 'drinks', 'sweets', 'supplements', 'sports_nutrition', 'other']

def get_lang():
    if current_user.is_authenticated:
        return current_user.language or 'ru'
    return session.get('lang', 'ru')

def get_t():
    return translations.get(get_lang(), translations['ru'])

# ===================== МАРШРУТЫ =====================

@app.before_request
def before_request():
    pass

@app.route('/')
@login_required
def index():
    lang = get_lang()
    t = get_t()
    today = date.today()
    entries = FoodEntry.query.filter_by(user_id=current_user.id, date=today).all()

    meals = {
        'breakfast': {'name': t.get('breakfast'), 'icon': '🌅', 'color': '#f39c12', 'total_cal': 0, 'total_protein': 0, 'total_fat': 0, 'total_carbs': 0, 'entries': []},
        'lunch':     {'name': t.get('lunch'),     'icon': '☀️',  'color': '#27ae60', 'total_cal': 0, 'total_protein': 0, 'total_fat': 0, 'total_carbs': 0, 'entries': []},
        'dinner':    {'name': t.get('dinner'),    'icon': '🌙',  'color': '#3498db', 'total_cal': 0, 'total_protein': 0, 'total_fat': 0, 'total_carbs': 0, 'entries': []},
        'snack':     {'name': t.get('snack'),     'icon': '🍿',  'color': '#e74c3c', 'total_cal': 0, 'total_protein': 0, 'total_fat': 0, 'total_carbs': 0, 'entries': []},
    }

    total_calories = total_protein = total_fat = total_carbs = 0

    for entry in entries:
        meal_type = entry.meal_type if entry.meal_type in meals else 'snack'
        meals[meal_type]['entries'].append({
            'id': entry.id,
            'name': entry.food_name,
            'grams': entry.grams,
            'calories': entry.calories,
            'protein': entry.protein,
            'fat': entry.fat,
            'carbs': entry.carbs,
        })
        meals[meal_type]['total_cal'] += entry.calories
        meals[meal_type]['total_protein'] += entry.protein
        meals[meal_type]['total_fat'] += entry.fat
        meals[meal_type]['total_carbs'] += entry.carbs
        total_calories += entry.calories
        total_protein += entry.protein
        total_fat += entry.fat
        total_carbs += entry.carbs

    return render_template('index.html',
        t=t, meals=meals,
        total_calories=int(total_calories),
        total_protein=round(total_protein, 1),
        total_fat=round(total_fat, 1),
        total_carbs=round(total_carbs, 1),
        lang=lang
    )

@app.route('/api/search')
@login_required
def search_foods():
    from food_data import food_data
    query = request.args.get('q', '').lower().strip()
    lang = get_lang()

    if not query:
        return jsonify([])

    results = []
    for idx, food in enumerate(food_data):
        names = [
            food.get('name_ru', '').lower(),
            food.get('name_en', '').lower(),
            food.get('name_uk', '').lower(),
            food.get('name_kk', '').lower(),
        ]
        if any(query in n for n in names):
            name = food.get(f'name_{lang}') or food.get('name_ru', '')
            results.append({
                'id': idx,
                'name': name,
                'name_ru': food['name_ru'],
                'calories': food['calories'],
                'protein': food.get('protein', 0),
                'fat': food.get('fat', 0),
                'carbs': food.get('carbs', 0),
                'category': food.get('category', 'other')
            })
    return jsonify(results[:20])

@app.route('/api/add-entry', methods=['POST'])
@login_required
def add_entry():
    from food_data import food_data
    data = request.get_json()
    food_id = int(data.get('food_id', 0))
    grams = float(data.get('grams', 100))
    meal_type = data.get('meal_type', 'snack')

    if food_id < 0 or food_id >= len(food_data):
        return jsonify({'error': 'Invalid food'}), 400

    food = food_data[food_id]
    lang = get_lang()
    name = food.get(f'name_{lang}') or food.get('name_ru', '')
    r = grams / 100

    entry = FoodEntry(
        user_id=current_user.id,
        food_id=food_id,
        food_name=name,
        grams=grams,
        calories=food['calories'] * r,
        protein=food.get('protein', 0) * r,
        fat=food.get('fat', 0) * r,
        carbs=food.get('carbs', 0) * r,
        meal_type=meal_type,
        date=date.today()
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify({'success': True, 'entry_id': entry.id})

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
    FoodEntry.query.filter_by(user_id=current_user.id, meal_type=meal_type, date=date.today()).delete()
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/clear-day', methods=['DELETE'])
@login_required
def clear_day():
    FoodEntry.query.filter_by(user_id=current_user.id, date=date.today()).delete()
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/recent')
@login_required
def get_recent():
    from food_data import food_data
    lang = get_lang()
    entries = FoodEntry.query.filter_by(user_id=current_user.id).order_by(FoodEntry.created_at.desc()).limit(30).all()
    seen = set()
    results = []
    for entry in entries:
        fid = entry.food_id
        if fid not in seen and 0 <= fid < len(food_data):
            seen.add(fid)
            food = food_data[fid]
            name = food.get(f'name_{lang}') or food.get('name_ru', '')
            results.append({'id': fid, 'name': name, 'calories': food['calories'],
                'protein': food.get('protein', 0), 'fat': food.get('fat', 0), 'carbs': food.get('carbs', 0)})
        if len(results) >= 10:
            break
    return jsonify(results)

@app.route('/api/favorites', methods=['GET'])
@login_required
def get_favorites():
    from food_data import food_data
    lang = get_lang()
    fav_ids = json.loads(current_user.favorites or '[]')
    results = []
    for fid in fav_ids:
        if 0 <= fid < len(food_data):
            food = food_data[fid]
            name = food.get(f'name_{lang}') or food.get('name_ru', '')
            results.append({'id': fid, 'name': name, 'calories': food['calories'],
                'protein': food.get('protein', 0), 'fat': food.get('fat', 0), 'carbs': food.get('carbs', 0)})
    return jsonify(results)

@app.route('/api/favorites', methods=['POST'])
@login_required
def add_favorite():
    data = request.get_json()
    food_id = int(data.get('food_id'))
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
    fav_ids = [x for x in fav_ids if x != food_id]
    current_user.favorites = json.dumps(fav_ids)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/history')
@login_required
def history():
    lang = get_lang()
    t = get_t()

    thirty_days_ago = date.today() - timedelta(days=30)
    entries = FoodEntry.query.filter(
        FoodEntry.user_id == current_user.id,
        FoodEntry.date >= thirty_days_ago
    ).order_by(FoodEntry.date.desc(), FoodEntry.created_at.desc()).all()

    days = {}
    for entry in entries:
        ds = entry.date.strftime('%d.%m.%Y')
        if ds not in days:
            days[ds] = {'entries': [], 'total_cal': 0, 'total_protein': 0, 'total_fat': 0, 'total_carbs': 0}
        days[ds]['entries'].append(entry)
        days[ds]['total_cal'] += entry.calories
        days[ds]['total_protein'] += entry.protein
        days[ds]['total_fat'] += entry.fat
        days[ds]['total_carbs'] += entry.carbs

    return render_template('history.html', days=days, t=t, lang=lang,
                           is_premium=current_user.is_premium)

@app.route('/goals', methods=['GET', 'POST'])
@login_required
def goals():
    lang = get_lang()
    t = get_t()

    if request.method == 'POST':
        try:
            current_user.daily_calorie_goal = int(request.form.get('daily_calories', 2000))
            current_user.protein_goal = int(request.form.get('protein', 150))
            current_user.fat_goal = int(request.form.get('fat', 70))
            current_user.carbs_goal = int(request.form.get('carbs', 250))
            current_user.age = int(request.form.get('age', 25))
            current_user.gender = request.form.get('gender', 'male')
            current_user.activity = request.form.get('activity', 'moderate')
            current_user.height = float(request.form.get('height', 170))
            current_user.current_weight = float(request.form.get('current_weight', 70))
            current_user.goal_weight = float(request.form.get('goal_weight', 70))
            db.session.commit()
            flash('✓ Цели сохранены!', 'success')
        except Exception as e:
            flash('Ошибка сохранения', 'error')
        return redirect(url_for('goals'))

    return render_template('goals.html', user=current_user, t=t, lang=lang)

@app.route('/categories')
@login_required
def categories():
    from food_data import food_data
    lang = get_lang()
    t = get_t()

    current_cat = request.args.get('cat', 'fruits')

    cats = {}
    for food in food_data:
        cat = food.get('category', 'other')
        if cat not in cats:
            cats[cat] = []
        cats[cat].append(food)

    # Sort foods alphabetically by localized name
    lang_key = f'name_{lang}'
    foods_in_cat = sorted(cats.get(current_cat, []), key=lambda f: f.get(lang_key) or f.get('name_ru', ''))

    # Add idx for food_id
    foods_with_id = []
    for food in food_data:
        food['_idx'] = food_data.index(food)

    foods_final = []
    for food in foods_in_cat:
        idx = food_data.index(food)
        foods_final.append({
            'id': idx,
            'name': food.get(lang_key) or food.get('name_ru', ''),
            'calories': food['calories'],
            'protein': food.get('protein', 0),
            'fat': food.get('fat', 0),
            'carbs': food.get('carbs', 0),
        })

    category_keys = [k for k in CATEGORY_ORDER if k in cats]

    return render_template('categories.html',
        foods=foods_final, current_cat=current_cat,
        category_keys=category_keys, t=t, lang=lang)

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
        else:
            flash('Неверный email или пароль', 'error')
    lang = session.get('lang', 'ru')
    t = translations.get(lang, translations['ru'])
    return render_template('login.html', t=t, lang=lang)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        language = request.form.get('language', 'ru')

        if User.query.filter_by(email=email).first():
            flash('Email уже зарегистрирован', 'error')
            return redirect(url_for('register'))
        if User.query.filter_by(username=username).first():
            flash('Имя пользователя занято', 'error')
            return redirect(url_for('register'))
        if len(password) < 6:
            flash('Пароль минимум 6 символов', 'error')
            return redirect(url_for('register'))

        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            language=language
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('index'))

    lang = session.get('lang', 'ru')
    t = translations.get(lang, translations['ru'])
    return render_template('register.html', t=t, lang=lang)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/premium')
@login_required
def premium():
    lang = get_lang()
    t = get_t()
    return render_template('premium.html', t=t, lang=lang,
                           trial_available=not current_user.trial_used)

@app.route('/set-language/<lang_code>')
def set_language(lang_code):
    if lang_code not in translations:
        lang_code = 'ru'
    if current_user.is_authenticated:
        current_user.language = lang_code
        db.session.commit()
    else:
        session['lang'] = lang_code
    return redirect(url_for('index') if current_user.is_authenticated else url_for('login'))

@app.route('/language', methods=['POST'])
def set_language_post():
    lang = request.form.get('lang', 'ru')
    return set_language(lang)

# ===================== ИНИЦИАЛИЗАЦИЯ =====================

with app.app_context():
    db.create_all()
    from food_data import food_data as fd
    # Ensure favorites column exists (for old SQLite DBs)
    try:
        db.session.execute(db.text("SELECT favorites FROM user LIMIT 1"))
    except Exception:
        try:
            db.session.execute(db.text('ALTER TABLE "user" ADD COLUMN favorites TEXT DEFAULT \'[]\''))
            db.session.commit()
        except Exception:
            pass

if __name__ == '__main__':
    app.run(debug=True)
