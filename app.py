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
        'pm_try_btn': 'Попробовать 7 дней бесплатно',
        'pm_monthly_note': 'затем 199 ₽/месяц',
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
        'premium_try': 'Попробовать 7 дней бесплатно',
        'premium_already_used': 'Пробный период уже использован',
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
        'pm_try_btn': 'Try 7 days free',
        'pm_monthly_note': 'then $2.99/month',
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
        'premium_try': 'Try 7 days free',
        'premium_already_used': 'Trial already used',
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
        'pm_try_btn': 'Спробувати 7 днів безкоштовно',
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
        'premium_try': 'Спробувати 7 днів безкоштовно',
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
        'pm_try_btn': '7 күн тегін байқап көру',
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
        'premium_try': '7 күн тегін байқап көру',
        'premium_already_used': 'Сынақ кезеңі қолданылды',
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
    protein_goal = current_user.protein_goal if current_user.is_authenticated else 150
    fat_goal = current_user.fat_goal if current_user.is_authenticated else 70
    carbs_goal = current_user.carbs_goal if current_user.is_authenticated else 250
    water_goal = current_user.water_goal if current_user.is_authenticated else 8
    is_premium = current_user.is_premium if current_user.is_authenticated else False
    progress_percent = min(100, int(total_cal / daily_goal * 100)) if daily_goal > 0 else 0

    # Считаем итоги по приёмам пищи
    meal_totals = {'breakfast': 0, 'lunch': 0, 'dinner': 0, 'snack': 0, 'other': 0}
    for e in today_entries:
        meal = e.meal_type if e.meal_type in meal_totals else 'other'
        meal_totals[meal] += e.calories

    return render_template('index.html', t=t, lang=lang,
                           today_entries=today_entries,
                           total_cal=round(total_cal),
                           total_protein=round(total_protein, 1),
                           total_fat=round(total_fat, 1),
                           total_carbs=round(total_carbs, 1),
                           daily_goal=daily_goal,
                           remaining=round(remaining),
                           progress_pct=progress_pct,
                           protein_goal=protein_goal,
                           fat_goal=fat_goal,
                           carbs_goal=carbs_goal,
                           water_goal=water_goal,
                           is_premium=is_premium,
                           progress_percent=progress_percent,
                           meal_totals=meal_totals,
                           category_keys=CATEGORY_KEYS,
                           now=datetime.utcnow())

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
    current_user.trial_ends = datetime.utcnow() + timedelta(days=7)
    current_user.is_premium = True
    db.session.commit()
    flash('🎉 Пробный период на 7 дней активирован!')
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
                           cat_labels=cat_labels)

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
        if duration == '7days':
            user.premium_ends = base + timedelta(days=7)
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

@app.route('/api/search')
def api_search():
    lang = session.get('language', 'ru')
    q = request.args.get('q', '').strip().lower()
    if not q:
        return jsonify([])

    name_col = {'ru': Food.name_ru, 'en': Food.name_en, 'uk': Food.name_uk, 'kk': Food.name_kk}.get(lang, Food.name_ru)
    foods = Food.query.filter(name_col.ilike(f'%{q}%')).limit(10).all()

    if len(foods) < 2:
        all_foods = Food.query.all()
        def similarity(a, b):
            a, b = a.lower(), b.lower()
            if a in b or b in a: return 0.9
            common = sum(1 for c in a if c in b)
            return common / max(len(a), len(b), 1)
        scored = [(similarity(q, get_food_name(f, lang)), f) for f in all_foods]
        scored = [(s, f) for s, f in scored if s > 0.4]
        scored.sort(reverse=True)
        foods = [f for _, f in scored[:10]]

    return jsonify([{
        'id': f.id,
        'name': get_food_name(f, lang),
        'calories': f.calories,
        'protein': f.protein,
        'fat': f.fat,
        'carbs': f.carbs,
        'category': f.category,
    } for f in foods])

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
            "amount": {"value": "199.00", "currency": "RUB"},
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

        if Food.query.count() == 0:
            try:
                from food_data import FOODS
                for f in FOODS:
                    db.session.add(Food(**f))
                db.session.commit()
                print(f"✅ Добавлено {len(FOODS)} продуктов")
            except Exception as e:
                print(f"⚠️ food_data import error: {e}")

init_db()

if __name__ == '__main__':
    app.run(debug=True)
