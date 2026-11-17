import os
import sys
import re
import html
import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

def search_web_evidence(query: str, max_results: int = 3) -> dict:
    """
    Execute web search across Google News RSS (current news/articles) and
    Wikipedia API (authoritative reference facts/incumbents).
    Ranks results by relevance to the query and returns exactly top 3 results.
    Each result contains title, snippet, url, and publication date.
    Never reuses stale search results.
    """
    if not query or not query.strip():
        return {"ok": False, "results": [], "error": "Empty query provided"}

    raw_query = query.strip()
    # Normalize common acronyms in queries for better search hit rates
    normalized_query = re.sub(r"\bPM\b", "Prime Minister", raw_query)
    normalized_query = re.sub(r"\bCM\b", "Chief Minister", normalized_query)
    cleaned_query = normalized_query.strip()
    results = []

    # 1. Source: Google News RSS for breaking news, current events, official appointments
    try:
        url = 'https://news.google.com/rss/search?q=' + quote_plus(cleaned_query) + '&hl=en-IN&gl=IN&ceid=IN:en'
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=3.5)
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            for it in root.findall('.//item'):
                title = it.findtext('title') or ''
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
                if len(results) >= 6:
                    break
    except Exception:
        pass

    # 2. Source: Wikipedia API for authoritative definitions, current officeholders & profiles
    try:
        wiki_url = 'https://en.wikipedia.org/w/api.php'
        p = {'action': 'query', 'list': 'search', 'srsearch': cleaned_query, 'format': 'json', 'utf8': 1}
        w_resp = requests.get(wiki_url, params=p, headers={'User-Agent': 'KyomaAI/2.0'}, timeout=3.5)
        if w_resp.status_code == 200:
            hits = w_resp.json().get('query', {}).get('search', [])
            top_hit_title = hits[0].get('title', '') if hits else ''
            
            # Retrieve page extract and infobox incumbent for top hit if available
            top_extract = ""
            incumbent_fact = ""
            if top_hit_title:
                try:
                    ext_params = {
                        'action': 'query',
                        'prop': 'extracts',
                        'exintro': 1,
                        'explaintext': 1,
                        'titles': top_hit_title,
                        'format': 'json',
                        'utf8': 1
                    }
                    ext_resp = requests.get(wiki_url, params=ext_params, headers={'User-Agent': 'KyomaAI/2.0'}, timeout=2.5)
                    if ext_resp.status_code == 200:
                        pages = ext_resp.json().get('query', {}).get('pages', {})
                        for pid, pdata in pages.items():
                            top_extract = pdata.get('extract', '').strip()
                            break
                    
                    # Also parse lead section wikitext for official infobox incumbent
                    parse_params = {
                        'action': 'parse',
                        'page': top_hit_title,
                        'prop': 'wikitext',
                        'section': 0,
                        'format': 'json'
                    }
                    p_resp = requests.get(wiki_url, params=parse_params, headers={'User-Agent': 'KyomaAI/2.0'}, timeout=2.0)
                    if p_resp.status_code == 200:
                        wt = p_resp.json().get('parse', {}).get('wikitext', {}).get('*', '')
                        m_inc = re.search(r'incumbent\s*=\s*\[\[([^\]\|]+)', wt, re.I)
                        if m_inc:
                            inc_name = m_inc.group(1).strip()
                            incumbent_fact = f"Current Incumbent: {inc_name}."
                except Exception:
                    pass

            for idx, hit in enumerate(hits[:3]):
                title = hit.get('title', '')
                snippet = re.sub(r'<[^<]+?>', '', html.unescape(hit.get('snippet', ''))).strip()
                if idx == 0 and (top_extract or incumbent_fact):
                    # Enrich snippet with extract and verified incumbent for the #1 authoritative match
                    base_snip = (incumbent_fact + " " if incumbent_fact else "") + (top_extract or snippet)
                    snippet = base_snip[:450].strip()
                pageid = hit.get('pageid', '')
                results.append({
                    'title': f"{title} - Wikipedia",
                    'snippet': snippet,
                    'url': f"https://en.wikipedia.org/?curid={pageid}",
                    'published': 'Wikipedia Official'
                })
    except Exception:
        pass

    if not results:
        return {"ok": False, "results": [], "error": "No search results returned or network offline"}

    # Rank results by query relevance
    words = [w.lower() for w in re.findall(r'\w+', cleaned_query) if len(w) > 2]
    def score_result(r):
        text = (r['title'] + ' ' + r['snippet']).lower()
        score = sum(3 if w in r['title'].lower() else 1 for w in words if w in text)
        if 'incumbent' in text or 'serving as' in text or 'current' in text:
            score += 8
        if 'prime minister of india' in text or 'chief minister of' in text:
            score += 5
        if 'wikipedia' in r['published'].lower():
            score += 3
        return score

    ranked = sorted(results, key=score_result, reverse=True)
    top_3 = ranked[:max_results]
    return {"ok": True, "results": top_3}
