#!/usr/bin/env python3
"""
🌍 Загрузчик 3млн+ продуктов из Open Food Facts в SQLite
Использование:
    python3 load_products.py
    
Результат: products.db (500-800 MB) с полной базой продуктов
"""

import sqlite3
import csv
import os
import sys
from pathlib import Path

def create_database(db_path='products.db'):
    """Создать SQLite БД с индексами для быстрого поиска"""
    
    print("📦 Создание базы данных...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Таблица продуктов
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_ru TEXT,
            name_en TEXT,
            calories REAL,
            protein REAL,
            fat REAL,
            carbs REAL,
            category TEXT,
            barcode TEXT UNIQUE,
            brand TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Индексы для быстрого поиска
    c.execute('CREATE INDEX IF NOT EXISTS idx_name_ru ON products(name_ru)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_name_en ON products(name_en)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_category ON products(category)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_barcode ON products(barcode)')
    
    conn.commit()
    print(f"✅ База создана: {db_path}")
    return conn

def load_from_csv(conn, csv_path):
    """Загрузить продукты из CSV (Open Food Facts формат)"""
    
    if not os.path.exists(csv_path):
        print(f"❌ Файл не найден: {csv_path}")
        print("\n📥 Как загрузить данные:")
        print("1. Скачать с https://world.openfoodfacts.org/data")
        print("2. Распаковать файл")
        print("3. Запустить этот скрипт с путем к CSV")
        return False
    
    c = conn.cursor()
    count = 0
    errors = 0
    
    print(f"📂 Чтение {csv_path}...")
    print("⏳ Это может занять несколько минут для 3млн продуктов...")
    
    try:
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f, delimiter='\t')
            
            for row_num, row in enumerate(reader, 1):
                try:
                    # Парсинг данных
                    name = row.get('product_name', '') or row.get('product_name_en', '')
                    name_ru = row.get('product_name_ru', '') or name
                    name_en = row.get('product_name_en', '') or name
                    
                    if not name:
                        continue
                    
                    # Питательные значения (на 100г)
                    energy = row.get('energy-kcal_100g', '') or row.get('energy_100g', '')
                    if energy:
                        try:
                            calories = float(energy) / 4.184 if float(energy) > 100 else float(energy)
                        except:
                            calories = 0
                    else:
                        calories = 0
                    
                    if calories <= 0:
                        continue
                    
                    protein = float(row.get('proteins_100g', '') or 0)
                    fat = float(row.get('fat_100g', '') or 0)
                    carbs = float(row.get('carbohydrates_100g', '') or 0)
                    
                    category = row.get('categories', '') or 'other'
                    barcode = row.get('code', '')
                    brand = row.get('brands', '')
                    
                    # Вставка в БД
                    try:
                        c.execute('''
                            INSERT INTO products 
                            (name_ru, name_en, calories, protein, fat, carbs, category, barcode, brand)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (name_ru, name_en, calories, protein, fat, carbs, category, barcode, brand))
                        
                        count += 1
                        
                        # Коммит каждые 10,000 записей
                        if count % 10000 == 0:
                            conn.commit()
                            print(f"  ✓ Загружено {count:,} продуктов...")
                    
                    except sqlite3.IntegrityError:
                        # Дубликат по штрихкоду
                        pass
                
                except Exception as e:
                    errors += 1
                    if errors < 10:  # Показать первые 10 ошибок
                        print(f"  ⚠️  Ошибка в строке {row_num}: {e}")
        
        conn.commit()
        print(f"\n✅ Загружено: {count:,} продуктов")
        print(f"⚠️  Ошибок: {errors:,}")
        return True
    
    except Exception as e:
        print(f"❌ Ошибка при чтении файла: {e}")
        return False

def add_sample_products(conn):
    """Добавить локальные продукты если датасет не загружен"""
    
    c = conn.cursor()
    
    # Проверить количество
    c.execute('SELECT COUNT(*) FROM products')
    count = c.fetchone()[0]
    
    if count > 100:  # Уже есть данные
        return
    
    print("📝 Добавление локальных продуктов...")
    
    sample_products = [
        # Фрукты
        ('Яблоко', 'Apple', 52, 0.3, 0.2, 14, 'fruits', '', 'Local'),
        ('Банан', 'Banana', 89, 1.1, 0.3, 22.8, 'fruits', '', 'Local'),
        ('Апельсин', 'Orange', 43, 0.9, 0.2, 8.1, 'fruits', '', 'Local'),
        ('Груша', 'Pear', 57, 0.4, 0.3, 15.2, 'fruits', '', 'Local'),
        ('Клубника', 'Strawberry', 30, 0.8, 0.4, 5.5, 'fruits', '', 'Local'),
        
        # Овощи
        ('Морковь', 'Carrot', 41, 0.9, 0.2, 9.6, 'vegetables', '', 'Local'),
        ('Помидор', 'Tomato', 18, 0.9, 0.2, 3.8, 'vegetables', '', 'Local'),
        ('Огурец', 'Cucumber', 15, 0.7, 0.1, 2.8, 'vegetables', '', 'Local'),
        ('Брокколи', 'Broccoli', 34, 2.8, 0.4, 7, 'vegetables', '', 'Local'),
        ('Капуста', 'Cabbage', 27, 1.8, 0.1, 6.8, 'vegetables', '', 'Local'),
        
        # Мясо
        ('Говядина', 'Beef', 187, 18.9, 12.4, 0, 'meat', '', 'Local'),
        ('Куриная грудка', 'Chicken breast', 165, 31, 3.6, 0, 'meat', '', 'Local'),
        ('Свинина', 'Pork', 242, 16, 21, 0, 'meat', '', 'Local'),
        
        # Молочные
        ('Молоко', 'Milk', 52, 2.8, 2.5, 4.7, 'dairy', '', 'Local'),
        ('Творог', 'Cottage cheese', 121, 17, 5, 3, 'dairy', '', 'Local'),
        ('Сыр', 'Cheese', 356, 25, 27.4, 2.2, 'dairy', '', 'Local'),
        
        # Злаки
        ('Рис белый', 'White rice', 344, 7, 0.6, 78.9, 'grains', '', 'Local'),
        ('Гречка', 'Buckwheat', 308, 12.6, 3.3, 57.1, 'grains', '', 'Local'),
        ('Хлеб белый', 'White bread', 265, 7.7, 3.2, 51, 'grains', '', 'Local'),
    ]
    
    for prod in sample_products:
        try:
            c.execute('''
                INSERT INTO products 
                (name_ru, name_en, calories, protein, fat, carbs, category, barcode, brand)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', prod)
        except sqlite3.IntegrityError:
            pass
    
    conn.commit()
    print(f"✅ Добавлено {len(sample_products)} локальных продуктов")

def check_database(db_path='products.db'):
    """Проверить статус БД"""
    
    if not os.path.exists(db_path):
        print(f"❌ База не найдена: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) FROM products')
    total = c.fetchone()[0]
    
    c.execute('SELECT COUNT(DISTINCT category) FROM products')
    categories = c.fetchone()[0]
    
    print(f"\n📊 Статус БД: {db_path}")
    print(f"  📦 Всего продуктов: {total:,}")
    print(f"  📂 Категорий: {categories}")
    
    if total > 0:
        c.execute('SELECT name_ru, name_en, calories, protein, fat, carbs FROM products LIMIT 3')
        print(f"\n  📝 Примеры продуктов:")
        for row in c.fetchall():
            print(f"    - {row[0]} ({row[1]}) - {row[2]} ккал")
    
    conn.close()
    return total > 0

if __name__ == '__main__':
    db_path = 'products.db'
    
    # Создать или открыть БД
    conn = create_database(db_path)
    
    # Если передан путь к CSV
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
        print(f"\n📥 Загрузка из: {csv_file}")
        if load_from_csv(conn, csv_file):
            print("✅ Данные загружены успешно!")
        else:
            print("⚠️  Используются только локальные продукты")
            add_sample_products(conn)
    else:
        print("\n📌 Использование:")
        print(f"  python3 {sys.argv[0]} <путь_к_csv>")
        print("\n  Пример:")
        print(f"  python3 {sys.argv[0]} en.openfoodfacts.org.products.csv")
        print("\n📥 Скачать CSV с https://world.openfoodfacts.org/data")
        print("\n⏭️  Добавляю локальные продукты...")
        add_sample_products(conn)
    
    conn.close()
    
    # Проверить результат
    check_database(db_path)
    print("\n✅ Готово! Используйте products.db в приложении")
