"""100 real-world theme strings customers would actually type.

Used by scripts/theme_loop.py to measure how often the dynamic theme engine
produces a *meaningful* skin (not the generic fallback) and to catch themes
that should match a motif but don't.
"""
# (theme text, expected motif or None if "generic fallback is acceptable")
SAMPLES = [
    # --- superhero / franchise-adjacent (10)
    ("Spider-Man", "web"), ("spiderman", "web"), ("Spider-Man: No Way Home", "web"),
    ("Superhero training academy", "burst"), ("Batman", "burst"), ("Avengers assemble", "burst"),
    ("Wonder Woman", "burst"), ("comic book heroes", "burst"), ("Marvel madness", "burst"),
    ("superhero squad", "burst"),
    # --- ice / winter (10)
    ("Frozen", "snow"), ("Frozen 2", "snow"), ("Winter wonderland", "snow"),
    ("Elsa and Anna", "snow"), ("ice princess", "snow"), ("snowflake sparkle", "snow"),
    ("arctic adventure", "snow"), ("polar express", "snow"), ("snow day", "snow"),
    ("winter ball", "snow"),
    # --- space (10)
    ("Space adventure", "stars"), ("Outer space", "stars"), ("Astronaut academy", "stars"),
    ("rocket launch", "stars"), ("galaxy far away", "stars"), ("Star Wars", "stars"),
    ("planets and moons", "stars"), ("cosmic birthday", "stars"), ("moon landing", "stars"),
    ("starry night", "stars"),
    # --- sea (10)
    ("Under the Sea", "waves"), ("Mermaid lagoon", "waves"), ("Ocean explorers", "waves"),
    ("Shark week", "waves"), ("pirate ship", "waves"), ("nautical nonsense", "waves"),
    ("beach bash", "waves"), ("fish and friends", "waves"), ("water park", "waves"),
    ("deep sea diving", "waves"),
    # --- dino / jungle (10)
    ("Dinosaurs", "leaves"), ("Dino explorers", "leaves"), ("Jurassic party", "leaves"),
    ("Jungle safari", "leaves"), ("Safari adventure", "leaves"), ("Zoo animals", "leaves"),
    ("Forest friends", "leaves"), ("wild things", "leaves"), ("animal kingdom", "leaves"),
    ("T-rex takeover", "leaves"),
    # --- unicorn / magic (10)
    ("Unicorn magic", "confetti"), ("Rainbow unicorn", "confetti"), ("Fairy garden", "confetti"),
    ("Magic show", "confetti"), ("My little pony", "confetti"), ("rainbow party", "confetti"),
    ("enchanted forest", "leaves"), ("wizard school", "confetti"), ("fairy tale", "confetti"),
    ("magical mystery", "confetti"),
    # --- racing (8)
    ("Racing cars", "checkers"), ("Race day", "checkers"), ("Formula 1", "checkers"),
    ("Hot wheels", "checkers"), ("Monster trucks", "checkers"), ("speed racer", "checkers"),
    ("motor mania", "checkers"), ("race track", "checkers"),
    # --- music / disco (8)
    ("Disco party", "notes"), ("Neon nights", "notes"), ("Dance party", "notes"),
    ("Pop star", "notes"), ("Karaoke night", "notes"), ("DJ battle", "notes"),
    ("concert vibes", "notes"), ("music festival", "notes"),
    # --- love / other (6)
    ("Sweetheart soiree", "hearts"), ("Valentine tea", "hearts"), ("Love and laughter", "hearts"),
    ("hearts and roses", "hearts"), ("valentines day", "hearts"), ("sweetheart 16", "hearts"),
    # --- generic / no strong signal — fallback is CORRECT (10)
    ("Birthday bash", None), ("Garden party", None), ("Tea party", None),
    ("Backyard BBQ", None), ("Retirement lunch", None), ("Graduation", None),
    ("Baby shower", None), ("Company family day", None), ("Sleepover", None),
    ("", None),
    # --- messy real-world input (8)
    ("SPIDER-MAN!!!", "web"), ("frozen (elsa theme)", "snow"), ("  space  ", "stars"),
    ("under-the-sea", "waves"), ("Dino's 5th 🦕", "leaves"), ("racing 🏎️ cars", "checkers"),
    ("Disco/70s", "notes"), ("un-i-corn", None),
]
assert len(SAMPLES) == 100, len(SAMPLES)
