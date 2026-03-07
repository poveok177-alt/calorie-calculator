import requests

def search_openfoodfacts(query: str, lang: str = 'ru', page_size: int = 20) -> list:
    """
    Ищет продукты через OpenFoodFacts API.
    Ничего не качает и не хранит — запрос в реальном времени.
    """
    try:
        url = "https://world.openfoodfacts.org/cgi/search.pl"
        params = {
            'search_terms': query,
            'search_simple': 1,
            'action': 'process',
            'json': 1,
            'page_size': page_size,
            'fields': 'product_name,product_name_ru,product_name_en,nutriments,categories,brands,code',
            # Только продукты с заполненным КБЖУ
            'nutriments_present': 'energy-kcal_100g',
        }

        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()

        results = []
        for p in data.get('products', []):
            n = p.get('nutriments', {})

            # Калории
            kcal = n.get('energy-kcal_100g') or n.get('energy_100g', 0)
            if kcal and kcal > 900:  # Если джоули — конвертируем
                kcal = round(kcal / 4.184, 1)
            if not kcal or kcal <= 0:
                continue

            # Название — предпочитаем русское
            name = (
                p.get('product_name_ru') or
                p.get('product_name') or
                p.get('product_name_en') or
                ''
            ).strip()

            if not name:
                continue

            results.append({
                'id': f"off_{p.get('code', '')}",   # Префикс чтобы не конфликтовать с твоей БД
                'name_ru': name,
                'name_en': p.get('product_name_en', name),
                'calories': round(float(kcal), 1),
                'protein': round(float(n.get('proteins_100g', 0) or 0), 1),
                'fat':     round(float(n.get('fat_100g', 0) or 0), 1),
                'carbs':   round(float(n.get('carbohydrates_100g', 0) or 0), 1),
                'brand':   p.get('brands', ''),
                'source':  'openfoodfacts',  # Маркер — пришло из OFF, не из твоей БД
            })

        return results

    except Exception as e:
        print(f"OpenFoodFacts error: {e}")
        return []  # Фаллбэк — просто ничего не возвращаем, своя БД работает


# =====================================================================
# Добавь в app.py этот endpoint:
# =====================================================================
"""
@app.route('/api/search')
@login_required  
def api_search():
    query = request.args.get('q', '').strip()
    lang = current_user.language or 'ru'
    
    if not query or len(query) < 2:
        return jsonify([])
    
    # 1. Сначала ищем в своей БД
    local_results = Food.query.filter(
        Food.name_ru.ilike(f'%{query}%') |
        Food.name_en.ilike(f'%{query}%')
    ).limit(10).all()
    
    results = [{
        'id': f.id,
        'name_ru': f.name_ru,
        'name_en': f.name_en,
        'calories': f.calories,
        'protein': f.protein,
        'fat': f.fat,
        'carbs': f.carbs,
        'source': 'local',
    } for f in local_results]
    
    # 2. Если своих меньше 5 — добираем из OpenFoodFacts
    if len(results) < 5:
        off_results = search_openfoodfacts(query, lang=lang, page_size=15)
        results += off_results[:10 - len(results)]
    
    return jsonify(results)
"""
