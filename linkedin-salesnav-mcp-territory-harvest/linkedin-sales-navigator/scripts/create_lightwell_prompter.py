#!/usr/bin/env python3
"""Create a Lightwell 3-minute pitch prompter PowerPoint deck."""

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

OUTPUT = Path(__file__).resolve().parent.parent / "output" / "Lightwell_3min_Pitch_Prompter.pptx"

# Full conversational lines — read exactly what appears on each slide.
SLIDES = [
    (
        "Quick question: when a serious security flaw shows up in open source software your business "
        "already runs in production — not your operating system, but the building blocks inside your "
        "applications — what happens next?"
    ),
    (
        "For most companies, the answer is a big upgrade. That means more testing, more approvals, "
        "more waiting — and more time exposed to risk."
    ),
    (
        "And the problem is getting bigger, faster. AI is helping security teams find issues sooner — "
        "but attackers are moving just as fast. Most enterprise applications rely heavily on open "
        "source, and the list of known issues keeps growing."
    ),
    (
        "That's the gap we keep hearing about: you know there's a problem, but getting a trusted fix "
        "into production takes too long. That's why Red Hat and IBM built Lightwell."
    ),
    (
        "Lightwell is a joint Red Hat and IBM offering that brings the same trusted support model "
        "we've used for Red Hat Enterprise Linux for over 20 years — tested fixes, delivered with "
        "confidence — to the open source components across your applications."
    ),
    (
        "Instead of forcing a disruptive upgrade, Lightwell gives you trusted security fixes for the "
        "exact versions you're already running. Your teams pull those fixes into the way they already "
        "build and release software — with the documentation and assurance enterprise customers expect."
    ),
    (
        "This isn't another scanning tool. It's a major investment — five billion dollars and "
        "20,000 engineers — combining AI speed with real human expertise to validate fixes before "
        "they reach your environment."
    ),
    (
        "And we do it the Red Hat way: fixes are shared back with the open source community, so "
        "customers get protection without creating a separate, unsupported version of the software."
    ),
    (
        "We launched with thousands of fixes already available, starting with common enterprise "
        "languages like Java and Python — and we're scaling fast, with input from leading financial "
        "services organizations."
    ),
    (
        "Lightwell is an annual subscription with two options. Lightwell Network is available now. "
        "It's the easiest place to start — ongoing access to a growing library of trusted fixes your "
        "teams can adopt through their existing development process. Most customers begin here."
    ),
    (
        "Lightwell Clearinghouse Premier is for organizations with higher stakes — critical "
        "infrastructure, stricter compliance needs, or industry-wide coordination. It includes "
        "everything in Network, plus the ability to raise your own security issues privately and "
        "work directly with Red Hat experts on fixes tailored to your environment."
    ),
    (
        "What does that mean for the business? Fewer security issues sitting in a backlog. Less "
        "pressure to rush risky upgrades. More confidence that production stays stable — while "
        "still moving faster than before."
    ),
    (
        "One honest point: Lightwell delivers fixes quickly, but only helps if your organization can "
        "deploy them quickly too. If it still takes months to push a change live, the fix waits on "
        "the shelf. That's why we also offer consulting, dedicated support, and training — to help "
        "you fix the process as well as the software."
    ),
    (
        "If your teams depend on open source in production and struggle to close security gaps at the "
        "pace the business expects, let's talk about starting with Lightwell Network."
    ),
    (
        "We can also offer a short assessment — about two weeks — to understand where you're exposed "
        "today and build a practical plan to move forward. Who on your side owns software supply chain "
        "security? I'd love to connect them with our Lightwell team."
    ),
    "Questions?",
]

OBJECTION_SLIDES = [
    (
        "We already have security tools. Lightwell isn't about finding problems — it's about "
        "delivering trusted fixes for the software versions you're actually running, without "
        "forcing an upgrade."
    ),
    (
        "Why not just upgrade? Because in many enterprises, testing, compliance, or customer "
        "commitments make a quick upgrade impossible. Lightwell gives you a safer path forward."
    ),
    (
        "Think of it this way: it's the same trusted Red Hat support model customers have relied on "
        "for Linux for decades — now extended to the open source building blocks inside your "
        "applications."
    ),
]


def set_slide_background(slide, color: RGBColor) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def font_size_for(text: str) -> int:
    chars = len(text)
    if chars > 320:
        return 24
    if chars > 260:
        return 26
    if chars > 200:
        return 28
    if chars > 140:
        return 32
    if chars > 90:
        return 36
    return 42


def add_speakable_text(slide, text: str) -> None:
    box = slide.shapes.add_textbox(Inches(0.9), Inches(0.8), Inches(11.5), Inches(5.9))
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = frame.paragraphs[0]
    p.text = text
    p.alignment = PP_ALIGN.LEFT
    p.font.size = Pt(font_size_for(text))
    p.font.color.rgb = RGBColor(245, 245, 245)
    p.font.name = "Calibri"
    p.line_spacing = 1.35


def build_deck() -> Path:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    bg = RGBColor(30, 30, 30)

    for text in SLIDES + OBJECTION_SLIDES:
        slide = prs.slides.add_slide(blank)
        set_slide_background(slide, bg)
        add_speakable_text(slide, text)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    path = build_deck()
    print(path)
