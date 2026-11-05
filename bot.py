import asyncio
import logging
import os
from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiosqlite
from dotenv import load_dotenv

load_dotenv()
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DB_PATH = os.getenv("DB_PATH", "white_deer.db")
POLL_INTERVAL_SECONDS = int(os.getenv("REMINDER_POLL_SECONDS", "20"))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("white_deer")

dp = Dispatcher()

MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Today"), KeyboardButton(text="Tasks")],
        [KeyboardButton(text="Reminders"), KeyboardButton(text="Notes")],
        [KeyboardButton(text="Habits"), KeyboardButton(text="Help")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Choose a tool or type a command",
)


async def db_connect():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    return db


async def init_db():
    async with await db_connect() as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                timezone TEXT NOT NULL DEFAULT 'UTC'
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                due_date TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                body TEXT NOT NULL,
                remind_at_utc TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS habits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS habit_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                habit_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                check_date TEXT NOT NULL,
                FOREIGN KEY(habit_id) REFERENCES habits(id),
                UNIQUE(habit_id, check_date)
            );

            CREATE INDEX IF NOT EXISTS idx_reminders_due
                ON reminders(status, remind_at_utc);
            CREATE INDEX IF NOT EXISTS idx_tasks_user_status
                ON tasks(user_id, status);
            """
        )
        await db.commit()


async def ensure_user(user_id: int):
    async with await db_connect() as db:
        await db.execute(
            "INSERT OR IGNORE INTO users(user_id, timezone) VALUES (?, 'UTC')",
            (user_id,),
        )
        await db.commit()


async def get_timezone(user_id: int) -> ZoneInfo:
    await ensure_user(user_id)
    async with await db_connect() as db:
        cur = await db.execute("SELECT timezone FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
    try:
        return ZoneInfo(row["timezone"] if row else "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def local_now(tz: ZoneInfo) -> datetime:
    return datetime.now(tz)


def main_menu_text() -> str:
    return (
        "<b>Welcome to White Deer</b>\n"
        "Your personal organizer for tasks, reminders, notes, and habits.\n\n"
        "Choose a tool below or use /help to see all commands."
    )


@dp.message(CommandStart())
async def start(message: Message):
    await ensure_user(message.from_user.id)
    await message.answer(main_menu_text(), reply_markup=MENU)


@dp.message(Command("help"))
@dp.message(F.text == "Help")
async def help_command(message: Message):
    text = (
        "<b>White Deer commands</b>\n\n"
        "/today — view today's tasks and reminders\n"
        "/tasks — list your open tasks\n"
        "/addtask Task title — create a task\n"
        "/done TASK_ID — complete a task\n"
        "/remind YYYY-MM-DD HH:MM Message — schedule a reminder\n"
        "/reminders — list upcoming reminders\n"
        "/note Your note — save a note\n"
        "/notes — view your recent notes\n"
        "/addhabit Habit name — create a habit\n"
        "/habits — list your habits\n"
        "/checkhabit HABIT_ID — mark a habit complete today\n"
        "/timezone Area/City — set your timezone, e.g. Africa/Lagos\n"
        "/help — show this help"
    )
    await message.answer(text, reply_markup=MENU)


@dp.message(Command("timezone"))
async def set_timezone(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Usage: /timezone Africa/Lagos")
        return
    tz_name = parts[1].strip()
    try:
        ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        await message.answer("I couldn't recognize that timezone. Use an IANA name such as Europe/London or Africa/Lagos.")
        return
    await ensure_user(message.from_user.id)
    async with await db_connect() as db:
        await db.execute("UPDATE users SET timezone = ? WHERE user_id = ?", (tz_name, message.from_user.id))
        await db.commit()
    await message.answer(f"Timezone set to <b>{escape(tz_name)}</b>.")


@dp.message(Command("addtask"))
async def add_task(message: Message):
    title = (message.text or "").partition(" ")[2].strip()
    if not title:
        await message.answer("Usage: /addtask Finish project proposal")
        return
    await ensure_user(message.from_user.id)
    async with await db_connect() as db:
        cur = await db.execute(
            "INSERT INTO tasks(user_id, title, created_at) VALUES (?, ?, ?)",
            (message.from_user.id, title[:500], now_utc_iso()),
        )
        task_id = cur.lastrowid
        await db.commit()
    await message.answer(f"Task added: <b>#{task_id}</b> — {escape(title[:500])}")


@dp.message(Command("tasks"))
@dp.message(F.text == "Tasks")
async def list_tasks(message: Message):
    await ensure_user(message.from_user.id)
    async with await db_connect() as db:
        cur = await db.execute(
            "SELECT id, title, due_date FROM tasks WHERE user_id = ? AND status = 'open' ORDER BY id DESC LIMIT 30",
            (message.from_user.id,),
        )
        rows = await cur.fetchall()
    if not rows:
        await message.answer("You have no open tasks. Add one with /addtask Task title.")
        return
    lines = ["<b>Your open tasks</b>"]
    for row in rows:
        due = f" (due {escape(row['due_date'])})" if row["due_date"] else ""
        lines.append(f"#{row['id']} — {escape(row['title'])}{due}")
    lines.append("\nComplete a task with /done TASK_ID.")
    await message.answer("\n".join(lines))


@dp.message(Command("done"))
async def complete_task(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Usage: /done TASK_ID")
        return
    task_id = int(parts[1])
    async with await db_connect() as db:
        cur = await db.execute(
            "UPDATE tasks SET status = 'done' WHERE id = ? AND user_id = ? AND status = 'open'",
            (task_id, message.from_user.id),
        )
        await db.commit()
    if cur.rowcount:
        await message.answer(f"Task #{task_id} marked complete.")
    else:
        await message.answer("I couldn't find an open task with that ID in your account.")


@dp.message(Command("remind"))
async def add_reminder(message: Message):
    parts = (message.text or "").split(maxsplit=3)
    if len(parts) != 4:
        await message.answer(
            "Usage: /remind YYYY-MM-DD HH:MM Reminder text\n"
            "Example: /remind 2026-11-05 18:30 Review my notes"
        )
        return
    _, date_part, time_part, body = parts
    tz = await get_timezone(message.from_user.id)
    try:
        local_dt = datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        remind_at = local_dt.astimezone(timezone.utc)
    except ValueError:
        await message.answer("Please use the date format YYYY-MM-DD and time format HH:MM (24-hour clock).")
        return
    if remind_at <= datetime.now(timezone.utc):
        await message.answer("That time is in the past. Please choose a future date and time.")
        return
    async with await db_connect() as db:
        cur = await db.execute(
            "INSERT INTO reminders(user_id, body, remind_at_utc, created_at) VALUES (?, ?, ?, ?)",
            (message.from_user.id, body[:500], remind_at.replace(microsecond=0).isoformat(), now_utc_iso()),
        )
        reminder_id = cur.lastrowid
        await db.commit()
    local_label = local_dt.strftime("%Y-%m-%d %H:%M")
    await message.answer(
        f"Reminder #{reminder_id} saved for <b>{local_label}</b> ({escape(tz.key)})."
    )


@dp.message(Command("reminders"))
@dp.message(F.text == "Reminders")
async def list_reminders(message: Message):
    await ensure_user(message.from_user.id)
    tz = await get_timezone(message.from_user.id)
    async with await db_connect() as db:
        cur = await db.execute(
            "SELECT id, body, remind_at_utc FROM reminders WHERE user_id = ? AND status = 'pending' ORDER BY remind_at_utc LIMIT 20",
            (message.from_user.id,),
        )
        rows = await cur.fetchall()
    if not rows:
        await message.answer("You have no upcoming reminders. Create one with /remind.")
        return
    lines = ["<b>Your upcoming reminders</b>"]
    for row in rows:
        dt = datetime.fromisoformat(row["remind_at_utc"]).astimezone(tz)
        lines.append(f"#{row['id']} — {escape(row['body'])}\n   {dt.strftime('%Y-%m-%d %H:%M')}")
    await message.answer("\n".join(lines))


@dp.message(Command("note"))
async def save_note(message: Message):
    body = (message.text or "").partition(" ")[2].strip()
    if not body:
        await message.answer("Usage: /note Remember the book recommendation")
        return
    await ensure_user(message.from_user.id)
    async with await db_connect() as db:
        cur = await db.execute(
            "INSERT INTO notes(user_id, body, created_at) VALUES (?, ?, ?)",
            (message.from_user.id, body[:4000], now_utc_iso()),
        )
        note_id = cur.lastrowid
        await db.commit()
    await message.answer(f"Note saved as <b>#{note_id}</b>.")


@dp.message(Command("notes"))
@dp.message(F.text == "Notes")
async def list_notes(message: Message):
    await ensure_user(message.from_user.id)
    async with await db_connect() as db:
        cur = await db.execute(
            "SELECT id, body, created_at FROM notes WHERE user_id = ? ORDER BY id DESC LIMIT 10",
            (message.from_user.id,),
        )
        rows = await cur.fetchall()
    if not rows:
        await message.answer("You haven't saved any notes yet. Use /note Your note.")
        return
    lines = ["<b>Your recent notes</b>"]
    for row in rows:
        created = row["created_at"][:10]
        preview = row["body"] if len(row["body"]) <= 300 else row["body"][:297] + "..."
        lines.append(f"#{row['id']} ({created})\n{escape(preview)}")
    await message.answer("\n\n".join(lines))


@dp.message(Command("addhabit"))
async def add_habit(message: Message):
    title = (message.text or "").partition(" ")[2].strip()
    if not title:
        await message.answer("Usage: /addhabit Read for 15 minutes")
        return
    await ensure_user(message.from_user.id)
    async with await db_connect() as db:
        cur = await db.execute(
            "INSERT INTO habits(user_id, title, created_at) VALUES (?, ?, ?)",
            (message.from_user.id, title[:200], now_utc_iso()),
        )
        habit_id = cur.lastrowid
        await db.commit()
    await message.answer(f"Habit added: <b>#{habit_id}</b> — {escape(title[:200])}")


@dp.message(Command("habits"))
@dp.message(F.text == "Habits")
async def list_habits(message: Message):
    await ensure_user(message.from_user.id)
    tz = await get_timezone(message.from_user.id)
    today = local_now(tz).date().isoformat()
    async with await db_connect() as db:
        cur = await db.execute(
            """
            SELECT h.id, h.title,
                   EXISTS(SELECT 1 FROM habit_checks c WHERE c.habit_id = h.id AND c.check_date = ?) AS checked
            FROM habits h
            WHERE h.user_id = ? AND h.active = 1
            ORDER BY h.id DESC
            """,
            (today, message.from_user.id),
        )
        rows = await cur.fetchall()
    if not rows:
        await message.answer("No habits yet. Create one with /addhabit Habit name.")
        return
    lines = ["<b>Your habits today</b>"]
    for row in rows:
        state = "Done today" if row["checked"] else f"Use /checkhabit {row['id']} to complete"
        lines.append(f"#{row['id']} — {escape(row['title'])} ({state})")
    await message.answer("\n".join(lines))


@dp.message(Command("checkhabit"))
async def check_habit(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Usage: /checkhabit HABIT_ID")
        return
    habit_id = int(parts[1])
    tz = await get_timezone(message.from_user.id)
    today = local_now(tz).date().isoformat()
    async with await db_connect() as db:
        cur = await db.execute(
            "SELECT id FROM habits WHERE id = ? AND user_id = ? AND active = 1",
            (habit_id, message.from_user.id),
        )
        habit = await cur.fetchone()
        if not habit:
            await message.answer("I couldn't find that habit in your account.")
            return
        await db.execute(
            "INSERT OR IGNORE INTO habit_checks(habit_id, user_id, check_date) VALUES (?, ?, ?)",
            (habit_id, message.from_user.id, today),
        )
        await db.commit()
    await message.answer("Habit marked complete for today.")


@dp.message(Command("today"))
@dp.message(F.text == "Today")
async def today(message: Message):
    await ensure_user(message.from_user.id)
    tz = await get_timezone(message.from_user.id)
    today_date = local_now(tz).date().isoformat()
    async with await db_connect() as db:
        cur = await db.execute(
            "SELECT id, title FROM tasks WHERE user_id = ? AND status = 'open' ORDER BY id DESC LIMIT 20",
            (message.from_user.id,),
        )
        tasks = await cur.fetchall()
        cur = await db.execute(
            "SELECT body, remind_at_utc FROM reminders WHERE user_id = ? AND status = 'pending' ORDER BY remind_at_utc LIMIT 20",
            (message.from_user.id,),
        )
        reminders = await cur.fetchall()
    lines = [f"<b>Your day — {today_date}</b>", "", "<b>Open tasks</b>"]
    lines.extend([f"#{r['id']} — {escape(r['title'])}" for r in tasks] or ["No open tasks."])
    lines.extend(["", "<b>Upcoming reminders</b>"])
    todays_reminders = [
        r for r in reminders
        if datetime.fromisoformat(r["remind_at_utc"]).astimezone(tz).date().isoformat() == today_date
    ]
    lines.extend([
        f"{datetime.fromisoformat(r['remind_at_utc']).astimezone(tz).strftime('%H:%M')} — {escape(r['body'])}"
        for r in todays_reminders
    ] or ["No reminders scheduled for today."])
    await message.answer("\n".join(lines), reply_markup=MENU)


async def reminder_worker(bot: Bot):
    while True:
        try:
            now = now_utc_iso()
            async with await db_connect() as db:
                cur = await db.execute(
                    "SELECT id, user_id, body FROM reminders WHERE status = 'pending' AND remind_at_utc <= ? ORDER BY remind_at_utc LIMIT 100",
                    (now,),
                )
                due = await cur.fetchall()
            for reminder in due:
                try:
                    await bot.send_message(
                        reminder["user_id"],
                        f"<b>White Deer reminder</b>\n{escape(reminder['body'])}",
                    )
                    async with await db_connect() as db:
                        await db.execute(
                            "UPDATE reminders SET status = 'sent' WHERE id = ? AND status = 'pending'",
                            (reminder["id"],),
                        )
                        await db.commit()
                except Exception:
                    logger.exception("Could not deliver reminder id=%s", reminder["id"])
        except Exception:
            logger.exception("Reminder worker iteration failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Copy .env.example to .env and add your Telegram bot token.")
    await init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    worker = asyncio.create_task(reminder_worker(bot))
    try:
        await dp.start_polling(bot)
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
