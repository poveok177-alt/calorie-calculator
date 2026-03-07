
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
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

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'mojasupertajnayastrokakotoruyaniktonevzlomaet123')
# НЕ используем filesystem сессии — на Railway диск эфемерный
# app.config['SESSION_TYPE'] = 'filesystem'

database_url = os.environ.get('DATABASE_URL', 'sqlite:///calories.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 280,
    'connect_args': {'connect_timeout': 10, 'sslmode': 'require'}
}

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
    is_superuser = db.Column(db.Boolean, default=False)
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
    premium_ends = db.Column(db.DateTime, nullable=True)
    email_reminders = db.Column(db.Boolean, default=True)

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

class WeightLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CustomFood(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    calories = db.Column(db.Float, nullable=False)
    protein = db.Column(db.Float, default=0)
    fat = db.Column(db.Float, default=0)
    carbs = db.Column(db.Float, default=0)
    category = db.Column(db.String(50), default='other')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
        'create_custom_food': '+ Создать свой продукт',
        'custom_food_name': 'Название продукта',
        'custom_food_saved': 'Продукт сохранён!',
        'my_foods': 'Мои продукты',
        'month_history': 'История за месяц',
        'weight_goal': 'Цель по весу',
        'current_weight': 'Текущий вес (кг)',
        'goal_weight': 'Цель (кг)',
        'height': 'Рост (см)',
        'save': 'Сохранить',
        'bju_counter': 'Счётчик БЖУ',
        'no_ads': 'Без рекламы',
        'premium_desc': 'Разблокируй все возможности для достижения твоих целей',
        'subscribe': 'Подписаться — 89 ₽/мес',
        'remove': 'Удалить',
        'kcal': 'ккал',
        'g': 'г',
        'back': 'Назад',
        'products_count': 'продуктов',
        'grams_label': 'Количество (граммов)',
        'confirm_add': 'Добавить',
        'added_to_diary': 'добавлен в дневник',
        'login_required': 'Войдите в аккаунт, чтобы добавлять продукты в дневник',
        'add_from_cat': '+ Добавить',
        'history_subtitle': 'Ваш прогресс и история питания',
        'streak_label': 'дней подряд',
        'streak_zero': 'Начните вести дневник!',
        'weekly_title': '📊 Неделя',
        'avg_cal_label': 'Среднее ккал',
        'days_on_goal_label': 'Дней в норме',
        'days_logged_label': 'Дней с записями',
        'weight_chart_title': '📈 График веса',
        'weight_placeholder': 'кг',
        'weight_save_btn': 'Записать',
        'weight_chart_premium': 'График веса доступен в Premium',
        'cal_history_title': '📅 История калорий',
        'click_day_hint': 'Нажмите на день — список продуктов',
        'daily_log': 'Дневник питания',
        'no_entries_yet': 'Нет записей. Начните вести дневник!',
        'no_foods_day': 'Нет записей',
        'foods_that_day': 'Продукты за этот день',
        'history_premium_msg': 'Полная история доступна в Premium',
        'pm_no_thanks': 'Нет, спасибо',
        'pm_try_btn': 'Попробовать 3 дня бесплатно',
        'pm_monthly_note': 'затем 89 ₽/месяц',
        'pm_history': '🔒 Полная история — это Premium',
        'pm_weight_chart': '📈 График динамики веса доступен в Premium',
        'pm_weekly': '📅 Месячные сводки — это Premium',
        'pm_generic': '👑 Весь потенциал приложения открыт в Premium',
        'water_goal': 'Цель по воде',
        'water_goal_label': 'Вода (стаканов/день)',
        'protein_goal_label': 'Белки (г/день)',
        'fat_goal_label': 'Жиры (г/день)',
        'carbs_goal_label': 'Углеводы (г/день)',
        'calc_auto': '⚡ Рассчитать автоматически',
        'calc_fill_all': 'Заполните все поля',
        'calc_done': 'Расчёт выполнен',
        'calc_bmr': 'Базовый обмен веществ',
        'calc_tdee': 'Дневная норма калорий',
        'calc_save': 'Нажмите Сохранить, чтобы применить',
        'calc_male': 'Мужчина',
        'calc_female': 'Женщина',
        'calc_activity_label': 'Активность',
        'formula_note': 'Расчёт по формуле Харриса-Бенедикта',
        'act_sedentary': 'Малоподвижный образ жизни',
        'act_light': 'Лёгкая активность (1-3 дня/нед)',
        'act_moderate': 'Умеренная (3-5 дней/нед)',
        'act_active': 'Высокая (6-7 дней/нед)',
        'act_very_active': 'Очень высокая (ежедневно)',
        'now': 'Сейчас',
        'goal': 'Цель',
        'to_goal_lose': 'Осталось сбросить {d} кг',
        'to_goal_gain': 'Осталось набрать {d} кг',
        'goal_reached': 'Цель достигнута 🎉',
        'your_norms': 'Ваши нормы',
        'select': 'Выберите',
        'gender_male': 'Мужской',
        'gender_female': 'Женский',
        'premium_title': '⭐ Premium',
        'premium_subtitle': 'Все функции без ограничений',
        'premium_feature_history': 'История за 30 дней',
        'premium_feature_chart': 'График веса',
        'premium_feature_reports': 'Недельные отчёты',
        'premium_feature_foods': 'Безлимит своих продуктов',
        'premium_feature_streak': 'Streak дней подряд',
        'premium_feature_ads': 'Без рекламы',
        'premium_active': 'Premium активен',
        'premium_activate_test': 'Активировать Premium (тест)',
        'premium_try': 'Попробовать 3 дня бесплатно',
        'premium_already_used': 'Пробный период уже использован',
        'supplements': 'Добавки 💊',
        'sports_nutrition': 'Спортпит 💪',
        'recent': 'Недавние',
        'favorites': 'Избранные',
        'eggs': '🥚 Яйца',
        'legumes': '🫘 Бобовые',
        'fastfood': '🍔 Фастфуд',
        'oils': '🫙 Масла',
        'sauces': '🥫 Соусы',
        'sports': '💪 Спортпит',
        'baby': '👶 Детское',
        'other': '🍽 Прочее',
        'all_categories': 'Все',
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
        'create_custom_food': '+ Create custom food',
        'custom_food_name': 'Food name',
        'custom_food_saved': 'Food saved!',
        'my_foods': 'My foods',
        'month_history': 'Monthly history',
        'weight_goal': 'Weight goal',
        'current_weight': 'Current weight (kg)',
        'goal_weight': 'Goal weight (kg)',
        'height': 'Height (cm)',
        'save': 'Save',
        'bju_counter': 'Macros counter',
        'no_ads': 'No ads',
        'premium_desc': 'Unlock all features to reach your goals',
        'subscribe': 'Subscribe — 89 ₽/мес',
        'remove': 'Remove',
        'kcal': 'kcal',
        'g': 'g',
        'back': 'Back',
        'products_count': 'products',
        'grams_label': 'Amount (grams)',
        'confirm_add': 'Add',
        'added_to_diary': 'added to diary',
        'login_required': 'Please log in to add foods to your diary',
        'add_from_cat': '+ Add',
        'history_subtitle': 'Your progress and food history',
        'streak_label': 'days in a row',
        'streak_zero': 'Start keeping a diary!',
        'weekly_title': '📊 This week',
        'avg_cal_label': 'Avg calories',
        'days_on_goal_label': 'Days on goal',
        'days_logged_label': 'Days logged',
        'weight_chart_title': '📈 Weight chart',
        'weight_placeholder': 'kg',
        'weight_save_btn': 'Log',
        'weight_chart_premium': 'Weight chart available in Premium',
        'cal_history_title': '📅 Calorie history',
        'click_day_hint': 'Tap a day to see foods',
        'daily_log': 'Food diary',
        'no_entries_yet': 'No entries yet. Start your diary!',
        'no_foods_day': 'No entries',
        'foods_that_day': 'Foods that day',
        'history_premium_msg': 'Full history available in Premium',
        'pm_no_thanks': 'No, thanks',
        'pm_try_btn': 'Try 3 days free',
        'pm_monthly_note': 'then 89 ₽/month',
        'pm_history': '🔒 Full history is a Premium feature',
        'pm_weight_chart': '📈 Weight chart is available in Premium',
        'pm_weekly': '📅 Monthly reports are Premium',
        'pm_generic': '👑 All app features unlocked with Premium',
        'water_goal': 'Water goal',
        'water_goal_label': 'Water (glasses/day)',
        'protein_goal_label': 'Protein (g/day)',
        'fat_goal_label': 'Fat (g/day)',
        'carbs_goal_label': 'Carbs (g/day)',
        'calc_auto': '⚡ Calculate automatically',
        'calc_fill_all': 'Fill in all fields',
        'calc_done': 'Calculation done',
        'calc_bmr': 'Basal metabolic rate',
        'calc_tdee': 'Daily calorie needs',
        'calc_save': 'Click Save to apply',
        'calc_male': 'Male',
        'calc_female': 'Female',
        'calc_activity_label': 'Activity',
        'formula_note': 'Harris-Benedict formula',
        'act_sedentary': 'Sedentary',
        'act_light': 'Light activity (1-3 days/wk)',
        'act_moderate': 'Moderate (3-5 days/wk)',
        'act_active': 'Active (6-7 days/wk)',
        'act_very_active': 'Very active (daily)',
        'now': 'Now',
        'goal': 'Goal',
        'to_goal_lose': '{d} kg left to lose',
        'to_goal_gain': '{d} kg left to gain',
        'goal_reached': 'Goal reached 🎉',
        'your_norms': 'Your norms',
        'select': 'Select',
        'gender_male': 'Male',
        'gender_female': 'Female',
        'premium_title': '⭐ Premium',
        'premium_subtitle': 'All features, no limits',
        'premium_feature_history': '30-day history',
        'premium_feature_chart': 'Weight chart',
        'premium_feature_reports': 'Weekly reports',
        'premium_feature_foods': 'Unlimited custom foods',
        'premium_feature_streak': 'Streak tracking',
        'premium_feature_ads': 'No ads',
        'premium_active': 'Premium active',
        'premium_activate_test': 'Activate Premium (test)',
        'premium_try': 'Try 3 days free',
        'premium_already_used': 'Trial already used',
        'supplements': 'Supplements 💊',
        'sports_nutrition': 'Sports nutrition 💪',
        'recent': 'Recent',
        'favorites': 'Favorites',
        'eggs': '🥚 Eggs',
        'legumes': '🫘 Legumes',
        'fastfood': '🍔 Fast food',
        'oils': '🫙 Oils',
        'sauces': '🥫 Sauces',
        'sports': '💪 Sports nutrition',
        'baby': '👶 Baby food',
        'other': '🍽 Other',
        'all_categories': 'All',
    },
    'uk': {
        'app_name': "КалоріМ'ята",
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
        'meat': "М'ясо 🥩",
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
        'consumed': "З'їдено",
        'remaining': 'Залишилось',
        'per_100g': 'на 100 г',
        'get_premium': 'Отримати Преміум',
        'premium_features': 'Преміум функції',
        'choose_language': 'Оберіть мову',
        'email': 'Email',
        'password': 'Пароль',
        'username': "Ім'я користувача",
        'no_account': 'Немає акаунту?',
        'have_account': 'Вже є акаунт?',
        'did_you_mean': 'Можливо ви мали на увазі:',
        'not_found': 'Нічого не знайдено',
        'create_custom_food': '+ Створити свій продукт',
        'custom_food_name': 'Назва продукту',
        'custom_food_saved': 'Продукт збережено!',
        'my_foods': 'Мої продукти',
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
        'supplements': 'Добавки 💊',
        'sports_nutrition': 'Спортхарч 💪',
        'recent': 'Недавні',
        'favorites': 'Вибрані',
        'back': 'Назад',
        'products_count': 'продуктів',
        'grams_label': 'Кількість (грамів)',
        'confirm_add': 'Додати',
        'added_to_diary': 'додано в щоденник',
        'login_required': 'Увійдіть, щоб додавати продукти',
        'add_from_cat': '+ Додати',
        'history_subtitle': 'Ваш прогрес та історія харчування',
        'streak_label': 'днів поспіль',
        'streak_zero': 'Почніть вести щоденник!',
        'weekly_title': '📊 Тиждень',
        'avg_cal_label': 'Середнє ккал',
        'days_on_goal_label': 'Днів у нормі',
        'days_logged_label': 'Днів із записами',
        'weight_chart_title': '📈 Графік ваги',
        'weight_placeholder': 'кг',
        'weight_save_btn': 'Записати',
        'weight_chart_premium': 'Графік ваги доступний у Premium',
        'cal_history_title': '📅 Історія калорій',
        'click_day_hint': 'Натисніть на день — список продуктів',
        'daily_log': 'Щоденник харчування',
        'no_entries_yet': 'Немає записів. Починайте!',
        'no_foods_day': 'Немає записів',
        'foods_that_day': 'Продукти за цей день',
        'history_premium_msg': 'Повна історія доступна в Premium',
        'pm_no_thanks': 'Ні, дякую',
        'pm_try_btn': 'Спробувати 3 дні безкоштовно',
        'pm_monthly_note': 'потім 79 ₴/місяць',
        'pm_history': '🔒 Повна історія — це Premium',
        'pm_weight_chart': '📈 Графік ваги доступний у Premium',
        'pm_weekly': '📅 Місячні зведення — це Premium',
        'pm_generic': '👑 Весь потенціал застосунку відкрито в Premium',
        'water_goal': 'Ціль по воді',
        'water_goal_label': 'Вода (склянок/день)',
        'protein_goal_label': 'Білки (г/день)',
        'fat_goal_label': 'Жири (г/день)',
        'carbs_goal_label': 'Вуглеводи (г/день)',
        'calc_auto': '⚡ Розрахувати автоматично',
        'calc_fill_all': 'Заповніть усі поля',
        'calc_done': 'Розрахунок виконано',
        'calc_bmr': 'Базовий обмін речовин',
        'calc_tdee': 'Денна норма калорій',
        'calc_save': 'Натисніть Зберегти, щоб застосувати',
        'calc_male': 'Чоловік',
        'calc_female': 'Жінка',
        'calc_activity_label': 'Активність',
        'formula_note': 'Розрахунок за формулою Харріса-Бенедикта',
        'act_sedentary': 'Малорухливий спосіб життя',
        'act_light': 'Легка активність',
        'act_moderate': 'Помірна активність',
        'act_active': 'Висока активність',
        'act_very_active': 'Дуже висока активність',
        'now': 'Зараз',
        'goal': 'Ціль',
        'to_goal_lose': 'Залишилось скинути {d} кг',
        'to_goal_gain': 'Залишилось набрати {d} кг',
        'goal_reached': 'Ціль досягнута 🎉',
        'your_norms': 'Ваші норми',
        'select': 'Оберіть',
        'gender_male': 'Чоловічий',
        'gender_female': 'Жіночий',
        'premium_title': '⭐ Premium',
        'premium_subtitle': 'Усі функції без обмежень',
        'premium_feature_history': 'Історія за 30 днів',
        'premium_feature_chart': 'Графік ваги',
        'premium_feature_reports': 'Тижневі звіти',
        'premium_feature_foods': 'Безліміт своїх продуктів',
        'premium_feature_streak': 'Streak днів поспіль',
        'premium_feature_ads': 'Без реклами',
        'premium_active': 'Premium активний',
        'premium_activate_test': 'Активувати Premium (тест)',
        'premium_try': 'Спробувати 3 дні безкоштовно',
        'premium_already_used': 'Пробний період вже використано',
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
        'create_custom_food': '+ Өз өнімді жасау',
        'custom_food_name': 'Өнім атауы',
        'custom_food_saved': 'Өнім сақталды!',
        'my_foods': 'Менің өнімдерім',
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
        'supplements': 'Қоспалар 💊',
        'sports_nutrition': 'Спорттық тамақтану 💪',
        'recent': 'Соңғы',
        'favorites': 'Таңдаулылар',
        'back': 'Артқа',
        'products_count': 'өнім',
        'grams_label': 'Мөлшері (грамм)',
        'confirm_add': 'Қосу',
        'added_to_diary': 'күнделікке қосылды',
        'login_required': 'Өнімдер қосу үшін кіріңіз',
        'add_from_cat': '+ Қосу',
        'history_subtitle': 'Сіздің прогресіңіз',
        'streak_label': 'күн қатарынан',
        'streak_zero': 'Күнделік жүргізуді бастаңыз!',
        'weekly_title': '📊 Апта',
        'avg_cal_label': 'Орта ккал',
        'days_on_goal_label': 'Норма күндері',
        'days_logged_label': 'Жазбалар бар күндер',
        'weight_chart_title': '📈 Салмақ графигі',
        'weight_placeholder': 'кг',
        'weight_save_btn': 'Жазу',
        'weight_chart_premium': 'Салмақ графигі Premium-да қол жетімді',
        'cal_history_title': '📅 Калория тарихы',
        'click_day_hint': 'Күнді басыңыз — өнімдер тізімі',
        'daily_log': 'Тамақтану күнделігі',
        'no_entries_yet': 'Жазба жоқ. Бастаңыз!',
        'no_foods_day': 'Жазба жоқ',
        'foods_that_day': 'Сол күнгі өнімдер',
        'history_premium_msg': 'Толық тарих Premium-да',
        'pm_no_thanks': 'Жоқ, рахмет',
        'pm_try_btn': '3 күн тегін байқап көру',
        'pm_monthly_note': 'содан кейін 799 ₸/ай',
        'pm_history': '🔒 Толық тарих — Premium',
        'pm_weight_chart': '📈 Салмақ графигі Premium-да',
        'pm_weekly': '📅 Айлық есептер — Premium',
        'pm_generic': '👑 Барлық мүмкіндіктер Premium-да',
        'water_goal': 'Су мақсаты',
        'water_goal_label': 'Су (стакан/күн)',
        'protein_goal_label': 'Ақуыз (г/күн)',
        'fat_goal_label': 'Май (г/күн)',
        'carbs_goal_label': 'Көмірсу (г/күн)',
        'calc_auto': '⚡ Автоматты есептеу',
        'calc_fill_all': 'Барлық өрістерді толтырыңыз',
        'calc_done': 'Есептеу аяқталды',
        'calc_bmr': 'Негізгі зат алмасу',
        'calc_tdee': 'Күнделікті калория нормасы',
        'calc_save': 'Сақтауды басыңыз',
        'calc_male': 'Еркек',
        'calc_female': 'Әйел',
        'calc_activity_label': 'Белсенділік',
        'formula_note': 'Харрис-Бенедикт формуласы',
        'act_sedentary': 'Отырықшы өмір салты',
        'act_light': 'Жеңіл белсенділік',
        'act_moderate': 'Орташа белсенділік',
        'act_active': 'Жоғары белсенділік',
        'act_very_active': 'Өте жоғары белсенділік',
        'now': 'Қазір',
        'goal': 'Мақсат',
        'to_goal_lose': '{d} кг азайту қалды',
        'to_goal_gain': '{d} кг жинау қалды',
        'goal_reached': 'Мақсатқа жетілді 🎉',
        'your_norms': 'Сіздің нормаларыңыз',
        'select': 'Таңдаңыз',
        'gender_male': 'Еркек',
        'gender_female': 'Әйел',
        'premium_title': '⭐ Premium',
        'premium_subtitle': 'Барлық мүмкіндіктер ашық',
        'premium_feature_history': '30 күн тарихы',
        'premium_feature_chart': 'Салмақ графигі',
        'premium_feature_reports': 'Апталық есептер',
        'premium_feature_foods': 'Шексіз жеке өнімдер',
        'premium_feature_streak': 'Streak қатарынан күндер',
        'premium_feature_ads': 'Жарнамасыз',
        'premium_active': 'Premium белсенді',
        'premium_activate_test': 'Premium-ды белсендіру (тест)',
        'premium_try': '3 күн тегін байқап көру',
        'premium_already_used': 'Сынақ кезеңі қолданылды',
    }
}

CATEGORY_KEYS = ['fruits', 'vegetables', 'meat', 'fish', 'dairy', 'grains', 'nuts', 'eggs', 'legumes', 'fastfood', 'sweets', 'drinks', 'oils', 'sauces', 'sports', 'supplements', 'baby', 'other']

def get_t():
    lang = session.get('language', 'ru')
    return TRANSLATIONS.get(lang, TRANSLATIONS['ru'])

def get_food_name(food, lang):
    if lang == 'en': return food.name_en
    if lang == 'uk': return food.name_uk or food.name_ru
    if lang == 'kk': return food.name_kk or food.name_ru
    return food.name_ru

# ===================== АВТОРАСЧЁТ =====================

def calculate_calories(weight, height, age, gender, activity):
    """Формула Харриса-Бенедикта"""
    if gender == 'male':
        bmr = 88.362 + (13.397 * weight) + (4.799 * height) - (5.677 * age)
    else:
        bmr = 447.593 + (9.247 * weight) + (3.098 * height) - (4.330 * age)

    multipliers = {
        'sedentary': 1.2,
        'light': 1.375,
        'moderate': 1.55,
        'active': 1.725,
        'very_active': 1.9
    }
    return int(bmr * multipliers.get(activity, 1.55))

# ===================== STREAK =====================

def calculate_streak(user_id):
    """Считаем streak — сколько дней подряд есть записи"""
    today = date.today()
    streak = 0
    check_date = today
    while True:
        has_entry = FoodEntry.query.filter_by(
            user_id=user_id, date=check_date
        ).first()
        if has_entry:
            streak += 1
            check_date = check_date - timedelta(days=1)
        else:
            break
    return streak

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

    remaining = max(0, daily_goal - total_cal)
    is_premium = current_user.is_premium if current_user.is_authenticated else False
    progress_percent = min(100, int(total_cal / daily_goal * 100)) if daily_goal > 0 else 0

    # Группируем записи по приёмам пищи
    meals = {'breakfast': [], 'lunch': [], 'dinner': [], 'snack': [], 'other': []}
    meal_totals = {'breakfast': 0, 'lunch': 0, 'dinner': 0, 'snack': 0, 'other': 0}
    for e in today_entries:
        meal = e.meal_type if e.meal_type in meals else 'other'
        meals[meal].append(e)
        meal_totals[meal] += e.calories

    return render_template('index.html', t=t, lang=lang,
                           today_entries=today_entries,
                           meals=meals,
                           meal_totals=meal_totals,
                           total_cal=round(total_cal),
                           total_protein=round(total_protein, 1),
                           total_fat=round(total_fat, 1),
                           total_carbs=round(total_carbs, 1),
                           daily_goal=daily_goal,
                           remaining=round(remaining),
                           progress_pct=progress_pct,
                           progress_percent=progress_percent,
                           is_premium=is_premium,
                           category_keys=CATEGORY_KEYS,
                           now=datetime.utcnow())
@app.route('/about')
def about():
    t = get_t()
    lang = session.get('language', 'ru')
    return render_template('about.html', t=t, lang=lang)

@app.route('/oferta')
def oferta():
    return render_template('oferta.html')

@app.route('/contacts')
def contacts():
    return render_template('contacts.html')

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
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=True)
            session['language'] = user.language
            session.modified = True
            return redirect(url_for('index'))
        else:
            flash('Неверный email или пароль')
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

@app.before_request
def check_trial():
    if current_user.is_authenticated and current_user.is_premium:
        if current_user.trial_ends and datetime.utcnow() > current_user.trial_ends:
            if not current_user.premium_ends:
                current_user.is_premium = False
                db.session.commit()

@app.route('/premium')
def premium():
    t = get_t()
    lang = session.get('language', 'ru')
    trial_available = False
    if current_user.is_authenticated and not current_user.trial_used:
        trial_available = True
    return render_template('premium.html', t=t, lang=lang, trial_available=trial_available, now=datetime.utcnow())

@app.route('/start-trial')
@login_required
def start_trial():
    if current_user.trial_used:
        flash(get_t().get('premium_already_used', 'Пробный период уже использован'))
        return redirect(url_for('premium'))
    current_user.trial_used = True
    current_user.trial_ends = datetime.utcnow() + timedelta(days=3)
    current_user.is_premium = True
    db.session.commit()
    flash('🎉 Пробный период на 3 дня активирован!')
    return redirect(url_for('index'))

@app.route('/history')
@login_required
def history():
    t = get_t()
    lang = session.get('language', 'ru')
    is_premium = current_user.is_premium

    today = date.today()
    thirty_days_ago = today - timedelta(days=30)

    entries = FoodEntry.query.filter(
        FoodEntry.user_id == current_user.id,
        FoodEntry.date >= thirty_days_ago
    ).order_by(FoodEntry.date.desc(), FoodEntry.created_at.desc()).all()

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

    streak = calculate_streak(current_user.id)
    now = datetime.utcnow()

    return render_template('history.html', t=t, lang=lang,
                           days=days,
                           is_premium=is_premium,
                           goal=current_user.daily_calorie_goal or 2000,
                           streak=streak,
                           current_user=current_user,
                           now=now)

@app.route('/goals', methods=['GET', 'POST'])
@login_required
def goals():
    t = get_t()
    lang = session.get('language', 'ru')

    last_weight = None
    wl = WeightLog.query.filter_by(user_id=current_user.id).order_by(WeightLog.date.desc()).first()
    if wl:
        last_weight = wl.weight

    if request.method == 'POST':
        try:
            w = float(request.form.get('current_weight') or 0)
            h = float(request.form.get('height') or 0)
            a = int(request.form.get('age') or 25)
            g = request.form.get('gender') or 'male'
            act = request.form.get('activity') or 'moderate'

            current_user.current_weight = w
            current_user.goal_weight = float(request.form.get('goal_weight') or 0)
            current_user.height = h
            current_user.age = a
            current_user.gender = g
            current_user.activity = act

            # Авторасчёт калорий
            if w and h and a:
                calories = calculate_calories(w, h, a, g, act)
                # Корректировка по цели
                goal_w = current_user.goal_weight
                if goal_w and goal_w < w:
                    calories -= 400
                elif goal_w and goal_w > w:
                    calories += 300
                calories = max(1200, calories)

                current_user.daily_calorie_goal = int(request.form.get('daily_calorie_goal') or calories)
                current_user.protein_goal = int(request.form.get('protein_goal') or int(w * 1.7))
                current_user.fat_goal = int(request.form.get('fat_goal') or int(w * 0.9))
                carbs_cal = (current_user.daily_calorie_goal - current_user.protein_goal * 4 - current_user.fat_goal * 9)
                current_user.carbs_goal = int(request.form.get('carbs_goal') or max(50, int(carbs_cal / 4)))
            else:
                current_user.daily_calorie_goal = int(request.form.get('daily_calorie_goal') or 2000)
                current_user.protein_goal = int(request.form.get('protein_goal') or 150)
                current_user.fat_goal = int(request.form.get('fat_goal') or 70)
                current_user.carbs_goal = int(request.form.get('carbs_goal') or 250)

            current_user.water_goal = int(request.form.get('water_goal') or 8)

            # Сохраняем вес в лог
            if w:
                existing = WeightLog.query.filter_by(user_id=current_user.id, date=date.today()).first()
                if existing:
                    existing.weight = w
                else:
                    db.session.add(WeightLog(user_id=current_user.id, weight=w))

            db.session.commit()
            flash('✅ Цели сохранены!')
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Ошибка: {str(e)}')

    return render_template('goals.html', t=t, lang=lang,
                           last_weight=last_weight,
                           current_user=current_user,
                           now=datetime.utcnow())

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

    cat_labels = {k: t.get(k, k) for k in CATEGORY_KEYS}

    return render_template('categories.html', t=t, lang=lang,
                           foods=foods_data, current_cat=cat,
                           category_keys=CATEGORY_KEYS,
                           cat_labels=cat_labels,
                           current_user=current_user)

# ===================== ADMIN =====================

@app.route('/admin')
@login_required
def admin():
    if not current_user.is_superuser:
        return redirect(url_for('index'))
    t = get_t()
    query = request.args.get('q', '')
    if query:
        users = User.query.filter(
            (User.email.ilike(f'%{query}%')) | (User.username.ilike(f'%{query}%'))
        ).all()
    else:
        users = User.query.order_by(User.created_at.desc()).all()
    now = datetime.utcnow()
    return render_template('admin.html', users=users, query=query, now=now, t=t)

@app.route('/admin/grant-premium', methods=['POST'])
@login_required
def admin_grant_premium():
    if not current_user.is_superuser:
        return redirect(url_for('index'))
    user_id = request.form.get('user_id')
    duration = request.form.get('duration', '1month')
    user = User.query.get(user_id)
    if user:
        user.is_premium = True
        now = datetime.utcnow()
        base = user.premium_ends if user.premium_ends and user.premium_ends > now else now
        if duration == '3days':
            user.premium_ends = base + timedelta(days=3)
        elif duration == '3months':
            user.premium_ends = base + timedelta(days=90)
        elif duration == 'forever':
            user.premium_ends = None
        else:
            user.premium_ends = base + timedelta(days=30)
        db.session.commit()
        flash(f'Premium выдан: {user.username}')
    return redirect(url_for('admin'))

@app.route('/admin/revoke-premium', methods=['POST'])
@login_required
def admin_revoke_premium():
    if not current_user.is_superuser:
        return redirect(url_for('index'))
    user_id = request.form.get('user_id')
    user = User.query.get(user_id)
    if user:
        user.is_premium = False
        user.premium_ends = None
        db.session.commit()
        flash(f'Premium отозван: {user.username}')
    return redirect(url_for('admin'))

# ===================== API =====================


@app.route('/api/custom-foods', methods=['GET', 'POST', 'DELETE'])
@login_required
def api_custom_foods():
    if request.method == 'GET':
        foods = CustomFood.query.filter_by(user_id=current_user.id).order_by(CustomFood.created_at.desc()).all()
        return jsonify([{
            'id': f'custom_{f.id}', 'name': f.name, 'calories': f.calories,
            'protein': f.protein, 'fat': f.fat, 'carbs': f.carbs,
            'category': f.category, 'is_custom': True
        } for f in foods])
    elif request.method == 'POST':
        data = request.get_json()
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'Название обязательно'}), 400
        try:
            cf = CustomFood(
                user_id=current_user.id, name=name,
                calories=float(data.get('calories', 0)),
                protein=float(data.get('protein', 0)),
                fat=float(data.get('fat', 0)),
                carbs=float(data.get('carbs', 0)),
                category=data.get('category', 'other')
            )
            db.session.add(cf)
            db.session.commit()
            return jsonify({'success': True, 'id': f'custom_{cf.id}', 'name': cf.name})
        except Exception as e:
            return jsonify({'error': str(e)}), 400
    elif request.method == 'DELETE':
        data = request.get_json()
        raw_id = str(data.get('id', '')).replace('custom_', '')
        cf = CustomFood.query.filter_by(id=int(raw_id), user_id=current_user.id).first()
        if cf:
            db.session.delete(cf)
            db.session.commit()
        return jsonify({'success': True})

@app.route('/api/search')
def api_search():
    lang = session.get('language', 'ru')
    q = request.args.get('q', '').strip()
    cat = request.args.get('cat', '').strip()
    limit = min(int(request.args.get('limit', 20)), 50)

    name_col = {'ru': Food.name_ru, 'en': Food.name_en, 'uk': Food.name_uk, 'kk': Food.name_kk}.get(lang, Food.name_ru)

    def food_to_dict(f):
        return {
            'id': f.id,
            'name': get_food_name(f, lang),
            'calories': round(f.calories, 1),
            'protein': round(f.protein, 1),
            'fat': round(f.fat, 1),
            'carbs': round(f.carbs, 1),
            'category': f.category,
        }

    # Фильтр по категории
    base_q = Food.query
    if cat:
        base_q = base_q.filter_by(category=cat)

    # Пустой запрос — популярные/категория
    if not q:
        foods = base_q.limit(limit).all()
        result = [food_to_dict(f) for f in foods]
        # Если БД пустая — подгружаем данные
        if not result:
            try:
                from food_data import FOODS
                for f_data in FOODS:
                    db.session.add(Food(**f_data))
                db.session.commit()
                foods = base_q.limit(limit).all()
                result = [food_to_dict(f) for f in foods]
            except Exception:
                pass
        return jsonify(result)

    # Ищем в локальной БД
    foods = base_q.filter(name_col.ilike(f'%{q}%')).limit(limit).all()
    result = [food_to_dict(f) for f in foods]

    # Если БД пустая — подгружаем данные и повторяем поиск
    if not result and Food.query.count() == 0:
        try:
            from food_data import FOODS
            for f_data in FOODS:
                db.session.add(Food(**f_data))
            db.session.commit()
            foods = base_q.filter(name_col.ilike(f'%{q}%')).limit(limit).all()
            result = [food_to_dict(f) for f in foods]
        except Exception:
            pass

    # Если мало — ищем в Open Food Facts
    if len(result) < 3 and not cat:
        try:
            import urllib.request, json as _json, urllib.parse

            # Словарь перевода ru/uk/kk → en для OFF
            RU_TO_EN = {
                'гречка': 'buckwheat', 'греча': 'buckwheat',
                'творог': 'cottage cheese', 'кефир': 'kefir',
                'ряженка': 'fermented baked milk', 'сметана': 'sour cream',
                'говядина': 'beef', 'свинина': 'pork', 'баранина': 'lamb',
                'курица': 'chicken', 'индейка': 'turkey',
                'семга': 'salmon', 'треска': 'cod', 'минтай': 'pollock',
                'селедка': 'herring', 'скумбрия': 'mackerel',
                'капуста': 'cabbage', 'морковь': 'carrot', 'свекла': 'beet',
                'огурец': 'cucumber', 'помидор': 'tomato', 'картофель': 'potato',
                'картошка': 'potato', 'лук': 'onion', 'чеснок': 'garlic',
                'яблоко': 'apple', 'груша': 'pear', 'слива': 'plum',
                'вишня': 'cherry', 'клубника': 'strawberry', 'банан': 'banana',
                'апельсин': 'orange', 'мандарин': 'tangerine', 'лимон': 'lemon',
                'виноград': 'grape', 'арбуз': 'watermelon', 'дыня': 'melon',
                'рис': 'rice', 'макароны': 'pasta', 'хлеб': 'bread',
                'овсянка': 'oatmeal', 'овес': 'oats', 'пшено': 'millet',
                'молоко': 'milk', 'сыр': 'cheese', 'масло': 'butter',
                'яйцо': 'egg', 'яйца': 'eggs',
                'сахар': 'sugar', 'соль': 'salt', 'мед': 'honey',
                'шоколад': 'chocolate', 'печенье': 'cookies', 'торт': 'cake',
                'кофе': 'coffee', 'чай': 'tea', 'сок': 'juice',
                'вода': 'water', 'молочко': 'milk',
                'горох': 'peas', 'фасоль': 'beans', 'чечевица': 'lentils', 'нут': 'chickpeas',
                'миндаль': 'almonds', 'грецкий орех': 'walnut', 'арахис': 'peanut',
                'семечки': 'sunflower seeds', 'тыквенные семечки': 'pumpkin seeds',
                'колбаса': 'sausage', 'сосиски': 'frankfurters', 'ветчина': 'ham',
                'пицца': 'pizza', 'бургер': 'burger', 'картофель фри': 'french fries',
            }

            q_search = q.lower().strip()
            # Если язык не английский — пробуем перевести (первое слово или всю фразу)
            if lang in ('ru', 'uk', 'kk'):
                translated = RU_TO_EN.get(q_search)
                if not translated:
                    # Пробуем перевести первое слово
                    first_word = q_search.split()[0]
                    translated = RU_TO_EN.get(first_word)
                q_search = translated if translated else q_search

            off_lang = {'ru': 'ru', 'en': 'en', 'uk': 'uk', 'kk': 'ru'}.get(lang, 'en')
            query_enc = urllib.parse.quote(q_search)
            url = (
                f"https://world.openfoodfacts.org/cgi/search.pl"
                f"?search_terms={query_enc}&search_simple=1&action=process"
                f"&json=1&page_size=25&fields=id,product_name,product_name_{off_lang},nutriments,categories_tags"
            )
            req = urllib.request.Request(url, headers={'User-Agent': 'CaloriMint/1.0'})
            with urllib.request.urlopen(req, timeout=4) as r:
                data = _json.loads(r.read())

            # Маппинг категорий OFF → наши
            OFF_CAT_MAP = {
                'en:fruits': 'fruits', 'en:vegetables': 'vegetables',
                'en:meats': 'meat', 'en:fish': 'fish', 'en:seafood': 'fish',
                'en:dairies': 'dairy', 'en:cheeses': 'dairy', 'en:milks': 'dairy',
                'en:cereals': 'grains', 'en:breads': 'grains', 'en:pastas': 'grains',
                'en:nuts': 'nuts', 'en:eggs': 'eggs', 'en:legumes': 'legumes',
                'en:sweets': 'sweets', 'en:chocolates': 'sweets', 'en:biscuits': 'sweets',
                'en:beverages': 'drinks', 'en:juices': 'drinks', 'en:coffees': 'drinks',
                'en:oils': 'oils', 'en:sauces': 'sauces',
                'en:fast-foods': 'fastfood', 'en:pizzas': 'fastfood',
            }

            def get_off_category(tags):
                if not tags:
                    return 'other'
                for tag in tags:
                    if tag in OFF_CAT_MAP:
                        return OFF_CAT_MAP[tag]
                return 'other'

            seen_names = {x['name'].lower() for x in result}
            for p in data.get('products', []):
                name = (p.get(f'product_name_{off_lang}') or p.get('product_name') or '').strip()
                if not name or name.lower() in seen_names:
                    continue
                nut = p.get('nutriments', {})
                cal = float(nut.get('energy-kcal_100g') or nut.get('energy_100g', 0) or 0)
                if cal <= 0 or cal > 1000: continue
                prot = round(float(nut.get('proteins_100g', 0) or 0), 1)
                fat  = round(float(nut.get('fat_100g', 0) or 0), 1)
                carb = round(float(nut.get('carbohydrates_100g', 0) or 0), 1)
                category = get_off_category(p.get('categories_tags', []))
                result.append({
                    'id': f'off_{p.get("id","x")}',
                    'name': name,
                    'calories': round(cal, 1), 'protein': prot, 'fat': fat, 'carbs': carb,
                    'category': category,
                })
                seen_names.add(name.lower())
                if len(result) >= limit: break
        except Exception as e:
            app.logger.warning(f'OpenFoodFacts search error: {e}')

    return jsonify(result[:limit])

@app.route('/api/recent')
@login_required
def api_recent():
    lang = session.get('language', 'ru')
    entries = FoodEntry.query.filter_by(user_id=current_user.id)\
        .order_by(FoodEntry.created_at.desc()).limit(50).all()
    seen = {}
    for e in entries:
        if e.food_id not in seen:
            food = Food.query.get(e.food_id)
            if food:
                seen[e.food_id] = {
                    'id': food.id,
                    'name': get_food_name(food, lang),
                    'calories': food.calories,
                    'protein': food.protein,
                    'fat': food.fat,
                    'carbs': food.carbs,
                }
        if len(seen) >= 10:
            break
    return jsonify(list(seen.values()))

@app.route('/api/favorites', methods=['GET', 'POST', 'DELETE'])
@login_required
def api_favorites():
    lang = session.get('language', 'ru')
    key = f'favorites_{current_user.id}'
    if request.method == 'GET':
        fav_ids = session.get(key, [])
        result = []
        for fid in fav_ids:
            food = Food.query.get(fid)
            if food:
                result.append({
                    'id': food.id,
                    'name': get_food_name(food, lang),
                    'calories': food.calories,
                    'protein': food.protein,
                    'fat': food.fat,
                    'carbs': food.carbs,
                })
        return jsonify(result)
    elif request.method == 'POST':
        data = request.get_json()
        fav_ids = session.get(key, [])
        food_id = data.get('food_id')
        if food_id not in fav_ids:
            fav_ids.append(food_id)
        session[key] = fav_ids
        session.modified = True
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        data = request.get_json()
        fav_ids = session.get(key, [])
        food_id = data.get('food_id')
        fav_ids = [f for f in fav_ids if f != food_id]
        session[key] = fav_ids
        session.modified = True
        return jsonify({'success': True})

@app.route('/api/add-entry', methods=['POST'])
@login_required
def api_add_entry():
    data = request.get_json()
    lang = session.get('language', 'ru')
    food_id = data.get('food_id', '')
    grams = float(data.get('grams', 100))
    ratio = grams / 100

    # Кастомный продукт пользователя
    if str(food_id).startswith('custom_'):
        raw_id = int(str(food_id).replace('custom_', ''))
        cf = CustomFood.query.filter_by(id=raw_id, user_id=current_user.id).first()
        if not cf:
            return jsonify({'error': 'Custom food not found'}), 404
        existing = Food.query.filter_by(name_ru=cf.name).first()
        if existing:
            food = existing
        else:
            food = Food(name_ru=cf.name, name_en=cf.name, name_uk=cf.name, name_kk=cf.name,
                        calories=cf.calories, protein=cf.protein, fat=cf.fat, carbs=cf.carbs,
                        category=cf.category)
            db.session.add(food)
            db.session.flush()
        calories, protein, fat, carbs, name = cf.calories, cf.protein, cf.fat, cf.carbs, cf.name

    # Продукт из Open Food Facts (id начинается с 'off_')
    elif str(food_id).startswith('off_'):
        name = data.get('name', 'Продукт')
        calories = float(data.get('calories', 0))
        protein  = float(data.get('protein', 0))
        fat      = float(data.get('fat', 0))
        carbs    = float(data.get('carbs', 0))
        # Сохраняем в локальную БД чтобы не терять
        existing = Food.query.filter_by(name_ru=name).first()
        if existing:
            food = existing
        else:
            food = Food(
                name_ru=name, name_en=name, name_uk=name, name_kk=name,
                calories=calories, protein=protein, fat=fat, carbs=carbs,
                category='other'
            )
            db.session.add(food)
            db.session.flush()
    else:
        food = Food.query.get(int(food_id))
        if not food:
            return jsonify({'error': 'Food not found'}), 404
        calories = food.calories
        protein  = food.protein
        fat      = food.fat
        carbs    = food.carbs
        name     = get_food_name(food, lang)

    entry = FoodEntry(
        user_id=current_user.id,
        food_id=food.id,
        food_name=name if str(food_id).startswith(('off_', 'custom_')) else get_food_name(food, lang),
        grams=grams,
        calories=round(calories * ratio, 1),
        protein=round(protein * ratio, 1),
        fat=round(fat * ratio, 1),
        carbs=round(carbs * ratio, 1),
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
    return jsonify({
        'calories': round(sum(e.calories for e in entries)),
        'protein': round(sum(e.protein for e in entries), 1),
        'fat': round(sum(e.fat for e in entries), 1),
        'carbs': round(sum(e.carbs for e in entries), 1),
    })

@app.route('/api/weight-log', methods=['GET', 'POST'])
@login_required
def api_weight_log():
    if request.method == 'POST':
        data = request.get_json()
        weight = float(data.get('weight', 0))
        if weight > 0:
            existing = WeightLog.query.filter_by(user_id=current_user.id, date=date.today()).first()
            if existing:
                existing.weight = weight
            else:
                db.session.add(WeightLog(user_id=current_user.id, weight=weight))
            current_user.current_weight = weight
            db.session.commit()
        return jsonify({'success': True})

    days = int(request.args.get('days', 30))
    since = date.today() - timedelta(days=days)
    logs = WeightLog.query.filter(
        WeightLog.user_id == current_user.id,
        WeightLog.date >= since
    ).order_by(WeightLog.date.asc()).all()
    return jsonify([{'date': str(l.date), 'weight': l.weight} for l in logs])

@app.route('/api/last-weight')
@login_required
def api_last_weight():
    log = WeightLog.query.filter_by(user_id=current_user.id).order_by(WeightLog.date.desc()).first()
    return jsonify({'weight': log.weight if log else None})

@app.route('/api/weekly-summary')
@login_required
def api_weekly_summary():
    since = date.today() - timedelta(days=7)
    entries = FoodEntry.query.filter(
        FoodEntry.user_id == current_user.id,
        FoodEntry.date >= since
    ).all()

    by_day = {}
    for e in entries:
        d = str(e.date)
        if d not in by_day:
            by_day[d] = {'cal': 0, 'protein': 0, 'fat': 0, 'carbs': 0}
        by_day[d]['cal'] += e.calories
        by_day[d]['protein'] += e.protein
        by_day[d]['fat'] += e.fat
        by_day[d]['carbs'] += e.carbs

    goal = current_user.daily_calorie_goal or 2000
    days_logged = len(by_day)
    days_on_goal = sum(1 for d in by_day.values() if d['cal'] <= goal * 1.05)
    avg_cal = round(sum(d['cal'] for d in by_day.values()) / max(days_logged, 1))
    avg_protein = round(sum(d['protein'] for d in by_day.values()) / max(days_logged, 1), 1)
    avg_fat = round(sum(d['fat'] for d in by_day.values()) / max(days_logged, 1), 1)
    avg_carbs = round(sum(d['carbs'] for d in by_day.values()) / max(days_logged, 1), 1)

    return jsonify({
        'avg_cal': avg_cal,
        'days_on_goal': days_on_goal,
        'days_logged': days_logged,
        'avg_protein': avg_protein,
        'avg_fat': avg_fat,
        'avg_carbs': avg_carbs,
    })

@app.route('/api/history-data')
@login_required
def api_history_data():
    days_count = int(request.args.get('days', 30))
    since = date.today() - timedelta(days=days_count)
    entries = FoodEntry.query.filter(
        FoodEntry.user_id == current_user.id,
        FoodEntry.date >= since
    ).all()

    by_day = {}
    for e in entries:
        d = str(e.date)
        if d not in by_day:
            by_day[d] = {'calories': 0, 'foods': []}
        by_day[d]['calories'] += e.calories
        by_day[d]['foods'].append({
            'name': e.food_name,
            'grams': e.grams,
            'calories': e.calories,
            'meal': e.meal_type
        })

    return jsonify({'days': by_day, 'goal': current_user.daily_calorie_goal or 2000})

@app.route('/api/create-payment', methods=['POST'])
@login_required
def create_payment():
    if Payment is None:
        return jsonify({'success': False, 'error': 'Payment not configured'}), 500
    try:
        payment = Payment.create({
            "amount": {"value": "89.00", "currency": "RUB"},
            "confirmation": {
                "type": "redirect",
                "return_url": request.host_url.rstrip('/') + '/premium-success'
            },
            "description": f"Премиум подписка для {current_user.username}",
            "metadata": {"user_id": current_user.id, "email": current_user.email}
        })
        return jsonify({'success': True, 'confirmation_url': payment.confirmation.confirmation_url})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/premium-success')
@login_required
def premium_success():
    flash('Если оплата прошла успешно — премиум активируется автоматически.')
    return redirect('/')

@app.route('/webhook/yookassa', methods=['POST'])
def yookassa_webhook():
    try:
        data = request.json
        if data.get('event') == 'payment.succeeded':
            user_id = data.get('object', {}).get('metadata', {}).get('user_id')
            if user_id:
                user = User.query.get(user_id)
                if user:
                    user.is_premium = True
                    user.premium_ends = datetime.utcnow() + timedelta(days=30)
                    db.session.commit()
        return jsonify({'status': 'ok'}), 200
    except Exception:
        return jsonify({'status': 'error'}), 400

# ===================== ЗАПУСК =====================

def init_db():
    with app.app_context():
        db.create_all()

        # Добавляем колонки если их нет (для старых БД)
        try:
            inspector = db.inspect(db.engine)
            user_cols = [c['name'] for c in inspector.get_columns('user')]
            with db.engine.connect() as conn:
                if 'is_superuser' not in user_cols:
                    conn.execute(db.text('ALTER TABLE "user" ADD COLUMN is_superuser BOOLEAN DEFAULT FALSE'))
                    conn.commit()
                if 'premium_ends' not in user_cols:
                    conn.execute(db.text('ALTER TABLE "user" ADD COLUMN premium_ends DATETIME'))
                    conn.commit()
        except Exception as e:
            print(f"Migration note: {e}")

        food_count = Food.query.count()
        if food_count < 10:
            try:
                from food_data import FOODS
                if food_count > 0:
                    Food.query.delete()
                    db.session.commit()
                for f in FOODS:
                    db.session.add(Food(**f))
                db.session.commit()
                print(f"✅ Добавлено {len(FOODS)} продуктов")
            except Exception as e:
                print(f"⚠️ food_data import error: {e}")
                # Добавляем базовые продукты если food_data не загрузился
                fallback = [
                    {"name_ru":"Яблоко","name_en":"Apple","name_uk":"Яблуко","name_kk":"Алма","calories":52,"protein":0.3,"fat":0.2,"carbs":14.0,"category":"fruits"},
                    {"name_ru":"Банан","name_en":"Banana","name_uk":"Банан","name_kk":"Банан","calories":89,"protein":1.1,"fat":0.3,"carbs":22.8,"category":"fruits"},
                    {"name_ru":"Куриная грудка","name_en":"Chicken breast","name_uk":"Куряча грудка","name_kk":"Тауық еті","calories":165,"protein":31.0,"fat":3.6,"carbs":0.0,"category":"meat"},
                    {"name_ru":"Говядина","name_en":"Beef","name_uk":"Яловичина","name_kk":"Сиыр еті","calories":187,"protein":18.9,"fat":12.4,"carbs":0.0,"category":"meat"},
                    {"name_ru":"Молоко","name_en":"Milk","name_uk":"Молоко","name_kk":"Сүт","calories":52,"protein":2.8,"fat":2.5,"carbs":4.7,"category":"dairy"},
                    {"name_ru":"Творог","name_en":"Cottage cheese","name_uk":"Сир","name_kk":"Ірімшік","calories":121,"protein":17.0,"fat":5.0,"carbs":3.0,"category":"dairy"},
                    {"name_ru":"Рис","name_en":"Rice","name_uk":"Рис","name_kk":"Күріш","calories":344,"protein":7.0,"fat":0.6,"carbs":78.9,"category":"grains"},
                    {"name_ru":"Гречка","name_en":"Buckwheat","name_uk":"Гречка","name_kk":"Қарақұмық","calories":308,"protein":12.6,"fat":3.3,"carbs":57.1,"category":"grains"},
                    {"name_ru":"Морковь","name_en":"Carrot","name_uk":"Морква","name_kk":"Сәбіз","calories":41,"protein":0.9,"fat":0.2,"carbs":9.6,"category":"vegetables"},
                    {"name_ru":"Помидор","name_en":"Tomato","name_uk":"Помідор","name_kk":"Қызанақ","calories":18,"protein":0.9,"fat":0.2,"carbs":3.8,"category":"vegetables"},
                    {"name_ru":"Яйцо куриное","name_en":"Chicken egg","name_uk":"Куряче яйце","name_kk":"Тауық жұмыртқасы","calories":155,"protein":12.7,"fat":10.9,"carbs":0.7,"category":"eggs"},
                    {"name_ru":"Семга","name_en":"Salmon","name_uk":"Лосось","name_kk":"Лосось","calories":208,"protein":20.0,"fat":13.0,"carbs":0.0,"category":"fish"},
                ]
                for f in fallback:
                    db.session.add(Food(**f))
                db.session.commit()
                print(f"✅ Добавлено {len(fallback)} базовых продуктов")

try:
    init_db()
except Exception as e:
    print(f"init_db error: {e}", flush=True)
"""
API эндпоинты для импорта продуктов через HTTP
Добавить в app.py или импортировать как blueprintнь

Использование:
    POST /api/import/start - начать импорт
    GET  /api/import/status - статус импорта
    POST /api/import/cancel - отменить импорт
"""

from flask import request, jsonify, session
from flask_login import login_required, current_user
import csv
import os
import threading
from datetime import datetime
from pathlib import Path

# ===================== ИМПОРТ ПРОДУКТОВ ЧЕРЕЗ API =====================

# Глобальное состояние импорта
IMPORT_STATE = {
    'status': 'idle',  # idle, uploading, importing, completed, error
    'total_lines': 0,
    'processed': 0,
    'added': 0,
    'skipped': 0,
    'errors': 0,
    'current_file': '',
    'progress_percent': 0,
    'message': '',
    'error_message': '',
    'start_time': None,
    'eta_seconds': None,
}

CATEGORY_MAP = {
    'fruits-vegetables': 'vegetables',
    'fruit': 'fruits',
    'vegetables': 'vegetables',
    'meat': 'meat',
    'fish': 'fish',
    'seafood': 'fish',
    'poultry': 'meat',
    'dairy': 'dairy',
    'milk': 'dairy',
    'cheese': 'dairy',
    'yogurt': 'dairy',
    'cereals': 'grains',
    'grains': 'grains',
    'bread': 'grains',
    'pasta': 'grains',
    'rice': 'grains',
    'nuts': 'nuts',
    'seeds': 'nuts',
    'eggs': 'eggs',
    'legumes': 'legumes',
    'beans': 'legumes',
    'lentils': 'legumes',
    'snacks': 'sweets',
    'confectionery': 'sweets',
    'desserts': 'sweets',
    'chocolate': 'sweets',
    'candy': 'sweets',
    'sweetened-beverages': 'drinks',
    'beverages': 'drinks',
    'soft-drinks': 'drinks',
    'juices': 'drinks',
    'coffee': 'drinks',
    'tea': 'drinks',
    'water': 'drinks',
    'oils': 'oils',
    'spreads': 'oils',
    'butter': 'oils',
    'sauces': 'sauces',
    'condiments': 'sauces',
    'prepared-meals': 'fastfood',
    'fast-food': 'fastfood',
    'soups': 'fastfood',
}

def get_category(off_categories):
    """Определить категорию"""
    if not off_categories:
        return 'other'
    
    tags = str(off_categories).lower().split(',')
    for tag in tags:
        tag = tag.strip()
        if tag in CATEGORY_MAP:
            return CATEGORY_MAP[tag]
    
    return 'other'

def parse_nutrition(row):
    """Парсить макронутриенты"""
    try:
        energy = float(row.get('energy-kcal_100g', 0) or 0)
    except (ValueError, TypeError):
        energy = 0
    
    try:
        protein = float(row.get('proteins_100g', 0) or 0)
    except (ValueError, TypeError):
        protein = 0
    
    try:
        fat = float(row.get('fat_100g', 0) or 0)
    except (ValueError, TypeError):
        fat = 0
    
    try:
        carbs = float(row.get('carbohydrates_100g', 0) or 0)
    except (ValueError, TypeError):
        carbs = 0
    
    # Конвертируем джоули в ккал
    if energy > 500:
        energy = energy / 4.184
    
    return round(energy, 1), round(protein, 1), round(fat, 1), round(carbs, 1)

def import_worker(filepath, batch_size=10000, limit=None):
    """Рабочая функция импорта в отдельном потоке"""
    try:
        IMPORT_STATE['status'] = 'importing'
        IMPORT_STATE['current_file'] = Path(filepath).name
        IMPORT_STATE['start_time'] = datetime.utcnow()
        
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f, delimiter='\t')
            lines = sum(1 for _ in open(filepath, encoding='utf-8', errors='ignore'))
            IMPORT_STATE['total_lines'] = lines
            
            batch = []
            
            for row_num, row in enumerate(reader, 1):
                # Лимит
                if limit and IMPORT_STATE['added'] >= limit:
                    break
                
                # Имя
                name = row.get('product_name', '').strip()
                if not name or len(name) < 2:
                    IMPORT_STATE['skipped'] += 1
                    continue
                
                # Проверка дубликата
                existing = Food.query.filter_by(name_ru=name).first()
                if existing:
                    IMPORT_STATE['skipped'] += 1
                    continue
                
                # Питание
                calories, protein, fat, carbs = parse_nutrition(row)
                if calories <= 0:
                    IMPORT_STATE['skipped'] += 1
                    continue
                
                # Категория
                category = get_category(row.get('categories', ''))
                
                # Создать продукт
                food = Food(
                    name_ru=name[:200],
                    name_en=name[:200],
                    name_uk=name[:200],
                    name_kk=name[:200],
                    calories=calories,
                    protein=protein,
                    fat=fat,
                    carbs=carbs,
                    category=category
                )
                
                batch.append(food)
                IMPORT_STATE['added'] += 1
                
                # Batch insert
                if len(batch) >= batch_size:
                    db.session.add_all(batch)
                    db.session.commit()
                    batch = []
                
                # Прогресс
                IMPORT_STATE['processed'] = row_num
                IMPORT_STATE['progress_percent'] = int((row_num / lines) * 100)
                
                # ETA
                elapsed = (datetime.utcnow() - IMPORT_STATE['start_time']).total_seconds()
                if elapsed > 0 and row_num > 0:
                    rate = row_num / elapsed
                    remaining = lines - row_num
                    IMPORT_STATE['eta_seconds'] = int(remaining / rate) if rate > 0 else 0
        
        # Вставить оставшиеся
        if batch:
            db.session.add_all(batch)
            db.session.commit()
        
        IMPORT_STATE['status'] = 'completed'
        IMPORT_STATE['message'] = f'✅ Импортировано {IMPORT_STATE["added"]} продуктов'
        
    except Exception as e:
        IMPORT_STATE['status'] = 'error'
        IMPORT_STATE['error_message'] = str(e)

@app.route('/api/import/upload', methods=['POST'])
@login_required
def api_import_upload():
    """Загрузить CSV файл для импорта"""
    
    # Только админ
    if not current_user.is_superuser:
        return jsonify({'error': 'Access denied'}), 403
    
    # Проверить файл
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'Only CSV files allowed'}), 400
    
    try:
        # Сохранить временный файл
        temp_dir = Path('/tmp/calori_import')
        temp_dir.mkdir(exist_ok=True)
        
        filepath = temp_dir / file.filename
        file.save(str(filepath))
        
        # Проверить размер
        size_mb = filepath.stat().st_size / 1e6
        if size_mb > 2000:  # 2GB макс
            filepath.unlink()
            return jsonify({'error': f'File too large: {size_mb:.1f}MB (max 2000MB)'}), 413
        
        # Начать импорт в отдельном потоке
        batch_size = request.json.get('batch_size', 10000) if request.is_json else 10000
        limit = request.json.get('limit', None) if request.is_json else None
        
        thread = threading.Thread(
            target=import_worker,
            args=(str(filepath), batch_size, limit),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Import started',
            'file': file.filename,
            'size_mb': size_mb
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/import/start', methods=['POST'])
@login_required
def api_import_start():
    """Запустить импорт из URL"""
    
    if not current_user.is_superuser:
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    url = data.get('url', '')
    
    if not url or not url.startswith('http'):
        return jsonify({'error': 'Invalid URL'}), 400
    
    try:
        # Скачать файл
        import urllib.request
        temp_dir = Path('/tmp/calori_import')
        temp_dir.mkdir(exist_ok=True)
        
        filename = url.split('/')[-1]
        filepath = temp_dir / filename
        
        IMPORT_STATE['status'] = 'uploading'
        IMPORT_STATE['message'] = f'⬇️ Скачивание {filename}...'
        
        # Простой способ скачивания (без проверки размера во время)
        urllib.request.urlretrieve(url, str(filepath))
        
        # Начать импорт
        batch_size = data.get('batch_size', 10000)
        limit = data.get('limit', None)
        
        thread = threading.Thread(
            target=import_worker,
            args=(str(filepath), batch_size, limit),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Import started',
            'file': filename
        })
    
    except Exception as e:
        IMPORT_STATE['status'] = 'error'
        IMPORT_STATE['error_message'] = str(e)
        return jsonify({'error': str(e)}), 500

@app.route('/api/import/status', methods=['GET'])
@login_required
def api_import_status():
    """Получить статус импорта"""
    
    if not current_user.is_superuser:
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify({
        'status': IMPORT_STATE['status'],
        'progress_percent': IMPORT_STATE['progress_percent'],
        'processed': IMPORT_STATE['processed'],
        'added': IMPORT_STATE['added'],
        'skipped': IMPORT_STATE['skipped'],
        'total_lines': IMPORT_STATE['total_lines'],
        'current_file': IMPORT_STATE['current_file'],
        'message': IMPORT_STATE['message'],
        'error': IMPORT_STATE['error_message'],
        'eta_seconds': IMPORT_STATE['eta_seconds'],
        'start_time': IMPORT_STATE['start_time'].isoformat() if IMPORT_STATE['start_time'] else None,
    })

@app.route('/api/import/cancel', methods=['POST'])
@login_required
def api_import_cancel():
    """Отменить импорт"""
    
    if not current_user.is_superuser:
        return jsonify({'error': 'Access denied'}), 403
    
    IMPORT_STATE['status'] = 'cancelled'
    IMPORT_STATE['message'] = 'Import cancelled by user'
    
    return jsonify({'success': True, 'message': 'Import cancelled'})

@app.route('/api/import/reset', methods=['POST'])
@login_required
def api_import_reset():
    """Сбросить состояние"""
    
    if not current_user.is_superuser:
        return jsonify({'error': 'Access denied'}), 403
    
    IMPORT_STATE.update({
        'status': 'idle',
        'total_lines': 0,
        'processed': 0,
        'added': 0,
        'skipped': 0,
        'errors': 0,
        'current_file': '',
        'progress_percent': 0,
        'message': '',
        'error_message': '',
        'start_time': None,
        'eta_seconds': None,
    })
    
    return jsonify({'success': True})

@app.route('/api/import/quick-sample', methods=['POST'])
@login_required
def api_import_quick_sample():
    """Быстрая загрузка 27 популярных продуктов"""
    
    if not current_user.is_superuser:
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        sample_products = [
            ('Яблоко', 'Apple', 52, 0.3, 0.2, 14, 'fruits'),
            ('Банан', 'Banana', 89, 1.1, 0.3, 23, 'fruits'),
            ('Апельсин', 'Orange', 43, 0.9, 0.2, 8.1, 'fruits'),
            ('Морковь', 'Carrot', 41, 0.9, 0.2, 10, 'vegetables'),
            ('Помидор', 'Tomato', 18, 0.9, 0.2, 3.9, 'vegetables'),
            ('Огурец', 'Cucumber', 15, 0.7, 0.1, 2.8, 'vegetables'),
            ('Брокколи', 'Broccoli', 34, 2.8, 0.4, 7, 'vegetables'),
            ('Куриное филе', 'Chicken breast', 165, 31, 3.6, 0, 'meat'),
            ('Говядина', 'Beef', 250, 26, 17, 0, 'meat'),
            ('Лосось', 'Salmon', 208, 20, 13, 0, 'fish'),
            ('Молоко 3.2%', 'Milk 3.2%', 61, 3.2, 3.3, 4.8, 'dairy'),
            ('Йогурт', 'Yogurt', 59, 3.5, 0.4, 4.7, 'dairy'),
            ('Сыр', 'Cheese', 356, 25, 27.4, 2.2, 'dairy'),
            ('Гречка', 'Buckwheat', 335, 13, 3.4, 72, 'grains'),
            ('Рис белый', 'White rice', 130, 2.7, 0.3, 28, 'grains'),
            ('Хлеб пшеничный', 'Wheat bread', 265, 7.5, 3.2, 49, 'grains'),
            ('Яйцо куриное', 'Chicken egg', 155, 13, 11, 0.7, 'eggs'),
            ('Чечевица', 'Lentils', 225, 25, 0.4, 40, 'legumes'),
            ('Нут', 'Chickpeas', 364, 19, 6, 61, 'legumes'),
            ('Миндаль', 'Almonds', 579, 21, 50, 22, 'nuts'),
            ('Грецкие орехи', 'Walnuts', 654, 15, 65, 14, 'nuts'),
            ('Оливковое масло', 'Olive oil', 884, 0, 100, 0, 'oils'),
            ('Помидорный соус', 'Tomato sauce', 18, 0.9, 0.2, 3.5, 'sauces'),
            ('Кока-кола', 'Coca-cola', 42, 0, 0, 11, 'drinks'),
            ('Кофе', 'Coffee', 2, 0.1, 0, 0, 'drinks'),
            ('Конфеты', 'Candies', 387, 0, 5, 96, 'sweets'),
            ('Шоколад чёрный', 'Dark chocolate', 546, 5.3, 31, 61, 'sweets'),
            ('Пицца', 'Pizza', 290, 12, 9, 38, 'fastfood'),
        ]
        
        added = 0
        for name_ru, name_en, cal, prot, fat, carbs, cat in sample_products:
            if not Food.query.filter_by(name_ru=name_ru).first():
                f = Food(
                    name_ru=name_ru,
                    name_en=name_en,
                    name_uk=name_ru,
                    name_kk=name_ru,
                    calories=cal,
                    protein=prot,
                    fat=fat,
                    carbs=carbs,
                    category=cat
                )
                db.session.add(f)
                added += 1
        
        db.session.commit()
        total = Food.query.count()
        
        return jsonify({
            'success': True,
            'added': added,
            'total_in_db': total,
            'message': f'✅ Добавлено {added} продуктов, всего в БД: {total}'
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
@app.route('/make-me-super')
@login_required
def make_me_super():
    current_user.is_superuser = True
    db.session.commit()
    return 'Готово — ты суперюзер'
@app.route('/admin/clean-dupes')
@login_required
def admin_clean_dupes():
    if not current_user.is_superuser:
        return 'Access denied', 403
    import re
    deleted = 0
    foods = Food.query.all()
    for f in foods:
        if re.search(r' \d+$', f.name_ru):
            db.session.delete(f)
            deleted += 1
    db.session.commit()
    return f'Удалено {deleted} дублей'

@app.route('/admin/import')
@login_required
def admin_import():
    if not current_user.is_superuser:
        return redirect(url_for('index'))
    return render_template('import_admin.html')
if __name__ == '__main__':
    app.run(debug=True)
#