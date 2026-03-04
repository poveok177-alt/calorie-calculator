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
    """Добавляет недостающие колонки в существующую БД (миграция без alembic)."""
    with app.app_context():
        try:
            inspector = db.inspect(db.engine)
            # Проверяем что таблица user существует
            if 'user' not in inspector.get_table_names():
                return  # db.create_all() создаст всё с нуля
            
            user_columns = [col['name'] for col in inspector.get_columns('user')]
            
            # Список новых колонок которые могут отсутствовать в старой БД
            new_columns = [
                ('favorites',       'TEXT DEFAULT \'[]\''),
                ('trial_used',      'BOOLEAN DEFAULT FALSE'),
                ('trial_ends',      'TIMESTAMP'),
                ('email_reminders', 'BOOLEAN DEFAULT TRUE'),
                ('is_premium',      'BOOLEAN DEFAULT FALSE'),
                ('current_weight',  'FLOAT'),
                ('goal_weight',     'FLOAT'),
                ('height',          'FLOAT'),
                ('daily_calorie_goal', 'INTEGER DEFAULT 2000'),
                ('water_goal',      'INTEGER DEFAULT 8'),
                ('protein_goal',    'INTEGER DEFAULT 150'),
                ('fat_goal',        'INTEGER DEFAULT 70'),
                ('carbs_goal',      'INTEGER DEFAULT 250'),
                ('age',             'INTEGER DEFAULT 25'),
                ('gender',          'VARCHAR(10) DEFAULT \'male\''),
                ('activity',        'VARCHAR(20) DEFAULT \'moderate\''),
                ('language',        'VARCHAR(10) DEFAULT \'ru\''),
            ]
            
            with db.engine.connect() as conn:
                for col_name, col_def in new_columns:
                    if col_name not in user_columns:
                        try:
                            # PostgreSQL и SQLite синтаксис
                            tbl = '"user"' if 'postgresql' in str(db.engine.url) else '"user"'
                            conn.execute(db.text(
                                f'ALTER TABLE {tbl} ADD COLUMN {col_name} {col_def}'
                            ))
                            conn.commit()
                            print(f'[init_db] Added column: {col_name}')
                        except Exception as e:
                            conn.rollback()
                            print(f'[init_db] Skip {col_name}: {e}')
        except Exception as e:
            print(f'[init_db] Error: {e}')

# ===================== ПЕРЕВОДЫ =====================

translations = {
    'ru': {
        # nav
        'app_name': 'CaloriMint', 'home': 'Главная', 'history': 'История',
        'goals': 'Цели', 'categories': 'Категории', 'premium': 'Премиум',
        'login': 'Вход', 'register': 'Регистрация', 'logout': 'Выход',
        'profile': 'Профиль', 'today': 'Сегодня', 'back': 'Назад',
        # food
        'search': 'Поиск продуктов...', 'search_placeholder': '🔍 Поиск продукта...',
        'add': 'Добавить', 'delete': 'Удалить', 'save': 'Сохранить',
        'calories': 'Калории', 'protein': 'Белки', 'fat': 'Жиры', 'carbs': 'Углеводы',
        'kcal': 'ккал', 'g': 'г', 'grams': 'г', 'ml': 'мл',
        'per100g': 'на 100 г', 'per100ml': 'на 100 мл',
        # meals
        'breakfast': 'Завтрак', 'lunch': 'Обед', 'dinner': 'Ужин', 'snack': 'Перекус',
        'clear': 'Очистить', 'clear_meal_confirm': 'Очистить',
        'clear_day': '🗑 Очистить всё за сегодня',
        'clear_day_confirm': 'Удалить ВСЕ продукты за сегодня?',
        'delete_entry_confirm': 'Удалить продукт?',
        'all': 'Все',
        # totals
        'today_title': '🎯 Сегодня', 'of': 'из',
        'water': '💧 Вода', 'cups': 'стак.',
        # modal
        'weight_label': 'Вес:', 'volume_label': 'Объём:',
        'total': 'Итого', 'cancel': 'Отмена', 'confirm_add': '✓ Добавить',
        'quick_loading': '⏳ Загрузка...', 'not_found': 'Ничего не найдено 🤷',
        'load_error': '❌ Ошибка загрузки',
        # goals
        'weight_goal': 'Цель по весу',
        'current_weight': 'Текущий вес (кг)', 'goal_weight': 'Целевой вес (кг)',
        'height': 'Рост (см)', 'age': 'Возраст', 'gender': 'Пол',
        'gender_male': '👨 Мужчина', 'gender_female': '👩 Женщина',
        'activity': 'Уровень активности',
        'act_sedentary': '📍 Сидячий образ жизни (1.2)',
        'act_light': '🚶 Лёгкая активность (1.375)',
        'act_moderate': '🏃 Умеренная активность (1.55)',
        'act_active': '💪 Активный образ жизни (1.725)',
        'act_very_active': '🏋️ Очень активный (1.9)',
        'formula_note': '📍 Калькулятор использует формулу Харриса-Бенедикта. Точность ≈ 90%.',
        'daily_goal': '🔥 Калории (ккал в день)',
        'protein_goal_label': '🥩 Белки (г в день)',
        'fat_goal_label': '🥑 Жиры (г в день)',
        'carbs_goal_label': '🍞 Углеводы (г в день)',
        'water_goal_label': '💧 Норма воды (стаканов в день)',
        'calc_auto': '🧮 Рассчитать автоматически',
        'now': 'Сейчас', 'goal': 'Цель',
        'to_goal_lose': 'До цели: {d} кг похудеть 💪',
        'to_goal_gain': 'До цели: {d} кг набрать 🌱',
        'goal_reached': '🎉 Цель достигнута!',
        'your_norms': '📋 Твои дневные нормы:',
        # categories
        'products_count': 'продуктов · сортировка по алфавиту',
        'add_from_cat': '+ Добавить',
        'grams_label': 'Количество (граммов)',
        'login_required': 'Войдите в аккаунт, чтобы добавлять продукты',
        'added_to_diary': 'добавлен в дневник!',
        # premium
        'premium_desc': 'Раскройте весь потенциал здорового питания',
        'free_badge': 'Бесплатно', 'premium_badge': '⭐ Премиум',
        'month_history': 'История за 30 дней', 'bju_counter': 'Счётчик БЖУ',
        'no_ads': 'Без рекламы',
        'per_month': 'в месяц',
        'trial_btn': '🎁 7 дней за 11 ₽',
        'buy_btn': 'Получить Премиум 🌿',
        'trial_only_new': '7 дней полного Премиума · Только для новых',
        'after_trial': 'После пробного периода — 129 ₽/месяц, отмена в любой момент',
        'secure_pay': 'Безопасная оплата · Отмена в любой момент',
        'premium_active': 'Премиум активен!',
        'all_features': 'Все функции доступны',
        'trial_until': 'Пробный период до',
        'trial_success_msg': '🎉 Пробный период активирован! 7 дней Премиума доступны.',
        'food_search_feat': 'Поиск продуктов',
        'food_search_desc': '100+ продуктов, поиск по категориям',
        'cal_counter_feat': 'Счётчик калорий',
        'cal_counter_desc': 'Завтрак, обед, ужин, перекус',
        'hist_feat_desc': 'Полная история питания за 30 дней',
        'bju_feat_desc': 'Белки, жиры, углеводы под контролем',
        'weight_feat_desc': 'ИМТ, прогресс к цели, калькулятор',
        'water_feat': 'Счётчик воды',
        'water_feat_desc': 'Контролируйте водный баланс каждый день',
        'sub_label': 'Премиум подписка',
        'hist_price_feat': 'История питания за 30 дней',
        'bju_price_feat': 'Счётчик БЖУ',
        'weight_price_feat': 'Цель по весу и ИМТ',
        'water_price_feat': 'Счётчик воды',
        'special_offer': 'Специальное предложение',
        'trial_period': 'Пробный период',
        'new_users_only': '7 дней полного Премиума · Только для новых пользователей',
        'trial_all_feat': 'Все Премиум функции',
        'trial_hist': 'История питания',
        'trial_bju': 'Счётчик БЖУ',
        'select': 'Выбери...',
        # js alert texts (passed as json)
        'calc_fill_all': 'Заполни все поля: вес, рост, возраст, пол и активность!',
        'calc_done': 'Расчёт завершён!',
        'calc_bmr': 'Метаболизм (BMR)',
        'calc_tdee': 'Дневная норма (TDEE)',
        'calc_save': 'Не забудь нажать "Сохранить"!',
        'calc_profile': 'Профиль',
        'calc_activity_label': 'Активность',
        'calc_male': 'мужчина', 'calc_female': 'женщина',
    },
    'en': {
        'app_name': 'CaloriMint', 'home': 'Home', 'history': 'History',
        'goals': 'Goals', 'categories': 'Categories', 'premium': 'Premium',
        'login': 'Login', 'register': 'Sign Up', 'logout': 'Logout',
        'profile': 'Profile', 'today': 'Today', 'back': 'Back',
        'search': 'Search products...', 'search_placeholder': '🔍 Search food...',
        'add': 'Add', 'delete': 'Delete', 'save': 'Save',
        'calories': 'Calories', 'protein': 'Protein', 'fat': 'Fat', 'carbs': 'Carbs',
        'kcal': 'kcal', 'g': 'g', 'grams': 'g', 'ml': 'ml',
        'per100g': 'per 100 g', 'per100ml': 'per 100 ml',
        'breakfast': 'Breakfast', 'lunch': 'Lunch', 'dinner': 'Dinner', 'snack': 'Snack',
        'clear': 'Clear', 'clear_meal_confirm': 'Clear',
        'clear_day': '🗑 Clear today\'s log',
        'clear_day_confirm': 'Delete ALL food for today?',
        'delete_entry_confirm': 'Remove this item?',
        'all': 'All',
        'today_title': '🎯 Today', 'of': 'of',
        'water': '💧 Water', 'cups': 'cups',
        'weight_label': 'Weight:', 'volume_label': 'Volume:',
        'total': 'Total', 'cancel': 'Cancel', 'confirm_add': '✓ Add',
        'quick_loading': '⏳ Loading...', 'not_found': 'Nothing found 🤷',
        'load_error': '❌ Load error',
        'weight_goal': 'Weight goal',
        'current_weight': 'Current weight (kg)', 'goal_weight': 'Target weight (kg)',
        'height': 'Height (cm)', 'age': 'Age', 'gender': 'Gender',
        'gender_male': '👨 Male', 'gender_female': '👩 Female',
        'activity': 'Activity level',
        'act_sedentary': '📍 Sedentary (1.2)',
        'act_light': '🚶 Lightly active (1.375)',
        'act_moderate': '🏃 Moderately active (1.55)',
        'act_active': '💪 Very active (1.725)',
        'act_very_active': '🏋️ Extra active (1.9)',
        'formula_note': '📍 Uses Harris-Benedict formula. Accuracy ≈ 90%.',
        'daily_goal': '🔥 Calories (kcal/day)',
        'protein_goal_label': '🥩 Protein (g/day)',
        'fat_goal_label': '🥑 Fat (g/day)',
        'carbs_goal_label': '🍞 Carbs (g/day)',
        'water_goal_label': '💧 Water goal (glasses/day)',
        'calc_auto': '🧮 Calculate automatically',
        'now': 'Current', 'goal': 'Goal',
        'to_goal_lose': 'To goal: {d} kg to lose 💪',
        'to_goal_gain': 'To goal: {d} kg to gain 🌱',
        'goal_reached': '🎉 Goal reached!',
        'your_norms': '📋 Your daily targets:',
        'products_count': 'products · sorted by name',
        'add_from_cat': '+ Add',
        'grams_label': 'Amount (grams)',
        'login_required': 'Log in to add foods to your diary',
        'added_to_diary': 'added to diary!',
        'premium_desc': 'Unlock the full potential of healthy eating',
        'free_badge': 'Free', 'premium_badge': '⭐ Premium',
        'month_history': '30-day history', 'bju_counter': 'Macro tracker',
        'no_ads': 'Ad-free',
        'per_month': 'per month',
        'trial_btn': '🎁 7 days for 11 ₽',
        'buy_btn': 'Get Premium 🌿',
        'trial_only_new': '7 days full Premium · New users only',
        'after_trial': 'After trial — 129 ₽/month, cancel anytime',
        'secure_pay': 'Secure payment · Cancel anytime',
        'premium_active': 'Premium is active!',
        'all_features': 'All features available',
        'trial_until': 'Trial until',
        'trial_success_msg': '🎉 Trial activated! 7 days of Premium are ready.',
        'food_search_feat': 'Food search',
        'food_search_desc': '100+ foods, search by category',
        'cal_counter_feat': 'Calorie counter',
        'cal_counter_desc': 'Breakfast, lunch, dinner, snack',
        'hist_feat_desc': 'Full 30-day nutrition history',
        'bju_feat_desc': 'Proteins, fats, carbs in control',
        'weight_feat_desc': 'BMI, goal progress, macro calculator',
        'water_feat': 'Water tracker',
        'water_feat_desc': 'Track your daily water intake',
        'sub_label': 'Premium subscription',
        'hist_price_feat': '30-day nutrition history',
        'bju_price_feat': 'Macro tracker',
        'weight_price_feat': 'Weight goal & BMI',
        'water_price_feat': 'Water tracker',
        'special_offer': 'Special offer',
        'trial_period': 'Free trial',
        'new_users_only': '7 days of full Premium · New users only',
        'trial_all_feat': 'All Premium features',
        'trial_hist': 'Nutrition history',
        'trial_bju': 'Macro tracker',
        'select': 'Choose...',
        'calc_fill_all': 'Fill in all fields: weight, height, age, gender and activity!',
        'calc_done': 'Calculation complete!',
        'calc_bmr': 'Metabolism (BMR)',
        'calc_tdee': 'Daily target (TDEE)',
        'calc_save': 'Don\'t forget to press "Save"!',
        'calc_profile': 'Profile',
        'calc_activity_label': 'Activity',
        'calc_male': 'male', 'calc_female': 'female',
    },
    'uk': {
        'app_name': 'CaloriMint', 'home': 'Головна', 'history': 'Історія',
        'goals': 'Цілі', 'categories': 'Категорії', 'premium': 'Преміум',
        'login': 'Вхід', 'register': 'Реєстрація', 'logout': 'Вихід',
        'profile': 'Профіль', 'today': 'Сьогодні', 'back': 'Назад',
        'search': 'Пошук продуктів...', 'search_placeholder': '🔍 Пошук продукту...',
        'add': 'Додати', 'delete': 'Видалити', 'save': 'Зберегти',
        'calories': 'Калорії', 'protein': 'Білки', 'fat': 'Жири', 'carbs': 'Вуглеводи',
        'kcal': 'ккал', 'g': 'г', 'grams': 'г', 'ml': 'мл',
        'per100g': 'на 100 г', 'per100ml': 'на 100 мл',
        'breakfast': 'Сніданок', 'lunch': 'Обід', 'dinner': 'Вечеря', 'snack': 'Закуска',
        'clear': 'Очистити', 'clear_meal_confirm': 'Очистити',
        'clear_day': '🗑 Очистити все за сьогодні',
        'clear_day_confirm': 'Видалити ВСЕ продукти за сьогодні?',
        'delete_entry_confirm': 'Видалити продукт?',
        'all': 'Все',
        'today_title': '🎯 Сьогодні', 'of': 'з',
        'water': '💧 Вода', 'cups': 'скл.',
        'weight_label': 'Вага:', 'volume_label': 'Обʼєм:',
        'total': 'Разом', 'cancel': 'Скасувати', 'confirm_add': '✓ Додати',
        'quick_loading': '⏳ Завантаження...', 'not_found': 'Нічого не знайдено 🤷',
        'load_error': '❌ Помилка завантаження',
        'weight_goal': 'Ціль по вазі',
        'current_weight': 'Поточна вага (кг)', 'goal_weight': 'Цільова вага (кг)',
        'height': 'Зріст (см)', 'age': 'Вік', 'gender': 'Стать',
        'gender_male': '👨 Чоловік', 'gender_female': '👩 Жінка',
        'activity': 'Рівень активності',
        'act_sedentary': '📍 Сидячий спосіб (1.2)',
        'act_light': '🚶 Легка активність (1.375)',
        'act_moderate': '🏃 Помірна активність (1.55)',
        'act_active': '💪 Активний спосіб (1.725)',
        'act_very_active': '🏋️ Дуже активний (1.9)',
        'formula_note': '📍 Формула Харріса-Бенедикта. Точність ≈ 90%.',
        'daily_goal': '🔥 Калорії (ккал на день)',
        'protein_goal_label': '🥩 Білки (г на день)',
        'fat_goal_label': '🥑 Жири (г на день)',
        'carbs_goal_label': '🍞 Вуглеводи (г на день)',
        'water_goal_label': '💧 Норма води (склянок на день)',
        'calc_auto': '🧮 Розрахувати автоматично',
        'now': 'Зараз', 'goal': 'Ціль',
        'to_goal_lose': 'До цілі: {d} кг схуднути 💪',
        'to_goal_gain': 'До цілі: {d} кг набрати 🌱',
        'goal_reached': '🎉 Ціль досягнута!',
        'your_norms': '📋 Твої денні норми:',
        'products_count': 'продуктів · сортування за алфавітом',
        'add_from_cat': '+ Додати',
        'grams_label': 'Кількість (грамів)',
        'login_required': 'Увійдіть, щоб додавати продукти',
        'added_to_diary': 'додано до щоденника!',
        'premium_desc': 'Розкрийте повний потенціал здорового харчування',
        'free_badge': 'Безкоштовно', 'premium_badge': '⭐ Преміум',
        'month_history': 'Історія за 30 днів', 'bju_counter': 'Лічильник БЖВ',
        'no_ads': 'Без реклами',
        'per_month': 'на місяць',
        'trial_btn': '🎁 7 днів за 11 ₽',
        'buy_btn': 'Отримати Преміум 🌿',
        'trial_only_new': '7 днів повного Преміума · Тільки для нових',
        'after_trial': 'Після пробного — 129 ₽/міс, скасування будь-коли',
        'secure_pay': 'Безпечна оплата · Скасування будь-коли',
        'premium_active': 'Преміум активний!',
        'all_features': 'Всі функції доступні',
        'trial_until': 'Пробний до',
        'trial_success_msg': '🎉 Пробний активовано! 7 днів Преміума доступні.',
        'food_search_feat': 'Пошук продуктів',
        'food_search_desc': '100+ продуктів, пошук за категоріями',
        'cal_counter_feat': 'Лічильник калорій',
        'cal_counter_desc': 'Сніданок, обід, вечеря, закуска',
        'hist_feat_desc': 'Повна історія харчування за 30 днів',
        'bju_feat_desc': 'Білки, жири, вуглеводи під контролем',
        'weight_feat_desc': 'ІМТ, прогрес до цілі, калькулятор',
        'water_feat': 'Лічильник води',
        'water_feat_desc': 'Контролюйте водний баланс кожен день',
        'sub_label': 'Преміум підписка',
        'hist_price_feat': 'Історія за 30 днів',
        'bju_price_feat': 'Лічильник БЖВ',
        'weight_price_feat': 'Ціль по вазі та ІМТ',
        'water_price_feat': 'Лічильник води',
        'special_offer': 'Спеціальна пропозиція',
        'trial_period': 'Пробний період',
        'new_users_only': '7 днів повного Преміума · Тільки для нових',
        'trial_all_feat': 'Всі Преміум функції',
        'trial_hist': 'Історія харчування',
        'trial_bju': 'Лічильник БЖВ',
        'select': 'Обери...',
        'calc_fill_all': 'Заповни всі поля: вага, зріст, вік, стать і активність!',
        'calc_done': 'Розрахунок завершено!',
        'calc_bmr': 'Метаболізм (BMR)',
        'calc_tdee': 'Денна норма (TDEE)',
        'calc_save': 'Не забудь натиснути "Зберегти"!',
        'calc_profile': 'Профіль',
        'calc_activity_label': 'Активність',
        'calc_male': 'чоловік', 'calc_female': 'жінка',
    },
    'kk': {
        'app_name': 'CaloriMint', 'home': 'Басты бет', 'history': 'Тарихы',
        'goals': 'Мақсаттар', 'categories': 'Санаттар', 'premium': 'Премиум',
        'login': 'Кіру', 'register': 'Тіркелу', 'logout': 'Шығу',
        'profile': 'Профиль', 'today': 'Бүгін', 'back': 'Артқа',
        'search': 'Өнімдерді іздеу...', 'search_placeholder': '🔍 Өнімді іздеу...',
        'add': 'Қосу', 'delete': 'Өшіру', 'save': 'Сақтау',
        'calories': 'Калориялар', 'protein': 'Ақуыз', 'fat': 'Май', 'carbs': 'Көмірсулар',
        'kcal': 'ккал', 'g': 'г', 'grams': 'г', 'ml': 'мл',
        'per100g': '100 г-ға', 'per100ml': '100 мл-ге',
        'breakfast': 'Таңғы ас', 'lunch': 'Түскі ас', 'dinner': 'Кешкі ас', 'snack': 'Аралық тамақ',
        'clear': 'Тазарту', 'clear_meal_confirm': 'Тазарту',
        'clear_day': '🗑 Бүгінгіні тазарту',
        'clear_day_confirm': 'Бүгінгі барлық тамақты жою?',
        'delete_entry_confirm': 'Өнімді жою?',
        'all': 'Барлығы',
        'today_title': '🎯 Бүгін', 'of': '/',
        'water': '💧 Су', 'cups': 'ст.',
        'weight_label': 'Салмақ:', 'volume_label': 'Көлем:',
        'total': 'Барлығы', 'cancel': 'Болдырмау', 'confirm_add': '✓ Қосу',
        'quick_loading': '⏳ Жүктелуде...', 'not_found': 'Ештеңе табылмады 🤷',
        'load_error': '❌ Жүктеу қатесі',
        'weight_goal': 'Салмақ мақсаты',
        'current_weight': 'Қазіргі салмақ (кг)', 'goal_weight': 'Мақсатты салмақ (кг)',
        'height': 'Бой (см)', 'age': 'Жас', 'gender': 'Жыныс',
        'gender_male': '👨 Ер', 'gender_female': '👩 Әйел',
        'activity': 'Белсенділік деңгейі',
        'act_sedentary': '📍 Отырықшы (1.2)',
        'act_light': '🚶 Аз белсенді (1.375)',
        'act_moderate': '🏃 Орташа белсенді (1.55)',
        'act_active': '💪 Белсенді (1.725)',
        'act_very_active': '🏋️ Өте белсенді (1.9)',
        'formula_note': '📍 Харрис-Бенедикт формуласы. Дәлдік ≈ 90%.',
        'daily_goal': '🔥 Калориялар (ккал/күн)',
        'protein_goal_label': '🥩 Ақуыз (г/күн)',
        'fat_goal_label': '🥑 Май (г/күн)',
        'carbs_goal_label': '🍞 Көмірсулар (г/күн)',
        'water_goal_label': '💧 Су нормасы (стақан/күн)',
        'calc_auto': '🧮 Автоматты есептеу',
        'now': 'Қазір', 'goal': 'Мақсат',
        'to_goal_lose': 'Мақсатқа: {d} кг азайту 💪',
        'to_goal_gain': 'Мақсатқа: {d} кг қосу 🌱',
        'goal_reached': '🎉 Мақсатқа жеттіңіз!',
        'your_norms': '📋 Күнделікті нормаларыңыз:',
        'products_count': 'өнімдер · алфавит бойынша',
        'add_from_cat': '+ Қосу',
        'grams_label': 'Мөлшер (грамм)',
        'login_required': 'Өнімдерді қосу үшін кіріңіз',
        'added_to_diary': 'күнделікке қосылды!',
        'premium_desc': 'Дұрыс тамақтанудың толық мүмкіндігін ашыңыз',
        'free_badge': 'Тегін', 'premium_badge': '⭐ Премиум',
        'month_history': '30 күндік тарих', 'bju_counter': 'БМУ есептегіш',
        'no_ads': 'Жарнамасыз',
        'per_month': 'айына',
        'trial_btn': '🎁 7 күн 11 ₽ үшін',
        'buy_btn': 'Премиум алу 🌿',
        'trial_only_new': '7 күн толық Премиум · Тек жаңалар үшін',
        'after_trial': 'Сынақтан кейін — 129 ₽/ай, кез келген уақытта',
        'secure_pay': 'Қауіпсіз төлем · Кез келген уақытта тоқтату',
        'premium_active': 'Премиум белсенді!',
        'all_features': 'Барлық функциялар қолжетімді',
        'trial_until': 'Сынақ мерзімі дейін',
        'trial_success_msg': '🎉 Сынақ мерзімі белсендірілді! 7 күн Премиум дайын.',
        'food_search_feat': 'Өнімдерді іздеу',
        'food_search_desc': '100+ өнімдер, санат бойынша іздеу',
        'cal_counter_feat': 'Калория есептегіш',
        'cal_counter_desc': 'Таңғы, түскі, кешкі ас, аралық',
        'hist_feat_desc': '30 күндік толық тамақтану тарихы',
        'bju_feat_desc': 'Ақуыз, май, көмірсулар бақылауда',
        'weight_feat_desc': 'ДМИ, мақсатқа прогресс, калькулятор',
        'water_feat': 'Су есептегіш',
        'water_feat_desc': 'Күнделікті су балансын бақылаңыз',
        'sub_label': 'Премиум жазылым',
        'hist_price_feat': '30 күндік тарих',
        'bju_price_feat': 'БМУ есептегіш',
        'weight_price_feat': 'Салмақ мақсаты және ДМИ',
        'water_price_feat': 'Су есептегіш',
        'special_offer': 'Арнайы ұсыныс',
        'trial_period': 'Сынақ мерзімі',
        'new_users_only': '7 күн толық Премиум · Тек жаңа қолданушылар',
        'trial_all_feat': 'Барлық Премиум мүмкіндіктер',
        'trial_hist': 'Тамақтану тарихы',
        'trial_bju': 'БМУ есептегіш',
        'select': 'Таңда...',
        'calc_fill_all': 'Барлық өрістерді толтырыңыз!',
        'calc_done': 'Есептеу аяқталды!',
        'calc_bmr': 'Метаболизм (BMR)',
        'calc_tdee': 'Күнделікті норма (TDEE)',
        'calc_save': '"Сақтау" батырмасын басуды ұмытпаңыз!',
        'calc_profile': 'Профиль',
        'calc_activity_label': 'Белсенділік',
        'calc_male': 'ер', 'calc_female': 'әйел',
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
            haystack = ' '.join([food.get('name_ru',''), food.get('name_en',''), food.get('name_uk',''), food.get('name_kk','')]).lower()
            if query not in haystack:
                continue
        results.append({'id': idx, 'name_ru': food['name_ru'], 'name_en': food.get('name_en', food['name_ru']),
            'calories': food['calories'], 'protein': food.get('protein', 0), 'fat': food.get('fat', 0),
            'carbs': food.get('carbs', 0), 'category': food.get('category', 'other')})
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
        cats[cat].append({'id': idx, 'name': food['name_ru'], 'calories': food['calories'],
            'protein': food.get('protein', 0), 'fat': food.get('fat', 0), 'carbs': food.get('carbs', 0), 'category': cat})
    cat_labels = {
        'fruits': '🍎 ' + {'ru':'Фрукты','en':'Fruits','uk':'Фрукти','kk':'Жемістер'}.get(lang,'Fruits'),
        'vegetables': '🥦 ' + {'ru':'Овощи','en':'Vegetables','uk':'Овочі','kk':'Көкөністер'}.get(lang,'Vegetables'),
        'meat': '🥩 ' + {'ru':'Мясо','en':'Meat','uk':'Мʼясо','kk':'Ет'}.get(lang,'Meat'),
        'dairy': '🥛 ' + {'ru':'Молочное','en':'Dairy','uk':'Молочне','kk':'Сүт өнімдері'}.get(lang,'Dairy'),
        'grains': '🌾 ' + {'ru':'Злаки','en':'Grains','uk':'Злаки','kk':'Астық'}.get(lang,'Grains'),
        'nuts': '🌰 ' + {'ru':'Орехи','en':'Nuts','uk':'Горіхи','kk':'Жаңғақтар'}.get(lang,'Nuts'),
        'fish': '🐟 ' + {'ru':'Рыба','en':'Fish','uk':'Риба','kk':'Балық'}.get(lang,'Fish'),
        'sweets': '🍫 ' + {'ru':'Сладкое','en':'Sweets','uk':'Солодке','kk':'Тәттілер'}.get(lang,'Sweets'),
        'drinks': '🥤 ' + {'ru':'Напитки','en':'Drinks','uk':'Напої','kk':'Сусындар'}.get(lang,'Drinks'),
        'supplements': '💊 ' + {'ru':'Витамины','en':'Supplements','uk':'Добавки','kk':'Қоспалар'}.get(lang,'Supplements'),
        'sports_nutrition': '💪 ' + {'ru':'Спортпит','en':'Sports Nutrition','uk':'Спортхарч','kk':'Спорт тамағы'}.get(lang,'Sports Nutrition'),
        'other': '🍽 ' + {'ru':'Прочее','en':'Other','uk':'Інше','kk':'Басқа'}.get(lang,'Other'),
    }
    category_keys = [k for k in cat_labels if k in cats]
    current_cat = request.args.get('cat', category_keys[0] if category_keys else 'fruits')
    if current_cat not in cats:
        current_cat = category_keys[0] if category_keys else 'other'
    foods = sorted(cats.get(current_cat, []), key=lambda x: x['name'])
    return render_template('categories.html', categories=cats, category_keys=category_keys,
        cat_labels=cat_labels, current_cat=current_cat, foods=foods, t=t, lang=lang)


@app.route('/premium')
@login_required
def premium():
    lang = current_user.language or 'ru'
    t = translations.get(lang, translations['ru'])
    trial_available = not current_user.trial_used and not current_user.is_premium
    trial_active = bool(current_user.trial_ends and current_user.trial_ends > datetime.utcnow())
    return render_template('premium.html', t=t, lang=lang,
                           trial_available=trial_available, trial_active=trial_active)

@app.route('/start-trial')
@login_required
def start_trial():
    from datetime import timedelta
    if current_user.trial_used or current_user.is_premium:
        return redirect(url_for('premium'))
    current_user.trial_used = True
    current_user.is_premium = True
    current_user.trial_ends = datetime.utcnow() + timedelta(days=7)
    db.session.commit()
    lang = current_user.language or 'ru'
    t = translations.get(lang, translations['ru'])
    return render_template('premium.html', t=t, lang=lang,
                           trial_available=False, trial_active=True, trial_success=True)

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
    init_db()  # Добавляем недостающие колонки если БД уже существует
    
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
