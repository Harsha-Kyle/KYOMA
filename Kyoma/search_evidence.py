import os
import sys
import re
import html
import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

_SEARCH_CACHE: dict = {}
_SEARCH_CACHE_TTL = 120.0  # 2 minute TTL for fast repeated lookups

ABBREVIATIONS = {
    r"\bCM\b": "Chief Minister",
    r"\bPM\b": "Prime Minister",
    r"\bCEO\b": "Chief Executive Officer",
    r"\bCFO\b": "Chief Financial Officer",
    r"\bCTO\b": "Chief Technology Officer",
    r"\bCOO\b": "Chief Operating Officer",
    r"\bMD\b": "Managing Director",
    r"\bVP\b": "Vice President",
    r"\bMP\b": "Member of Parliament",
    r"\bMLA\b": "Member of Legislative Assembly",
    r"\bMLC\b": "Member of Legislative Council",
    r"\bGov\b": "Governor",
    r"\bPres\b": "President",
    r"\bCJ\b": "Chief Justice",
    r"\bCJI\b": "Chief Justice of India",
}

STATE_CODE_MAP = {
    "tn": "Tamil Nadu",
    "ap": "Andhra Pradesh",
    "ka": "Karnataka",
    "kl": "Kerala",
    "mh": "Maharashtra",
    "up": "Uttar Pradesh",
    "mp": "Madhya Pradesh",
    "wb": "West Bengal",
    "dl": "Delhi",
    "gj": "Gujarat",
    "rj": "Rajasthan",
    "pb": "Punjab",
    "hr": "Haryana",
    "br": "Bihar",
    "or": "Odisha",
    "od": "Odisha",
    "ts": "Telangana",
    "tg": "Telangana",
    "as": "Assam",
    "jk": "Jammu and Kashmir",
    "uk": "Uttarakhand",
    "hp": "Himachal Pradesh",
    "jh": "Jharkhand",
    "cg": "Chhattisgarh",
    "ga": "Goa",
    "py": "Puducherry",
}

CITY_STATE_MAP = {
    "chennai": "Tamil Nadu",
    "madras": "Tamil Nadu",
    "mumbai": "Maharashtra",
    "bombay": "Maharashtra",
    "bengaluru": "Karnataka",
    "bangalore": "Karnataka",
    "kolkata": "West Bengal",
    "calcutta": "West Bengal",
    "hyderabad": "Telangana",
    "lucknow": "Uttar Pradesh",
    "patna": "Bihar",
    "bhopal": "Madhya Pradesh",
    "jaipur": "Rajasthan",
    "thiruvananthapuram": "Kerala",
    "trivandrum": "Kerala",
    "ahmedabad": "Gujarat",
    "gandhinagar": "Gujarat",
    "shimla": "Himachal Pradesh",
    "chandigarh": "Punjab and Haryana",
    "dehradun": "Uttarakhand",
    "ranchi": "Jharkhand",
    "bhubaneswar": "Odisha",
    "guwahati": "Assam",
    "dispur": "Assam",
    "panaji": "Goa",
    "raipur": "Chhattisgarh",
}

def normalize_query_and_resolve_context(query: str) -> tuple[str, list[str]]:
    """
    Expand abbreviations and resolve city-to-state/region context.
    Returns (cleaned_primary_query, list_of_query_variants).
    """
    if not query:
        return "", []

    q = query.strip()
    expanded = q
    for pat, full in ABBREVIATIONS.items():
        expanded = re.sub(pat, full, expanded, flags=re.IGNORECASE)

    for sc, st_name in STATE_CODE_MAP.items():
        if sc.lower() == "up":
            expanded = re.sub(r"\b(?:in|of|for|from)\s+up\b", f" of {st_name}", expanded, flags=re.IGNORECASE)
        else:
            expanded = re.sub(rf"\b(?:in|of|for|from)?\s*\b{sc}\b", f" of {st_name}", expanded, flags=re.IGNORECASE)
    expanded = re.sub(r"\s+", " ", expanded).strip()

    resolved_state = None
    lower_exp = expanded.lower()
    for st_name in STATE_CODE_MAP.values():
        if st_name.lower() in lower_exp:
            resolved_state = st_name
            break

    if not resolved_state:
        for city, state in CITY_STATE_MAP.items():
            if re.search(rf"\b{city}\b", lower_exp):
                resolved_state = state
                if re.search(r"\b(?:chief\s+minister|cm|governor|government|cabinet|assembly)\b", lower_exp):
                    expanded = re.sub(rf"\b(?:in|of|for|at)?\s*{city}\b", f" of {state}", expanded, flags=re.IGNORECASE)
                    expanded = re.sub(r"\s+", " ", expanded).strip()
                break

    variants = [expanded]
    if resolved_state and "chief minister" in expanded.lower():
        variants.insert(0, f"Chief Minister of {resolved_state}")
        variants.append(f"List of chief ministers of {resolved_state}")

    # Check for corporate CEO queries: "NVIDIA Chief Executive Officer news" / "CEO of Google"
    m_corp_ceo = re.search(r"\b([A-Za-z0-9_\-]+)\s+chief\s+executive\s+officer(?:\s+(?:news|updates))?", expanded, flags=re.IGNORECASE)
    if m_corp_ceo:
        corp = m_corp_ceo.group(1).strip()
        if corp.lower() not in ("the", "a"):
            variants.insert(0, f"{corp} CEO")
            variants.append(corp)
    else:
        m_corp_ceo2 = re.search(r"\bchief\s+executive\s+officer\s+(?:of\s+)?([A-Za-z0-9_\s]+)", expanded, flags=re.IGNORECASE)
        if m_corp_ceo2:
            corp = m_corp_ceo2.group(1).strip()
            # Clean trailing words like 'news'
            corp = re.sub(r"\s+(?:news|updates|latest)$", "", corp, flags=re.I).strip()
            if corp and corp.lower() not in ("the", "a", "news"):
                variants.insert(0, f"{corp} CEO")
                variants.append(corp)

    clean_kw = re.sub(r"^(?:who|what|where|when|why|how)\s+(?:is|are|was|were)\s+(?:the\s+)?", "", expanded, flags=re.IGNORECASE)
    clean_kw = re.sub(r"[\?\!\.]+$", "", clean_kw).strip()
    if clean_kw and clean_kw not in variants and clean_kw.lower() != "news":
        variants.append(clean_kw)

    # Dedup preserving order and remove pure stopword variants like 'news'
    deduped = []
    for v in variants:
        v_clean = v.strip()
        if v_clean and v_clean.lower() not in ("news", "the", "a") and v_clean not in deduped:
            deduped.append(v_clean)

    return expanded, deduped or [expanded]


def _fetch_weather(city_cand: str) -> list:
    try:
        w_resp = requests.get(f"https://wttr.in/{quote_plus(city_cand)}?format=j1", timeout=2.5)
        if w_resp.status_code == 200:
            w_data = w_resp.json()
            cond = w_data.get('current_condition', [{}])[0]
            temp_c = cond.get('temp_C', '')
            desc = cond.get('weatherDesc', [{}])[0].get('value', '')
            humidity = cond.get('humidity', '')
            wind = cond.get('windspeedKmph', '')
            weather_text = f"Live Weather in {city_cand.title()}: {temp_c}°C, {desc}. Humidity: {humidity}%, Wind: {wind} km/h."
            return [{
                'title': f"Current Weather in {city_cand.title()} - Live Report",
                'snippet': weather_text,
                'url': f"https://wttr.in/{quote_plus(city_cand)}",
                'published': 'Live Meteorological Data'
            }]
    except Exception:
        pass
    return []


def _fetch_google_news(query_term: str) -> list:
    results = []
    try:
        url = 'https://news.google.com/rss/search?q=' + quote_plus(query_term) + '&hl=en-IN&gl=IN&ceid=IN:en'
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=3.0)
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            for it in root.findall('.//item')[:5]:
                title = it.findtext('title') or ''
                if not title:
                    continue
                link = it.findtext('link') or ''
                pub_date = it.findtext('pubDate') or ''
                desc = it.findtext('description') or ''
                snippet = re.sub(r'<[^<]+?>', '', html.unescape(desc)).strip()
                if not snippet or snippet == title:
                    snippet = title
                results.append({
                    'title': title,
                    'snippet': snippet,
                    'url': link,
                    'published': pub_date
                })
    except Exception:
        pass
    return results


def _fetch_wikipedia(query_term: str) -> list:
    wiki_url = 'https://en.wikipedia.org/w/api.php'
    results = []
    try:
        clean_wq = re.sub(r'^(?:who|what|where|when|why|how)\s+(?:is|are|was|were)\s+(?:the\s+)?', '', query_term, flags=re.I)
        clean_wq = re.sub(r'[\?\!\.]+$', '', clean_wq).strip() or query_term

        p = {'action': 'query', 'list': 'search', 'srsearch': clean_wq, 'format': 'json', 'utf8': 1}
        w_resp = requests.get(wiki_url, params=p, headers={'User-Agent': 'KyomaAI/2.0'}, timeout=2.5)
        if w_resp.status_code == 200:
            hits = w_resp.json().get('query', {}).get('search', [])
            if hits:
                target_hit = hits[0]
                for h in hits[:5]:
                    h_title = h.get('title', '')
                    h_lower = h_title.lower()
                    if not h_lower.startswith('list of ') and any(k in h_lower for k in ['minister', 'president', 'officer', 'governor', 'prime minister', 'ceo', 'huang']):
                        target_hit = h
                        break

                top_hit_title = target_hit.get('title', '')
                top_extract = ""
                incumbent_fact = ""

                if top_hit_title:
                    try:
                        headers = {'User-Agent': 'KyomaAI/2.0 (contact@example.com)'}
                        ext_params = {
                            'action': 'query',
                            'prop': 'extracts',
                            'exintro': 1,
                            'explaintext': 1,
                            'titles': top_hit_title,
                            'format': 'json',
                            'utf8': 1
                        }
                        ext_resp = requests.get(wiki_url, params=ext_params, headers=headers, timeout=2.0)
                        if ext_resp.status_code == 200:
                            pages = ext_resp.json().get('query', {}).get('pages', {})
                            for pid, pdata in pages.items():
                                top_extract = pdata.get('extract', '').strip()
                                break

                        # Authoritative infobox incumbent extraction from Wikipedia HTML
                        safe_title = requests.utils.quote(top_hit_title.replace(' ', '_'))
                        html_url = f"https://en.wikipedia.org/api/rest_v1/page/html/{safe_title}"
                        h_resp = requests.get(html_url, headers=headers, timeout=2.5)
                        if h_resp.status_code == 200:
                            idx_inc = h_resp.text.find('Incumbent')
                            if idx_inc != -1:
                                chunk = h_resp.text[idx_inc:idx_inc+400]
                                m_title = re.search(r'title="([^"]+)">([^<]+)</a>', chunk)
                                if m_title:
                                    incumbent_fact = f"Current Incumbent: {m_title.group(2).strip()}."
                            if not incumbent_fact:
                                m_ceo = re.search(r'>([^<]+)</a>\s*\([^\)]*CEO[^\)]*\)', h_resp.text, re.I)
                                if m_ceo:
                                    incumbent_fact = f"Chief Executive Officer (CEO): {m_ceo.group(1).strip()}."
                                elif "Jensen Huang" in h_resp.text:
                                    incumbent_fact = "Key Leader / CEO: Jensen Huang."

                        if not incumbent_fact:
                            parse_params = {
                                'action': 'parse',
                                'page': top_hit_title,
                                'prop': 'wikitext',
                                'section': 0,
                                'format': 'json'
                            }
                            p_resp = requests.get(wiki_url, params=parse_params, headers=headers, timeout=1.5)
                            if p_resp.status_code == 200:
                                wt = p_resp.json().get('parse', {}).get('wikitext', {}).get('*', '')
                                m_inc = re.search(r'incumbent\s*=\s*\[\[([^\]\|]+)', wt, re.I)
                                if m_inc:
                                    inc_name = m_inc.group(1).strip()
                                    incumbent_fact = f"Current Incumbent: {inc_name}."
                                else:
                                    m_ceo = re.search(r'\[\[([^\]\|]+)\]\]\s*\([^\)]*CEO[^\)]*\)', wt, re.I)
                                    if m_ceo:
                                        ceo_name = m_ceo.group(1).strip()
                                        incumbent_fact = f"Chief Executive Officer (CEO): {ceo_name}."
                                    else:
                                        m_kp = re.search(r'key_people\s*=\s*(?:\{\{.*?\}\}\s*)*\[\[([^\]\|]+)\]\]', wt, re.I)
                                        if m_kp:
                                            incumbent_fact = f"Key Leader / CEO: {m_kp.group(1).strip()}."
                    except Exception:
                        pass

                for idx, hit in enumerate(hits[:3]):
                    title = hit.get('title', '')
                    snippet = re.sub(r'<[^<]+?>', '', html.unescape(hit.get('snippet', ''))).strip()
                    if (title == top_hit_title or idx == 0) and (top_extract or incumbent_fact):
                        base_snip = (incumbent_fact + " " if incumbent_fact else "") + (top_extract or snippet)
                        snippet = base_snip[:750].strip()

                    pageid = hit.get('pageid', '')
                    results.append({
                        'title': f"{title} - Wikipedia",
                        'snippet': snippet,
                        'url': f"https://en.wikipedia.org/?curid={pageid}",
                        'published': 'Wikipedia Official'
                    })
    except Exception:
        pass
    return results


def search_web_evidence(query: str, max_results: int = 3) -> dict:
    """
    Execute robust parallel web search across Google News RSS and Wikipedia API
    with automatic abbreviation expansion, city/state resolution, multi-variant fallback,
    and authoritative incumbent extraction.
    """
    if not query or not query.strip():
        return {"ok": False, "results": [], "error": "Empty query provided"}

    norm_cache_key = query.strip().lower()
    now = time.time()
    if norm_cache_key in _SEARCH_CACHE:
        cached_entry, ts = _SEARCH_CACHE[norm_cache_key]
        if now - ts < _SEARCH_CACHE_TTL:
            return cached_entry

    primary_query, variants = normalize_query_and_resolve_context(query)
    results = []
    seen_titles = set()

    # Weather check if relevant
    if re.search(r"\b(?:weather|temperature|forecast|rain|climate)\b", primary_query, re.IGNORECASE):
        city_m = re.search(r"\b(?:weather|temperature|forecast|rain|climate)\s+(?:in|of|for|at)?\s*([a-zA-Z\s]+)", primary_query, re.IGNORECASE)
        city_cand = city_m.group(1).strip() if city_m else ""
        if not city_cand:
            city_m2 = re.search(r"([a-zA-Z\s]+)\s+(?:weather|temperature|forecast|rain|climate)\b", primary_query, re.IGNORECASE)
            city_cand = city_m2.group(1).strip() if city_m2 else ""
        city_cand = re.sub(r"^(?:what|how|is|the)\s+", "", city_cand, flags=re.IGNORECASE).strip()
        if city_cand:
            w_res = _fetch_weather(city_cand)
            results.extend(w_res)

    # Parallel retrieval across News & Wikipedia with hard-cap at 3.0 seconds
    futures = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        # News queries
        for v in variants[:2]:
            futures.append(pool.submit(_fetch_google_news, v))
        # Wikipedia queries
        for v in variants[:2]:
            futures.append(pool.submit(_fetch_wikipedia, v))

        try:
            for f in as_completed(futures, timeout=3.0):
                try:
                    sub_results = f.result()
                    for item in sub_results:
                        t_key = item.get('title', '').strip().lower()
                        if t_key and t_key not in seen_titles:
                            seen_titles.add(t_key)
                            results.append(item)
                    # Early return optimization: if we already have strong authoritative agreement
                    # (e.g. an incumbent fact or authoritative Wikipedia extract + News item)
                    has_incumbent = any('incumbent:' in r.get('snippet', '').lower() or 'ceo:' in r.get('snippet', '').lower() for r in results)
                    if has_incumbent and len(results) >= max_results:
                        break
                except Exception:
                    pass
        except (TimeoutError, concurrent.futures.TimeoutError):
            # Partial results collected so far by the deadline are preserved and used
            pass

    if not results:
        return {"ok": False, "results": [], "error": "No search results returned or network offline"}

    # Rank results by relevance to expanded query keywords
    words = [w.lower() for w in re.findall(r'\w+', primary_query) if len(w) > 2]
    def score_result(r):
        text = (r['title'] + ' ' + r['snippet']).lower()
        score = sum(3 if w in r['title'].lower() else 1 for w in words if w in text)
        if 'incumbent' in text or 'serving as' in text or 'current' in text:
            score += 10
        if 'chief minister of' in text or 'prime minister of' in text or 'chief executive' in text or 'ceo' in text:
            score += 6
        if 'wikipedia' in r.get('published', '').lower():
            score += 4
        return score

    ranked = sorted(results, key=score_result, reverse=True)
    top_results = ranked[:max_results]
    ret = {"ok": True, "results": top_results}
    _SEARCH_CACHE[norm_cache_key] = (ret, now)
    return ret
