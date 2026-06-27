import asyncio
import aiosqlite
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import database

TOKEN = '8741319740:AAH2F8hMfv18lWlIl8d-qgVPIEBohFrBQI0'
MASTER_IDS = [2117254464, 455239362]

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- Заглушка для Render (Web Service) ---
async def handle(request):
    return web.Response(text="Bot is running")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started on port {port}")

# --- Состояния ---
class Booking(StatesGroup):
    waiting_for_time = State()
    waiting_for_desc = State()
    waiting_for_price = State()

# --- Обработчики ---
@dp.message(Command("start"))
async def start(message: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Записаться")]], resize_keyboard=True)
    await message.answer("Привет! Нажми кнопку для записи.", reply_markup=kb)

@dp.message(F.text == "Записаться")
async def choose_all(message: types.Message):
    slots = await database.get_all_slots()
    if not slots:
        await message.answer("Свободных записей пока нет.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{slot[1]} — {slot[2]}", callback_data=f"slot_{slot[0]}")] 
        for slot in slots
    ])
    await message.answer("Выберите дату и время:", reply_markup=kb)

@dp.callback_query(F.data.startswith("slot_"))
async def select_slot(callback: types.CallbackQuery, state: FSMContext):
    slot_id = callback.data.split("_")[1]
    slot_info = await database.get_slot_by_id(slot_id) 
    if slot_info:
        await state.update_data(date=slot_info[0], time=slot_info[1])
        await callback.message.answer("Пришлите фото эскиза или опишите тату:")
        await state.set_state(Booking.waiting_for_desc)
    else:
        await callback.message.answer("Ошибка: этот слот уже занят или удален.")
    await callback.answer()

@dp.message(Booking.waiting_for_desc)
async def finish(msg: Message, state: FSMContext):
    data = await state.get_data()
    if 'date' not in data or 'time' not in data:
        await msg.answer("Ошибка: данные записи не найдены. Попробуйте снова.")
        await state.clear()
        return

    photo_id = msg.photo[-1].file_id if msg.photo else None
    username = msg.from_user.username or "без никнейма"
    app_id = await database.add_appointment(msg.from_user.id, username, data['date'], data['time'], msg.text or "")
    
    text = (f"🔔 Новая запись!\n👤 Клиент: @{username}\n📅 Дата: {data['date']}\n⏰ Время: {data['time']}\n📝 Описание: {msg.text or 'Без описания'}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{app_id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"decline_{app_id}")]
    ])
    
    for m_id in MASTER_IDS:
        try:
            if photo_id: await bot.send_photo(m_id, photo=photo_id, caption=text, reply_markup=kb)
            else: await bot.send_message(m_id, text, reply_markup=kb)
        except Exception as e: print(f"Ошибка отправки мастеру: {e}")
    await msg.answer("Заявка успешно отправлена мастеру!")
    await state.clear()

@dp.callback_query(F.data.startswith("accept_"))
async def accept(callback: types.CallbackQuery, state: FSMContext):
    app_id = callback.data.split("_")[1]
    await state.update_data(app_id=app_id)
    await callback.message.answer("Запись принята! Введите цену для клиента:")
    await state.set_state(Booking.waiting_for_price)
    await callback.answer()

@dp.message(Booking.waiting_for_price)
async def price_set(message: types.Message, state: FSMContext):
    data = await state.get_data()
    info = await database.get_appointment(data['app_id'])
    await database.update_appointment(data['app_id'], 'accepted', message.text)
    await bot.send_message(info[0], f"✅ Запись подтверждена! {info[1]} в {info[2]}. Цена: {message.text}")
    await message.answer("Клиент уведомлен.")
    await state.clear()

# --- Главная функция запуска ---
async def main():
    await database.init_db()
    # Запускаем сервер заглушку для Render
    await start_web_server()
    # Запускаем бота
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())