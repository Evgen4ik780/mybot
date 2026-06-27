import asyncio
import aiosqlite
import os
from aiohttp import web
import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import database

TOKEN = '8741319740:AAH2F8hMfv18lWlIl8d-qgVPIEBohFrBQI0'
MASTER_IDS = [2117254464, 455239362] # Список ID мастеров

bot = Bot(token=TOKEN)
dp = Dispatcher()


class Booking(StatesGroup):
    waiting_for_time = State()
    waiting_for_desc = State()
    waiting_for_price = State()

@dp.message(Command("start"))
async def start(message: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Записаться")]], resize_keyboard=True)
    await message.answer("Привет! Нажми кнопку для записи.", reply_markup=kb)

@dp.message(F.text == "Записаться")
async def choose_all(message: types.Message):
    slots = await database.get_all_slots() # Берем всё сразу
    if not slots:
        await message.answer("Свободных записей пока нет.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{slot[1]} — {slot[2]}", callback_data=f"slot_{slot[0]}")] 
        for slot in slots
    ])
    await message.answer("Выберите дату и время:", reply_markup=kb)

# Новый обработчик для выбора конкретного слота
@dp.callback_query(F.data.startswith("slot_"))
async def select_slot(callback: types.CallbackQuery, state: FSMContext):
    slot_id = callback.data.split("_")[1]
    
    # ВАЖНО: Нам нужно получить данные этого слота из базы, 
    # чтобы знать дату и время, и сохранить их в state!
    # Добавим функцию в database.py для этого (см. ниже)
    slot_info = await database.get_slot_by_id(slot_id) 
    
    # slot_info вернет кортеж (date, time)
    if slot_info:
        await state.update_data(date=slot_info[0], time=slot_info[1])
        await callback.message.answer("Пришлите фото эскиза или опишите тату:")
        await state.set_state(Booking.waiting_for_desc)
    else:
        await callback.message.answer("Ошибка: этот слот уже занят или удален.")

@dp.callback_query(F.data.startswith("date_"))
async def select_date(callback: types.CallbackQuery, state: FSMContext):
    # Уведомляем Telegram, что нажатие принято (предотвращает зависание кнопки)
    await callback.answer() 
    chosen_date = callback.data.split("_")[1]
    
    print(f"DEBUG: Получаю время для даты: {chosen_date}") # Лог в консоль
    
    # Получаем время
    times = await database.get_times(chosen_date)
    
    print(f"DEBUG: Найдено слотов: {len(times)}") # Лог в консоль
    
    if not times:
        await callback.message.answer("На эту дату нет свободного времени.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⏰ {t}", callback_data=f"time_{t}")] for t in times
    ])
    
    await callback.message.edit_text("Выберите время:", reply_markup=kb)
    await state.update_data(date=chosen_date)

@dp.message(Command("add_slot"))
async def add_slot_cmd(message: types.Message):
    if message.from_user.id not in MASTER_IDS: return
    # Пример команды: /add_slot 28.06 14:00
    args = message.text.split()
    if len(args) == 3:
        await database.add_slot(args[1], args[2])
        await message.answer(f"Слот {args[1]} в {args[2]} добавлен!")

@dp.message(Booking.waiting_for_time)
async def select_time(message: types.Message, state: FSMContext):
    await state.update_data(time=message.text)
    await message.answer("Пришлите фото эскиза или опишите тату:")
    await state.set_state(Booking.waiting_for_desc)

@dp.message(Booking.waiting_for_desc)
async def finish(msg: Message, state: FSMContext):
    # 1. Получаем данные из FSM
    data = await state.get_data()
    
    # ПРОВЕРКА: Если даты нет в памяти, сообщаем пользователю
    if 'date' not in data or 'time' not in data:
        await msg.answer("Произошла ошибка: информация о записи не найдена. Попробуйте записаться снова через /start")
        await state.clear()
        return

    # 2. Получаем ID фото
    photo_id = msg.photo[-1].file_id if msg.photo else None
    
    # 3. Формируем текст
    username = msg.from_user.username or "без никнейма"
    
    # Сохраняем в БД
    app_id = await database.add_appointment(
        msg.from_user.id, username, data['date'], data['time'], msg.text or ""
    )
    
    text = (f"🔔 Новая запись!\n"
            f"👤 Клиент: @{username}\n"
            f"📅 Дата: {data['date']}\n"
            f"⏰ Время: {data['time']}\n"
            f"📝 Описание: {msg.text or 'Без описания'}")
    
    # 4. Отправка мастеру
    # В функции finish в main.py измените создание клавиатуры:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{app_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"decline_{app_id}")
        ]
    ])
    
    for m_id in MASTER_IDS:
        try:
            if photo_id:
                await bot.send_photo(m_id, photo=photo_id, caption=text, reply_markup=kb)
            else:
                await bot.send_message(m_id, text, reply_markup=kb)
        except Exception as e:
            print(f"Ошибка при отправке мастеру: {e}")
        
    await msg.answer("Заявка успешно отправлена мастеру!")
    await state.clear()

@dp.callback_query(F.data.startswith("accept_"))
async def accept(callback: types.CallbackQuery, state: FSMContext):
    # Разделяем данные, чтобы получить app_id
    try:
        app_id = callback.data.split("_")[1]
        await state.update_data(app_id=app_id)
        
        # Получаем данные записи, чтобы найти slot_id и забронировать его
        info = await database.get_appointment(app_id) # вернет (client_id, date, time)
        
        if info:
            # Ищем ID слота по дате и времени в таблице slots
            async with aiosqlite.connect(database.DB_PATH) as db:
                async with db.execute("SELECT id FROM slots WHERE date = ? AND time = ?", (info[1], info[2])) as cursor:
                    slot = await cursor.fetchone()
                    if slot:
                        await database.book_slot(slot[0]) # Ставим is_booked = 1
            
            # Отвечаем мастеру
            await callback.message.answer("Запись принята! Введите цену для клиента:")
            await state.set_state(Booking.waiting_for_price)
        else:
            await callback.message.answer("Ошибка: запись не найдена в базе данных.")
            
    except Exception as e:
        print(f"Ошибка при принятии заявки: {e}")
        await callback.message.answer("Произошла ошибка при обработке заявки.")
    
    await callback.answer()

@dp.callback_query(F.data.startswith("decline_"))
async def decline(callback: types.CallbackQuery):
    app_id = callback.data.split("_")[1]
    
    # 1. Сначала получаем информацию о записи (включая client_id)
    # Функция get_appointment возвращает (client_id, date, time)
    appointment_info = await database.get_appointment(app_id)
    
    if appointment_info:
        client_id = appointment_info[0] # Получаем ID клиента
        
        # 2. Обновляем статус в базе данных на 'declined'
        await database.update_appointment(app_id, 'declined', "0")
        
        # 3. Уведомляем клиента
        try:
            await bot.send_message(
                client_id, 
                f"К сожалению, мастер отклонил вашу запись на {appointment_info[1]} в {appointment_info[2]}."
            )
        except Exception as e:
            print(f"Не удалось отправить сообщение клиенту: {e}")
    
    # 4. Обновляем сообщение мастера
    new_text = callback.message.caption + "\n\n❌ Запись отклонена." if callback.message.caption else callback.message.text + "\n\n❌ Запись отклонена."
    
    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=new_text, reply_markup=None)
        else:
            await callback.message.edit_text(text=new_text, reply_markup=None)
    except Exception as e:
        print(f"Ошибка при обновлении статуса мастера: {e}")
    
    await callback.answer("Запись отклонена, клиент уведомлен")

@dp.message(Booking.waiting_for_price)
async def price_set(message: types.Message, state: FSMContext):
    data = await state.get_data()
    info = await database.get_appointment(data['app_id'])
    await database.update_appointment(data['app_id'], 'accepted', message.text)
    await bot.send_message(info[0], f"✅ Запись подтверждена! {info[1]} в {info[2]}. Цена: {message.text}")
    await message.answer("Клиент уведомлен.")
    await state.clear()

@dp.message(Command("view"))
async def view(message: types.Message):
    if message.from_user.id not in MASTER_IDS: return
    
    slots = await database.get_all_slots() # Получаем все (включая будущие или прошлые)
    if not slots:
        await message.answer("Слотов нет.")
        return
    
    text = "Список свободных слотов:\n"
    for s in slots:
        text += f"ID: {s[0]} | Дата: {s[1]} | Время: {s[2]}\n"
    await message.answer(text)

@dp.message(Command("remove"))
async def remove(message: types.Message):
    if message.from_user.id not in MASTER_IDS: return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Используй: /remove <id>")
        return
    
    slot_id = args[1]
    await database.remove_slot(slot_id)
    await message.answer(f"Слот с ID {slot_id} удален.")

async def main():
    await database.init_db() # Убедитесь, что эта строка есть
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())