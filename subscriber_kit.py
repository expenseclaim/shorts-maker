"""
subscriber_kit.py - adds subscriber-focused metadata to each shorts-bot upload.

Drop this file into the root of the shorts-bot repo. For every video it builds:
  - a title (<= 60 characters, ends with #shorts)
  - a description with a subscribe line and a comment question
  - a closing voice-over line that invites a follow
  - a first comment to post (pin it by hand in YouTube Studio)
  - hashtags and tags

Wording rotates and is remembered in state/subscriber_kit_history.json,
so the same title or outro pattern is not reused on back-to-back videos.

Usage in your pipeline:

    from subscriber_kit import build_kit

    kit = build_kit(video)            # video = one object from the queue JSON
    video["title"] = kit["title"]
    video["description"] = kit["description"]
    video["tags"] = kit["tags"]
    video["script"].append({"line": kit["outro_line"],
                            "visual": "text overlay: Follow for daily tech tips"})
    # after upload (needs the youtube.force-ssl scope):
    # post_first_comment(youtube, video_id, kit["first_comment"])
"""

import hashlib
import json
import os
import random
import re

CHANNEL_NAME = os.environ.get("CHANNEL_NAME", "Papzz")
HISTORY_FILE = os.environ.get("SUBSCRIBER_KIT_HISTORY", "state/subscriber_kit_history.json")
MAX_TITLE = 60

TITLE_PATTERNS = [
    "How to {topic} ({device})",
    "Hidden {device} trick: {topic}",
    "{Topic} in 5 seconds",
    "{device} tip: {topic}",
    "You didn't know {device_phrase} could {topic}",
    "Easiest way to {topic} on {device}",
    "Stop wasting time: {topic}",
]

SUBSCRIBE_LINES = [
    "New tech tips every day. Subscribe to {channel} so you catch the next one.",
    "One quick tech tip a day on {channel}. Subscribe if this helped.",
    "Subscribe to {channel} for daily tips that save you time.",
    "Want more tricks like this? {channel} posts one every day. Subscribe.",
]

QUESTIONS = [
    "Which tip should I show next? Tell me in the comments.",
    "Did this work on your device? Comment your model.",
    "What tech problem annoys you most? I might make a short on it.",
    "Did you already know this one? Yes or no in the comments.",
]

OUTROS = [
    "Follow for one new tech trick every day.",
    "Follow so tomorrow's tip finds you.",
    "Follow for more tricks your phone hides.",
    "There's a new tip tomorrow. Follow so you don't miss it.",
]

FIRST_COMMENTS = [
    "Did this work for you? Reply with your device model and I'll check the steps.",
    "Next tip drops tomorrow. Which one do you want: battery, privacy or speed?",
    "Tell me a tech task you do the slow way, and I'll find a shortcut for it.",
]

STOPWORDS = {"with", "your", "from", "into", "that", "this", "without", "using", "phone", "the", "and", "for"}

DEVICES = {
    "android": "Android", "iphone": "iPhone", "ios": "iPhone", "windows": "Windows",
    "mac": "Mac", "macos": "Mac", "chrome": "Chrome", "wifi": "Wi-Fi", "wi-fi": "Wi-Fi",
}


def _load_history():
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_history(history):
    os.makedirs(os.path.dirname(HISTORY_FILE) or ".", exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def _choose(rng, options, key, history):
    """Pick an option, avoiding the last two used for this slot."""
    recent = history.get(key, [])[-2:]
    fresh = [i for i in range(len(options)) if i not in recent] or list(range(len(options)))
    i = rng.choice(fresh)
    history[key] = (history.get(key, []) + [i])[-10:]
    return options[i]


def _guess_device(video):
    text = " ".join(str(video.get(k, "")) for k in ("topic", "bucket", "title")).lower()
    for word, name in DEVICES.items():
        if re.search(r"\b" + re.escape(word) + r"\b", text):
            return name
    return "phone"


def _clean_topic(topic):
    topic = re.sub(r"[.?!]+$", "", topic.strip())
    topic = re.sub(r"^how to\s+", "", topic, flags=re.I)
    return topic[:1].lower() + topic[1:] if topic else "a hidden tech trick"


def _hashtags(device, topic):
    words = [w for w in re.findall(r"[a-z0-9]+", topic.lower()) if len(w) > 3 and w not in STOPWORDS]
    tags = ["#shorts", "#techtips", "#" + re.sub(r"[^a-z0-9]", "", device.lower()) + "tips"]
    tags += ["#" + w for w in words[:2]]
    seen, out = set(), []
    for t in tags:
        if len(t) > 1 and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:5]


def build_kit(video, channel=CHANNEL_NAME, save=True):
    """Return subscriber-focused metadata for one queued video."""
    topic = _clean_topic(video.get("topic") or video.get("title") or "")
    device = video.get("device") or _guess_device(video)
    device_phrase = "your phone" if device == "phone" else "your " + device
    seed = int(hashlib.sha256((video.get("id", "") + topic).encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    history = _load_history()

    fill = {"topic": topic, "Topic": topic[:1].upper() + topic[1:], "device": device.title() if device == "phone" else device,
            "device_phrase": device_phrase, "channel": channel}

    # Title: rotate patterns, fall back to a shorter one if it runs long.
    title = _choose(rng, TITLE_PATTERNS, "title", history).format(**fill)
    if len(title) > MAX_TITLE - 8:
        named = device.lower() in topic.lower() or device == "phone"
        title = ("{Topic}" if named else "{Topic} ({device})").format(**fill)
    if len(title) > MAX_TITLE - 8:
        title = title[: MAX_TITLE - 9].rstrip() + "…"
    title += " #shorts"

    hashtags = _hashtags(device, topic)
    summary = video.get("description", "").split("\n\n")[0].strip() or \
        "How to {topic}, step by step in under a minute.".format(**fill)

    description = "\n\n".join([
        summary,
        _choose(rng, SUBSCRIBE_LINES, "subscribe", history).format(**fill),
        _choose(rng, QUESTIONS, "question", history),
        " ".join(hashtags),
    ])

    tags = list(dict.fromkeys((video.get("tags") or []) + [h.lstrip("#") for h in hashtags] + [device.lower() + " tips", "tech tips"]))[:15]

    kit = {
        "title": title,
        "description": description,
        "outro_line": _choose(rng, OUTROS, "outro", history),
        "first_comment": _choose(rng, FIRST_COMMENTS, "comment", history),
        "hashtags": hashtags,
        "tags": tags,
    }
    if save:
        _save_history(history)
    return kit


def post_first_comment(youtube, video_id, text):
    """Post the first comment with the YouTube Data API (scope: youtube.force-ssl).
    The API cannot pin comments, so pin it in YouTube Studio (or the YouTube app)."""
    return youtube.commentThreads().insert(
        part="snippet",
        body={"snippet": {"videoId": video_id,
                          "topLevelComment": {"snippet": {"textOriginal": text}}}},
    ).execute()


if __name__ == "__main__":
    sample = {"id": "2026-11-18-01", "bucket": "Hidden phone settings",
              "topic": "Scan documents with your Android camera", "tags": ["android", "document scanner"]}
    print(json.dumps(build_kit(sample, save=False), indent=2))
