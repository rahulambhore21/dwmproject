"""Synthetic demo-data simulator for the fictional brand "Northwind Studio".

The simulator draws post attributes, then draws engagement from a *hidden* effect
model plus noise. Nothing downstream reads the hidden effects: the analytics and
ML layers must rediscover (some of) the signal from the generated rows, which is
what makes the demo realistic rather than hard-coded. Everything is driven by a
seeded numpy Generator, so it is reproducible.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np

from ..etl.text import extract_text_features

PLATFORMS = {
    # weight, base engagement rate, followers (start, end), optimal caption length
    "Instagram": dict(weight=0.34, base=0.040, followers=(18000, 31000), opt_len=190),
    "LinkedIn": dict(weight=0.30, base=0.034, followers=(9000, 17000), opt_len=520),
    "TikTok": dict(weight=0.16, base=0.070, followers=(6000, 21000), opt_len=110),
    "X": dict(weight=0.20, base=0.016, followers=(12000, 14500), opt_len=150),
}

FORMATS = {
    "Instagram": {"Reel": (0.38, 0.18, 1.9), "Carousel": (0.32, 0.22, 0.95), "Image": (0.30, 0.0, 0.65)},
    "LinkedIn": {"Text": (0.35, 0.05, 0.9), "Carousel": (0.25, 0.30, 1.3), "Image": (0.20, -0.05, 0.8), "Video": (0.20, 0.0, 1.0)},
    "TikTok": {"Video": (1.0, 0.0, 2.2)},
    "X": {"Text": (0.50, 0.0, 0.35), "Thread": (0.25, 0.20, 0.5), "Image": (0.25, 0.05, 0.4)},
}

HOOK_EFFECT = {"Question": 0.10, "Bold claim": 0.04, "Story": 0.12, "Numbered list": 0.14, "Statistic": 0.02, "How-to": 0.08, "None": -0.12}
HOOK_WEIGHT = {"Question": 0.17, "Bold claim": 0.15, "Story": 0.14, "Numbered list": 0.14, "Statistic": 0.10, "How-to": 0.16, "None": 0.14}
TONE_EFFECT = {
    "Playful": {"Instagram": 0.08, "TikTok": 0.10, "LinkedIn": -0.08, "X": 0.03},
    "Authoritative": {"Instagram": -0.03, "TikTok": -0.04, "LinkedIn": 0.08, "X": -0.02},
    "Warm": {"Instagram": 0.04, "TikTok": 0.04, "LinkedIn": 0.04, "X": 0.03},
    "Direct": {"Instagram": 0.0, "TikTok": 0.0, "LinkedIn": 0.02, "X": 0.06},
}
TOPIC_EFFECT = {
    "Customer stories": 0.12, "Education": 0.10, "Product tips": 0.06, "Behind the scenes": 0.04,
    "Industry takes": 0.0, "Launches": -0.06, "Team culture": 0.02,
}
TOPIC_WEIGHT = {"Customer stories": 0.12, "Education": 0.18, "Product tips": 0.20, "Behind the scenes": 0.14,
                "Industry takes": 0.14, "Launches": 0.10, "Team culture": 0.12}
CTA_EFFECT = {"Instagram": -0.04, "LinkedIn": 0.05, "TikTok": 0.02, "X": -0.06}
HOURS = {
    "Instagram": ([7, 8, 12, 13, 17, 18, 19, 20, 21], [2, 2, 3, 3, 2, 3, 4, 4, 2]),
    "LinkedIn": ([7, 8, 9, 12, 13, 17, 18], [4, 4, 3, 3, 2, 2, 1]),
    "TikTok": ([12, 15, 18, 19, 20, 21, 22], [2, 2, 3, 4, 4, 3, 2]),
    "X": ([8, 9, 12, 13, 15, 17, 19], [3, 3, 3, 2, 2, 2, 2]),
}
MIX = {  # likes, comments, shares, saves
    "Instagram": (0.78, 0.05, 0.07, 0.10),
    "LinkedIn": (0.80, 0.09, 0.05, 0.06),
    "TikTok": (0.72, 0.05, 0.15, 0.08),
    "X": (0.70, 0.07, 0.18, 0.05),
}

SUBJECTS = {
    "Product tips": ["dashboard filters", "weekly reports", "shared workspaces", "keyboard shortcuts"],
    "Behind the scenes": ["our design sprint", "the roadmap wall", "a week of user calls", "the studio setup"],
    "Customer stories": ["a retail design team", "a two-person studio", "an agency in Lisbon", "a nonprofit comms team"],
    "Industry takes": ["vanity metrics", "the attention economy", "creative burnout", "AI in design workflows"],
    "Launches": ["Northwind Reports 2.0", "the new timeline view", "team templates", "the public API"],
    "Team culture": ["our no-meeting Wednesdays", "async standups", "demo day", "our reading list"],
    "Education": ["content calendars", "A/B testing basics", "reading engagement data", "brief writing"],
}
HOOKS = {
    "Question": ["Why do most teams ignore {s}?", "What if {s} is the real bottleneck?", "Still guessing about {s}?"],
    "Bold claim": ["Nobody talks about {s} honestly.", "{s} is the most underrated lever on your team.", "Stop treating {s} as an afterthought."],
    "Story": ["Last spring we nearly gave up on {s}.", "A customer once told us something about {s} we never forgot.", "Three years ago, {s} was a mess for us."],
    "Numbered list": ["5 things we learned about {s}.", "3 mistakes teams make with {s}.", "7 quick wins for {s}."],
    "Statistic": ["68% of teams we surveyed struggle with {s}.", "We measured {s} across 40 teams. The spread was huge.", "Teams that fix {s} early ship noticeably faster."],
    "How-to": ["How to get more out of {s} in ten minutes.", "A simple way to rethink {s}.", "How we set up {s}, step by step."],
    "None": ["{S}.", "{S}, again.", "Notes on {s}."],
}
BODY = {
    "Product tips": ["Start with one saved view and build from there.", "Small defaults compound across a whole quarter.", "Pin the three numbers you check every Monday.", "Share the view instead of a screenshot so it stays live.", "Most teams never touch the advanced filters, and that is fine.", "Try one change this week and compare against last week."],
    "Behind the scenes": ["The messy middle is where the useful decisions happen.", "We keep the whiteboard up long after the sprint ends.", "Half of what we ship starts as a hallway comment.", "Nothing here is staged, this is just a Tuesday.", "We argue a lot, mostly about naming things.", "The team rotates who presents each Friday."],
    "Customer stories": ["They went from monthly guesses to weekly decisions.", "The turning point was a single comparison chart.", "Their team of four now reviews results every Friday.", "The outcome surprised even them.", "They kept what worked and dropped the rest.", "Nothing fancy, just a consistent habit."],
    "Industry takes": ["Counting the wrong thing precisely is still wrong.", "Most dashboards reward activity, not learning.", "The loudest metric is rarely the most useful one.", "Fast feedback beats perfect measurement.", "Teams copy tactics and skip the reasoning behind them.", "The honest answer is usually: it depends, so test it."],
    "Launches": ["It is live for every workspace today.", "We rebuilt it from user feedback, line by line.", "The old flow still works if you prefer it.", "Early users cut their weekly reporting time noticeably.", "Docs and examples are ready, and so is the changelog.", "We would love to hear what is missing."],
    "Team culture": ["We protect focus time on purpose.", "Writing things down saves everyone an hour a week.", "Nobody is expected to reply instantly.", "Rituals matter more than perks.", "New joiners ship something in week one.", "It is a small habit with a large payoff."],
    "Education": ["Change one variable at a time or you learn nothing.", "A single post is an anecdote, a pattern is evidence.", "Write the hypothesis before you look at the numbers.", "Sample size decides how much you can trust a difference.", "Compare like with like: same platform, same format.", "Keep a log of what you tried and what happened."],
}
CTAS = ["Save this for your next planning session.", "Comment with your take.", "Share this with a teammate who needs it.", "Follow for more weekly breakdowns.", "Tell us what you would add.", "Try it and let us know how it goes."]
TAGS = {
    "Product tips": ["#productivity", "#saas", "#workflow", "#tips"], "Behind the scenes": ["#bts", "#studiolife", "#design", "#teamwork"],
    "Customer stories": ["#customerstory", "#casestudy", "#results", "#community"], "Industry takes": ["#marketing", "#strategy", "#analytics", "#opinion"],
    "Launches": ["#launch", "#newrelease", "#product", "#update"], "Team culture": ["#culture", "#remotework", "#teams", "#hiring"],
    "Education": ["#learning", "#howto", "#contentstrategy", "#data"],
}
EMOJIS = ["✨", "🚀", "📊", "💡", "🔥", "🙌", "✅"]


def _choice(rng: np.random.Generator, items: list, p: list[float] | None = None):
    if p is not None:
        arr = np.asarray(p, dtype=float)
        p = list(arr / arr.sum())
    return items[int(rng.choice(len(items), p=p))]


def build_caption(rng: np.random.Generator, platform: str, topic: str, hook: str, tone: str, target_len: int,
                  force_cta: bool | None = None, force_question: bool | None = None) -> str:
    subject = _choice(rng, SUBJECTS[topic])
    opener = _choice(rng, HOOKS[hook]).format(s=subject, S=subject[0].upper() + subject[1:])
    if force_question is True and "?" not in opener:
        opener = opener.rstrip(".") + "?"
    if force_question is False:
        opener = opener.replace("?", ".")
    parts = [opener]
    pool = list(BODY[topic])
    rng.shuffle(pool)
    while sum(len(p) + 1 for p in parts) < target_len and pool:
        parts.append(pool.pop())
    if tone == "Direct":
        parts = [p.replace(", and ", ". ").replace(", so ", ". ") for p in parts]
    if tone == "Warm":
        parts.insert(1, "We have been there too.")
    has_cta = bool(rng.random() < 0.38) if force_cta is None else force_cta
    if has_cta:
        parts.append(_choice(rng, CTAS))
    text = " ".join(parts)
    if tone == "Playful" or (tone == "Warm" and rng.random() < 0.4):
        n_emoji = int(rng.integers(1, 4)) if platform != "LinkedIn" else int(rng.integers(0, 2))
        text += " " + " ".join(_choice(rng, EMOJIS) for _ in range(n_emoji)) if n_emoji else ""
    n_tags = {"Instagram": int(rng.integers(2, 10)), "LinkedIn": int(rng.integers(0, 6)),
              "TikTok": int(rng.integers(2, 7)), "X": int(rng.integers(0, 4))}[platform]
    if n_tags:
        tags = list(TAGS[topic]) + ["#brand", "#growth", "#creative", "#design", "#teams", "#data"]
        text += "\n" + " ".join(tags[:n_tags])
    return text


def expected_log_er(*, platform: str, format: str, topic: str, hook: str, tone: str, hour: int, dow: int,
                    caption: str, days_since_start: float) -> float:
    """Hidden simulator effect model (log engagement rate). Not used by analytics."""
    f = extract_text_features(caption)
    cfg = PLATFORMS[platform]
    v = math.log(cfg["base"])
    v += FORMATS[platform][format][1] + HOOK_EFFECT[hook] + TONE_EFFECT[tone][platform] + TOPIC_EFFECT[topic]
    weekend = dow >= 5
    if platform == "Instagram":
        v += 0.07 if 18 <= hour <= 21 else (0.02 if 12 <= hour <= 13 else 0.0)
        v += 0.03 if weekend else 0.0
        v += -0.012 * (f.hashtag_count - 5) ** 2 / 4 + 0.02 * min(f.emoji_count, 3)
    elif platform == "LinkedIn":
        v += 0.08 if (7 <= hour <= 9 and not weekend) else (0.02 if 12 <= hour <= 13 else 0.0)
        v += -0.12 if weekend else 0.0
        v += -0.03 * max(f.hashtag_count - 3, 0) - 0.04 * max(f.emoji_count - 1, 0)
    elif platform == "TikTok":
        v += 0.08 if 19 <= hour <= 22 else 0.0
        v += -0.006 * (f.hashtag_count - 4) ** 2 / 2 + 0.015 * min(f.emoji_count, 3)
    else:
        v += 0.04 if 8 <= hour <= 9 else (0.03 if 12 <= hour <= 13 else 0.0)
        v += -0.05 if weekend else 0.0
        v += -0.07 * max(f.hashtag_count - 1, 0)
    v += -0.14 * ((math.log(max(f.caption_length, 20)) - math.log(cfg["opt_len"])) / 0.6) ** 2
    v += 0.06 if f.has_question else 0.0
    v += CTA_EFFECT[platform] if f.has_cta else 0.0
    v += 0.0004 * days_since_start
    return v


def _split_engagement(rng: np.random.Generator, platform: str, format: str, has_question: bool, n_eng: int):
    likes, comments, shares, saves = MIX[platform]
    if format == "Carousel":
        saves *= 1.8
    if format in ("Reel", "Video"):
        shares *= 1.5
    if format in ("Text", "Thread"):
        comments *= 1.5
    if has_question:
        comments *= 1.4
    p = np.array([likes, comments, shares, saves])
    p = p * rng.dirichlet(np.full(4, 60.0)) * 4
    p = p / p.sum()
    return [int(x) for x in rng.multinomial(n_eng, p)]


def simulate_metrics(rng: np.random.Generator, *, platform: str, format: str, topic: str, hook: str, tone: str,
                     published_at: datetime, caption: str, start: datetime, noise_sd: float = 0.18) -> dict:
    days = (published_at - start).total_seconds() / 86400
    cfg = PLATFORMS[platform]
    span = 540.0
    frac = min(max(days / span, 0), 1)
    followers = cfg["followers"][0] + (cfg["followers"][1] - cfg["followers"][0]) * frac
    mult = FORMATS[platform][format][2]
    sd = 0.7 if platform == "TikTok" else 0.42
    impressions = max(int(followers * mult * math.exp(rng.normal(0, sd))), 80)
    log_er = expected_log_er(platform=platform, format=format, topic=topic, hook=hook, tone=tone,
                             hour=published_at.hour, dow=published_at.weekday(), caption=caption, days_since_start=days)
    log_er += rng.normal(0, noise_sd)
    if rng.random() < 0.02:  # occasional breakout post
        log_er += 0.5
    er = min(math.exp(log_er), 0.5)
    n_eng = int(rng.binomial(impressions, er))
    f = extract_text_features(caption)
    likes, comments, shares, saves = _split_engagement(rng, platform, format, f.has_question, n_eng)
    reach = int(impressions * rng.uniform(0.72, 0.92))
    return dict(impressions=impressions, reach=reach, likes=likes, comments=comments, shares=shares, saves=saves)


def generate_posts(n: int, as_of: datetime, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    start = as_of - timedelta(days=540)
    end = as_of - timedelta(days=3)  # recent posts have immature metrics
    total_days = (end - start).days
    plats = list(PLATFORMS)
    records: list[dict] = []
    for i in range(n):
        platform = _choice(rng, plats, [PLATFORMS[p]["weight"] for p in plats])
        fmts = list(FORMATS[platform])
        fmt = _choice(rng, fmts, [FORMATS[platform][f][0] for f in fmts])
        topic = _choice(rng, list(TOPIC_WEIGHT), list(TOPIC_WEIGHT.values()))
        hook = _choice(rng, list(HOOK_WEIGHT), list(HOOK_WEIGHT.values()))
        tone = _choice(rng, list(TONE_EFFECT))
        day = start + timedelta(days=int(rng.integers(0, total_days)))
        shift_weekend = rng.random() < 0.8  # always drawn so the stream does not depend on the calendar
        if platform == "LinkedIn" and day.weekday() >= 5 and shift_weekend:
            day += timedelta(days=int(7 - day.weekday()))
            if day > end:
                day -= timedelta(days=7)
        hours, w = HOURS[platform]
        hour = _choice(rng, hours, w)
        published = day.replace(hour=hour, minute=int(rng.integers(0, 60)), second=0, microsecond=0)
        target_len = int(rng.lognormal(math.log(PLATFORMS[platform]["opt_len"]), 0.55))
        target_len = max(target_len, 40)
        caption = build_caption(rng, platform, topic, hook, tone, target_len)
        metrics = simulate_metrics(rng, platform=platform, format=fmt, topic=topic, hook=hook, tone=tone,
                                   published_at=published, caption=caption, start=start)
        records.append(dict(
            external_id=f"{platform[:2].upper()}-{i + 1:05d}", platform=platform, format=fmt, topic=topic,
            hook_type=hook, tone=tone, caption=caption, published_at=published.isoformat(),
            media_count={"Carousel": int(rng.integers(3, 9)), "Thread": int(rng.integers(3, 8))}.get(fmt, 1), **metrics,
        ))
    return records
