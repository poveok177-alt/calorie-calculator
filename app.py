from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
import json
import os
import uuid
import hashlib
from dotenv import load_dotenv

load_dotenv()

# ===== YooKassa (without crashing server) =====
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
    """Add missing columns to existing DB (migration without alembic)."""
    with app.app_context():
        try:
            inspector = db.inspect(db.engine)
            if 'user' not in inspector.get_table_names():
                return

            user_columns = [col['name'] for col in inspector.get_columns('user')]

            new_columns = [
                ('favorites',          "TEXT DEFAULT '[]'"),
                ('trial_used',         'BOOLEAN DEFAULT FALSE'),
                ('trial_ends',         'TIMESTAMP'),
                ('email_reminders',    'BOOLEAN DEFAULT TRUE'),
                ('is_premium',         'BOOLEAN DEFAULT FALSE'),
                ('is_superuser',       'BOOLEAN DEFAULT FALSE'),
                ('premium_ends',       'TIMESTAMP'),
                ('current_weight',     'FLOAT'),
                ('goal_weight',        'FLOAT'),
                ('height',             'FLOAT'),
                ('daily_calorie_goal', 'INTEGER DEFAULT 2000'),
                ('water_goal',         'INTEGER DEFAULT 8'),
                ('protein_goal',       'INTEGER DEFAULT 150'),
                ('fat_goal',           'INTEGER DEFAULT 70'),
                ('carbs_goal',         'INTEGER DEFAULT 250'),
                ('age',                'INTEGER DEFAULT 25'),
                ('gender',             "VARCHAR(10) DEFAULT 'male'"),
                ('activity',           "VARCHAR(20) DEFAULT 'moderate'"),
                ('language',           "VARCHAR(10) DEFAULT 'ru'"),
            ]

            with db.engine.connect() as conn:
                for col_name, col_def in new_columns:
                    if col_name not in user_columns:
                        try:
                            conn.execute(db.text(
                                f'ALTER TABLE "user" ADD COLUMN {col_name} {col_def}'
                            ))
                            conn.commit()
                            print(f'[init_db] Added column: {col_name}')
                        except Exception as e:
                            conn.rollback()
                            print(f'[init_db] Skip {col_name}: {e}')
        except Exception as e:
            print(f'[init_db] Error: {e}')

# ===================== TRANSLATIONS =====================

translations = {
    'ru': {
        'app_name': 'CaloriMint', 'home': 'Главная', 'history': 'История',
        'goals': 'Цели', 'categories': 'Категории', 'premium': 'Премиум',
        'login': 'Вход', 'register': 'Регистрация', 'logout': 'Выход',
        'profile': 'Профиль', 'today': 'Сегодня', 'back': 'Назад',
        'search': 'Поиск продуктов...', 'search_placeholder': '🔍 Поиск продукта...',
        'add': 'Добавить', 'delete': 'Удалить', 'save': 'Сохранить',
        'calories': 'Калории', 'protein': 'Белки', 'fat': 'Жиры', 'carbs': 'Углеводы',
        'kcal': 'ккал', 'g': 'г', 'grams': 'г', 'ml': 'мл',
        'per100g': 'на 100 г', 'per100ml': 'на 100 мл',
        'breakfast': 'Завтрак', 'lunch': 'Обед', 'dinner': 'Ужин', 'snack': 'Перекус',
        'clear': 'Очистить', 'clear_meal_confirm': 'Очистить',
        'clear_day': '🗑 Очистить всё за сегодня',
        'clear_day_confirm': 'Удалить ВСЕ продукты за сегодня?',
        'delete_entry_confirm': 'Удалить продукт?',
        'all': 'Все',
        'today_title': '🎯 Сегодня', 'of': 'из',
        'water': '💧 Вода', 'cups': 'стак.',
        'weight_label': 'Вес:', 'volume_label': 'Объём:',
        'total': 'Итого', 'cancel': 'Отмена', 'confirm_add': '✓ Добавить',
        'quick_loading': '⏳ Загрузка...', 'not_found': 'Ничего не найдено 🤷',
        'load_error': '❌ Ошибка загрузки',
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
        'products_count': 'продуктов · сортировка по алфавиту',
        'add_from_cat': '+ Добавить',
        'grams_label': 'Количество (граммов)',
        'login_required': 'Войдите в аккаунт, чтобы добавлять продукты',
        'added_to_diary': 'добавлен в дневник!',
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
        'food_search_desc': '100+ продуктов + 3 млн в Open Food Facts',
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
        'calc_fill_all': 'Заполни все поля: вес, рост, возраст, пол и активность!',
        'calc_done': 'Расчёт завершён!',
        'calc_bmr': 'Метаболизм (BMR)',
        'calc_tdee': 'Дневная норма (TDEE)',
        'calc_save': 'Не забудь нажать "Сохранить"!',
        'calc_profile': 'Профиль',
        'calc_activity_label': 'Активность',
        'calc_male': 'мужчина', 'calc_female': 'женщина',
        'pm_history': '🔒 Полная история — это Premium',
        'pm_weight_chart': '📈 График динамики веса доступен в Premium',
        'pm_weekly': '📅 Месячные сводки — это Premium',
        'pm_custom_limit': '⭐️ Безлимитные свои продукты доступны в Premium',
        'pm_export': '📤 Экспорт данных доступен в Premium',
        'pm_meals': '🥗 Разбивка по приёмам пищи доступна в Premium',
        'pm_macros': '💪 Серьёзный инструмент для серьёзного подхода. Premium',
        'pm_generic': '👑 Весь потенциал приложения открыт в Premium',
        'pm_data': '🌿 Больше данных — лучше результат. Premium',
        'pm_no_thanks': 'Нет, спасибо',
        'pm_try_btn': 'Попробовать — 11 ₽ / неделя',
        'pm_monthly_note': 'или 129 ₽ / месяц',
        'pm_profile_section': '⭐ Premium возможности',
        'pm_profile_desc': 'Разблокируйте всё — история за всё время, графики, экспорт, безлимитные продукты.',
        'pm_profile_btn': 'Подключить Premium',
        'pm_active_until': 'Premium активен до',
        'pm_active_forever': 'Premium активен навсегда',
        'streak_label': '🔥 дней подряд', 'streak_zero': 'Начните вести дневник!',
        'weight_chart_title': '📈 График веса', 'weight_log_today': 'Внести вес сегодня',
        'weight_placeholder': 'кг', 'weight_save_btn': 'Записать',
        'weekly_title': '📊 Неделя', 'avg_cal_label': 'Среднее ккал',
        'days_on_goal_label': 'Дней в норме', 'days_logged_label': 'Дней с записями',
        'cal_history_title': '📅 История калорий', 'click_day_hint': 'Нажмите на день — список продуктов',
        'history_premium_msg': 'Полная история доступна в Premium',
        'foods_that_day': 'Продукты за этот день', 'no_foods_day': 'Нет записей',
        'weight_chart_premium': '📈 График веса доступен в Premium',
        'tab_search': 'Поиск', 'tab_recent': 'Недавние', 'tab_favorites': 'Избранные', 'tab_custom': 'Мои',
        'nothing_recent': 'Ещё нет недавних продуктов', 'nothing_favorites': 'Нет избранных продуктов',
        'nothing_custom': 'Нет своих продуктов — создайте первый!',
        'custom_limit_msg': 'Бесплатно: до 3 своих продуктов. Для безлимита — Premium',
        'limit_reached_msg': 'Лимит (3 продукта). Получите Premium для безлимита.',
        'create_food': 'Создать свой продукт', 'save_food': 'Сохранить',
        'product_name_label': 'Название', 'product_name_ph': 'Например: Мой омлет',
        'meal_type_label': 'Приём пищи', 'recent_label': 'Последние добавленные',
        'favorites_label': 'Избранные продукты', 'custom_label': 'Мои продукты',
        'off_source': 'Open Food Facts',
        'off_searching': '🌐 Ищем в Open Food Facts...',
        'off_tab': '🌐 Интернет',
        'off_found': 'найдено в Open Food Facts',
        'cat_fruits': 'Фрукты', 'cat_vegetables': 'Овощи', 'cat_meat': 'Мясо',
        'cat_dairy': 'Молочное', 'cat_grains': 'Злаки', 'cat_nuts': 'Орехи',
        'cat_fish': 'Рыба', 'cat_sweets': 'Сладкое', 'cat_drinks': 'Напитки',
        'cat_supplements': 'Витамины', 'cat_sports': 'Спортпит',
        'history_subtitle': 'Ваш прогресс и история питания',
        'daily_log': 'Дневник питания',
        'no_entries_yet': 'Нет записей. Начните вести дневник!',
        'language': 'Язык',
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
        'food_search_desc': '100+ foods + 3M products via Open Food Facts',
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
        'pm_history': '🔒 Full history is a Premium feature',
        'pm_weight_chart': '📈 Weight progress chart is available in Premium',
        'pm_weekly': '📅 Monthly summaries are a Premium feature',
        'pm_custom_limit': '⭐️ Unlimited custom foods available in Premium',
        'pm_export': '📤 Data export available in Premium',
        'pm_meals': '🥗 Meal breakdown available in Premium',
        'pm_macros': '💪 A serious tool for a serious approach. Premium',
        'pm_generic': '👑 Unlock the full potential in Premium',
        'pm_data': '🌿 More data — better results. Premium',
        'pm_no_thanks': 'No thanks',
        'pm_try_btn': 'Try — 11 ₽ / week',
        'pm_monthly_note': 'or 129 ₽ / month',
        'pm_profile_section': '⭐ Premium features',
        'pm_profile_desc': 'Unlock everything — full history, charts, export, unlimited foods.',
        'pm_profile_btn': 'Get Premium',
        'pm_active_until': 'Premium active until',
        'pm_active_forever': 'Premium active forever',
        'streak_label': '🔥 days in a row', 'streak_zero': 'Start your diary!',
        'weight_chart_title': '📈 Weight chart', 'weight_log_today': 'Log weight today',
        'weight_placeholder': 'kg', 'weight_save_btn': 'Save',
        'weekly_title': '📊 This week', 'avg_cal_label': 'Avg kcal',
        'days_on_goal_label': 'Days on target', 'days_logged_label': 'Days logged',
        'cal_history_title': '📅 Calorie history', 'click_day_hint': 'Click a day to see foods',
        'history_premium_msg': 'Full history available in Premium',
        'foods_that_day': 'Foods that day', 'no_foods_day': 'No entries',
        'weight_chart_premium': '📈 Weight chart available in Premium',
        'tab_search': 'Search', 'tab_recent': 'Recent', 'tab_favorites': 'Favorites', 'tab_custom': 'Mine',
        'nothing_recent': 'No recent foods yet', 'nothing_favorites': 'No favorites yet',
        'nothing_custom': 'No custom foods — create your first!',
        'custom_limit_msg': 'Free: up to 3 custom foods. Unlimited with Premium',
        'limit_reached_msg': 'Limit reached (3 foods). Get Premium for unlimited.',
        'create_food': 'Create custom food', 'save_food': 'Save',
        'product_name_label': 'Name', 'product_name_ph': 'e.g. My omelette',
        'meal_type_label': 'Meal', 'recent_label': 'Recently added',
        'favorites_label': 'Favorite foods', 'custom_label': 'My foods',
        'off_source': 'Open Food Facts',
        'off_searching': '🌐 Searching Open Food Facts...',
        'off_tab': '🌐 Internet',
        'off_found': 'found in Open Food Facts',
        'cat_fruits': 'Fruits', 'cat_vegetables': 'Vegetables', 'cat_meat': 'Meat',
        'cat_dairy': 'Dairy', 'cat_grains': 'Grains', 'cat_nuts': 'Nuts',
        'cat_fish': 'Fish', 'cat_sweets': 'Sweets', 'cat_drinks': 'Drinks',
        'cat_supplements': 'Vitamins', 'cat_sports': 'Sports nutrition',
        'history_subtitle': 'Your progress and nutrition history',
        'daily_log': 'Nutrition diary',
        'no_entries_yet': 'No entries yet. Start your diary!',
        'language': 'Language',
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
        'food_search_desc': '100+ продуктів + 3 млн у Open Food Facts',
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
        'pm_history': '🔒 Повна історія — це Premium',
        'pm_weight_chart': '📈 Графік динаміки ваги доступний в Premium',
        'pm_weekly': '📅 Місячні зведення — це Premium',
        'pm_custom_limit': '⭐️ Безліміт своїх продуктів доступний в Premium',
        'pm_export': '📤 Експорт даних доступний в Premium',
        'pm_meals': '🥗 Розбивка по прийомах їжі доступна в Premium',
        'pm_macros': '💪 Серйозний інструмент для серйозного підходу. Premium',
        'pm_generic': '👑 Весь потенціал застосунку відкритий в Premium',
        'pm_data': '🌿 Більше даних — кращий результат. Premium',
        'pm_no_thanks': 'Ні, дякую',
        'pm_try_btn': 'Спробувати — 11 ₽ / тиждень',
        'pm_monthly_note': 'або 129 ₽ / місяць',
        'pm_profile_section': '⭐ Premium можливості',
        'pm_profile_desc': 'Розблокуйте все — повна історія, графіки, експорт, безліміт продуктів.',
        'pm_profile_btn': 'Підключити Premium',
        'pm_active_until': 'Premium активний до',
        'pm_active_forever': 'Premium активний назавжди',
        'streak_label': '🔥 днів підряд', 'streak_zero': 'Почніть вести щоденник!',
        'weight_chart_title': '📈 Графік ваги', 'weight_log_today': 'Внести вагу сьогодні',
        'weight_placeholder': 'кг', 'weight_save_btn': 'Записати',
        'weekly_title': '📊 Тиждень', 'avg_cal_label': 'Середнє ккал',
        'days_on_goal_label': 'Днів у нормі', 'days_logged_label': 'Днів із записами',
        'cal_history_title': '📅 Історія калорій', 'click_day_hint': 'Натисніть на день — список продуктів',
        'history_premium_msg': 'Повна історія доступна в Premium',
        'foods_that_day': 'Продукти за цей день', 'no_foods_day': 'Немає записів',
        'weight_chart_premium': '📈 Графік ваги доступний в Premium',
        'tab_search': 'Пошук', 'tab_recent': 'Недавні', 'tab_favorites': 'Вибрані', 'tab_custom': 'Мої',
        'nothing_recent': 'Ще немає недавніх продуктів', 'nothing_favorites': 'Немає вибраних',
        'nothing_custom': 'Немає своїх продуктів — створіть перший!',
        'custom_limit_msg': 'Безкоштовно: до 3 своїх продуктів. Безліміт — Premium',
        'limit_reached_msg': 'Ліміт (3 продукти). Отримайте Premium для безліміту.',
        'create_food': 'Створити свій продукт', 'save_food': 'Зберегти',
        'product_name_label': 'Назва', 'product_name_ph': 'Наприклад: Мій омлет',
        'meal_type_label': 'Прийом їжі', 'recent_label': 'Останні додані',
        'favorites_label': 'Вибрані продукти', 'custom_label': 'Мої продукти',
        'off_source': 'Open Food Facts',
        'off_searching': '🌐 Шукаємо в Open Food Facts...',
        'off_tab': '🌐 Інтернет',
        'off_found': 'знайдено в Open Food Facts',
        'cat_fruits': 'Фрукти', 'cat_vegetables': 'Овочі', 'cat_meat': 'Мʼясо',
        'cat_dairy': 'Молочне', 'cat_grains': 'Злаки', 'cat_nuts': 'Горіхи',
        'cat_fish': 'Риба', 'cat_sweets': 'Солодке', 'cat_drinks': 'Напої',
        'cat_supplements': 'Вітаміни', 'cat_sports': 'Спортхарч',
        'history_subtitle': 'Ваш прогрес та історія харчування',
        'daily_log': 'Щоденник харчування',
        'no_entries_yet': 'Немає записів. Почніть вести щоденник!',
        'language': 'Мова',
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
        'food_search_desc': '100+ өнімдер + 3 млн Open Food Facts-та',
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
        'pm_history': '🔒 Толық тарих — бұл Premium',
        'pm_weight_chart': '📈 Салмақ динамикасы графигі Premium-да',
        'pm_weekly': '📅 Айлық есептер Premium-да',
        'pm_custom_limit': '⭐️ Шексіз өз өнімдер Premium-да',
        'pm_export': '📤 Деректерді экспорттау Premium-да',
        'pm_meals': '🥗 Тамақ бойынша бөлу Premium-да',
        'pm_macros': '💪 Байыпты тәсіл үшін байыпты құрал. Premium',
        'pm_generic': '👑 Қолданбаның толық мүмкіндіктері Premium-да',
        'pm_data': '🌿 Көбірек деректер — жақсырақ нәтиже. Premium',
        'pm_no_thanks': 'Жоқ, рахмет',
        'pm_try_btn': 'Сынап көру — 11 ₽ / апта',
        'pm_monthly_note': 'немесе 129 ₽ / ай',
        'pm_profile_section': '⭐ Premium мүмкіндіктер',
        'pm_profile_desc': 'Барлығын ашыңыз — толық тарих, графиктер, экспорт, шексіз өнімдер.',
        'pm_profile_btn': 'Premium қосу',
        'pm_active_until': 'Premium белсенді',
        'pm_active_forever': 'Premium мәңгі белсенді',
        'streak_label': '🔥 күн қатарынан', 'streak_zero': 'Күнделік жүргізуді бастаңыз!',
        'weight_chart_title': '📈 Салмақ графигі', 'weight_log_today': 'Бүгін салмақты енгізу',
        'weight_placeholder': 'кг', 'weight_save_btn': 'Жазу',
        'weekly_title': '📊 Апта', 'avg_cal_label': 'Орт. ккал',
        'days_on_goal_label': 'Нормадағы күндер', 'days_logged_label': 'Жазбалы күндер',
        'cal_history_title': '📅 Калория тарихы', 'click_day_hint': 'Күнді басыңыз — өнімдер тізімі',
        'history_premium_msg': 'Толық тарих Premium-да қол жетімді',
        'foods_that_day': 'Сол күнгі өнімдер', 'no_foods_day': 'Жазба жоқ',
        'weight_chart_premium': '📈 Салмақ графигі Premium-да қол жетімді',
        'tab_search': 'Іздеу', 'tab_recent': 'Соңғы', 'tab_favorites': 'Таңдаулы', 'tab_custom': 'Менің',
        'nothing_recent': 'Әзірше соңғы өнімдер жоқ', 'nothing_favorites': 'Таңдаулылар жоқ',
        'nothing_custom': 'Өз өнімдерім жоқ — бірінші жасаңыз!',
        'custom_limit_msg': 'Тегін: 3 өз өнімге дейін. Шексіз — Premium',
        'limit_reached_msg': 'Шек жетті (3 өнім). Premium алыңыз.',
        'create_food': 'Өз өнімді жасау', 'save_food': 'Сақтау',
        'product_name_label': 'Атауы', 'product_name_ph': 'Мысалы: Менің омлетім',
        'meal_type_label': 'Тамақ қабылдау', 'recent_label': 'Соңғы қосылған',
        'favorites_label': 'Таңдаулы өнімдер', 'custom_label': 'Менің өнімдерім',
        'off_source': 'Open Food Facts',
        'off_searching': '🌐 Open Food Facts іздеуде...',
        'off_tab': '🌐 Интернет',
        'off_found': 'Open Food Facts-та табылды',
        'cat_fruits': 'Жемістер', 'cat_vegetables': 'Көкөністер', 'cat_meat': 'Ет',
        'cat_dairy': 'Сүт өнімдері', 'cat_grains': 'Астық', 'cat_nuts': 'Жаңғақтар',
        'cat_fish': 'Балық', 'cat_sweets': 'Тәттілер', 'cat_drinks': 'Сусындар',
        'cat_supplements': 'Витаминдер', 'cat_sports': 'Спорт тамағы',
        'history_subtitle': 'Сіздің прогрессіңіз және тамақтану тарихы',
        'daily_log': 'Күнделік',
        'no_entries_yet': 'Жазба жоқ. Күнделік жүргізуді бастаңыз!',
        'language': 'Тіл',
    }
}


# ===================== OPEN FOOD FACTS API =====================

# Simple in-memory cache to avoid hammering the API
_off_cache = {}

def _off_cache_key(query, lang):
    raw = f"{query.lower().strip()}:{lang}"
    return hashlib.md5(raw.encode()).hexdigest()


def search_openfoodfacts(query, lang='ru', page_size=20):
    """
    Search Open Food Facts for products matching the query.
    Returns a list of dicts compatible with the local food format.
    Results are cached in memory for the lifetime of the process.
    """
    import requests as req

    cache_key = _off_cache_key(query, lang)
    if cache_key in _off_cache:
        return _off_cache[cache_key]

    # Map app language to OFF search language hint
    lang_map = {'ru': 'ru', 'en': 'en', 'uk': 'uk', 'kk': 'kk'}
    search_lc = lang_map.get(lang, 'en')

    # Field we prefer for display name, in priority order
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
            'fields': (
                'code,product_name,product_name_ru,product_name_en,'
                'product_name_uk,product_name_kk,'
                'nutriments,categories_tags,brands,quantity,'
                'image_front_small_url'
            )
        }
        resp = req.get(url, params=params, timeout=6,
                       headers={'User-Agent': 'CaloriMint/1.0 (calorietracker; contact@calorimit.app)'})
        if resp.status_code != 200:
            return []

        data = resp.json()
        results = []
        seen_names = set()

        for p in data.get('products', []):
            n = p.get('nutriments', {})

            # Calories (prefer kcal, fall back to kJ / 4.184)
            cal = (n.get('energy-kcal_100g')
                   or n.get('energy-kcal')
                   or (n.get('energy_100g', 0) / 4.184 if n.get('energy_100g') else 0))
            if not cal or cal <= 0:
                continue

            protein = float(n.get('proteins_100g') or n.get('proteins') or 0)
            fat     = float(n.get('fat_100g')      or n.get('fat')      or 0)
            carbs   = float(n.get('carbohydrates_100g') or n.get('carbohydrates') or 0)

            # Pick best available display name
            display_name = ''
            for field in preferred_fields:
                v = p.get(field, '').strip()
                if v:
                    display_name = v
                    break
            if not display_name:
                continue

            # Deduplicate by lower-cased display name
            name_key = display_name.lower()
            if name_key in seen_names:
                continue
            seen_names.add(name_key)

            # Build a stable OFF id using the barcode
            barcode = str(p.get('code', ''))[:13]
            off_id = f'off_{barcode}' if barcode else f'off_nob_{len(results)}'

            # Brand / quantity hint shown as subtitle in UI
            brand = p.get('brands', '').split(',')[0].strip()
            quantity = p.get('quantity', '').strip()
            subtitle_parts = [x for x in [brand, quantity] if x]
            subtitle = ' · '.join(subtitle_parts) if subtitle_parts else ''

            results.append({
                'id': off_id,
                'name_ru': display_name,
                'name_en': p.get('product_name_en') or p.get('product_name') or display_name,
                'calories': round(float(cal), 1),
                'protein': round(protein, 1),
                'fat':     round(fat, 1),
                'carbs':   round(carbs, 1),
                'category': 'other',
                'source': 'off',
                'subtitle': subtitle,
                'image': p.get('image_front_small_url', ''),
            })

        _off_cache[cache_key] = results
        return results

    except Exception as e:
        print(f'[OFF] Error: {e}')
        return []


# ===================== ROUTES =====================

@app.before_request
def before_request():
    try:
        if current_user.is_authenticated:
            session['lang'] = current_user.language or 'ru'
        elif 'lang' not in session:
            session['lang'] = 'ru'
    except Exception:
        pass

    try:
        if current_user.is_authenticated and current_user.is_premium:
            if current_user.premium_ends and current_user.premium_ends < datetime.utcnow():
                current_user.is_premium = False
                current_user.premium_ends = None
                db.session.commit()
    except Exception:
        pass


@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))

    lang = current_user.language or 'ru'
    t = translations.get(lang, translations['ru'])
    today = date.today()
    entries = FoodEntry.query.filter_by(user_id=current_user.id, date=today).all()

    meals = {
        'breakfast': {'name': t.get('breakfast'), 'icon': '🌅', 'color': '#f39c12', 'total': 0, 'entries': []},
        'lunch':     {'name': t.get('lunch'),     'icon': '☀️',  'color': '#27ae60', 'total': 0, 'entries': []},
        'dinner':    {'name': t.get('dinner'),    'icon': '🌙', 'color': '#3498db', 'total': 0, 'entries': []},
        'snack':     {'name': t.get('snack'),     'icon': '🍿', 'color': '#e74c3c', 'total': 0, 'entries': []},
    }

    total_calories = total_protein = total_fat = total_carbs = 0

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
        total_protein  += entry.protein
        total_fat      += entry.fat
        total_carbs    += entry.carbs

    from datetime import timedelta
    streak = 0
    check = today
    while True:
        has_entry = FoodEntry.query.filter_by(user_id=current_user.id, date=check).first()
        if has_entry:
            streak += 1
            check = check - timedelta(days=1)
        else:
            break

    return render_template('index.html',
        t=t,
        meals=meals,
        total_calories=int(total_calories),
        total_protein=int(total_protein),
        total_fat=int(total_fat),
        total_carbs=int(total_carbs),
        lang=lang,
        streak=streak
    )


@app.route('/api/search', methods=['GET'])
@login_required
def search_foods():
    query    = request.args.get('q', '').strip().lower()
    category = request.args.get('category', '').strip()
    show_all = request.args.get('show_all', '')
    off_only = request.args.get('off_only', '')      # NEW: dedicated OFF search
    lang     = current_user.language or 'ru'

    if not query and not category and not show_all and not off_only:
        return jsonify([])

    # ── OFF-ONLY mode (called by front-end tab independently) ──
    if off_only and query:
        off_results = search_openfoodfacts(query, lang, page_size=25)
        return jsonify(off_results[:25])

    # ── LOCAL search first ──
    from food_data import food_data
    results = []
    for idx, food in enumerate(food_data):
        if category and food.get('category') != category:
            continue
        if query:
            haystack = ' '.join([food.get('name_ru', ''), food.get('name_en', ''),
                                  food.get('name_uk', ''), food.get('name_kk', '')]).lower()
            if query not in haystack:
                continue
        results.append({
            'id': idx,
            'name_ru': food['name_ru'],
            'name_en': food.get('name_en', food['name_ru']),
            'calories': food['calories'],
            'protein':  food.get('protein', 0),
            'fat':      food.get('fat', 0),
            'carbs':    food.get('carbs', 0),
            'category': food.get('category', 'other'),
            'source': 'local'
        })

    # ── Augment with OFF when query given and local results are sparse ──
    if query and len(results) < 8:
        off_results = search_openfoodfacts(query, lang, page_size=15)
        local_names = {r['name_ru'].lower() for r in results}
        for item in off_results:
            if item['name_ru'].lower() not in local_names:
                results.append(item)
                local_names.add(item['name_ru'].lower())

    return jsonify(results[:30])


# NEW: dedicated Open Food Facts search endpoint (non-blocking for UI)
@app.route('/api/search-off', methods=['GET'])
@login_required
def search_foods_off():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])
    lang = current_user.language or 'ru'
    results = search_openfoodfacts(query, lang, page_size=20)
    return jsonify(results[:20])


@app.route('/api/add-entry', methods=['POST'])
@login_required
def add_entry():
    data = request.get_json()
    food_id = data.get('food_id')
    grams = float(data.get('grams', 100))
    meal_type = data.get('meal_type', 'snack')

    if isinstance(food_id, str) and (food_id.startswith('off_') or food_id.startswith('custom_')):
        cal_per_100     = float(data.get('calories', 0))
        protein_per_100 = float(data.get('protein', 0))
        fat_per_100     = float(data.get('fat', 0))
        carbs_per_100   = float(data.get('carbs', 0))
        food_name = data.get('food_name', 'Unknown')
        multiplier = grams / 100
        entry = FoodEntry(
            user_id=current_user.id, food_id=0, food_name=food_name,
            grams=grams,
            calories=cal_per_100 * multiplier,
            protein=protein_per_100 * multiplier,
            fat=fat_per_100 * multiplier,
            carbs=carbs_per_100 * multiplier,
            meal_type=meal_type, date=date.today()
        )
        db.session.add(entry)
        db.session.commit()
        return jsonify({'success': True})

    from food_data import food_data
    food_id = int(food_id)
    if food_id < 0 or food_id >= len(food_data):
        return jsonify({'error': 'Invalid food'}), 400

    food = food_data[food_id]
    multiplier = grams / 100
    entry = FoodEntry(
        user_id=current_user.id, food_id=food_id, food_name=food['name_ru'],
        grams=grams,
        calories=food['calories'] * multiplier,
        protein=food.get('protein', 0) * multiplier,
        fat=food.get('fat', 0) * multiplier,
        carbs=food.get('carbs', 0) * multiplier,
        meal_type=meal_type, date=date.today()
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
        user_id=current_user.id, meal_type=meal_type, date=date.today()
    ).all()
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
    entries = FoodEntry.query.filter_by(user_id=current_user.id).order_by(
        FoodEntry.created_at.desc()
    ).limit(50).all()
    seen = set()
    results = []
    for entry in entries:
        if entry.food_id == 0 or entry.food_id in seen or entry.food_id >= len(food_data):
            continue
        seen.add(entry.food_id)
        food = food_data[entry.food_id]
        results.append({
            'id': entry.food_id, 'name_ru': food['name_ru'],
            'calories': food['calories'], 'protein': food.get('protein', 0),
            'fat': food.get('fat', 0), 'carbs': food.get('carbs', 0)
        })
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
            results.append({
                'id': fid, 'name_ru': food['name_ru'],
                'calories': food['calories'], 'protein': food.get('protein', 0),
                'fat': food.get('fat', 0), 'carbs': food.get('carbs', 0)
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


# ===================== CUSTOM FOODS =====================

@app.route('/api/custom-foods', methods=['GET'])
@login_required
def get_custom_foods():
    foods = CustomFood.query.filter_by(user_id=current_user.id).order_by(CustomFood.created_at.desc()).all()
    return jsonify([{
        'id': f'custom_{f.id}', 'name_ru': f.name,
        'calories': f.calories, 'protein': f.protein,
        'fat': f.fat, 'carbs': f.carbs, 'source': 'custom'
    } for f in foods])


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
    f = CustomFood(
        user_id=current_user.id, name=name,
        calories=float(data.get('calories', 0)),
        protein=float(data.get('protein', 0)),
        fat=float(data.get('fat', 0)),
        carbs=float(data.get('carbs', 0))
    )
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


# ===================== WEIGHT LOG =====================

@app.route('/api/weight-log', methods=['GET'])
@login_required
def get_weight_log():
    from datetime import timedelta
    days = int(request.args.get('days', 30))
    since = date.today() - timedelta(days=days)
    logs = WeightLog.query.filter(
        WeightLog.user_id == current_user.id,
        WeightLog.date >= since
    ).order_by(WeightLog.date.asc()).all()
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
    return jsonify({
        'weight': last.weight if last else (current_user.current_weight or ''),
        'date': last.date.strftime('%Y-%m-%d') if last else None
    })


# ===================== HISTORY / PROGRESS =====================

@app.route('/api/history-data', methods=['GET'])
@login_required
def history_data():
    from datetime import timedelta
    days = int(request.args.get('days', 30))
    since = date.today() - timedelta(days=days)
    entries = FoodEntry.query.filter(
        FoodEntry.user_id == current_user.id,
        FoodEntry.date >= since
    ).all()
    day_map = {}
    for e in entries:
        ds = e.date.strftime('%Y-%m-%d')
        if ds not in day_map:
            day_map[ds] = {'calories': 0, 'protein': 0, 'fat': 0, 'carbs': 0, 'foods': []}
        day_map[ds]['calories'] += e.calories
        day_map[ds]['protein']  += e.protein
        day_map[ds]['fat']      += e.fat
        day_map[ds]['carbs']    += e.carbs
        day_map[ds]['foods'].append({
            'name': e.food_name, 'grams': e.grams,
            'calories': e.calories, 'meal': e.meal_type
        })
    return jsonify({'days': day_map, 'goal': current_user.daily_calorie_goal or 2000})


@app.route('/api/streak', methods=['GET'])
@login_required
def get_streak():
    from datetime import timedelta
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
    from datetime import timedelta
    today = date.today()
    since = today - timedelta(days=6)
    entries = FoodEntry.query.filter(
        FoodEntry.user_id == current_user.id,
        FoodEntry.date >= since
    ).all()
    goal = current_user.daily_calorie_goal or 2000
    day_map = {}
    for e in entries:
        ds = e.date.strftime('%Y-%m-%d')
        if ds not in day_map:
            day_map[ds] = {'cal': 0, 'protein': 0, 'fat': 0, 'carbs': 0}
        day_map[ds]['cal']     += e.calories
        day_map[ds]['protein'] += e.protein
        day_map[ds]['fat']     += e.fat
        day_map[ds]['carbs']   += e.carbs
    days_logged  = len(day_map)
    days_on_goal = sum(1 for d in day_map.values() if d['cal'] <= goal)
    avg_cal      = round(sum(d['cal']     for d in day_map.values()) / max(days_logged, 1))
    avg_protein  = round(sum(d['protein'] for d in day_map.values()) / max(days_logged, 1))
    avg_fat      = round(sum(d['fat']     for d in day_map.values()) / max(days_logged, 1))
    avg_carbs    = round(sum(d['carbs']   for d in day_map.values()) / max(days_logged, 1))
    return jsonify({
        'days_logged': days_logged, 'days_on_goal': days_on_goal,
        'avg_cal': avg_cal, 'avg_protein': avg_protein,
        'avg_fat': avg_fat, 'avg_carbs': avg_carbs, 'goal': goal
    })


@app.route('/history')
@login_required
def history():
    from datetime import timedelta
    from collections import OrderedDict
    lang = current_user.language or 'ru'
    t = translations.get(lang, translations['ru'])
    is_premium = current_user.is_premium

    if is_premium:
        entries = FoodEntry.query.filter_by(user_id=current_user.id).order_by(FoodEntry.date.desc()).all()
    else:
        since = date.today() - timedelta(days=6)
        entries = FoodEntry.query.filter(
            FoodEntry.user_id == current_user.id,
            FoodEntry.date >= since
        ).order_by(FoodEntry.date.desc()).all()

    days = OrderedDict()
    for e in entries:
        ds = e.date.strftime('%d.%m.%Y')
        if ds not in days:
            days[ds] = {'entries': [], 'total_cal': 0, 'total_protein': 0, 'total_fat': 0, 'total_carbs': 0}
        days[ds]['entries'].append({
            'food_name': e.food_name, 'grams': e.grams, 'calories': e.calories,
            'protein': e.protein, 'fat': e.fat, 'carbs': e.carbs,
            'meal_type': e.meal_type or 'other'
        })
        days[ds]['total_cal']     += e.calories
        days[ds]['total_protein'] += e.protein
        days[ds]['total_fat']     += e.fat
        days[ds]['total_carbs']   += e.carbs

    streak = 0
    check = date.today()
    while True:
        has_entry = FoodEntry.query.filter_by(user_id=current_user.id, date=check).first()
        if has_entry:
            streak += 1
            check = check - timedelta(days=1)
        else:
            break

    return render_template('history.html', days=days, t=t, lang=lang, is_premium=is_premium,
                           streak=streak, goal=current_user.daily_calorie_goal or 2000,
                           current_user=current_user)


@app.route('/goals', methods=['GET', 'POST'])
@login_required
def goals():
    lang = current_user.language or 'ru'
    t = translations.get(lang, translations['ru'])

    last_weight_log = WeightLog.query.filter_by(user_id=current_user.id).order_by(WeightLog.date.desc()).first()
    last_weight = last_weight_log.weight if last_weight_log else current_user.current_weight

    if request.method == 'POST':
        current_user.daily_calorie_goal = int(request.form.get('daily_calorie_goal', 2000))
        current_user.protein_goal       = int(request.form.get('protein_goal', 150))
        current_user.fat_goal           = int(request.form.get('fat_goal', 70))
        current_user.carbs_goal         = int(request.form.get('carbs_goal', 250))
        current_user.age                = int(request.form.get('age', 25))
        current_user.gender             = request.form.get('gender', 'male')
        current_user.activity           = request.form.get('activity', 'moderate')
        current_user.height             = float(request.form.get('height', 170))
        current_user.current_weight     = float(request.form.get('current_weight', 70))
        current_user.goal_weight        = float(request.form.get('goal_weight', 70))
        current_user.water_goal         = int(request.form.get('water_goal', 8))
        db.session.commit()
        flash('Goals updated!', 'success')
        return redirect(url_for('goals'))

    return render_template('goals.html', user=current_user, t=t, lang=lang, last_weight=last_weight)


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
            'id': idx, 'name': food['name_ru'], 'calories': food['calories'],
            'protein': food.get('protein', 0), 'fat': food.get('fat', 0),
            'carbs': food.get('carbs', 0), 'category': cat
        })
    cat_labels = {
        'fruits':          '🍎 ' + {'ru':'Фрукты','en':'Fruits','uk':'Фрукти','kk':'Жемістер'}.get(lang,'Fruits'),
        'vegetables':      '🥦 ' + {'ru':'Овощи','en':'Vegetables','uk':'Овочі','kk':'Көкөністер'}.get(lang,'Vegetables'),
        'meat':            '🥩 ' + {'ru':'Мясо','en':'Meat','uk':'Мʼясо','kk':'Ет'}.get(lang,'Meat'),
        'dairy':           '🥛 ' + {'ru':'Молочное','en':'Dairy','uk':'Молочне','kk':'Сүт өнімдері'}.get(lang,'Dairy'),
        'grains':          '🌾 ' + {'ru':'Злаки','en':'Grains','uk':'Злаки','kk':'Астық'}.get(lang,'Grains'),
        'nuts':            '🌰 ' + {'ru':'Орехи','en':'Nuts','uk':'Горіхи','kk':'Жаңғақтар'}.get(lang,'Nuts'),
        'fish':            '🐟 ' + {'ru':'Рыба','en':'Fish','uk':'Риба','kk':'Балық'}.get(lang,'Fish'),
        'sweets':          '🍫 ' + {'ru':'Сладкое','en':'Sweets','uk':'Солодке','kk':'Тәттілер'}.get(lang,'Sweets'),
        'drinks':          '🥤 ' + {'ru':'Напитки','en':'Drinks','uk':'Напої','kk':'Сусындар'}.get(lang,'Drinks'),
        'supplements':     '💊 ' + {'ru':'Витамины','en':'Supplements','uk':'Добавки','kk':'Қоспалар'}.get(lang,'Supplements'),
        'sports_nutrition':'💪 ' + {'ru':'Спортпит','en':'Sports Nutrition','uk':'Спортхарч','kk':'Спорт тамағы'}.get(lang,'Sports Nutrition'),
        'other':           '🍽 ' + {'ru':'Прочее','en':'Other','uk':'Інше','kk':'Басқа'}.get(lang,'Other'),
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
                           trial_available=trial_available, trial_active=trial_active,
                           now=datetime.utcnow())


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
                           trial_available=False, trial_active=True,
                           trial_success=True, now=datetime.utcnow())


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()
        if not user:
            user = User.query.filter_by(email=username).first()

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
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        language = request.form.get('language', 'ru')

        if not username or not email or not password:
            flash('All fields are required', 'error')
            lang = session.get('lang', 'ru')
            t = translations.get(lang, translations['ru'])
            return render_template('register.html', t=t, lang=lang)

        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            lang = session.get('lang', 'ru')
            t = translations.get(lang, translations['ru'])
            return render_template('register.html', t=t, lang=lang)

        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            lang = session.get('lang', 'ru')
            t = translations.get(lang, translations['ru'])
            return render_template('register.html', t=t, lang=lang)

        user = User(
            username=username, email=email,
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
    if lang not in translations:
        lang = 'ru'
    if current_user.is_authenticated:
        current_user.language = lang
        db.session.commit()
    else:
        session['lang'] = lang
    return redirect(request.referrer or '/')


# ===================== DB INITIALIZATION =====================

with app.app_context():
    db.create_all()
    init_db()

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


# ===================== ADMIN =====================

from functools import wraps

def superuser_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_superuser:
            from flask import abort
            abort(403)
        return f(*args, **kwargs)
    return decorated


@app.route('/admin')
@login_required
@superuser_required
def admin_panel():
    query = request.args.get('q', '').strip()
    if query:
        users = User.query.filter(
            (User.email.ilike(f'%{query}%')) | (User.username.ilike(f'%{query}%'))
        ).order_by(User.created_at.desc()).all()
    else:
        users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin.html', users=users, query=query, now=datetime.utcnow())


@app.route('/admin/grant-premium', methods=['POST'])
@login_required
@superuser_required
def admin_grant_premium():
    from datetime import timedelta
    user_id  = int(request.form.get('user_id'))
    duration = request.form.get('duration', '1month')
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    user.is_premium = True
    if duration == '7days':
        user.premium_ends = datetime.utcnow() + timedelta(days=7)
    elif duration == '1month':
        user.premium_ends = datetime.utcnow() + timedelta(days=30)
    elif duration == '3months':
        user.premium_ends = datetime.utcnow() + timedelta(days=90)
    elif duration == 'forever':
        user.premium_ends = None
    db.session.commit()
    return redirect(url_for('admin_panel', q=request.args.get('q', '')))


@app.route('/admin/revoke-premium', methods=['POST'])
@login_required
@superuser_required
def admin_revoke_premium():
    user_id = int(request.form.get('user_id'))
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    user.is_premium = False
    user.premium_ends = None
    user.trial_ends = None
    db.session.commit()
    return redirect(url_for('admin_panel', q=request.args.get('q', '')))


@app.route('/admin/make-superuser', methods=['POST'])
@login_required
@superuser_required
def admin_make_superuser():
    user_id = int(request.form.get('user_id'))
    user = User.query.get(user_id)
    if user:
        user.is_superuser = True
        db.session.commit()
    return redirect(url_for('admin_panel'))


if __name__ == '__main__':
    app.run(debug=True)