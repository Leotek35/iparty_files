"""The Party Concept composer — a deterministic creative engine.

A party is not a shopping list; it is a concept with a signature moment, a
table that matches it, a sweet moment, a look, and a run of show. The composer
turns a request into that concept from catalog v2, offline and in
milliseconds, so every host gets a *good* party even when no model is reachable
— and the model backend starts from this verified baseline instead of a blank
page.

How it reads a request
  * `profile_for` reads the honoree's age into a band (toddler → adult), the
    theme into an occasion, moods, cuisines and weighted keywords (direct words
    count 1.0, synonyms 0.6), the budget into a tier, and the dietary picture
    (including needs the theme states outright, e.g. "Halal Engagement").
  * `affinity` scores every eligible item for that profile: keyword hits,
    palette match, cuisine identity, niche/needs gates, certifications, moods,
    tier distance. It is what keeps a fire performer off a toddler's party and
    marigolds off a Burns supper.
  * `_compose_once` fills slots in a signature-first order with a held-back
    reserve for the essentials, picks by affinity + budget fit + a seeded
    jitter, de-duplicates by vocabulary, and writes the story, moments and
    schedule. Three passes (as asked → essential tier → loose) guarantee a
    verified draft whenever one exists; `baseline_draft` in the LLM client
    falls back to the cheapest compliant plan after that.

Everything here is pure and seeded: the same request and variant always give
the same concept, which is what makes it testable and portable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..pricing.catalog import TIERS, Catalog, CatalogItem, DietContext, dietary_context
from .feasibility import KOSHER_SUPERVISION_SKU, eligible, units_to_cover
from .grounding import ground_draft
from .models import Moment, PartyRequest, PlanDraft, ScheduleSlot, Selection
from .verifier import verify_plan

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------
BANDS = (("toddler", 1, 4), ("kids", 5, 8), ("tween", 9, 12), ("teen", 13, 17), ("adult", 18, 120))
BAND_SEGMENTS = {b: ("seg:" + b, "seg:all") for b, _, _ in BANDS}

# Ordered: the first family whose word appears wins, so specific occasions
# come before generic ones.
OCCASIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("first_birthday", ("1st birthday", "first birthday", "one year", "turning one", "cake smash")),
    ("sweet16", ("sweet 16", "sweet sixteen")),
    ("quince", ("quince", "quinceañera", "quinceanera", "xv años")),
    ("mitzvah", ("mitzvah",)),
    ("wedding", ("wedding", "shaadi", "sangeet", "mehndi", "nikah", "reception", "vow renewal", "elopement")),
    ("engagement", ("engagement", "proposal")),
    ("bridal", ("bridal shower", "bachelorette", "bachelor party", "hen do", "hen party", "stag")),
    ("baby_shower", ("baby shower", "sprinkle", "gender reveal", "sip and see", "sip & see")),
    ("welcome", ("naming ceremony", "naming", "100-day", "100 day", "baptism", "christening", "bris", "aqiqah", "dedication", "doljanchi")),
    ("anniversary", ("anniversary",)),
    ("graduation", ("graduation", "grad party", "commencement")),
    ("retirement", ("retirement", "farewell", "send-off", "send off")),
    ("housewarming", ("housewarming", "house warming", "new home")),
    ("reunion", ("reunion", "friendsgiving", "family gathering", "get-together", "get together")),
    ("holiday", ("christmas", "halloween", "hanukkah", "diwali", "eid", "lunar new year", "losar", "new year", "juneteenth",
                 "pride", "thanksgiving", "valentine", "midsummer", "moon festival", "mid-autumn", "muertos", "burns",
                 "slava", "easter", "holi", "nowruz", "oktoberfest", "st patrick", "st. patrick")),
    ("gala", ("gala", "fundraiser", "charity", "ball", "benefit", "auction", "debutante", "vernissage")),
    ("corporate", ("launch", "product reveal", "reveal", "series a", "series b", "summit", "offsite", "hackathon", "meetup",
                   "expo", "pitch", "demo day", "conference", "networking", "client", "team event", "company", "vc dinner",
                   "investor", "awards", "takeover", "pop-up", "pop up", "podcast", "release", "cupping", "masterclass", "lab",
                   "session", "studio", "tournament", "slam", "gig", "cinema", "takeover", "test")),
    ("birthday", ("birthday", "bday", "b-day", "turning", "golden")),
)
_ORDINAL = re.compile(r"\b(\d{1,3})(st|nd|rd|th)\b")

MOOD_WORDS: dict[str, tuple[str, ...]] = {
    "elegant": ("elegant", "chic", "black tie", "gala", "formal", "luxury", "luxe", "couture", "classy", "sophisticated",
                "soirée", "soiree", "omakase", "kaiseki", "tasting", "wine", "champagne", "anniversary", "vernissage", "polo",
                "debutante", "haute", "cellar", "ballroom", "golden", "watch", "executive", "vc dinner", "auction", "yacht",
                "wedding", "engagement"),
    "playful": ("fun", "silly", "carnival", "circus", "bounce", "play", "games", "arcade", "wild", "pet", "puppy", "dog"),
    "glow": ("neon", "glow", "blacklight", "rave", "disco", "8-bit", "dance", "club"),
    "cozy": ("cozy", "cosy", "book", "movie", "film", "cinema", "board game", "boardgame", "game night", "friendsgiving",
             "tea", "fireside", "vinyl", "podcast", "poetry", "craft", "sip", "retirement", "housewarming"),
    "outdoor": ("backyard", "bbq", "barbecue", "cookout", "picnic", "park", "beach", "garden", "camp", "bonfire", "tailgate",
                "braai", "luau", "festival", "field day", "pool", "lawn", "farm", "island", "midsummer", "reunion"),
    "winter": ("winter", "snow", "frozen", "ice", "christmas", "cocoa", "nordic", "ski", "holiday"),
    "brunch": ("brunch", "breakfast", "luncheon", "lunch", "tea party", "afternoon tea", "mimosa", "coffee", "cupping", "morning"),
    "evening": ("night", "evening", "cocktail", "speakeasy", "gatsby", "dinner", "after dark", "club", "lounge", "mystery",
                "gothic", "masquerade", "casino", "rooftop", "gig", "release", "dance", "ball"),
    "wellness": ("spa", "wellness", "yoga", "sound bath", "meditation", "retreat", "self care", "self-care", "pamper",
                 "skincare", "beauty", "glam", "mindful"),
    "nerdy": ("science", "space", "robot", "robotics", "coding", "hackathon", "lan", "esports", "gaming", "gamer", "vr",
              "drone", "escape", "puzzle", "trivia", "tabletop", "boardgame", "board game", "tech", "ai", "3d", "maker",
              "chemistry", "dnd", "stream", "modular", "biotech", "oss", "arcade", "cyberpunk", "test"),
    "retro": ("retro", "vintage", "80s", "90s", "y2k", "throwback", "disco", "arcade", "vinyl", "speakeasy", "gatsby",
              "roller", "8-bit", "decade"),
    "sporty": ("soccer", "football", "basketball", "sports", "laser tag", "nerf", "tournament", "olympics", "field day",
               "ninja", "race", "racing", "tailgate", "golf", "bowling", "trampoline", "polo", "drone racing"),
    "festive": ("fiesta", "carnival", "festival", "celebration", "holi", "diwali", "eid", "lunar", "parade", "owambe",
                "traditional", "sangeet", "mehndi", "quince", "quinceañera", "quinceanera", "shaadi", "midsummer", "slava"),
}
LUXURY_WORDS = ("luxury", "luxe", "vip", "gala", "yacht", "estate", "black tie", "couture", "champagne", "caviar",
                "penthouse", "private island", "island pop-up", "exclusive", "five-star", "bespoke", "haute", "debutante",
                "executive", "vc dinner", "omakase", "kaiseki")

CUISINE_WORDS: dict[str, tuple[str, ...]] = {
    "mexican": ("mexican", "taco", "fiesta", "quince", "quinceañera", "quinceanera", "muertos", "mariachi", "cinco de mayo", "tex-mex"),
    "italian": ("italian", "pasta", "pizza", "trattoria", "tuscan", "nonna"),
    "indian": ("indian", "desi", "bollywood", "diwali", "holi", "mehndi", "sangeet", "shaadi", "jain", "punjabi", "dosa", "biryani", "hindu"),
    "chinese": ("chinese", "lunar new year", "moon festival", "mid-autumn", "dim sum", "100-day", "100 day", "red egg", "cantonese"),
    "japanese": ("japanese", "sushi", "kaiseki", "omakase", "ramen", "anime", "sakura", "izakaya", "matcha"),
    "korean": ("korean", "k-pop", "kpop", "kbbq", "korean bbq", "doljanchi", "seoul"),
    "thai": ("thai", "songkran"),
    "vietnamese": ("vietnamese", "pho", "tet ", "tết", "banh mi", "bánh mì"),
    "filipino": ("filipino", "boodle", "debut party", "pinoy"),
    "greek": ("greek", "hellenic", "greek baptism"),
    "mediterranean": ("mediterranean",),
    "middle_eastern": ("middle eastern", "arab", "arabic", "lebanese", "eid", "iftar", "ramadan", "halal", "shawarma", "henna night"),
    "turkish": ("turkish", "istanbul"),
    "persian": ("persian", "iranian", "nowruz"),
    "jewish": ("jewish", "kosher", "mitzvah", "hanukkah", "shabbat", "bris", "passover", "glatt", "klezmer", "israeli"),
    "nigerian": ("nigerian", "naija", "owambe", "yoruba", "igbo", "jollof", "aso ebi", "lagos"),
    "african": ("african", "ghanaian", "kenyan", "senegalese", "heritage"),
    "south_african": ("south african", "braai", "heritage braai", "heritage day"),
    "ethiopian": ("ethiopian", "eritrean", "injera"),
    "caribbean": ("caribbean", "jamaican", "trinidad", "cuban", "reggae", "soca", "bahamas", "jerk"),
    "brazilian": ("brazilian", "samba", "churrasco", "carnaval", "rio"),
    "peruvian": ("peruvian", "lima", "ceviche"),
    "spanish": ("spanish", "tapas", "flamenco", "paella", "barcelona"),
    "french": ("french", "parisian", "paris", "bistro", "provence", "patisserie"),
    "german": ("german", "oktoberfest", "bavarian"),
    "scandinavian": ("scandinavian", "swedish", "nordic", "midsummer", "norwegian", "danish", "fika", "hygge"),
    "balkan": ("serbian", "slava", "balkan", "croatian", "bosnian"),
    "scottish": ("scottish", "burns", "ceilidh", "tartan", "highland", "scotch"),
    "irish": ("irish", "st patrick", "st. patrick", "paddy", "celtic"),
    "british": ("british", "english tea", "afternoon tea", "royal tea", "high tea"),
    "american": ("american", "all-american", "4th of july", "fourth of july", "diner", "southern", "tailgate", "cookout"),
    "bbq": ("bbq", "barbecue", "cookout", "smokehouse", "grill"),
    "hawaiian": ("hawaiian", "luau", "aloha", "tiki", "hawaii"),
    "tibetan": ("tibetan", "losar", "nepali", "himalayan", "momo"),
}
POPULAR_CUISINES = frozenset({"mexican", "italian", "american", "bbq"})
SPECIFIC_CUISINES = frozenset(CUISINE_WORDS) - POPULAR_CUISINES

# Theme word -> item vocabulary it also means (weight SYNONYM_HIT).
SYNONYMS: dict[str, tuple[str, ...]] = {
    "dino": ("dinosaur", "prehistoric", "fossil", "rex", "jurassic"), "dinosaur": ("dino", "fossil", "prehistoric", "rex"),
    "jurassic": ("dino", "dinosaur", "fossil"), "space": ("planet", "rocket", "star", "galaxy", "astronaut", "cosmic", "planetarium"),
    "galaxy": ("space", "star", "planet"), "astronaut": ("space", "rocket"), "rocket": ("space", "planet"),
    "mermaid": ("sea", "ocean", "shell", "bubble", "splash", "water"), "ocean": ("sea", "mermaid", "beach", "splash", "water"),
    "sea": ("ocean", "mermaid", "water", "beach"), "pirate": ("treasure", "ship", "captain", "map"),
    "princess": ("castle", "crown", "royal", "tiara", "tea", "pony"), "superhero": ("hero", "cape", "comic"),
    "hero": ("superhero", "cape"), "unicorn": ("rainbow", "sparkle", "magic", "pony"), "rainbow": ("unicorn", "pride", "color"),
    "fairy": ("enchanted", "garden", "woodland", "magic", "harp"), "frozen": ("snow", "ice", "winter"), "winter": ("snow", "ice", "cocoa"),
    "snow": ("winter", "ice", "frozen"), "ice": ("snow", "winter", "frozen"), "minecraft": ("block", "pixel", "brick", "build"),
    "block": ("brick", "pixel", "build"), "gaming": ("arcade", "game", "video", "esports", "console", "level"),
    "gamer": ("gaming", "arcade", "video", "console"), "arcade": ("game", "retro", "pixel", "cabinet"),
    "video": ("game", "console", "gaming"), "fortnite": ("gaming", "video", "nerf"), "roblox": ("gaming", "video", "pixel"),
    "pokemon": ("pocket", "monster", "card"), "soccer": ("sports", "goal", "football", "coach", "pitch"),
    "football": ("soccer", "sports", "tailgate", "pitch"), "sports": ("coach", "soccer", "tournament", "medal"),
    "racing": ("race", "car", "kart", "checkered", "speed"), "race": ("racing", "car", "kart", "checkered"),
    "car": ("racing", "race", "kart"), "neon": ("glow", "blacklight", "uv", "led"), "glow": ("neon", "blacklight", "led", "light", "uv"),
    "music": ("dj", "band", "song", "playlist", "karaoke", "concert", "mic", "live", "trio", "quartet", "singer"),
    "chamber": ("quartet", "classical", "string", "cellist", "pianist", "harpist"), "classical": ("quartet", "string", "cellist", "pianist", "harpist"),
    "jazz": ("trio", "speakeasy", "saxophone", "swing"), "acoustic": ("singer", "songwriter", "guitar"), "concert": ("band", "stage", "music", "dj"),
    "karaoke": ("sing", "mic", "song", "music"), "dance": ("dj", "disco", "floor", "dancers"), "disco": ("dance", "retro", "mirror", "ball"),
    "retro": ("vintage", "throwback", "arcade", "vinyl", "disco"), "spa": ("pamper", "mask", "nail", "wellness", "robe", "facial"),
    "glam": ("makeup", "beauty", "nail", "sparkle"), "pamper": ("spa", "nail", "mask"), "safari": ("jungle", "animal", "zoo", "wild"),
    "jungle": ("safari", "animal", "leaf", "wild"), "animal": ("petting", "zoo", "pony", "safari", "farm"), "zoo": ("animal", "petting", "safari"),
    "wizard": ("magic", "potion", "spell", "wand"), "magic": ("magician", "wizard", "wand", "potion", "spell"),
    "carnival": ("circus", "fair", "booth", "popcorn", "cotton", "candy", "stilt"), "circus": ("carnival", "juggling", "stilt", "big top"),
    "movie": ("cinema", "film", "screening", "popcorn", "projector"), "cinema": ("movie", "film", "screening", "projector"),
    "film": ("movie", "cinema", "screening"), "book": ("reading", "author", "story", "library", "club"),
    "tea": ("afternoon", "scone", "teapot", "ceremony"), "coffee": ("espresso", "barista", "cupping", "roaster"),
    "cupping": ("coffee", "roaster", "origin"), "wine": ("sommelier", "vineyard", "tasting", "cellar", "pairing"),
    "whisky": ("dram", "tasting", "scotch"), "beer": ("brewery", "tap", "taproom", "craft", "keg"), "tap": ("beer", "brewery", "keg"),
    "cocktail": ("mixologist", "bar", "bartender", "shaker"), "bbq": ("grill", "cookout", "smoke", "brisket", "pulled"),
    "cookout": ("bbq", "grill", "burger", "hot dog", "lawn"), "picnic": ("park", "blanket", "lawn", "outdoor"),
    "garden": ("floral", "flower", "terrace", "botanical", "bloom"), "beach": ("sand", "sea", "ocean", "surf", "luau", "shell"),
    "pool": ("swim", "water", "splash", "lifeguard", "slide"), "camp": ("bonfire", "campfire", "smores", "tent", "songs"),
    "science": ("lab", "experiment", "slime", "stem", "mad"), "robot": ("robotics", "build", "stem", "tech"),
    "robotics": ("robot", "build", "stem", "tech"), "tech": ("ai", "hackathon", "coding", "demo", "lan", "wifi"),
    "ai": ("hackathon", "tech", "coding", "demo"), "hackathon": ("mentor", "judging", "coding", "tech", "hack"),
    "lan": ("gaming", "esports", "tournament", "pc", "rig"), "esports": ("gaming", "lan", "tournament", "caster", "stream"),
    "vr": ("virtual", "headset", "arcade"), "escape": ("puzzle", "mystery", "clue", "room"),
    "mystery": ("murder", "detective", "clue", "escape"), "puzzle": ("escape", "trivia", "riddle", "clue"),
    "trivia": ("quiz", "host", "buzzer"), "boardgame": ("board", "tabletop", "library", "cards"),
    "tabletop": ("board", "game master", "dnd", "cafe"), "podcast": ("mic", "studio", "recording", "live", "episode"),
    "poetry": ("slam", "open mic", "mic", "spoken", "poet"), "slam": ("poetry", "mic", "poet"),
    "fashion": ("runway", "models", "pop-up", "designer", "couture"), "couture": ("fashion", "runway", "designer", "gown"),
    "art": ("gallery", "easel", "paint", "exhibition", "curator", "canvas"), "gallery": ("art", "exhibition", "curator"),
    "vernissage": ("gallery", "art", "curator", "champagne", "exhibition"), "pottery": ("clay", "wheel", "ceramic", "studio"),
    "paint": ("canvas", "art", "sip", "easel"), "craft": ("workshop", "kit", "diy", "make", "handmade"), "sip": ("paint", "wine", "canvas"),
    "diy": ("kit", "craft", "homemade"), "yoga": ("wellness", "mat", "flow", "breath"), "wellness": ("yoga", "meditation", "spa", "retreat", "sound"),
    "sound": ("bath", "bowls", "meditation", "gong"), "skincare": ("esthetician", "mask", "serum", "beauty", "lab"),
    "beauty": ("makeup", "glam", "skincare", "masterclass", "artist"), "watch": ("horology", "collector", "loupe", "expert"),
    "vinyl": ("record", "dj", "retro", "crate"), "modular": ("synth", "jam", "gear", "patch"), "drone": ("fpv", "racing", "pilot", "aerial"),
    "laser": ("tagger", "arena", "mission", "tag"), "nerf": ("blaster", "battle", "barricade"),
    "tailgate": ("cornhole", "cooler", "canopy", "sports", "wings"), "yacht": ("charter", "harbor", "crew", "deck"),
    "island": ("beach", "boat", "private", "tropical", "luau"), "speakeasy": ("jazz", "prohibition", "cocktail", "gatsby", "velvet"),
    "gatsby": ("speakeasy", "jazz", "art deco", "1920s"), "masquerade": ("mask", "ball", "black", "gold", "gala"),
    "gala": ("ballroom", "black tie", "plated", "gown", "charity"), "charity": ("gala", "auction", "fundraiser", "benefit", "paddle"),
    "auction": ("gala", "paddle", "charity", "sommelier"), "polo": ("luncheon", "lawn", "hats", "champagne", "garden"),
    "debutante": ("ball", "gown", "waltz", "presentation", "ballroom"), "wedding": ("ceremony", "reception", "first dance", "officiant", "vows", "tier"),
    "barn": ("rustic", "string", "hay", "farm", "lantern"), "sangeet": ("dhol", "bollywood", "dance", "mehndi", "marigold"),
    "mehndi": ("henna", "marigold", "bollywood", "dhol"), "shaadi": ("wedding", "baraat", "dhol", "sangeet", "marigold"),
    "mitzvah": ("hora", "klezmer", "kippot", "motivator", "candle"), "quince": ("waltz", "court", "tiara", "mariachi", "choreographer", "ceremony"),
    "quinceanera": ("quince", "waltz", "tiara", "mariachi", "ceremony"), "quinceañera": ("quince", "waltz", "tiara", "mariachi", "ceremony"),
    "sweet": ("candle", "glam", "drip", "limo", "showpiece"), "sixteen": ("sweet", "candle", "showpiece"),
    "graduation": ("cap", "diploma", "class", "grad"), "grad": ("graduation", "cap", "diploma"),
    "retirement": ("farewell", "memory", "toast", "adventure"), "anniversary": ("golden", "toast", "first dance", "timeline"),
    "baby": ("onesie", "pastel", "gift", "sprinkle", "shower"), "shower": ("pastel", "gift", "games", "baby"),
    "housewarming": ("home", "toast", "tour", "welcome"), "reunion": ("photo", "timeline", "memory", "games", "family"),
    "holiday": ("christmas", "winter", "gift", "santa"), "christmas": ("santa", "winter", "snow", "gift", "tree"),
    "halloween": ("spooky", "pumpkin", "haunted", "costume"), "spooky": ("halloween", "haunted", "pumpkin"),
    "diwali": ("diya", "rangoli", "lights", "indian", "marigold"), "eid": ("crescent", "lantern", "halal"),
    "hanukkah": ("dreidel", "menorah", "latke", "gelt"), "lunar": ("lion", "red", "lantern", "dumpling"),
    "moon": ("lantern", "mooncake", "festival"), "losar": ("prayer", "flag", "momo", "tibetan"),
    "muertos": ("sugar skull", "ofrenda", "marigold", "papel picado"), "juneteenth": ("heritage", "freedom", "red"),
    "pride": ("rainbow", "drag", "parade"), "midsummer": ("flower crown", "maypole", "swedish", "strawberry"),
    "burns": ("haggis", "bagpipe", "tartan", "whisky"), "slava": ("serbian", "roast", "icon", "balkan"),
    "baptism": ("greek", "christening", "godparents", "olive"), "naming": ("blessing", "welcome", "family"),
    "pet": ("dog", "puppy", "treat", "park", "paw"), "dog": ("puppy", "pet", "paw"), "puppy": ("dog", "pet", "paw"),
    "1st": ("first", "smash", "toddler", "one"), "first": ("1st", "smash", "toddler"), "100-day": ("baby", "welcome", "red egg"),
    "product": ("launch", "reveal", "demo", "stage"), "launch": ("reveal", "demo", "stage", "toast"),
    "reveal": ("launch", "demo", "stage", "unveil"), "summit": ("conference", "keynote", "breakout", "executive"),
    "meetup": ("talks", "networking", "pizza", "open source"), "oss": ("open source", "meetup", "coding", "tech"),
    "expo": ("booths", "demo", "stage", "robotics"), "pitch": ("demo", "judges", "investors", "stage"),
    "biotech": ("pitch", "demo", "lab", "tech"), "series": ("launch", "toast", "team", "funding"),
    "executive": ("summit", "boardroom", "plated", "chauffeur"), "vc": ("investor", "dinner", "plated", "wine"),
    "stream": ("studio", "mic", "camera", "gaming"), "studio": ("recording", "mic", "session"),
    "jam": ("session", "synth", "music"), "8-bit": ("chiptune", "pixel", "arcade", "retro"),
    "cyberpunk": ("neon", "mystery", "vr", "tech"), "gothic": ("candelabra", "velvet", "dark", "mystery"),
    "release": ("launch", "listening", "gig", "stage"), "gig": ("band", "stage", "music", "live"),
    "takeover": ("tap", "beer", "brewery"), "kaiseki": ("japanese", "tasting", "chef", "course"),
    "omakase": ("sushi", "chef", "counter", "japanese"), "haute": ("couture", "fashion", "runway", "designer"),
    "medical": ("gala", "charity", "ballroom"),
    "field": ("sports", "lawn", "games", "relay"), "glatt": ("kosher", "supervision"), "kosher": ("supervision", "jewish"),
    "halal": ("certified", "grill", "shawarma"), "jain": ("vegetarian", "indian", "pure"), "vegan": ("plant", "vegetarian"),
    "cocoa": ("winter", "chocolate", "marshmallow"), "bowling": ("lanes", "strike", "retro"),
    "trampoline": ("jump", "bounce"), "ninja": ("obstacle", "course", "warrior"), "obstacle": ("course", "ninja", "race"),
    "swim": ("pool", "water", "splash"), "slime": ("science", "glitter", "craft"), "lego": ("brick", "build", "block"),
    "brick": ("lego", "block", "build"), "cars": ("racing", "race", "kart", "checkered"), "truck": ("monster", "racing", "big"),
    "monster": ("truck", "racing", "big"), "kart": ("racing", "race", "checkered"), "mario": ("kart", "pixel", "mushroom"),
    "bluey": ("blue", "heeler", "dog", "puppy"), "cocomelon": ("melon", "watermelon", "toddler"), "paw": ("puppy", "dog", "rescue"),
    "patrol": ("puppy", "rescue", "dog"), "elsa": ("frozen", "ice", "snow"), "barbie": ("pink", "dream", "glam"),
    "spider": ("web", "hero", "superhero"), "taylor": ("eras", "pop", "concert", "friendship"),
    "eras": ("concert", "pop", "friendship", "music"), "swiftie": ("eras", "concert", "friendship", "music"),
    "tiktok": ("dance", "selfie", "music", "ring light"), "selfie": ("photo", "wall", "booth", "ring light"),
    "photo": ("booth", "photographer", "camera", "backdrop"), "golden": ("gold", "anniversary", "50th", "elegant"),
    "black": ("gold", "masquerade", "elegant"), "gold": ("black", "elegant", "gala"), "pink": ("dream", "coquette", "bow"),
    "coquette": ("bow", "ribbon", "pearl", "pink"), "ballet": ("bow", "coquette", "pink", "dance"),
    "love": ("heart", "valentine", "rose"), "valentine": ("heart", "love", "rose", "chocolate"), "heart": ("love", "valentine"),
    "test": ("playtest", "board", "tabletop", "feedback"),
}
DIRECT_HIT, SYNONYM_HIT, MAX_HITS = 1.0, 0.6, 2.0
HUB_HIT = 0.5          # words so broad they say little on their own ("music", "night", "game")
PHRASE_HIT = 1.0       # a two-word phrase is unambiguous: what it implies counts as direct
_HUB_WORDS = frozenset({"music", "game", "games", "dance", "food", "dinner", "lunch", "night", "fun", "show", "big",
                        "mini", "studio", "session", "lab", "club", "meetup", "pop", "up", "fest", "festival", "release",
                        "secret", "surprise", "class", "experience", "time", "test", "house", "home", "summit", "retreat"})
# Two-word phrases and what they unmistakably mean (weight PHRASE_HIT).
PHRASES: dict[str, tuple[str, ...]] = {
    "chamber music": ("quartet", "classical", "string", "cellist", "pianist", "harpist"),
    "secret gig": ("band", "live", "stage", "singer"), "live music": ("band", "live", "singer", "trio"),
    "sound bath": ("bowls", "meditation", "practitioner", "wellness"), "laser tag": ("tagger", "arena", "mission", "laser"),
    "game night": ("board", "trivia", "cards", "tabletop", "library"), "movie night": ("cinema", "film", "screening", "projector"),
    "secret cinema": ("cinema", "film", "screening", "projector"), "board game": ("tabletop", "library", "board"),
    "boardgame test": ("tabletop", "library", "board", "playtest"), "book club": ("discussion", "reading", "author", "book"),
    "coffee cupping": ("roaster", "origin", "cupping", "barista"), "escape room": ("escape", "puzzle", "clue"),
    "escape puzzle": ("escape", "puzzle", "clue"), "pool party": ("pool", "swim", "splash", "slide"),
    "glow party": ("neon", "glow", "blacklight", "uv"), "paint and sip": ("paint", "canvas", "sip", "instructor"),
    "craft and sip": ("craft", "workshop", "candle", "terrarium", "jewelry", "pottery"), "trivia night": ("trivia", "quiz"),
    "karaoke night": ("karaoke", "sing", "mic"), "dance party": ("dj", "dance", "disco"), "silent disco": ("headphones", "silent"),
    "backyard bbq": ("grill", "bbq", "cookout", "burger", "lawn"), "pizza party": ("pizza",), "wine tasting": ("sommelier", "wine"),
    "wine auction": ("sommelier", "wine", "paddle", "cellar"), "tap takeover": ("beer", "brewery", "tap", "keg"),
    "cocktail hour": ("cocktail", "mixologist", "bartender"),
    "game master": ("tabletop",), "beauty masterclass": ("beauty", "makeup", "artist", "glam"),
    "skincare lab": ("skincare", "esthetician", "serum", "facial"), "watch meetup": ("watch", "horology", "loupe"),
    "vinyl session": ("vinyl", "record", "dj"), "modular jam": ("synth", "modular", "jam"), "stream studio": ("stream", "camera", "mic", "gaming"),
    "live podcast": ("podcast", "mic", "recording", "episode"), "poetry slam": ("poetry", "slam", "mic", "poet"),
    "fashion pop-up": ("runway", "models", "fashion", "rack"), "fashion pop": ("runway", "models", "fashion"),
    "art vernissage": ("gallery", "curator", "exhibition", "easel"), "gothic release": ("gothic", "candelabra", "velvet", "mystery"),
    "tabletop cafe": ("tabletop", "board", "library"), "retro arcade": ("arcade", "cabinet", "pinball", "retro"),
    "vr arcade": ("vr", "headset", "virtual"), "drone racing": ("drone", "fpv", "pilot"), "robotics expo": ("robotics", "robot", "build"),
    "ai hackathon": ("hackathon", "mentor", "coding", "tech"), "lan tournament": ("lan", "tournament", "esports", "pc"),
    "cyberpunk mystery": ("mystery", "murder", "neon", "vr"), "8-bit dance": ("chiptune", "8-bit", "pixel", "dj"),
    "biotech pitch": ("pitch", "demo", "judges", "stage"), "oss meetup": ("meetup", "talks", "open source", "coding"),
    "halal engagement": ("halal", "shawarma", "grill", "henna"), "glatt kosher": ("kosher", "supervision"),
    "kaiseki experience": ("kaiseki", "chef", "course", "japanese"), "jain pure": ("vegetarian", "thali", "indian"),
    "heritage braai": ("braai", "grill", "boerewors"), "burns supper": ("haggis", "bagpiper", "whisky", "tartan"),
    "greek baptism": ("greek", "christening", "olive", "dancers"), "moon festival": ("mooncake", "lantern", "moon"),
    "losar new": ("momo", "prayer", "flag", "tibetan"), "serbian slava": ("serbian", "roast", "balkan"),
    "midsummer feast": ("midsummer", "swedish", "flower crown", "strawberry"), "dia de": ("sugar skull", "ofrenda", "marigold", "muertos"),
    "los muertos": ("sugar skull", "ofrenda", "marigold", "muertos"), "gluten free": ("gluten",),
    "nigerian traditional": ("jollof", "aso", "owambe", "afrobeats", "small chops"), "sweet 16": ("sweet", "candle", "limo", "showpiece"),
    "bar mitzvah": ("mitzvah", "hora", "klezmer", "kippot", "motivator"), "bat mitzvah": ("mitzvah", "hora", "klezmer", "kippot", "motivator"),
    "family reunion": ("reunion", "lawn", "photo", "timeline"), "shaadi": ("baraat", "dhol", "sangeet", "marigold", "bollywood"),
    "sangeet": ("dhol", "bollywood", "mehndi", "marigold"), "mehndi night": ("henna", "marigold", "bollywood", "dhol", "mehndi"), "golden 50th": ("gold", "golden", "anniversary"),
    "surprise 40th": ("surprise",), "21st festival": ("festival", "band", "stage", "beer"), "naming ceremony": ("blessing", "welcome", "family", "baby"),
    "100-day party": ("baby", "welcome", "red egg", "dim sum"), "italian anniversary": ("italian", "pasta", "anniversary"),
    "pet birthday": ("puppy", "paw", "pet", "treat"), "music festival": ("band", "stage", "live", "lawn"),
    "garden brunch": ("garden", "floral", "flower", "tea", "harpist", "terrace"), "garden party": ("garden", "floral", "flower", "lawn", "tea", "harpist"),
    "tea party": ("tea", "teapot", "scone", "harpist"), "spa day": ("spa", "pamper", "nail", "mask", "robe", "facial"),
    "friendsgiving": ("turkey", "pie", "harvest", "potluck", "cozy"), "thanksgiving": ("turkey", "pie", "harvest"), "1st birthday": ("first", "smash", "toddler", "one", "highchair"),
    "retirement tea": ("retirement", "tea", "scone", "farewell"), "diy birthday": ("diy", "kit", "homemade"),
    "under the": ("sea", "ocean", "mermaid"), "the sea": ("sea", "ocean", "mermaid", "shell", "bubble"),
    "black and": ("black", "gold", "masquerade"), "and gold": ("black", "gold", "masquerade"),
}

_STOPWORDS = frozenset({"party", "the", "a", "an", "and", "of", "for", "with", "my", "our", "his", "her", "their", "at", "to",
                        "in", "on", "celebration", "event", "bash", "theme", "themed", "birthday", "style", "day", "big",
                        "little", "super", "mega", "fun", "night", "turns", "turning", "years", "year", "old", "s", "up", "pop",
                        "set", "time", "new", "best", "ever", "ultimate", "epic", "annual"})
_GENERIC_TOKENS = frozenset({"party", "per", "person", "serves", "rental", "kit", "set", "station", "bar", "hr", "pack", "pp",
                             "people", "guest", "guests", "everyone", "home", "backyard", "your", "with", "and", "the", "for",
                             "a", "of", "in", "on", "to", "from", "an", "or", "by", "at", "it", "is", "all", "one", "two",
                             "three", "four", "five", "six", "plus", "kids", "kid", "adult", "adults", "teen", "teens",
                             "service", "mobile", "live", "host", "included", "includes", "delivered", "setup", "up", "own",
                             "we", "you", "our", "their", "who", "what", "small", "mini", "real", "full", "pro", "min",
                             "every", "each", "that", "this", "them", "they", "its", "into", "out", "over", "under",
                             "dozen", "tray", "platter", "box", "boxes", "cart", "table", "tables", "chairs", "day", "night",
                             "hour", "hours", "ft", "no", "not", "any", "more", "most", "then", "than", "when", "where"})
_TRAILING = ("rental", "rentals", "kit", "set", "package", "session", "service")
_SUBSTITUTE_WORDS = ("gluten", "vegan", "kosher", "halal", "nut-free", "plant-based", "vegetarian", "pure veg", "dedicated")
_NO_ARTICLE_ENDINGS = ("s", "service", "hour", "tea", "supervision")
_JITTER = 0.25        # essentials: near-deterministic
_JITTER_OPEN = 0.55   # open slots: ties break differently from party to party
_DIETARY_WORDS = {
    "gluten_free": ("gluten", "celiac", "coeliac", "wheat"), "vegan": ("vegan", "plant"), "vegetarian": ("vegetarian", "veg", "jain"),
    "nut_free": ("nut", "peanut"), "halal": ("halal", "zabiha"), "kosher": ("kosher", "glatt"),
}
TIER_THRESHOLDS = (("essential", 0.0), ("standard", 30.0), ("premium", 80.0), ("luxury", 190.0))

SUGGESTED_THEMES = {
    "toddler": ("Bubbles & Balloons", "Under the Sea", "Safari Babies", "Bluey Backyard"),
    "kids": ("Dino Dig", "Space Explorers", "Superhero Training", "Mermaid Lagoon", "Wizard School", "Carnival"),
    "tween": ("Glow Party", "Minecraft Build", "Spa Day", "Laser Tag Showdown", "Escape Room"),
    "teen": ("Neon Glow", "Music Fest", "Retro Y2K", "Black & Gold Night", "Silent Disco"),
    "adult": ("Backyard Cookout", "Cocktail Hour", "Game Night", "Garden Brunch", "Speakeasy Night", "Taco Fiesta"),
}
ADULT_THEMES = SUGGESTED_THEMES["adult"]
ADULT_PREMIUM_THEMES = ("Black Tie Dinner", "Rooftop Soirée", "Wine Cellar Dinner", "Garden Party")
_OCCASION_PHRASES = {
    "first_birthday": "{name}'s first birthday", "birthday": "{name}'s {ordinal} birthday", "sweet16": "{name}'s Sweet 16",
    "quince": "{name}'s quinceañera", "mitzvah": "{name}'s mitzvah", "wedding": "the wedding", "engagement": "the engagement party",
    "bridal": "the shower", "baby_shower": "the baby shower", "welcome": "the welcome celebration", "anniversary": "the anniversary",
    "graduation": "{name}'s graduation", "retirement": "{name}'s retirement party", "housewarming": "the housewarming",
    "reunion": "the reunion", "holiday": "the holiday party", "gala": "the gala", "corporate": "the event", "gathering": "{name}'s party",
}
_SHED_COURSES = ("drink", "snack", "side", "dessert", "cake")


# ---------------------------------------------------------------------------
# Small deterministic PRNG (mulberry32 over an FNV-1a seed) — trivially
# portable, so the preview engine reproduces every concept bit for bit.
# ---------------------------------------------------------------------------
def _fnv1a(text: str) -> int:
    h = 0x811C9DC5
    for b in text.encode("utf-8"):
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


class Rng:
    def __init__(self, seed: str) -> None:
        self.state = _fnv1a(seed) or 0x9E3779B9

    def random(self) -> float:
        self.state = (self.state + 0x6D2B79F5) & 0xFFFFFFFF
        t = self.state
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0


# ---------------------------------------------------------------------------
# Reading the request
# ---------------------------------------------------------------------------
def word_in(word: str, text: str) -> bool:
    """Whole-word containment: 'ai' must not match 'kaiseki', 'tea' must not match 'steak'."""
    return re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", text) is not None


def need_in(need: str, text: str) -> bool:
    """A needs: word matches whole or as a word stem: 'quince' -> quinceañera, 'grad' -> graduation."""
    return re.search(r"(?<![a-z0-9])" + re.escape(need), text) is not None


def band_for(age: int) -> str:
    for name, lo, hi in BANDS:
        if lo <= age <= hi:
            return name
    return "adult"


def _singular(tok: str) -> str:
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def _tokens(text: str) -> list[str]:
    """Lowercase word tokens, singularized; hyphenated compounds yield the
    compound and its parts ('singer-songwriter' -> singer-songwriter, singer, songwriter)."""
    out: list[str] = []
    for t in re.split(r"[^a-z0-9ñáéíóúü'&-]+", (text or "").lower()):
        if not t or t in {"'", "&", "-"}:
            continue
        out.append(_singular(t))
        if "-" in t:
            out.extend(_singular(part) for part in t.split("-") if part)
    return out


def theme_tokens(theme: str) -> dict[str, float]:
    """Weighted vocabulary a theme asks for: its own words at 1.0, what those
    words also mean at 0.6 ('dino' -> fossil, prehistoric)."""
    raw = [t.strip("'-") for t in _tokens(theme)]
    words = [t for t in raw if t and t not in _STOPWORDS and not t.isdigit()]  # '16' must not match '16 settings'
    out: dict[str, float] = {}
    for w in words:
        out[w] = max(out.get(w, 0.0), HUB_HIT if w in _HUB_WORDS else DIRECT_HIT)
    text = " ".join(_tokens(theme))
    for phrase, implied in PHRASES.items():
        if word_in(phrase, text):
            for syn in implied:
                for s in syn.split():
                    s = _singular(s)
                    if s not in _STOPWORDS:
                        out[s] = max(out.get(s, 0.0), HUB_HIT if s in _HUB_WORDS else PHRASE_HIT)
    pairs = list(zip(words, words[1:], strict=False))
    keys = list(words) + [f"{a} {b}" for a, b in pairs] + [f"{a}-{b}" for a, b in pairs]
    for key in keys:
        for syn in SYNONYMS.get(key, ()):
            for s in syn.split():
                s = _singular(s)
                if s not in _STOPWORDS:
                    out[s] = max(out.get(s, 0.0), SYNONYM_HIT)
    return out


def item_tokens(item: CatalogItem) -> frozenset[str]:
    text = f"{item.name} {item.description} {item.subcategory}"
    for t in item.tags:
        fam, _, val = t.partition(":")
        if fam in {"mood", "cuisine", "style", "needs", "for"}:
            text += " " + val.replace("_", " ").replace("-", " ")
    return frozenset(t.strip("'-") for t in _tokens(text) if t.strip("'-") and t not in _GENERIC_TOKENS)


_TOKEN_CACHE: dict[str, frozenset[str]] = {}


def _cached_tokens(item: CatalogItem) -> frozenset[str]:
    toks = _TOKEN_CACHE.get(item.sku)
    if toks is None:
        toks = item_tokens(item)
        _TOKEN_CACHE[item.sku] = toks
    return toks


def theme_hits(item: CatalogItem, words: dict[str, float]) -> float:
    if not words:
        return 0.0
    toks = _cached_tokens(item)
    return min(MAX_HITS, sum(w for tok, w in words.items() if tok in toks))


def direct_hits(item: CatalogItem, words: dict[str, float]) -> float:
    """Hits from the host's own words (and unambiguous phrases) only — no synonyms."""
    toks = _cached_tokens(item)
    return min(MAX_HITS, sum(w for tok, w in words.items() if w >= DIRECT_HIT and tok in toks))


def occasion_for(theme: str) -> str:
    text = (theme or "").lower()
    for name, keys in OCCASIONS:
        if any(word_in(k, text) for k in keys):
            return name
    if _ORDINAL.search(text):
        return "birthday"
    return "gathering"


def moods_for(theme: str) -> set[str]:
    text = (theme or "").lower()
    return {m for m, words in MOOD_WORDS.items() if any(word_in(w, text) for w in words)}


def cuisines_for(theme: str) -> list[str]:
    text = (theme or "").lower()
    found: list[tuple[int, str]] = []
    for cuisine, words in CUISINE_WORDS.items():
        pos = min((text.find(w) for w in words if word_in(w.strip(), text)), default=-1)
        if pos >= 0:
            found.append((pos, cuisine))
    return [c for _, c in sorted(found)]


def tier_for(per_guest: float, luxury: bool) -> str:
    tier = "essential"
    for name, threshold in TIER_THRESHOLDS:
        if per_guest >= threshold:
            tier = name
    if luxury and TIERS.index(tier) < TIERS.index("premium"):
        tier = "premium"
    return tier


def suggest_theme(request: PartyRequest, variant: int = 0) -> str:
    band = band_for(request.honoree_age)
    per_guest = request.budget / max(1, request.guest_count)
    options = ADULT_PREMIUM_THEMES if band == "adult" and per_guest >= 80 else SUGGESTED_THEMES[band]
    rng = Rng(f"theme|{request.honoree_name}|{request.honoree_age}|{request.guest_count}|{request.budget}|{variant}")
    return options[int(rng.random() * len(options)) % len(options)]


@dataclass
class Profile:
    band: str
    occasion: str
    birthday: bool
    moods: set[str]
    cuisines: list[str]
    words: dict[str, float]
    text: str
    luxury: bool
    tier: str
    per_guest: float
    diet: DietContext
    need_keys: set[str] = field(default_factory=set)
    explicit_moods: set[str] = field(default_factory=set)

    @property
    def avoid(self) -> frozenset[str]:
        return self.diet.avoid

    @property
    def prefer_certs(self) -> frozenset[str]:
        return self.diet.certifications

    @property
    def dietary_needs(self) -> list[str]:
        return [p for p in re.split(r"\s*;\s*", self.diet.text) if p]


def profile_for(request: PartyRequest, tier_override: str | None = None, theme: str | None = None) -> Profile:
    """Read a request. `theme` overrides the host's theme text (the composer
    passes its suggestion when the host left it blank); a blank host theme on
    a 'turning N' request is always a birthday, whatever we suggest."""
    blank = not (request.theme or "").strip()
    theme = request.theme if theme is None else theme
    text = (theme or "").lower()
    band = band_for(request.honoree_age)
    occasion = occasion_for(theme)
    birthday = occasion in {"birthday", "first_birthday", "sweet16", "quince"} or blank or (
        band != "adult" and occasion in {"gathering", "holiday"})
    if band == "adult" and occasion == "gathering" and text.strip() and not blank:
        birthday = False
    if occasion == "gathering" and request.honoree_age == 1:
        occasion, birthday = "first_birthday", True
    per_guest = request.budget / max(1, request.guest_count)
    luxury = any(word_in(w, text) for w in LUXURY_WORDS)
    diet = dietary_context(request)
    need_keys = set()
    for key, words in _DIETARY_WORDS.items():
        if any(w in diet.text.lower() for w in words):
            need_keys.add(key)
    if "wheat" in diet.forbidden:
        need_keys.add("gluten_free")
    if diet.forbidden & {"peanut", "tree_nut"}:
        need_keys.add("nut_free")
    if diet.vegan:
        need_keys |= {"vegan", "vegetarian"}
    elif diet.vegetarian:
        need_keys.add("vegetarian")
    need_keys |= set(diet.certifications)
    explicit = moods_for(theme)
    moods = explicit | OCCASION_MOODS.get(occasion, frozenset())
    return Profile(band=band, occasion=occasion, birthday=birthday, moods=moods, cuisines=cuisines_for(theme),
                   words=theme_tokens(theme), text=text, luxury=luxury,
                   tier=tier_override or tier_for(per_guest, luxury), per_guest=per_guest, diet=diet, need_keys=need_keys,
                   explicit_moods=explicit)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
# Moods an occasion implies even when the theme doesn't say so.
OCCASION_MOODS: dict[str, frozenset[str]] = {
    "wedding": frozenset({"elegant", "evening"}), "gala": frozenset({"elegant", "evening"}),
    "anniversary": frozenset({"elegant"}), "engagement": frozenset({"elegant", "evening"}),
    "corporate": frozenset(), "sweet16": frozenset({"glow", "evening"}), "quince": frozenset({"festive", "elegant"}),
    "mitzvah": frozenset({"festive"}), "baby_shower": frozenset({"brunch"}), "bridal": frozenset({"brunch"}),
    "retirement": frozenset({"cozy"}), "welcome": frozenset({"festive"}), "reunion": frozenset({"outdoor"}),
}
FORMAL_OCCASIONS = frozenset({"wedding", "gala", "anniversary", "engagement", "corporate", "quince", "mitzvah"})
PARTY_OCCASIONS = frozenset({"sweet16", "quince", "mitzvah", "wedding", "birthday", "gala", "anniversary", "engagement", "graduation"})
# Venue kinds each occasion naturally books (+0.9).
OCCASION_VENUES: dict[str, frozenset[str]] = {
    "wedding": frozenset({"ballroom", "barn", "garden", "estate", "beach", "hall"}),
    "gala": frozenset({"ballroom", "estate", "theater", "gallery", "garden"}),
    "corporate": frozenset({"event_space", "loft", "gallery", "studio", "taproom", "rooftop"}),
    "engagement": frozenset({"rooftop", "garden", "restaurant", "loft", "estate"}),
    "anniversary": frozenset({"restaurant", "garden", "estate", "yacht", "rooftop"}),
    "sweet16": frozenset({"loft", "rooftop", "entertainment", "music", "hall"}),
    "quince": frozenset({"ballroom", "hall", "barn"}),
    "mitzvah": frozenset({"hall", "loft", "entertainment", "ballroom"}),
    "baby_shower": frozenset({"restaurant", "garden", "home"}),
    "graduation": frozenset({"restaurant", "hall", "park", "home"}),
    "reunion": frozenset({"park", "hall", "barn", "home"}),
    "holiday": frozenset({"hall", "home", "restaurant"}),
    "welcome": frozenset({"hall", "restaurant", "home", "garden"}), "first_birthday": frozenset({"home", "park", "kids_venue"}),
    "birthday": frozenset({"restaurant", "loft", "rooftop", "entertainment", "home", "park", "kids_venue", "taproom", "garden"}),
    "retirement": frozenset({"restaurant", "garden", "home", "hall"}), "housewarming": frozenset({"home"}),
}
# Activity kinds each occasion naturally books (+0.8).
OCCASION_ACTIVITIES: dict[str, frozenset[str]] = {
    "corporate": frozenset({"tech", "photo", "music", "entertainment"}),
    "gala": frozenset({"music", "effects", "photo", "entertainment"}),
    "wedding": frozenset({"music", "photo", "effects", "ceremony"}),
    "anniversary": frozenset({"music", "photo"}), "engagement": frozenset({"music", "photo"}),
    "birthday": frozenset({"music", "games", "entertainment", "workshop"}),
    "first_birthday": frozenset({"entertainment", "games", "photo"}),
    "sweet16": frozenset({"music", "photo", "effects", "entertainment"}), "quince": frozenset({"music", "photo", "ceremony", "effects"}),
    "mitzvah": frozenset({"music", "entertainment", "photo", "games"}),
    "baby_shower": frozenset({"workshop", "games", "photo"}), "bridal": frozenset({"workshop", "games", "photo", "wellness"}),
    "graduation": frozenset({"photo", "music", "games"}), "retirement": frozenset({"music", "entertainment", "games"}),
    "reunion": frozenset({"games", "photo", "music"}), "holiday": frozenset({"entertainment", "workshop", "music"}),
    "welcome": frozenset({"entertainment", "photo"}), "housewarming": frozenset({"games", "music"}),
    "gathering": frozenset({"games", "music", "entertainment", "workshop"}),
}
BAND_ACTIVITIES: dict[str, frozenset[str]] = {
    "toddler": frozenset({"entertainment", "games", "inflatables"}), "kids": frozenset({"entertainment", "inflatables", "games", "workshop"}),
    "tween": frozenset({"games", "workshop", "tech", "entertainment"}), "teen": frozenset({"music", "games", "photo", "tech"}),
    "adult": frozenset(),
}
BAND_VENUES: dict[str, frozenset[str]] = {
    "toddler": frozenset({"kids_venue", "home", "park"}), "kids": frozenset({"kids_venue", "entertainment", "park", "home"}),
    "tween": frozenset({"entertainment", "kids_venue", "studio"}), "teen": frozenset({"entertainment", "loft", "music", "rooftop"}),
    "adult": frozenset(),
}


def segment_ok(item: CatalogItem, band: str) -> bool:
    return any(s in item.tags for s in BAND_SEGMENTS[band])


def _cuisine_tags(item: CatalogItem) -> list[str]:
    return sorted(t[8:] for t in item.tags if t.startswith("cuisine:"))


def affinity(item: CatalogItem, p: Profile, slot: str) -> float:
    s = 0.0
    tags = item.tags
    hits = theme_hits(item, p.words)
    s += hits * (1.4 if item.category != "food" else 1.0)
    strong = hits >= 1.6  # two direct words — the theme really is about this

    palettes = {t[6:] for t in tags if t.startswith("theme:")}
    if palettes:
        palette_hit = any(theme_hits_palette(pal, p.words) for pal in palettes)
        direct = direct_hits(item, p.words)
        if palette_hit:
            s += 1.2
        elif item.category == "supplies" and direct < DIRECT_HIT:
            s -= 1.6 if p.band != "adult" else 2.6  # dino plates at a space party; themed paper goods are a kids' thing
        elif item.category == "food" and direct < DIRECT_HIT:
            s -= 1.6  # dino nuggets belong at the dino party
        elif "style:character" in tags and direct < DIRECT_HIT:
            s -= 2.5  # a superhero at a dinosaur party

    cuisines = _cuisine_tags(item)
    if cuisines:
        matched = any(c in p.cuisines for c in cuisines)
        specific = [c for c in cuisines if c in SPECIFIC_CUISINES]
        if matched:
            s += 1.8 if slot == "main" else (1.2 if item.category == "food" else 1.0)
            if p.cuisines and cuisines[0] == p.cuisines[0]:
                s += 0.4
        elif item.category != "food":
            # Cultural identity items belong only where that culture was asked for.
            s -= 3.0 if specific else (2.5 if p.cuisines else (0.5 if hits < DIRECT_HIT else 0.0))
        elif specific:
            s -= (2.0 if slot == "main" else 2.6) if not strong else 0.0
        elif p.cuisines:
            s -= 0.9 if slot == "main" else 0.5  # a specific cuisine was asked for; this is something else
        else:
            s += 0.2 if slot == "main" else 0.1

    if "niche" in tags and hits < DIRECT_HIT and not any(c in p.cuisines for c in cuisines):
        s -= 2.4
    if "niche:adult" in tags and (p.band != "adult" or hits < DIRECT_HIT):
        s -= 3.0
    needs = [t[6:] for t in tags if t.startswith("needs:")]
    if needs:
        s += 1.2 if any(need_in(n, p.text) for n in needs) else -5.0
    fors = [t[4:] for t in tags if t.startswith("for:")]
    if fors:
        substitute = any(w in item.name.lower() for w in _SUBSTITUTE_WORDS)
        if any(f in p.need_keys for f in fors):
            s += 1.0 if substitute else 0.5
        elif substitute:
            s -= 1.5
    if item.certifications:
        s += 0.8 if item.certifications & p.prefer_certs else -0.9
    if "includes:main" in tags and item.category == "venue":
        s += 0.6 if p.tier in ("essential", "standard") else 0.0

    moods = {t[5:] for t in tags if t.startswith("mood:")}
    s += 0.5 * len(moods & p.moods)
    if "brunch" in moods and "brunch" not in p.moods:
        s -= 1.0
    if "evening" in moods and "brunch" in p.moods:
        s -= 1.0
    if "winter" in moods and "winter" not in p.moods:
        s -= 0.6
    if "glow" in moods and "glow" in p.moods:
        s += 0.4
    if "wellness" in moods and "wellness" not in p.moods:
        s -= 2.0
    if "elegant" in moods and "elegant" not in p.moods and p.band in ("toddler", "kids", "tween"):
        s -= 0.6
    formal = p.occasion in FORMAL_OCCASIONS or p.luxury or ("elegant" in p.moods and p.band == "adult")
    if formal and hits < DIRECT_HIT:
        if moods & {"sporty", "playful"}:
            s -= 1.2
        if "outdoor" in moods and "outdoor" not in p.moods and item.category != "venue":
            s -= 0.6
    if item.category == "activities" and not item.is_service:
        if item.subcategory in OCCASION_ACTIVITIES.get(p.occasion, frozenset()):
            s += 0.8
        if item.subcategory in BAND_ACTIVITIES[p.band]:
            s += 0.5
    if item.category == "venue":
        if (item.subcategory == "entertainment" and p.band == "adult" and p.tier in ("premium", "luxury")
                and hits < DIRECT_HIT and not (p.explicit_moods & {"playful", "sporty", "retro", "nerdy"})):
            s -= 1.2  # a bowling alley is a choice, not a default, for a premium adult party
        if item.subcategory in OCCASION_VENUES.get(p.occasion, frozenset()):
            s += 0.9
        if item.subcategory in BAND_VENUES[p.band]:
            s += 0.7
        if "outdoor" in moods and "outdoor" in p.explicit_moods:
            s += 0.8
        if "outdoor" in moods and "outdoor" not in p.moods and p.occasion in FORMAL_OCCASIONS:
            s -= 0.5

    d = abs(TIERS.index(item.tier) - TIERS.index(p.tier))
    s += {0: 0.6, 1: 0.2, 2: -0.8}.get(d, -1.4)
    if "style:diy" in tags and p.tier in ("premium", "luxury") and item.category != "food":
        s -= 0.8
    if "signature" in tags:
        s += 0.4
    if slot == "signature":
        if item.category == "activities":
            s += 0.8
            if item.subcategory == "music" and p.occasion in PARTY_OCCASIONS and p.band in ("teen", "adult"):
                s += 1.0
        elif item.category == "supplies":
            s -= 0.8 if hits < DIRECT_HIT else 0.0
    if slot == "cake" and p.birthday and item.course == "cake":
        s += 1.5
    if p.tier == "luxury" and item.tier == "luxury":
        s += 0.3

    segs = {t[4:] for t in tags if t.startswith("seg:")}
    if p.band in segs:
        s += 0.6
    elif "all" in segs:
        s += 0.3
    return s


_PALETTE_WORDS: dict[str, frozenset[str]] = {}


def register_palettes(themes: list[dict]) -> None:
    """Teach the composer the palette keywords (a projection of web/themes.json,
    shipped as pricing/data/palettes.json) so a themed product (theme:dino-dig)
    matches 'Jurassic', not just 'dino'."""
    for t in themes:
        words = set()
        for kw in t.get("keywords", []):
            words |= {_singular(x) for x in _tokens(kw)}
        _PALETTE_WORDS[t["id"]] = frozenset(words - _STOPWORDS)


def _load_palettes() -> None:
    import json

    from ..pricing.catalog import DATA_DIR
    path = DATA_DIR / "palettes.json"
    if path.exists():
        register_palettes(json.loads(path.read_text(encoding="utf-8"))["palettes"])


def theme_hits_palette(palette: str, words: dict[str, float]) -> bool:
    if not _PALETTE_WORDS:
        _load_palettes()
    pal_words = _PALETTE_WORDS.get(palette)
    if pal_words is None:
        pal_words = frozenset(_singular(x) for x in palette.split("-"))
    return any(w in pal_words and weight >= DIRECT_HIT for w, weight in words.items())


def fit(price: float, target: float, tier: str = "standard", band: str = "adult") -> float:
    """How well a price sits against the share the slot may reach for: free up
    to the target, a slope above it, and (above the essential tier) a nudge
    away from token-cheap picks that would make a premium party feel thin."""
    if target <= 0:
        return -1.0 if price > 0 else 0.0
    if price > target:
        return -1.8 * (price - target) / target
    if tier == "essential" or band in ("toddler", "kids", "tween"):
        return 0.0  # kids' entertainers and treats are cheap by nature; cheap is not thin
    soft, hard, lo, hi = {"standard": (-0.4, -0.8, 0.12, 0.25), "premium": (-0.8, -1.5, 0.15, 0.4),
                          "luxury": (-1.0, -1.8, 0.2, 0.5)}[tier]
    if price < lo * target:
        return hard
    if price < hi * target:
        return soft
    return 0.0


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------
# Spending envelopes by tier: the order slots are filled and the share of the
# budget each may reach for. Unspent money flows forward (a $0 home venue pays
# for a better entertainer), so these are planning weights, not hard walls.
ENVELOPES: dict[str, tuple[tuple[str, float], ...]] = {
    "essential": (("signature", 0.26), ("venue", 0.14), ("main", 0.28), ("tableware", 0.07), ("cake", 0.08), ("decor", 0.05),
                  ("entertainment", 0.08), ("music", 0.03), ("drink", 0.04), ("side", 0.04), ("snack", 0.03), ("dessert", 0.02),
                  ("favors", 0.02)),
    "standard": (("signature", 0.26), ("venue", 0.16), ("main", 0.22), ("tableware", 0.05), ("cake", 0.06), ("decor", 0.06),
                 ("lighting", 0.02), ("entertainment", 0.08), ("music", 0.05), ("drink", 0.04), ("side", 0.04), ("snack", 0.03),
                 ("side2", 0.02), ("dessert", 0.03), ("favors", 0.03), ("photo", 0.05)),
    "premium": (("signature", 0.17), ("venue", 0.22), ("main", 0.22), ("tableware", 0.07), ("cake", 0.04), ("decor", 0.07),
                ("lighting", 0.03), ("entertainment", 0.07), ("music", 0.07), ("drink", 0.05), ("side", 0.03), ("snack", 0.04),
                ("side2", 0.02), ("dessert", 0.03), ("alcohol", 0.05), ("favors", 0.03), ("decor2", 0.03), ("stationery", 0.02),
                ("rentals", 0.03), ("entertainment2", 0.04), ("photo", 0.05), ("services", 0.04)),
    "luxury": (("signature", 0.14), ("venue", 0.18), ("main", 0.22), ("tableware", 0.06), ("cake", 0.03), ("decor", 0.08),
               ("lighting", 0.04), ("entertainment", 0.06), ("music", 0.07), ("drink", 0.04), ("side", 0.02), ("snack", 0.04),
               ("side2", 0.02), ("dessert", 0.03), ("alcohol", 0.06), ("favors", 0.03), ("decor2", 0.03), ("stationery", 0.02),
               ("rentals", 0.03), ("entertainment2", 0.04), ("photo", 0.04), ("services", 0.04), ("extras", 0.08)),
}
_CARRY = {"essential": 1.3, "standard": 1.35, "premium": 1.5, "luxury": 1.8}   # reach past the envelope (+ carry-over)
_HIT_REACH = 3.0   # an item the theme names outright may stretch to 3x its envelope


@dataclass
class Pick:
    item: CatalogItem
    quantity: int
    price: float
    slot: str


class _Composer:
    def __init__(self, request: PartyRequest, catalog: Catalog, profile: Profile, variant: int, loose: bool) -> None:
        self.req, self.catalog, self.p, self.variant, self.loose = request, catalog, profile, variant, loose
        self.guests = request.guest_count
        self.budget = float(request.budget)
        self.rng = Rng(f"{request.honoree_name}|{request.honoree_age}|{request.guest_count}|{request.budget}|"
                       f"{request.theme}|{request.dietary_restrictions}|{request.location_type}|{variant}")
        self.pool = eligible(request, catalog, profile.diet)
        band = profile.band
        self.venues = [v for v in self.pool["venues"] if segment_ok(v, band)]
        self.foods = [f for f in self.pool["foods"] if segment_ok(f, band)]
        self.supplies = [s for s in self.pool["supplies"] if segment_ok(s, band)]
        self.activities = [a for a in self.pool["activities"] if segment_ok(a, band)]
        self.services = [a for a in self.pool["services"] if segment_ok(a, band)]
        self.picks: list[Pick] = []
        self.taken: set[str] = set()
        self.spent = 0.0
        self.supervision = catalog.get(KOSHER_SUPERVISION_SKU) if "kosher" in profile.prefer_certs else None
        weights = dict(ENVELOPES[profile.tier])
        if profile.band in ("toddler", "kids", "tween"):
            weights["signature"] *= 1.6   # for kids the entertainer IS the party; the meal is pizza-cheap
            weights["main"] *= 0.7
        total = sum(weights.values())
        self.envelope = {slot: share / total * self.budget for slot, share in weights.items()}
        self.avail = 0.0
        self.deferred = 0.0   # a signature envelope nobody claimed waits for the entertainment slot
        self.debug = False

    # ---- helpers ----
    def remaining(self) -> float:
        return self.budget - self.spent

    def chosen(self, sku: str) -> bool:
        return any(pk.item.sku == sku for pk in self.picks)

    def qty_for(self, item: CatalogItem) -> int:
        if item.category == "food" or item.is_tableware:
            return units_to_cover(item, self.guests)
        return 1

    def _dedup_penalty(self, item: CatalogItem) -> float:
        shared = _cached_tokens(item) & self.taken
        return -min(2.0, 1.0 * len(shared))

    def has_slot(self, slot: str) -> bool:
        return any(pk.slot == slot for pk in self.picks)

    def of_course(self, course: str) -> list[CatalogItem]:
        return [f for f in self.foods if f.course == course and "style:included" not in f.tags]

    def cheapest_cost(self, items: list[CatalogItem]) -> float:
        if not items:
            return 0.0
        return min(it.price_for(self.qty_for(it), self.guests) for it in items)

    @property
    def venue_feeds(self) -> bool:
        return any(pk.slot == "venue" and "includes:main" in pk.item.tags for pk in self.picks)

    @property
    def fed(self) -> bool:
        return self.venue_feeds or any(pk.item.course == "main" for pk in self.picks)

    @property
    def has_activity(self) -> bool:
        return any(pk.item.category == "activities" and not pk.item.is_service for pk in self.picks)

    def reserve_needed(self, assuming: str | None = None) -> float:
        """Money that must stay untouched for the essentials not yet chosen."""
        total = 0.0
        if not self.has_slot("venue") and assuming != "venue":
            total += self.cheapest_cost(self.venues)
        if not self.fed and assuming != "main":
            total += self.cheapest_cost(self.of_course("main"))
        if not self.has_slot("tableware") and assuming != "tableware":
            total += self.cheapest_cost([s for s in self.supplies if s.is_tableware])
        if not self.has_activity and assuming != "entertainment":
            total += self.cheapest_cost(self.activities)
        if self.supervision is not None and not self.chosen(self.supervision.sku):
            total += self.supervision.price_for(1, self.guests)
        if self.p.birthday and not self.has_slot("cake") and assuming != "cake":
            total += self.cheapest_cost(self.of_course("cake"))
        if not self.has_slot("decor") and assuming != "decor":
            total += self.cheapest_cost([s for s in self.supplies if s.subcategory == "decor"])
        return total

    def pick(self, candidates: list[CatalogItem], slot: str, *, envelope: str | None = None, boost: float = 0.0,
             cover: bool = False, rank: int = 0, min_affinity: float | None = None, essential: bool = False,
             min_score: float = -0.8) -> Pick | None:
        """Choose for a slot. The slot's envelope (plus whatever earlier slots left
        unspent) is what it may reach for; essentials may exceed it when nothing
        else fits, nothing may exceed the budget minus the reserve."""
        env = self.envelope.get(envelope or slot, 0.0)
        self.avail += env
        target = max(env, self.avail, 0.0)
        reach = max(self.avail, env) * _CARRY[self.p.tier]
        if essential:
            reach = max(reach, env * (2.4 if self.p.tier in ("premium", "luxury") else 1.8))
        hit_reach = max(reach, env * _HIT_REACH)
        cap = self.remaining() - self.reserve_needed(assuming=slot)
        jitter = _JITTER if essential else _JITTER_OPEN
        rows: list[tuple[float, CatalogItem, int, float]] = []
        for item in candidates:
            if self.chosen(item.sku):
                continue
            qty = self.qty_for(item) if cover else 1
            price = item.price_for(qty, self.guests)
            if price > cap + 1e-9:
                continue
            aff = affinity(item, self.p, slot)
            if min_affinity is not None and aff < min_affinity:
                continue
            hits = theme_hits(item, self.p.words)
            if hits < DIRECT_HIT and (
                    any(theme_hits_palette(t[6:], self.p.words) for t in item.tags if t.startswith("theme:"))
                    or (item.certifications & self.p.prefer_certs)
                    or (item.category == "food" and any(c in self.p.cuisines for c in _cuisine_tags(item)))):
                hits = DIRECT_HIT  # a palette, certification or cuisine match is as good as the host naming it
            fit_pen = fit(price, target, self.p.tier, self.p.band)
            if fit_pen < 0 and hits >= DIRECT_HIT:
                fit_pen *= 0.3 if hits >= 1.6 else 0.5  # the party is about this; price matters less
            score = aff + fit_pen + (boost if hits >= DIRECT_HIT else 0.0) + self.rng.random() * jitter
            score += self._dedup_penalty(item)
            if cover and (item.category == "food" or item.is_tableware):
                provided = item.servings_for(qty, self.guests) if item.category == "food" else item.settings_for(qty, self.guests)
                score -= 0.5 * max(0.0, provided / max(1, self.guests) - 1.6)  # a 48-serving cake for 15 is waste, not generosity
            rows.append((score, item, qty, price, hits))
        if self.debug:
            print(f"  [{slot}] target ${target:,.0f} reach ${reach:,.0f} cap ${cap:,.0f}")
            for r in sorted(rows, key=lambda x: -x[0])[:5]:
                print(f"     {r[0]:6.2f} ${r[3]:>8,.0f} x{r[2]} {r[1].sku} hits {r[4]:.1f}")
        if not rows:
            return None
        within = [r for r in rows if r[3] <= (cap if r[4] >= 1.6 else hit_reach if r[4] >= DIRECT_HIT else reach) + 1e-9]
        scored = within if within or not essential else rows
        if not scored:
            return None
        scored.sort(key=lambda x: (-x[0], x[1].sku))
        chosen = scored[min(rank, len(scored) - 1)]
        if not essential and chosen[0] < min_score:
            return None  # nothing fits this slot well enough to be worth the money
        return Pick(chosen[1], chosen[2], chosen[3], slot)

    def take(self, pk: Pick | None) -> Pick | None:
        if pk is None:
            return None
        self.picks.append(pk)
        self.spent = round(self.spent + pk.price, 2)
        self.avail -= pk.price
        self.taken |= _cached_tokens(pk.item)
        return pk

    # ---- the pass ----
    def run(self) -> PlanDraft | None:
        p = self.p
        tableware = [s for s in self.supplies if s.is_tableware]
        if not self.venues or not tableware or not self.activities:
            return None
        if self.remaining() < self.reserve_needed():
            return None
        premium = p.tier in ("premium", "luxury")

        # 1. Signature first — the one thing people will talk about — with every
        #    essential still reserved. Variants rotate through the ranked list.
        sig_cands = [a for a in self.activities if "signature" in a.tags]
        sig_cands += [m for m in self.of_course("main") if "signature" in m.tags]
        sig_cands += [s for s in self.supplies if "signature" in s.tags and not s.is_tableware]
        if p.tier != "essential":
            sig_cands += [f for f in self.foods if "signature" in f.tags and f.course in ("dessert", "drink")]
        sig = self.take(self.pick(sig_cands, "signature", boost=0.35, cover=True, rank=self.variant,
                                  min_affinity=None if self.loose else 0.5))
        signature_main = sig is not None and sig.item.course == "main"
        if sig is None:
            self.deferred, self.avail = self.envelope["signature"], self.avail - self.envelope["signature"]

        # 2. Venue — a package that includes the meal competes on its all-in price,
        #    unless the signature already feeds everyone.
        venues = [v for v in self.venues if not (signature_main and "includes:main" in v.tags)]
        if self.take(self.pick(venues, "venue", boost=0.3, essential=True)) is None:
            return None

        # 3. The meal and a place setting for everyone.
        if not self.fed and self.take(self.pick(self.of_course("main"), "main", boost=0.4, cover=True, essential=True)) is None:
            return None
        if self.take(self.pick(tableware, "tableware", cover=True, essential=True)) is None:
            return None
        if self.supervision is not None:
            self.take(Pick(self.supervision, 1, self.supervision.price_for(1, self.guests), "services"))

        # 4. Sweet moment: a cake for birthdays and milestones.
        cake_occasions = {"birthday", "first_birthday", "sweet16", "quince", "mitzvah", "wedding", "anniversary",
                          "baby_shower", "graduation", "engagement", "welcome", "retirement"}
        if p.birthday or p.occasion in cake_occasions:
            self.take(self.pick(self.of_course("cake"), "cake", boost=0.3, cover=True, essential=p.birthday))

        # 5. The look before the second helping.
        decor = [s for s in self.supplies if s.subcategory == "decor" and "signature" not in s.tags]
        lighting = [s for s in self.supplies if s.subcategory == "lighting"]
        self.take(self.pick(decor, "decor", boost=0.5, cover=True))
        after_dark = "evening" in p.moods or "glow" in p.moods or (premium and p.band in ("teen", "adult"))
        if after_dark and "lighting" in self.envelope:
            self.take(self.pick(lighting, "lighting", boost=0.5, cover=True))

        # 6. Entertainment and music — at least one real activity, always.
        acts = [a for a in self.activities if a.subcategory != "music"]
        music = [a for a in self.activities if a.subcategory == "music"]
        extra_floor = 2.0 if premium else (1.5 if p.tier == "standard" else 1.2)
        self.avail += self.deferred
        self.deferred = 0.0
        if not self.has_activity:
            if self.take(self.pick(acts + music, "entertainment", boost=0.45, essential=True)) is None:
                return None
        else:
            self.take(self.pick(acts, "entertainment", boost=0.45, min_affinity=extra_floor))
        wants_music = p.band in ("teen", "adult") or "glow" in p.moods or word_in("music", p.text) or word_in("dance", p.text) or p.occasion in (
            "sweet16", "quince", "mitzvah", "wedding", "gala")
        if wants_music and not any(pk.item.subcategory == "music" for pk in self.picks):
            self.take(self.pick(music, "music", boost=0.45, min_affinity=extra_floor))

        # 7. Round out the table.
        feeds = self.venue_feeds
        if not feeds or premium:
            self.take(self.pick(self.of_course("drink"), "drink", boost=0.3, cover=True))
        if not feeds:
            self.take(self.pick(self.of_course("side"), "side", boost=0.3, cover=True))
            self.take(self.pick(self.of_course("snack"), "snack", boost=0.3, cover=True))
            if "side2" in self.envelope and (premium or self.guests >= 30):
                self.take(self.pick(self.of_course("side"), "side", envelope="side2", boost=0.3, cover=True))
        if not self.has_slot("cake") or premium:
            self.take(self.pick(self.of_course("dessert"), "dessert", boost=0.3, cover=True))
        if p.band == "adult" and premium and "alcohol" not in p.avoid and "brunch" not in p.moods:
            self.take(self.pick([d for d in self.of_course("drink") if "contains:alcohol" in d.tags], "drink", envelope="alcohol",
                                boost=0.3, cover=True))
        favors = [s for s in self.supplies if s.subcategory == "favors"]
        self.take(self.pick(favors, "favors", boost=0.4, cover=True))
        if premium:
            self.take(self.pick(decor, "decor", envelope="decor2", boost=0.5, cover=True, min_affinity=0.5))
            self.take(self.pick([s for s in self.supplies if s.subcategory == "stationery"], "stationery", cover=True))
            self.take(self.pick([s for s in self.supplies if s.subcategory == "rentals"], "rentals", cover=True, min_affinity=0.0))
            self.take(self.pick(acts, "entertainment", envelope="entertainment2", boost=0.45, min_affinity=2.2))

        # 8. Photo, services, luxury extras.
        if "photo" in self.envelope:
            photo = [a for a in self.activities if a.subcategory == "photo"]
            self.take(self.pick(photo, "photo", boost=0.3, min_affinity=0.0 if p.tier == "standard" else None))
        if premium:
            svc = [s for s in self.services if s.subcategory in ("staffing", "planning")]
            self.take(self.pick(svc, "services", cover=True, min_affinity=0.0))
            if p.tier == "luxury":
                for _ in range(6):
                    music_acts = sum(1 for pk in self.picks if pk.item.subcategory == "music")
                    extras = [a for a in self.activities if a.tier in ("premium", "luxury") and (a.subcategory != "music" or music_acts < 2)] + \
                             [s for s in self.supplies if s.tier in ("premium", "luxury") and not s.is_tableware] + \
                             [f for f in self.foods if f.tier in ("premium", "luxury") and f.course in ("snack", "dessert", "drink")]
                    if self.take(self.pick(extras, "extras", boost=0.4, cover=True, min_affinity=1.6)) is None:
                        break
        self.upgrade()
        return self.to_draft()

    # ---- spend what is left well ----
    def upgrade(self) -> None:
        """Money left after the pass buys a better version of the anchors — the
        meal, the signature, the music, the venue — never another trinket."""
        for slot, course in (("main", "main"), ("signature", None), ("music", None), ("venue", None), ("cake", "cake"), ("drink", "drink")):
            if self.remaining() < 0.04 * self.budget:
                return
            idx = next((i for i, pk in enumerate(self.picks) if pk.slot == slot), None)
            if idx is None:
                continue
            old = self.picks[idx]
            if course:
                cands = self.of_course(course)
            elif slot == "venue":
                cands = [v for v in self.venues if not (self.fed and "includes:main" in v.tags and old.item.course != "main")]
            elif slot == "music":
                cands = [a for a in self.activities if a.subcategory == "music"]
            else:
                cands = [a for a in self.activities if "signature" in a.tags]
            budget_for = self.remaining() + old.price
            old_aff = affinity(old.item, self.p, slot)
            best: tuple[float, CatalogItem, int, float] | None = None
            for item in cands:
                if item.sku == old.item.sku or self.chosen(item.sku):
                    continue
                qty = self.qty_for(item)
                price = item.price_for(qty, self.guests)
                if price <= old.price or price > budget_for + 1e-9:
                    continue
                aff = affinity(item, self.p, slot)
                if aff < old_aff + 0.3:
                    continue
                score = aff - 0.4 * (price - old.price) / max(1.0, self.budget * 0.1)
                if best is None or score > best[0]:
                    best = (score, item, qty, price)
            if best is not None:
                self.spent = round(self.spent - old.price + best[3], 2)
                self.picks[idx] = Pick(best[1], best[2], best[3], slot)

    # ---- rendering ----
    def to_draft(self) -> PlanDraft:
        p, req = self.p, self.req
        venue = next(pk for pk in self.picks if pk.slot == "venue")
        food = [Selection(sku=pk.item.sku, quantity=pk.quantity) for pk in self.picks if pk.item.category == "food"]
        supplies = [Selection(sku=pk.item.sku, quantity=pk.quantity) for pk in self.picks if pk.item.category == "supplies"]
        activities = [Selection(sku=pk.item.sku, quantity=pk.quantity) for pk in self.picks if pk.item.category == "activities"]
        theme = req.theme or suggest_theme(req, self.variant)
        sig = next((pk for pk in self.picks if pk.slot == "signature"), None)
        main = next((pk for pk in self.picks if pk.slot == "main"), None) or (sig if sig and sig.item.course == "main" else None)
        cake = next((pk for pk in self.picks if pk.slot == "cake"), None)
        dessert = next((pk for pk in self.picks if pk.slot == "dessert"), None)
        decor = next((pk for pk in self.picks if pk.slot == "decor"), None)
        lighting = next((pk for pk in self.picks if pk.slot == "lighting"), None)
        favors = next((pk for pk in self.picks if pk.slot == "favors"), None)
        ent = [pk for pk in self.picks if pk.slot in ("entertainment", "music", "signature", "extras") and pk.item.category == "activities"]
        photo = next((pk for pk in self.picks if pk.slot == "photo"), None)
        sides = [pk for pk in self.picks if pk.slot in ("side", "snack")]
        drinks = [pk for pk in self.picks if pk.slot == "drink"]
        venue_feeds = "includes:main" in venue.item.tags

        acts = [pk for pk in ent if pk.item.subcategory not in ("effects", "staffing", "planning", "transport", "ceremony")]
        anchor = sig or (max(acts, key=lambda pk: affinity(pk.item, p, "signature")) if acts else None)
        if anchor is None and main is not None and "signature" in main.item.tags:
            anchor = main
        # The thing the host literally named wins the title — a pottery studio, a
        # taco truck, a laser-tag arena — but a plain main course never does.
        named = [pk for pk in [sig, *acts, venue] if pk is not None and direct_hits(pk.item, p.words) >= 1.5]
        if main is not None and "signature" in main.item.tags and direct_hits(main.item, p.words) >= 1.5:
            named.append(main)
        if named:
            anchor = max(named, key=lambda pk: (round(direct_hits(pk.item, p.words) * 2) / 2, pk is sig,
                                                pk.item.category == "activities", pk.item.category == "food"))
        title = _title(theme)
        concept = title
        if anchor:
            head = headline(anchor.item)
            head_toks = {t for t in _tokens(head) if t not in _GENERIC_TOKENS}
            if not head_toks or len(head_toks & set(p.words)) < max(1, len(head_toks) * 0.6):
                concept = f"{title} · {head}"
        event = _event_phrase(p.occasion, req, p.birthday)
        sentences = []
        if anchor is venue:
            sentences.append(f"{event[0].upper()}{event[1:]} takes over {with_article(headline(anchor.item))}.")
        elif anchor:
            sentences.append(f"{event[0].upper()}{event[1:]} opens with {with_article(headline(anchor.item))}.")
        else:
            sentences.append(f"{event[0].upper()}{event[1:]}, planned end to end.")
        table_bits = []
        if venue_feeds:
            table_bits.append(f"{headline(venue.item).lower()} feeds everyone")
        elif main and main is not anchor:
            table_bits.append(headline(main.item).lower())
        table_bits += [headline(pk.item).lower() for pk in sides[:2]]
        if drinks:
            table_bits.append(headline(drinks[0].item).lower())
        if table_bits:
            sentences.append("On the table: " + _join(table_bits) + ".")
        if cake:
            sentences.append(f"The sweet moment is {with_article(headline(cake.item))}" + (f", with {headline(dessert.item).lower()} alongside." if dessert else "."))
        elif dessert:
            sentences.append(f"For something sweet, {headline(dessert.item).lower()}.")
        look_bits = [headline(pk.item).lower() for pk in (decor, lighting) if pk]
        if favors:
            look_bits.append(f"{headline(favors.item).lower()} to take home")
        if look_bits:
            sentences.append("For the look, " + _join(look_bits) + ".")
        extras = [headline(pk.item) for pk in ent if pk is not anchor] + ([headline(photo.item)] if photo else [])
        if extras:
            sentences.append("Also on: " + _join([e.lower() for e in extras]) + ".")
        story = " ".join(sentences)

        moments: list[Moment] = []
        if anchor:
            moments.append(Moment(label="Signature", text=short_name(anchor.item)))
        table = ([short_name(venue.item)] if venue_feeds else ([short_name(main.item)] if main and main is not anchor else [])) + \
            [short_name(pk.item) for pk in sides[:2]]
        if table:
            moments.append(Moment(label="On the table", text=" · ".join(table)))
        if cake or dessert:
            moments.append(Moment(label="Sweet moment", text=" · ".join(short_name(pk.item) for pk in (cake, dessert) if pk)))
        if decor or lighting:
            moments.append(Moment(label="The look", text=" · ".join(short_name(pk.item) for pk in (decor, lighting) if pk)))
        others = [pk for pk in ent if pk is not anchor]
        if others or photo:
            moments.append(Moment(label="Also on", text=" · ".join(short_name(pk.item) for pk in [*others, *([photo] if photo else [])])))
        if favors:
            moments.append(Moment(label="Take-home", text=short_name(favors.item)))

        notes = []
        if p.diet.any:
            notes.append(f"Checked for: {p.diet.text}.")
        if "pork" in p.avoid:
            notes.append("No pork on the menu.")
        if "halal" in p.prefer_certs:
            notes.append("Every meat dish is halal-certified.")
        if "kosher" in p.prefer_certs:
            notes.append("Kosher-certified food with a mashgiach on site.")
        lead = max((pk.item.lead_days for pk in self.picks), default=0)
        if lead >= 7:
            longest = max(self.picks, key=lambda pk: pk.item.lead_days)
            notes.append(f"Book {short_name(longest.item)} at least {lead} days ahead.")
        headliner = anchor.item if anchor and anchor.item.category == "activities" else (sig.item if sig and sig.item.category == "activities" else None)
        schedule = build_schedule(p, req, headliner, bool(cake), [pk.item for pk in ent if pk.item is not headliner], venue_feeds or main is not None)
        return PlanDraft(theme=theme, venue_sku=venue.item.sku, food=food, supplies=supplies, activities=activities,
                         schedule=schedule, notes=" ".join(notes), concept_name=concept[:120], story=story[:1200], moments=moments[:6])


# ---------------------------------------------------------------------------
# Words
# ---------------------------------------------------------------------------
def _title(theme: str) -> str:
    t = (theme or "").strip()
    if not t:
        return "The Party"
    return t if (t.isupper() and len(t) <= 4) or any(c.isupper() for c in t[1:]) else t[:1].upper() + t[1:]


def _join(bits: list[str]) -> str:
    bits = [b for b in bits if b]
    if not bits:
        return ""
    if len(bits) == 1:
        return bits[0]
    return ", ".join(bits[:-1]) + " and " + bits[-1]


def short_name(item: CatalogItem) -> str:
    name = re.sub(r"\s*\((?:serves|per|\d+|two|dozen|up to|[0-9x]+|[^)]*hr|[^)]*settings|[^)]*person|[^)]*seats)[^)]*\)", "", item.name)
    return name.strip(" ,")


def headline(item: CatalogItem) -> str:
    name = re.sub(r"\s*\(.*?\)", "", short_name(item)).strip()
    for cut in (" with ", " for ", ", ", " — "):
        if cut in name:
            name = name.split(cut)[0]
    words = name.split()
    while words and words[-1].lower() in _TRAILING:
        words.pop()
    return " ".join(words) or short_name(item)


def _decap(p: str) -> str:
    """Lowercase a leading capital unless the first word is an acronym (DIY, VR, LAN)."""
    first = p.split()[0] if p.split() else p
    return p if sum(ch.isupper() for ch in first) >= 2 else p[:1].lower() + p[1:]


def with_article(phrase: str) -> str:
    p = phrase.strip()
    low = p.lower()
    if not p or low.endswith(_NO_ARTICLE_ENDINGS) or low.split()[0] in {"live", "licensed", "chef-led", "pro-installed", "hand-cut"}:
        return _decap(p) if p else p
    article = "an" if low[0] in "aeiou" else "a"
    return f"{article} {_decap(p)}"


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _event_phrase(occasion: str, req: PartyRequest, birthday: bool = False) -> str:
    if birthday and occasion in ("gathering", "holiday"):
        occasion = "first_birthday" if req.honoree_age == 1 else "birthday"
    tpl = _OCCASION_PHRASES.get(occasion, _OCCASION_PHRASES["gathering"])
    return tpl.format(name=req.honoree_name.strip() or "The honoree", ordinal=_ordinal(req.honoree_age))


# ---------------------------------------------------------------------------
# Run of show
# ---------------------------------------------------------------------------
def _hhmm(minutes: int) -> str:
    minutes = max(0, min(23 * 60 + 59, minutes))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def build_schedule(p: Profile, req: PartyRequest, signature: CatalogItem | None, has_cake: bool,
                   others: list[CatalogItem], has_meal: bool) -> list[ScheduleSlot]:
    if "brunch" in p.moods:
        start, length, longest = 11 * 60, 180, 240
    elif p.band == "toddler":
        start, length, longest = 10 * 60, 120, 150
    elif p.band == "kids":
        start, length, longest = 14 * 60, 150, 210
    elif p.band == "tween":
        start, length, longest = 15 * 60, 180, 240
    elif p.band == "teen":
        start, length, longest = 18 * 60, 180, 240
    elif "evening" in p.moods or p.occasion in ("wedding", "gala", "corporate", "engagement", "anniversary"):
        start, length, longest = 18 * 60 + 30, 240, 300
    else:
        start, length, longest = 16 * 60, 210, 270
    if p.tier == "luxury":
        length, longest = length + 60, longest + 60
    slots: list[tuple[int, str]] = []  # (duration, label)
    slots.append((30, "Arrivals & welcome" + (" drinks" if p.band == "adult" else "")))
    if signature is not None:
        slots.append((60 if p.band != "toddler" else 40, f"{headline(signature)}"))
    if has_meal:
        slots.append((50 if p.band != "toddler" else 30, "Dinner is served" if "evening" in p.moods or p.occasion in ("wedding", "gala") else "Food is served"))
    if has_cake:
        slots.append((25, "Cake" + (", candles & singing" if p.birthday else " & toasts")))
    elif p.band == "adult":
        slots.append((20, "Toasts"))
    for item in others[:2]:
        slots.append((45, headline(item)))
    if p.band in ("teen", "adult") and not any("dance" in s[1].lower() for s in slots) and p.occasion not in ("corporate",):
        slots.append((60, "Dance floor open"))
    slots.append((20, "Goodbyes" + (" & take-home bags" if p.band != "adult" else "")))
    # Grow the window to fit the plan, then squeeze only past the longest sane party.
    total = sum(d for d, _ in slots)
    end = min(start + max(length, min(total, longest)), 23 * 60 + 59)
    if total > end - start:
        scale = (end - start) / total
        slots = [(max(10, int(d * scale)), label) for d, label in slots]
    out: list[ScheduleSlot] = []
    t = start
    for d, label in slots:
        s, e = t, min(t + d, 23 * 60 + 59)
        if e <= s:
            break
        out.append(ScheduleSlot(start=_hhmm(s), end=_hhmm(e), activity=label[:200]))
        t = e
    return out if len(out) >= 2 else [ScheduleSlot(start=_hhmm(start), end=_hhmm(start + 60), activity="Arrivals & welcome"),
                                      ScheduleSlot(start=_hhmm(start + 60), end=_hhmm(start + 120), activity="Food, cake & goodbyes")]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _compose_once(request: PartyRequest, catalog: Catalog, variant: int, tier_override: str | None, loose: bool) -> PlanDraft | None:
    theme = request.theme if request.theme.strip() else suggest_theme(request, variant)
    profile = profile_for(request, tier_override=tier_override, theme=theme)
    draft = _Composer(request, catalog, profile, variant, loose).run()
    if draft is None:
        return None
    plan = ground_draft(draft, catalog, request.guest_count)
    report = verify_plan(plan, request, catalog)
    return draft if report.passed else None


def compose(request: PartyRequest, catalog: Catalog, variant: int = 0, tier_override: str | None = None) -> PlanDraft | None:
    """A verified Party Concept for the request, or None when no concept fits
    (the caller then falls back to the cheapest compliant plan)."""
    if dietary_context(request).unverifiable:
        return None
    attempts = [(tier_override, False), ("essential", False), ("essential", True)]
    for tier, loose in attempts:
        draft = _compose_once(request, catalog, variant, tier, loose)
        if draft is not None:
            return draft
    return None


def compose_candidates(request: PartyRequest, catalog: Catalog, n: int = 3) -> list[PlanDraft]:
    """Up to n distinct concepts, in variant order."""
    out: list[PlanDraft] = []
    seen: set[tuple] = set()
    for v in range(max(1, n)):
        d = compose(request, catalog, variant=v)
        if d is None:
            continue
        key = (d.venue_sku, tuple((s.sku, s.quantity) for s in d.food), tuple((s.sku, s.quantity) for s in d.supplies),
               tuple((s.sku, s.quantity) for s in d.activities))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def catalog_slice(request: PartyRequest, catalog: Catalog, limit: int = 140) -> list[CatalogItem]:
    """The part of the catalog worth showing a model for this request: every
    eligible item, ranked by affinity, capped per category so the prompt stays
    small but never hides the certified / allergen-safe options."""
    profile = profile_for(request)
    pool = eligible(request, catalog, profile.diet)
    cands = [*pool["venues"], *pool["foods"], *pool["supplies"], *pool["activities"], *pool["services"]]
    cands = [c for c in cands if segment_ok(c, profile.band)]
    caps = {"venue": max(6, limit // 10), "food": max(30, limit // 2), "supplies": max(14, limit // 6), "activities": max(24, limit // 4)}
    by_cat: dict[str, list[tuple[float, CatalogItem]]] = {}
    for c in cands:
        slot = c.course if c.category == "food" else c.category
        by_cat.setdefault(c.category, []).append((affinity(c, profile, slot) - (0.0 if c.price_for(1, request.guest_count) <= request.budget else 5.0), c))
    out: list[CatalogItem] = []
    for cat, rows in by_cat.items():
        rows.sort(key=lambda r: (-r[0], r[1].sku))
        out.extend(c for _, c in rows[: caps.get(cat, 20)])
    return out
