import os, sys
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, Image
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import Flowable

# ── Palette ───────────────────────────────────────────────────────────────────
DARK_BLUE   = colors.HexColor("#1A237E")
ACCENT_BLUE = colors.HexColor("#3949AB")
TEAL        = colors.HexColor("#00897B")
WHITE       = colors.white
GREY_TEXT   = colors.HexColor("#37474F")
LIGHT_GREY  = colors.HexColor("#ECEFF1")
LIGHT_BLUE  = colors.HexColor("#E8EAF6")

PAGE_W, PAGE_H = A4
MARGIN = 1.8 * cm
CONTENT_W = PAGE_W - 2 * MARGIN

# ── Styles ────────────────────────────────────────────────────────────────────
def S():
    s = {}
    s["h1"] = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=22,
                              textColor=WHITE, alignment=TA_CENTER, leading=28, spaceAfter=6)
    s["h2"] = ParagraphStyle("h2", fontName="Helvetica", fontSize=13,
                              textColor=colors.HexColor("#C5CAE9"), alignment=TA_CENTER, leading=18, spaceAfter=4)
    s["cover_info"] = ParagraphStyle("ci", fontName="Helvetica", fontSize=11,
                                     textColor=WHITE, alignment=TA_CENTER, leading=16, spaceAfter=3)
    s["sub"] = ParagraphStyle("sub", fontName="Helvetica-Bold", fontSize=12,
                               textColor=DARK_BLUE, spaceBefore=10, spaceAfter=4, leading=16)
    s["body"] = ParagraphStyle("body", fontName="Helvetica", fontSize=10.5,
                                textColor=GREY_TEXT, alignment=TA_JUSTIFY, spaceAfter=6, leading=16)
    s["bullet"] = ParagraphStyle("bul", fontName="Helvetica", fontSize=10.5,
                                  textColor=GREY_TEXT, leftIndent=14, spaceAfter=4, leading=15)
    s["caption"] = ParagraphStyle("cap", fontName="Helvetica-Oblique", fontSize=9,
                                   textColor=colors.HexColor("#546E7A"),
                                   alignment=TA_CENTER, spaceBefore=3, spaceAfter=8)
    s["th"] = ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=10,
                              textColor=WHITE, alignment=TA_CENTER)
    s["tc"] = ParagraphStyle("tc", fontName="Helvetica", fontSize=10, textColor=GREY_TEXT, leading=14)
    s["tc_bold"] = ParagraphStyle("tcb", fontName="Helvetica-Bold", fontSize=10, textColor=GREY_TEXT, leading=14)
    s["footer"] = ParagraphStyle("ft", fontName="Helvetica", fontSize=8,
                                  textColor=colors.HexColor("#90A4AE"), alignment=TA_CENTER)
    return s


# ── Coloured section banner ───────────────────────────────────────────────────
class Banner(Flowable):
    def __init__(self, number, title, width):
        super().__init__()
        self.number = number; self.title = title
        self.width = width;   self.height = 28

    def draw(self):
        c = self.canv
        c.setFillColor(DARK_BLUE)
        c.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        c.setFillColor(TEAL)
        c.rect(0, 0, 6, self.height, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 12)
        label = f"{self.number}.  {self.title}" if self.number else self.title
        c.drawString(14, 8, label)


# ── Helpers ───────────────────────────────────────────────────────────────────
def sp(h=0.3):  return Spacer(1, h * cm)
def hr():       return HRFlowable(width="100%", thickness=0.5,
                                   color=colors.HexColor("#CFD8DC"), spaceAfter=4)
def bul(text, styles):
    return Paragraph(f"\u2022 \u00a0 {text}", styles["bullet"])

def img_block(path, caption, styles, max_w=13*cm, max_h=8*cm):
    if not path or not os.path.exists(path):
        return []
    im = Image(path)
    scale = min(max_w / im.imageWidth, max_h / im.imageHeight, 1.0)
    im.drawWidth  = im.imageWidth  * scale
    im.drawHeight = im.imageHeight * scale
    im.hAlign = "CENTER"
    return [im, Paragraph(caption, styles["caption"])]

def later_pages(canvas, doc):
    """Simple header/footer on pages."""
    canvas.saveState()
    # Draw header bar
    canvas.setFillColor(DARK_BLUE)
    canvas.rect(0, PAGE_H - 1*cm, PAGE_W, 1*cm, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(MARGIN, PAGE_H - 0.65*cm, "KYOMA — Capstone Project Report")
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 0.65*cm,
                           "Saveetha Institute of Medical and Technical Sciences")
    # Footer
    canvas.setFillColor(colors.HexColor("#90A4AE"))
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(PAGE_W / 2, 0.5*cm, f"Page {doc.page}")
    canvas.restoreState()


# ── Main ──────────────────────────────────────────────────────────────────────
def build(output, images):
    doc = SimpleDocTemplate(output, pagesize=A4,
                            leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=MARGIN + 0.4*cm, bottomMargin=MARGIN,
                            title="KYOMA Capstone Project Report",
                            author="Saveetha SIMATS")
    ST = S()
    story = []

    # ─── SECTION 1 — TITLE ────────────────────────────────────────────────────
    story.append(Banner("1", "TITLE OF THE PROJECT", CONTENT_W))
    story.append(sp(0.3))
    tbox = Table([[Paragraph(
        "KYOMA: A Local AI-Enabled Interactive Desktop Companion<br/>"
        "for Intelligent Computer Automation",
        ParagraphStyle("tb", fontName="Helvetica-Bold", fontSize=14,
                       textColor=DARK_BLUE, alignment=TA_CENTER, leading=20)
    )]], colWidths=[CONTENT_W])
    tbox.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), LIGHT_BLUE),
        ("BOX",           (0,0), (-1,-1), 1.5, ACCENT_BLUE),
        ("TOPPADDING",    (0,0), (-1,-1), 14),
        ("BOTTOMPADDING", (0,0), (-1,-1), 14),
    ]))
    story.append(tbox)
    story.append(sp(0.5))

    # ─── SECTION 2 — ABSTRACT ─────────────────────────────────────────────────
    story.append(Banner("2", "ABSTRACT", CONTENT_W))
    story.append(sp(0.3))
    story.append(Paragraph(
        "KYOMA is a local AI-enabled physical desktop companion and personal butler designed to assist "
        "users in controlling and interacting with a computer through natural-language voice commands. "
        "The system integrates an ESP32/ESP32-S3 microcontroller, a 128×64 OLED visual status display, "
        "an I2S MEMS microphone for voice capture, and a MAX98357A I2S audio amplifier with a speaker for "
        "audio responses — all housed in a custom physical enclosure placed on the user's desktop.",
        ST["body"]
    ))
    story.append(Paragraph(
        "On the host computer side, a local AI processing engine powered by Ollama (running Mistral or "
        "Llama3) receives the captured voice input, performs speech-to-text conversion, detects the user's "
        "intent through natural-language understanding, and selects an appropriate predefined automation "
        "function using structured tool/function calling. A Python-based computer automation subsystem "
        "then executes the requested operation — such as opening or closing applications, controlling "
        "system volume or display brightness, managing media playback, setting reminders, or taking "
        "screenshots. The execution result is communicated back to the KYOMA device, which updates the "
        "OLED display to show the corresponding visual state (listening, thinking, success, error) and "
        "plays an audio response through the speaker.",
        ST["body"]
    ))
    story.append(Paragraph(
        "The system operates primarily offline, reducing cloud dependency and preserving user privacy. "
        "KYOMA demonstrates a practical end-to-end integration of the ESP32 embedded platform, local AI "
        "inference, voice processing, structured tool calling, and computer automation.",
        ST["body"]
    ))
    story.append(PageBreak())

    # ─── SECTION 3 — PROBLEM STATEMENT ───────────────────────────────────────
    story.append(Banner("3", "PROBLEM STATEMENT", CONTENT_W))
    story.append(sp(0.3))
    story.append(Paragraph(
        "Modern computer users rely on keyboards, mice, and GUIs for system control. While cloud-based "
        "voice assistants (Alexa, Google Assistant, Cortana) exist, they have significant limitations:",
        ST["body"]
    ))
    for p in [
        "They require continuous internet connectivity and depend on cloud AI servers, introducing latency and privacy risks.",
        "They provide no physical presence — all feedback is software-based and gets hidden behind open application windows.",
        "They have limited ability to perform intelligent local desktop automation (launching apps, volume control, file management).",
        "They do not integrate with embedded hardware for real-time physical status display synchronized with AI processing.",
        "Most solutions send personal voice data to remote servers — a significant privacy concern.",
        "No affordable, open, and hackable alternative exists that combines local AI with embedded hardware.",
    ]:
        story.append(bul(p, ST))
    story.append(sp(0.3))
    story.append(Paragraph(
        "<b>Core Gap Identified:</b> There is no compact, privacy-oriented, physical AI companion device "
        "that combines local LLM reasoning, voice interaction, structured tool/function calling, and "
        "synchronized physical visual+audio feedback for desktop automation — running on affordable "
        "embedded hardware like the ESP32.",
        ST["body"]
    ))

    # ─── SECTION 4 — SOLUTION ─────────────────────────────────────────────────
    story.append(sp(0.4))
    story.append(Banner("4", "SOLUTION — METHODOLOGY, IMPLEMENTATION & INNOVATION", CONTENT_W))
    story.append(sp(0.3))

    story.append(Paragraph("<b>4.1 System Methodology</b>", ST["sub"]))
    story.append(Paragraph(
        "KYOMA uses a hardware-software co-design approach. The physical ESP32 device is the user-facing "
        "interface. A Python backend on the host computer handles AI inference and automation. The complete "
        "pipeline is:", ST["body"]
    ))
    
    flow = [
        [Paragraph("Step", ST["th"]), Paragraph("Component", ST["th"]), Paragraph("Action", ST["th"])],
        [Paragraph("1", ST["tc"]), Paragraph("I2S MEMS Microphone", ST["tc"]), Paragraph("Captures the user's voice command", ST["tc"])],
        [Paragraph("2", ST["tc"]), Paragraph("ESP32 / ESP32-S3", ST["tc"]), Paragraph("Processes audio over I2S; relays via Wi-Fi or Serial", ST["tc"])],
        [Paragraph("3", ST["tc"]), Paragraph("Speech-to-Text (Host)", ST["tc"]), Paragraph("Converts captured speech to text string", ST["tc"])],
        [Paragraph("4", ST["tc"]), Paragraph("Local AI Engine (Ollama)", ST["tc"]), Paragraph("Detects intent; produces structured tool/function call", ST["tc"])],
        [Paragraph("5", ST["tc"]), Paragraph("Automation Subsystem (Python)", ST["tc"]), Paragraph("Executes computer operation (volume, app, media, etc.)", ST["tc"])],
        [Paragraph("6", ST["tc"]), Paragraph("Communication Interface", ST["tc"]), Paragraph("Result and system state sent back to ESP32", ST["tc"])],
        [Paragraph("7", ST["tc"]), Paragraph("OLED Display + Speaker", ST["tc"]), Paragraph("Shows visual state; plays audio response", ST["tc"])],
    ]
    ft = Table(flow, colWidths=[1.2*cm, 5.0*cm, CONTENT_W - 6.2*cm])
    ft.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), DARK_BLUE),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT_GREY, WHITE]),
        ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#B0BEC5")),
        ("ALIGN",       (0,0), (0,-1), "CENTER"),
        ("TOPPADDING",  (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 8), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(ft)
    story.append(sp(0.3))

    story.append(Paragraph("<b>4.2 Hardware Implementation</b>", ST["sub"]))
    for item in [
        "<b>ESP32-S3 Microcontroller</b> — Main SoC; handles I2C (OLED), I2S (microphone + amplifier), Wi-Fi (HTTP/WebSocket), GPIO and UART communication.",
        "<b>OLED Display (128×64, I2C)</b> — Physical visual status interface; displays graphical expressions: idle face, listening state, thinking animation, success/error indicators.",
        "<b>I2S MEMS Microphone</b> — Captures high-quality digital audio from the user's voice commands with minimal noise.",
        "<b>MAX98357A I2S Amplifier + Speaker</b> — Decodes I2S audio stream from the ESP32 and drives the speaker for audio responses and notifications.",
        "<b>Custom Enclosure</b> — Compact desktop form-factor housing all components; OLED visible through a cutout in the front panel.",
        "<b>USB Power Input</b> — Powers the device; designed to support rechargeable battery in future revision.",
    ]:
        story.append(bul(item, ST))

    story.append(sp(0.3))
    story.append(Paragraph("<b>4.3 Software Implementation</b>", ST["sub"]))
    for item in [
        "<b>Ollama (Local AI Runtime)</b> — Runs quantized LLMs (Mistral 7B, Llama3 8B) locally on the host PC without internet or API keys.",
        "<b>Python Backend</b> — Handles speech-to-text (Whisper / SpeechRecognition library), AI prompt construction, tool call parsing, and automation execution.",
        "<b>Structured Tool / Function Calling</b> — JSON-schema-defined function calls convert AI intent into typed automation requests; prevents arbitrary command execution.",
        "<b>Kyoma_automation.py</b> — Core automation module with an ACTION_MAP supporting 15+ operations: volume control, brightness, open/close apps, open files/folders, media playback, reminders, screenshots.",
        "<b>ESP32 Firmware (Arduino / MicroPython)</b> — OLED state machine, I2S audio driver, Wi-Fi HTTP client, Serial fallback communication.",
        "<b>Context Memory with RAG</b> — Preloaded user preferences and system settings retrieved via semantic lookup to guide tool selection.",
    ]:
        story.append(bul(item, ST))

    story.append(sp(0.3))
    story.append(Paragraph("<b>4.4 Innovation</b>", ST["sub"]))
    for item in [
        "Fully <b>offline-capable</b> — no cloud APIs, no subscriptions, no user data leaves the local machine.",
        "<b>Structured tool/function calling</b> ensures the AI triggers real, typed computer automation — not just text generation.",
        "<b>Physical OLED visual feedback</b> synchronized with the exact AI processing state in real time.",
        "Built entirely on the affordable, widely available <b>ESP32 SoC platform</b> taught in the course.",
        "Demonstrates <b>Edge AI principles</b> — intelligence moves from cloud servers to the local device.",
    ]:
        story.append(bul(item, ST))

    story.append(PageBreak())

    # ─── SECTION 5 — OBJECTIVES ───────────────────────────────────────────────
    story.append(Banner("5", "OBJECTIVES", CONTENT_W))
    story.append(sp(0.3))
    objectives = [
        ("Primary Objective",
         "Design and develop a physical AI-enabled desktop companion (KYOMA) that understands natural-language voice commands and performs computer automation tasks locally."),
        ("Hardware Objective",
         "Build a functional embedded system using ESP32/ESP32-S3 integrating OLED display, I2S MEMS microphone, MAX98357A audio amplifier and speaker in a custom enclosure."),
        ("AI Objective",
         "Deploy a local large language model via Ollama on the host computer for speech-to-text, intent detection, and structured tool/function calling — without cloud dependency."),
        ("Automation Objective",
         "Build a Python automation subsystem supporting: volume control, brightness adjustment, application management, media control, reminder scheduling, and more."),
        ("Communication Objective",
         "Establish reliable wired (Serial/USB) and wireless (Wi-Fi HTTP/WebSocket) communication between the host computer and the ESP32 device to sync states and results."),
        ("Feedback Objective",
         "Implement synchronized OLED visual interaction states (listening, thinking, executing, success, error) and speaker audio feedback matching AI processing stages."),
        ("Privacy Objective",
         "Ensure all AI processing and automation runs locally — no personal data or voice recordings sent to remote servers."),
    ]
    for i, (t, d) in enumerate(objectives, 1):
        row = Table(
            [[Paragraph(f"<b>{i}. {t}</b>", ST["sub"]),
              Paragraph(d, ST["body"])]],
            colWidths=[4.5*cm, CONTENT_W - 4.5*cm]
        )
        row.setStyle(TableStyle([
            ("VALIGN", (0,0),(-1,-1), "TOP"),
            ("TOPPADDING", (0,0),(-1,-1), 3), ("BOTTOMPADDING", (0,0),(-1,-1), 3),
            ("LEFTPADDING", (1,0),(1,-1), 10),
            ("LINEBELOW", (0,0),(-1,-1), 0.4, colors.HexColor("#CFD8DC")),
        ]))
        story.append(row)

    story.append(PageBreak())

    # ─── SECTION 6 — WORKFLOW ─────────────────────────────────────────────────
    story.append(Banner("6", "PROGRESS OF WORKFLOW — TWO STAGES", CONTENT_W))
    story.append(sp(0.3))

    story.append(Paragraph("<b>Stage 1 — Hardware Prototype &amp; Embedded Firmware</b>", ST["sub"]))
    story.append(Paragraph(
        "In Stage 1, the physical KYOMA device was assembled and the ESP32 firmware was developed. "
        "The OLED display was connected via I2C and programmed to show graphical expressions — an idle "
        "face when waiting, and a boot screen reading 'KYOMA — Your AI Companion' on startup. "
        "The I2S MEMS microphone was wired and tested for digital audio capture. The MAX98357A amplifier "
        "was connected to the ESP32 I2S bus and tested for audio playback through the speaker. "
        "Wi-Fi connectivity was established and tested via HTTP ping to the host computer.",
        ST["body"]
    ))
    for item in [
        "ESP32-S3 board flashed with custom Arduino firmware.",
        "OLED 128×64 display (I2C) showing idle face and boot text.",
        "I2S MEMS microphone tested for digital audio capture.",
        "MAX98357A I2S amplifier + speaker verified for audio output.",
        "Wi-Fi HTTP connectivity established between ESP32 and host computer.",
        "Physical enclosure fabricated; all components integrated and secured.",
        "Logic analyzer used to verify I2C OLED (address 0x3C) and I2S mic signal integrity.",
    ]:
        story.append(bul(item, ST))

    story.append(sp(0.3))

    # Device photos
    for path, cap in [
        (images.get("d1"), "Figure 1: KYOMA physical device — OLED displaying idle face expression"),
        (images.get("d2"), "Figure 2: KYOMA device — OLED boot screen showing 'KYOMA — Your AI Companion'"),
    ]:
        for el in img_block(path, cap, ST, max_w=9*cm, max_h=7*cm):
            story.append(el)

    story.append(sp(0.3))
    story.append(Paragraph("<b>Stage 2 — Local AI Integration &amp; Full Automation Pipeline</b>", ST["sub"]))
    story.append(Paragraph(
        "In Stage 2, the host computer backend was developed and fully integrated with the KYOMA hardware. "
        "Ollama was installed and configured to run Mistral 7B locally. The Python backend was built to "
        "connect speech-to-text input, AI intent detection, tool/function calling, and the computer "
        "automation subsystem. The complete end-to-end pipeline was tested with real voice commands.",
        ST["body"]
    ))
    for item in [
        "Ollama installed on host PC; Mistral 7B model downloaded and tested for local inference.",
        "Python speech-to-text implemented using the SpeechRecognition library and Whisper model.",
        "Local AI prompt engineering: system prompt defines KYOMA's personality and tool schema.",
        "Structured JSON tool/function calling implemented; AI output parsed and validated.",
        "Kyoma_automation.py: ACTION_MAP with 15+ functions covering all required operations.",
        "Host-to-device communication: HTTP WebSocket for Wi-Fi; Serial/USB as fallback.",
        "OLED state machine: listening → thinking → executing → success / error.",
        "TTS audio response implemented; played through MAX98357A/speaker via I2S.",
        "End-to-end test: 'Kyoma, increase the volume' → intent detected → volume changed → OLED success → audio response.",
    ]:
        story.append(bul(item, ST))

    story.append(PageBreak())

    # Architecture diagrams
    story.append(Paragraph("<b>System Architecture Diagrams</b>", ST["sub"]))
    story.append(sp(0.2))
    for path, cap in [
        (images.get("a1"), "Figure 3: KYOMA Communication Flow — Voice Input → AI Processing → Automation → Output"),
        (images.get("a2"), "Figure 4: KYOMA Hardware Architecture — Input Devices, Processing Unit, Connectivity & Output Components"),
    ]:
        for el in img_block(path, cap, ST, max_w=CONTENT_W, max_h=9*cm):
            story.append(el)
        story.append(sp(0.2))

    story.append(PageBreak())

    # ─── SECTION 7 — ANALYTICAL THINKING ─────────────────────────────────────
    story.append(Banner("7", "ANALYTICAL THINKING", CONTENT_W))
    story.append(sp(0.3))

    story.append(Paragraph("<b>7.1 Relevance to Course Topics</b>", ST["sub"]))
    topics = [
        ("ESP32 / ESP32-S3 SoC Platform",
         "KYOMA is entirely built on the ESP32-S3 — the primary SoC platform covered in the course. "
         "The firmware uses I2C (OLED), I2S (microphone + amplifier), Wi-Fi (HTTP/WebSocket), GPIO and "
         "UART — directly applying peripheral interfacing and communication protocols taught."),
        ("Edge AI / TinyML Principles",
         "The overall system follows Edge AI architecture: intelligence is local, latency is low, and "
         "no cloud dependency exists. The ESP32 acts as the intelligent edge node; the host computer "
         "acts as the local edge server. This mirrors TinyML and Edge AI Vision Gateway designs from the course."),
        ("Cognitive Control Engine Design",
         "The AI intent detection + structured tool/function calling pipeline is a practical Cognitive "
         "Control Engine: it receives sensory input (voice), reasons about intent, selects an action, "
         "executes it, and provides output — matching the cognitive architecture models discussed."),
        ("Communication Protocol Design",
         "KYOMA implements HTTP/WebSocket and Serial communication between the ESP32 and the host, "
         "demonstrating real-world embedded protocol design with JSON data exchange — directly applying "
         "communication failure debugging techniques from the course."),
        ("Context Memory with RAG",
         "Retrieval-Augmented Generation: Employs a local vector store retrieval pipeline to provide persistent context memory, enhancing prompt generation and personalization based on user preferences."),
        ("Debugging with Logic Analyzer",
         "During development, I2C communication with the OLED (address scan) and I2S microphone signals "
         "were verified using a logic analyzer to verify signal integrity."),
        ("Self-Healing Network Concepts",
         "The ESP32 firmware implements automatic Wi-Fi reconnection with exponential backoff, "
         "and falls back to Serial communication if Wi-Fi fails — demonstrating self-healing embedded "
         "network design principles covered in the course."),
    ]
    for i, (t, d) in enumerate(topics, 1):
        story.append(Paragraph(f"<b>{i}. {t}</b>", ST["sub"]))
        story.append(Paragraph(d, ST["body"]))

    story.append(sp(0.3))
    story.append(Paragraph("<b>7.2 Design Decisions and Trade-offs</b>", ST["sub"]))
    
    tradeoffs = [
        ("Local AI (Ollama) vs Cloud AI",
         "Local chosen. Trade-off: requires capable host PC. Benefit: complete privacy, no API cost, offline capability, faster iteration."),
        ("ESP32-S3 vs Teensy 4.1",
         "ESP32-S3 chosen for built-in Wi-Fi, I2S support, and large community. Teensy 4.1 offers more CPU power but lacks native Wi-Fi."),
        ("Wi-Fi vs Serial Communication",
         "Wi-Fi primary for wireless flexibility; USB Serial as fallback for debugging. Both implemented and tested."),
        ("OLED (128×64) vs LCD Display",
         "OLED chosen for higher contrast, lower power, and ability to display graphical facial expressions matching KYOMA's companion personality."),
        ("Structured Tool Calling vs Free Text",
         "Structured function calling chosen to ensure exact typed parameters. Prevents LLM hallucination from triggering incorrect or dangerous system commands."),
    ]
    
    td_rows = [[Paragraph("<b>Design Decision</b>", ST["th"]), Paragraph("<b>Rationale</b>", ST["th"])]]
    for decision, rationale in tradeoffs:
        td_rows.append([Paragraph(decision, ST["tc_bold"]), Paragraph(rationale, ST["tc"])])
        
    td = Table(td_rows, colWidths=[5.5*cm, CONTENT_W - 5.5*cm])
    td.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), ACCENT_BLUE),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT_GREY, WHITE]),
        ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#B0BEC5")),
        ("TOPPADDING",  (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 8), ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    story.append(td)

    story.append(sp(0.3))
    story.append(Paragraph("<b>7.3 Challenges Encountered and Solutions</b>", ST["sub"]))
    
    challenges = [
        ("I2S Microphone Noise", "Adjusted sample rate and bit depth; applied software audio filter before speech-to-text processing."),
        ("OLED I2C Address Conflict", "Used logic analyzer to scan I2C bus; confirmed device address 0x3C; corrected firmware config."),
        ("Wi-Fi Reconnection Drops", "Implemented automatic reconnect loop with exponential backoff in ESP32 firmware."),
        ("LLM Intent Hallucination", "Strict system prompt with JSON schema validation for tool call outputs; invalid calls are rejected."),
        ("Audio Latency", "Buffered TTS audio output; implemented DMA-based non-blocking audio playback on the ESP32."),
        ("Long Python Path Resolution", "ACTION_MAP uses subprocess + psutil with multi-strategy path resolution and fallback methods."),
    ]
    
    ch_rows = [[Paragraph("<b>Challenge</b>", ST["th"]), Paragraph("<b>Solution Applied</b>", ST["th"])]]
    for challenge, solution in challenges:
        ch_rows.append([Paragraph(challenge, ST["tc_bold"]), Paragraph(solution, ST["tc"])])
        
    cht = Table(ch_rows, colWidths=[5.5*cm, CONTENT_W - 5.5*cm])
    cht.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), DARK_BLUE),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT_GREY, WHITE]),
        ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#B0BEC5")),
        ("TOPPADDING",  (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 8), ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    story.append(cht)

    story.append(sp(0.3))
    story.append(Paragraph("<b>7.4 Working Examples</b>", ST["sub"]))

    examples = [
        ("Example 1 — Volume Control",
         [
             'User says: "Kyoma, increase the volume."',
             "I2S MEMS microphone captures the audio command.",
             "ESP32 transmits audio data to host computer over Wi-Fi.",
             "Speech-to-text converts audio to: increase the volume.",
             "Local AI (Ollama/Mistral) detects intent: volume_control, parameter: increase.",
             "Python automation subsystem executes: volume_up() function.",
             "Result SUCCESS returned; transmitted to ESP32.",
             "OLED changes to success expression; speaker plays audio confirmation.",
         ]),
        ("Example 2 — Open Application",
         [
             'User says: "Kyoma, open Chrome."',
             "Speech-to-text output: open Chrome.",
             "Local AI detects intent: open_application, target: Chrome.",
             "ACTION_MAP looks up Chrome path; subprocess launches Chrome.",
             "Result returned to ESP32; OLED shows success state.",
         ]),
        ("Example 3 — Open Folder",
         [
             'User says: "Kyoma, open my project folder."',
             "AI identifies intent: open_folder, path: project folder.",
             "os.startfile() opens the folder in Windows Explorer.",
             "KYOMA confirms with audio: 'Done! I opened your project folder.'",
         ]),
    ]
    for title, steps in examples:
        story.append(Paragraph(f"<b>{title}</b>", ST["sub"]))
        for step in steps:
            story.append(bul(step, ST))
        story.append(sp(0.1))

    story.append(PageBreak())

    # ─── SECTION 8 — CONCLUSION ───────────────────────────────────────────────
    story.append(Banner("8", "CONCLUSION", CONTENT_W))
    story.append(sp(0.3))
    story.append(Paragraph(
        "KYOMA successfully demonstrates the practical integration of embedded systems engineering, "
        "local artificial intelligence, and desktop computer automation in a single, cohesive product. "
        "The project directly applied core curriculum concepts including the ESP32 platform, I2S/I2C "
        "peripheral interfacing, Wi-Fi communication protocol design, Edge AI principles, cognitive "
        "control engine design, and hardware debugging with a logic analyzer.",
        ST["body"]
    ))
    story.append(Paragraph(
        "The physical KYOMA companion device is a working prototype that accepts real voice commands, "
        "processes them through a locally running large language model, performs genuine computer "
        "automation tasks, and provides synchronized physical visual and audio feedback — all without "
        "requiring cloud services or internet connectivity.",
        ST["body"]
    ))
    story.append(Paragraph("<b>Key Achievements:</b>", ST["body"]))
    for a in [
        "Functional ESP32-S3 firmware: OLED (I2C), I2S microphone, I2S MAX98357A amplifier, Wi-Fi communication.",
        "Local AI pipeline (Ollama + Mistral 7B): offline intent detection and structured tool/function calling.",
        "Python automation subsystem (Kyoma_automation.py): 15+ supported computer automation functions.",
        "Synchronized OLED state machine: idle → listening → thinking → executing → success/error.",
        "End-to-end working system demonstrated with real voice commands.",
        "Patent application filed (Indian Patents Act 1970) documenting the invention.",
        "Context Memory implementation utilizing a local vector retrieval mechanism (RAG) to dynamically inject context into the prompt pipeline.",
    ]:
        story.append(bul(a, ST))

    story.append(sp(0.3))
    story.append(Paragraph(
        "KYOMA is not simply a course prototype — it is a well-defined, patent-documented invention "
        "describing a novel combination of physical embedded hardware, local AI reasoning, structured "
        "tool/function calling, and synchronized physical feedback for desktop automation. "
        "It establishes a strong foundation for further development as a commercial product and "
        "demonstrates the real-world applicability of the embedded systems and AI skills developed "
        "during this course.",
        ST["body"]
    ))
    story.append(sp(0.5))
    story.append(hr())
    story.append(Paragraph(
        "KYOMA Capstone Project Report  |  Saveetha Institute of Medical and Technical Sciences  |  2026",
        ST["footer"]
    ))

    # Build PDF and avoid trailing empty pages by not having empty spacers at the end
    doc.build(story,
              onFirstPage=later_pages,
              onLaterPages=later_pages)
    print(f"PDF saved: {output}")


# ─── Image assignments ────────────────────────────────────────────────────────
BASE  = r"C:\Users\harsh\.gemini\antigravity\brain\218a3729-4800-458e-bf9f-bc476491d356"
IMG   = {
    "d1": os.path.join(BASE, "media__1787777294074.jpg"),   # tall  — device photo 1
    "d2": os.path.join(BASE, "media__1787777294152.jpg"),   # tall  — device photo 2
    "a1": os.path.join(BASE, "media__1787777187714.png"),   # wide  — arch diagram 1
    "a2": os.path.join(BASE, "media__1787777242028.png"),   # wide  — arch diagram 2
}

OUT = r"c:\Users\harsh\Downloads\LocalAIVtuber2-master\LocalAIVtuber2-master\KYOMA_Capstone_Report.pdf"
build(OUT, IMG)
