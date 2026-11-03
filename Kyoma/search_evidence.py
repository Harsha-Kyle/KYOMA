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
        
    cleaned_query = query.strip()
    results = []
    
    # 1. Source: Google News RSS for breaking news, current events, official appointments
    try:
        url = 'https://news.google.com/rss/search?q=' + quote_plus(cleaned_query) + '&hl=en-IN&gl=IN&ceid=IN:en'
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=4)
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
        w_resp = requests.get(wiki_url, params=p, headers={'User-Agent': 'KyomaAI/2.0'}, timeout=4)
        if w_resp.status_code == 200:
            hits = w_resp.json().get('query', {}).get('search', [])
            for hit in hits[:3]:
                title = hit.get('title', '')
                snippet = re.sub(r'<[^<]+?>', '', html.unescape(hit.get('snippet', ''))).strip()
                pageid = hit.get('pageid', '')
                
                # Fetch wikitext revision to extract official incumbent if applicable
                try:
                    rev_resp = requests.get(wiki_url, params={
                        'action': 'query', 'prop': 'revisions', 'pageids': str(pageid),
                        'rvslots': '*', 'rvprop': 'content', 'format': 'json'
                    }, headers={'User-Agent': 'KyomaAI/2.0'}, timeout=3)
                    if rev_resp.status_code == 200:
                        text_content = rev_resp.text
                        m = re.search(r'incumbent\s*=\s*\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', text_content)
                        if m:
                            snippet = f"Incumbent / Current Officeholder: {m.group(1)}. " + snippet
                except Exception:
                    pass
                    
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
        if 'incumbent' in text:
            score += 6
        if 'wikipedia' in r['published'].lower():
            score += 2
        return score

    ranked = sorted(results, key=score_result, reverse=True)
    
    # Return exactly top 3 results
    top_3 = ranked[:max_results]
    return {"ok": True, "results": top_3}
