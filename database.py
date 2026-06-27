import aiosqlite
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = "tattoo.db"
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS slots 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, time TEXT, is_booked INTEGER DEFAULT 0)""")
        
        # Добавил сюда date и time, чтобы они сохранялись
        await db.execute("""CREATE TABLE IF NOT EXISTS appointments 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, username TEXT, 
             date TEXT, time TEXT, description TEXT, status TEXT DEFAULT 'pending', price TEXT)""")
        await db.commit()

# Функция для мастера: добавить слот
async def add_slot(date, time):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO slots (date, time, is_booked) VALUES (?, ?, 0)", (date, time))
        await db.commit()

# Добавь эту функцию в свой файл database.py
async def get_times(date):
    async with aiosqlite.connect(DB_PATH) as db:
        # Получаем время для конкретной даты, где слот еще не забронирован
        async with db.execute("SELECT time FROM slots WHERE date = ? AND is_booked = 0", (date,)) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

async def get_slot_by_id(slot_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT date, time FROM slots WHERE id = ?", (slot_id,)) as cursor:
            return await cursor.fetchone()

# Функция для клиента: получить свободные даты
async def get_free_dates():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT DISTINCT date FROM slots WHERE is_booked = 0") as cursor:
            return [row[0] for row in await cursor.fetchall()]
# Добавь это в database.py
async def get_all_slots():
    async with aiosqlite.connect(DB_PATH) as db:
        # Получаем все свободные слоты, отсортированные по дате и времени
        async with db.execute("SELECT id, date, time FROM slots WHERE is_booked = 0 ORDER BY date, time") as cursor:
            return await cursor.fetchall() # Возвращает список кортежей (id, date, time)

async def add_appointment(client_id, username, date, time, description):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO appointments (client_id, username, date, time, description, status) VALUES (?,?,?,?,?,?)",
            (client_id, username, date, time, description, 'pending'))
        await db.commit()
        return cursor.lastrowid

async def get_appointment(app_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT client_id, date, time FROM appointments WHERE id = ?", (app_id,)) as cursor:
            return await cursor.fetchone()

async def update_appointment(app_id, status, price):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE appointments SET status = ?, price = ? WHERE id = ?", (status, price, app_id))
        await db.commit()

async def book_slot(slot_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE slots SET is_booked = 1 WHERE id = ?", (slot_id,))
        await db.commit()

async def remove_slot(slot_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM slots WHERE id = ?", (slot_id,))
        await db.commit()