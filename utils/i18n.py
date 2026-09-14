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
            "🔗 YouTube / Instagram Reels link\n"
            "👤 Instagram profile link or @username\n\n"
            "Send a link and I'll ask whether to download it, identify the movie, "
            "or turn it into music.\n"
            "Send a profile and I'll show its info, posts and stories."
        ),
        "ru": (
            "🎬 AI Movie Finder\n\n"
            "Отправь скриншот, короткое видео или ссылку с YouTube/Instagram,\n"
            "и я найду название фильма или сериала.\n\n"
            "📸 Скриншот\n"
            "🎥 Видеофайл\n"
            "🔗 Ссылка YouTube / Instagram Reels\n"
            "👤 Ссылка на профиль Instagram или @username\n\n"
            "Пришли ссылку — и я спрошу: скачать видео, найти фильм "
            "или сделать из него музыку.\n"
            "Пришли профиль — покажу информацию, публикации и истории."
        ),
        "uz": (
            "🎬 AI Movie Finder\n\n"
            "Skrinshot, qisqa video yoki YouTube/Instagram havolasini yubor,\n"
            "men film yoki serial nomini topib beraman.\n\n"
            "📸 Skrinshot\n"
            "🎥 Video fayl\n"
            "🔗 YouTube / Instagram Reels havolasi\n"
            "👤 Instagram profil havolasi yoki @username\n\n"
            "Havola yuborsangiz, so'rayman: videoni yuklab beraymi, kinoni topaymi "
            "yoki musiqaga o'giraymi.\n"
            "Profil yuborsangiz, ma'lumotlari, postlari va story'larini ko'rsataman."
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
    "link_action_prompt": {
        "en": "🔗 Link received. What should I do with it?",
        "ru": "🔗 Ссылка получена. Что с ней сделать?",
        "uz": "🔗 Havola qabul qilindi. Buning bilan nima qilay?",
    },
    "action_download_video": {
        "en": "📥 Download video",
        "ru": "📥 Скачать видео",
        "uz": "📥 Videoni yuklab olish",
    },
    "action_find_movie": {
        "en": "🎬 Find the movie",
        "ru": "🎬 Найти фильм",
        "uz": "🎬 Kino sifatida qidirish",
    },
    "action_extract_audio": {
        "en": "🎵 Convert to music",
        "ru": "🎵 Сделать музыкой",
        "uz": "🎵 Musiqaga o'girish",
    },
    "downloading_video": {
        "en": "📥 Downloading video...",
        "ru": "📥 Скачиваю видео...",
        "uz": "📥 Video yuklanmoqda...",
    },
    "extracting_audio": {
        "en": "🎵 Converting to music...",
        "ru": "🎵 Конвертирую в музыку...",
        "uz": "🎵 Musiqaga o'girilmoqda...",
    },
    "link_expired": {
        "en": "This link has expired. Please send it again.",
        "ru": "Срок действия этой ссылки истёк. Отправьте её снова.",
        "uz": "Bu havolaning muddati tugadi. Qaytadan yuboring.",
    },
    "file_too_large_to_send": {
        "en": "The file is over 50 MB, so Telegram won't let me send it. Try a shorter clip.",
        "ru": "Файл больше 50 МБ, Telegram не позволяет его отправить. Попробуйте более короткий ролик.",
        "uz": "Fayl 50 MB dan katta, Telegram uni yubora olmaydi. Qisqaroq video sinab ko'ring.",
    },
    "audio_error": {
        "en": "Couldn't convert that link to music. Make sure it's a public link and try again.",
        "ru": "Не удалось преобразовать ссылку в музыку. Убедитесь, что ссылка публичная, и попробуйте снова.",
        "uz": "Havolani musiqaga o'girib bo'lmadi. Havola ochiq (public) ekanini tekshirib, qaytadan urinib ko'ring.",
    },
    "media_too_long": {
        "en": "This video is too long for that. Please send a shorter one.",
        "ru": "Это видео слишком длинное для такой операции. Отправьте покороче.",
        "uz": "Bu video buning uchun juda uzun. Qisqaroq video yuboring.",
    },
    "ig_looking_up": {
        "en": "🔎 Looking up @{username}...",
        "ru": "🔎 Ищу профиль @{username}...",
        "uz": "🔎 @{username} profili qidirilmoqda...",
    },
    "ig_profile_not_found": {
        "en": "No Instagram account found with that username.",
        "ru": "Аккаунт Instagram с таким именем не найден.",
        "uz": "Bunday nomli Instagram akkaunti topilmadi.",
    },
    "ig_private": {
        "en": "🔒 This account is private, so only the profile picture is available.",
        "ru": "🔒 Это закрытый аккаунт, доступна только фотография профиля.",
        "uz": "🔒 Bu yopiq akkaunt, faqat profil rasmi mavjud.",
    },
    "ig_auth_error": {
        "en": "Instagram is asking me to log in. The session has expired — please tell the admin to refresh the cookies.",
        "ru": "Instagram требует входа. Сессия истекла — сообщите админу, чтобы он обновил cookies.",
        "uz": "Instagram tizimga kirishni so'ramoqda. Sessiya muddati tugagan — administratorga cookie'larni yangilashini ayting.",
    },
    "ig_rate_limited": {
        "en": "Instagram is rate-limiting me right now. Please try again in a few minutes.",
        "ru": "Instagram сейчас ограничивает запросы. Попробуйте через несколько минут.",
        "uz": "Instagram hozir so'rovlarni cheklayapti. Bir necha daqiqadan keyin urinib ko'ring.",
    },
    "ig_error": {
        "en": "Couldn't reach Instagram right now. Please try again in a moment.",
        "ru": "Сейчас не удалось связаться с Instagram. Попробуйте чуть позже.",
        "uz": "Hozir Instagram bilan bog'lana olmadim. Birozdan keyin urinib ko'ring.",
    },
    "ig_no_posts": {
        "en": "This account has no downloadable posts.",
        "ru": "У этого аккаунта нет доступных для скачивания публикаций.",
        "uz": "Bu akkauntda yuklab olsa bo'ladigan post yo'q.",
    },
    "ig_no_stories": {
        "en": "No active stories right now.",
        "ru": "Сейчас нет активных историй.",
        "uz": "Hozircha faol story yo'q.",
    },
    "ig_fetching_posts": {
        "en": "📥 Fetching the latest posts...",
        "ru": "📥 Загружаю последние публикации...",
        "uz": "📥 So'nggi postlar yuklanmoqda...",
    },
    "ig_fetching_stories": {
        "en": "📸 Fetching stories...",
        "ru": "📸 Загружаю истории...",
        "uz": "📸 Story'lar yuklanmoqda...",
    },
    "ig_fetching_pic": {
        "en": "🖼 Fetching the profile picture...",
        "ru": "🖼 Загружаю фото профиля...",
        "uz": "🖼 Profil rasmi yuklanmoqda...",
    },
    "ig_send_failed": {
        "en": "Found the media but couldn't send it. Instagram links expire quickly — try again.",
        "ru": "Медиа найдено, но отправить не удалось. Ссылки Instagram быстро истекают — попробуйте снова.",
        "uz": "Media topildi, lekin yuborib bo'lmadi. Instagram havolalari tez eskiradi — qaytadan urinib ko'ring.",
    },
    "action_ig_posts": {
        "en": "📥 Latest posts",
        "ru": "📥 Последние публикации",
        "uz": "📥 So'nggi postlar",
    },
    "action_ig_stories": {
        "en": "📸 Stories",
        "ru": "📸 Истории",
        "uz": "📸 Story'lar",
    },
    "action_ig_stories_active": {
        "en": "📸 Stories · Active now 🔴",
        "ru": "📸 Истории · Сейчас активна 🔴",
        "uz": "📸 Story'lar · Hozir faol 🔴",
    },
    "ig_changes_header": {
        "en": "🆕 Changed since last check:",
        "ru": "🆕 Изменилось с прошлой проверки:",
        "uz": "🆕 Oldingi tekshiruvdan beri o'zgarganlar:",
    },
    "ig_diff_avatar": {
        "en": "🖼 Profile picture changed",
        "ru": "🖼 Изменилось фото профиля",
        "uz": "🖼 Profil rasmi almashtirilgan",
    },
    "ig_diff_name": {
        "en": "✏️ Display name changed",
        "ru": "✏️ Изменилось отображаемое имя",
        "uz": "✏️ Ismi (full name) o'zgargan",
    },
    "ig_diff_bio": {
        "en": "📝 Bio changed",
        "ru": "📝 Изменилось описание (bio)",
        "uz": "📝 Bio (tavsif) o'zgargan",
    },
    "ig_diff_highlights_up": {
        "en": "✨ New highlight added",
        "ru": "✨ Добавлен новый хайлайт",
        "uz": "✨ Yangi highlight qo'shilgan",
    },
    "ig_diff_highlights_down": {
        "en": "🗑 A highlight was removed",
        "ru": "🗑 Хайлайт был удалён",
        "uz": "🗑 Highlight o'chirilgan",
    },
    "action_profile_pic": {
        "en": "🖼 Profile picture (HD)",
        "ru": "🖼 Фото профиля (HD)",
        "uz": "🖼 Profil rasmi (HD)",
    },
    "ig_followers_label": {"en": "Followers", "ru": "Подписчики", "uz": "Obunachilar"},
    "ig_following_label": {"en": "Following", "ru": "Подписки", "uz": "Obunalari"},
    "ig_posts_label": {"en": "Posts", "ru": "Публикации", "uz": "Postlar"},
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
    "also_maybe": {"en": "Maybe also", "ru": "Возможно также", "uz": "Balki yana"},
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
