LANGUAGES = ("uz", "ru", "en")
DEFAULT_LANGUAGE = "en"

TEXTS: dict[str, dict[str, str]] = {
    "start": {
        "en": (
            "🎬 AI Movie Finder\n\n"
            "Send me a movie screenshot, a short video, or a YouTube/Instagram link\n"
            "and I will find the movie or show name.\n\n"
            "📸 Screenshot\n"
            "🎥 Video file\n"
            "🔗 YouTube / Instagram Reels link"
        ),
        "ru": (
            "🎬 AI Movie Finder\n\n"
            "Отправь скриншот, короткое видео или ссылку с YouTube/Instagram,\n"
            "и я найду название фильма или сериала.\n\n"
            "📸 Скриншот\n"
            "🎥 Видеофайл\n"
            "🔗 Ссылка YouTube / Instagram Reels"
        ),
        "uz": (
            "🎬 AI Movie Finder\n\n"
            "Skrinshot, qisqa video yoki YouTube/Instagram havolasini yubor,\n"
            "men film yoki serial nomini topib beraman.\n\n"
            "📸 Skrinshot\n"
            "🎥 Video fayl\n"
            "🔗 YouTube / Instagram Reels havolasi"
        ),
    },
    "choose_language": {
        "en": "Choose your language:",
        "ru": "Выберите язык:",
        "uz": "Tilni tanlang:",
    },
    "language_set": {
        "en": "Language set to English.",
        "ru": "Язык установлен: русский.",
        "uz": "Til o'zbek tiliga o'rnatildi.",
    },
    "limit_reached": {
        "en": "You've reached your free limit of {limit} searches today.\nUpgrade to Premium for unlimited searches.",
        "ru": "Вы достигли дневного лимита в {limit} бесплатных поисков.\nОформите Premium для безлимитного поиска.",
        "uz": "Siz bugungi {limit} bepul qidiruv chegarasiga yetdingiz.\nCheksiz qidiruv uchun Premiumga o'ting.",
    },
    "history_empty": {
        "en": "No searches yet. Send a screenshot or video to get started!",
        "ru": "Пока нет истории поиска. Отправьте скриншот или видео, чтобы начать!",
        "uz": "Hali qidiruvlar yo'q. Boshlash uchun skrinshot yoki video yuboring!",
    },
    "history_header": {
        "en": "Your search history:\n",
        "ru": "История поиска:\n",
        "uz": "Qidiruvlar tarixi:\n",
    },
    "analyzing_image": {
        "en": "🔍 Analyzing screenshot...",
        "ru": "🔍 Анализирую скриншот...",
        "uz": "🔍 Skrinshot tahlil qilinmoqda...",
    },
    "analyzing_video": {
        "en": "🔍 Analyzing video...",
        "ru": "🔍 Анализирую видео...",
        "uz": "🔍 Video tahlil qilinmoqda...",
    },
    "image_error": {
        "en": "Something went wrong while analyzing the image. Please try again.",
        "ru": "Что-то пошло не так при анализе изображения. Попробуйте снова.",
        "uz": "Rasmni tahlil qilishda xatolik yuz berdi. Qaytadan urinib ko'ring.",
    },
    "video_error": {
        "en": "Something went wrong while analyzing the video. Please try again.",
        "ru": "Что-то пошло не так при анализе видео. Попробуйте снова.",
        "uz": "Videoni tahlil qilishda xatolik yuz berdi. Qaytadan urinib ko'ring.",
    },
    "file_too_large_image": {
        "en": "This image is too large. Please send a smaller file.",
        "ru": "Это изображение слишком большое. Отправьте файл меньшего размера.",
        "uz": "Rasm hajmi juda katta. Kichikroq fayl yuboring.",
    },
    "file_too_large_video": {
        "en": "This video is too large. Please send a shorter clip.",
        "ru": "Это видео слишком большое. Отправьте более короткий ролик.",
        "uz": "Video hajmi juda katta. Qisqaroq video yuboring.",
    },
    "video_too_long": {
        "en": "This video is too long. Please send a clip under 3 minutes.",
        "ru": "Это видео слишком длинное. Отправьте ролик короче 3 минут.",
        "uz": "Video juda uzun. 3 daqiqadan qisqaroq video yuboring.",
    },
    "link_fetch_error": {
        "en": "Couldn't fetch that video. Make sure it's a public YouTube or Instagram Reels link and try again.",
        "ru": "Не удалось загрузить это видео. Убедитесь, что это публичная ссылка YouTube или Instagram Reels, и попробуйте снова.",
        "uz": "Bu videoni yuklab bo'lmadi. Havola ochiq (public) YouTube yoki Instagram Reels havolasi ekanini tekshirib, qaytadan urinib ko'ring.",
    },
    "not_identified": {
        "en": "Sorry, I couldn't identify the movie from this. Try a clearer screenshot or video.",
        "ru": "Извините, не удалось определить фильм. Попробуйте более четкий скриншот или видео.",
        "uz": "Afsuski, filmni aniqlay olmadim. Yaqqolroq skrinshot yoki video yuboring.",
    },
    "no_tmdb_details": {
        "en": "Couldn't find extra details on TMDB.",
        "ru": "Не удалось найти дополнительные сведения в TMDB.",
        "uz": "TMDB'dan qo'shimcha ma'lumot topilmadi.",
    },
    "trailer_button": {
        "en": "▶️ Watch Trailer",
        "ru": "▶️ Смотреть трейлер",
        "uz": "▶️ Treylerni ko'rish",
    },
    "genre_label": {"en": "Genre", "ru": "Жанр", "uz": "Janr"},
    "rating_label": {"en": "Rating", "ru": "Рейтинг", "uz": "Reyting"},
    "confidence_label": {"en": "Confidence", "ru": "Уверенность", "uz": "Ishonch"},
    "cast_label": {"en": "Cast", "ru": "Актёры", "uz": "Aktyorlar"},
    "watch_label": {"en": "Where to watch", "ru": "Где смотреть", "uz": "Qayerda ko'rish"},
    "watch_button": {"en": "🍿 Where to watch", "ru": "🍿 Где смотреть", "uz": "🍿 Qayerda ko'rish"},
    "unknown": {"en": "Unknown", "ru": "Неизвестно", "uz": "Noma'lum"},
    "menu_history": {"en": "📜 History", "ru": "📜 История", "uz": "📜 Tarix"},
    "menu_language": {"en": "🌐 Language", "ru": "🌐 Язык", "uz": "🌐 Til"},
}

TMDB_LANGUAGE_MAP = {
    "en": "en-US",
    "ru": "ru-RU",
    "uz": "en-US",  # TMDB has no Uzbek locale; fall back to English content
}

# Region for JustWatch/TMDB watch providers (streaming availability is region-specific).
TMDB_REGION_MAP = {
    "en": "US",
    "ru": "RU",
    "uz": "RU",  # No UZ catalog on JustWatch; RU market is the closest match for Uzbek users
}


def t(key: str, lang: str, **kwargs) -> str:
    lang = lang if lang in LANGUAGES else DEFAULT_LANGUAGE
    template = TEXTS.get(key, {}).get(lang) or TEXTS.get(key, {}).get(DEFAULT_LANGUAGE, "")
    return template.format(**kwargs) if kwargs else template


def all_variants(key: str) -> set[str]:
    return set(TEXTS.get(key, {}).values())


def tmdb_language(lang: str) -> str:
    return TMDB_LANGUAGE_MAP.get(lang, "en-US")


def tmdb_region(lang: str) -> str:
    return TMDB_REGION_MAP.get(lang, "US")
