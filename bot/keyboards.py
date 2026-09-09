from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from utils.i18n import t


def movie_result_keyboard(
    trailer_url: str | None, watch_url: str | None, lang: str
) -> InlineKeyboardMarkup | None:
    rows = []
    if trailer_url:
        rows.append([InlineKeyboardButton(text=t("trailer_button", lang), url=trailer_url)])
    if watch_url:
        rows.append([InlineKeyboardButton(text=t("watch_button", lang), url=watch_url)])
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


def link_action_keyboard(token: str, lang: str) -> InlineKeyboardMarkup:
    """Ask what to do with a pasted video link: download, identify, or rip the audio."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("action_download_video", lang), callback_data=f"link:video:{token}")],
            [InlineKeyboardButton(text=t("action_find_movie", lang), callback_data=f"link:movie:{token}")],
            [InlineKeyboardButton(text=t("action_extract_audio", lang), callback_data=f"link:audio:{token}")],
        ]
    )


def instagram_profile_keyboard(token: str, lang: str, is_private: bool) -> InlineKeyboardMarkup:
    """Actions on a looked-up profile. A private account exposes nothing but the
    avatar, so the post/story buttons are left off rather than offered and refused."""
    rows = [[InlineKeyboardButton(text=t("action_profile_pic", lang), callback_data=f"ig:pic:{token}")]]
    if not is_private:
        rows.insert(
            0,
            [InlineKeyboardButton(text=t("action_ig_posts", lang), callback_data=f"ig:posts:{token}")],
        )
        rows.insert(
            1,
            [InlineKeyboardButton(text=t("action_ig_stories", lang), callback_data=f"ig:stories:{token}")],
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("menu_history", lang)),
                KeyboardButton(text=t("menu_language", lang)),
            ]
        ],
        resize_keyboard=True,
    )


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang:uz"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
            ]
        ]
    )


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Overview", callback_data="admin:overview"),
                InlineKeyboardButton(text="🎬 Top movies", callback_data="admin:movies"),
            ],
            [
                InlineKeyboardButton(text="👥 Active users", callback_data="admin:active"),
                InlineKeyboardButton(text="🔄 Refresh", callback_data="admin:overview"),
            ],
        ]
    )
