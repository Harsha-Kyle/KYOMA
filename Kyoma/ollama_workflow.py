import time
import re
import asyncio
import concurrent.futures
import socket
import ollama
from demo_safety import is_demo_mode_active, check_demo_mode_refusal
from search_evidence import search_web_evidence

# ─────────────────────────────────────────────────────────────────────────────
# Search intent detection
# ─────────────────────────────────────────────────────────────────────────────

# Narrow, high-precision patterns for clear search intent.
# These must NOT match ordinary conversation or fast-router commands.
# Ambiguous queries fall through to the LLM tool-selection path unchanged.
_SEARCH_INTENT_PATTERNS = [
    # Explicit "who is / who was" factual look-ups
    re.compile(r"^\bwho\s+(?:is|was|are|were)\b", re.IGNORECASE),
    # "What is the current X" / "what's the current X" / "current X of Y"
    re.compile(r"\b(?:what(?:'s|\s+is)\s+the\s+current|current\s+(?:prime\s+minister|president|ceo|status|leader|news))\b", re.IGNORECASE),
    # Explicit search commands
    re.compile(r"\b(?:search\s+for|look\s+up|look\s+it\s+up|google\s+(?:it|for))\b", re.IGNORECASE),
    # "latest X" / "recent X" / "news about X" — factual time-sensitive
    re.compile(r"\b(?:latest|recent|news\s+about|current\s+news)\b", re.IGNORECASE),
    # "what happened to/with" — news-type query
    re.compile(r"\bwhat\s+happened\s+(?:to|with)\b", re.IGNORECASE),
    # "find out X"
    re.compile(r"\bfind\s+out\b", re.IGNORECASE),
    # "tell me about X" followed by a named entity (person/place/thing) — only when clearly factual
    re.compile(r"\btell\s+me\s+about\s+\w[\w\s]{2,30}$", re.IGNORECASE),
]

# Guard: phrases that look like search intent but are really fast-router commands.
# If any guard matches, return False (let fast_router handle it).
_SEARCH_GUARD_PATTERNS = [
    re.compile(r"\b(?:open|launch|go\s+to|browse|navigate)\b", re.IGNORECASE),
    re.compile(r"\b(?:play|pause|skip|next|previous|restart)\b", re.IGNORECASE),
    re.compile(r"\b(?:volume|brightness|screenshot|lock|mute|unmute)\b", re.IGNORECASE),
    re.compile(r"\b(?:time|date|battery|network|wifi|disk|cpu|ram|vpn)\b", re.IGNORECASE),
    re.compile(r"\b(?:reminder|alarm|birthday|schedule|app)\b", re.IGNORECASE),
    # "who is on the phone / who is calling" — not a web search
    re.compile(r"\bwho\s+is\s+(?:calling|on\s+the\s+phone|there|that)\b", re.IGNORECASE),
]


def is_search_query(text: str) -> bool:
    """
    Return True if the query has clear, unambiguous web-search intent.
    Returns False for ordinary conversation, fast-router commands, or anything ambiguous.

    Design rules:
    - Only match when at least one HIGH-CONFIDENCE pattern fires.
    - Always check guard patterns first to avoid misrouting commands.
    - Err on the side of False (fall through to LLM tool-selection) when unsure.
    """
    if not text or len(text.strip()) < 5:
        return False
    t = text.strip()

    # Guard: if looks like a fast-router command, do not mark as search
    for guard in _SEARCH_GUARD_PATTERNS:
        if guard.search(t):
            return False

    # Intent: at least one high-confidence pattern must match
    for pat in _SEARCH_INTENT_PATTERNS:
        if pat.search(t):
            return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
# Connectivity check
# ─────────────────────────────────────────────────────────────────────────────

def _check_connectivity(timeout: float = 1.0) -> bool:
    """Fast TCP-level check: can we reach Google DNS?  Takes ≤ timeout seconds."""
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except Exception:
        return False


def select_relevant_tools(user_text, tools_dict):
    text = (user_text or "").lower()
    selected = set()

    # Web search
    if any(w in text for w in ['search', 'google', 'who is', 'who was', 'what is the current', 'latest', 'news', 'find out', 'look up']):
        if 'web_search' in tools_dict: selected.add(tools_dict['web_search'])
        if 'open_browser' in tools_dict: selected.add(tools_dict['open_browser'])

    # Time / Date
    if any(w in text for w in ['time', 'date', 'day', 'clock', 'today']):
        if 'get_time' in tools_dict: selected.add(tools_dict['get_time'])
        if 'get_date' in tools_dict: selected.add(tools_dict['get_date'])

    # Battery / Power
    if any(w in text for w in ['battery', 'charge', 'charging', 'power', 'plugged']):
        if 'get_battery' in tools_dict: selected.add(tools_dict['get_battery'])
        if 'get_power_status' in tools_dict: selected.add(tools_dict['get_power_status'])

    # Volume / Audio
    if any(w in text for w in ['volume', 'mute', 'unmute', 'sound', 'audio', 'loud', 'quiet']):
        for k in ['set_volume', 'change_volume', 'mute_volume', 'unmute_volume', 'get_volume']:
            if k in tools_dict: selected.add(tools_dict[k])

    # Brightness / Screen / Lock
    if any(w in text for w in ['bright', 'dim', 'display', 'screen', 'lock']):
        for k in ['set_brightness', 'get_brightness', 'brightness_up', 'brightness_down', 'lock_screen']:
            if k in tools_dict: selected.add(tools_dict[k])

    # Media
    if any(w in text for w in ['play', 'pause', 'track', 'song', 'music', 'skip']):
        for k in ['play_pause', 'next_track', 'previous_track', 'startfrombegin_track']:
            if k in tools_dict: selected.add(tools_dict[k])

    # Reminders
    if any(w in text for w in ['remind', 'reminder', 'alarm', 'birthday', 'schedule']):
        for k in ['add_reminder', 'list_active_reminders', 'reminder_details', 'cancel_reminder_by_title', 'add_birthday_reminder', 'list_birthday_reminders', 'delete_birthday_reminder']:
            if k in tools_dict: selected.add(tools_dict[k])

    # Screenshot
    if any(w in text for w in ['screenshot', 'capture', 'screen shot', 'snapshot']):
        if 'take_screenshot_save' in tools_dict: selected.add(tools_dict['take_screenshot_save'])

    # Apps
    if any(w in text for w in ['open', 'launch', 'close', 'minimize', 'maximize', 'restore', 'start', 'app', 'notepad', 'calc', 'chrome']):
        for k in ['open_application', 'close_application', 'minimize_application', 'restore_application', 'open_browser']:
            if k in tools_dict: selected.add(tools_dict[k])

    # System / Performance
    if any(w in text for w in ['cpu', 'ram', 'memory', 'disk', 'storage', 'system', 'network', 'wifi', 'vpn', 'spec', 'performance']):
        for k in ['get_time', 'get_date', 'get_battery', 'get_power_status', 'get_network_status', 'get_vpn_status', 'get_performance', 'get_system_info']:
            if k in tools_dict: selected.add(tools_dict[k])

    if not selected:
        for k in ['web_search', 'get_time', 'get_battery', 'open_application', 'set_volume', 'take_screenshot_save']:
            if k in tools_dict: selected.add(tools_dict[k])

    return list(selected)[:8]

def execute_ollama_workflow(user_text, model_name, memory, available_tools_list, timeout_seconds=10.0,
                            pre_search_callback=None):
    """
    Execute the Kyoma Ollama tool-calling workflow.

    Args:
        user_text:             The user's transcribed utterance.
        model_name:            Ollama model to call (e.g. "gemma4:e2b").
        memory:                MemoryManager instance for conversation history.
        available_tools_list:  List of callable tool functions exposed to Ollama.
        timeout_seconds:       Per-call Ollama timeout (default 10 s).
        pre_search_callback:   Optional no-arg callable invoked synchronously just
                               before the web search executes (e.g. to broadcast
                               "thinking" state).  Exceptions are swallowed.

    Search fast-path:
        When is_search_query() detects clear search intent the function:
        1. Runs a 1-second TCP connectivity check.
        2. If offline: returns an offline spoken response immediately.
        3. Calls search_web_evidence() in a ThreadPoolExecutor with a hard
           15-second overall timeout so the event loop / WebSocket / ESP32
           remain responsive.
        4. Passes the original question + top-3 results to a single Gemma call
           (no second LLM summarisation pass).
        5. Results are never cached/reused between requests.
    """
    t_start = time.perf_counter()
    memory.add_user_message(user_text)

    system_prompt = (
        "You are KYOMA, a physical AI desktop companion. "
        "Always call an appropriate tool for PC automation or search tasks. "
        "Answer directly, concisely, and speak naturally."
    )

    # ── Direct search fast-path ───────────────────────────────────────────────
    if is_search_query(user_text):
        t_search_start = time.perf_counter()
        print(f"[KYOMA_SEARCH] Direct search path for: {user_text!r}")

        # 1. Connectivity pre-check (1 second max)
        if not _check_connectivity(timeout=1.0):
            offline_msg = "I can't look that up right now; I'm offline."
            memory.add_assistant_message(text=offline_msg)
            print(f"[KYOMA_SEARCH] Offline — returning immediately in {time.perf_counter()-t_start:.2f}s")
            return {"ok": True, "text": offline_msg}

        # 2. Fire pre-search callback (e.g. speak "Let me look that up")
        if pre_search_callback:
            try:
                pre_search_callback()
            except Exception as _cb_err:
                print(f"[KYOMA_SEARCH] pre_search_callback error (ignored): {_cb_err}")

        # 3. Execute search in a thread with hard 6.0-second timeout
        search_result = None
        try:
            _executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                _future = _executor.submit(search_web_evidence, user_text.strip(), 3)
                search_result = _future.result(timeout=6.0)
            except concurrent.futures.TimeoutError:
                print("[KYOMA_SEARCH] Search timed out after 6.0s")
                search_result = None
            except Exception as _se:
                print(f"[KYOMA_SEARCH] Search exception: {_se}")
                search_result = None
            finally:
                _executor.shutdown(wait=False, cancel_futures=True)
        except Exception as _pool_err:
            print(f"[KYOMA_SEARCH] ThreadPool error: {_pool_err}")

        t_search_wall = time.perf_counter() - t_search_start
        print(f"[KYOMA_TIMING] SEARCH_DIRECT | wall={t_search_wall:.3f}s")

        # 4. Build evidence string (top 3 only, never cached)
        if search_result and search_result.get("ok") and search_result.get("results"):
            evidence_items = search_result["results"][:3]
            lines = []
            for idx, item in enumerate(evidence_items):
                lines.append(
                    f"Result {idx+1}:\n"
                    f"Title: {item.get('title', '')}\n"
                    f"Snippet: {item.get('snippet', '')}\n"
                    f"Date: {item.get('published', '')}\n"
                    f"URL: {item.get('url', '')}"
                )
            search_evidence_context = "\n\n".join(lines)
        else:
            # Mid-search disconnect / no results — give honest fallback
            fallback_msg = "I searched but couldn't find reliable results right now. Try again in a moment."
            memory.add_assistant_message(text=fallback_msg)
            print(f"[KYOMA_SEARCH] No usable results — returning fallback in {time.perf_counter()-t_start:.2f}s")
            return {"ok": True, "text": fallback_msg}

        # 5. Single Gemma call: question + top-3 evidence
        search_prompt = (
            f"User Question: {user_text}\n\n"
            f"Search Evidence (Top 3 Results):\n{search_evidence_context}\n\n"
            "Please answer the question directly in 1-2 concise spoken sentences based strictly "
            "on the search evidence. If the evidence is conflicting or insufficient, communicate "
            "uncertainty instead of inventing an answer."
        )
        try:
            t_llm_start = time.perf_counter()
            resp_search = ollama.chat(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are KYOMA. Answer directly and concisely from the provided search evidence without guessing."},
                    {"role": "user", "content": search_prompt}
                ],
                keep_alive="1h",
                think=False,
                options={"temperature": 0.2, "num_predict": 80}
            )
            t_llm_wall = time.perf_counter() - t_llm_start
            final_text = resp_search["message"].get("content", "").strip()
            try:
                c_total = (getattr(resp_search, "total_duration", None) or 0) / 1e9
                c_eval_tok = getattr(resp_search, "eval_count", None) or 0
                print(f"[KYOMA_TIMING] SEARCH_LLM | wall={t_llm_wall:.3f}s | total={c_total:.3f}s | eval_tok={c_eval_tok}")
            except Exception:
                pass
        except Exception as _llm_err:
            print(f"[KYOMA_SEARCH] LLM call failed: {_llm_err}")
            final_text = ""

        if not final_text:
            # Last resort: return raw snippet from top result
            top = evidence_items[0] if evidence_items else {}
            final_text = top.get("snippet", "I found some results but couldn't summarise them.")

        memory.add_assistant_message(text=final_text)
        t_e2e = time.perf_counter() - t_start
        print(f"[KYOMA_TIMING] E2E_REQUEST | wall={t_e2e:.3f}s | path=search_direct")
        return {"ok": True, "text": final_text}

    # ── Standard tool-calling path (unchanged) ────────────────────────────────
    tools_dict = {fn.__name__: fn for fn in available_tools_list}
    active_tools = select_relevant_tools(user_text, tools_dict)

    # 1. First round Ollama call
    try:
        t_call1_start = time.perf_counter()
        resp = ollama.chat(
            model=model_name,
            messages=memory.get_messages(system_prompt=system_prompt),
            tools=active_tools,
            keep_alive="1h",
            think=False,
            options={"temperature": 0.2, "num_predict": 80}
        )
        t_call1_wall = time.perf_counter() - t_call1_start
    except Exception as tool_err:
        err_str = str(tool_err).lower()
        if "does not support tools" in err_str or "400" in err_str:
            t_call1_start = time.perf_counter()
            resp = ollama.chat(
                model=model_name,
                messages=memory.get_messages(system_prompt=system_prompt),
                keep_alive="1h",
                think=False,
                options={"temperature": 0.2, "num_predict": 80}
            )
            t_call1_wall = time.perf_counter() - t_call1_start
        else:
            raise tool_err

    msg = resp["message"]

    # Metrics logging
    try:
        c1_total_s = (resp.get("total_duration") or 0) / 1e9
        c1_load_s = (resp.get("load_duration") or 0) / 1e9
        c1_prompt_s = (resp.get("prompt_eval_duration") or 0) / 1e9
        c1_prompt_tok = resp.get("prompt_eval_count") or 0
        c1_eval_s = (resp.get("eval_duration") or 0) / 1e9
        c1_eval_tok = resp.get("eval_count") or 0
        c1_has_thinking = bool(msg.get("thinking"))
        print(f"[KYOMA_TIMING] CALL_1 | wall={t_call1_wall:.3f}s | total={c1_total_s:.3f}s | load={c1_load_s:.3f}s | prompt_eval={c1_prompt_s:.3f}s ({c1_prompt_tok}tok) | eval={c1_eval_s:.3f}s ({c1_eval_tok}tok) | thinking_present={c1_has_thinking}")
    except Exception as timing_ex:
        pass

    if msg.get("tool_calls"):
        memory.add_assistant_message(tool_calls=msg["tool_calls"])
        t_tools_start = time.perf_counter()

        executed_results = []
        has_search_evidence = False
        search_evidence_context = ""

        for tool_call in msg["tool_calls"]:
            func_name = tool_call["function"]["name"]
            args = tool_call["function"]["arguments"]
            print(f"Tool called: {func_name}({args})")

            # Demo mode safety refusal
            is_refused, refusal_msg = check_demo_mode_refusal(func_name, args)
            if is_refused:
                print(f"Demo Mode refusal applied for {func_name}")
                memory.add_tool_message(text=refusal_msg, name=func_name)
                executed_results.append((func_name, refusal_msg, True))
                # Prune refused command context to prevent subsequent turns from inheriting refused arguments
                if hasattr(memory, "history") and len(memory.history) > 1:
                    # Clear the immediately preceding user message from history so future tool calls cannot hallucinate its parameters
                    memory.history = [m for m in memory.history if m.get("content") != user_text]
                continue

            fn = tools_dict.get(func_name)
            if fn is None:
                err_msg = f"I am unable to perform {func_name.replace('_', ' ')}."
                memory.add_tool_message(text=err_msg, name=func_name)
                executed_results.append((func_name, err_msg, True))
                continue

            try:
                res = fn(**args)
                if isinstance(res, dict) and res.get("is_search_evidence"):
                    has_search_evidence = True
                    evidence_items = res.get("evidence", [])
                    if evidence_items:
                        lines = []
                        for idx, item in enumerate(evidence_items):
                            lines.append(f"Result {idx+1}:\nTitle: {item.get('title', '')}\nSnippet: {item.get('snippet', '')}\nDate: {item.get('published', '')}\nURL: {item.get('url', '')}")
                        search_evidence_context = "\n\n".join(lines)
                        raw_tool_text = "Retrieved search evidence:\n" + search_evidence_context
                    else:
                        search_evidence_context = "No search results found or internet connection is offline."
                        raw_tool_text = search_evidence_context
                    memory.add_tool_message(text=raw_tool_text, name=func_name)
                    executed_results.append((func_name, raw_tool_text, False))
                else:
                    if isinstance(res, dict):
                        spoken_clean = res.get("out") or res.get("text") or res.get("error") or str(res)
                    else:
                        spoken_clean = str(res)
                    memory.add_tool_message(text=spoken_clean, name=func_name)
                    executed_results.append((func_name, spoken_clean, True))
            except Exception as ex:
                fail_msg = f"Operation failed: {ex}"
                memory.add_tool_message(text=fail_msg, name=func_name)
                executed_results.append((func_name, fail_msg, True))

        t_tools_wall = time.perf_counter() - t_tools_start
        print(f"[KYOMA_TIMING] TOOL_EXEC | wall={t_tools_wall:.3f}s | count={len(msg['tool_calls'])}")

        # Optimization: Skip 2nd LLM call for clean user-readable tool results
        if not has_search_evidence and executed_results:
            all_clean = all(is_clean for _, _, is_clean in executed_results)
            if all_clean:
                clean_texts = []
                for fname, dtext, _ in executed_results:
                    txt = str(dtext).strip()
                    if txt.startswith("{") and "out" in txt:
                        txt = re.sub(r'^[^{]*\{.*?out[\'": ]+', '', txt).strip(" }'\"")
                    if txt:
                        clean_texts.append(txt)
                if clean_texts:
                    combined_spoken = " and ".join(clean_texts)
                    memory.add_assistant_message(text=combined_spoken)
                    t_total_e2e = time.perf_counter() - t_start
                    print(f"[KYOMA_TIMING] MULTI_TOOL_SHORTCUT | wall={t_total_e2e:.3f}s | count={len(executed_results)}")
                    print(f"[KYOMA_TIMING] E2E_REQUEST | wall={t_total_e2e:.3f}s | path=multi_tool_shortcut")
                    return {"ok": True, "text": combined_spoken}

        # Second round: for search interpretation or multi-step results
        try:
            t_call2_start = time.perf_counter()
            if has_search_evidence:
                search_prompt = (
                    f"User Question: {user_text}\n\n"
                    f"Search Evidence (Top 3 Results):\n{search_evidence_context}\n\n"
                    "Please answer the question directly in 1-2 concise spoken sentences based strictly on the search evidence. "
                    "If the evidence is conflicting or insufficient, communicate uncertainty instead of inventing an answer."
                )
                resp2 = ollama.chat(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are KYOMA. Answer directly and concisely from the provided search evidence without guessing."},
                        {"role": "user", "content": search_prompt}
                    ],
                    keep_alive="1h",
                    think=False,
                    options={"temperature": 0.2, "num_predict": 80}
                )
            else:
                resp2 = ollama.chat(
                    model=model_name,
                    messages=memory.get_messages(system_prompt=system_prompt),
                    keep_alive="1h",
                    think=False,
                    options={"temperature": 0.2, "num_predict": 80}
                )
            t_call2_wall = time.perf_counter() - t_call2_start
            final_text = resp2["message"].get("content", "")

            try:
                c2_total_s = (resp2.get("total_duration") or 0) / 1e9
                c2_load_s = (resp2.get("load_duration") or 0) / 1e9
                c2_prompt_s = (resp2.get("prompt_eval_duration") or 0) / 1e9
                c2_prompt_tok = resp2.get("prompt_eval_count") or 0
                c2_eval_s = (resp2.get("eval_duration") or 0) / 1e9
                c2_eval_tok = resp2.get("eval_count") or 0
                c2_msg = resp2["message"]
                c2_has_thinking = bool(c2_msg.get("thinking"))
                print(f"[KYOMA_TIMING] CALL_2 | wall={t_call2_wall:.3f}s | total={c2_total_s:.3f}s | load={c2_load_s:.3f}s | prompt_eval={c2_prompt_s:.3f}s ({c2_prompt_tok}tok) | eval={c2_eval_s:.3f}s ({c2_eval_tok}tok) | thinking_present={c2_has_thinking}")
            except Exception as timing_ex2:
                pass
        except Exception as chat_err:
            print(f"⚠️ Second-round chat failed: {chat_err}")
            final_text = ""

        # Fallback if 2nd LLM call returned empty or a generic greeting
        greetings = ("hello", "hi!", "how can i assist", "how may i assist", "i am kyoma")
        is_generic_greeting = any(final_text.lower().startswith(g) for g in greetings)
        if not final_text or not final_text.strip() or is_generic_greeting:
            if executed_results:
                clean_fallbacks = []
                for _, rtxt, _ in executed_results:
                    c = str(rtxt).strip()
                    if c.startswith("{") and "out" in c:
                        c = re.sub(r'^[^{]*\{.*?out[\'": ]+', '', c).strip(" }'\"")
                    if c:
                        clean_fallbacks.append(c)
                if clean_fallbacks:
                    final_text = " and ".join(clean_fallbacks)
                else:
                    final_text = executed_results[0][1]
            else:
                final_text = "I have performed the requested task."

        memory.add_assistant_message(text=final_text)
        t_total_e2e = time.perf_counter() - t_start
        print(f"[KYOMA_TIMING] E2E_REQUEST | wall={t_total_e2e:.3f}s | path=tool_calling")
        return {"ok": True, "text": final_text}

    else:
        text = msg.get("content", "")
        memory.add_assistant_message(text=text)
        t_total_e2e = time.perf_counter() - t_start
        print(f"[KYOMA_TIMING] E2E_REQUEST | wall={t_total_e2e:.3f}s | path=text_only")
        return {"ok": True, "text": text}
