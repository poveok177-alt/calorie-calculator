from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
import json
import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
import json
import os
try:
    from yookassa import Configuration, Payment
except ImportError:
    pass
import uuid
from dotenv import load_dotenv
import os

import uuid
from dotenv import load_dotenv
import os

load_dotenv()

Client.configure(
    account_id=os.getenv('YOOKASSA_SHOP_ID', '123456'),
    secret_key=os.getenv('YOOKASSA_SECRET_KEY', 'test_key')
)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mojasupertajnayastrokakotoruyaniktonevzlomaet123'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///calories.db'
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

    # Пробный период
    trial_used = db.Column(db.Boolean, default=False)
    trial_ends = db.Column(db.DateTime, nullable=True)
    email_reminders = db.Column(db.Boolean, default=True)

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

# ===================== ПЕРЕВОДЫ =====================

TRANSLATIONS = {
    'ru': {
        'app_name': 'КалориМинт',
        'tagline': 'Забота о теле начинается здесь',
        'search_placeholder': 'Поиск продукта...',
        'add_food': 'Добавить',
        'today': 'Сегодня',
        'calories': 'Калории',
        'protein': 'Белки',
        'fat': 'Жиры',
        'carbs': 'Углеводы',
        'grams': 'граммов',
        'categories': 'Категории',
        'fruits': 'Фрукты 🍎',
        'vegetables': 'Овощи 🥦',
        'meat': 'Мясо 🥩',
        'dairy': 'Молочное 🥛',
        'grains': 'Злаки 🌾',
        'nuts': 'Орехи и семена 🌰',
        'fish': 'Рыба и морепродукты 🐟',
        'sweets': 'Сладкое 🍫',
        'drinks': 'Напитки 🥤',
        'other': 'Другое 🍽️',
        'login': 'Войти',
        'register': 'Регистрация',
        'logout': 'Выйти',
        'premium': 'Премиум',
        'history': 'История питания',
        'goals': 'Мои цели',
        'breakfast': 'Завтрак',
        'lunch': 'Обед',
        'dinner': 'Ужин',
        'snack': 'Перекус',
        'daily_goal': 'Дневная цель',
        'consumed': 'Съедено',
        'remaining': 'Осталось',
        'per_100g': 'на 100 г',
        'get_premium': 'Получить Премиум',
        'premium_features': 'Премиум функции',
        'choose_language': 'Выберите язык',
        'email': 'Email',
        'password': 'Пароль',
        'username': 'Имя пользователя',
        'no_account': 'Нет аккаунта?',
        'have_account': 'Уже есть аккаунт?',
        'did_you_mean': 'Возможно вы имели в виду:',
        'not_found': 'Ничего не найдено',
        'month_history': 'История за месяц',
        'weight_goal': 'Цель по весу',
        'current_weight': 'Текущий вес (кг)',
        'goal_weight': 'Цель (кг)',
        'height': 'Рост (см)',
        'save': 'Сохранить',
        'bju_counter': 'Счётчик БЖУ',
        'no_ads': 'Без рекламы',
        'premium_desc': 'Разблокируй все возможности для достижения твоих целей',
        'subscribe': 'Подписаться — 199 ₽/мес',
        'remove': 'Удалить',
        'kcal': 'ккал',
        'g': 'г',
    },
    'en': {
        'app_name': 'CaloriMint',
        'tagline': 'Your body care starts here',
        'search_placeholder': 'Search food...',
        'add_food': 'Add',
        'today': 'Today',
        'calories': 'Calories',
        'protein': 'Protein',
        'fat': 'Fat',
        'carbs': 'Carbs',
        'grams': 'grams',
        'categories': 'Categories',
        'fruits': 'Fruits 🍎',
        'vegetables': 'Vegetables 🥦',
        'meat': 'Meat 🥩',
        'dairy': 'Dairy 🥛',
        'grains': 'Grains 🌾',
        'nuts': 'Nuts & Seeds 🌰',
        'fish': 'Fish & Seafood 🐟',
        'sweets': 'Sweets 🍫',
        'drinks': 'Drinks 🥤',
        'other': 'Other 🍽️',
        'login': 'Login',
        'register': 'Register',
        'logout': 'Logout',
        'premium': 'Premium',
        'history': 'Food history',
        'goals': 'My goals',
        'breakfast': 'Breakfast',
        'lunch': 'Lunch',
        'dinner': 'Dinner',
        'snack': 'Snack',
        'daily_goal': 'Daily goal',
        'consumed': 'Consumed',
        'remaining': 'Remaining',
        'per_100g': 'per 100g',
        'get_premium': 'Get Premium',
        'premium_features': 'Premium features',
        'choose_language': 'Choose language',
        'email': 'Email',
        'password': 'Password',
        'username': 'Username',
        'no_account': "Don't have an account?",
        'have_account': 'Already have an account?',
        'did_you_mean': 'Did you mean:',
        'not_found': 'Nothing found',
        'month_history': 'Monthly history',
        'weight_goal': 'Weight goal',
        'current_weight': 'Current weight (kg)',
        'goal_weight': 'Goal weight (kg)',
        'height': 'Height (cm)',
        'save': 'Save',
        'bju_counter': 'Macros counter',
        'no_ads': 'No ads',
        'premium_desc': 'Unlock all features to reach your goals',
        'subscribe': 'Subscribe — $2.99/mo',
        'remove': 'Remove',
        'kcal': 'kcal',
        'g': 'g',
    },
    'uk': {
        'app_name': 'КалоріМʼята',
        'tagline': 'Турбота про тіло починається тут',
        'search_placeholder': 'Пошук продукту...',
        'add_food': 'Додати',
        'today': 'Сьогодні',
        'calories': 'Калорії',
        'protein': 'Білки',
        'fat': 'Жири',
        'carbs': 'Вуглеводи',
        'grams': 'грамів',
        'categories': 'Категорії',
        'fruits': 'Фрукти 🍎',
        'vegetables': 'Овочі 🥦',
        'meat': 'Мʼясо 🥩',
        'dairy': 'Молочне 🥛',
        'grains': 'Злаки 🌾',
        'nuts': 'Горіхи та насіння 🌰',
        'fish': 'Риба та морепродукти 🐟',
        'sweets': 'Солодке 🍫',
        'drinks': 'Напої 🥤',
        'other': 'Інше 🍽️',
        'login': 'Увійти',
        'register': 'Реєстрація',
        'logout': 'Вийти',
        'premium': 'Преміум',
        'history': 'Історія харчування',
        'goals': 'Мої цілі',
        'breakfast': 'Сніданок',
        'lunch': 'Обід',
        'dinner': 'Вечеря',
        'snack': 'Перекус',
        'daily_goal': 'Денна ціль',
        'consumed': 'Зʼїдено',
        'remaining': 'Залишилось',
        'per_100g': 'на 100 г',
        'get_premium': 'Отримати Преміум',
        'premium_features': 'Преміум функції',
        'choose_language': 'Оберіть мову',
        'email': 'Email',
        'password': 'Пароль',
        'username': 'Імʼя користувача',
        'no_account': 'Немає акаунту?',
        'have_account': 'Вже є акаунт?',
        'did_you_mean': 'Можливо ви мали на увазі:',
        'not_found': 'Нічого не знайдено',
        'month_history': 'Історія за місяць',
        'weight_goal': 'Ціль за вагою',
        'current_weight': 'Поточна вага (кг)',
        'goal_weight': 'Ціль (кг)',
        'height': 'Зріст (см)',
        'save': 'Зберегти',
        'bju_counter': 'Лічильник БЖВ',
        'no_ads': 'Без реклами',
        'premium_desc': 'Розблокуй усі можливості для досягнення цілей',
        'subscribe': 'Підписатись — 79 ₴/міс',
        'remove': 'Видалити',
        'kcal': 'ккал',
        'g': 'г',
    },
    'kk': {
        'app_name': 'КалориМята',
        'tagline': 'Денсаулық туралы қамқорлық осында басталады',
        'search_placeholder': 'Өнімді іздеу...',
        'add_food': 'Қосу',
        'today': 'Бүгін',
        'calories': 'Калория',
        'protein': 'Ақуыз',
        'fat': 'Май',
        'carbs': 'Көмірсу',
        'grams': 'грамм',
        'categories': 'Санаттар',
        'fruits': 'Жемістер 🍎',
        'vegetables': 'Көкөністер 🥦',
        'meat': 'Ет 🥩',
        'dairy': 'Сүт өнімдері 🥛',
        'grains': 'Дән 🌾',
        'nuts': 'Жаңғақтар 🌰',
        'fish': 'Балық 🐟',
        'sweets': 'Тәттілер 🍫',
        'drinks': 'Сусындар 🥤',
        'other': 'Басқа 🍽️',
        'login': 'Кіру',
        'register': 'Тіркелу',
        'logout': 'Шығу',
        'premium': 'Премиум',
        'history': 'Тамақтану тарихы',
        'goals': 'Менің мақсаттарым',
        'breakfast': 'Таңғы ас',
        'lunch': 'Түскі ас',
        'dinner': 'Кешкі ас',
        'snack': 'Тамақ аралық',
        'daily_goal': 'Күнделікті мақсат',
        'consumed': 'Жеген',
        'remaining': 'Қалды',
        'per_100g': '100 г үшін',
        'get_premium': 'Премиум алу',
        'premium_features': 'Премиум мүмкіндіктер',
        'choose_language': 'Тілді таңдаңыз',
        'email': 'Email',
        'password': 'Құпия сөз',
        'username': 'Пайдаланушы аты',
        'no_account': 'Тіркелмеген бе?',
        'have_account': 'Тіркелген бе?',
        'did_you_mean': 'Мүмкін сіз ойлаған:',
        'not_found': 'Ештеңе табылмады',
        'month_history': 'Ай тарихы',
        'weight_goal': 'Салмақ мақсаты',
        'current_weight': 'Қазіргі салмақ (кг)',
        'goal_weight': 'Мақсат (кг)',
        'height': 'Бой (см)',
        'save': 'Сақтау',
        'bju_counter': 'БЖК санауышы',
        'no_ads': 'Жарнамасыз',
        'premium_desc': 'Мақсатыңызға жету үшін барлық мүмкіндіктерді ашыңыз',
        'subscribe': 'Жазылу — 799 ₸/ай',
        'remove': 'Жою',
        'kcal': 'ккал',
        'g': 'г',
    }
}

CATEGORY_KEYS = ['fruits', 'vegetables', 'meat', 'dairy', 'grains', 'nuts', 'fish', 'sweets', 'drinks', 'other']

def get_t():
    lang = session.get('language', 'ru')
    return TRANSLATIONS.get(lang, TRANSLATIONS['ru'])

def get_food_name(food, lang):
    if lang == 'en': return food.name_en
    if lang == 'uk': return food.name_uk or food.name_ru
    if lang == 'kk': return food.name_kk or food.name_ru
    return food.name_ru

# ===================== МАРШРУТЫ =====================

@app.route('/')
def index():
    if not session.get('language'):
        return redirect(url_for('choose_language'))
    t = get_t()
    lang = session.get('language', 'ru')
    
    today_entries = []
    total_cal = total_protein = total_fat = total_carbs = 0
    daily_goal = 2000
    
    if current_user.is_authenticated:
        today_entries = FoodEntry.query.filter_by(
            user_id=current_user.id, date=date.today()
        ).order_by(FoodEntry.created_at.desc()).all()
        
        for e in today_entries:
            total_cal += e.calories
            total_protein += e.protein
            total_fat += e.fat
            total_carbs += e.carbs
        daily_goal = current_user.daily_calorie_goal or 2000
    
    progress_pct = min(100, int(total_cal / daily_goal * 100)) if daily_goal > 0 else 0
    
    return render_template('index.html', t=t, lang=lang,
                           today_entries=today_entries,
                           total_cal=round(total_cal),
                           total_protein=round(total_protein, 1),
                           total_fat=round(total_fat, 1),
                           total_carbs=round(total_carbs, 1),
                           daily_goal=daily_goal,
                           progress_pct=progress_pct,
                           category_keys=CATEGORY_KEYS)

@app.route('/set-language/<lang>')
def set_language(lang):
    if lang in TRANSLATIONS:
        session['language'] = lang
        session.modified = True
    return redirect(url_for('index'))

@app.route('/choose-language')
def choose_language():
    return render_template('choose_language.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    t = get_t()
    lang = session.get('language', 'ru')
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user:
            if check_password_hash(user.password_hash, password):
                login_user(user, remember=True)
                session['language'] = user.language
                session.modified = True
                return redirect(url_for('index'))
            else:
                flash('Неверный пароль')
        else:
            flash('Пользователь с таким email не найден')
    return render_template('login.html', t=t, lang=lang)

@app.route('/register', methods=['GET', 'POST'])
def register():
    t = get_t()
    lang = session.get('language', 'ru')
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if User.query.filter_by(email=email).first():
            flash('Email уже используется')
            return render_template('register.html', t=t, lang=lang)

        if User.query.filter_by(username=username).first():
            flash('Имя пользователя уже занято')
            return render_template('register.html', t=t, lang=lang)

        try:
            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
                language=lang
            )
            db.session.add(user)
            db.session.commit()
            login_user(user, remember=True)
            session['language'] = lang
            session.modified = True
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash('Ошибка при регистрации, попробуй ещё раз')
            return render_template('register.html', t=t, lang=lang)

    return render_template('register.html', t=t, lang=lang)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/premium')
def premium():
    t = get_t()
    lang = session.get('language', 'ru')
    trial_available = False
    if current_user.is_authenticated and not current_user.trial_used:
        trial_available = True
    return render_template('premium.html', t=t, lang=lang, trial_available=trial_available)
@app.route('/start-trial')
@login_required
def start_trial():
    if current_user.trial_used:
        flash('Пробный период уже использован')
        return redirect(url_for('premium'))
    from datetime import timedelta
    current_user.trial_used = True
    current_user.trial_ends = datetime.utcnow() + timedelta(days=7)
    current_user.is_premium = True
    db.session.commit()
    flash('🎉 Пробный период на 7 дней активирован!')
    return redirect(url_for('index'))

@app.before_request
def check_trial():
    if current_user.is_authenticated and current_user.is_premium:
        if current_user.trial_ends and datetime.utcnow() > current_user.trial_ends:
            current_user.is_premium = False
            db.session.commit()
@app.route('/history')
@login_required
def history():
    t = get_t()
    lang = session.get('language', 'ru')
    if not current_user.is_premium:
        return redirect(url_for('premium'))
    
    from datetime import timedelta
    today = date.today()
    thirty_days_ago = today - timedelta(days=30)
    
    entries = FoodEntry.query.filter(
        FoodEntry.user_id == current_user.id,
        FoodEntry.date >= thirty_days_ago
    ).order_by(FoodEntry.date.desc(), FoodEntry.created_at.desc()).all()
    
    # Группируем по дням
    days = {}
    for e in entries:
        d = str(e.date)
        if d not in days:
            days[d] = {'entries': [], 'total_cal': 0, 'total_protein': 0, 'total_fat': 0, 'total_carbs': 0}
        days[d]['entries'].append(e)
        days[d]['total_cal'] += e.calories
        days[d]['total_protein'] += e.protein
        days[d]['total_fat'] += e.fat
        days[d]['total_carbs'] += e.carbs
    
    return render_template('history.html', t=t, lang=lang, days=days)

@app.route('/goals', methods=['GET', 'POST'])
@login_required
def goals():
    t = get_t()
    lang = session.get('language', 'ru')
    if not current_user.is_premium:
        return redirect(url_for('premium'))

    if request.method == 'POST':
        current_user.current_weight = float(request.form.get('current_weight') or 0)
        current_user.goal_weight = float(request.form.get('goal_weight') or 0)
        current_user.height = float(request.form.get('height') or 0)
        current_user.daily_calorie_goal = int(request.form.get('daily_calorie_goal') or 2000)
        current_user.water_goal = int(request.form.get('water_goal') or 8)
        current_user.protein_goal = int(request.form.get('protein_goal') or 150)
        current_user.fat_goal = int(request.form.get('fat_goal') or 70)
        current_user.carbs_goal = int(request.form.get('carbs_goal') or 250)
        current_user.age = int(request.form.get('age') or 25)
        db.session.commit()
        flash('Цели сохранены!')

    return render_template('goals.html', t=t, lang=lang)

@app.route('/categories')
def categories():
    t = get_t()
    lang = session.get('language', 'ru')
    cat = request.args.get('cat', 'fruits')
    
    foods = Food.query.filter_by(category=cat).all()
    foods_data = []
    for f in foods:
        foods_data.append({
            'id': f.id,
            'name': get_food_name(f, lang),
            'calories': f.calories,
            'protein': f.protein,
            'fat': f.fat,
            'carbs': f.carbs,
        })
    foods_data.sort(key=lambda x: x['name'])
    
    return render_template('categories.html', t=t, lang=lang,
                           foods=foods_data, current_cat=cat,
                           category_keys=CATEGORY_KEYS)

# ===================== API =====================

@app.route('/api/search')
def api_search():
    lang = session.get('language', 'ru')
    q = request.args.get('q', '').strip().lower()
    
    if not q:
        return jsonify([])
    
    # Точный поиск
    name_col = {'ru': Food.name_ru, 'en': Food.name_en, 'uk': Food.name_uk, 'kk': Food.name_kk}.get(lang, Food.name_ru)
    
    foods = Food.query.filter(name_col.ilike(f'%{q}%')).limit(10).all()
    
    # Умный поиск с опечатками — если меньше 2 результатов
    if len(foods) < 2:
        all_foods = Food.query.all()
        def similarity(a, b):
            a, b = a.lower(), b.lower()
            if a in b or b in a: return 0.9
            # Simple char overlap
            common = sum(1 for c in a if c in b)
            return common / max(len(a), len(b), 1)
        
        scored = []
        for f in all_foods:
            name = get_food_name(f, lang).lower()
            s = similarity(q, name)
            if s > 0.4:
                scored.append((s, f))
        scored.sort(reverse=True)
        foods = [f for _, f in scored[:10]]
    
    result = []
    for f in foods:
        result.append({
            'id': f.id,
            'name': get_food_name(f, lang),
            'calories': f.calories,
            'protein': f.protein,
            'fat': f.fat,
            'carbs': f.carbs,
            'category': f.category,
        })
    return jsonify(result)

@app.route('/api/add-entry', methods=['POST'])
@login_required
def api_add_entry():
    data = request.get_json()
    food = Food.query.get(data['food_id'])
    if not food:
        return jsonify({'error': 'Food not found'}), 404
    
    lang = session.get('language', 'ru')
    grams = float(data.get('grams', 100))
    ratio = grams / 100
    
    entry = FoodEntry(
        user_id=current_user.id,
        food_id=food.id,
        food_name=get_food_name(food, lang),
        grams=grams,
        calories=round(food.calories * ratio, 1),
        protein=round(food.protein * ratio, 1),
        fat=round(food.fat * ratio, 1),
        carbs=round(food.carbs * ratio, 1),
        meal_type=data.get('meal_type', 'other')
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify({'success': True, 'entry_id': entry.id})

@app.route('/api/remove-entry/<int:entry_id>', methods=['DELETE'])
@login_required
def api_remove_entry(entry_id):
    entry = FoodEntry.query.filter_by(id=entry_id, user_id=current_user.id).first()
    if entry:
        db.session.delete(entry)
        db.session.commit()
    return jsonify({'success': True})

@app.route('/api/clear-day', methods=['DELETE'])
@login_required
def api_clear_day():
    FoodEntry.query.filter_by(user_id=current_user.id, date=date.today()).delete()
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/water', methods=['GET', 'POST'])
@login_required
def api_water():
    key = f'water_{current_user.id}_{date.today()}'
    if request.method == 'POST':
        data = request.get_json()
        session[key] = data.get('glasses', 0)
        session.modified = True
        return jsonify({'success': True, 'glasses': session[key]})
    return jsonify({'glasses': session.get(key, 0), 'goal': current_user.water_goal or 8})

@app.route('/api/today-summary')
@login_required
def api_today_summary():
    entries = FoodEntry.query.filter_by(user_id=current_user.id, date=date.today()).all()
    total_cal = sum(e.calories for e in entries)
    total_protein = sum(e.protein for e in entries)
    total_fat = sum(e.fat for e in entries)
    total_carbs = sum(e.carbs for e in entries)
    return jsonify({
        'calories': round(total_cal),
        'protein': round(total_protein, 1),
        'fat': round(total_fat, 1),
        'carbs': round(total_carbs, 1),
    })

# ===================== ЗАПУСК =====================

def init_db():
    with app.app_context():
        db.create_all()
        
        # Добавляем продукты если БД пустая
        if Food.query.count() < 9999:
            Food.query.delete()
            db.session.commit()
            from food_data import FOODS
            for f in FOODS:
                food = Food(**f)
                db.session.add(food)
            db.session.commit()
            print(f"✅ Добавлено {len(FOODS)} продуктов в базу данных")
@app.route('/api/create-payment', methods=['POST'])
@login_required
def create_payment():
    try:
        payment = Payment.create({
            "amount": {
                "value": "199.00",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": request.host_url.rstrip('/') + '/premium-success'
            },
            "description": f"Премиум подписка для {current_user.username}",
            "metadata": {
                "user_id": current_user.id,
                "email": current_user.email
            }
        })

        return jsonify({
            'success': True,
            'confirmation_url': payment.confirmation.confirmation_url
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/premium-success')
@login_required
def premium_success():
    current_user.is_premium = True
    db.session.commit()
    flash('✅ Спасибо! Премиум активирован!', 'success')
    return redirect('/')


@app.route('/webhook/yookassa', methods=['POST'])
def yookassa_webhook():
    try:
        data = request.json
        if data.get('event') == 'payment.succeeded':
            payment_data = data.get('object', {})
            user_id = payment_data.get('metadata', {}).get('user_id')

            if user_id:
                user = User.query.get(user_id)
                if user:
                    user.is_premium = True
                    db.session.commit()

        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        return jsonify({'status': 'error'}), 400
if __name__ == '__main__':
    init_db()
    app.run(debug=True)
