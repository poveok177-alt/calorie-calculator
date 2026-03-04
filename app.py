from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
import json
import os
import uuid
from dotenv import load_dotenv

load_dotenv()

# ===== YooKassa (без падения сервера) =====
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
app.config['SECRET_KEY'] = 'mojasupertajnayastrokakotoruyaniktonevzlomaet123'
app.config['SESSION_TYPE'] = 'filesystem'
database_url = os.environ.get('DATABASE_URL', 'sqlite:///calories.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ===================== МОДЕЛИ БД =====================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    language = db.Column(db.String(10), default='ru')
    is_premium = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Цели
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

    # Пробный период
    trial_used = db.Column(db.Boolean, default=False)
    trial_ends = db.Column(db.DateTime, nullable=True)
    email_reminders = db.Column(db.Boolean, default=True)
    
    # Избранное и недавние
    favorites = db.Column(db.Text, default='[]')  # JSON список food_id

    entries = db.relationship('FoodEntry', backref='user', lazy=True)

class Food(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name_ru = db.Column(db.String(200), nullable=False)
    name_en = db.Column(db.String(200), nullable=False)
    name_uk = db.Column(db.String(200), nullable=True)
    name_kk = db.Column(db.String(200), nullable=True)
    calories = db.Column(db.Float, nullable=False)  # на 100г
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
    meal_type = db.Column(db.String(20), default='other')  # breakfast, lunch, dinner, snack
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    food = db.relationship('Food')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ===================== ИНИЦИАЛИЗАЦИЯ БД =====================

def init_db():
    with app.app_context():
        inspector = db.inspect(db.engine)
        user_columns = [col['name'] for col in inspector.get_columns('user')]
        with db.engine.connect() as conn:
            if 'favorites' not in user_columns:
                conn.execute(db.text('ALTER TABLE "user" ADD COLUMN favorites TEXT DEFAULT \'[]\''))
                conn.commit()

# ===================== ПЕРЕВОДЫ =====================

translations = {
    'ru': {
        'app_name': 'CaloriMint',
        'home': 'Главная',
        'history': 'История',
        'goals': 'Цели',
        'categories': 'Категории',
        'premium': 'Премиум',
        'login': 'Вход',
        'register': 'Регистрация',
        'logout': 'Выход',
        'profile': 'Профиль',
        'search': 'Поиск продуктов...',
        'add': 'Добавить',
        'calories': 'Калории',
        'protein': 'Белки',
        'fat': 'Жиры',
        'carbs': 'Углеводы',
        'breakfast': 'Завтрак',
        'lunch': 'Обед',
        'dinner': 'Ужин',
        'snack': 'Перекус',
        'today': 'Сегодня',
        'delete': 'Удалить',
        'clear': 'Очистить',
        'all': 'Все',
        'grams': 'г',
        'kcal': 'ккал',
        'g': 'г',
        'recent': 'Недавние',
        'favorites': 'Избранные',
        'favorites_icon': '⭐',
        'supplements': 'Витамины',
        'sports_nutrition': 'Спортпит',
        'save': 'Сохранить',
        'daily_goal': 'Дневная цель',
        'weight_goal': 'Цель по весу',
        'current_weight': 'Текущий вес (кг)',
        'goal_weight': 'Целевой вес (кг)',
        'height': 'Рост (см)',
        'water': 'Вода',
        'month_history': 'История за 30 дней',
        'bju_counter': 'Счётчик БЖУ',
        'no_ads': 'Без рекламы',
        'premium_desc': 'Раскройте весь потенциал здорового питания',
        'trial_btn': '🎁 7 дней бесплатно за 11 ₽',
        'buy_btn': 'Получить Премиум 🌿',
        'per_month': 'в месяц',
        'free_badge': 'Бесплатно',
        'premium_badge': '⭐ Премиум',
    },
    'en': {
        'app_name': 'CaloriMint',
        'home': 'Home',
        'history': 'History',
        'goals': 'Goals',
        'categories': 'Categories',
        'premium': 'Premium',
        'login': 'Login',
        'register': 'Sign Up',
        'logout': 'Logout',
        'profile': 'Profile',
        'search': 'Search products...',
        'add': 'Add',
        'calories': 'Calories',
        'protein': 'Protein',
        'fat': 'Fat',
        'carbs': 'Carbs',
        'breakfast': 'Breakfast',
        'lunch': 'Lunch',
        'dinner': 'Dinner',
        'snack': 'Snack',
        'today': 'Today',
        'delete': 'Delete',
        'clear': 'Clear',
        'all': 'All',
        'grams': 'g',
        'kcal': 'kcal',
        'g': 'g',
        'recent': 'Recent',
        'favorites': 'Favorites',
        'favorites_icon': '⭐',
        'supplements': 'Supplements',
        'sports_nutrition': 'Sports Nutrition',
        'save': 'Save',
        'daily_goal': 'Daily goal',
        'weight_goal': 'Weight goal',
        'current_weight': 'Current weight (kg)',
        'goal_weight': 'Target weight (kg)',
        'height': 'Height (cm)',
        'water': 'Water',
        'month_history': '30-day history',
        'bju_counter': 'Macros tracker',
        'no_ads': 'Ad-free',
        'premium_desc': 'Unlock the full potential of healthy eating',
        'trial_btn': '🎁 7 days trial for 11 ₽',
        'buy_btn': 'Get Premium 🌿',
        'per_month': 'per month',
        'free_badge': 'Free',
        'premium_badge': '⭐ Premium',
    },
    'uk': {
        'app_name': 'CaloriMint',
        'home': 'Головна',
        'history': 'Історія',
        'goals': 'Цілі',
        'categories': 'Категорії',
        'premium': 'Преміум',
        'login': 'Вхід',
        'register': 'Реєстрація',
        'logout': 'Вихід',
        'profile': 'Профіль',
        'search': 'Пошук продуктів...',
        'add': 'Додати',
        'calories': 'Калорії',
        'protein': 'Білки',
        'fat': 'Жири',
        'carbs': 'Вуглеводи',
        'breakfast': 'Сніданок',
        'lunch': 'Обід',
        'dinner': 'Вечеря',
        'snack': 'Закуска',
        'today': 'Сьогодні',
        'delete': 'Видалити',
        'clear': 'Очистити',
        'all': 'Все',
        'grams': 'г',
        'kcal': 'ккал',
        'g': 'г',
        'recent': 'Недавні',
        'favorites': 'Улюблені',
        'favorites_icon': '⭐',
        'supplements': 'Добавки',
        'sports_nutrition': 'Спортивне харчування',
        'save': 'Зберегти',
        'daily_goal': 'Денна норма',
        'weight_goal': 'Ціль по вазі',
        'current_weight': 'Поточна вага (кг)',
        'goal_weight': 'Цільова вага (кг)',
        'height': 'Зріст (см)',
        'water': 'Вода',
        'month_history': 'Історія за 30 днів',
        'bju_counter': 'Лічильник БЖВ',
        'no_ads': 'Без реклами',
        'premium_desc': 'Розкрийте повний потенціал здорового харчування',
        'trial_btn': '🎁 7 днів пробно за 11 ₽',
        'buy_btn': 'Отримати Преміум 🌿',
        'per_month': 'на місяць',
        'free_badge': 'Безкоштовно',
        'premium_badge': '⭐ Преміум',
    },
    'kk': {
        'app_name': 'CaloriMint',
        'home': 'Басты бет',
        'history': 'Тарихы',
        'goals': 'Мақсаттар',
        'categories': 'Санаттар',
        'premium': 'Премиум',
        'login': 'Кіру',
        'register': 'Тіркелу',
        'logout': 'Шығу',
        'profile': 'Профиль',
        'search': 'Өнімдерді іздеу...',
        'add': 'Қосу',
        'calories': 'Калориялар',
        'protein': 'Ақуыз',
        'fat': 'Май',
        'carbs': 'Көмірсулар',
        'breakfast': 'Таңғы ас',
        'lunch': 'Түскі ас',
        'dinner': 'Кешкі ас',
        'snack': 'Аралық тамақ',
        'today': 'Бүгін',
        'delete': 'Өшіру',
        'clear': 'Тазарту',
        'all': 'Барлығы',
        'grams': 'г',
        'kcal': 'ккал',
        'g': 'г',
        'recent': 'Соңғы',
        'favorites': 'Таңдамалар',
        'favorites_icon': '⭐',
        'supplements': 'Қоспалар',
        'sports_nutrition': 'Спорт тамағы',
        'save': 'Сақтау',
        'daily_goal': 'Күнделікті норма',
        'weight_goal': 'Салмақ мақсаты',
        'current_weight': 'Қазіргі салмақ (кг)',
        'goal_weight': 'Мақсатты салмақ (кг)',
        'height': 'Бой (см)',
        'water': 'Су',
        'month_history': '30 күндік тарих',
        'bju_counter': 'БМУ есептегіш',
        'no_ads': 'Жарнамасыз',
        'premium_desc': 'Дұрыс тамақтанудың толық мүмкіндігін ашыңыз',
        'trial_btn': '🎁 7 күн 11 ₽ үшін',
        'buy_btn': 'Премиум алу 🌿',
        'per_month': 'айына',
        'free_badge': 'Тегін',
        'premium_badge': '⭐ Премиум',
    }
}


# ===================== МАРШРУТЫ =====================

@app.before_request
def before_request():
    session['lang'] = current_user.language if current_user.is_authenticated else session.get('lang', 'ru')

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    
    lang = current_user.language or 'ru'
    t = translations.get(lang, translations['ru'])
    today = date.today()
    entries = FoodEntry.query.filter_by(user_id=current_user.id, date=today).all()
    
    # Считаем по приёмам пищи
    meals = {
        'breakfast': {'name': t.get('breakfast'), 'icon': '🌅', 'color': '#f39c12', 'total': 0, 'entries': []},
        'lunch': {'name': t.get('lunch'), 'icon': '☀️', 'color': '#27ae60', 'total': 0, 'entries': []},
        'dinner': {'name': t.get('dinner'), 'icon': '🌙', 'color': '#3498db', 'total': 0, 'entries': []},
        'snack': {'name': t.get('snack'), 'icon': '🍿', 'color': '#e74c3c', 'total': 0, 'entries': []},
    }
    
    total_calories = 0
    total_protein = 0
    total_fat = 0
    total_carbs = 0
    
    for entry in entries:
        meal_type = entry.meal_type or 'snack'
        if meal_type in meals:
            meals[meal_type]['entries'].append({
                'id': entry.id,
                'name': entry.food_name,
                'grams': entry.grams,
                'calories': entry.calories
            })
            meals[meal_type]['total'] += entry.calories
        
        total_calories += entry.calories
        total_protein += entry.protein
        total_fat += entry.fat
        total_carbs += entry.carbs
    
    return render_template('index.html', 
        t=t, 
        meals=meals,
        total_calories=int(total_calories),
        total_protein=int(total_protein),
        total_fat=int(total_fat),
        total_carbs=int(total_carbs),
        lang=lang
    )

@app.route('/api/search', methods=['GET'])
@login_required
def search_foods():
    query = request.args.get('q', '').strip().lower()
    category = request.args.get('category', '').strip()
    show_all = request.args.get('show_all', '')

    if not query and not category and not show_all:
        return jsonify([])

    from food_data import food_data

    results = []
    for idx, food in enumerate(food_data):
        if category and food.get('category') != category:
            continue
        if query:
            haystack = ' '.join([
                food.get('name_ru', ''),
                food.get('name_en', ''),
                food.get('name_uk', ''),
                food.get('name_kk', ''),
            ]).lower()
            if query not in haystack:
                continue
        results.append({
            'id': idx,
            'name_ru': food['name_ru'],
            'name_en': food.get('name_en', food['name_ru']),
            'calories': food['calories'],
            'protein': food.get('protein', 0),
            'fat': food.get('fat', 0),
            'carbs': food.get('carbs', 0),
            'category': food.get('category', 'other')
        })

    return jsonify(results[:30])

@app.route('/api/add-entry', methods=['POST'])
@login_required
def add_entry():
    data = request.get_json()
    food_id = data.get('food_id')
    grams = float(data.get('grams', 100))
    meal_type = data.get('meal_type', 'snack')
    
    from food_data import food_data
    
    if food_id < 0 or food_id >= len(food_data):
        return jsonify({'error': 'Invalid food'}), 400
    
    food = food_data[food_id]
    
    # Расчёт по граммам
    cal_per_100 = food['calories']
    protein_per_100 = food.get('protein', 0)
    fat_per_100 = food.get('fat', 0)
    carbs_per_100 = food.get('carbs', 0)
    
    multiplier = grams / 100
    
    entry = FoodEntry(
        user_id=current_user.id,
        food_id=food_id,
        food_name=food['name_ru'],
        grams=grams,
        calories=cal_per_100 * multiplier,
        protein=protein_per_100 * multiplier,
        fat=fat_per_100 * multiplier,
        carbs=carbs_per_100 * multiplier,
        meal_type=meal_type,
        date=date.today()
    )
    
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
    
    entries = FoodEntry.query.filter_by(
        user_id=current_user.id,
        meal_type=meal_type,
        date=date.today()
    ).all()
    
    for entry in entries:
        db.session.delete(entry)
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/clear-day', methods=['DELETE'])
@login_required
def clear_day():
    entries = FoodEntry.query.filter_by(
        user_id=current_user.id,
        date=date.today()
    ).all()
    
    for entry in entries:
        db.session.delete(entry)
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/recent', methods=['GET'])
@login_required
def get_recent():
    from food_data import food_data
    
    entries = FoodEntry.query.filter_by(user_id=current_user.id).order_by(
        FoodEntry.created_at.desc()
    ).limit(10).all()
    
    seen = set()
    results = []
    for entry in entries:
        if entry.food_id not in seen and entry.food_id < len(food_data):
            seen.add(entry.food_id)
            food = food_data[entry.food_id]
            results.append({
                'id': entry.food_id,
                'name_ru': food['name_ru'],
                'calories': food['calories'],
                'protein': food.get('protein', 0),
                'fat': food.get('fat', 0),
                'carbs': food.get('carbs', 0)
            })
    
    return jsonify(results)

@app.route('/api/favorites', methods=['GET'])
@login_required
def get_favorites():
    from food_data import food_data
    
    fav_ids = json.loads(current_user.favorites or '[]')
    results = []
    
    for fid in fav_ids:
        if 0 <= fid < len(food_data):
            food = food_data[fid]
            results.append({
                'id': fid,
                'name_ru': food['name_ru'],
                'calories': food['calories'],
                'protein': food.get('protein', 0),
                'fat': food.get('fat', 0),
                'carbs': food.get('carbs', 0)
            })
    
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

@app.route('/history')
@login_required
def history():
    lang = current_user.language or 'ru'
    t = translations.get(lang, translations['ru'])
    
    entries = FoodEntry.query.filter_by(user_id=current_user.id).order_by(
        FoodEntry.date.desc()
    ).all()
    
    return render_template('history.html', entries=entries, t=t, lang=lang)

@app.route('/goals', methods=['GET', 'POST'])
@login_required
def goals():
    lang = current_user.language or 'ru'
    t = translations.get(lang, translations['ru'])
    
    if request.method == 'POST':
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
        flash('Goals updated!', 'success')
    
    return render_template('goals.html', user=current_user, t=t, lang=lang)

@app.route('/categories')
@login_required
def categories():
    lang = current_user.language or 'ru'
    t = translations.get(lang, translations['ru'])

    from food_data import food_data

    cats = {}
    for idx, food in enumerate(food_data):
        cat = food.get('category', 'other')
        if cat not in cats:
            cats[cat] = []
        cats[cat].append({
            'id': idx,
            'name': food['name_ru'],
            'calories': food['calories'],
            'protein': food.get('protein', 0),
            'fat': food.get('fat', 0),
            'carbs': food.get('carbs', 0),
            'category': cat,
        })

    cat_labels = {
        'fruits':           '🍎 ' + {'ru':'Фрукты','en':'Fruits','uk':'Фрукти','kk':'Жемістер'}.get(lang,'Fruits'),
        'vegetables':       '🥦 ' + {'ru':'Овощи','en':'Vegetables','uk':'Овочі','kk':'Көкөністер'}.get(lang,'Vegetables'),
        'meat':             '🥩 ' + {'ru':'Мясо','en':'Meat','uk':'Мʼясо','kk':'Ет'}.get(lang,'Meat'),
        'dairy':            '🥛 ' + {'ru':'Молочное','en':'Dairy','uk':'Молочне','kk':'Сүт өнімдері'}.get(lang,'Dairy'),
        'grains':           '🌾 ' + {'ru':'Злаки','en':'Grains','uk':'Злаки','kk':'Астық'}.get(lang,'Grains'),
        'nuts':             '🌰 ' + {'ru':'Орехи','en':'Nuts','uk':'Горіхи','kk':'Жаңғақтар'}.get(lang,'Nuts'),
        'fish':             '🐟 ' + {'ru':'Рыба','en':'Fish','uk':'Риба','kk':'Балық'}.get(lang,'Fish'),
        'sweets':           '🍫 ' + {'ru':'Сладкое','en':'Sweets','uk':'Солодке','kk':'Тәттілер'}.get(lang,'Sweets'),
        'drinks':           '🥤 ' + {'ru':'Напитки','en':'Drinks','uk':'Напої','kk':'Сусындар'}.get(lang,'Drinks'),
        'supplements':      '💊 ' + {'ru':'Витамины','en':'Supplements','uk':'Добавки','kk':'Қоспалар'}.get(lang,'Supplements'),
        'sports_nutrition': '💪 ' + {'ru':'Спортпит','en':'Sports Nutrition','uk':'Спортхарч','kk':'Спорт тамағы'}.get(lang,'Sports Nutrition'),
        'other':            '🍽 ' + {'ru':'Прочее','en':'Other','uk':'Інше','kk':'Басқа'}.get(lang,'Other'),
    }

    category_keys = [k for k in cat_labels if k in cats]
    current_cat = request.args.get('cat', category_keys[0] if category_keys else 'fruits')
    if current_cat not in cats:
        current_cat = category_keys[0] if category_keys else 'other'

    foods = sorted(cats.get(current_cat, []), key=lambda x: x['name'])

    return render_template(
        'categories.html',
        categories=cats,
        category_keys=category_keys,
        cat_labels=cat_labels,
        current_cat=current_cat,
        foods=foods,
        t=t,
        lang=lang,
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials', 'error')
    
    lang = session.get('lang', 'ru')
    t = translations.get(lang, translations['ru'])
    return render_template('login.html', t=t, lang=lang)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        language = request.form.get('language', 'ru')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
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
    lang = current_user.language or 'ru'
    t = translations.get(lang, translations['ru'])
    from datetime import datetime
    trial_available = not current_user.trial_used and not current_user.is_premium
    trial_active = (current_user.trial_ends and current_user.trial_ends > datetime.utcnow())
    return render_template('premium.html', t=t, lang=lang,
                           trial_available=trial_available, trial_active=trial_active)

@app.route('/start-trial', methods=['GET', 'POST'])
@login_required
def start_trial():
    from datetime import datetime, timedelta
    if current_user.trial_used or current_user.is_premium:
        return redirect(url_for('premium'))
    # Помечаем пробный период — активируется после оплаты 11 руб.
    # Здесь заглушка — активируем сразу (после интеграции ЮKassa заменить)
    current_user.trial_used = True
    current_user.is_premium = True
    current_user.trial_ends = datetime.utcnow() + timedelta(days=7)
    db.session.commit()
    lang = current_user.language or 'ru'
    t = translations.get(lang, translations['ru'])
    return render_template('premium.html', t=t, lang=lang,
                           trial_available=False, trial_active=True,
                           trial_success=True)

@app.route('/language', methods=['POST'])
def set_language():
    lang = request.form.get('lang', 'ru')
    if current_user.is_authenticated:
        current_user.language = lang
        db.session.commit()
    else:
        session['lang'] = lang
    return redirect(request.referrer or '/')

# ===================== ИНИЦИАЛИЗАЦИЯ =====================

with app.app_context():
    db.create_all()
    
    # Инициализируем food_data в БД если пусто
    if Food.query.count() == 0:
        from food_data import food_data
        for food in food_data:
            f = Food(
                name_ru=food['name_ru'],
                name_en=food.get('name_en', food['name_ru']),
                name_uk=food.get('name_uk', food['name_ru']),
                name_kk=food.get('name_kk', food['name_ru']),
                calories=food['calories'],
                protein=food.get('protein', 0),
                fat=food.get('fat', 0),
                carbs=food.get('carbs', 0),
                category=food.get('category', 'other')
            )
            db.session.add(f)
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
