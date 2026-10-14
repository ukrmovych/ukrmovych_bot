from aiogram.types import InlineKeyboardButton as Btn
from aiogram.types import InlineKeyboardMarkup

from . import texts as T
from .config import config


def _kb(*rows: list[Btn]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows])


def welcome() -> InlineKeyboardMarkup:
    return _kb([Btn(text=T.BTN_PEEK, callback_data="features")])


def features() -> InlineKeyboardMarkup:
    return _kb([Btn(text=T.BTN_NAV, callback_data="nav")])


def nav() -> InlineKeyboardMarkup:
    return _kb(
        [Btn(text=T.BTN_REPEAT, callback_data="tp:r:0")],
        [Btn(text=T.BTN_MATERIALS, callback_data="tp:m:0")],
        [Btn(text=T.BTN_OWN, callback_data="own")],
        [Btn(text=T.BTN_TIP, callback_data="tip")],
        [Btn(text=T.BTN_ADMINS, callback_data="admins")],
        [Btn(text=T.BTN_HELP, callback_data="help")],
    )


def back_to_nav() -> InlineKeyboardMarkup:
    return _kb([Btn(text=T.BTN_BACK, callback_data="nav")])


def topics(mode: str, page: int) -> InlineKeyboardMarkup:
    """mode: "r" — інтервальне повторення, "m" — допоміжні матеріали."""
    start = page * T.TOPICS_PER_PAGE
    chunk = T.TOPICS[start : start + T.TOPICS_PER_PAGE]
    action = "rs" if mode == "r" else "ms"
    rows = [[Btn(text=t.button, callback_data=f"{action}:{t.id}")] for t in chunk]
    if start + T.TOPICS_PER_PAGE < len(T.TOPICS):
        rows.append([Btn(text=T.BTN_MORE_TOPICS, callback_data=f"tp:{mode}:{page + 1}")])
    if page > 0:
        rows.append([Btn(text=T.BTN_PREV_TOPICS, callback_data=f"tp:{mode}:{page - 1}")])
    rows.append([Btn(text=T.BTN_BACK, callback_data="nav")])
    return _kb(*rows)


def _test_button(topic: T.Topic) -> Btn:
    # Пряме посилання відкривається миттєво, без запиту до бота
    if topic.test_url:
        return Btn(text=T.BTN_TEST, url=topic.test_url)
    return Btn(text=T.BTN_TEST, callback_data=f"test:{topic.id}")


def repetition(topic: T.Topic) -> InlineKeyboardMarkup:
    return _kb(
        [Btn(text=T.BTN_DO_REVIEW, callback_data=f"do:{topic.id}"), _test_button(topic)],
        [Btn(text=T.BTN_BACK, callback_data="tp:r:0")],
    )


def material(topic: T.Topic, back: str) -> InlineKeyboardMarkup:
    rows = []
    if topic.material_url:
        rows.append([Btn(text=T.BTN_OPEN_MATERIAL, url=topic.material_url)])
    rows.append([_test_button(topic)])
    rows.append([Btn(text=T.BTN_BACK, callback_data=back)])
    return _kb(*rows)


def material_from_list(topic: T.Topic) -> InlineKeyboardMarkup:
    rows = []
    if topic.material_url:
        rows.append([Btn(text=T.BTN_OPEN_MATERIAL, url=topic.material_url)])
    rows.append([_test_button(topic)])
    rows.append([Btn(text=T.BTN_START_REPEAT, callback_data=f"rs:{topic.id}")])
    rows.append([Btn(text=T.BTN_BACK, callback_data="tp:m:0")])
    return _kb(*rows)


def test_back(topic: T.Topic) -> InlineKeyboardMarkup:
    return _kb([Btn(text=T.BTN_BACK, callback_data=f"rs:{topic.id}")])


def limit() -> InlineKeyboardMarkup:
    return _kb(
        [Btn(text=T.BTN_SUBSCRIBE, url=config.subscription_url)],
        [Btn(text=T.BTN_BACK, callback_data="nav")],
    )


def tip(topic: T.Topic) -> InlineKeyboardMarkup:
    return _kb(
        [Btn(text=T.BTN_START_REPEAT, callback_data=f"rs:{topic.id}")],
        [Btn(text=T.BTN_TIP_AGAIN, callback_data="tip")],
        [Btn(text=T.BTN_BACK, callback_data="nav")],
    )


def admins() -> InlineKeyboardMarkup:
    return _kb(
        [Btn(text=T.BTN_WRITE_ADMINS, url=f"https://t.me/{config.admin_username}")],
        [Btn(text=T.BTN_BACK, callback_data="nav")],
    )


def own_list(items: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows = [[Btn(text=f"🗑 {title}", callback_data=f"od:{oid}")] for oid, title in items]
    rows.append([Btn(text=T.BTN_OWN_ADD, callback_data="oa")])
    rows.append([Btn(text=T.BTN_BACK, callback_data="nav")])
    return _kb(*rows)


def own_cancel() -> InlineKeyboardMarkup:
    return _kb([Btn(text=T.BTN_CANCEL, callback_data="own")])


def own_reminder(own_id: int) -> InlineKeyboardMarkup:
    return _kb([Btn(text=T.BTN_DONE, callback_data=f"oc:{own_id}")])
