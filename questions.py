"""Prompts and example hints for each game mode."""

QUESTIONS = {
    "Bestie Mode": (
        ("What does your perfect weekend look like?", "A slow morning, a hike, or a late-night catch-up?"),
        ("What do you enjoy doing in your free time?", "Think about a hobby or something you do to unwind."),
        ("Where or what do you love to eat?", "A favourite dish, a hawker stall, or somewhere cosy?"),
        ("Where would you love to go on holiday?", "Think about the destination and what you would do there."),
        ("What makes a friendship special to you?", "Think about the little things you value in a friend."),
    ),
    "Couple Mode": (
        ("What does your perfect date look like?", "A quiet dinner, a day out, or something unexpected?"),
        ("How do you like to spend time together?", "Think about an everyday moment you look forward to."),
        ("What makes you feel appreciated?", "A thoughtful gesture, a kind word, or practical help?"),
        ("What would your dream holiday together look like?", "Picture where you would go and how you would spend a day."),
        ("What matters most to you in a relationship?", "Think about a value or habit that matters to you."),
    ),
}

QUESTION_COUNT = 5

# One category per prompt, in the same order as QUESTIONS.
QUESTION_CATEGORIES = {
    "Bestie Mode": ("Everyday life", "Everyday life", "Experiences", "Experiences", "Connection"),
    "Couple Mode": ("Experiences", "Everyday life", "Connection", "Experiences", "Connection"),
}
