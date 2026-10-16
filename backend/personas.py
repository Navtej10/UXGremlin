from dataclasses import dataclass, field
from typing import Any
import re

@dataclass
class PersonaConfig:
    name: str
    label: str
    viewport: dict[str, int]
    is_mobile: bool = False
    has_touch: bool = False
    timeouts: dict[str, float] = field(default_factory=dict)
    behavior_rules: str = ""
    hard_rules: dict[str, Any] = field(default_factory=dict)


PERSONAS: dict[str, PersonaConfig] = {
    "impatient": PersonaConfig(
        name="impatient",
        label="😈 Impatient User",
        viewport={"width": 1280, "height": 800},
        is_mobile=False,
        has_touch=False,
        timeouts={
            "action_timeout": 2.0,       # wait timeout 2s
            "settle_timeout": 0.3,
            "slow_step_threshold": 2.0,  # steps > 2s count as slow
        },
        behavior_rules=(
            "You are an extremely impatient user. You skim quickly and click prominent visible controls immediately. "
            "You do not read lengthy instructions or marketing copy. If any step or page load takes longer than 2 seconds, "
            "you become visibly frustrated. If clicking an element produces no immediate response, you repeatedly click it "
            "in rapid succession (rage-clicking). If the site stalls or has 3 slow steps, you abandon the task in disgust."
        ),
        hard_rules={
            "wait_timeout": 2.0,
            "rage_click_no_change_threshold": 2,  # rage-click after 2 no-change clicks
            "max_slow_steps": 3,                  # abandons after 3 slow steps
        },
    ),
    "confused": PersonaConfig(
        name="confused",
        label="😵‍💫 Confused User",
        viewport={"width": 1280, "height": 800},
        is_mobile=False,
        has_touch=False,
        timeouts={
            "action_timeout": 3.0,
            "settle_timeout": 0.7,
            "slow_step_threshold": 4.0,
        },
        behavior_rules=(
            "You are a confused, non-technical user. You overlook small links, fine print, and footer text. "
            "You strongly prefer large, obvious buttons over subtle links. You interpret all button labels and text strictly "
            "literally, and you get lost when encountering technical jargon. When faced with icon-only buttons that lack "
            "text labels, you hesitate and perform extra observations to guess what they do."
        ),
        hard_rules={
            "ignore_link_area_threshold": 1200,   # ignores links under 1200px^2 bounding area
            "prefer_prominent_buttons": True,     # prefers prominent buttons over links
            "re_read_labels_literally": True,     # reads copy word-for-word literally
            "hesitate_on_icon_only": True,        # hesitates (extra observation) on icon-only controls
            "hesitation_delay": 0.6,
        },
    ),
    "skeptic": PersonaConfig(
        name="skeptic",
        label="🧐 Skeptical User",
        viewport={"width": 1280, "height": 800},
        is_mobile=False,
        has_touch=False,
        timeouts={
            "action_timeout": 3.5,
            "settle_timeout": 0.6,
            "slow_step_threshold": 4.0,
        },
        behavior_rules=(
            "You are a cautious, privacy-first skeptical user. You distrust unverified forms and aggressive sales pitches. "
            "You REFUSE to enter real personal data (real email, phone number, address, or payment details) into forms. "
            "When forced to type into a personal information field, you provide obviously synthetic/fake data and flag the form. "
            "You actively look for trust signals: privacy policy links, user reviews/ratings, and transparent pricing. "
            "If any of these trust signals are absent, you record their absence as critical credibility findings."
        ),
        hard_rules={
            "refuse_personal_data": True,         # uses obviously fake data and flags form
            "flag_personal_data_forms": True,
            "check_trust_signals": True,          # checks privacy policy, reviews, pricing visibility
        },
    ),
    "pro_tester": PersonaConfig(
        name="pro_tester",
        label="🎯 Professional UX Tester",
        viewport={"width": 1280, "height": 800},
        is_mobile=False,
        has_touch=False,
        timeouts={
            "action_timeout": 3.0,
            "settle_timeout": 0.5,
            "slow_step_threshold": 4.0,
        },
        behavior_rules=(
            "You are a meticulous, senior Professional UX & QA Engineer. Your directive is to systematically audit, "
            "inspect, and test the entire interface while accomplishing the task. You systematically visit each interactive "
            "control category: buttons, input fields, dropdown selects, and navigation links. You actively check for bugs, "
            "layout misalignments, validation gaps, and unresponsive controls before concluding."
        ),
        hard_rules={
            "track_control_categories": True,     # systematically visits each interactive control category
            "systematic_categories": ["button", "input", "select", "link", "textarea"],
        },
    ),
    "mobile": PersonaConfig(
        name="mobile",
        label="📱 Mobile User",
        viewport={"width": 390, "height": 844},
        is_mobile=True,
        has_touch=True,
        timeouts={
            "action_timeout": 2.5,
            "settle_timeout": 0.5,
            "slow_step_threshold": 3.0,
        },
        behavior_rules=(
            "You are using a mobile smartphone with a 390x844 touchscreen display. You navigate using touch taps. "
            "You are sensitive to small tap targets that are hard to tap accurately. "
            "You audit the interface for mobile responsiveness, viewport scaling, and accessible touch target sizes (minimum 44x44px). "
            "You flag any interactive control smaller than 44px as an ergonomic defect."
        ),
        hard_rules={
            "min_tap_target_size": 44,            # flags tap targets below 44px
            "enforce_touch": True,
        },
    ),
    "baseline": PersonaConfig(
        name="baseline",
        label="⚡ Direct Baseline Agent",
        viewport={"width": 1280, "height": 800},
        is_mobile=False,
        has_touch=False,
        timeouts={
            "action_timeout": 3.0,
            "settle_timeout": 0.4,
            "slow_step_threshold": 4.0,
        },
        behavior_rules=(
            "You are an expert, highly efficient user testing baseline. "
            "You take the shortest, most direct path to successfully accomplish the goal. "
            "You do not wander, hesitate, or perform redundant actions."
        ),
        hard_rules={},
    ),
}


def get_persona_config(persona_name: str | None) -> PersonaConfig:
    key = (persona_name or "pro_tester").lower().strip()
    return PERSONAS.get(key, PERSONAS["pro_tester"])


def is_personal_data_field(label: str, target: str, field_type: str = "") -> bool:
    """Checks if a form control is requesting personal or sensitive user information."""
    combined = f"{label} {target} {field_type}".lower()
    patterns = [
        r"\bemail\b",
        r"\bphone\b",
        r"\btel\b",
        r"\bmobile\b",
        r"\bfirst\s*name\b",
        r"\blast\s*name\b",
        r"\bfull\s*name\b",
        r"\baddress\b",
        r"\bzip\b",
        r"\bpostal\b",
        r"\bcredit\b",
        r"\bcard\b",
        r"\bssn\b",
        r"\bpassword\b",
    ]
    return any(re.search(pat, combined) for pat in patterns)


def get_fake_personal_data(label: str, target: str = "") -> str:
    """Generates obviously synthetic/fake data (e.g. fake_user@example.com) for form fields."""
    combined = f"{label} {target}".lower()
    if "email" in combined:
        return "fake_user@example.com"
    if any(k in combined for k in ["phone", "tel", "mobile"]):
        return "555-0100"
    if any(k in combined for k in ["name", "user"]):
        return "Fake User Refused"
    if any(k in combined for k in ["zip", "postal"]):
        return "00000"
    if "address" in combined:
        return "123 Synthetic Privacy Way"
    if any(k in combined for k in ["card", "credit", "cvv"]):
        return "0000000000000000"
    return "Refused Private Data"


def audit_trust_signals_in_page(page_text: str, page_links: list[dict]) -> list[dict]:
    """
    Audits a page for trust signals:
      1. Privacy policy link or statement
      2. Customer reviews or social proof
      3. Transparent pricing visibility
    Returns a list of structured findings for missing trust signals.
    """
    text_lower = page_text.lower()
    findings: list[dict] = []

    # 1. Privacy Policy check
    has_privacy_link = any(
        "privacy" in (l.get("href", "") + " " + l.get("text", "")).lower()
        for l in page_links
    )
    has_privacy_text = "privacy policy" in text_lower or "data privacy" in text_lower
    if not (has_privacy_link or has_privacy_text):
        findings.append({
            "title": "Trust Deficit: Missing Privacy Policy",
            "severity": "high",
            "evidence_steps": [],
            "what_happened": "No visible privacy policy link or data protection statement was detected on the page.",
            "impact": "Skeptical and privacy-conscious users hesitate or refuse to proceed without clear data usage terms.",
            "recommendation": "Add a prominent, accessible Privacy Policy link in the navigation or footer.",
        })

    # 2. Reviews / Social Proof check
    review_terms = ["reviews", "customer review", "testimonials", "stars", "rating", "trusted by", "feedback"]
    has_reviews = any(term in text_lower for term in review_terms)
    if not has_reviews:
        findings.append({
            "title": "Trust Deficit: Absence of Verified Reviews or Social Proof",
            "severity": "medium",
            "evidence_steps": [],
            "what_happened": "No customer reviews, ratings, testimonials, or trust badges were visible on the site.",
            "impact": "Prospective users lack confidence in the product's legitimacy and quality.",
            "recommendation": "Include verified third-party reviews, testimonial quotes, or customer rating badges.",
        })

    # 3. Transparent Pricing Visibility check
    pricing_terms = ["$", "pricing", "plans", "price", "refund", "guarantee", "free trial", "money-back", "billed"]
    has_pricing = any(term in text_lower for term in pricing_terms)
    if not has_pricing:
        findings.append({
            "title": "Trust Deficit: Opaque or Missing Pricing Terms",
            "severity": "high",
            "evidence_steps": [],
            "what_happened": "Clear pricing tiers, refund policies, or cost transparency could not be identified.",
            "impact": "Users worry about hidden fees or subscriptions and frequently abandon the workflow.",
            "recommendation": "Display transparent pricing breakdowns and explicit refund or guarantee policies.",
        })

    return findings
